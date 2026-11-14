"""Shift-and-stack: find a world too faint to see in any single SPHEREx exposure.

A body at S/N 3 in each exposure is invisible one image at a time.  Add 45 exposures together along the path it
really takes, and it reaches about 20 sigma.  Nobody knows that path in advance, so every path in a grid of trial
motions is tried (Holman et al. 2019 used the same idea on TESS; it is the standard way to reach faint movers).

Steps, for each visit of a field:
  1  every exposure is registered to Gaia, background-subtracted and resampled onto one sky grid (pipeline/hunt.py)
  2  the static sky (the median of the visit's exposures) is subtracted, and the cores of stars are masked
  3  each residual image is matched-filtered once; then, for every trial motion (vx, vy), the filtered images are shifted
     by vx*(t - t0), vy*(t - t0) and added.  The trial with the highest signal at each position is kept
  4  peaks above the threshold become candidates, each with a position at t0 and a motion within the visit
Then candidates from different visits are joined with one orbit (pipeline/distant.py) and must pass the mirrored-Earth test.
"""
from __future__ import annotations

import math
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy.ndimage import binary_dilation, correlate, maximum_filter, shift as nd_shift

from . import distant, hunt
from .frames import display_wcs

BIN = 2                       # resample the half-pixel grid 2x2: 6.15 arcsec pixels
PIX = hunt.GRID_ARCSEC * BIN  # arcsec per pixel of the shift-stack grid
VMAX = 12.0                   # arcsec / day: covers bound bodies beyond about 60 AU near quadrature
MIN_SMEAR_PX = 1.5            # the trial motion must move the body at least this far across the visit (static sky excluded)
THRESH = 7.0                  # S/N, after renormalising every trial map; ~10^4 trials x 10^4 pixels need a high bar
STAR_SNR = 8.0                # template pixels brighter than this are star cores: masked


def thresholds() -> dict:
    return {'version': 3, 'link_by': 'visit centres, three visits', 'sigma_pos_arcsec': SIGMA_POS_ARCSEC, 'orbit_parameters': 5, 'bin_px': BIN, 'pixel_arcsec': PIX, 'vmax_arcsec_day': VMAX, 'min_smear_px': MIN_SMEAR_PX, 'snr_threshold': THRESH,
            'star_mask_snr': STAR_SNR}


