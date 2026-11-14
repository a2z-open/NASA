"""Distant-world search: find slow solar-system bodies by their parallax.

SPHEREx images every patch of sky about every six months, always near 90 degrees from the Sun.  Between two
visits the Earth has moved to the other side of its orbit, so a body at distance r appears to jump by about
2 x (206265 / r) arcseconds: 2.2 degrees for Makemake at 53 AU, 14 arcminutes for a planet at 500 AU.  That
jump is parallax, and it gives the distance directly.

Stages (none of them is given an ephemeris or a target position):
  A  detect   matched-filter detection on the native pixels of every exposure, registered to Gaia DR3
  B  orphans  drop every detection that Gaia DR3 or CatWISE2020 already explains
  C  tracklet link orphans inside one visit along a straight sky track (hours to days)
  D  orbit    join tracklets from different visits with one orbit: six numbers, the heliocentric position
              and velocity at a reference time, moved under the Sun's gravity.  This follows the idea of
              HelioLinC (Holman et al. 2018, AJ 156, 135): at the right distance the body moves in a
              straight line as seen from the Sun.
  E  vetting  the orbit must be bound to the Sun, fit within the errors, and fail when the Earth is put on
              the wrong side of the Sun (the mirrored-Earth null test)
"""
from __future__ import annotations

import csv
import io
import json
import math
import time
from pathlib import Path

import numpy as np
from scipy.ndimage import correlate, median_filter
from scipy.optimize import least_squares

from .astrometry import JULIAN_YEAR_DAYS, earth_barycentric_au
from .hunt import _mad, find_peaks
from .measure import gaia_field, gaia_positions, measure_position, reference_candidates, register
from .spherex import PIXEL_ARCSEC, USER_AGENT, load_observation

MU = 4.0 * math.pi ** 2                 # GM of the Sun, AU^3 / yr^2
C_AU_YR = 63241.077                     # speed of light, AU / yr
RAD_ARCSEC = 180.0 * 3600.0 / math.pi
OBLIQUITY = math.radians(23.4392911)
IRSA_TAP = 'https://irsa.ipac.caltech.edu/TAP/sync'

# ---- thresholds: fixed before any distant-body data was scored (validation/distant/PROTOCOL.md) ----
DETECT_SNR = 5.0                        # matched-filter threshold per exposure
FIT_SNR_MIN = 4.0                       # ePSF-fit signal-to-noise needed to keep a detection
STAR_RADIUS_PX = 1.3                    # a detection this close to a catalogued source is "explained"
BRIGHT_RADII = ((7.0, 14.0), (10.0, 7.0), (13.0, 3.5))   # (Gaia G brighter than, exclusion radius in pixels)
RATE_MAX_ARCSEC_DAY = 200.0             # fastest sky motion linked (covers bodies beyond about 20 AU)
TRACKLET_MIN = 4                        # detections (distinct exposures) needed for a tracklet
TRACKLET_TOL_ARCSEC = 2.5               # link tolerance floor
SIGMA_FLOOR_ARCSEC = 0.6                # per-detection astrometric floor
R_MIN_AU, R_MAX_AU = 15.0, 20000.0
ORBIT_CHI2R_MAX = 4.0
MIRROR_RATIO_MIN = 9.0                  # mirrored-Earth chi-square must be at least this many times worse


def thresholds() -> dict:
    return {'detect_snr': DETECT_SNR, 'fit_snr_min': FIT_SNR_MIN, 'star_radius_px': STAR_RADIUS_PX,
            'rate_max_arcsec_day': RATE_MAX_ARCSEC_DAY, 'tracklet_min': TRACKLET_MIN,
            'tracklet_tol_arcsec': TRACKLET_TOL_ARCSEC, 'sigma_floor_arcsec': SIGMA_FLOOR_ARCSEC,
            'r_min_au': R_MIN_AU, 'r_max_au': R_MAX_AU, 'orbit_chi2r_max': ORBIT_CHI2R_MAX,
            'mirror_ratio_min': MIRROR_RATIO_MIN}


# =====================================================================================
# Stage A + B: detections in one exposure that no catalogue explains
# =====================================================================================

