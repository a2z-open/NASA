"""Cold-world spectra: can a model read spectral types from SPHEREx's 102 colours, and does it flag anything new?

    python -m validation.coldspec lists      # 1. known M, L, T/Y dwarfs (training) and unclassified objects, from SIMBAD
    python -m validation.coldspec extract    # 2. a SPHEREx spectrum for every object (pipeline/cubespec.py)
    python -m validation.coldspec quality    #    where the photometry is trustworthy (known objects, against 2MASS colours)
    python -m validation.coldspec train      # 3. cross-validated model: spectral type from the spectrum alone
    python -m validation.coldspec lock       # 4. lock the model, the cuts and the decision rule in the ledger
    python -m validation.coldspec apply      # 5. only then: score the unclassified objects, vet the candidates

The unclassified objects are never used to choose features, cuts or thresholds: step 4 hashes those choices before
step 5 reads any unclassified spectrum's model output.  A "candidate" here means: SIMBAD lists no spectral type, and
the SPHEREx spectrum looks like a T dwarf to a model that was validated on known ones.  It is not a confirmed
discovery; that needs a proper spectrum from a large telescope.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation' / 'coldspec'
SIMBAD_TAP = 'https://simbad.cfa.harvard.edu/simbad/sim-tap/sync'
SEED = 20261114
J_MIN, B_MIN = 11.0, 10.0          # brighter saturates SPHEREx; closer to the Galactic plane is too crowded for 12.9" pixels

COLS = 'b.oid, b.main_id, b.ra, b.dec, b.otype, b.sp_type, b.pmra, b.pmdec, b.plx_value, f.J, f.H, f.K'
JOIN = 'FROM basic AS b JOIN allfluxes AS f ON f.oidref = b.oid WHERE '
PM2 = '(b.pmra*b.pmra + b.pmdec*b.pmdec)'
NO_TYPE = "(b.sp_type IS NULL OR b.sp_type = '')"
QUERIES = {
    # ---- known types: the training set ----
    'T': f"(b.sp_type LIKE 'T%' OR b.sp_type LIKE 'Y%') AND f.J > {J_MIN} AND f.J < 17.2",
    'L': f"b.sp_type LIKE 'L%' AND f.J > {J_MIN} AND f.J < 16.5",
    'M_late': f"(b.sp_type LIKE 'M6%' OR b.sp_type LIKE 'M7%' OR b.sp_type LIKE 'M8%' OR b.sp_type LIKE 'M9%') AND f.J BETWEEN {J_MIN} AND 15.5 AND {PM2} > 10000",
    'M_mid': f"(b.sp_type LIKE 'M3%' OR b.sp_type LIKE 'M4%' OR b.sp_type LIKE 'M5%') AND f.J BETWEEN 12 AND 14.5 AND {PM2} > 40000",
    # ---- no spectral type in SIMBAD: the unknowns ----
    'U_bd': f"b.otype = 'BD?' AND {NO_TYPE} AND f.J > {J_MIN} AND f.J < 17.2",
    'U_pm': f"b.otype = 'PM*' AND {NO_TYPE} AND f.J BETWEEN 13 AND 17.2 AND f.J - f.K > 1.0 AND {PM2} > 40000",
}
CAP = {'L': 36, 'M_late': 60, 'M_mid': 30}       # per whole subtype, so no type dominates


def tap(adql: str) -> list[dict]:
    for k in range(4):
        try:
            r = requests.post(SIMBAD_TAP, data={'request': 'doQuery', 'lang': 'adql', 'format': 'csv', 'query': adql}, timeout=180)
            r.raise_for_status()
            return list(csv.DictReader(io.StringIO(r.text)))
        except requests.RequestException:
            time.sleep(3 * (k + 1))
    raise RuntimeError('SIMBAD TAP did not answer')


def numeric_type(sp: str) -> float | None:
    """M0 = 0, L0 = 10, T0 = 20, Y0 = 30.  None for giants, subdwarfs, composites and anything unclear."""
    s = (sp or '').strip()
    if not s or '+' in s or '/' in s or s.lower().startswith(('sd', 'esd', 'usd', 'd/')):
        return None
    m = re.match(r'^([MLTY])\s*(\d(?:\.\d)?)?', s)
    if not m:
        return None
    rest = s[m.end():]
    if re.search(r'I{1,3}(?!V)|\bIb|\bIa', rest) and 'V' not in rest:       # luminosity class I, II, III: a giant
        return None
    sub = float(m.group(2)) if m.group(2) else 5.0 if m.group(1) in 'LT' else None
    if sub is None:
        return None
    return {'M': 0, 'L': 10, 'T': 20, 'Y': 30}[m.group(1)] + sub


def _num(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def build_lists(log=print) -> dict:
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    rng = np.random.default_rng(SEED)
    objects, seen, counts = [], set(), {}
    for group, where in QUERIES.items():
        rows = tap(f'SELECT {COLS} {JOIN}{where}')
        keep = []
        for r in rows:
            ra, dec, j = _num(r['ra']), _num(r['dec']), _num(r['J'])
            if ra is None or dec is None or j is None or r['oid'] in seen:
                continue
            b = float(SkyCoord(ra * u.deg, dec * u.deg).galactic.b.deg)
            if abs(b) < B_MIN:
                continue
            known = not group.startswith('U_')
            nt = numeric_type(r['sp_type']) if known else None
            if known and nt is None:
                continue
            keep.append({'oid': r['oid'], 'name': r['main_id'].strip('"'), 'group': group, 'ra': ra, 'dec': dec, 'otype': r['otype'],
                         'sp_type': r['sp_type'].strip('"') if known else None, 'type_num': nt, 'pmra': _num(r['pmra']), 'pmdec': _num(r['pmdec']),
                         'plx': _num(r['plx_value']), 'J': j, 'H': _num(r['H']), 'K': _num(r['K']), 'gal_b': round(b, 2)})
        if group in CAP:                                             # an even spread over subtypes, chosen at random
            by = {}
            for o in keep:
                by.setdefault(int(o['type_num']), []).append(o)
            keep = [o for k in sorted(by) for o in [by[k][i] for i in rng.permutation(len(by[k]))[:CAP[group]]]]
        for o in keep:
            seen.add(o['oid'])
        counts[group] = {'from_simbad': len(rows), 'kept': len(keep)}
        objects += keep
        log(f"{group:8s} SIMBAD rows {len(rows):5d}  kept {len(keep):5d}")
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'source': 'SIMBAD (CDS), queried through the CfA mirror TAP service',
           'cuts': {'J_min': J_MIN, 'abs_gal_b_min': B_MIN, 'seed': SEED, 'cap_per_subtype': CAP}, 'queries': QUERIES, 'counts': counts, 'objects': objects}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'objects.json').write_text(json.dumps(doc, indent=1))
    return doc


VIZIER = 'https://vizier.cfa.harvard.edu/viz-bin/asu-tsv'          # CDS VizieR, CfA mirror
ALLWISE_EPOCH = 2010.56                                            # mean epoch of AllWISE positions


def _vizier(source: str, ra: float, dec: float, radius_arcsec: float, cols: list[str]) -> list[dict]:
    params = [('-source', source), ('-c', f'{ra:.6f} {dec:+.6f}'), ('-c.rs', f'{radius_arcsec:.1f}'), ('-out.max', '30')] + [('-out', c) for c in cols]
    for k in range(4):
        try:
            r = requests.get(VIZIER, params=params, timeout=60)
            if r.status_code == 200 and '#RESOURCE' in r.text:      # a complete answer names the catalogue it searched
                break
        except requests.RequestException:
            pass
        time.sleep(2 * (k + 1))
    else:
        return []
    lines = [ln for ln in r.text.splitlines() if ln and not ln.startswith('#')]
    if len(lines) < 4:
        return []
    names = lines[0].split('\t')
    return [dict(zip(names, ln.split('\t'))) for ln in lines[3:]]


def _sep(ra1, dec1, ra2, dec2) -> float:
    return math.hypot((ra1 - ra2) * math.cos(math.radians(dec1)), dec1 - dec2) * 3600


def _locate(o: dict) -> dict:
    """Where the object was in 2MASS (about 2000) and in AllWISE (2010.56), the motion between them, and so where it
    should be in the SPHEREx cube.  Only catalogue positions are used; no SPHEREx data."""
    tw = [{'ra': _num(r['RAJ2000']), 'dec': _num(r['DEJ2000']), 'J': _num(r.get('Jmag')), 'jd': _num(r.get('JD'))}
          for r in _vizier('II/246/out', o['ra'], o['dec'], 30, ['RAJ2000', 'DEJ2000', 'Jmag', 'JD'])]
    aw = [{'ra': _num(r['RAJ2000']), 'dec': _num(r['DEJ2000']), 'W1': _num(r.get('W1mag')), 'W2': _num(r.get('W2mag')), 'e_W2': _num(r.get('e_W2mag'))}
          for r in _vizier('II/328/allwise', o['ra'], o['dec'], 30, ['RAJ2000', 'DEJ2000', 'W1mag', 'W2mag', 'e_W2mag'])]
    tw = [t for t in tw if t['ra'] is not None]
    aw = [w for w in aw if w['ra'] is not None]
    out = {'n_2mass': len(tw), 'n_allwise': len(aw)}
    # the object in 2MASS: same J magnitude as SIMBAD quotes (SIMBAD's J is almost always the 2MASS one), closest to SIMBAD's position
    m2 = [t for t in tw if t['J'] is not None and abs(t['J'] - o['J']) <= 0.12 and _sep(t['ra'], t['dec'], o['ra'], o['dec']) <= 12]
    t2 = min(m2, key=lambda t: _sep(t['ra'], t['dec'], o['ra'], o['dec'])) if m2 else None
    t2_year = 2000.0 + (t2['jd'] - 2451545.0) / 365.25 if t2 and t2['jd'] else None
    has_pm = o['pmra'] is not None and o['pmdec'] is not None
    cosd = max(math.cos(math.radians(o['dec'])), 1e-6)
    # where it should be in AllWISE
    guesses = []
    if t2 and t2_year:
        yr = ALLWISE_EPOCH - t2_year
        guesses.append((t2['ra'] + (o['pmra'] * yr / 3.6e6 / cosd if has_pm else 0), t2['dec'] + (o['pmdec'] * yr / 3.6e6 if has_pm else 0)))
    for ep in EPOCHS:
        yr = ALLWISE_EPOCH - ep
        guesses.append((o['ra'] + (o['pmra'] * yr / 3.6e6 / cosd if has_pm else 0), o['dec'] + (o['pmdec'] * yr / 3.6e6 if has_pm else 0)))
        if not has_pm:
            break
    best = None
    for w in aw:
        d = min(_sep(w['ra'], w['dec'], g[0], g[1]) for g in guesses)
        if best is None or d < best[0]:
            best = (d, w)
    lim = 3.0 if has_pm else 10.0                 # with no known motion, allow up to about 1"/yr since 2000
    w = best[1] if best and best[0] <= lim else None
    if w:
        out.update({'allwise': {'ra': w['ra'], 'dec': w['dec'], 'W1': w['W1'], 'W2': w['W2'], 'e_W2': w['e_W2'], 'sep_arcsec': round(best[0], 2)}})
        if t2 and t2_year and ALLWISE_EPOCH - t2_year > 5:
            yr = ALLWISE_EPOCH - t2_year
            pm = ((w['ra'] - t2['ra']) * cosd * 3600 / yr, (w['dec'] - t2['dec']) * 3600 / yr)
            src = '2MASS to AllWISE'
        elif has_pm:
            pm, src = (o['pmra'] / 1000, o['pmdec'] / 1000), 'SIMBAD'
        else:
            pm, src = (0.0, 0.0), 'none'
        yr = 2000.0 + (60980.0 - 51544.5) / 365.25 - ALLWISE_EPOCH
        out.update({'pm_arcsec_yr': [round(pm[0], 4), round(pm[1], 4)], 'pm_source': src,
                    'expected': [(w['ra'] + pm[0] * yr / 3600 / cosd) % 360, w['dec'] + pm[1] * yr / 3600]})
    if t2:
        out['twomass'] = {'ra': t2['ra'], 'dec': t2['dec'], 'year': round(t2_year, 2) if t2_year else None}
    return out


def positions(log=print, workers: int = 6) -> dict:
    """2MASS and AllWISE positions for every object, and from them where to look in the SPHEREx cube."""
    objs = json.loads((OUT / 'objects.json').read_text())['objects']
    path = OUT / 'positions.json'
    have = json.loads(path.read_text()) if path.is_file() else {}

    def one(o):
        prev = have.get(o['oid'])
        if prev and 'error' not in prev and (prev.get('n_2mass') or prev.get('n_allwise')):
            return o['oid'], prev                                    # an empty answer from both catalogues is retried
        try:
            return o['oid'], _locate(o)
        except Exception as error:  # noqa: BLE001
            return o['oid'], {'error': f'{type(error).__name__}: {error}'[:100]}

    t0, done = time.time(), 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for oid, c in ex.map(one, objs):
            have[oid] = c
            done += 1
            if done % 200 == 0:
                path.write_text(json.dumps(have))
                log(f'{done}/{len(objs)} position lookups, {time.time() - t0:.0f} s')
    path.write_text(json.dumps(have))
    n = sum(1 for v in have.values() if 'expected' in v)
    log(f'AllWISE counterpart and expected position for {n} of {len(objs)} objects; motion from 2MASS to AllWISE for '
        f"{sum(1 for v in have.values() if v.get('pm_source') == '2MASS to AllWISE')}")
    return {'n': len(objs), 'located': n}


EPOCHS = [2000.0, 2010.5, 2015.4]      # SIMBAD positions are at J2000 for most objects, but at the WISE or CatWISE epoch for some


def position_at_cube(o: dict, epoch: float = 2000.0) -> tuple[float, float]:
    """SIMBAD position moved to the middle of the cube's exposures with SIMBAD's proper motion, for a given position epoch."""
    from pipeline.cubespec import MID_EPOCH_MJD
    if o['pmra'] is None or o['pmdec'] is None:
        return o['ra'], o['dec']
    yr = 2000.0 + (MID_EPOCH_MJD - 51544.5) / 365.25 - epoch
    dec = o['dec'] + o['pmdec'] * yr / 3.6e6
    ra = o['ra'] + o['pmra'] * yr / 3.6e6 / max(math.cos(math.radians(o['dec'])), 1e-6)
    return ra % 360.0, dec


def extract(log=print, workers: int = 5) -> dict:
    from pipeline import cubespec
    doc = json.loads((OUT / 'objects.json').read_text())
    objs = doc['objects']

    import os
    located = json.loads((OUT / 'positions.json').read_text()) if (OUT / 'positions.json').is_file() else {}
    cached_only = bool(os.environ.get('COLDSPEC_CACHED_ONLY'))        # use what is already downloaded; fetch nothing

    def one(o):
        ra, dec = position_at_cube(o)
        try:
            if cached_only and not (cubespec.CACHE / 'cubespec' / 'win' / f"o{o['oid']}.npz").is_file():
                raise LookupError('not downloaded yet')
            alts, labels = [], ['SIMBAD position, epoch 2000']
            if o['pmra'] is not None:
                alts += [position_at_cube(o, e) for e in EPOCHS[1:]]
                labels += ['SIMBAD position, epoch 2010.5', 'SIMBAD position, epoch 2015.4']
            c = located.get(o['oid'])
            if c and 'expected' in c:
                alts.append(tuple(c['expected']))
                labels.append('2MASS and AllWISE')
            s = cubespec.spectrum(ra, dec, key=f"o{o['oid']}", alternatives=alts or None)
            return o['oid'], {'ok': True, 'flux': s['flux_ujy'], 'err': s['err_ujy'], 'offset_pix': s['offset_pix'],
                              'near_rival': s['near_rival'], 'resid': s['resid'], 'position_from': labels[s['hypothesis']]}
        except Exception as error:  # noqa: BLE001
            return o['oid'], {'ok': False, 'why': f'{type(error).__name__}: {error}'[:120]}

    t0, done, res = time.time(), 0, {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for oid, r in ex.map(one, objs):
            res[oid] = r
            done += 1
            if done % 100 == 0:
                log(f'{done}/{len(objs)} spectra, {sum(1 for v in res.values() if v["ok"])} ok, {time.time() - t0:.0f} s')
    ok = [o for o in objs if res[o['oid']]['ok']]
    np.savez_compressed(OUT / 'spectra.npz', oid=np.array([o['oid'] for o in ok]), wave_um=cubespec.WAVES,
                        flux_ujy=np.array([res[o['oid']]['flux'] for o in ok], np.float32), err_ujy=np.array([res[o['oid']]['err'] for o in ok], np.float32),
                        offset_pix=np.array([res[o['oid']]['offset_pix'] for o in ok], np.float32),
                        near_rival=np.array([res[o['oid']]['near_rival'] for o in ok], np.float32),
                        resid=np.array([res[o['oid']]['resid'] for o in ok], np.float32),
                        position_from=np.array([res[o['oid']]['position_from'] for o in ok]))
    fails = {}
    for v in res.values():
        if not v['ok']:
            k = v['why'].split(':')[1].strip()[:40] if ':' in v['why'] else v['why']
            fails[k] = fails.get(k, 0) + 1
    summary = {'n_objects': len(objs), 'n_spectra': len(ok), 'failures': fails, 'seconds': round(time.time() - t0),
               'source': 'SPHEREx DR1 all-sky data cube (IRSA HiPS, order 5), read with HTTP byte ranges'}
    (OUT / 'extract.json').write_text(json.dumps(summary, indent=1))
    log(json.dumps(summary))
    return summary



# ---------------------------------------------------------------------------
# Features: the SHAPE of the spectrum only.  Brightness is left out on purpose: the known T dwarfs are fainter than
# the known M dwarfs, so a model given brightness could "learn" faint = cold and fool us.
# ---------------------------------------------------------------------------

EDGES = [0.75, 0.85, 0.95, 1.05, 1.15, 1.22, 1.34, 1.45, 1.52, 1.63, 1.78, 1.95, 2.05, 2.20, 2.40, 2.70, 3.10, 3.45, 3.80, 4.10, 4.40, 4.75, 5.00]
BIN_NAMES = [f'f{a:.2f}-{b:.2f}' for a, b in zip(EDGES[:-1], EDGES[1:])]
INDEX_NAMES = ['ch4_H', 'h2o_J', 'ch4_K', 'K_over_J', 'f33_over_f45', 'f45_over_J', 'Y_over_J', 'z_over_J']
FEATURES = BIN_NAMES + INDEX_NAMES
# quality cuts, applied the same way to known and unknown objects
# Set from known objects only, by `quality` below: beyond these values SPHEREx's K/J colour stops agreeing with 2MASS.
CUTS = {'min_valid_fraction': 0.85, 'max_offset_pix': 0.5, 'min_snr_J': 5.0, 'max_near_rival': 2.0, 'max_resid': 0.12, 'J_ratio_range': [0.6, 4.0]}
SNR_RANGE = (5.0, 40.0)        # training spectra are degraded to this range of J-band signal-to-noise (log-uniform)
N_AUG = 4


def _band(wave, flux, err, lo, hi):
    m = (wave >= lo) & (wave < hi) & np.isfinite(flux) & np.isfinite(err) & (err > 0)
    if not m.any():
        return np.nan, np.nan
    w = 1.0 / err[m] ** 2
    return float(np.sum(w * flux[m]) / np.sum(w)), float(1.0 / math.sqrt(np.sum(w)))


def features(wave, flux, err) -> tuple[np.ndarray, dict]:
    bins = np.array([_band(wave, flux, err, a, b)[0] for a, b in zip(EDGES[:-1], EDGES[1:])])
    nir, nir_err = _band(wave, flux, err, 1.0, 2.4)
    j, j_err = _band(wave, flux, err, 1.22, 1.34)
    scale = nir if np.isfinite(nir) and nir > 0 else np.nan
    b = lambda lo, hi: _band(wave, flux, err, lo, hi)[0]                      # noqa: E731
    idx = np.array([b(1.66, 1.78) / scale - b(1.52, 1.63) / scale,            # methane in H: strongly negative for T dwarfs
                    b(1.38, 1.46) / scale - b(1.22, 1.34) / scale,            # water next to the J peak
                    b(2.20, 2.35) / scale - b(2.00, 2.15) / scale,            # methane in K
                    b(2.00, 2.20) / scale, b(3.20, 3.45) / scale - b(4.40, 4.75) / scale,
                    b(4.40, 4.75) / scale, b(1.00, 1.10) / scale, b(0.82, 0.95) / scale])
    meta = {'snr_J': float(j / j_err) if np.isfinite(j) and j_err and j_err > 0 else 0.0, 'snr_nir': float(nir / nir_err) if np.isfinite(nir) and nir_err else 0.0,
            'valid_fraction': float(np.isfinite(flux).mean()), 'J_ujy': float(j) if np.isfinite(j) else None}
    return np.concatenate([bins / scale, idx]), meta


def load() -> tuple[list[dict], dict]:
    objs = {o['oid']: o for o in json.loads((OUT / 'objects.json').read_text())['objects']}
    d = np.load(OUT / 'spectra.npz')
    rows = []
    for i, oid in enumerate(d['oid']):
        o = dict(objs[str(oid)])
        f, e = d['flux_ujy'][i].astype(float), d['err_ujy'][i].astype(float)
        x, meta = features(d['wave_um'], f, e)
        o.update(meta)
        # measured J-band flux over the flux the catalogue J magnitude implies: far from 1 means the light is not this object's
        o['J_ratio'] = (meta['J_ujy'] / (1594e6 * 10 ** (-0.4 * o['J']))) if meta['J_ujy'] and o['J'] else None
        o.update({'i': i, 'x': x, 'offset_pix': float(d['offset_pix'][i]), 'near_rival': float(d['near_rival'][i]), 'resid': float(d['resid'][i])})
        o['pass'] = bool(o['valid_fraction'] >= CUTS['min_valid_fraction'] and o['offset_pix'] <= CUTS['max_offset_pix'] and o['snr_J'] >= CUTS['min_snr_J']
                         and o['near_rival'] <= CUTS['max_near_rival'] and o['resid'] <= CUTS['max_resid'] and np.isfinite(x).all()
                         and o['J_ratio'] is not None and CUTS['J_ratio_range'][0] <= o['J_ratio'] <= CUTS['J_ratio_range'][1])
        rows.append(o)
    return rows, {'wave': d['wave_um'], 'flux': d['flux_ujy'], 'err': d['err_ujy']}


def quality(log=print) -> dict:
    """Where does the photometry stop being trustworthy?  Known objects only: SPHEREx's K/J colour against 2MASS's."""
    rows, spec = load()
    pts = []
    for o in rows:
        if o['type_num'] is None or o['K'] is None or o['snr_J'] < 8:
            continue
        f, e = spec['flux'][o['i']].astype(float), spec['err'][o['i']].astype(float)
        j, k = _band(spec['wave'], f, e, 1.22, 1.34)[0], _band(spec['wave'], f, e, 2.0, 2.3)[0]
        if not (np.isfinite(j) and np.isfinite(k)) or j <= 0 or k <= 0:
            continue
        pts.append((math.log10((k / j) / (666.7 / 1594 * 10 ** (0.4 * (o['J'] - o['K'])))), o['near_rival'], o['resid'], o['offset_pix'], o['pass']))
    a = np.array(pts, float)
    med = float(np.median(a[:, 0]))

    def table(col, edges):
        out = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            m = (a[:, col] >= lo) & (a[:, col] < hi)
            if m.sum() >= 5:
                x = a[m, 0]
                out.append({'from': lo, 'to': hi, 'n': int(m.sum()), 'scatter_dex': round(float(1.4826 * np.median(np.abs(x - np.median(x)))), 3),
                            'percent_off_by_over_0.15_dex': round(float(np.mean(np.abs(x - med) > 0.15) * 100))})
        return out
    ok = a[a[:, 4] > 0, 0]
    # a second, independent check at longer wavelengths: SPHEREx's 4.6 / 3.4 micron flux ratio against WISE's W2 / W1
    located = json.loads((OUT / 'positions.json').read_text()) if (OUT / 'positions.json').is_file() else {}
    wise = []
    for o in rows:
        w = (located.get(o['oid']) or {}).get('allwise')
        if o['type_num'] is None or not o['pass'] or not w or w['W1'] is None or w['W2'] is None:
            continue
        f, e = spec['flux'][o['i']].astype(float), spec['err'][o['i']].astype(float)
        f1, e1 = _band(spec['wave'], f, e, 3.1, 3.7)
        f2, e2 = _band(spec['wave'], f, e, 4.3, 4.95)
        if not (np.isfinite(f1) and np.isfinite(f2)) or f1 <= 3 * e1 or f2 <= 3 * e2:
            continue
        wise.append(math.log10((f2 / f1) / (171.787 / 309.540 * 10 ** (0.4 * (w['W1'] - w['W2'])))))
    wise = np.array(wise)
    doc = {'n': len(a), 'what': 'log10 of (SPHEREx K/J flux ratio) / (2MASS K/J flux ratio), known objects with J-band S/N above 8',
           'median_dex': round(med, 3), 'scatter_all_dex': round(float(1.4826 * np.median(np.abs(a[:, 0] - med))), 3),
           'scatter_passing_cuts_dex': round(float(1.4826 * np.median(np.abs(ok - np.median(ok)))), 3), 'n_passing': int(len(ok)),
           'by_near_rival': table(1, [0, 0.3, 0.6, 1, 2, 4, 10, 1e9]), 'by_resid': table(2, [0, 0.05, 0.1, 0.12, 0.2, 0.35, 5]),
           'by_offset_pix': table(3, [0, 0.3, 0.5, 0.6, 1.0, 1.5]), 'cuts': CUTS,
           'wise_check': ({'what': 'log10 of (SPHEREx 4.6/3.4 micron flux ratio) / (AllWISE W2/W1 flux ratio), known objects that pass the cuts',
                           'n': int(len(wise)), 'median_dex': round(float(np.median(wise)), 3),
                           'scatter_dex': round(float(1.4826 * np.median(np.abs(wise - np.median(wise)))), 3)} if len(wise) >= 10 else None)}
    (OUT / 'quality.json').write_text(json.dumps(doc, indent=1))
    log(f"colour check on {len(a)} known objects: scatter {doc['scatter_all_dex']} dex overall, {doc['scatter_passing_cuts_dex']} dex for the {len(ok)} that pass the cuts; WISE check: {doc['wise_check']}")
    return doc


def _degrade(wave, flux, err, snr_j, target_snr, rng):
    """The same spectrum as it would look if the object were fainter: scaled down, with this exposure's own noise added."""
    if snr_j <= target_snr:
        return flux, err
    s = target_snr / snr_j
    return flux * s + rng.normal(0, 1, flux.shape) * err * math.sqrt(max(1 - s * s, 0)), err