def _bin(a: np.ndarray, k: int, how: str) -> np.ndarray:
    n0, n1 = (a.shape[0] // k) * k, (a.shape[1] // k) * k
    b = a[:n0, :n1].reshape(n0 // k, k, n1 // k, k)
    with np.errstate(all='ignore'):
        return np.nanmean(b, axis=(1, 3)) if how == 'mean' else np.nansum(b, axis=(1, 3)) / k ** 4


def prepare(files, ra0, dec0, fov, refs, workers=8):
    """Resample every exposure onto one grid (reusing the hunt's step), then bin 2x2."""
    jobs = [(str(f), ra0, dec0, fov, refs, 4, None) for f in files]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(hunt._stack_one, jobs, chunksize=2))
    items = [r for r in res if 'error' not in r]
    for it in items:
        it['img'] = _bin(it['img'], BIN, 'mean')
        it['var'] = _bin(it['var'], BIN, 'var')          # variance of a mean of k*k pixels
        if it.get('sat') is not None:
            it['sat'] = _bin(it['sat'].astype('f4'), BIN, 'mean') > 0
    return items, [r for r in res if 'error' in r]


def _kernel(fwhm_px: float):
    s = fwhm_px / 2.3548
    r = int(math.ceil(3 * s))
    y, x = np.mgrid[-r:r + 1, -r:r + 1]
    return np.exp(-(x * x + y * y) / (2 * s * s))


def search_visit(items: list[dict], *, vmax=VMAX, thresh=THRESH, fwhm_arcsec=8.0, template_items=None) -> dict:
    """Shift-and-stack one visit.  `items` are prepared exposures of the visit (same grid).  Returns candidates."""
    items = sorted(items, key=lambda i: i['mjd'])
    n = len(items)
    t = np.array([i['mjd'] for i in items])
    t0 = float(np.median(t))
    T = float(t.max() - t.min())
    cube = np.stack([i['img'] for i in items]).astype('f8')
    var = np.stack([i['var'] for i in items]).astype('f8')
    ok = np.isfinite(cube) & np.isfinite(var) & (var > 0)
    src = template_items if template_items else items
    tc = np.stack([i['img'] for i in src]).astype('f8')
    with np.errstate(all='ignore'):
        template = np.nanmedian(tc, axis=0)
        tnoise = 1.4826 * np.nanmedian(np.abs(tc - template), axis=0) / math.sqrt(max(len(src), 1))
        tsnr = template / np.where(tnoise > 0, tnoise, np.nan)
    stars = np.nan_to_num(tsnr, nan=0.0) > STAR_SNR
    stars = binary_dilation(stars, iterations=2)
    sat = np.zeros_like(stars)
    for i in items:
        if i.get('sat') is not None:
            sat |= i['sat']
    bad = stars | binary_dilation(sat, iterations=2)
    K = _kernel(fwhm_arcsec / PIX)
    nums, dens = [], []
    for k in range(n):
        r = cube[k] - template
        w = np.where(ok[k] & ~bad, 1.0 / np.where(ok[k], var[k], 1.0), 0.0)
        r = np.where(w > 0, r, 0.0)
        nums.append(correlate(r * w, K, mode='constant'))
        dens.append(correlate(w, K * K, mode='constant'))
    nums, dens = np.stack(nums), np.stack(dens)
    ny, nx = nums.shape[1:]
    # the trial grid: one pixel of smear across the whole visit
    vpx_max = vmax / PIX
    step = 1.0 / max(T, 1.0)
    vs = np.arange(-vpx_max, vpx_max + step / 2, step)
    pad = int(math.ceil(vpx_max * max(t.max() - t0, t0 - t.min()))) + 2
    best = np.full((ny, nx), -np.inf)
    best_v = np.zeros((ny, nx, 2))
    n_trials = 0
    scales = []
    for vx in vs:
        for vy in vs:
            if math.hypot(vx, vy) > vpx_max or math.hypot(vx, vy) * T < MIN_SMEAR_PX:
                continue
            n_trials += 1
            NUM = np.zeros((ny + 2 * pad, nx + 2 * pad))
            DEN = np.zeros_like(NUM)
            for k in range(n):
                dx = int(round(vx * (t[k] - t0)))
                dy = int(round(vy * (t[k] - t0)))
                # a source at grid (x, y) at t0 sits at (x + dx, y + dy) at t[k]: move image k back by (dx, dy)
                NUM[pad - dy:pad - dy + ny, pad - dx:pad - dx + nx] += nums[k]
                DEN[pad - dy:pad - dy + ny, pad - dx:pad - dx + nx] += dens[k]
            NUM, DEN = NUM[pad:pad + ny, pad:pad + nx], DEN[pad:pad + ny, pad:pad + nx]
            cover = DEN > 0.5 * np.median(DEN[DEN > 0]) if (DEN > 0).any() else DEN > 0
            with np.errstate(all='ignore'):
                snr = np.where(cover, NUM / np.sqrt(DEN), np.nan)
            sc = hunt._mad(snr[np.isfinite(snr)])
            if not math.isfinite(sc) or sc <= 0:
                continue
            scales.append(sc)
            snr = np.nan_to_num(snr / sc, nan=-np.inf)
            upd = snr > best
            best[upd] = snr[upd]
            best_v[upd] = (vx, vy)
    peaks = []
    b = np.where(np.isfinite(best), best, -1e9)
    mx = maximum_filter(b, size=5)
    ys, xs = np.where((b == mx) & (b >= thresh))
    edge = 4
    for y, x in zip(ys, xs):
        if not (edge <= x < nx - edge and edge <= y < ny - edge) or bad[y, x]:
            continue
        peaks.append({'x': float(x), 'y': float(y), 'snr': float(best[y, x]), 'vx_px_day': float(best_v[y, x, 0]), 'vy_px_day': float(best_v[y, x, 1])})
    peaks.sort(key=lambda p: -p['snr'])
    peaks = [refine(p, nums, dens, t, t0, step) for p in peaks[:40]]
    return {'t0_mjd': t0, 'span_days': T, 'n_exposures': n, 'n_trials': n_trials, 'peaks': peaks[:40],
            'median_noise_scale': float(np.median(scales)) if scales else None, 'masked_fraction': float(bad.mean())}


def refine(p: dict, nums, dens, t, t0, step, half=6) -> dict:
    """Version 2: refine a peak below the pixel and the trial-motion step.  Around the peak, the filtered images are
    shifted by fractional pixels (bilinear) for a fine grid of motions, and the peak position is found by a parabola."""
    ny, nx = nums.shape[1:]
    x0, y0 = int(round(p['x'])), int(round(p['y']))
    m = half + int(math.ceil(abs(p['vx_px_day']) * np.max(np.abs(t - t0)) + abs(p['vy_px_day']) * np.max(np.abs(t - t0)))) + 3
    ya, yb, xa, xb = max(0, y0 - m), min(ny, y0 + m + 1), max(0, x0 - m), min(nx, x0 + m + 1)
    best = (-np.inf, p['vx_px_day'], p['vy_px_day'], None)
    for dvx in np.linspace(-0.6, 0.6, 7) * step:
        for dvy in np.linspace(-0.6, 0.6, 7) * step:
            vx, vy = p['vx_px_day'] + dvx, p['vy_px_day'] + dvy
            NUM = np.zeros((yb - ya, xb - xa))
            DEN = np.zeros_like(NUM)
            for k in range(len(t)):
                sh = (-vy * (t[k] - t0), -vx * (t[k] - t0))
                NUM += nd_shift(nums[k, ya:yb, xa:xb], sh, order=1, mode='constant', cval=0.0)
                DEN += nd_shift(dens[k, ya:yb, xa:xb], sh, order=1, mode='constant', cval=0.0)
            with np.errstate(all='ignore'):
                snr = np.where(DEN > 0, NUM / np.sqrt(DEN), -np.inf)
            cy, cx = y0 - ya, x0 - xa
            win = snr[max(0, cy - 2):cy + 3, max(0, cx - 2):cx + 3]
            if win.size and np.nanmax(win) > best[0]:
                best = (float(np.nanmax(win)), vx, vy, snr)
    _, vx, vy, snr = best
    if snr is None:
        return p | {'sub_pixel': False}
    cy, cx = y0 - ya, x0 - xa
    win = snr[max(0, cy - 2):cy + 3, max(0, cx - 2):cx + 3]
    iy, ix = np.unravel_index(np.nanargmax(win), win.shape)
    py, px = iy + max(0, cy - 2), ix + max(0, cx - 2)

    def para(a, b, c):
        d = a - 2 * b + c
        return float(np.clip(0.5 * (a - c) / d, -0.5, 0.5)) if np.isfinite(d) and d < 0 else 0.0
    ox = para(snr[py, px - 1], snr[py, px], snr[py, px + 1]) if 0 < px < snr.shape[1] - 1 else 0.0
    oy = para(snr[py - 1, px], snr[py, px], snr[py + 1, px]) if 0 < py < snr.shape[0] - 1 else 0.0
    return p | {'x': float(xa + px + ox), 'y': float(ya + py + oy), 'vx_px_day': float(vx), 'vy_px_day': float(vy), 'sub_pixel': True}


SIGMA_POS_ARCSEC = 2.5        # version 2: position error of a refined shift-and-stack peak (about 0.4 pixel)


def to_sky(peaks, ra0, dec0, fov, t0, span):
    """Turn peaks into pseudo-detections: the position at t0 and at the start and end of the visit, from its motion."""
    w, n = display_wcs(ra0, dec0, fov, hunt.GRID_ARCSEC)
    out = []
    for p in peaks:
        dets = []
        for dt in (-span / 2, 0.0, span / 2):
            # binned pixel (x, y) covers half-pixel grid pixels BIN*x .. BIN*x + BIN - 1: centre at BIN*x + (BIN - 1) / 2
            gx = BIN * (p['x'] + p['vx_px_day'] * dt) + (BIN - 1) / 2
            gy = BIN * (p['y'] + p['vy_px_day'] * dt) + (BIN - 1) / 2
            ra, dec = w.pixel_to_world_values(gx, gy)
            dets.append({'mjd': t0 + dt, 'ra': float(ra), 'dec': float(dec), 'sigma_arcsec': SIGMA_POS_ARCSEC if dt == 0 else SIGMA_POS_ARCSEC * 1.4,
                         'obs_id': f'ss{t0 + dt:.3f}', 'product_id': ''})
        rate = math.hypot(p['vx_px_day'], p['vy_px_day']) * PIX
        out.append(p | {'ra': dets[1]['ra'], 'dec': dets[1]['dec'], 'rate_arcsec_day': rate, 'pseudo': dets})
    return out


def link(visit_candidates: list[list[dict]]) -> list[dict]:
    """Version 3: join one candidate from each of three or more visits by its CENTRE position only.

    Near 90 degrees from the Sun a world at ~100 AU follows a visibly curved path within a two-week visit, so the
    straight-line motion that shift-and-stack measures is right on average but wrong at the ends of the visit.  The
    centre position is accurate.  One centre per visit gives two numbers per visit; with three visits, six numbers
    against a five-number orbit (radial speed held at zero), as in the Planet Nine linker.
    """
    import itertools
    usable = [i for i, v in enumerate(visit_candidates) if v]
    out = []
    if len(usable) < 3:
        return out
    for vset in itertools.combinations(usable, 3):
        for combo in itertools.product(*[range(len(visit_candidates[v])) for v in vset]):
            members = [(v, visit_candidates[v][i]) for v, i in zip(vset, combo)]
            pts = [dict(c['pseudo'][1], sigma_arcsec=SIGMA_POS_ARCSEC) for _, c in members]
            orb = distant.fit_orbit(pts, fix_radial=True)
            if not orb or not orb['bound'] or orb['chi2r'] > distant.ORBIT_CHI2R_MAX or not (distant.R_MIN_AU <= orb['r_au'] <= distant.R_MAX_AU):
                continue
            mir = distant.fit_orbit(pts, fix_radial=True, mirror=True)
            ratio = (mir['chi2r'] / max(orb['chi2r'], 1e-6)) if mir else None
            out.append({'visits': list(vset), 'members': [{'visit': v, 'ra': c['ra'], 'dec': c['dec'], 'snr': c['snr'], 'rate_arcsec_day': c['rate_arcsec_day']}
                                                          for v, c in members],
                        'orbit': orb, 'mirror_ratio': ratio, 'passes_mirror_test': bool(ratio is None or ratio >= distant.MIRROR_RATIO_MIN),
                        'detections': pts})
    # one solution per object: drop any solution that shares a candidate with a better one
    out.sort(key=lambda o: o['orbit']['chi2r'])
    used, keep = set(), []
    for o in out:
        key = {(m['visit'], round(m['ra'], 4), round(m['dec'], 4)) for m in o['members']}
        if key & used:
            continue
        used |= key
        keep.append(o)
    return keep
