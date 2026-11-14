"""Native-pixel measurements: ePSF fitting, forced photometry and field-star registration.

All measurements are made on the original (non-reprojected) cutout pixels, using
the release-provided effective PSF (EPSF extension) nearest the source.  The ePSF
is pixel-integrated and normalised to unit sum on its 5x oversampled grid, so a
native-pixel value at offset (dx, dy) from the source centre is
    flux * ov^2 * P(c + ov*dy, c + ov*dx)
where c = 16 is the ePSF peak index.  A constant offset in that convention is
common to every star and cancels in the differential registration.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import io
import csv
import json
import math
from pathlib import Path

import numpy as np
import requests
from scipy.ndimage import map_coordinates
from scipy.optimize import least_squares

from .astrometry import propagate
from .spherex import Observation, HARD_FLAGS, STRICT_EXTRA, flag_mask

GAIA_TAP = 'https://gea.esac.esa.int/tap-server/tap/sync'
EPSF_CENTER = 16.0
STAMP_RADIUS = 3            # pixels; 7x7 fitting stamp
BKG_INNER, BKG_OUTER = 5, 9


@dataclass
class Fit:
    ok: bool
    reason: str
    x: float = math.nan
    y: float = math.nan
    sx: float = math.nan
    sy: float = math.nan
    flux: float = math.nan        # sum in MJy/sr * pixel
    flux_err: float = math.nan
    background: float = math.nan
    chi2r: float = math.nan
    n_pix: int = 0
    n_masked_core: int = 0
    snr: float = math.nan
    flags: tuple = ()

    def to_dict(self):
        d = asdict(self)
        d['flags'] = list(self.flags)
        return {k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in d.items()}


def epsf_values(zone, dx, dy):
    """ePSF fraction of total flux in native pixels at offsets dx, dy (arrays)."""
    ov = zone.oversample
    coords = [EPSF_CENTER + ov * np.asarray(dy, dtype=float), EPSF_CENTER + ov * np.asarray(dx, dtype=float)]
    vals = map_coordinates(zone.data, coords, order=3, mode='constant', cval=0.0)
    return vals * ov * ov


def local_background(obs: Observation, x: float, y: float, mask: np.ndarray) -> tuple[float, float]:
    yy, xx = np.indices(obs.shape)
    r2 = (xx - x) ** 2 + (yy - y) ** 2
    sel = (r2 >= BKG_INNER ** 2) & (r2 <= BKG_OUTER ** 2) & ~mask
    vals = obs.image[sel]
    if vals.size < 12:
        return math.nan, math.nan
    for _ in range(4):  # sigma clip
        med = np.median(vals)
        mad = 1.4826 * np.median(np.abs(vals - med))
        keep = np.abs(vals - med) < 3 * max(mad, 1e-6)
        if keep.all():
            break
        vals = vals[keep]
    return float(np.median(vals)), float(1.4826 * np.median(np.abs(vals - np.median(vals))) / math.sqrt(max(vals.size, 1)))


def fit_source(obs: Observation, x0: float, y0: float, *, fix_position: bool = False, strict: bool = False,
               max_shift: float = 1.5, others=(), allow_saturated_core: bool = False) -> Fit:
    """Fit flux (and optionally position) of a point source with the local ePSF.

    `others` lists (x, y) pixel positions of known neighbours (e.g. Gaia stars propagated to this
    epoch).  Their fluxes are fitted simultaneously with fixed positions (scene-model deblending).
    """
    ny, nx = obs.shape
    if not (STAMP_RADIUS <= x0 <= nx - 1 - STAMP_RADIUS and STAMP_RADIUS <= y0 <= ny - 1 - STAMP_RADIUS):
        return Fit(False, 'off_image')
    zone = obs.epsf_at(x0, y0)
    if zone is None:
        return Fit(False, 'no_epsf')
    mask = obs.hard_mask(strict=strict)
    if allow_saturated_core:
        # Wing mode: additionally exclude bleeding/bloom pixels; fit only clean pixels around a saturated core.
        mask = mask | ((obs.flags & flag_mask(obs.flag_names, {'BLOOM', 'TRANSIENT', 'OVERFLOW', 'NONLINEAR', 'SUR_ERROR'})) != 0)
    xc, yc = int(round(x0)), int(round(y0))
    ys = slice(yc - STAMP_RADIUS, yc + STAMP_RADIUS + 1)
    xs = slice(xc - STAMP_RADIUS, xc + STAMP_RADIUS + 1)
    data = obs.image[ys, xs]
    var = obs.variance[ys, xs]
    bad = mask[ys, xs]
    yy, xx = np.mgrid[ys, xs]
    core = (xx - x0) ** 2 + (yy - y0) ** 2 <= 1.5 ** 2
    n_masked_core = int((bad & core).sum())
    near_flags = tuple(obs.flags_near(x0, y0, 1.5))
    if allow_saturated_core:
        if (~bad).sum() < 10:
            return Fit(False, 'too_few_wing_pixels', n_masked_core=n_masked_core, flags=near_flags)
    elif (~bad & core).sum() < 3:
        sat = flag_mask(obs.flag_names, {'OVERFLOW', 'NONLINEAR'})
        reason = 'core_saturated' if (obs.flags[ys, xs][core] & sat).any() else 'core_masked'
        return Fit(False, reason, n_masked_core=n_masked_core, flags=near_flags)
    bkg, bkg_err = local_background(obs, x0, y0, mask)
    if not math.isfinite(bkg):
        return Fit(False, 'no_background', flags=near_flags)
    good = ~bad
    d = (data - bkg)[good]
    sig = np.sqrt(var[good] + bkg_err ** 2)
    px, py = xx[good].astype(float), yy[good].astype(float)

    others = [(ox, oy) for ox, oy in others if abs(ox - x0) <= STAMP_RADIUS + 1.5 and abs(oy - y0) <= STAMP_RADIUS + 1.5]
    other_psf = [epsf_values(zone, px - ox, py - oy) for ox, oy in others]
    k_other = len(other_psf)

    def model(p):
        extra = sum(p[len(p) - k_other + i] * other_psf[i] for i in range(k_other)) if k_other else 0.0
        if fix_position:
            f, b = p[0], p[1]
            return f * epsf_values(zone, px - x0, py - y0) + b + extra
        f, x, y, b = p[0], p[1], p[2], p[3]
        return f * epsf_values(zone, px - x, py - y) + b + extra

    def resid(p):
        return (d - model(p)) / sig

    f0 = max(float(np.nansum(d[(px - x0) ** 2 + (py - y0) ** 2 <= 2.5])), 1e-3)
    if fix_position:
        p0, lb, ub = [f0, 0.0], [-np.inf, -np.inf], [np.inf, np.inf]
    else:
        p0 = [f0, x0, y0, 0.0]
        lb = [-np.inf, x0 - max_shift, y0 - max_shift, -np.inf]
        ub = [np.inf, x0 + max_shift, y0 + max_shift, np.inf]
    if k_other:
        p0 = p0 + [f0] * k_other
        lb = lb + [-np.inf] * k_other
        ub = ub + [np.inf] * k_other
    if d.size <= len(p0) + 2:
        return Fit(False, 'too_few_pixels', flags=near_flags)
    try:
        res = least_squares(resid, p0, bounds=(lb, ub), x_scale='jac', max_nfev=200)
    except (ValueError, np.linalg.LinAlgError):
        return Fit(False, 'fit_failed', flags=near_flags)
    n = d.size
    k = len(p0)
    dof = max(n - k, 1)
    chi2r = float(np.sum(res.fun ** 2) / dof)
    try:
        J = res.jac
        cov = np.linalg.inv(J.T @ J) * max(chi2r, 1.0)
        err = np.sqrt(np.clip(np.diag(cov), 0, np.inf))
    except np.linalg.LinAlgError:
        return Fit(False, 'singular', flags=near_flags)
    if fix_position:
        f, b = res.x[0], res.x[1]
        x, y, sx, sy = x0, y0, 0.0, 0.0
        ferr = err[0]
    else:
        f, x, y, b = res.x[0], res.x[1], res.x[2], res.x[3]
        ferr, sx, sy = err[0], err[1], err[2]
        if abs(x - x0) >= max_shift - 1e-3 or abs(y - y0) >= max_shift - 1e-3:
            return Fit(False, 'centroid_at_bound', flux=float(f), flags=near_flags)
    return Fit(True, 'ok', float(x), float(y), float(sx), float(sy), float(f), float(ferr), float(bkg + b),
               chi2r, int(n), n_masked_core, float(f / ferr) if ferr > 0 else math.nan, near_flags)


# ---------------------------------------------------------------------------
# Gaia DR3 field stars (for registration and catalogue context)
# ---------------------------------------------------------------------------

def gaia_field(ra: float, dec: float, radius_deg: float, *, gmax: float = 18.5, cache: Path | None = None) -> list[dict]:
    if cache is not None and cache.is_file():
        return json.loads(cache.read_text())
    adql = (
        'SELECT source_id, ra, dec, pmra, pmdec, parallax, pmra_error, pmdec_error, parallax_error, '
        'phot_g_mean_mag, bp_rp, ruwe, ref_epoch FROM gaiadr3.gaia_source '
        f'WHERE 1=CONTAINS(POINT(ra, dec), CIRCLE({ra:.7f}, {dec:.7f}, {radius_deg:.5f})) '
        f'AND phot_g_mean_mag < {gmax}'
    )
    r = requests.post(GAIA_TAP, data={'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': 'csv', 'QUERY': adql}, timeout=90)
    r.raise_for_status()
    rows = []
    for row in csv.DictReader(io.StringIO(r.text)):
        def num(k):
            try:
                v = float(row[k])
                return v if math.isfinite(v) else None
            except (TypeError, ValueError):
                return None
        rows.append({'source_id': row['source_id'], 'ra': num('ra'), 'dec': num('dec'), 'pmra': num('pmra'),
                     'pmdec': num('pmdec'), 'parallax': num('parallax'), 'pmra_error': num('pmra_error'),
                     'pmdec_error': num('pmdec_error'), 'parallax_error': num('parallax_error'),
                     'g': num('phot_g_mean_mag'), 'bp_rp': num('bp_rp'), 'ruwe': num('ruwe'),
                     'ref_epoch': num('ref_epoch')})
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rows))
    return rows


GAIA_EPOCH_MJD = 57388.5   # J2016.0


def gaia_positions(stars: list[dict], mjd: float) -> tuple[np.ndarray, np.ndarray]:
    ra = np.empty(len(stars))
    dec = np.empty(len(stars))
    for i, s in enumerate(stars):
        if s.get('pmra') is not None and s.get('pmdec') is not None:
            p = propagate(s['ra'], s['dec'], GAIA_EPOCH_MJD, s['pmra'], s['pmdec'], s.get('parallax') or 0.0, [mjd])
            ra[i], dec[i] = p.ra[0], p.dec[0]
        else:
            ra[i], dec[i] = s['ra'], s['dec']
    return ra, dec


@dataclass
class Registration:
    ok: bool
    dx: float          # measured - predicted (pixels); subtract from measured positions
    dy: float
    err_x: float
    err_y: float
    n_stars: int
    rms_arcsec: float
    star_scatter_px: float   # empirical per-star centroid scatter after registration
    sys_floor_px: float = math.nan  # scatter in excess of the formal centroid errors
    reason: str = 'ok'

    def to_dict(self):
        return {k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in asdict(self).items()}


def reference_candidates(stars, *, exclude_ids=(), min_sep_arcsec=20.0):
    """Gaia stars with full astrometry, low RUWE, and no comparably bright neighbour within 20"."""
    good = [s for s in stars if s['pmra'] is not None and s['g'] is not None and (s['ruwe'] or 99) < 1.4
            and s['source_id'] not in set(exclude_ids)]
    if not good:
        return []
    ra = np.array([s['ra'] for s in stars])
    dec = np.array([s['dec'] for s in stars])
    g = np.array([s['g'] if s['g'] is not None else 25 for s in stars])
    out = []
    for s in good:
        d = np.hypot((ra - s['ra']) * math.cos(math.radians(s['dec'])), dec - s['dec']) * 3600
        neighbour = (d > 0.01) & (d < min_sep_arcsec) & (g < s['g'] + 2.5)
        if not neighbour.any():
            out.append(s)
    return out


