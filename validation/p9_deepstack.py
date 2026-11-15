"""Planet Nine, as deep as SPHEREx can go: stack one week of images along the motion that parallax predicts.

    python -m validation.p9_deepstack fetch  [field]   # every 0.75-1.6 um image of a patch on the predicted Planet Nine track
    python -m validation.p9_deepstack stack  [field]   # remove the fixed sky (fitted from the other visits), stack along parallax, controls
    python -m validation.p9_deepstack inject [field]   # SYNTHETIC planets added to the real images: the depth reached
    python -m validation.p9_deepstack vet    [field]   # after the lock: split-half, per-detector and one-image checks of each candidate

Why this can work at all: over one week a body 150-1500 AU away moves on the sky almost only because the Earth moves
(its own orbital motion is a few per cent of that).  Its path is then fixed by its distance alone, so the stack needs a
grid of distances, not of every possible motion.  Fixed stars and galaxies are removed first by subtracting a template
made from all the images.  Synthetic Planet Nines are added to the real images to measure the depth reached, and the
same stack with the parallax reversed (a motion no distant body can have) measures the false-alarm level.
"""
from __future__ import annotations

import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    'p9-074+16': {'ra': 74.0, 'dec': 16.0, 'why': 'on the predicted Planet Nine track; the most 0.75-1.6 um images in one visit of the track points we checked. '
                                                  'Galactic latitude -15 deg: a crowded field.'},
    'p9-033-02': {'ra': 33.0, 'dec': -2.0, 'why': 'on the predicted Planet Nine track at Galactic latitude -60 deg: few stars, so deeper.'},
}
FIELD_ID = 'p9-074+16'
FIELD = FIELDS[FIELD_ID]
OUT = ROOT / 'validation' / 'p9_deepstack' / FIELD_ID
CACHE = ROOT / '.parallax-cache' / 'p9_deepstack' / FIELD_ID


def _use(field_id: str):
    global FIELD_ID, FIELD, OUT, CACHE
    FIELD_ID, FIELD = field_id, FIELDS[field_id]
    OUT = ROOT / 'validation' / 'p9_deepstack' / field_id
    CACHE = ROOT / '.parallax-cache' / 'p9_deepstack' / field_id
SIZE_ARCMIN = 30.0
PIX = 6.15
DETECTORS = (1, 2)
D_MIN, D_MAX = 150.0, 1500.0


def fetch(log=print) -> dict:
    """Every 0.75-1.6 um image of the patch, from every visit (the other visits make the fixed-sky template)."""
    from pipeline import spherex
    from pipeline.measure import gaia_field
    prods = [p for p in spherex.dedupe(spherex.search(FIELD['ra'], FIELD['dec'], radius_deg=0.001)) if p.detector in DETECTORS]
    visits = spherex.group_visits(prods, gap_days=20.0)
    CACHE.mkdir(parents=True, exist_ok=True)
    t = time.time()
    ok, failed = spherex.fetch_many(prods, FIELD['ra'], FIELD['dec'], SIZE_ARCMIN, CACHE, workers=6)
    gaia_field(FIELD['ra'], FIELD['dec'], SIZE_ARCMIN / 60 * 0.75, gmax=18.5, cache=CACHE / 'gaia_all.json')
    doc = {'field': FIELD, 'size_arcmin': SIZE_ARCMIN, 'n_images': len(prods), 'n_downloaded': len(ok), 'failed': [f['product_id'] for f in failed],
           'visits': [{'n_images': len(v), 'mjd_start': round(min(p.t_min for p in v), 2), 'span_days': round(max(p.t_min for p in v) - min(p.t_min for p in v), 2)}
                      for v in visits], 'detectors': DETECTORS}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'fetch.json').write_text(json.dumps(doc, indent=1))
    log(f"{len(ok)} of {len(prods)} images of RA {FIELD['ra']} Dec {FIELD['dec']} in {len(visits)} visits, in {time.time() - t:.0f} s")
    return doc


GRID_ARCSEC = 4.0                 # the common sky grid (native pixels are 6.15")
HALF_ARCMIN = 13.0                # grid half-width: a 26' square around the field centre
P9_R_AU = 550.0                   # Brown, Holman & Batygin (2024): V 22.0 at 550 AU (7.2 uJy); V 20.6 at the bright end (26.3 uJy)
INJECT = [(550.0, 80.0), (550.0, 60.0), (550.0, 40.0), (550.0, 26.0), (550.0, 15.0), (300.0, 40.0), (1000.0, 40.0)]   # (AU, uJy), SYNTHETIC
N_INJECT = 20
CLIP = 4.0                        # a sample more than 4 sigma off the fixed-sky fit is dropped (cosmic rays, star cores)
STAR_UJY = 400.0                  # sky pixels where the fixed sky is brighter than this are masked, with a 12" border
OVERSAMPLE = 3                    # the matched filter is evaluated at 3 x 3 sub-pixel offsets
HOLE_SIGMA = 3.0                  # ... and where the template visits' sky is 3 sigma darker than the ring around it (a dark hole)
HOLE_UJY = 15.0                   #     and at least 15 uJy below the field's usual level
SYS_FRAC = 0.05                   # each sample also carries 5% of the fixed sky under it as error (residuals of stars)
OUTLIER_PX = 2                    # a 4-sigma outlier masks a disc of 2 grid pixels (8") around it in that image
MOTION_MARGIN = 1.5               # a planet-like peak beats both controls at the same spot by 1.5 in S/N (a still source scores the same in all)
PEAK_BOX = 7                      # candidates are local maxima in a 7 x 7 box (28")
MIN_COVER = 0.6                   # a stacked pixel needs 60% of the images
ARCSEC_PER_RAD = 206264.806


