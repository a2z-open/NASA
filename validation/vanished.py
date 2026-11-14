"""What disappeared? Sources WISE saw around 2015 that SPHEREx cannot see now.

    python -m validation.vanished

For every field of the hunt: take each CatWISE2020 source (the WISE and NEOWISE sky, positions near 2015) that should
be easy for SPHEREx at 3.8-5.0 micrometres (expected S/N of 15 or more), and measure SPHEREx's stacked image at that
position in every visit (forced photometry: a matched filter at a fixed position, so a missing source gives ~0).

A bright WISE source with nothing there now has three possible stories, and each is checked:
  moved     it is a fast mover: CatWISE itself measured a motion, or SPHEREx sees a moving source nearby
  faded     something is still there, but much fainter than WISE saw (a variable star, or a fading object)
  vanished  nothing at all.  A WISE artefact, a blend, a source behind a SPHEREx mask, or something genuinely gone
Planet Nine itself would be far too faint for this; the point is the method: the sky of ten years ago against today's.
"""
from __future__ import annotations

import csv
import io
import json
import math
import time
from pathlib import Path

import numpy as np
import requests

from pipeline.astrometry import to_tangent
from pipeline.spherex import USER_AGENT

ROOT = Path(__file__).resolve().parents[1]
HUNT = ROOT / 'data' / 'hunt'
CACHE = ROOT / '.parallax-cache' / 'vanished'
W2_ZERO_JY = 171.787              # WISE W2 Vega zero point (Jarrett et al. 2011)
FWHM_ARCSEC = 9.6                 # SPHEREx 3.8-5.0 um point-spread function, as in the hunt
EXPECT_MIN = 15.0                 # only sources SPHEREx should see at S/N >= 15
GONE_SNR = 3.0                    # below this in every visit: not seen
FADED_RATIO = 0.3                 # seen, but at less than 30 % of what WISE implies
EDGE = 0.85                       # inner fraction of the field
BRIGHT_W2 = 8.0                   # brighter than this saturates SPHEREx: excluded, and 60" around it
GLARE_SIGMA = 300.0               # stack pixels brighter than this (in noise units) mark a star that saturates SPHEREx
GLARE_ARCSEC = 45.0               # nothing within this distance of such a star is tested (its glare spoils the image)
SAT_GLARE_ARCSEC = 120.0          # ...and within 2 arcminutes of a star whose core saturates SPHEREx


def wise_field(ra, dec, radius_deg, cache: Path):
    """CatWISE2020 with proper motions, from NOIRLab Astro Data Lab (IRSA's catalogue service was down on 14 Nov)."""
    if cache.is_file():
        return json.loads(cache.read_text())
    q = ('SELECT source_name, ra, dec, w1mpro, w2mpro, w2sigmpro, pmra, pmdec, sigpmra, sigpmdec, meanobsmjd, cc_flags, ab_flags, w2sat, nb FROM catwise2020.main '
         f"WHERE 't'=Q3C_RADIAL_QUERY(ra, dec, {ra:.6f}, {dec:.6f}, {radius_deg:.5f})")
    for attempt in range(4):
        try:
            r = requests.post('https://datalab.noirlab.edu/tap/sync', data={'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': 'csv', 'QUERY': q},
                              timeout=180, headers={'User-Agent': USER_AGENT})
            if r.status_code == 200 and r.text.startswith('source_name'):
                break
        except requests.RequestException:
            pass
        time.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError('CatWISE query failed')
    rows = []
    for x in csv.DictReader(io.StringIO(r.text)):
        def num(k):
            try:
                v = float(x[k])
                return v if math.isfinite(v) else None
            except (TypeError, ValueError):
                return None
        rows.append({'name': x['source_name'], 'ra': num('ra'), 'dec': num('dec'), 'w1': num('w1mpro'), 'w2': num('w2mpro'), 'w2err': num('w2sigmpro'),
                     'pmra': num('pmra'), 'pmdec': num('pmdec'), 'sigpmra': num('sigpmra'), 'sigpmdec': num('sigpmdec'), 'mjd': num('meanobsmjd'),
                     'cc_flags': (x.get('cc_flags') or '').strip(), 'ab_flags': (x.get('ab_flags') or '').strip(), 'w2sat': num('w2sat'), 'nb': num('nb')})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(rows))
    return rows


def _kernel(sigma_px):
    r = int(math.ceil(3 * sigma_px))
    y, x = np.mgrid[-r:r + 1, -r:r + 1]
    return np.exp(-(x * x + y * y) / (2 * sigma_px ** 2)), r