def register(obs: Observation, refs: list[dict], *, min_snr=15.0, max_stars=40) -> tuple[Registration, list[dict]]:
    """Fit a pure shift between WCS-predicted and measured positions of Gaia reference stars."""
    if not refs:
        return Registration(False, 0, 0, math.nan, math.nan, 0, math.nan, math.nan, math.nan, 'no_reference_stars'), []
    ra, dec = gaia_positions(refs, obs.mjd)
    x, y = obs.wcs.world_to_pixel_values(ra, dec)
    ny, nx = obs.shape
    inside = (x > 4) & (x < nx - 5) & (y > 4) & (y < ny - 5)
    order = np.argsort([refs[i]['g'] for i in range(len(refs))])
    rows = []
    for i in order:
        if not inside[i] or len(rows) >= max_stars * 2:
            continue
        f = fit_source(obs, float(x[i]), float(y[i]), strict=True, max_shift=1.5)
        if not f.ok or f.snr < min_snr or f.chi2r > 25 or 'OVERFLOW' in f.flags:
            continue
        rows.append({'source_id': refs[i]['source_id'], 'g': refs[i]['g'], 'x_pred': float(x[i]), 'y_pred': float(y[i]),
                     'x': f.x, 'y': f.y, 'sx': f.sx, 'sy': f.sy, 'snr': f.snr})
        if len(rows) >= max_stars:
            break
    if len(rows) < 3:
        return Registration(False, 0, 0, math.nan, math.nan, len(rows), math.nan, math.nan, math.nan, 'too_few_reference_stars'), rows
    ddx = np.array([r['x'] - r['x_pred'] for r in rows])
    ddy = np.array([r['y'] - r['y_pred'] for r in rows])
    keep = np.ones(len(rows), bool)
    for _ in range(5):
        mx, my = np.median(ddx[keep]), np.median(ddy[keep])
        rr = np.hypot(ddx - mx, ddy - my)
        scale = 1.4826 * np.median(rr[keep]) + 0.02
        new = rr < 3.5 * scale
        if new.sum() < 3 or (new == keep).all():
            break
        keep = new
    mx, my = float(np.mean(ddx[keep])), float(np.mean(ddy[keep]))
    n = int(keep.sum())
    scat_x = float(np.std(ddx[keep], ddof=1)) if n > 1 else math.nan
    scat_y = float(np.std(ddy[keep], ddof=1)) if n > 1 else math.nan
    scatter = float(np.sqrt(0.5 * (scat_x ** 2 + scat_y ** 2)))
    rms = float(np.sqrt(np.mean((ddx[keep] - mx) ** 2 + (ddy[keep] - my) ** 2))) * 6.15
    formal = float(np.median([math.hypot(r['sx'], r['sy']) / math.sqrt(2) for r, k in zip(rows, keep) if k]))
    sys_floor = math.sqrt(max(scatter ** 2 - formal ** 2, 0.0)) if math.isfinite(scatter) else math.nan
    for r, k in zip(rows, keep):
        r['used'] = bool(k)
    return Registration(True, mx, my, scat_x / math.sqrt(n), scat_y / math.sqrt(n), n, rms, scatter, sys_floor), rows