def _tangent(ra, dec, ra0, dec0):
    ra, dec, ra0, dec0 = (np.radians(np.asarray(v, dtype=float)) for v in (ra, dec, ra0, dec0))
    c = np.sin(dec0) * np.sin(dec) + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0)
    xi = np.cos(dec) * np.sin(ra - ra0) / c
    eta = (np.cos(dec0) * np.sin(dec) - np.sin(dec0) * np.cos(dec) * np.cos(ra - ra0)) / c
    return np.degrees(xi) * 3600, np.degrees(eta) * 3600


def _untangent(xi, eta, ra0, dec0):
    xi, eta = np.radians(np.asarray(xi, dtype=float) / 3600), np.radians(np.asarray(eta, dtype=float) / 3600)
    ra0r, dec0r = math.radians(ra0), math.radians(dec0)
    rho = np.hypot(xi, eta)
    c = np.arctan(rho)
    with np.errstate(all='ignore'):
        dec = np.where(rho > 0, np.arcsin(np.cos(c) * math.sin(dec0r) + eta * np.sin(c) * math.cos(dec0r) / np.where(rho > 0, rho, 1)), dec0r)
    ra = ra0r + np.arctan2(xi * np.sin(c), rho * math.cos(dec0r) * np.cos(c) - eta * math.sin(dec0r) * np.sin(c))
    return np.degrees(ra) % 360, np.degrees(dec)


def _grid():
    n = int(round(2 * HALF_ARCMIN * 60 / GRID_ARCSEC))
    c = (n - 1) / 2
    X, Y = np.meshgrid((np.arange(n) - c) * GRID_ARCSEC, (np.arange(n) - c) * GRID_ARCSEC)
    return n, X, Y


def _mad(a):
    a = a[np.isfinite(a)]
    return float(1.4826 * np.median(np.abs(a - np.median(a)))) if a.size else float('nan')


def _parallax(mjd):
    """Arcsec of sky motion per (1 / distance in AU), east and north, at the field centre."""
    from pipeline.astrometry import parallax_factors
    pa, pd = parallax_factors(FIELD['ra'], FIELD['dec'], np.atleast_1d(mjd))
    return ARCSEC_PER_RAD * np.asarray(pa), ARCSEC_PER_RAD * np.asarray(pd)


def _track_dir():
    """Unit vector (east, north) of the predicted Planet Nine track at the field: the direction it moves along its orbit."""
    a = _tangent(60.0, 11.0, FIELD['ra'], FIELD['dec'])
    b = _tangent(90.0, 21.0, FIELD['ra'], FIELD['dec'])
    v = np.array([b[0] - a[0], b[1] - a[1]], dtype=float)
    return v / np.hypot(*v)


def _prepare(args):
    """One image: register to Gaia, add SYNTHETIC planets if asked, matched-filter flux and error maps, sampled on the grid."""
    path, inject, t_ref, field_id = args
    _use(field_id)
    from scipy.ndimage import binary_dilation, correlate, map_coordinates, median_filter
    from pipeline.measure import epsf_values, reference_candidates, register
    from pipeline.spherex import flag_mask, load_observation
    try:
        obs = load_observation(path)
        gaia = json.loads((CACHE / 'gaia_all.json').read_text())
        reg, _ = register(obs, reference_candidates([g for g in gaia if g.get('g') is not None and g['g'] < 18.5]))
        if not reg.ok:
            return path, None
        ny, nx = obs.shape
        if inject:
            pe, pn = _parallax([obs.mjd, t_ref])
            for xi0, eta0, r_au, f_ujy in inject:
                xi = xi0 + (pe[0] - pe[1]) / r_au
                eta = eta0 + (pn[0] - pn[1]) / r_au
                ra, dec = _untangent(xi, eta, FIELD['ra'], FIELD['dec'])
                x, y = (float(v) for v in obs.wcs.world_to_pixel_values(float(ra), float(dec)))
                x, y = x + reg.dx, y + reg.dy
                if not (7 <= x < nx - 7 and 7 <= y < ny - 7):
                    continue
                zone = obs.epsf_at(x, y)
                yy, xx = np.mgrid[int(y) - 5:int(y) + 6, int(x) - 5:int(x) + 6]
                obs.image[yy, xx] += (f_ujy / obs.ujy_per_unit) * epsf_values(zone, xx - x, yy - y)
        # SPHEREx's own artifact flags are masked too: crosstalk (an electronic echo of a bright star, a dark spot at a fixed place on the
        # detector, so at a different sky position in each visit), ghosts, halos, streaks, transients and ramp outliers.
        echo = flag_mask(obs.flag_names, {'CROSSTALK', 'GHOST', 'GHOST_FPA', 'GHOST_EXT'})
        other = flag_mask(obs.flag_names, {'HALO', 'STREAK', 'BLOOM', 'SNOWBALL', 'PHANMISS', 'DICHROIC'})
        mask = obs.hard_mask(strict=True) | binary_dilation((obs.flags & echo) != 0, iterations=1) | ((obs.flags & other) != 0)
        img = np.where(mask, np.nan, obs.image)
        med = np.nanmedian(img)
        resid = np.where(mask, 0.0, img - median_filter(np.where(mask, med, img), size=11, mode='nearest'))
        w = np.where(mask, 0.0, 1.0 / np.where(mask, 1.0, obs.variance))
        cover = correlate((~mask).astype(float), np.ones((3, 3)), mode='constant') / 9
        # The PSF is sharp and undersampled, so the matched filter (this image's own ePSF) is evaluated at 3 x 3 sub-pixel offsets
        # and interleaved into a map 3 times finer than the native pixels.
        zone = obs.epsf_at((nx - 1) / 2, (ny - 1) / 2)
        yy, xx = np.mgrid[-5:6, -5:6].astype(float)
        A = np.full((ny * OVERSAMPLE, nx * OVERSAMPLE), np.nan)
        E = np.full_like(A, np.nan)
        for iy in range(OVERSAMPLE):
            for ix in range(OVERSAMPLE):
                fx, fy = (ix - (OVERSAMPLE - 1) / 2) / OVERSAMPLE, (iy - (OVERSAMPLE - 1) / 2) / OVERSAMPLE
                K = epsf_values(zone, xx - fx, yy - fy)
                num = correlate(resid * w, K, mode='constant')
                den = correlate(w, K * K, mode='constant')
                ok = (den > 0) & (cover > 0.7)
                with np.errstate(all='ignore'):
                    A[iy::OVERSAMPLE, ix::OVERSAMPLE] = np.where(ok, num / den * obs.ujy_per_unit, np.nan)
                    E[iy::OVERSAMPLE, ix::OVERSAMPLE] = np.where(ok, obs.ujy_per_unit / np.sqrt(den), np.nan)
        n, X, Y = _grid()
        ra, dec = _untangent(X, Y, FIELD['ra'], FIELD['dec'])
        x, y = obs.wcs.world_to_pixel_values(ra, dec)
        x, y = np.asarray(x) + reg.dx, np.asarray(y) + reg.dy
        fine = [OVERSAMPLE * y + (OVERSAMPLE - 1) / 2, OVERSAMPLE * x + (OVERSAMPLE - 1) / 2]
        out = {'F': map_coordinates(A, fine, order=1, mode='constant', cval=np.nan).astype(np.float32),
               'S': map_coordinates(E, fine, order=1, mode='constant', cval=np.nan).astype(np.float32),
               'L': map_coordinates(obs.wave, [y, x], order=1, mode='constant', cval=np.nan).astype(np.float32)}
        return path, {'mjd': obs.mjd, 'detector': obs.detector, 'reg': [round(reg.dx, 3), round(reg.dy, 3)], **out}
    except Exception as error:  # noqa: BLE001
        return path, {'error': str(error)[:200]}


