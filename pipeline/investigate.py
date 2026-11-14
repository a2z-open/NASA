"""Per-observation measurements of one source across many SPHEREx exposures.

A *track* is a linear-motion + parallax ephemeris
    {'ra': deg, 'dec': deg, 't0_mjd': MJD, 'pmra': mas/yr, 'pmdec': mas/yr, 'parallax': mas}
used to predict where the source should be in each exposure.  For a catalogue
target it comes from the catalogue; for a clicked source it starts stationary
at the click and is refined from SPHEREx's own measurements.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import math
from pathlib import Path

import numpy as np

from .astrometry import propagate, from_tangent
from .measure import fit_source, register, measure_position, pixel_scale_arcsec
from .spherex import load_observation

SNR_POSITION_MIN = 5.0


def track_from_catalog(a) -> dict:
    from .astrometry import target_epoch_mjd
    return {'ra': a.ra_deg, 'dec': a.dec_deg, 't0_mjd': target_epoch_mjd(a), 'pmra': a.pmra_masyr or 0.0,
            'pmdec': a.pmdec_masyr or 0.0, 'parallax': a.parallax_mas or 0.0, 'source': a.source}


def track_from_fit(fit) -> dict:
    """Convert a MotionFit into a track (position at t0, motion and parallax)."""
    p = fit.params
    ra, dec = from_tangent(p['xi0'], p['eta0'], fit.ra_ref, fit.dec_ref)
    plx = p.get('parallax', fit.fixed_parallax_arcsec or 0.0) or 0.0
    return {'ra': float(ra), 'dec': float(dec), 't0_mjd': fit.t0_mjd, 'pmra': p.get('pmra', 0.0) * 1000,
            'pmdec': p.get('pmdec', 0.0) * 1000, 'parallax': plx * 1000, 'source': f'SPHEREx fit ({fit.model})'}


def track_position(track: dict, mjd: float) -> tuple[float, float]:
    p = propagate(track['ra'], track['dec'], track['t0_mjd'], track['pmra'], track['pmdec'], track['parallax'], [mjd])
    return float(p.ra[0]), float(p.dec[0])


def _clean(v):
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def measure_one(args) -> dict:
    path, track, fixed, refs, strict = args
    try:
        obs = load_observation(path, keep_epsf_zones=4)
    except Exception as error:  # noqa: BLE001
        return {'path': str(path), 'status': 'unreadable', 'reason': str(error)[:200]}
    prov = obs.meta.get('provenance', {})
    row = {'product_id': prov.get('product_id', obs.product_id), 'obs_id': obs.obs_id, 'detector': obs.detector,
           'release': obs.release or prov.get('release'), 'mjd': obs.mjd, 'path': str(path),
           'archive_url': prov.get('archive_url'), 'sha256': prov.get('sha256')}
    ra_p, dec_p = track_position(track, obs.mjd)
    x_p, y_p = obs.wcs.world_to_pixel_values(ra_p, dec_p)
    x_p, y_p = float(x_p), float(y_p)
    ny, nx = obs.shape
    row.update({'pred_ra': ra_p, 'pred_dec': dec_p, 'pred_x': x_p, 'pred_y': y_p})
    if not (3 <= x_p <= nx - 4 and 3 <= y_p <= ny - 4):
        row['status'] = 'outside_cutout'
        return row
    lam, bw = obs.wavelength_at(x_p, y_p)
    row.update({'wavelength_um': _clean(lam), 'bandwidth_um': _clean(bw), 'ujy_per_unit': obs.ujy_per_unit,
                'flags': obs.flags_near(x_p, y_p, 1.5)})
    reg, ref_rows = register(obs, refs)
    row['registration'] = reg.to_dict()
    dx, dy = (reg.dx, reg.dy) if reg.ok else (0.0, 0.0)
    # Free centroid (position measurement)
    fit, pos = measure_position(obs, reg, x_p + dx, y_p + dy, strict=strict)
    row['centroid'] = fit.to_dict()
    if pos:
        row['position'] = pos
    # Forced photometry at the predicted (follow) position, registration-corrected
    forced = fit_source(obs, x_p + dx, y_p + dy, fix_position=True, strict=strict)
    k = obs.ujy_per_unit
    row['follow'] = {'ok': forced.ok, 'reason': forced.reason,
                     'flux_ujy': _clean(forced.flux * k) if forced.ok else None,
                     'flux_err_ujy': _clean(forced.flux_err * k) if forced.ok else None,
                     'chi2r': _clean(forced.chi2r) if forced.ok else None}
    if fixed is not None:
        xf, yf = obs.wcs.world_to_pixel_values(fixed[0], fixed[1])
        ff = fit_source(obs, float(xf) + dx, float(yf) + dy, fix_position=True, strict=strict)
        row['fixed'] = {'ok': ff.ok, 'reason': ff.reason, 'offset_px': float(math.hypot(float(xf) - x_p, float(yf) - y_p)),
                        'flux_ujy': _clean(ff.flux * k) if ff.ok else None,
                        'flux_err_ujy': _clean(ff.flux_err * k) if ff.ok else None}
    row['status'] = 'measured'
    return row


def measure_epochs(files, track, refs, *, fixed=None, strict=False, workers=6) -> list[dict]:
    jobs = [(str(f), track, fixed, refs, strict) for f in files]
    if workers <= 1 or len(jobs) < 8:
        return [measure_one(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(measure_one, jobs, chunksize=4))


def usable_positions(rows, *, snr_min=SNR_POSITION_MIN):
    """Rows with a successful free centroid, no saturation in the core, and S/N above threshold."""
    out = []
    for r in rows:
        c = r.get('centroid') or {}
        if r.get('status') != 'measured' or not c.get('ok') or 'position' not in r:
            continue
        if (c.get('snr') or 0) < snr_min:
            continue
        if any(f in (r.get('flags') or []) for f in ('OVERFLOW', 'NONLINEAR')):
            continue
        out.append(r)
    return out


def quality_summary(rows) -> dict:
    total = len(rows)
    by_reason = {}
    for r in rows:
        c = r.get('centroid') or {}
        reason = r.get('status') if r.get('status') != 'measured' else (c.get('reason') if not c.get('ok') else 'ok')
        if reason == 'ok' and (c.get('snr') or 0) < SNR_POSITION_MIN:
            reason = 'low_snr'
        if reason == 'ok' and any(f in (r.get('flags') or []) for f in ('OVERFLOW', 'NONLINEAR')):
            reason = 'saturation_flag_near_core'
        by_reason[reason] = by_reason.get(reason, 0) + 1
    flags = {}
    for r in rows:
        for f in r.get('flags') or []:
            flags[f] = flags.get(f, 0) + 1
    return {'n_observations': total, 'outcomes': by_reason, 'flag_counts_near_source': flags}
