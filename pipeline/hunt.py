"""Blind search for moving sources in a SPHEREx field ("Planet X mode").

Nothing in stages 1-3 uses a catalogue to decide where to look or what moves.

Stage 1  Stack each visit's exposures in three wavelength bands on one sky grid and detect every
         source in every stack (matched filter, empirical noise).
Stage 2  Link detections across visits: sources that stay put, sources that are present in one
         visit and absent in another, and chains of such "orphans" that fit a straight line.
Stage 3  Measure EVERY linked source in every exposure on native pixels (the same ePSF + Gaia
         registration engine as a single-source investigation) and apply the same pre-declared
         motion test: >= 5 sigma and |mu| / error >= 5.
Stage 4  Only now look the movers up (Gaia DR3, optional CatWISE) and apply vetting flags.

The stacks are for detection and display.  Every reported motion comes from native pixels,
except "stack-level" candidates that are too faint to centroid in single exposures; those are
labelled as such and never called confirmed.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time
import warnings

import numpy as np
from scipy.ndimage import correlate, maximum_filter, map_coordinates, median_filter

from .analysis import MOTION_PM_SNR, MOTION_SIGMA, analyse_motion
from .astrometry import JULIAN_YEAR_DAYS, mjd_to_iso
from .frames import display_wcs
from .measure import GAIA_EPOCH_MJD, gaia_field, gaia_positions, measure_position, reference_candidates, register
from .motion import fit_motion
from .spherex import CACHE, ROOT, SR_PER_ARCSEC2, load_observation

GRID_ARCSEC = 3.075                       # stack grid: half a native pixel
BANDS = {'short': (1, 2, 3), 'mid': (4,), 'cold': (5, 6)}
BAND_RANGE_UM = {'short': [0.75, 2.42], 'mid': [2.42, 3.82], 'cold': [3.82, 5.0]}
KERNEL_FWHM_ARCSEC = {'short': 8.0, 'mid': 8.8, 'cold': 9.6}
VISIT_GAP_DAYS = 30.0

# Pre-declared search thresholds (fixed before the search was run on any field).
SEED_SNR = 5.0            # a source must reach this in at least one visit stack to be tested
FAINT_SNR = 3.0           # sub-threshold peaks count as "still there" when matching visits
R_STATIC = 2.0            # arcsec: same place in two visits
R_MERGE = 3.5             # arcsec: same source in two bands of one visit
V_MAX = 15.0              # arcsec / yr: fastest motion the orphan linker will propose
LINK_TOL = 2.5            # arcsec: tolerance on a straight line (covers parallax up to ~1")
EXPECT_SNR = 6.0          # an absence only counts if the source should have reached this
MIN_COVER = 3             # exposures per stack pixel
CANDIDATE_PM_MIN = 0.2    # arcsec / yr: slower drifts are reported but not listed as candidates
CHROMATIC_SIGMA = 4.0
MAX_MODEL_CHI2R = 4.0
BRIGHT_STAR = [(7.0, 90.0), (9.5, 45.0)]   # (Gaia G limit, exclusion radius in arcsec)
BLOCKING_FLAGS = ('colour_dependent_motion', 'poor_model_fit', 'near_bright_star', 'near_edge',
                  'motion_explained_by_colour', 'depends_on_one_visit', 'negative_parallax')

HUNT_DATA = ROOT / 'data' / 'hunt'
HUNT_CACHE = CACHE / 'hunt'


# ---------------------------------------------------------------------------
# Stage 1: stacks
# ---------------------------------------------------------------------------

def _mad(v):
    v = v[np.isfinite(v)]
    if v.size < 10:
        return math.nan
    return float(1.4826 * np.median(np.abs(v - np.median(v))))


def _stack_one(args):
    path, ra0, dec0, fov, refs, nz = args
    try:
        obs = load_observation(path, keep_epsf_zones=nz)
    except Exception as error:  # noqa: BLE001
        return {'path': str(path), 'error': str(error)[:200]}
    mask = obs.hard_mask(strict=False)        # OUTLIER / TRANSIENT are NOT masked: they can be set on movers
    if (~mask).sum() < 400:
        return {'path': str(path), 'error': 'mostly masked'}
    reg, _ = register(obs, refs)
    dx, dy = (reg.dx, reg.dy) if reg.ok else (0.0, 0.0)
    img = obs.image
    fill = np.where(mask, np.median(img[~mask]), img)
    res = np.where(mask, np.nan, img - median_filter(fill, size=17, mode='nearest'))
    var = np.where(mask, np.nan, obs.variance)
    scale = _mad(res / np.sqrt(var))           # empirical noise scale of this exposure
    if math.isfinite(scale):
        var = var * float(np.clip(scale, 0.5, 4.0)) ** 2
    w, n = display_wcs(ra0, dec0, fov, GRID_ARCSEC)
    yy, xx = np.indices((n, n), dtype=float)
    ra, dec = w.pixel_to_world_values(xx, yy)
    x, y = obs.wcs.world_to_pixel_values(ra, dec)
    out = map_coordinates(res, [y + dy, x + dx], order=1, mode='constant', cval=np.nan)
    v = map_coordinates(var, [y + dy, x + dx], order=1, mode='constant', cval=np.nan)
    prov = obs.meta.get('provenance', {})
    return {'id': prov.get('product_id', obs.product_id), 'mjd': obs.mjd, 'detector': obs.detector, 'path': str(path),
            'img': out.astype('f4'), 'var': v.astype('f4'), 'reg_ok': bool(reg.ok),
            'reg_rms': reg.rms_arcsec if reg.ok else None, 'release': obs.release or prov.get('release'),
            'sha256': prov.get('sha256'), 'archive_url': prov.get('archive_url')}


def combine(items):
    """Inverse-variance mean with outlier rejection across exposures."""
    cube = np.stack([i['img'] for i in items])
    vcube = np.stack([i['var'] for i in items])
    ok = np.isfinite(cube) & np.isfinite(vcube) & (vcube > 0)
    with warnings.catch_warnings(), np.errstate(all='ignore'):
        warnings.simplefilter('ignore')
        if len(items) >= 4:
            c = np.where(ok, cube, np.nan)
            med = np.nanmedian(c, axis=0)
            mad = 1.4826 * np.nanmedian(np.abs(c - med), axis=0)
            tol = 5.0 * np.maximum(mad, np.sqrt(np.where(ok, vcube, np.nan)))
            ok &= np.abs(cube - med) <= tol
        w = np.where(ok, 1.0 / np.where(ok, vcube, 1.0), 0.0)
        wsum = w.sum(0)
        mean = (w * np.where(ok, cube, 0.0)).sum(0) / wsum
        noise = 1.0 / np.sqrt(wsum)
    ncov = ok.sum(0)
    mean[ncov == 0] = np.nan
    noise[ncov == 0] = np.nan
    return mean.astype('f4'), noise.astype('f4'), ncov


def _kernel(fwhm_px):
    s = fwhm_px / 2.3548
    r = int(math.ceil(3 * s))
    y, x = np.mgrid[-r:r + 1, -r:r + 1]
    return np.exp(-(x * x + y * y) / (2 * s * s)), s


def snr_map(mean, noise, ncov, band):
    """Matched-filter S/N, amplitude and amplitude error; noise renormalised empirically."""
    K, s = _kernel(KERNEL_FWHM_ARCSEC[band] / GRID_ARCSEC)
    good = np.isfinite(mean) & np.isfinite(noise) & (noise > 0) & (ncov >= MIN_COVER)
    w = np.where(good, 1.0 / np.where(good, noise, 1.0) ** 2, 0.0)
    num = correlate(np.where(good, mean, 0.0) * w, K, mode='constant')
    den = correlate(w, K * K, mode='constant')
    cover = correlate(good.astype(float), K, mode='constant') / K.sum()
    valid = (den > 0) & (cover > 0.7)
    with np.errstate(all='ignore'):
        amp = num / den
        snr = num / np.sqrt(den)
        err = 1.0 / np.sqrt(den)
    scale = _mad(snr[valid])
    if not math.isfinite(scale) or scale <= 0:
        scale = 1.0
    snr = np.where(valid, snr / scale, np.nan)
    err = np.where(valid, err * scale, np.nan)
    amp = np.where(valid, amp, np.nan)
    # peak surface brightness (MJy/sr) -> total point-source flux (uJy), Gaussian approximation
    to_ujy = 2 * math.pi * s * s * GRID_ARCSEC ** 2 * SR_PER_ARCSEC2 * 1e12
    return snr, amp, err, to_ujy, scale


def find_peaks(snr, thresh, edge=5):
    s = np.nan_to_num(snr, nan=-1e9)
    mx = maximum_filter(s, size=5)
    ys, xs = np.where((s == mx) & (s >= thresh))
    ny, nx = snr.shape
    out = []
    for y, x in zip(ys, xs):
        if not (edge <= x < nx - edge and edge <= y < ny - edge):
            continue
        c = s[y, x]
        # sub-pixel peak from a parabola through the three samples on each axis
        def off(a, b):
            d = 2 * c - a - b
            return float(np.clip(0.5 * (b - a) / d, -0.5, 0.5)) if d > 0 and a > -1e8 and b > -1e8 else 0.0
        out.append((x + off(s[y, x - 1], s[y, x + 1]), y + off(s[y - 1, x], s[y + 1, x]), float(c)))
    return out


def group_visits(mjds, gap=VISIT_GAP_DAYS):
    order = np.argsort(mjds)
    visits, cur = [], [order[0]]
    for i in order[1:]:
        if mjds[i] - mjds[cur[-1]] > gap:
            visits.append(cur)
            cur = []
        cur.append(i)
    visits.append(cur)
    return visits


def build_stacks(files, ra0, dec0, fov, refs, *, workers=8, nz=4, log=print):
    jobs = [(str(f), ra0, dec0, fov, refs, nz) for f in files]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_stack_one, jobs, chunksize=4))
    items = [r for r in res if 'error' not in r]
    errors = [{'path': Path(r['path']).name, 'error': r['error']} for r in res if 'error' in r]
    if not items:
        raise RuntimeError('no readable exposures')
    mjds = np.array([i['mjd'] for i in items])
    visits = []
    for k, idx in enumerate(group_visits(mjds)):
        members = [items[i] for i in idx]
        v = {'id': f'visit-{k + 1}', 'mjd_start': float(mjds[idx].min()), 'mjd_end': float(mjds[idx].max()),
             'mjd_mid': float(np.median(mjds[idx])), 'n_exposures': len(members), 'bands': {}}
        for band, dets in BANDS.items():
            sel = [m for m in members if m['detector'] in dets]
            if len(sel) < MIN_COVER:
                continue
            mean, noise, ncov = combine(sel)
            snr, amp, err, to_ujy, scale = snr_map(mean, noise, ncov, band)
            v['bands'][band] = {'mean': mean, 'snr': snr, 'amp': amp, 'err': err, 'to_ujy': to_ujy, 'n': len(sel),
                                'noise_scale': scale, 'ncov': ncov}
        visits.append(v)
        log(f"  {v['id']}: {len(members)} exposures, bands " + ', '.join(f"{b}:{d['n']}" for b, d in v['bands'].items()))
    return items, visits, errors


def detect_visit(v, k):
    """Sources in one visit: peaks >= FAINT_SNR in any band, merged across bands."""
    peaks = []
    for band, d in v['bands'].items():
        for x, y, s in find_peaks(d['snr'], FAINT_SNR):
            peaks.append((s, x, y, band))
    peaks.sort(reverse=True)
    sources = []
    r2 = (R_MERGE / GRID_ARCSEC) ** 2
    for s, x, y, band in peaks:
        hit = next((q for q in sources if (q['x'] - x) ** 2 + (q['y'] - y) ** 2 <= r2), None)
        if hit is None:
            fw = KERNEL_FWHM_ARCSEC[band]
            sources.append({'visit': k, 'x': x, 'y': y, 'band': band, 'snr': s, 'det': {band: s},
                            'sigma': math.hypot(0.6 * fw / s, 0.3)})
        else:
            hit['det'].setdefault(band, s)
    for q in sources:
        xi, yi = int(round(q['x'])), int(round(q['y']))
        q['forced'], q['flux_ujy'] = {}, {}
        for band, d in v['bands'].items():
            sv = d['snr'][yi, xi]
            q['forced'][band] = float(sv) if np.isfinite(sv) else None
            a = d['amp'][yi, xi]
            q['flux_ujy'][band] = float(a * d['to_ujy']) if np.isfinite(a) else None
    return sources


# ---------------------------------------------------------------------------
# Stage 2: linking
# ---------------------------------------------------------------------------

class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def _expected_snr(src, visit):
    """S/N this source would have had in another visit's stack (same band), if it had stayed put."""
    d = visit['bands'].get(src['band'])
    if d is None:
        return None, None
    xi, yi = int(round(src['x'])), int(round(src['y']))
    err = d['err'][yi, xi]
    if not np.isfinite(err) or err <= 0:
        return None, None
    amp = src['_amp']
    forced = d['snr'][yi, xi]
    return float(amp / err), (float(forced) if np.isfinite(forced) else None)