def pixel_scale_arcsec(obs: Observation) -> float:
    scales = obs.wcs.proj_plane_pixel_scales()
    return float(np.mean([abs(s.to_value('deg')) if hasattr(s, 'to_value') else abs(float(s)) for s in scales])) * 3600


def measure_position(obs: Observation, reg: Registration, x0: float, y0: float, *, strict=False, others=()):
    """Centroid a source near (x0, y0) and return registered sky position + uncertainty (arcsec)."""
    f = fit_source(obs, x0, y0, strict=strict, others=others)
    if not f.ok:
        return f, None
    dx, dy = (reg.dx, reg.dy) if reg.ok else (0.0, 0.0)
    xr, yr = f.x - dx, f.y - dy
    ra, dec = obs.wcs.pixel_to_world_values(xr, yr)
    # Uncertainty: formal centroid error, registration error, and an empirical floor from
    # the reference-star scatter (which captures PSF/undersampling systematics).
    floor = reg.sys_floor_px if reg.ok and math.isfinite(reg.sys_floor_px) else 0.15
    ex = math.sqrt(f.sx ** 2 + (reg.err_x if reg.ok else 0.3) ** 2 + floor ** 2)
    ey = math.sqrt(f.sy ** 2 + (reg.err_y if reg.ok else 0.3) ** 2 + floor ** 2)
    # pixel -> arcsec using the local WCS scale
    scale = pixel_scale_arcsec(obs)
    return f, {'ra': float(ra), 'dec': float(dec), 'sigma_arcsec': float(scale * math.hypot(ex, ey) / math.sqrt(2)),
               'sigma_x_arcsec': float(scale * ex), 'sigma_y_arcsec': float(scale * ey), 'x': xr, 'y': yr,
               'pixel_scale_arcsec': scale}