def _fit(F, S, L, use):
    """At every grid pixel, fit flux against wavelength (a quadratic) using the images in `use`, dropping 4-sigma outliers.
    Returns a function giving the fitted fixed sky at any image's wavelengths, and the brightest fitted value per pixel."""
    ok = np.isfinite(F) & np.isfinite(S) & (S > 0) & np.isfinite(L) & use[:, None, None]
    w0 = np.where(ok, 1.0 / np.where(ok, S, 1.0) ** 2, 0.0)
    x = np.where(np.isfinite(L), L - 1.15, 0.0)
    f = np.where(ok, F, 0.0)
    w = w0.copy()
    for _ in range(3):
        m = [np.sum(w * x ** k, axis=0) for k in range(5)]
        M = np.stack([np.stack([m[a + b] for b in range(3)], -1) for a in range(3)], -2)
        b = np.stack([np.sum(w * x ** a * f, axis=0) for a in range(3)], -1)
        good = (w > 0).sum(axis=0) >= 8
        coef = np.zeros(b.shape)
        coef[good] = np.linalg.solve(M[good] + np.eye(3) * 1e-12 * m[0][good][:, None, None], b[good][..., None])[..., 0]
        T = coef[None, ..., 0] + coef[None, ..., 1] * x + coef[None, ..., 2] * x * x
        z = np.where(ok, (f - T) * np.sqrt(w0), 0.0)
        w = np.where(np.abs(z) > CLIP, 0.0, w0)
    return T, good, np.where(ok, T, -np.inf).max(axis=0)


def _holes(F, S, use):
    """Dark holes in the template visits: the average there is HOLE_SIGMA below the ring of sky 8-20" around it, and HOLE_UJY below the
    field's usual level (crosstalk echoes the
    flags missed).  A real planet seen in the searched visit leaves the template visits' sky normal, so it is never masked by this."""
    from scipy.ndimage import correlate
    ok = np.isfinite(F) & np.isfinite(S) & (S > 0) & use[:, None, None]
    w = np.where(ok, 1.0 / np.where(ok, S, 1.0) ** 2, 0.0)
    sw = w.sum(axis=0)
    with np.errstate(all='ignore'):
        avg = np.where(sw > 0, (w * np.where(ok, F, 0.0)).sum(axis=0) / sw, np.nan)
        sig = 1.0 / np.sqrt(sw)
    r = int(round(20 / GRID_ARCSEC))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1] * GRID_ARCSEC
    ring = ((np.hypot(xx, yy) >= 8) & (np.hypot(xx, yy) <= 20)).astype(float)
    fin = np.isfinite(avg)
    with np.errstate(all='ignore'):
        around = correlate(np.where(fin, avg, 0.0), ring, mode='constant') / correlate(fin.astype(float), ring, mode='constant')
        return fin & ((avg - around) / sig < -HOLE_SIGMA) & (avg < np.nanmedian(avg) - HOLE_UJY)


def _clean(F, S, L, target):
    """Residuals of the target visit's images after removing the fixed sky, which is fitted from the OTHER visits only
    (months away, a distant planet is far from where it is now, so it cannot subtract itself)."""
    from scipy.ndimage import binary_dilation
    T, good, tmax = _fit(F, S, L, ~target)
    idx = np.nonzero(target)[0]
    Tt = T[idx]
    Fx = F[idx]
    Sx = S[idx].copy()
    ok = np.isfinite(Fx) & np.isfinite(Sx) & good[None]
    gains, scales = [], []
    R = np.zeros_like(Fx)
    for k in range(len(idx)):
        sel = ok[k] & (Tt[k] > 100) & (Tt[k] < 3000)          # each image's flux scale, from the stars it shares with the template
        g = float(np.sum(Fx[k][sel] * Tt[k][sel]) / np.sum(Tt[k][sel] ** 2)) if sel.sum() > 50 else 1.0
        gains.append(g)
        R[k] = np.where(ok[k], Fx[k] - g * Tt[k], 0.0)
        sc = _mad((R[k] / Sx[k])[ok[k]])                      # each image's real noise, measured on its residual
        scales.append(sc)
        Sx[k] = np.sqrt((Sx[k] * sc) ** 2 + (SYS_FRAC * np.abs(Tt[k])) ** 2)
    # sky pixels where the template cannot be trusted: bright stars (residuals), and dark holes (echoes the flags missed)
    stars = binary_dilation(tmax > STAR_UJY, iterations=int(round(12 / GRID_ARCSEC))) | binary_dilation(_holes(F, S, ~target), iterations=1)
    z = np.where(ok, R / np.where(ok, Sx, 1.0), 0.0)
    disc = np.hypot(*np.mgrid[-OUTLIER_PX:OUTLIER_PX + 1, -OUTLIER_PX:OUTLIER_PX + 1]) <= OUTLIER_PX
    bad = np.stack([binary_dilation(np.abs(zk) > CLIP, structure=disc) for zk in z])
    w = np.where(ok & ~bad & ~stars[None], 1.0 / np.where(ok, Sx, 1.0) ** 2, 0.0)
    R = np.where(w > 0, R, 0.0)
    return R, w, stars, {'single_5sigma_ujy': round(float(5 * np.nanmedian(np.where(ok, Sx, np.nan))), 1),
                         'noise_scale_median': round(float(np.median(scales)), 2), 'gain_range': [round(min(gains), 3), round(max(gains), 3)],
                         'outlier_fraction': round(float(bad.mean()), 4), 'masked_star_fraction': round(float(stars.mean()), 3)}