def catwise_field(ra: float, dec: float, radius_deg: float, cache: Path | None = None) -> list[dict]:
    """WISE sources in a cone.  CatWISE2020 (Marocco et al. 2021) from IRSA; if IRSA is down, the same catalogue
    from NOIRLab's Astro Data Lab; if that fails too, AllWISE from the ESA archive.  Each row records its source."""
    if cache is not None and cache.is_file():
        return json.loads(cache.read_text())
    import requests
    cone = f"CIRCLE('ICRS',{ra:.7f},{dec:.7f},{radius_deg:.5f})"
    services = [
        ('CatWISE2020 (IRSA)', 'get', IRSA_TAP, {'FORMAT': 'csv', 'QUERY': f"SELECT ra, dec, w1mpro, w2mpro FROM catwise_2020 WHERE CONTAINS(POINT('ICRS',ra,dec),{cone})=1"}, 45),
        ('CatWISE2020 (NOIRLab Astro Data Lab)', 'post', 'https://datalab.noirlab.edu/tap/sync',
         {'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': 'csv',
          'QUERY': f"SELECT ra, dec, w1mpro, w2mpro FROM catwise2020.main WHERE 't'=Q3C_RADIAL_QUERY(ra, dec, {ra:.7f}, {dec:.7f}, {radius_deg:.5f})"}, 120),
        ('AllWISE (ESA Gaia archive)', 'post', 'https://gea.esac.esa.int/tap-server/tap/sync',
         {'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': 'csv',
          'QUERY': f"SELECT ra, dec, w1mpro, w2mpro FROM gaiadr1.allwise_original_valid WHERE 1=CONTAINS(POINT('ICRS', ra, dec), {cone})"}, 120),
    ]
    rows, errors = None, []
    for name, method, url, params, timeout in services:
        for attempt in range(2):
            try:
                kw = {'timeout': timeout, 'headers': {'User-Agent': USER_AGENT}}
                r = requests.get(url, params=params, **kw) if method == 'get' else requests.post(url, data=params, **kw)
                if r.status_code != 200 or not r.text.lower().startswith('ra'):
                    raise RuntimeError(f'HTTP {r.status_code}')
                rows = []
                for row in csv.DictReader(io.StringIO(r.text)):
                    def num(k):
                        try:
                            v = float(row[k])
                            return v if math.isfinite(v) else None
                        except (TypeError, ValueError):
                            return None
                    if num('ra') is not None and num('dec') is not None:
                        rows.append({'ra': num('ra'), 'dec': num('dec'), 'w1': num('w1mpro'), 'w2': num('w2mpro'), 'cat': name})
                break
            except Exception as error:  # noqa: BLE001 - try the next service
                errors.append(f'{name}: {error}'[:120])
                rows = None
                time.sleep(3)
        if rows is not None:
            break
    if rows is None:
        raise RuntimeError('no WISE catalogue service answered: ' + '; '.join(errors))
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rows))
    return rows


def _snr_map(obs):
    """Matched-filter signal-to-noise on native pixels, renormalised to unit scatter."""
    mask = obs.hard_mask()
    img = np.where(mask, np.nan, obs.image)
    med = np.nanmedian(img)
    if not np.isfinite(med):
        return None, mask
    resid = np.where(mask, 0.0, img - median_filter(np.where(mask, med, img), size=11, mode='nearest'))
    fwhm_px = (obs.psf_fwhm_arcsec or 7.5) / PIXEL_ARCSEC
    s = max(fwhm_px / 2.3548, 0.45)
    r = int(math.ceil(3 * s))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    K = np.exp(-(xx * xx + yy * yy) / (2 * s * s))
    w = np.where(mask, 0.0, 1.0 / np.where(mask, 1.0, obs.variance))
    num = correlate(resid * w, K, mode='constant')
    den = correlate(w, K * K, mode='constant')
    cover = correlate((~mask).astype(float), K, mode='constant') / K.sum()
    valid = (den > 0) & (cover > 0.7)
    with np.errstate(all='ignore'):
        snr = num / np.sqrt(den)
    scale = _mad(snr[valid]) if valid.any() else 1.0
    if not math.isfinite(scale) or scale <= 0:
        scale = 1.0
    return np.where(valid, snr / scale, np.nan), mask