def forced_snr(img, sigma, grid, ra, dec):
    """Matched-filter S/N of a point source at a fixed sky position in a stored stack (row 0 = north, east left)."""
    xi, eta = to_tangent(ra, dec, grid['ra0'], grid['dec0'])
    xi, eta = float(xi), float(eta)              # to_tangent already returns arcseconds
    cx, cy = grid.get('cx', (grid['nx'] - 1) / 2), grid.get('cy', (grid['ny'] - 1) / 2)
    col, row = cx - xi / grid['pixel_arcsec'], cy - eta / grid['pixel_arcsec']
    K, r = _kernel(FWHM_ARCSEC / 2.3548 / grid['pixel_arcsec'])
    c0, r0 = int(round(col)), int(round(row))
    if not (r <= c0 < grid['nx'] - r and r <= r0 < grid['ny'] - r):
        return None
    cut = img[r0 - r:r0 + r + 1, c0 - r:c0 + r + 1]
    ok = np.isfinite(cut)
    if ok.mean() < 0.7:
        return None
    return float(np.sum(np.where(ok, cut, 0) * K) / (sigma * math.sqrt(np.sum(K[ok] ** 2))))


def field(fid: str) -> dict:
    h = json.loads((HUNT / fid / 'hunt.json').read_text())
    grid = h['grid']
    stacks = [s for s in h['stacks'] if s['band'] == 'cold']
    imgs = []
    for s in stacks:
        a = np.fromfile(HUNT / fid / 'frames' / f"{s['id']}.bin", dtype=np.float16 if grid['dtype'] == 'float16' else np.float32)
        imgs.append((s, a.reshape(grid['ny'], grid['nx']).astype('f8') - s['stats']['median']))
    depth = (h.get('depth_5sigma_ujy') or {}).get('cold')
    # glare zones: around anything so bright it saturates SPHEREx (found from the stacks themselves)
    from scipy.ndimage import binary_dilation
    glare = np.zeros((grid['ny'], grid['nx']), bool)
    for s, img in imgs:
        glare |= np.nan_to_num(img, nan=0.0) > GLARE_SIGMA * s['stats']['sigma']
        # saturated cores are masked out of the stacks: a compact masked hole well inside the field marks one
        from scipy.ndimage import label
        lab, nlab = label(~np.isfinite(img))
        for k in range(1, nlab + 1):
            ys, xs = np.where(lab == k)
            inner = ys.min() > 2 and xs.min() > 2 and ys.max() < grid['ny'] - 3 and xs.max() < grid['nx'] - 3
            if inner and 3 <= ys.size <= 400:
                glare |= np.hypot(*np.mgrid[0:grid['ny'], 0:grid['nx']] - np.array([ys.mean(), xs.mean()])[:, None, None]) \
                    <= SAT_GLARE_ARCSEC / grid['pixel_arcsec']
    glare = binary_dilation(glare, iterations=int(round(GLARE_ARCSEC / grid['pixel_arcsec'])))
    radius = h['fov_arcmin'] / 60 / 2 * EDGE
    wise = wise_field(h['ra'], h['dec'], radius, CACHE / f'{fid}.json')
    bright = [w for w in wise if w['w2'] is not None and w['w2'] < BRIGHT_W2]
    movers = [s for s in h['sources'] if s.get('class') in ('candidate', 'known_mover', 'two_visit_candidate', 'stack_candidate')]
    t_ref = float(np.median([v['mjd_mid'] for v in h['visits']])) if h.get('visits') else 61000.0

    def mover_was_here(ra, dec):
        """Did a SPHEREx mover, run back along its own measured motion, pass here between 2010 and 2020?"""
        for m in movers:
            if m.get('pmra_masyr') is None or m.get('pmdec_masyr') is None:
                continue
            for year in np.arange(2010.0, 2020.5, 0.25):
                dt = (51544.5 + (year - 2000.0) * 365.25 - t_ref) / 365.25
                pr = m['ra'] + m['pmra_masyr'] / 1000 * dt / 3600 / math.cos(math.radians(m['dec']))
                pd = m['dec'] + m['pmdec_masyr'] / 1000 * dt / 3600
                if math.hypot((pr - ra) * math.cos(math.radians(dec)), pd - dec) * 3600 < 15.0:
                    return m.get('truth_match') or m.get('id')
        return None
    out, n_tested = [], 0
    for w in wise:
        if w['w2'] is None or w['w2'] < BRIGHT_W2 or not depth or not stacks:
            continue
        # WISE's own artefact flags: D diffraction spike, P persistence, H halo, O optical ghost (cc_flags / ab_flags).
        # Capital letters mean the entry is judged an artefact, so it cannot "vanish".  Lower-case letters (possible
        # contamination) and blend counts are kept: fast movers are often split into blended pieces by WISE.
        if any(ch.isupper() for ch in (w.get('cc_flags') or '') + (w.get('ab_flags') or '')):
            continue
        f_ujy = W2_ZERO_JY * 10 ** (-0.4 * w['w2']) * 1e6
        expect = 5.0 * f_ujy / depth
        if expect < EXPECT_MIN:
            continue
        cosd = math.cos(math.radians(w['dec']))
        if any(math.hypot((b['ra'] - w['ra']) * cosd, b['dec'] - w['dec']) * 3600 < 60 for b in bright):
            continue
        xi, eta = to_tangent(w['ra'], w['dec'], grid['ra0'], grid['dec0'])
        col = int(round(grid.get('cx', (grid['nx'] - 1) / 2) - float(xi) / grid['pixel_arcsec']))
        row = int(round(grid.get('cy', (grid['ny'] - 1) / 2) - float(eta) / grid['pixel_arcsec']))
        if 0 <= row < grid['ny'] and 0 <= col < grid['nx'] and glare[row, col]:
            continue
        snrs = [forced_snr(img, s['stats']['sigma'], grid, w['ra'], w['dec']) for s, img in imgs]
        snrs = [x for x in snrs if x is not None]
        if len(snrs) < 2:
            continue
        n_tested += 1
        best = max(snrs)
        # a SPHEREx stack S/N is not on the same scale as the depth-based expectation, so compare with the field's own
        # relation: the median ratio measured/expected for sources that ARE there (computed below)
        out.append({'name': w['name'], 'ra': w['ra'], 'dec': w['dec'], 'w2': w['w2'], 'expected_snr': expect, 'snr_by_visit': snrs, 'best_snr': best,
                    'pm_arcsec_yr': (math.hypot(w['pmra'], w['pmdec']) if w['pmra'] is not None and w['pmdec'] is not None else None),
                    'pm_sigma': (math.hypot(w['pmra'], w['pmdec']) / max(math.hypot(w['sigpmra'] or 9, w['sigpmdec'] or 9), 1e-3)
                                 if w['pmra'] is not None and w['pmdec'] is not None else None),
                    'spherex_mover_within_60': any(math.hypot((m['ra'] - w['ra']) * cosd, m['dec'] - w['dec']) * 3600 < 60 for m in movers),
                    'mover_track': mover_was_here(w['ra'], w['dec'])})
    # calibrate expectation against what is actually seen: median of measured / expected over all tested sources
    ratios = [o['best_snr'] / o['expected_snr'] for o in out if o['best_snr'] > 0]
    scale = float(np.median(ratios)) if ratios else 1.0
    flagged = []
    for o in out:
        exp_cal = o['expected_snr'] * scale
        o['expected_snr_calibrated'] = exp_cal
        if exp_cal < EXPECT_MIN:
            continue
        if o['best_snr'] < GONE_SNR:
            kind = 'vanished'
        elif o['best_snr'] < FADED_RATIO * exp_cal:
            kind = 'faded'
        else:
            continue
        if (o['pm_sigma'] or 0) >= 5 and (o['pm_arcsec_yr'] or 0) >= 0.15:
            kind = 'moved'
        elif o['spherex_mover_within_60'] or o['mover_track']:
            kind = 'moved'
        flagged.append(o | {'kind': kind, 'fraction_seen': max(o['best_snr'], 0) / exp_cal})
    return {'field_id': fid, 'title': h['title'], 'n_wise': len(wise), 'n_tested': n_tested, 'calibration_scale': scale, 'depth_cold_ujy': depth,
            'flagged': sorted(flagged, key=lambda f: f['fraction_seen'])}