def _models():
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    kw = dict(max_iter=300, learning_rate=0.06, max_leaf_nodes=15, l2_regularization=1.0, random_state=0)
    return HistGradientBoostingRegressor(**kw), HistGradientBoostingClassifier(**kw)


def _training_matrix(rows, spec, rng):
    X, y, g = [], [], []
    for o in rows:
        f, e = spec['flux'][o['i']].astype(float), spec['err'][o['i']].astype(float)
        X.append(o['x']); y.append(o['type_num']); g.append(o['oid'])
        for _ in range(N_AUG):
            t = math.exp(rng.uniform(math.log(SNR_RANGE[0]), math.log(SNR_RANGE[1])))
            x, m = features(spec['wave'], *_degrade(spec['wave'], f, e, o['snr_J'], t, rng))
            if np.isfinite(x).all():
                X.append(x); y.append(o['type_num']); g.append(o['oid'])
    return np.array(X), np.array(y), np.array(g)


def train(log=print) -> dict:
    from sklearn.metrics import roc_auc_score
    rows, spec = load()
    known = [o for o in rows if o['type_num'] is not None]
    use = [o for o in known if o['pass']]
    log(f"known objects with a spectrum: {len(known)}; pass the quality cuts: {len(use)} "
        f"(M {sum(o['type_num'] < 10 for o in use)}, L {sum(10 <= o['type_num'] < 20 for o in use)}, T/Y {sum(o['type_num'] >= 20 for o in use)})")
    rng = np.random.default_rng(SEED)
    order = rng.permutation(len(use))
    folds = [order[k::5] for k in range(5)]
    pred, prob, faint_pred, faint_prob = np.full(len(use), np.nan), np.full(len(use), np.nan), np.full(len(use), np.nan), np.full(len(use), np.nan)
    for k, test in enumerate(folds):
        tr = [use[i] for i in order if i not in set(test)]
        X, y, _ = _training_matrix(tr, spec, np.random.default_rng(SEED + k))
        reg, clf = _models()
        reg.fit(X, y); clf.fit(X, (y >= 20).astype(int))
        Xt = np.array([use[i]['x'] for i in test])
        pred[test], prob[test] = reg.predict(Xt), clf.predict_proba(Xt)[:, 1]
        # the same held-out objects, made as faint as the faintest we accept (J-band signal-to-noise 6 to 10)
        r2 = np.random.default_rng(SEED + 100 + k)
        Xf = []
        for i in test:
            o = use[i]
            x, _ = features(spec['wave'], *_degrade(spec['wave'], spec['flux'][o['i']].astype(float), spec['err'][o['i']].astype(float), o['snr_J'], r2.uniform(6, 10), r2))
            Xf.append(x if np.isfinite(x).all() else o['x'])
        Xf = np.array(Xf)
        faint_pred[test], faint_prob[test] = reg.predict(Xf), clf.predict_proba(Xf)[:, 1]
    y = np.array([o['type_num'] for o in use])
    is_t = y >= 20
    # the threshold: the lowest probability at which at most 1 % of known M and L dwarfs would be called T (both tests)
    neg = np.concatenate([prob[~is_t], faint_prob[~is_t]])
    thr = float(min(0.99, max(0.9, np.quantile(neg, 0.99) + 1e-6)))        # never below 0.9
    thr = math.ceil(thr * 100) / 100

    def stats(p, q, label):
        call = (q >= thr) & (p >= 20)
        d = {'rms_subtypes': float(np.sqrt(np.mean((p - y) ** 2))), 'median_abs_subtypes': float(np.median(np.abs(p - y))),
             'rms_M': float(np.sqrt(np.mean((p - y)[y < 10] ** 2))), 'rms_L': float(np.sqrt(np.mean((p - y)[(y >= 10) & (y < 20)] ** 2))),
             'rms_T': float(np.sqrt(np.mean((p - y)[is_t] ** 2))), 'auc_T': float(roc_auc_score(is_t, q)),
             'T_found': int(np.sum(call & is_t)), 'T_total': int(is_t.sum()), 'false_T': int(np.sum(call & ~is_t)), 'not_T_total': int((~is_t).sum())}
        log(f"{label}: type RMS {d['rms_subtypes']:.2f} subtypes (M {d['rms_M']:.2f}, L {d['rms_L']:.2f}, T {d['rms_T']:.2f}); AUC {d['auc_T']:.3f}; "
            f"T dwarfs called T: {d['T_found']}/{d['T_total']}; M or L wrongly called T: {d['false_T']}/{d['not_T_total']}")
        return d
    # a plain physical rule for comparison: the methane dip in the H band, with its best threshold
    ch4 = np.array([o['x'][FEATURES.index('ch4_H')] for o in use])
    out = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'n_known_with_spectrum': len(known), 'n_used': len(use),
           'by_class': {'M': int(np.sum(y < 10)), 'L': int(np.sum((y >= 10) & (y < 20))), 'T': int(is_t.sum())},
           'features': FEATURES, 'cuts': CUTS, 'snr_range': SNR_RANGE, 'n_augment': N_AUG, 'threshold_p_T': thr,
           'model': 'gradient-boosted trees (scikit-learn HistGradientBoosting): a regressor for the type and a classifier for T/Y',
           'cv': '5-fold, split by object; degraded copies of an object stay in the same fold as the object',
           'held_out': stats(pred, prob, 'held-out, as observed'), 'held_out_faint': stats(faint_pred, faint_prob, 'held-out, degraded to S/N 6-10'),
           'baseline_methane_index_auc': float(roc_auc_score(is_t, -ch4)),
           'points': [{'name': o['name'], 'sp_type': o['sp_type'], 'true': o['type_num'], 'pred': round(float(pred[i]), 2), 'p_T': round(float(prob[i]), 3),
                       'snr_J': round(o['snr_J'], 1)} for i, o in enumerate(use)]}
    log(f"threshold on P(T): {thr}; baseline (methane index alone) AUC {out['baseline_methane_index_auc']:.3f}")
    (OUT / 'cv.json').write_text(json.dumps(out, indent=1))
    return out