def detect_exposure(path, gaia_all: list[dict], catwise: list[dict], *, snr_min: float = DETECT_SNR) -> dict:
    """Every point source in one exposure that is NOT at the position of a Gaia DR3 or CatWISE2020 source.

    Returns {'ok', 'product_id', 'mjd', 'detector', 'n_peaks', 'n_explained', 'orphans': [...], 'reg': {...}}.
    """
    obs = load_observation(path)
    out = {'ok': False, 'product_id': obs.product_id, 'mjd': obs.mjd, 'detector': obs.detector, 'n_peaks': 0,
           'n_explained': 0, 'orphans': [], 'path': str(path)}
    refs = reference_candidates([s for s in gaia_all if s.get('g') is not None and s['g'] < 18.5])
    reg, _ = register(obs, refs)
    out['reg'] = {'ok': reg.ok, 'n_stars': reg.n_stars, 'rms_arcsec': None if not math.isfinite(reg.rms_arcsec) else round(reg.rms_arcsec, 3)}
    if not reg.ok:
        out['reason'] = reg.reason
        return out
    snr, _ = _snr_map(obs)
    if snr is None:
        out['reason'] = 'no_valid_pixels'
        return out
    peaks = find_peaks(snr, snr_min, edge=4)
    out['n_peaks'] = len(peaks)
    # catalogue sources in this exposure's own pixel frame (measured = predicted + registration shift)
    cx, cy, cr = [], [], []
    if gaia_all:
        gra, gdec = gaia_positions(gaia_all, obs.mjd)
        gx, gy = obs.wcs.world_to_pixel_values(gra, gdec)
        for x, y, s in zip(gx, gy, gaia_all):
            g = s.get('g') if s.get('g') is not None else 21.0
            cx.append(x + reg.dx)
            cy.append(y + reg.dy)
            cr.append(next((rad for lim, rad in BRIGHT_RADII if g < lim), STAR_RADIUS_PX))
    if catwise:
        wx, wy = obs.wcs.world_to_pixel_values([s['ra'] for s in catwise], [s['dec'] for s in catwise])
        for x, y, s in zip(wx, wy, catwise):
            w1 = s.get('w1') if s.get('w1') is not None else 18.0
            cx.append(x + reg.dx)
            cy.append(y + reg.dy)
            cr.append(4.0 if w1 < 8.5 else STAR_RADIUS_PX)
    cx, cy, cr = np.asarray(cx, float), np.asarray(cy, float), np.asarray(cr, float)
    for x, y, s in peaks:
        if cx.size and (np.hypot(cx - x, cy - y) <= cr).any():
            out['n_explained'] += 1
            continue
        f, pos = measure_position(obs, reg, x, y)
        if pos is None or not f.ok or not (f.snr >= FIT_SNR_MIN) or 'OVERFLOW' in f.flags:
            continue
        lam, _ = obs.wavelength_at(f.x, f.y)
        out['orphans'].append({
            'product_id': obs.product_id, 'obs_id': obs.obs_id, 'detector': obs.detector, 'mjd': obs.mjd,
            'ra': pos['ra'], 'dec': pos['dec'], 'sigma_arcsec': max(pos['sigma_arcsec'], SIGMA_FLOOR_ARCSEC),
            'snr': float(f.snr), 'peak_snr': float(s), 'flux_ujy': float(f.flux * obs.ujy_per_unit),
            'flux_err_ujy': float(f.flux_err * obs.ujy_per_unit), 'wavelength_um': None if not math.isfinite(lam) else float(lam),
            'chi2r': None if not math.isfinite(f.chi2r) else float(f.chi2r), 'flags': list(f.flags), 'x': float(f.x), 'y': float(f.y)})
    out['ok'] = True
    return out


def detect_file(args):
    path, gaia_all, catwise = args
    try:
        return detect_exposure(path, gaia_all, catwise)
    except Exception as error:  # noqa: BLE001 - one bad file must not stop the field
        return {'ok': False, 'path': str(path), 'reason': f'{type(error).__name__}: {error}'[:200], 'orphans': [], 'n_peaks': 0,
                'n_explained': 0}