def link(visits, per_visit):
    """Return objects: static groups and straight-line chains of orphans."""
    src = [q for lst in per_visit for q in lst]
    for q in src:
        d = visits[q['visit']]['bands'][q['band']]
        q['_amp'] = float(d['amp'][int(round(q['y'])), int(round(q['x']))])
    n = len(src)
    uf = _UF(n)
    xy = np.array([[q['x'], q['y']] for q in src]) * GRID_ARCSEC if n else np.zeros((0, 2))
    vis = np.array([q['visit'] for q in src])
    sig = np.array([q['sigma'] for q in src])
    for i in range(n):
        d = np.hypot(xy[:, 0] - xy[i, 0], xy[:, 1] - xy[i, 1])
        lim = np.clip(2.5 * np.hypot(sig, sig[i]), R_STATIC, 3.5)
        for j in np.where((d <= lim) & (vis != vis[i]))[0]:
            uf.union(i, int(j))
    groups = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    tmid = np.array([v['mjd_mid'] for v in visits])
    objects, pool = [], []
    for members in groups.values():
        best = max(members, key=lambda i: src[i]['snr'])
        if src[best]['snr'] < SEED_SNR:
            continue
        seen = {src[i]['visit'] for i in members}
        missing = []
        for k, v in enumerate(visits):
            if k in seen:
                continue
            exp, forced = _expected_snr(src[best], v)
            if exp is not None and exp >= EXPECT_SNR:
                missing.append(k)
        g = {'members': members, 'best': best, 'missing': missing}
        if missing:
            pool.append(g)
        else:
            objects.append(g)

    # Orphan linking: chains of incomplete groups along a straight line.
    proposals = []
    for a in range(len(pool)):
        for b in range(a + 1, len(pool)):
            ga, gb = pool[a], pool[b]
            for i in ga['members']:
                for j in gb['members']:
                    if vis[i] == vis[j]:
                        continue
                    dt = (tmid[vis[j]] - tmid[vis[i]]) / JULIAN_YEAR_DAYS
                    d = float(np.hypot(*(xy[j] - xy[i])))
                    if d > R_STATIC + V_MAX * abs(dt) or abs(dt) < 0.05:
                        continue
                    vel = (xy[j] - xy[i]) / dt
                    chain, resid = {a, b}, 0.0
                    for c in range(len(pool)):
                        if c in chain:
                            continue
                        for m in pool[c]['members']:
                            pred = xy[i] + vel * (tmid[vis[m]] - tmid[vis[i]]) / JULIAN_YEAR_DAYS
                            r = float(np.hypot(*(xy[m] - pred)))
                            if r <= LINK_TOL:
                                chain.add(c)
                                resid += r
                                break
                    ok_all = True      # every member of the two seed groups must also lie on the line
                    for g in (ga, gb):
                        for m in g['members']:
                            pred = xy[i] + vel * (tmid[vis[m]] - tmid[vis[i]]) / JULIAN_YEAR_DAYS
                            if np.hypot(*(xy[m] - pred)) > LINK_TOL:
                                ok_all = False
                    if not ok_all:
                        continue
                    fa, fb = src[i]['_amp'], src[j]['_amp']
                    if not (0.33 < fa / fb < 3.0):
                        continue        # a real source does not change brightness threefold between visits
                    nvis = len({int(vis[m]) for c in chain for m in pool[c]['members']})
                    proposals.append((nvis, -resid, -float(np.hypot(*vel)), sorted(chain)))
    proposals.sort(reverse=True)
    used = set()
    for nvis, _, _, chain in proposals:
        if any(c in used for c in chain):
            continue
        used.update(chain)
        members = [m for c in chain for m in pool[c]['members']]
        objects.append({'members': members, 'best': max(members, key=lambda i: src[i]['snr']), 'missing': [],
                        'linked_orphans': True})
    for c, g in enumerate(pool):
        if c not in used:
            g['intermittent'] = True
            objects.append(g)

    out = []
    for g in objects:
        ms = sorted(g['members'], key=lambda i: vis[i])
        t = np.array([tmid[vis[i]] for i in ms])
        px = np.array([src[i]['x'] for i in ms])
        py = np.array([src[i]['y'] for i in ms])
        vx = vy = 0.0
        if g.get('linked_orphans') and len(set(t)) >= 2:
            ty = (t - t.mean()) / JULIAN_YEAR_DAYS
            vx, vy = float(np.polyfit(ty, px, 1)[0]), float(np.polyfit(ty, py, 1)[0])
        b = src[g['best']]
        det_snr = {band: max((src[i]['det'].get(band, 0) for i in ms), default=0) for band in BANDS}
        forced_max = {band: max((src[i]['forced'].get(band) or -9 for i in ms), default=-9) for band in BANDS}
        out.append({'knots_t': t.tolist(), 'knots_x': px.tolist(), 'knots_y': py.tolist(), 'vx': vx, 'vy': vy,
                    'visits_detected': sorted({int(vis[i]) for i in ms}), 'missing_visits': g.get('missing', []),
                    'linked_orphans': bool(g.get('linked_orphans')), 'intermittent': bool(g.get('intermittent')),
                    'best_band': b['band'], 'best_snr': b['snr'], 'det_snr': det_snr, 'forced_snr': forced_max,
                    'knot_sigma': [src[i]['sigma'] for i in ms],
                    'flux_ujy': {band: b['flux_ujy'].get(band) for band in BANDS}})
    return out