def _trials(mjds, t_ref):
    """(distance AU, rate along the track arcsec/day) pairs, spaced so that no image's predicted position moves by more than half a native pixel."""
    pe, pn = _parallax(mjds)
    pe0, pn0 = _parallax([t_ref])
    reach = float(np.max(np.hypot(pe - pe0[0], pn - pn0[0])))
    half_span = float(np.max(np.abs(np.asarray(mjds) - t_ref)))
    step_inv = 0.5 * PIX / reach
    inv = np.arange(1 / D_MAX, 1 / D_MIN + step_inv / 2, step_inv)
    out = []
    for d in 1 / inv:
        v_kms = 29.78 / math.sqrt(d)
        r_max = v_kms / (d * 1.495978707e8) * ARCSEC_PER_RAD * 86400
        dr = 0.5 * PIX / half_span
        k = int(math.floor(r_max / dr))
        out += [(float(d), float(j * dr)) for j in range(-k, k + 1)]
    return out, reach


def _offsets(mjds, t_ref, d, rate, mode):
    """Where a body at distance d sits in each image, relative to where it sits at t_ref, in grid pixels (east, north)."""
    pe, pn = _parallax(mjds)
    pe0, pn0 = _parallax([t_ref])
    u = (pe - pe0[0]) / d
    v = (pn - pn0[0]) / d
    if mode == 'reversed':                 # control: the parallax backwards, a motion no distant body can have
        u, v = -u, -v
    elif mode == 'rotated':                # control: the parallax turned by 90 degrees
        u, v = -v, u
    e = _track_dir()
    dt = np.asarray(mjds) - t_ref
    return (u + rate * dt * e[0]) / GRID_ARCSEC, (v + rate * dt * e[1]) / GRID_ARCSEC


def _stack_all(R, w, mjds, t_ref, trials, mode, keep=None):
    """Shift-and-stack every trial; return the best S/N at every pixel, which trial gave it, and (optionally) maps for some trials."""
    N, n, _ = R.shape
    offs = [_offsets(mjds, t_ref, d, r, mode) for d, r in trials]
    P = int(math.ceil(max(max(np.max(np.abs(u)), np.max(np.abs(v))) for u, v in offs))) + 2
    wr = np.pad(w * R, ((0, 0), (P, P), (P, P)))
    wp = np.pad(w, ((0, 0), (P, P), (P, P)))
    cp = np.pad((w > 0).astype(np.float32), ((0, 0), (P, P), (P, P)))
    best = np.full((n, n), -np.inf)
    which = np.full((n, n), -1, dtype=int)
    kept = {}
    for k, (u, v) in enumerate(offs):
        num = np.zeros((n, n))
        den = np.zeros((n, n))
        cnt = np.zeros((n, n))
        for i in range(N):
            iu, iv = int(math.floor(u[i])), int(math.floor(v[i]))
            fu, fv = u[i] - iu, v[i] - iv
            r0, c0 = P + iv, P + iu
            for arr, acc in ((wr, num), (wp, den), (cp, cnt)):
                a = arr[i]
                acc += ((1 - fu) * (1 - fv)) * a[r0:r0 + n, c0:c0 + n] + (fu * (1 - fv)) * a[r0:r0 + n, c0 + 1:c0 + 1 + n] \
                    + ((1 - fu) * fv) * a[r0 + 1:r0 + 1 + n, c0:c0 + n] + (fu * fv) * a[r0 + 1:r0 + 1 + n, c0 + 1:c0 + 1 + n]
        valid = (cnt >= MIN_COVER * N) & (den > 0)
        with np.errstate(all='ignore'):
            snr = np.where(valid, num / np.sqrt(den), np.nan)
            flux = np.where(valid, num / den, np.nan)
        scale = _mad(snr)
        snr = snr / scale
        if keep is not None and k in keep:
            kept[k] = {'snr': snr, 'flux': flux, 'sigma': np.where(valid, scale / np.sqrt(den), np.nan)}
        better = np.nan_to_num(snr, nan=-np.inf) > best
        best[better] = snr[better]
        which[better] = k
    return best, which, kept


MIN_VISIT_IMAGES = 10             # a visit is searched only if it has 10+ images (smaller ones still help the template)
STILL_SNR = 7.0                   # still sources (same S/N in every mode) brighter in this visit than in the others are listed from S/N 7


def _marked(res, mode, floor=5.0):
    """Peaks of one mode, each with its margin: its S/N minus the best S/N of the other two modes within 1 grid pixel."""
    from scipy.ndimage import maximum_filter
    others = [maximum_filter(np.nan_to_num(res[m][0], nan=-np.inf), size=3) for m in res if m != mode]
    out = []
    for snr, y, x in _peaks(res[mode][0], floor):
        out.append({'mode': mode, 'snr': snr, 'y': y, 'x': x, 'margin': snr - max(float(o[y, x]) for o in others)})
    return out