# =====================================================================================
# Stage C: tracklets inside one visit
# =====================================================================================

def _local_xy(ra, dec, ra0, dec0):
    """Small-field tangent offsets in arcseconds."""
    return ((np.asarray(ra) - ra0 + 180.0) % 360.0 - 180.0) * math.cos(math.radians(dec0)) * 3600.0, (np.asarray(dec) - dec0) * 3600.0


def split_visits(mjd, gap_days: float = 25.0) -> np.ndarray:
    mjd = np.asarray(mjd, float)
    order = np.argsort(mjd)
    vid = np.zeros(len(mjd), int)
    v = 0
    for a, b in zip(order[:-1], order[1:]):
        if mjd[b] - mjd[a] > gap_days:
            v += 1
        vid[b] = v
    return vid


def tracklets(dets: list[dict], *, rate_max: float = RATE_MAX_ARCSEC_DAY, n_min: int = TRACKLET_MIN,
              tol_floor: float = TRACKLET_TOL_ARCSEC, min_dt: float = 0.02) -> list[dict]:
    """Link detections from one visit that lie on one straight sky track.  Returns tracklets, best first."""
    n = len(dets)
    if n < n_min:
        return []
    t = np.array([d['mjd'] for d in dets])
    ra0, dec0 = float(np.median([d['ra'] for d in dets])), float(np.median([d['dec'] for d in dets]))
    x, y = _local_xy([d['ra'] for d in dets], [d['dec'] for d in dets], ra0, dec0)
    sig = np.array([d['sigma_arcsec'] for d in dets])
    exp = np.array([hash(d['obs_id'] or d['product_id']) for d in dets])
    cands = []
    for i in range(n):
        dt = t - t[i]
        js = np.where(dt > min_dt)[0]
        if js.size == 0:
            continue
        vx, vy = (x[js] - x[i]) / dt[js], (y[js] - y[i]) / dt[js]
        ok = np.hypot(vx, vy) <= rate_max
        js, vx, vy = js[ok], vx[ok], vy[ok]
        if js.size == 0:
            continue
        # residual of every detection k from the line through i with each trial velocity j
        rx = x[None, :] - x[i] - vx[:, None] * dt[None, :]
        ry = y[None, :] - y[i] - vy[:, None] * dt[None, :]
        tol = np.maximum(tol_floor, 3.0 * np.sqrt(sig[None, :] ** 2 + sig[i] ** 2))
        hit = np.hypot(rx, ry) <= tol
        counts = hit.sum(axis=1)
        b = int(np.argmax(counts))
        members = np.where(hit[b])[0]
        if len(set(exp[members])) >= n_min:
            cands.append((len(set(exp[members])), i, members))
    cands.sort(key=lambda c: -c[0])
    used = np.zeros(n, bool)
    out = []
    for _, _, members in cands:
        members = members[~used[members]]
        if len(set(exp[members])) < n_min:
            continue
        # refine: weighted straight-line fit, then re-collect everything on that line
        for _ in range(3):
            tm = float(np.mean(t[members]))
            A = np.vstack([np.ones(len(members)), t[members] - tm]).T
            w = 1.0 / sig[members]
            (x0, vx0), *_ = np.linalg.lstsq(A * w[:, None], x[members] * w, rcond=None)
            (y0, vy0), *_ = np.linalg.lstsq(A * w[:, None], y[members] * w, rcond=None)
            res = np.hypot(x - x0 - vx0 * (t - tm), y - y0 - vy0 * (t - tm))
            new = np.where((res <= np.maximum(tol_floor, 3.0 * sig)) & ~used)[0]
            if len(set(exp[new])) < n_min or set(new) == set(members):
                break
            members = new
        if len(set(exp[members])) < n_min:
            continue
        # keep the best detection per exposure
        best = {}
        for k in members:
            if exp[k] not in best or res[k] < res[best[exp[k]]]:
                best[exp[k]] = k
        members = np.array(sorted(best.values(), key=lambda k: t[k]))
        used[members] = True
        rate = math.hypot(vx0, vy0)
        out.append({'members': [int(k) for k in members], 'n': int(len(members)), 't_mid_mjd': tm,
                    'span_days': float(t[members].max() - t[members].min()), 'rate_arcsec_day': float(rate),
                    'rms_arcsec': float(np.sqrt(np.mean(res[members] ** 2))),
                    'nights': int(len(set(np.floor(t[members]).astype(int))))})
    return out