def lock(log=print) -> dict:
    """Fit the final model on every usable known object and lock it, with the cuts and the rule, before any unknown is scored."""
    import joblib
    from validation import ledger
    cv = json.loads((OUT / 'cv.json').read_text())
    rows, spec = load()
    use = [o for o in rows if o['type_num'] is not None and o['pass']]
    X, y, _ = _training_matrix(use, spec, np.random.default_rng(SEED + 999))
    reg, clf = _models()
    reg.fit(X, y); clf.fit(X, (y >= 20).astype(int))
    joblib.dump({'reg': reg, 'clf': clf, 'features': FEATURES, 'train_X': np.array([o['x'] for o in use])}, OUT / 'model.joblib')
    protocol = {'locked_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'cuts': CUTS, 'features': FEATURES, 'threshold_p_T': cv['threshold_p_T'],
                'rule': ('An unclassified object is a T-dwarf candidate if its SPHEREx spectrum passes the quality cuts, the classifier gives '
                         f"P(T/Y) >= {cv['threshold_p_T']}, the regressor gives a type of T0 or later, and its features are not outliers "
                         '(nearest known object closer than the 99th percentile of that distance among known objects).'),
                'n_training_objects': len(use), 'cross_validation': {k: cv[k] for k in ('held_out', 'held_out_faint', 'baseline_methane_index_auc')},
                'statement': 'No unclassified object was scored by any model before this file was written.'}
    (OUT / 'protocol.json').write_text(json.dumps(protocol, indent=1))
    e = ledger.append('coldspec:protocol', [OUT / 'protocol.json', OUT / 'model.joblib', OUT / 'objects.json', OUT / 'spectra.npz', ROOT / 'validation' / 'coldspec.py',
                                           ROOT / 'pipeline' / 'cubespec.py'], note='Model, cuts and decision rule for the cold-world spectral search, locked before scoring unclassified objects.')
    log(f"locked as ledger entry {e['seq']}: threshold {cv['threshold_p_T']}, {len(use)} training objects")
    return protocol