def main(log=print) -> dict:
    fields = []
    for p in sorted(HUNT.glob('*/hunt.json')):
        fid = p.parent.name
        try:
            r = field(fid)
        except Exception as error:  # noqa: BLE001
            log(f'{fid}: failed ({error})')
            continue
        fields.append(r)
        kinds = {k: sum(1 for f in r['flagged'] if f['kind'] == k) for k in ('moved', 'faded', 'vanished')}
        log(f"{fid:16s} WISE {r['n_wise']:5d}  tested {r['n_tested']:4d}  moved {kinds['moved']}  faded {kinds['faded']}  vanished {kinds['vanished']}")
    allf = [f | {'field_id': r['field_id']} for r in fields for f in r['flagged']]
    doc = {'method': __doc__.strip().split('\n\n')[1], 'thresholds': {'expected_snr_min': EXPECT_MIN, 'gone_snr': GONE_SNR, 'faded_ratio': FADED_RATIO,
                                                                   'glare_sigma': GLARE_SIGMA, 'glare_arcsec': GLARE_ARCSEC,
                                                                   'bright_w2': BRIGHT_W2, 'edge_fraction': EDGE},
           'n_fields': len(fields), 'n_tested': sum(r['n_tested'] for r in fields),
           'counts': {k: sum(1 for f in allf if f['kind'] == k) for k in ('moved', 'faded', 'vanished')}, 'fields': fields, 'flagged': allf}
    (ROOT / 'validation' / 'vanished.json').write_text(json.dumps(doc, indent=1))
    log(f"{doc['n_tested']} bright WISE sources tested in {len(fields)} fields: {doc['counts']}")
    return doc


if __name__ == '__main__':
    main()