# =====================================================================================
# Stage D: one orbit through several visits
# =====================================================================================

def _unit(ra_deg, dec_deg):
    a, d = np.radians(ra_deg), np.radians(dec_deg)
    return np.stack([np.cos(d) * np.cos(a), np.cos(d) * np.sin(a), np.sin(d)], axis=-1)


def _basis(a, d):
    rhat = np.array([math.cos(d) * math.cos(a), math.cos(d) * math.sin(a), math.sin(d)])
    east = np.array([-math.sin(a), math.cos(a), 0.0])
    north = np.array([-math.sin(d) * math.cos(a), -math.sin(d) * math.sin(a), math.cos(d)])
    return rhat, east, north


def predict(p, tau_yr, earth):
    """Apparent (RA, Dec) in degrees for an orbit p = (ra0, dec0 [rad], r0 [AU], v_east, v_north, v_radial [AU/yr]).

    The body starts at heliocentric distance r0 in direction (ra0, dec0) at tau = 0 and moves under the Sun's
    gravity (second-order series with the third-order term, ample for bodies beyond 15 AU over two years).
    Light-travel time is included.  `earth` is the observer's barycentric position in AU, shape (N, 3).
    """
    rhat, east, north = _basis(p[0], p[1])
    b0 = p[2] * rhat
    v0 = p[3] * east + p[4] * north + p[5] * rhat
    r3 = p[2] ** 3
    acc = -MU * b0 / r3
    jerk = -MU * (v0 / r3 - 3.0 * b0 * float(b0 @ v0) / p[2] ** 5)

    def pos(tau):
        tau = tau[:, None]
        return b0 + v0 * tau + 0.5 * acc * tau ** 2 + jerk * tau ** 3 / 6.0

    tau_yr = np.asarray(tau_yr, float)
    d = pos(tau_yr) - earth
    d = pos(tau_yr - np.linalg.norm(d, axis=1) / C_AU_YR) - earth
    rho = np.linalg.norm(d, axis=1)
    return np.degrees(np.arctan2(d[:, 1], d[:, 0])) % 360.0, np.degrees(np.arcsin(d[:, 2] / rho)), rho


def _residuals(p, tau, earth, ra, dec, sig):
    pra, pdec, _ = predict(p, tau, earth)
    dra = ((pra - ra + 180.0) % 360.0 - 180.0) * np.cos(np.radians(dec)) * 3600.0
    return np.concatenate([dra / sig, (pdec - dec) * 3600.0 / sig])


def _seed(r, tau, earth, u):
    """HelioLinC-style seed: put every detection at heliocentric distance r and fit a straight line in space."""
    eu = np.einsum('ij,ij->i', earth, u)
    disc = eu ** 2 - (np.einsum('ij,ij->i', earth, earth) - r * r)
    if (disc < 0).any():
        return None
    b = earth + (-eu + np.sqrt(disc))[:, None] * u
    A = np.vstack([np.ones(len(tau)), tau]).T
    coef, *_ = np.linalg.lstsq(A, b, rcond=None)
    b0, v0 = coef[0], coef[1]
    r0 = float(np.linalg.norm(b0))
    a0, d0 = math.atan2(b0[1], b0[0]), math.asin(b0[2] / r0)
    rhat, east, north = _basis(a0, d0)
    return np.array([a0, d0, r0, float(v0 @ east), float(v0 @ north), float(v0 @ rhat)])