def object_xy(o, mjd):
    t, x, y = o['knots_t'], o['knots_x'], o['knots_y']
    if len(t) == 1 or not o['linked_orphans']:
        k = int(np.argmin(np.abs(np.asarray(t) - mjd)))
        return x[k], y[k]
    tm = float(np.mean(t))
    dt = (mjd - tm) / JULIAN_YEAR_DAYS
    return float(np.mean(x)) + o['vx'] * dt, float(np.mean(y)) + o['vy'] * dt


# ---------------------------------------------------------------------------
# Stage 3: native-pixel astrometry of every object in every exposure
# ---------------------------------------------------------------------------

def _astrometry_one(args):
    path, ra0, dec0, fov, refs, nz, objs = args
    try:
        obs = load_observation(path, keep_epsf_zones=nz)
    except Exception as error:  # noqa: BLE001
        return {'path': str(path), 'error': str(error)[:200]}
    reg, _ = register(obs, refs)
    dx, dy = (reg.dx, reg.dy) if reg.ok else (0.0, 0.0)
    gw, _ = display_wcs(ra0, dec0, fov, GRID_ARCSEC)
    gxy = np.array([object_xy(o, obs.mjd) for o in objs])
    ra, dec = gw.pixel_to_world_values(gxy[:, 0], gxy[:, 1])
    px, py = obs.wcs.world_to_pixel_values(ra, dec)
    ny, nx = obs.shape
    rows = []
    for k in range(len(objs)):
        x0, y0 = float(px[k]) + dx, float(py[k]) + dy
        if not (5 <= x0 <= nx - 6 and 5 <= y0 <= ny - 6):
            continue
        d2 = (px - px[k]) ** 2 + (py - py[k]) ** 2
        others = [(float(px[j]) + dx, float(py[j]) + dy) for j in np.where((d2 > 0.42) & (d2 < 20.0))[0]]
        f, pos = measure_position(obs, reg, x0, y0, others=others)
        if not f.ok or pos is None or not math.isfinite(f.snr):
            continue
        lam, _ = obs.wavelength_at(f.x, f.y)
        sat = any(n in f.flags for n in ('OVERFLOW', 'NONLINEAR'))
        rows.append((k, pos['ra'], pos['dec'], pos['sigma_arcsec'], f.snr, f.chi2r, lam, int(sat)))
    prov = obs.meta.get('provenance', {})
    return {'id': prov.get('product_id', obs.product_id), 'mjd': obs.mjd, 'detector': obs.detector, 'rows': rows,
            'reg_ok': bool(reg.ok)}