# ---------------------------------------------------------------------------
# Step 5: score the unclassified objects (only after the lock), then vet whatever is flagged.
# ---------------------------------------------------------------------------

def _nn_distance(Xtrain: np.ndarray, X: np.ndarray, *, leave_one_out: bool = False) -> np.ndarray:
    mu, sd = Xtrain.mean(0), Xtrain.std(0) + 1e-9
    A, B = (Xtrain - mu) / sd, (X - mu) / sd
    d = np.sqrt(((B[:, None, :] - A[None, :, :]) ** 2).sum(-1))
    if leave_one_out:
        np.fill_diagonal(d, np.inf)
    return d.min(1)


def _simbad_types(oids: list[str]) -> dict:
    """Every spectral-type measurement SIMBAD holds for these objects (its 'basic' table can be empty when this is not)."""
    if not oids:
        return {}
    out = {}
    try:
        for r in tap(f"SELECT oidref, sptype, bibcode FROM mesSpT WHERE oidref IN ({','.join(oids)})"):
            out.setdefault(r['oidref'], []).append({'sptype': r['sptype'].strip('"'), 'bibcode': r['bibcode'].strip('"')})
    except Exception as error:  # noqa: BLE001
        out['_error'] = str(error)[:120]
    return out


def _binned(wave, flux, err) -> list[dict]:
    out = []
    for a, b in zip(EDGES[:-1], EDGES[1:]):
        f, e = _band(wave, flux, err, a, b)
        if np.isfinite(f):
            out.append({'um': round((a + b) / 2, 3), 'ujy': round(f, 1), 'err': round(e, 1)})
    return out