def _peaks(best, thresh):
    from scipy.ndimage import maximum_filter
    b = np.where(np.isfinite(best), best, -np.inf)
    loc = (b == maximum_filter(b, size=PEAK_BOX)) & (b >= thresh)
    ys, xs = np.nonzero(loc)
    return sorted(((float(b[y, x]), int(y), int(x)) for y, x in zip(ys, xs)), reverse=True)


def _visits(mjds):
    order = np.argsort(mjds)
    lab = np.zeros(len(mjds), dtype=int)
    v = 0
    for a, b in zip(order[:-1], order[1:]):
        if mjds[b] - mjds[a] > 20:
            v += 1
        lab[b] = v
    return lab


def _load(target, inject=None, workers=8):
    """Every image on the grid. `target` is the visit to search (0, 1, 2 in time order); t_ref is its mean time."""
    from astropy.io import fits
    files = sorted(CACHE.glob('*.fits'))
    mj = np.array([fits.getheader(f, 'IMAGE')['MJD-AVG'] for f in files])
    lab = _visits(mj)
    t_ref = float(mj[lab == target].mean())
    with ProcessPoolExecutor(max_workers=workers) as ex:
        got = dict(ex.map(_prepare, [(str(f), inject, t_ref, FIELD_ID) for f in files], chunksize=1))
    good = [(p, g) for p, g in got.items() if g and 'F' in g]
    good.sort(key=lambda t: t[1]['mjd'])
    F = np.stack([g['F'] for _, g in good]).astype(np.float64)
    S = np.stack([g['S'] for _, g in good]).astype(np.float64)
    L = np.stack([g['L'] for _, g in good]).astype(np.float64)
    mjds = np.array([g['mjd'] for _, g in good])
    vis = _visits(mjds)
    info = {'n_files': len(files), 'n_used': len(good), 'dropped': [Path(p).name for p, g in got.items() if not (g and 'F' in g)],
            't_ref_mjd': t_ref, 'n_target': int((vis == target).sum()), 'n_template': int((vis != target).sum()),
            'detectors': [g['detector'] for _, g in good]}
    return F, S, L, mjds, vis == target, t_ref, info


def _injection_positions(stars, seed):
    """SYNTHETIC planet positions at t_ref: spread over the inner grid, away from masked bright stars and from each other."""
    rng = np.random.default_rng(seed)
    n, X, Y = _grid()
    inner = HALF_ARCMIN * 60 * 0.62
    out, tries = [], 0
    while len(out) < N_INJECT and tries < 20000:
        tries += 1
        xi, eta = rng.uniform(-inner, inner, 2)
        j, k = int(round(xi / GRID_ARCSEC + (n - 1) / 2)), int(round(eta / GRID_ARCSEC + (n - 1) / 2))
        if stars[max(k - 4, 0):k + 5, max(j - 4, 0):j + 5].any():
            continue
        if any(math.hypot(xi - a, eta - b) < 150 for a, b in out):
            continue
        out.append((float(xi), float(eta)))
    return out


def _search_visit(target, log):
    t0 = time.time()
    F, S, L, mjds, tgt, t_ref, info = _load(target)
    R, w, stars, noise = _clean(F, S, L, tgt)
    m = mjds[tgt]
    trials, reach = _trials(m, t_ref)
    n = R.shape[1]
    log(f"visit {target + 1}: {info['n_target']} images searched, {info['n_template']} make the template; single-image 5-sigma "
        f"{noise['single_5sigma_ujy']} uJy; {len(trials)} trial motions; loaded in {time.time() - t0:.0f} s")
    res = {}
    for mode in ('real', 'reversed', 'rotated'):
        best, which, _ = _stack_all(R, w, m, t_ref, trials, mode)
        res[mode] = (best, which)
    top = {k: float(np.nanmax(np.where(np.isfinite(v[0]), v[0], np.nan))) for k, v in res.items()}
    area = float(np.isfinite(res['real'][0]).sum() * (GRID_ARCSEC / 3600) ** 2)
    marked = {mode: _marked(res, mode) for mode in res}
    ctrl = [p for mode in ('reversed', 'rotated') for p in marked[mode] if p['margin'] >= MOTION_MARGIN]
    thresh = max(5.0, math.ceil(max((p['snr'] for p in ctrl), default=0.0) * 10) / 10)
    rows, still = [], []
    for p in marked['real']:
        y, x = p['y'], p['x']
        xi, eta = (x - (n - 1) / 2) * GRID_ARCSEC, (y - (n - 1) / 2) * GRID_ARCSEC
        ra, dec = _untangent(xi, eta, FIELD['ra'], FIELD['dec'])
        d, r = trials[res['real'][1][y, x]]
        row = {'visit': target + 1, 'snr': round(p['snr'], 2), 'margin_over_controls': round(p['margin'], 2), 'ra': round(float(ra), 5),
               'dec': round(float(dec), 5), 'xi': xi, 'eta': eta, 'distance_au': round(d, 0), 'rate_arcsec_day': round(r, 2),
               'near_masked_star': bool(stars[max(y - 3, 0):y + 4, max(x - 3, 0):x + 4].any())}
        if p['margin'] >= MOTION_MARGIN and p['snr'] >= thresh:
            rows.append(row)
        elif p['margin'] < MOTION_MARGIN and p['snr'] >= STILL_SNR:
            still.append(row)
    out = {'visit': target + 1, 'images': info, 'noise': noise, 'mjd_span': [round(float(m.min()), 3), round(float(m.max()), 3)], 'area_deg2': round(area, 4),
           'n_trials': len(trials), 'parallax_reach_arcsec_au': round(reach, 0), 'max_snr': {k: round(v, 2) for k, v in top.items()},
           'threshold_snr': thresh, 'peaks_by_threshold': {mode: {str(t): len(_peaks(res[mode][0], t)) for t in (4.5, 5.0, 5.5, 6.0)} for mode in res},
           'control_planet_like': sorted([{'mode': p['mode'], 'snr': round(p['snr'], 2), 'margin': round(p['margin'], 2)} for p in ctrl], key=lambda q: -q['snr'])[:10],
           'candidates': rows, 'still_changes': still}
    np.savez_compressed(CACHE / f'stack_maps_v{target + 1}.npz', real=res['real'][0].astype(np.float32), reversed=res['reversed'][0].astype(np.float32),
                        rotated=res['rotated'][0].astype(np.float32), stars=stars)
    log(f"visit {target + 1}: max S/N real {top['real']:.2f}, reversed {top['reversed']:.2f}, rotated {top['rotated']:.2f}; threshold {thresh}; "
        f"{len(rows)} planet-like candidate(s); {len(still)} still change(s) at S/N {STILL_SNR}+; area {area:.3f} deg2; {time.time() - t0:.0f} s")
    return out