def native_astrometry(files, ra0, dec0, fov, refs, objs, *, workers=8, nz=4):
    slim = [{k: o[k] for k in ('knots_t', 'knots_x', 'knots_y', 'vx', 'vy', 'linked_orphans')} for o in objs]
    jobs = [(str(f), ra0, dec0, fov, refs, nz, slim) for f in files]
    per_obj = [[] for _ in objs]
    band_of = {d: b for b, dets in BANDS.items() for d in dets}
    # A source is only centroided in bands where its stack was detected.  Otherwise a free centroid on a
    # source that is invisible at that wavelength (e.g. a cold object below 3.8 um) can wander on to a neighbour.
    allowed = [{b for b, v in o['det_snr'].items() if v and v >= FAINT_SNR} for o in objs]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(_astrometry_one, jobs, chunksize=4):
            if 'error' in r:
                continue
            for k, ra, dec, sig, snr, chi2r, lam, sat in r['rows']:
                if band_of.get(r['detector']) not in allowed[k]:
                    continue
                per_obj[k].append({'status': 'measured', 'product_id': r['id'], 'mjd': r['mjd'], 'detector': r['detector'],
                                   'centroid': {'ok': True, 'snr': snr, 'chi2r': chi2r},
                                   'position': {'ra': ra, 'dec': dec, 'sigma_arcsec': sig},
                                   'wavelength_um': lam, 'flags': ['OVERFLOW'] if sat else []})
    return per_obj


# ---------------------------------------------------------------------------
# Stage 4: motion test, vetting, identification
# ---------------------------------------------------------------------------

def _pm_of(rows):
    """Linear proper motion (arcsec/yr) with errors from a set of usable rows, or None."""
    if len(rows) < 6:
        return None
    mjd = np.array([r['mjd'] for r in rows])
    if mjd.max() - mjd.min() < 60:
        return None
    try:
        f = fit_motion(mjd, [r['position']['ra'] for r in rows], [r['position']['dec'] for r in rows],
                       [r['position']['sigma_arcsec'] for r in rows], model='linear')
    except (ValueError, np.linalg.LinAlgError):
        return None
    e = f.errors()
    return f.params['pmra'], f.params['pmdec'], e['pmra'], e['pmdec']


def chromatic_check(usable):
    """Does the motion look the same below and above 2.42 um?  A colour-dependent blend does not."""
    lo = [r for r in usable if (r.get('wavelength_um') or 0) < 2.42]
    hi = [r for r in usable if (r.get('wavelength_um') or 0) >= 2.42]
    a, b = _pm_of(lo), _pm_of(hi)
    if a is None or b is None:
        return {'tested': False}
    dra = (a[0] - b[0]) / math.hypot(a[2], b[2])
    ddec = (a[1] - b[1]) / math.hypot(a[3], b[3])
    return {'tested': True, 'n_short': len(lo), 'n_long': len(hi), 'd_sigma': float(math.hypot(dra, ddec)),
            'pm_short_masyr': [a[0] * 1000, a[1] * 1000], 'pm_long_masyr': [b[0] * 1000, b[1] * 1000],
            'consistent': bool(math.hypot(dra, ddec) < CHROMATIC_SIGMA)}


def robust_motion(usable, visits_doc):
    """Two independent checks on a claimed motion.

    (a) Refit linear motion with a chromatic term per axis (position = a + mu*t + c*(lambda - median)).
        A blend of two sources with different colours shifts its photocentre with wavelength; if the
        wavelength mix differs between visits that shift imitates motion.  The chromatic term absorbs it.
    (b) Leave one visit out: a real mover keeps its direction and speed whichever visit is dropped.
    """
    from .analysis import visit_of
    from .astrometry import to_tangent
    mjd = np.array([r['mjd'] for r in usable])
    ra = np.array([r['position']['ra'] for r in usable])
    dec = np.array([r['position']['dec'] for r in usable])
    sig = np.array([r['position']['sigma_arcsec'] for r in usable])
    lam = np.array([r.get('wavelength_um') or np.nan for r in usable], dtype=float)
    lam = np.where(np.isfinite(lam), lam, np.nanmedian(lam) if np.isfinite(lam).any() else 0.0)
    vis = np.array([visit_of(m, visits_doc) for m in mjd])
    w = 1 / sig ** 2
    xi, eta = to_tangent(ra, dec, float(np.average(ra, weights=w)), float(np.average(dec, weights=w)))
    t = (mjd - mjd.mean()) / JULIAN_YEAR_DAYS
    lc = lam - np.median(lam)

    def solve(sel):
        A = np.stack([np.ones(sel.sum()), t[sel], lc[sel]], -1)
        AtW = A.T * w[sel]
        try:
            cov = np.linalg.inv(AtW @ A)
        except np.linalg.LinAlgError:
            return None
        px, py = cov @ (AtW @ xi[sel]), cov @ (AtW @ eta[sel])
        chi2 = float(np.sum(w[sel] * ((xi[sel] - A @ px) ** 2 + (eta[sel] - A @ py) ** 2)))
        dof = max(2 * int(sel.sum()) - 6, 1)
        err = math.sqrt(cov[1, 1] * max(chi2 / dof, 1.0))
        return float(px[1]), float(py[1]), err, chi2 / dof

    full = solve(np.ones(len(mjd), bool))
    if full is None:
        return {'tested': False}
    pm = math.hypot(full[0], full[1])
    out = {'tested': True, 'pm_arcsec_yr': round(pm, 4), 'pm_err_arcsec_yr': round(full[2], 4),
           'pm_over_error': round(pm / full[2], 2) if full[2] > 0 else None, 'chi2_reduced': round(full[3], 2),
           'n_visits': int(len(set(vis))), 'jackknife': [], 'jackknife_stable': None}
    names = sorted(set(vis))
    if len(names) >= 3:
        stable = True
        for v in names:
            sel = vis != v
            if sel.sum() < 6 or np.ptp(mjd[sel]) < 60:
                continue
            j = solve(sel)
            if j is None:
                continue
            pj = math.hypot(j[0], j[1])
            cosang = (j[0] * full[0] + j[1] * full[1]) / (pj * pm) if pj > 0 and pm > 0 else 0.0
            ok = bool(cosang >= 0.7 and 0.5 <= pj / pm <= 2.0)
            stable &= ok
            out['jackknife'].append({'without': v, 'pm_arcsec_yr': round(pj, 4), 'cos_angle': round(cosang, 3), 'ok': ok})
        out['jackknife_stable'] = bool(stable) if out['jackknife'] else None
    return out