def apply(log=print) -> dict:
    import joblib
    from validation import ledger
    ledger.locked('coldspec:protocol', OUT / 'protocol.json')            # refuses to run if the lock is missing or changed
    proto = json.loads((OUT / 'protocol.json').read_text())
    m = joblib.load(OUT / 'model.joblib')
    rows, spec = load()
    located = json.loads((OUT / 'positions.json').read_text()) if (OUT / 'positions.json').is_file() else {}
    thr = proto['threshold_p_T']
    lim = float(np.quantile(_nn_distance(m['train_X'], m['train_X'], leave_one_out=True), 0.99))
    unknown = [o for o in rows if o['type_num'] is None]
    ok = [o for o in unknown if o['pass']]
    X = np.array([o['x'] for o in ok])
    pred, prob, dist = m['reg'].predict(X), m['clf'].predict_proba(X)[:, 1], _nn_distance(m['train_X'], X)
    letters = 'MLTY'
    name_of = lambda t: f"{letters[min(int(max(t, 0)) // 10, 3)]}{max(t, 0) % 10:.1f}"          # noqa: E731
    scored = []
    for o, p, q, d in zip(ok, pred, prob, dist):
        scored.append({'oid': o['oid'], 'name': o['name'], 'group': o['group'], 'otype': o['otype'], 'ra': o['ra'], 'dec': o['dec'], 'J': o['J'], 'K': o['K'],
                       'pm_arcsec_yr': round(math.hypot(o['pmra'] or 0, o['pmdec'] or 0) / 1000, 3), 'snr_J': round(o['snr_J'], 1),
                       'pred_type_num': round(float(p), 2), 'pred_type': name_of(float(p)), 'p_T': round(float(q), 3),
                       'outlier': bool(d > lim), 'candidate': bool(q >= thr and p >= 20 and d <= lim), 'i': o['i']})
    cands = sorted([c for c in scored if c['candidate']], key=lambda c: -c['p_T'])
    log(f"unclassified objects: {len(unknown)} with a spectrum, {len(ok)} pass the quality cuts, {sum(c['outlier'] for c in scored)} outliers, {len(cands)} flagged as T-dwarf candidates")
    # ---- vetting: does anything already say what these are? ----
    types = _simbad_types([c['oid'] for c in cands])
    for c in cands:
        c['simbad_types'] = types.get(c['oid'], [])
        w = (located.get(c['oid']) or {}).get('allwise')
        c['wise'] = {'W1': w['W1'], 'W2': w['W2'], 'W1_W2': round(w['W1'] - w['W2'], 2) if w['W1'] is not None and w['W2'] is not None else None} if w else None
        f, e = spec['flux'][c['i']].astype(float), spec['err'][c['i']].astype(float)
        c['spectrum'] = _binned(spec['wave'], f, e)
        known_already = bool(c['simbad_types'])
        wise_ok = c['wise'] is not None and c['wise']['W1_W2'] is not None and c['wise']['W1_W2'] >= 0.5
        c['verdict'] = ('already typed in the literature' if known_already else
                        'new candidate, WISE colour agrees' if wise_ok else
                        'new candidate, no WISE confirmation' if c['wise'] is None or c['wise']['W1_W2'] is None else
                        'doubtful: WISE colour is not that of a T dwarf')
        log(f"  {c['name']:32s} {c['pred_type']} P(T) {c['p_T']:.2f} S/N {c['snr_J']:5.1f}  SIMBAD types {[t['sptype'] for t in c['simbad_types']]}  "
            f"W1-W2 {c['wise']['W1_W2'] if c['wise'] else None}  -> {c['verdict']}")
        del c['i']
    for c in scored:
        c.pop('i', None)
    typed = [c for c in scored if not c['outlier']]
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'threshold_p_T': thr, 'outlier_distance_limit': round(lim, 3),
           'n_unclassified': len(unknown), 'n_pass_quality': len(ok), 'n_outliers': int(sum(c['outlier'] for c in scored)),
           'n_typed': len(typed), 'typed_by_class': {k: int(sum(1 for c in typed if c['pred_type'][0] == k)) for k in 'MLT'},
           'n_candidates': len(cands), 'candidates': cands,
           'n_new_wise_agrees': sum(1 for c in cands if c['verdict'] == 'new candidate, WISE colour agrees'),
           'typed': [{k: c[k] for k in ('name', 'ra', 'dec', 'J', 'pred_type', 'p_T', 'snr_J', 'group')} for c in typed],
           'caveat': ('A candidate is an object with no spectral type in SIMBAD whose SPHEREx spectrum looks like a T dwarf to a model validated on known ones. '
                      'It is not a confirmed discovery. Confirmation needs a spectrum from a large telescope.')}
    (OUT / 'results.json').write_text(json.dumps(doc, indent=1))
    from validation import ledger as _l
    _l.append('coldspec:results', [OUT / 'results.json'], note='Scores of the unclassified objects under the locked protocol.')
    return doc