def fit_orbit(dets: list[dict], *, fix_radial: bool = False, mirror: bool = False, t0_mjd: float | None = None) -> dict | None:
    """Least-squares orbit through detections.  `mirror` puts the Earth on the wrong side of the Sun (null test)."""
    if len(dets) < 3:
        return None
    mjd = np.array([d['mjd'] for d in dets])
    ra = np.array([d['ra'] for d in dets])
    dec = np.array([d['dec'] for d in dets])
    sig = np.maximum(np.array([d['sigma_arcsec'] for d in dets]), SIGMA_FLOOR_ARCSEC)
    t0 = float(np.mean(mjd)) if t0_mjd is None else t0_mjd
    tau = (mjd - t0) / JULIAN_YEAR_DAYS
    earth = earth_barycentric_au(mjd)
    if mirror:
        earth = -earth
    u = _unit(ra, dec)
    n_par = 5 if fix_radial else 6

    def run(seed):
        if fix_radial:
            fun = lambda q: _residuals(np.array([q[0], q[1], q[2], q[3], q[4], 0.0]), tau, earth, ra, dec, sig)  # noqa: E731
            x0 = seed[:5]
        else:
            fun = lambda q: _residuals(q, tau, earth, ra, dec, sig)  # noqa: E731
            x0 = seed
        scale = np.array([1e-6, 1e-6, max(seed[2] * 0.01, 0.05), 0.02, 0.02, 0.05])[:n_par]
        lo = np.array([-np.inf, -np.inf, 2.0, -np.inf, -np.inf, -np.inf])[:n_par]
        try:
            return least_squares(fun, x0, x_scale=scale, bounds=(lo, np.inf), max_nfev=400)
        except Exception:  # noqa: BLE001
            return None

    seeds = []
    for r in np.geomspace(R_MIN_AU, R_MAX_AU, 60):
        s = _seed(r, tau, earth, u)
        if s is None:
            continue
        seeds.append((float(np.sum(_residuals(s, tau, earth, ra, dec, sig) ** 2)), s))
    if not seeds:
        return None
    seeds.sort(key=lambda z: z[0])
    best = None
    for _, s in seeds[:4]:
        sol = run(s)
        if sol is not None and (best is None or sol.cost < best.cost):
            best = sol
    if best is None:
        return None
    q = best.x
    p = np.array([q[0], q[1], q[2], q[3], q[4], 0.0 if fix_radial else q[5]])
    chi2 = float(2.0 * best.cost)
    dof = max(2 * len(dets) - n_par, 1)
    chi2r = chi2 / dof
    try:
        cov = np.linalg.inv(best.jac.T @ best.jac) * max(chi2r, 1.0)
        err = np.sqrt(np.clip(np.diag(cov), 0, None))
    except np.linalg.LinAlgError:
        err = np.full(n_par, np.nan)
    rhat, east, north = _basis(p[0], p[1])
    b0, v0 = p[2] * rhat, p[3] * east + p[4] * north + p[5] * rhat
    speed2 = float(v0 @ v0)
    energy = 0.5 * speed2 - MU / p[2]
    h = np.cross(b0, v0)
    pole = np.array([0.0, -math.sin(OBLIQUITY), math.cos(OBLIQUITY)])
    inc = math.degrees(math.acos(np.clip(h @ pole / (np.linalg.norm(h) or 1.0), -1, 1))) if np.linalg.norm(h) > 0 else None
    res = _residuals(p, tau, earth, ra, dec, sig)
    half = len(dets)
    pra, pdec, rho = predict(p, tau, earth)
    return {
        't0_mjd': t0, 'params': [float(v) for v in p], 'n': len(dets), 'n_par': n_par, 'chi2': chi2, 'dof': dof, 'chi2r': chi2r,
        'r_au': float(p[2]), 'r_err_au': float(err[2]) if math.isfinite(err[2]) else None,
        'ra0_deg': math.degrees(p[0]) % 360.0, 'dec0_deg': math.degrees(p[1]),
        'speed_au_yr': math.sqrt(speed2), 'escape_au_yr': math.sqrt(2 * MU / p[2]), 'bound': bool(energy < 0),
        'tangential_arcsec_yr': float(math.hypot(p[3], p[4]) / p[2] * RAD_ARCSEC),
        'parallax_arcsec': float(RAD_ARCSEC / p[2]),
        'a_au': float(-MU / (2 * energy)) if energy < 0 else None, 'inclination_deg': inc,
        'rms_arcsec': float(np.sqrt(np.mean((res[:half] * sig) ** 2 + (res[half:] * sig) ** 2))),
        'geocentric_au': [float(v) for v in rho],
        'resid_arcsec': [[float(a * s), float(b * s)] for a, b, s in zip(res[:half], res[half:], sig)],
    }


