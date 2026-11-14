"""Brightness changes of SATURATED stars from their unsaturated halo (experimental).

RW Aurigae and R Draconis, the two variable stars among NASA's test targets, saturate the
SPHEREx detector core, so PSF photometry is impossible.  But the light a bright star scatters
into a ring a few pixels out is not saturated, and at a fixed wavelength it is proportional
to the star's flux.  We therefore measure the median surface brightness in a ring around the
star in every exposure, and compare exposures ONLY at matched wavelength:

    ln H(exposure) = S(wavelength bin) + V(visit) + noise

S absorbs the star's spectrum and the wavelength dependence of the PSF wings; V is the
brightness of each visit relative to the first.  Nothing about the ring profile needs to be
known, only that it is the same instrument at the same wavelength.

The method is validated on a control: Barnard's Star, which is saturated too but is not a
large-amplitude variable.  Its visit-to-visit ratio measures the systematic floor.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import json
import math
from pathlib import Path
import sys

import numpy as np

from .astrometry import mjd_to_iso
from .investigate import track_from_catalog, track_position
from .measure import reference_candidates, register
from .spherex import CACHE, ROOT, flag_mask, load_observation

RINGS = {'r3-5': (3.0, 5.0), 'r5-8': (5.0, 8.0), 'r8-12': (8.0, 12.0)}
BKG_RING = (24.0, 42.0)
EXTRA_MASK = {'BLOOM', 'STREAK', 'SNOWBALL', 'PERSIST'}
BIN_FRACTION = 0.025              # wavelength bins of 2.5 % width
VAR_SIGMA = 5.0                   # same pre-declared variability thresholds as analysis.py
VAR_MIN_AMPLITUDE = 0.05
VISIT_GAP_DAYS = 30.0


def halo_one(args):
    path, track, refs = args
    try:
        obs = load_observation(path, keep_epsf_zones=4)
    except Exception as error:  # noqa: BLE001
        return {'path': str(path), 'status': 'unreadable', 'reason': str(error)[:120]}
    reg, _ = register(obs, refs)
    dx, dy = (reg.dx, reg.dy) if reg.ok else (0.0, 0.0)
    ra, dec = track_position(track, obs.mjd)
    x, y = obs.wcs.world_to_pixel_values(ra, dec)
    x, y = float(x) + dx, float(y) + dy
    ny, nx = obs.shape
    prov = obs.meta.get('provenance', {})
    row = {'product_id': prov.get('product_id', obs.product_id), 'mjd': obs.mjd, 'detector': obs.detector, 'status': 'measured'}
    if not (13 <= x <= nx - 14 and 13 <= y <= ny - 14):
        row['status'] = 'near_edge'
        return row
    mask = obs.hard_mask(strict=False) | ((obs.flags & flag_mask(obs.flag_names, EXTRA_MASK)) != 0)
    yy, xx = np.indices(obs.shape)
    r = np.hypot(xx - x, yy - y)
    bsel = (r >= BKG_RING[0]) & (r <= BKG_RING[1]) & ~mask
    if bsel.sum() < 200:
        row['status'] = 'no_background'
        return row
    bvals = obs.image[bsel]
    bkg = float(np.median(bvals))
    bsig = float(1.4826 * np.median(np.abs(bvals - bkg)))
    lam, _ = obs.wavelength_at(x, y)
    row['wavelength_um'] = lam if math.isfinite(lam) else None
    sat = flag_mask(obs.flag_names, {'OVERFLOW', 'NONLINEAR'})
    row['core_saturated_pixels'] = int(((obs.flags & sat) != 0)[r <= 2.0].sum())
    rings = {}
    for name, (r1, r2) in RINGS.items():
        sel = (r >= r1) & (r < r2)
        good = sel & ~mask
        if sel.sum() == 0 or good.sum() < 12 or good.sum() / sel.sum() < 0.6:
            continue
        vals = obs.image[good] - bkg
        h = float(np.median(vals))
        err = float(1.2533 * 1.4826 * np.median(np.abs(vals - h)) / math.sqrt(vals.size))
        rings[name] = {'h': h, 'err': err, 'snr': h / max(bsig / math.sqrt(vals.size), 1e-12), 'valid_fraction': float(good.sum() / sel.sum())}
    row['rings'] = rings
    return row


def measure(files, track, refs, workers=8):
    jobs = [(str(f), track, refs) for f in files]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(halo_one, jobs, chunksize=4))


def _visits(mjd):
    order = np.argsort(mjd)
    lab = np.zeros(len(mjd), int)
    k = 0
    for a, b in zip(order[:-1], order[1:]):
        if mjd[b] - mjd[a] > VISIT_GAP_DAYS:
            k += 1
        lab[b] = k
    return lab


def analyse(rows, *, ring=None):
    ok = [r for r in rows if r.get('status') == 'measured' and r.get('wavelength_um') and r.get('rings')]
    if ring is None:
        counts = {name: sum(1 for r in ok if name in r['rings'] and r['rings'][name]['snr'] >= 10 and r['rings'][name]['h'] > 0) for name in RINGS}
        best = max(counts.values()) if counts else 0
        ring = next((name for name in RINGS if counts[name] >= 0.7 * best and counts[name] > 0), None)
    use = [r for r in ok if ring and ring in r['rings'] and r['rings'][ring]['snr'] >= 10 and r['rings'][ring]['h'] > 0]
    out = {'method': 'median surface brightness in an unsaturated ring around the star, compared at matched wavelength',
           'ring': ring, 'ring_pixels': list(RINGS[ring]) if ring else None, 'n_exposures': len(rows), 'n_used': len(use),
           'thresholds': {'sigma': VAR_SIGMA, 'min_amplitude': VAR_MIN_AMPLITUDE}}
    if len(use) < 12:
        out['status'] = 'insufficient'
        return out
    mjd = np.array([r['mjd'] for r in use])
    lam = np.array([r['wavelength_um'] for r in use])
    lnh = np.log(np.array([r['rings'][ring]['h'] for r in use]))
    rel_err = np.array([r['rings'][ring]['err'] / r['rings'][ring]['h'] for r in use])
    vis = _visits(mjd)
    nv = int(vis.max()) + 1
    b = np.floor(np.log(lam / 0.7) / math.log(1 + BIN_FRACTION)).astype(int)
    # bins observed in at least two visits carry the visit-to-visit information
    multi = np.array([len(set(vis[b == k])) >= 2 for k in b])
    out['n_matched'] = int(multi.sum())
    out['n_visits'] = nv
    if nv < 2 or multi.sum() < 8:
        out['status'] = 'insufficient'
        return out
    V = np.zeros(nv)
    S = {}
    for _ in range(25):
        for k in set(b):
            sel = b == k
            S[k] = float(np.median(lnh[sel] - V[vis[sel]]))
        s = np.array([S[k] for k in b])
        for v in range(nv):
            sel = (vis == v) & multi
            if sel.any():
                V[v] = float(np.median(lnh[sel] - s[sel]))
        V -= V[0]
    s = np.array([S[k] for k in b])
    resid = lnh - s - V[vis]
    visits = []
    for v in range(nv):
        sel = (vis == v) & multi
        n = int(sel.sum())
        scat = float(1.4826 * np.median(np.abs(resid[sel] - np.median(resid[sel])))) if n >= 3 else math.nan
        visits.append({'visit': f'visit-{v + 1}', 'n': n, 'start_utc': mjd_to_iso(float(mjd[vis == v].min())), 'end_utc': mjd_to_iso(float(mjd[vis == v].max())),
                       'ln_ratio': float(V[v]), 'ratio': float(math.exp(V[v])), 'scatter': scat,
                       'err': float(1.2533 * scat / math.sqrt(n)) if n >= 3 else None})
    e0 = visits[0]['err'] or 0.0
    for d in visits[1:]:
        if d['err'] is not None:
            d['err_vs_first'] = float(math.hypot(d['err'], e0))
            d['sigma'] = float(abs(d['ln_ratio']) / d['err_vs_first']) if d['err_vs_first'] > 0 else None
    # light curve: brightness relative to the first visit, per exposure
    curve = [{'mjd': float(m), 'time_utc': mjd_to_iso(float(m)), 'relative': float(math.exp(x)), 'err': float(e), 'wavelength_um': float(w),
              'visit': f'visit-{int(v) + 1}', 'matched': bool(mm)}
             for m, x, e, w, v, mm in zip(mjd, lnh - s, rel_err, lam, vis, multi)]
    curve.sort(key=lambda p: p['mjd'])
    # within-visit trend: slope of ln(relative brightness) per 30 days, per visit
    for d, v in zip(visits, range(nv)):
        sel = vis == v
        if sel.sum() >= 8 and np.ptp(mjd[sel]) >= 10:
            t = (mjd[sel] - mjd[sel].mean()) / 30.0
            y = (lnh - s)[sel]
            slope = float(np.sum(t * (y - y.mean())) / np.sum(t * t))
            rs = y - y.mean() - slope * t
            serr = float(1.4826 * np.median(np.abs(rs)) / math.sqrt(np.sum(t * t)))
            d['trend_per_30d'] = slope
            d['trend_err'] = serr
            d['span_days'] = float(np.ptp(mjd[sel]))
    changes = [d for d in visits[1:] if d.get('sigma') is not None]
    big = [d for d in changes if d['sigma'] >= VAR_SIGMA and abs(d['ratio'] - 1) >= VAR_MIN_AMPLITUDE]
    out.update({'status': 'variable' if big else 'not_detected', 'visits': visits, 'light_curve': curve,
                'max_ratio_change': float(max((abs(d['ratio'] - 1) for d in changes), default=0.0)),
                'residual_scatter': float(1.4826 * np.median(np.abs(resid[multi] - np.median(resid[multi]))))})
    return out


def run_files(files, gaia, track, label, *, workers=8):
    refs = reference_candidates(gaia)
    rows = measure(files, track, refs, workers=workers)
    doc = analyse(rows)
    doc['target'] = label
    doc['n_core_saturated'] = sum(1 for r in rows if (r.get('core_saturated_pixels') or 0) > 0)
    return doc, rows


def star_track(source):
    return {'ra': source['ra'], 'dec': source['dec'], 't0_mjd': 57388.5, 'pmra': source.get('pmra') or 0.0,
            'pmdec': source.get('pmdec') or 0.0, 'parallax': source.get('parallax') or 0.0}


def run_target(slug, *, source=None, workers=8):
    from .targets import TARGETS
    gaia = json.loads((ROOT / 'data' / 'targets' / slug / 'gaia_field.json').read_text())
    files = sorted((CACHE / 'targets' / slug / 'raw').glob('*.fits'))
    if source is None:
        return run_files(files, gaia, track_from_catalog(TARGETS[slug].astrometry), TARGETS[slug].title, workers=workers)
    return run_files(files, gaia, star_track(source), f"Gaia DR3 {source['source_id']}", workers=workers)


if __name__ == '__main__':
    for slug in sys.argv[1:]:
        doc, rows = run_target(slug)
        print(slug, doc.get('status'), 'ring', doc.get('ring'), 'used', doc.get('n_used'), 'matched', doc.get('n_matched'),
              'saturated', doc.get('n_core_saturated'), 'of', doc['n_exposures'])
        for v in doc.get('visits', []):
            print('   ', v['visit'], v['start_utc'][:10], v['end_utc'][:10], 'n', v['n'], 'ratio %.3f' % v['ratio'],
                  'err', None if v.get('err_vs_first') is None else round(v['err_vs_first'], 4), 'sigma', None if v.get('sigma') is None else round(v['sigma'], 1),
                  'scatter', round(v['scatter'], 3), 'trend/30d', None if 'trend_per_30d' not in v else (round(v['trend_per_30d'], 3), round(v['trend_err'], 3)))