def stack_motion(o):
    """Motion from per-visit stack positions only (for sources too faint for single exposures)."""
    t = np.asarray(o['knots_t'])
    if len(set(t.tolist())) < 2:
        return None
    x = np.asarray(o['knots_x']) * GRID_ARCSEC
    y = np.asarray(o['knots_y']) * GRID_ARCSEC
    s = np.hypot(np.asarray(o['knot_sigma']), 0.5)      # 0.5" covers unmodelled parallax
    ty = (t - t.mean()) / JULIAN_YEAR_DAYS
    w = 1 / s ** 2
    sxx = np.sum(w * ty ** 2)
    vx, vy = np.sum(w * ty * (x - np.average(x, weights=w))) / sxx, np.sum(w * ty * (y - np.average(y, weights=w))) / sxx
    verr = 1 / math.sqrt(sxx)
    rx = x - np.average(x, weights=w) - vx * ty
    ry = y - np.average(y, weights=w) - vy * ty
    chi2 = float(np.sum(w * (rx ** 2 + ry ** 2)))
    dof = 2 * len(t) - 4
    pm = math.hypot(vx, vy)
    return {'pm_arcsec_yr': float(pm), 'pm_err_arcsec_yr': float(verr), 'significance': float(pm / verr),
            'pmra_arcsec_yr': float(-vx), 'pmdec_arcsec_yr': float(vy), 'n_visits': int(len(set(t.tolist()))),
            'chi2': chi2, 'dof': int(dof)}


def classify(o, rows, visits_doc, gaia, grid_wcs, n_grid, epoch_mjd):
    motion, usable = analyse_motion(rows, visits_doc)
    x, y = object_xy(o, epoch_mjd)
    ra, dec = (float(v) for v in grid_wcs.pixel_to_world_values(x, y))
    doc = {'ra': ra, 'dec': dec, 'best_band': o['best_band'], 'stack_snr': round(o['best_snr'], 1),
           'det_snr': {k: round(v, 1) for k, v in o['det_snr'].items() if v},
           'forced_snr': {k: round(v, 1) for k, v in o['forced_snr'].items() if v > -9},
           'flux_ujy': {k: (round(v, 1) if v is not None else None) for k, v in o['flux_ujy'].items()},
           'visits_detected': [f'visit-{k + 1}' for k in o['visits_detected']],
           'missing_visits': [f'visit-{k + 1}' for k in o['missing_visits']],
           'linked_orphans': o['linked_orphans'], 'intermittent': o['intermittent'],
           'n_native_positions': len(usable), 'n_native_visits': motion.get('n_visits') if motion.get('models') else 0,
           'motion_status': motion['status'], 'flags': []}
    doc['cold_only'] = bool(o['det_snr'].get('cold', 0) >= SEED_SNR and not o['det_snr'].get('short'))
    if motion.get('models'):
        m = motion['models'][motion['reported_model']]
        s = motion['significance']
        pm = math.hypot(m.get('pmra_masyr') or 0, m.get('pmdec_masyr') or 0) / 1000
        doc.update({'model': motion['reported_model'], 'sigma': round(float(s['equivalent_sigma']), 2),
                    'pm_over_error': round(float(s['pm_over_error'] or 0), 2), 'pm_arcsec_yr': round(pm, 4),
                    'pmra_masyr': m.get('pmra_masyr'), 'pmdec_masyr': m.get('pmdec_masyr'),
                    'pmra_err_masyr': m.get('pmra_err_masyr'), 'pmdec_err_masyr': m.get('pmdec_err_masyr'),
                    'parallax_mas': m.get('parallax_mas'), 'parallax_err_mas': m.get('parallax_err_mas'),
                    'chi2r': m.get('chi2_reduced'), 'baseline_days': motion.get('baseline_days')})
        if motion['status'] == 'significant':
            ch = chromatic_check(usable)
            doc['chromatic'] = ch
            if ch.get('tested') and not ch['consistent']:
                doc['flags'].append('colour_dependent_motion')
            if (m.get('chi2_reduced') or 0) > MAX_MODEL_CHI2R:
                doc['flags'].append('poor_model_fit')
            rb = robust_motion(usable, visits_doc)
            doc['robust'] = rb
            if rb.get('tested'):
                if (rb['pm_over_error'] or 0) < MOTION_PM_SNR:
                    doc['flags'].append('motion_explained_by_colour')
                if rb['jackknife_stable'] is False:
                    doc['flags'].append('depends_on_one_visit')
                if rb['n_visits'] < 3:
                    doc['flags'].append('two_visits_only')
            if m.get('parallax_mas') is not None and (m.get('parallax_err_mas') or 0) > 0 \
                    and m['parallax_mas'] < -3 * m['parallax_err_mas']:
                doc['flags'].append('negative_parallax')
    sm = stack_motion(o) if o['linked_orphans'] else None
    if sm:
        doc['stack_motion'] = sm

    # --- identification (after the motion test) ---
    if gaia:
        gra, gdec = gaia_positions(gaia, epoch_mjd)
        d = np.hypot((gra - ra) * math.cos(math.radians(dec)), gdec - dec) * 3600
        j = int(np.argmin(d))
        if d[j] <= 4.0:
            g = gaia[j]
            doc['gaia'] = {'source_id': g['source_id'], 'g': g.get('g'), 'sep_arcsec': round(float(d[j]), 2),
                           'pmra_masyr': g.get('pmra'), 'pmdec_masyr': g.get('pmdec'), 'parallax_mas': g.get('parallax'),
                           'ruwe': g.get('ruwe')}
        gmag = np.array([s.get('g') if s.get('g') is not None else 99 for s in gaia])
        for glim, rad in BRIGHT_STAR:
            near = (gmag < glim) & (d < rad) & (d > 4.0)
            if near.any():
                doc['flags'].append('near_bright_star')
                break
    edge = 15.0 / GRID_ARCSEC
    if not (edge <= x <= n_grid - 1 - edge and edge <= y <= n_grid - 1 - edge):
        doc['flags'].append('near_edge')

    # --- class ---
    sig_ok = doc['motion_status'] == 'significant'
    if sig_ok and doc['pm_arcsec_yr'] >= CANDIDATE_PM_MIN:
        g = doc.get('gaia')
        if g and g.get('pmra_masyr') is not None:
            dpm = math.hypot(doc['pmra_masyr'] - g['pmra_masyr'], doc['pmdec_masyr'] - g['pmdec_masyr']) / 1000
            tol = 3 * math.hypot(doc['pmra_err_masyr'] or 0, doc['pmdec_err_masyr'] or 0) / 1000 + 0.15
            doc['gaia_pm_difference_arcsec_yr'] = round(dpm, 3)
            doc['class'] = 'known_mover' if dpm <= tol else 'suspect'
            if dpm > tol:
                doc['flags'].append('disagrees_with_gaia')
        elif any(f in doc['flags'] for f in BLOCKING_FLAGS):
            doc['class'] = 'suspect'
        elif 'two_visits_only' in doc['flags']:
            doc['class'] = 'two_visit_candidate'
        else:
            doc['class'] = 'candidate'
    elif sig_ok:
        doc['class'] = 'slow_drift'
    elif sm and sm['significance'] >= 5 and sm['pm_arcsec_yr'] >= CANDIDATE_PM_MIN and len(usable) < 6 \
            and not any(f in doc['flags'] for f in ('near_bright_star', 'near_edge')) and 'gaia' not in doc:
        doc['class'] = 'stack_candidate' if sm['n_visits'] >= 3 and sm['chi2'] <= 4 * max(sm['dof'], 1) else 'two_visit_candidate'
    elif doc['motion_status'] == 'insufficient':
        doc['class'] = 'intermittent' if o['intermittent'] else 'too_faint'
    else:
        doc['class'] = 'static'
    return doc, motion