def link_orbits(dets: list[dict], tracks: list[dict], visit_of: list[int], *, chi2r_max: float = ORBIT_CHI2R_MAX,
                fix_radial: bool = False) -> list[dict]:
    """Join tracklets from different visits.  `tracks[i]['members']` index into `dets`; `visit_of[i]` is its visit."""
    cands = []
    for i in range(len(tracks)):
        for j in range(i + 1, len(tracks)):
            if visit_of[i] == visit_of[j]:
                continue
            members = tracks[i]['members'] + tracks[j]['members']
            orb = fit_orbit([dets[k] for k in members], fix_radial=fix_radial)
            if orb and orb['chi2r'] <= chi2r_max and orb['bound'] and R_MIN_AU <= orb['r_au'] <= R_MAX_AU:
                cands.append({'tracks': [i, j], 'members': members, 'orbit': orb})
    # grow pairs into triples, quadruples, ... while the orbit still fits
    grown = True
    while grown:
        grown = False
        for c in list(cands):
            vs = {visit_of[i] for i in c['tracks']}
            for k in range(len(tracks)):
                if k in c['tracks'] or visit_of[k] in vs:
                    continue
                members = c['members'] + tracks[k]['members']
                orb = fit_orbit([dets[m] for m in members], fix_radial=fix_radial)
                if orb and orb['chi2r'] <= chi2r_max and orb['bound']:
                    new = {'tracks': c['tracks'] + [k], 'members': members, 'orbit': orb}
                    if not any(set(new['tracks']) == set(o['tracks']) for o in cands):
                        cands.append(new)
                        grown = True
    cands.sort(key=lambda c: (-len(c['tracks']), c['orbit']['chi2r']))
    out, used = [], set()
    for c in cands:
        if used & set(c['tracks']):
            continue
        used |= set(c['tracks'])
        mirror = fit_orbit([dets[m] for m in c['members']], fix_radial=fix_radial, mirror=True)
        c['mirror_chi2r'] = mirror['chi2r'] if mirror else None
        c['mirror_ratio'] = (mirror['chi2r'] / max(c['orbit']['chi2r'], 1e-9)) if mirror else None
        c['passes_mirror_test'] = bool(mirror is None or c['mirror_ratio'] >= MIRROR_RATIO_MIN)
        c['n_visits'] = len({visit_of[i] for i in c['tracks']})
        out.append(c)
    return out


def reflectance(dets: list[dict], bins: int = 24) -> list[dict]:
    """Relative reflectance along a track: measured flux divided by a 5772 K black body (a stand-in for the solar
    spectrum), binned in wavelength and normalised to its median.  Indicative only."""
    lam = np.array([d['wavelength_um'] or np.nan for d in dets])
    f = np.array([d['flux_ujy'] for d in dets])
    e = np.array([d['flux_err_ujy'] for d in dets])
    ok = np.isfinite(lam) & np.isfinite(f) & np.isfinite(e) & (e > 0)
    if ok.sum() < 6:
        return []
    lam, f, e = lam[ok], f[ok], e[ok]
    x = 14387.77 / (lam * 5772.0)
    sun = 1.0 / (lam ** 3 * np.expm1(x))          # B_nu shape
    refl, rerr = f / sun, e / sun
    edges = np.linspace(lam.min(), lam.max() + 1e-6, bins + 1)
    rows = []
    for a, b in zip(edges[:-1], edges[1:]):
        s = (lam >= a) & (lam < b)
        if s.sum() == 0:
            continue
        w = 1.0 / rerr[s] ** 2
        rows.append({'wavelength_um': float(np.sum(lam[s] * w) / w.sum()), 'value': float(np.sum(refl[s] * w) / w.sum()),
                     'err': float(1.0 / math.sqrt(w.sum())), 'n': int(s.sum()),
                     'flux_ujy': float(np.sum(f[s] / e[s] ** 2) / np.sum(1.0 / e[s] ** 2))})
    med = float(np.median([r['value'] for r in rows])) or 1.0
    for r in rows:
        r['value'] /= med
        r['err'] /= med
    return rows