# ---------------------------------------------------------------------------
# A queue of real objects for people to check by eye ("does the light vanish in the methane bands?").
# Known objects are mixed in so that a volunteer gets feedback; flagged and unclassified objects are the real task.
# ---------------------------------------------------------------------------

def check_queue(log=print) -> dict:
    res = json.loads((OUT / 'results.json').read_text())
    cv = json.loads((OUT / 'cv.json').read_text())
    rows, spec = load()
    by_oid = {o['oid']: o for o in rows}
    by_name = {o['name']: o for o in rows}
    rng = np.random.default_rng(SEED + 7)

    def spectrum_of(o):
        return _binned(spec['wave'], spec['flux'][o['i']].astype(float), spec['err'][o['i']].astype(float))

    def shape(objs):
        """Median spectrum of a group, each scaled to its own 1.0-2.4 micron mean."""
        stack = []
        for o in objs:
            f, e = spec['flux'][o['i']].astype(float), spec['err'][o['i']].astype(float)
            nir = _band(spec['wave'], f, e, 1.0, 2.4)[0]
            if nir and nir > 0:
                stack.append([_band(spec['wave'], f, e, a, b)[0] / nir for a, b in zip(EDGES[:-1], EDGES[1:])])
        med = np.nanmedian(np.array(stack), axis=0)
        return [{'um': round((a + b) / 2, 3), 'v': round(float(v), 3)} for a, b, v in zip(EDGES[:-1], EDGES[1:], med) if np.isfinite(v)]

    known = [o for o in rows if o['type_num'] is not None and o['pass']]
    cold = [o for o in known if 23 <= o['type_num'] < 30]                 # T3 and later: clear methane
    warm = [o for o in known if o['type_num'] < 16]                       # M and early L: none
    pcv = {p['name']: p for p in cv['points']}

    def item(o, kind, truth=None, truth_label=None, model=None):
        return {'id': f"o{o['oid']}", 'kind': kind, 'name': o['name'], 'truth': truth, 'truth_label': truth_label, 'model': model,
                'snr': round(o['snr_J'], 1), 'ra': o['ra'], 'dec': o['dec'], 'spectrum': spectrum_of(o)}

    def pick(pool, n, lo=8.0, hi=60.0):
        pool = [o for o in pool if lo <= o['snr_J'] <= hi] or pool
        return [pool[i] for i in rng.permutation(len(pool))[:n]]

    def model_of(o):
        p = pcv.get(o['name'])
        return {'type': f"{'MLTY'[min(int(p['pred']) // 10, 3)]}{p['pred'] % 10:.1f}", 'p_T': p['p_T']} if p else None

    # two clear warm-ups, then everything else shuffled
    warmup = [item(o, 'known', 'dips', f"a {o['sp_type']} dwarf: a cold world with methane", model_of(o)) for o in pick(cold, 1, 20, 200)]
    warmup += [item(o, 'known', 'smooth', f"a {o['sp_type']} dwarf: a small, warmer star", model_of(o)) for o in pick(warm, 1, 20, 200)]
    used = {w['id'] for w in warmup}
    rest = []
    for c in res['candidates']:                                               # every object the model flagged
        o = by_oid[c['oid']]
        typed = c['simbad_types'][0]['sptype'] if c['simbad_types'] else None
        rest.append(item(o, 'known' if typed else 'unknown', ('dips' if typed and typed.strip().startswith(('T', 'Y')) else 'smooth') if typed else None,
                         f"typed {typed} in the literature" if typed else None, {'type': c['pred_type'], 'p_T': c['p_T']}))
        rest[-1]['flagged'] = True
    typed_unknown = {t['name']: t for t in res['typed']}
    others = [by_name[n] for n in typed_unknown if n in by_name and f"o{by_name[n]['oid']}" not in {r['id'] for r in rest}]
    for o in pick(others, 10):                                                # unclassified objects the model did not flag
        t = typed_unknown[o['name']]
        rest.append(item(o, 'unknown', None, None, {'type': t['pred_type'], 'p_T': t['p_T']}))
    for o in pick([o for o in cold if f"o{o['oid']}" not in used], 6):        # hidden known answers
        rest.append(item(o, 'known', 'dips', f"a {o['sp_type']} dwarf: a cold world with methane", model_of(o)))
    for o in pick([o for o in warm if f"o{o['oid']}" not in used], 6):
        rest.append(item(o, 'known', 'smooth', f"a {o['sp_type']} dwarf: a small, warmer star", model_of(o)))
    rest = [rest[i] for i in rng.permutation(len(rest))]
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
           'question': 'Does the light almost vanish inside the two grey bands?',
           'reference': {'cold': shape(cold), 'warm': shape(warm)}, 'bands_um': [[1.63, 1.78], [3.10, 3.45]],
           'items': warmup + rest,
           'note': 'Spectra: SPHEREx DR1 all-sky cube. Known answers are spectral types from SIMBAD. A check is a human opinion on a real object; it does not confirm anything by itself.'}
    (OUT / 'check_queue.json').write_text(json.dumps(doc, indent=1))
    log(f"check queue: {len(doc['items'])} objects ({sum(1 for i in doc['items'] if i['kind'] == 'unknown')} with no known answer, "
        f"{sum(1 for i in doc['items'] if i.get('flagged'))} flagged by the model)")
    return doc


if __name__ == '__main__':
    step = sys.argv[1] if len(sys.argv) > 1 else 'lists'
    {'lists': build_lists, 'positions': positions, 'extract': extract, 'quality': quality, 'train': train, 'lock': lock, 'apply': apply,
     'check': check_queue}[step]()