def stack(log=print) -> dict:
    from validation import ledger
    listed = json.loads((OUT / 'fetch.json').read_text())['visits']
    n_visits = sum(1 for v in listed if v['n_images'] >= MIN_VISIT_IMAGES)
    visits = [_search_visit(k, log) for k, v in enumerate(listed) if v['n_images'] >= MIN_VISIT_IMAGES]
    cands = [c for v in visits for c in v['candidates']]
    still = [c for v in visits for c in v['still_changes']]
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'field': FIELD, 'distance_au': [D_MIN, D_MAX],
           'settings': {'grid_arcsec': GRID_ARCSEC, 'clip_sigma': CLIP, 'star_mask_ujy': STAR_UJY, 'min_cover': MIN_COVER, 'peak_box_px': PEAK_BOX,
                        'template': 'per-pixel quadratic in wavelength fitted to the OTHER visits, 4-sigma clipped, 3 passes',
                        'oversample': OVERSAMPLE, 'sys_frac': SYS_FRAC, 'outlier_disc_px': OUTLIER_PX, 'hole_mask_sigma': HOLE_SIGMA,
                        'hole_mask_ujy': HOLE_UJY, 'motion_margin': MOTION_MARGIN, 'still_snr': STILL_SNR, 'min_visit_images': MIN_VISIT_IMAGES},
           'visits': visits, 'candidates': cands, 'n_candidates': len(cands), 'still_changes': still,
           'rule': 'Each visit is searched on its own, three ways: along the real parallax, along the parallax reversed, and along the parallax turned '
                   'by 90 degrees (no distant body can move in the last two ways). A peak is planet-like only if its S/N beats both other ways at '
                   f'the same spot by {MOTION_MARGIN}; a still source scores the same in all three. The threshold is the highest planet-like peak '
                   'of the two controls. A real planet-like peak above it is a candidate. Still sources that are brighter in one visit than in the '
                   f'others (S/N {STILL_SNR}+) are listed apart: they are not planets (variable stars, supernovae, optical ghosts). Everything is '
                   'written here and locked in the ledger before any checking.'}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'search.json').write_text(json.dumps(doc, indent=1))
    e = ledger.append(f'p9:deepstack:search:{FIELD_ID}', [OUT / 'search.json', OUT / 'fetch.json', Path(__file__)],
                      note=f'Planet Nine shift-and-stack along parallax, {n_visits} visits of patch {FIELD_ID}. Candidates locked before checking.')
    log(f"{len(cands)} planet-like candidate(s), {len(still)} still change(s), in {n_visits} visits; ledger entry {e['seq']}")
    return doc


def inject(log=print, target=None) -> dict:
    """SYNTHETIC planets, never real: added to every real image at the place their distance puts them, then visit `target` is searched
    with exactly the same steps to see which come back."""
    from validation import ledger
    search = json.loads((OUT / 'search.json').read_text())
    if target is None:                                   # the visit with the most images
        target = max(search['visits'], key=lambda v: v['images']['n_target'])['visit'] - 1
    vis = next(v for v in search['visits'] if v['visit'] == target + 1)
    thresh = vis['threshold_snr']
    stars = np.load(CACHE / f'stack_maps_v{target + 1}.npz')['stars']
    rows = []
    for k, (r_au, f_ujy) in enumerate(INJECT):
        t = time.time()
        pos = _injection_positions(stars, seed=100 + k)
        F, S, L, mjds, tgt, t_ref, info = _load(target, inject=[(xi, eta, r_au, f_ujy) for xi, eta in pos])
        R, w, _, _ = _clean(F, S, L, tgt)
        m = mjds[tgt]
        trials, _ = _trials(m, t_ref)
        res = {mode: _stack_all(R, w, m, t_ref, trials, mode)[:2] for mode in ('real', 'reversed', 'rotated')}
        best, which = res['real']
        marked = _marked(res, 'real', floor=-np.inf)
        n = R.shape[1]
        found, dist_ratio, snrs = 0, [], []
        for xi, eta in pos:
            y0, x0 = int(round(eta / GRID_ARCSEC + (n - 1) / 2)), int(round(xi / GRID_ARCSEC + (n - 1) / 2))
            near = [p for p in marked if abs(p['y'] - y0) <= 2 and abs(p['x'] - x0) <= 2]
            if not near:
                box = best[y0 - 2:y0 + 3, x0 - 2:x0 + 3]
                if np.isfinite(box).any():
                    snrs.append(float(np.nanmax(np.where(np.isfinite(box), box, np.nan))))
                continue
            p = max(near, key=lambda q: q['snr'])
            snrs.append(p['snr'])
            if p['snr'] >= thresh and p['margin'] >= MOTION_MARGIN:
                found += 1
                dist_ratio.append(trials[which[p['y'], p['x']]][0] / r_au)
        rows.append({'distance_au': r_au, 'flux_ujy': f_ujy, 'n_injected': len(pos), 'n_measured': len(snrs), 'n_recovered': found,
                     'median_snr': round(float(np.median(snrs)), 2) if snrs else None,
                     'distance_ratio_median': round(float(np.median(dist_ratio)), 3) if dist_ratio else None})
        log(f"SYNTHETIC {f_ujy:g} uJy at {r_au:g} AU: {found} of {len(snrs)} recovered above S/N {thresh} (median S/N {rows[-1]['median_snr']}) in {time.time() - t:.0f} s")
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'synthetic': True, 'visit': target + 1, 'threshold_snr': thresh,
           'results': rows,
           'note': 'SYNTHETIC planets built from each image\'s own ePSF (flat spectrum) and added to the real images of this patch, then searched for '
                   'with exactly the same steps. They measure the depth the stack reaches. Never real.'}
    (OUT / 'injection.json').write_text(json.dumps(doc, indent=1))
    e = ledger.append(f'p9:deepstack:injection:{FIELD_ID}', [OUT / 'injection.json'], note='Synthetic Planet Nines added to the real images: depth of the stack.')
    log(f"ledger entry {e['seq']}")
    return doc