# ---------------------------------------------------------------------------
# Stage 5: decade-baseline checks for movers that are not in the bright Gaia list
# ---------------------------------------------------------------------------

IRSA_TAP = 'https://irsa.ipac.caltech.edu/TAP/sync'
GAIA_TAP_URL = 'https://gea.esac.esa.int/tap-server/tap/sync'


def _csv_rows(text):
    import csv
    import io
    return list(csv.DictReader(io.StringIO(text)))


def _num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def external_checks(doc, epoch_mjd, session=None):
    """Was this "mover" already at the same place in Gaia (2016.0) or WISE (about 2015)?

    A source moving at mu arcsec/yr was mu * ~10 yr away from its 2026 position a decade ago.
    If an older catalogue shows a source at the *current* position, the object did not move that far:
    the SPHEREx motion is rejected.  If the catalogue instead shows a source where the motion says
    the object should have been, that is an independent confirmation over a ~10 year baseline.
    """
    import requests
    http = session or requests
    pm = doc.get('pm_arcsec_yr') or (doc.get('stack_motion') or {}).get('pm_arcsec_yr') or 0.0
    if doc.get('pmra_masyr') is not None:
        pmra, pmdec = doc['pmra_masyr'] / 1000, doc['pmdec_masyr'] / 1000
        pm_err = math.hypot(doc.get('pmra_err_masyr') or 0, doc.get('pmdec_err_masyr') or 0) / 1000
    else:
        sm = doc['stack_motion']
        pmra, pmdec, pm_err = sm['pmra_arcsec_yr'], sm['pmdec_arcsec_yr'], sm['pm_err_arcsec_yr']
    ra, dec = doc['ra'], doc['dec']
    cosd = math.cos(math.radians(dec))
    out = {'gaia': {'status': 'not_checked'}, 'wise': {'status': 'not_checked'}}

    def sep(ra2, dec2, ra1=ra, dec1=dec):
        return math.hypot((ra2 - ra1) * cosd, dec2 - dec1) * 3600

    # ---- Gaia DR3, all magnitudes: propagate every source to our epoch with its own motion ----
    dt_g = (epoch_mjd - GAIA_EPOCH_MJD) / JULIAN_YEAR_DAYS
    try:
        rad = min((8 + max(pm, 1.0) * dt_g) / 3600, 0.08)
        q = ('SELECT source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag FROM gaiadr3.gaia_source '
             f'WHERE 1=CONTAINS(POINT(ra, dec), CIRCLE({ra:.7f}, {dec:.7f}, {rad:.5f}))')
        r = http.post(GAIA_TAP_URL, data={'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': 'csv', 'QUERY': q}, timeout=60)
        r.raise_for_status()
        rows = _csv_rows(r.text)
        best = None
        for x in rows:
            gra, gdec, gpa, gpd = _num(x['ra']), _num(x['dec']), _num(x['pmra']) or 0.0, _num(x['pmdec']) or 0.0
            now = sep(gra + gpa / 1000 * dt_g / 3600 / cosd, gdec + gpd / 1000 * dt_g / 3600)
            if now <= 3.0 and (best is None or now < best[0]):
                best = (now, x, math.hypot(gpa, gpd) / 1000, gpa, gpd)
        g = {'status': 'checked', 'n_in_cone': len(rows), 'epoch': 2016.0, 'expected_shift_arcsec': round(pm * dt_g, 1)}
        if best:
            d_pm = math.hypot(best[3] / 1000 - pmra, best[4] / 1000 - pmdec)
            g.update({'source_id': best[1]['source_id'], 'g': _num(best[1]['phot_g_mean_mag']), 'sep_arcsec': round(best[0], 2),
                      'pmra_masyr': _num(best[1]['pmra']), 'pmdec_masyr': _num(best[1]['pmdec']),
                      'verdict': 'same_motion' if d_pm <= max(0.15, 3 * pm_err) else 'static_counterpart'})
        else:
            g['verdict'] = 'no_counterpart'
        out['gaia'] = g
    except Exception as error:  # noqa: BLE001
        out['gaia'] = {'status': 'failed', 'error': str(error)[:120]}

    # ---- CatWISE2020 (WISE + NEOWISE 2010-2018; positions near 2015) ----
    try:
        dt_w = (epoch_mjd - 57170.0) / JULIAN_YEAR_DAYS
        rad = min((10 + max(pm, 1.0) * dt_w * 1.5) / 3600, 0.1)
        q = ('SELECT source_name, ra, dec, w1mpro, w2mpro, pmra, pmdec, sigpmra, sigpmdec, meanobsmjd FROM catwise_2020 '
             f"WHERE CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{ra:.7f},{dec:.7f},{rad:.5f}))=1")
        r = http.get(IRSA_TAP, params={'FORMAT': 'csv', 'QUERY': q}, timeout=90)
        r.raise_for_status()
        rows = _csv_rows(r.text)
        w = {'status': 'checked', 'n_in_cone': len(rows), 'epoch': 2015.4, 'baseline_yr': round(dt_w, 1),
             'expected_shift_arcsec': round(pm * dt_w, 1)}

        def pack(dist, x):
            return {'source_name': x['source_name'], 'sep_arcsec': round(dist, 2), 'w1': _num(x['w1mpro']), 'w2': _num(x['w2mpro']),
                    'pmra_arcsec_yr': _num(x['pmra']), 'pmdec_arcsec_yr': _num(x['pmdec']),
                    'sigpmra': _num(x['sigpmra']), 'sigpmdec': _num(x['sigpmdec'])}
        moving, static = None, None
        for x in rows:
            wra, wdec = _num(x['ra']), _num(x['dec'])
            wpa, wpd = _num(x['pmra']) or 0.0, _num(x['pmdec']) or 0.0
            sa, sd = _num(x['sigpmra']) or 9.0, _num(x['sigpmdec']) or 9.0
            wpm = math.hypot(wpa, wpd)
            wsig = math.hypot(wpa * sa, wpd * sd) / wpm if wpm > 0 else 9.0
            dtx = (epoch_mjd - (_num(x['meanobsmjd']) or 57170.0)) / JULIAN_YEAR_DAYS
            if wpm >= 0.15 and wpm / wsig >= 5:
                # a catalogued mover: where is it now, by WISE's own motion?
                now = sep(wra + wpa * dtx / 3600 / cosd, wdec + wpd * dtx / 3600)
                if now <= 4.0 + 3 * wsig * dtx and (moving is None or now < moving[0]):
                    moving = (now, x, wpm)
            else:
                here = sep(wra, wdec)
                if here <= 3.5 and (static is None or here < static[0]):
                    static = (here, x)
        if moving:
            w.update({'verdict': 'same_motion', 'catwise_pm_arcsec_yr': round(moving[2], 3)} | pack(moving[0], moving[1]))
        elif static and pm * dt_w > 7.0:
            w.update({'verdict': 'static_counterpart'} | pack(static[0], static[1]))
        else:
            w['verdict'] = 'no_counterpart'
        out['wise'] = w
    except Exception as error:  # noqa: BLE001
        out['wise'] = {'status': 'failed', 'error': str(error)[:120]}
    return out


def apply_external(doc, ext):
    doc['external'] = ext
    gv, wv = ext['gaia'].get('verdict'), ext['wise'].get('verdict')
    if gv == 'static_counterpart':
        doc['flags'].append('gaia_2016_shows_it_here')
    if wv == 'static_counterpart':
        doc['flags'].append('wise_2015_shows_it_here')
    if gv == 'static_counterpart' or wv == 'static_counterpart':
        doc['class'] = 'suspect'
    elif gv == 'same_motion' or wv == 'same_motion':
        doc['decade_confirmed'] = True
        doc['catalogued_as'] = 'Gaia DR3 ' + ext['gaia']['source_id'] if gv == 'same_motion' else 'CatWISE2020 ' + ext['wise']['source_name']


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_field(name, files, ra0, dec0, fov, *, title=None, workers=8, truth=None, gaia=None, out_dir=None, log=print,
              kind='hunt', notes=None, max_objects=900, external=True):
    t_start = time.time()
    files = sorted(str(f) for f in files)
    nz = 4 if fov <= 12 else 16
    if gaia is None:
        gaia = gaia_field(ra0, dec0, fov / 60 * 0.75, cache=HUNT_CACHE / name / 'gaia_field.json')
    refs = reference_candidates(gaia)
    log(f'[{name}] {len(files)} exposures, {len(gaia)} Gaia stars ({len(refs)} usable references)')
    items, visits, errors = build_stacks(files, ra0, dec0, fov, refs, workers=workers, nz=nz, log=log)
    per_visit = [detect_visit(v, k) for k, v in enumerate(visits)]
    objs = link(visits, per_visit)
    n_linked = len(objs)
    if len(objs) > max_objects:      # crowded field: keep every orphan chain, then the brightest
        objs.sort(key=lambda o: (not o['linked_orphans'], -o['best_snr']))
        objs = objs[:max_objects]
    log(f'[{name}] stage 1-2: {sum(len(p) for p in per_visit)} stack detections -> {len(objs)} sources to test '
        f'({sum(o["linked_orphans"] for o in objs)} linked-orphan chains) in {time.time() - t_start:.0f}s')
    rows = native_astrometry(files, ra0, dec0, fov, refs, objs, workers=workers, nz=nz) if objs else []
    visits_doc = [{'id': v['id'], 'mjd_start': v['mjd_start'], 'mjd_end': v['mjd_end']} for v in visits]
    gw, n = display_wcs(ra0, dec0, fov, GRID_ARCSEC)
    epoch = float(np.median([i['mjd'] for i in items]))
    sources = []
    for k, o in enumerate(objs):
        doc, motion = classify(o, rows[k], visits_doc, gaia, gw, n, epoch)
        doc['id'] = f's{k + 1:04d}'
        doc['track'] = [{'visit': f'visit-{vi + 1}', 'ra': float(a), 'dec': float(b)} for vi, (a, b) in
                        zip(o['visits_detected'] if len(o['visits_detected']) == len(o['knots_x']) else range(len(o['knots_x'])),
                            zip(*gw.pixel_to_world_values(np.asarray(o['knots_x']), np.asarray(o['knots_y']))))]
        sources.append(doc)

    # --- decade-baseline checks (Gaia all-magnitude, CatWISE) for movers not explained by the bright Gaia list ---
    if external:
        for s_ in sources:
            if s_['class'] in ('candidate', 'two_visit_candidate', 'stack_candidate'):
                apply_external(s_, external_checks(s_, epoch))

    # --- truth comparison for validation fields (never used by the search itself) ---
    truth_doc = None
    if truth:
        from .astrometry import propagate
        p = propagate(truth['ra'], truth['dec'], truth['epoch_mjd'], truth['pmra'], truth['pmdec'], truth.get('parallax', 0.0), [epoch])
        tra, tdec = float(p.ra[0]), float(p.dec[0])
        cat_pm = math.hypot(truth['pmra'], truth['pmdec']) / 1000
        movers = ('candidate', 'known_mover', 'stack_candidate', 'two_visit_candidate')
        best, bsep, bscore = None, None, -1
        for s_ in sources:
            sep = math.hypot((s_['ra'] - tra) * math.cos(math.radians(tdec)), s_['dec'] - tdec) * 3600
            if sep > 15.0:
                continue
            pm_s = s_.get('pm_arcsec_yr') if s_['class'] != 'stack_candidate' else s_['stack_motion']['pm_arcsec_yr']
            e_pm = math.hypot(s_.get('pmra_err_masyr') or 0, s_.get('pmdec_err_masyr') or 0) / 1000
            agrees = bool(pm_s and abs(pm_s - cat_pm) <= max(0.35, 0.3 * cat_pm, 3 * e_pm))
            score = (2 if (s_['class'] in movers and agrees) else 1 if sep <= 5.0 else 0) * 100 - sep
            if score > bscore:
                best, bsep, bscore = s_, sep, score
        found = best is not None and bscore > 0
        pm_meas = None
        if found:
            pm_meas = best['stack_motion']['pm_arcsec_yr'] if best['class'] in ('stack_candidate',) and best.get('stack_motion') else best.get('pm_arcsec_yr')
        truth_doc = {'name': truth['name'], 'catalogue_pm_arcsec_yr': round(cat_pm, 3), 'source': truth.get('source'),
                     'spectral_type': truth.get('spectral_type'), 'w2_mag': truth.get('w2_mag'),
                     'detected': bool(found), 'nearest_source': best['id'] if found else None,
                     'separation_arcsec': round(bsep, 2) if found else None,
                     'recovered': bool(found and bscore >= 100),
                     'recovered_class': best['class'] if found else None,
                     'measured_pm_arcsec_yr': pm_meas, 'measured_sigma': best.get('sigma') if found else None}
        if found:
            best['truth_match'] = truth['name']

    order = {'candidate': 0, 'stack_candidate': 1, 'two_visit_candidate': 2, 'known_mover': 3, 'suspect': 4, 'slow_drift': 5}
    sources.sort(key=lambda s: (order.get(s['class'], 9), -(s.get('sigma') or 0), -s['stack_snr']))
    counts = {}
    for s in sources:
        counts[s['class']] = counts.get(s['class'], 0) + 1
    tested = [s for s in sources if s['motion_status'] != 'insufficient']
    # depth: median 5-sigma point-source limit of each visit's stacks
    depth = {}
    for v in visits:
        for band, d in v['bands'].items():
            lim = 5 * np.nanmedian(d['err']) * d['to_ujy']
            depth.setdefault(band, []).append(float(lim))
    depth = {b: round(float(np.median(v)), 1) for b, v in depth.items()}

    out_dir = Path(out_dir or HUNT_DATA / name)
    (out_dir / 'frames').mkdir(parents=True, exist_ok=True)
    stacks = []
    for v in visits:
        for band in ('cold', 'short', 'mid'):
            d = v['bands'].get(band)
            if d is None:
                continue
            arr = np.flipud(d['mean']).astype('<f4')
            fn = f"{v['id']}-{band}.bin"
            arr.tofile(out_dir / 'frames' / fn)
            vals = arr[np.isfinite(arr)]
            med = float(np.median(vals)) if vals.size else 0.0
            sg = _mad(vals) if vals.size else 0.0
            stacks.append({'id': f"{v['id']}-{band}", 'visit': v['id'], 'band': band, 'wavelength_range_um': BAND_RANGE_UM[band],
                           'n_exposures': d['n'], 'mjd': v['mjd_mid'], 'time_utc': mjd_to_iso(v['mjd_mid']),
                           'data_url': f'/files/hunt/{name}/frames/{fn}',
                           'stats': {'median': med, 'sigma': sg, 'p995': float(np.percentile(vals, 99.5)) if vals.size else 0.0}})
    doc = {
        'field_id': name, 'title': title or name, 'kind': kind, 'ra': ra0, 'dec': dec0, 'fov_arcmin': fov,
        'area_deg2': round((fov / 60) ** 2, 4), 'notes': notes,
        'grid': {'nx': n, 'ny': n, 'pixel_arcsec': GRID_ARCSEC, 'ra0': ra0, 'dec0': dec0, 'projection': 'TAN',
                 'orientation': 'north-up east-left', 'dtype': 'float32', 'row0': 'north'},
        'visits': [{'id': v['id'], 'start_utc': mjd_to_iso(v['mjd_start']), 'end_utc': mjd_to_iso(v['mjd_end']),
                    'mjd_mid': v['mjd_mid'], 'n_exposures': v['n_exposures'],
                    'bands': {b: d['n'] for b, d in v['bands'].items()}} for v in visits],
        'baseline_days': round(visits[-1]['mjd_end'] - visits[0]['mjd_start'], 1),
        'n_exposures': len(items), 'n_unreadable': len(errors), 'n_gaia': len(gaia),
        'n_detections': int(sum(len(p) for p in per_visit)), 'n_sources': len(sources), 'n_sources_before_cap': n_linked, 'n_motion_tested': len(tested),
        'counts': counts, 'depth_5sigma_ujy': depth, 'truth': truth_doc,
        'thresholds': {'seed_snr': SEED_SNR, 'motion_sigma': MOTION_SIGMA, 'pm_over_error': MOTION_PM_SNR,
                       'candidate_pm_min_arcsec_yr': CANDIDATE_PM_MIN, 'v_max_arcsec_yr': V_MAX,
                       'chromatic_sigma': CHROMATIC_SIGMA, 'max_model_chi2r': MAX_MODEL_CHI2R},
        'stacks': stacks, 'sources': sources,
        'exposures': [{'id': i['id'], 'mjd': i['mjd'], 'detector': i['detector'], 'release': i['release'],
                       'sha256': i['sha256'], 'archive_url': i['archive_url']} for i in sorted(items, key=lambda i: i['mjd'])],
        'runtime_s': round(time.time() - t_start, 1),
        'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    (out_dir / 'hunt.json').write_text(json.dumps(doc, indent=1, default=float))
    log(f"[{name}] {len(sources)} sources, {len(tested)} motion-tested: {counts}; depth {depth} uJy; {doc['runtime_s']}s")
    if truth_doc:
        log(f"[{name}] truth {truth_doc}")
    return doc


def curated_field(slug):
    """A field that is already cached for one of the curated targets."""
    from .targets import TARGETS
    from .astrometry import target_epoch_mjd
    man = json.loads((ROOT / 'data' / 'targets' / slug / 'archive_manifest.json').read_text())
    files = sorted((CACHE / 'targets' / slug / 'raw').glob('*.fits'))
    gaia = json.loads((ROOT / 'data' / 'targets' / slug / 'gaia_field.json').read_text())
    t = TARGETS[slug]
    a = t.astrometry
    truth = {'name': t.title, 'ra': a.ra_deg, 'dec': a.dec_deg, 'epoch_mjd': target_epoch_mjd(a), 'pmra': a.pmra_masyr,
             'pmdec': a.pmdec_masyr, 'parallax': a.parallax_mas or 0.0, 'source': a.source}
    return {'name': slug, 'title': t.title, 'files': files, 'ra': man['field_center']['ra'], 'dec': man['field_center']['dec'],
            'fov': float(man['field_size_arcmin']), 'gaia': gaia, 'truth': truth}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('slug', nargs='+')
    ap.add_argument('--workers', type=int, default=8)
    args = ap.parse_args(argv)
    for slug in args.slug:
        f = curated_field(slug)
        run_field(f['name'], f['files'], f['ra'], f['dec'], f['fov'], title=f['title'], workers=args.workers,
                  truth=f['truth'], gaia=f['gaia'], kind='validation')
    return 0


if __name__ == '__main__':
    sys.exit(main())