def vet(log=print) -> dict:
    """Checks of the locked candidates, run after the lock.  A real source must show in both halves of the visit (by time) and in
    both detectors, and must not rest on one image.  Also: how many candidates the locked rule gives by chance, and whether
    the other visits can be checked at all (where its distance says it would be then)."""
    from validation import ledger
    search = json.loads((OUT / 'search.json').read_text())
    rows = []
    for c in search['candidates']:
        target = c['visit'] - 1
        F, S, L, mjds, tgt, t_ref, info = _load(target)
        R, w, _, _ = _clean(F, S, L, tgt)
        m = mjds[tgt]
        det = np.array(info['detectors'])[tgt]
        n = R.shape[1]
        y, x = int(round(c['eta'] / GRID_ARCSEC + (n - 1) / 2)), int(round(c['xi'] / GRID_ARCSEC + (n - 1) / 2))
        trial = [(c['distance_au'], c['rate_arcsec_day'])]

        def snr_of(sel):
            if sel.sum() < 4:
                return None
            _, _, kept = _stack_all(R[sel], w[sel], m[sel], t_ref, trial, 'real', keep={0})
            box = kept[0]['snr'][y - 1:y + 2, x - 1:x + 2]
            return round(float(np.nanmax(box)), 2) if np.isfinite(box).any() else None

        allsel = np.ones(len(m), bool)
        half = m < np.median(m)
        loo = []
        for i in range(len(m)):
            sel = allsel.copy()
            sel[i] = False
            loo.append(snr_of(sel))
        full = snr_of(allsel)
        drops = [full - v for v in loo if v is not None]
        u_ref = _offsets(np.array([t_ref]), t_ref, c['distance_au'], 0.0, 'real')
        others = []
        for v in search['visits']:
            if v['visit'] == c['visit']:
                continue
            tm = 0.5 * (v['mjd_span'][0] + v['mjd_span'][1])
            u, w_ = _offsets(np.array([tm]), t_ref, c['distance_au'], 0.0, 'real')
            sep = float(np.hypot(u[0] - u_ref[0][0], w_[0] - u_ref[1][0]) * GRID_ARCSEC / 60)
            others.append({'visit': v['visit'], 'predicted_shift_arcmin': round(sep, 1), 'inside_patch': bool(sep < HALF_ARCMIN)})
        res = {'snr_all': full, 'snr_first_half': snr_of(half), 'snr_second_half': snr_of(~half),
               'snr_detector_1': snr_of(det == 1), 'snr_detector_2': snr_of(det == 2),
               'largest_drop_removing_one_image': round(max(drops), 2) if drops else None, 'n_images': int(len(m)), 'other_visits': others}
        exp_half = (full or 0) / math.sqrt(2)
        res['passes_split_tests'] = bool(all(v is not None and v >= max(2.5, 0.5 * exp_half)
                                             for v in (res['snr_first_half'], res['snr_second_half'], res['snr_detector_1'], res['snr_detector_2'])))
        res['rests_on_one_image'] = bool(drops and max(drops) > 0.35 * full)
        rows.append({**c, 'checks': res})
        log(f"visit {c['visit']} candidate S/N {c['snr']}: halves {res['snr_first_half']} / {res['snr_second_half']}, detectors {res['snr_detector_1']} / "
            f"{res['snr_detector_2']}, largest one-image drop {res['largest_drop_removing_one_image']}; other visits: "
            + ', '.join(f"visit {o['visit']} {o['predicted_shift_arcmin']}' away" for o in others))
    n_vis = len(search['visits'])
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'field': FIELD, 'candidates': rows,
           'chance_expectation': {'per_visit': round(1 / 3, 3), 'visits': n_vis, 'expected': round(n_vis / 3, 2),
                                  'why': 'With no planet, the real search and the two controls are alike, so the real map\'s highest peak beats both '
                                         'controls\' highest peaks one time in three. The locked rule therefore expects about one chance candidate per '
                                         'three visits searched.'},
           'rule': 'A real source shows in both halves of the visit and in both detectors (S/N at least 2.5 and at least half of what a real '
                   'source would give in each), and does not rest on one image (removing any one image drops its S/N by less than 35%).'}
    (OUT / 'vet.json').write_text(json.dumps(doc, indent=1))
    e = ledger.append(f'p9:deepstack:vet:{FIELD_ID}', [OUT / 'vet.json', Path(__file__)], note='Checks of the locked Planet Nine stack candidates (after the lock).')
    log(f"{sum(1 for r in rows if r['checks']['passes_split_tests'] and not r['checks']['rests_on_one_image'])} of {len(rows)} pass; "
        f"chance expectation {doc['chance_expectation']['expected']}; ledger entry {e['seq']}")
    return doc


def cross(log=print) -> dict:
    """The deciding check for a candidate that passed vet: is it in another visit, where it must be?  For every other visit, the places
    it could be are worked out from the distances (2/3 to 3/2 of its best one, inside 100-1500 AU) and speeds along the track (its
    best speed, plus or minus two grid steps) that fit it.  The highest S/N of that visit's own search map over those places is
    compared with the same shape put at 300 random places in that map (how often noise alone gives as much)."""
    from scipy.ndimage import binary_dilation
    from validation import ledger
    search = json.loads((OUT / 'search.json').read_text())
    vet_doc = json.loads((OUT / 'vet.json').read_text())
    rng = np.random.default_rng(11)
    rows = []
    for c in vet_doc['candidates']:
        k = c['checks']
        if not (k['passes_split_tests'] and not k['rests_on_one_image']):
            continue
        vis_c = next(v for v in search['visits'] if v['visit'] == c['visit'])
        t_ref = vis_c['images']['t_ref_mjd']
        half = 0.5 * (vis_c['mjd_span'][1] - vis_c['mjd_span'][0])
        dr = 0.5 * PIX / max(half, 1e-3)
        out = []
        for v in search['visits']:
            if v['visit'] == c['visit']:
                continue
            maps = np.load(CACHE / f"stack_maps_v{v['visit']}.npz")
            best = maps['real']
            n = best.shape[0]
            tm = v['images']['t_ref_mjd']
            foot = np.zeros((n, n), bool)
            for d in np.linspace(max(100.0, c['distance_au'] / 1.5), min(1500.0, c['distance_au'] * 1.5), 25):
                for r in np.linspace(c['rate_arcsec_day'] - 2 * dr, c['rate_arcsec_day'] + 2 * dr, 9):
                    u, w_ = _offsets(np.array([tm]), t_ref, d, r, 'real')
                    x = int(round(c['xi'] / GRID_ARCSEC + u[0] + (n - 1) / 2))
                    y = int(round(c['eta'] / GRID_ARCSEC + w_[0] + (n - 1) / 2))
                    if 0 <= x < n and 0 <= y < n:
                        foot[y, x] = True
            if not foot.any():
                out.append({'visit': v['visit'], 'checkable': False, 'why': 'all the places it could be are outside this patch'})
                continue
            foot = binary_dilation(foot, iterations=2)
            fin = np.isfinite(best)
            cover = float((foot & fin).sum() / foot.sum())
            obs = float(np.nanmax(np.where(foot & fin, best, np.nan))) if (foot & fin).any() else None
            ys, xs = np.nonzero(foot)
            ctrl = []
            for _ in range(300):
                ang = rng.uniform(0, 2 * np.pi)
                cy, cx = ys.mean(), xs.mean()
                ry = np.round(cy + (ys - cy) * np.cos(ang) - (xs - cx) * np.sin(ang) + rng.uniform(-n / 2, n / 2)).astype(int)
                rx = np.round(cx + (ys - cy) * np.sin(ang) + (xs - cx) * np.cos(ang) + rng.uniform(-n / 2, n / 2)).astype(int)
                ok = (ry >= 0) & (ry < n) & (rx >= 0) & (rx < n)
                if ok.sum() < 0.8 * len(ys):
                    continue
                vals = best[ry[ok], rx[ok]]
                if np.isfinite(vals).sum() >= 0.5 * len(ys):
                    ctrl.append(float(np.nanmax(vals)))
            p_noise = round(float(np.mean(np.array(ctrl) >= obs)), 3) if (ctrl and obs is not None) else None
            out.append({'visit': v['visit'], 'checkable': True, 'places_px': int(foot.sum()), 'unmasked_fraction': round(cover, 2),
                        'max_snr_there': None if obs is None else round(obs, 2), 'n_random_shapes': len(ctrl),
                        'chance_of_as_much': p_noise})
            log(f"candidate visit {c['visit']} -> visit {v['visit']}: highest S/N where it must be {obs if obs is None else round(obs, 2)} "
                f"({cover:.0%} of those places searchable); noise gives as much {p_noise if p_noise is not None else '?'} of the time")
        rows.append({'visit': c['visit'], 'ra': c['ra'], 'dec': c['dec'], 'snr': c['snr'], 'distance_au': c['distance_au'],
                     'rate_arcsec_day': c['rate_arcsec_day'], 'other_visits': out})
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'field': FIELD, 'candidates': rows,
           'rule': 'A real distant body must also show in another visit where its distance and speed put it. Seen there: the highest S/N over '
                   'those places is 5 or more and noise gives as much less than 5% of the time. Not seen: below that.',
           'note': f'Speeds along the track use one direction per patch; for {FIELD_ID} it is ' +
                   ('the track direction at this patch.' if FIELD_ID == 'p9-074+16' else 'the direction of the track near RA 60-90 deg projected here (an approximation, disclosed).')}
    for r in rows:
        seen = [o for o in r['other_visits'] if o.get('checkable') and o['max_snr_there'] is not None and o['max_snr_there'] >= 5
                and (o['chance_of_as_much'] or 1) < 0.05]
        tried = [o for o in r['other_visits'] if o.get('checkable')]
        r['verdict'] = ('seen again: needs a third look before anything is said' if seen else
                        'not seen where it must be: not a planet' if tried else 'cannot be checked with these photos')
    (OUT / 'cross.json').write_text(json.dumps(doc, indent=1))
    e = ledger.append(f'p9:deepstack:cross:{FIELD_ID}', [OUT / 'cross.json', Path(__file__)], note='Candidates that passed vet, looked for in the other visits.')
    log('; '.join(f"visit {r['visit']} candidate: {r['verdict']}" for r in rows) + f"; ledger entry {e['seq']}")
    return doc


if __name__ == '__main__':
    if len(sys.argv) > 2:
        _use(sys.argv[2])
    {'fetch': fetch, 'stack': stack, 'inject': inject, 'vet': vet, 'cross': cross}[sys.argv[1] if len(sys.argv) > 1 else 'fetch']()
