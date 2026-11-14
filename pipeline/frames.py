"""Display frames: native cutouts reprojected onto one north-up TAN grid (for viewing only).

Scientific measurements never use these arrays.  Each frame is stored as a raw
little-endian float16 (or float32) array with row 0 = north and column 0 = east,
NaN where the native pixel is hard-flagged or absent.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import math
from pathlib import Path

import numpy as np
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates

from .astrometry import mjd_to_iso
from .spherex import Observation, load_observation

DISPLAY_PIXEL_ARCSEC = 6.15


def display_wcs(ra0: float, dec0: float, fov_arcmin: float, pixel_arcsec: float = DISPLAY_PIXEL_ARCSEC):
    n = max(8, int(round(fov_arcmin * 60 / pixel_arcsec)))
    if n % 2 == 0:
        n += 1
    w = WCS(naxis=2)
    w.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    w.wcs.crval = [ra0, dec0]
    w.wcs.crpix = [(n + 1) / 2, (n + 1) / 2]
    w.wcs.cdelt = [-pixel_arcsec / 3600, pixel_arcsec / 3600]
    return w, n


def grid_doc(ra0, dec0, fov_arcmin, dtype='float16', pixel_arcsec=DISPLAY_PIXEL_ARCSEC):
    _, n = display_wcs(ra0, dec0, fov_arcmin, pixel_arcsec)
    return {'nx': n, 'ny': n, 'pixel_arcsec': pixel_arcsec, 'ra0': ra0, 'dec0': dec0, 'projection': 'TAN',
            'orientation': 'north-up east-left', 'dtype': dtype, 'row0': 'north'}


def reproject(obs: Observation, ra0, dec0, fov_arcmin) -> np.ndarray:
    w, n = display_wcs(ra0, dec0, fov_arcmin)
    yy, xx = np.indices((n, n), dtype=float)
    ra, dec = w.pixel_to_world_values(xx, yy)
    x, y = obs.wcs.world_to_pixel_values(ra, dec)
    img = obs.image.copy()
    img[obs.hard_mask(strict=False)] = np.nan
    out = map_coordinates(img, [y, x], order=1, mode='constant', cval=np.nan)
    return np.flipud(out)   # row 0 = north


def frame_stats(arr: np.ndarray) -> dict:
    v = arr[np.isfinite(arr)]
    if v.size < 10:
        return {'median': None, 'sigma': None, 'p995': None, 'finite_fraction': float(v.size / arr.size)}
    med = float(np.median(v))
    sig = float(1.4826 * np.median(np.abs(v - med)))
    return {'median': med, 'sigma': sig, 'p995': float(np.percentile(v, 99.5)), 'finite_fraction': float(v.size / arr.size)}


def make_frame(args):
    path, ra0, dec0, fov, out_dir, dtype, visit = args
    try:
        obs = load_observation(path, keep_epsf_zones=0)
    except Exception as error:  # noqa: BLE001
        return {'error': str(error)[:200], 'path': path}
    arr = reproject(obs, ra0, dec0, fov)
    stats = frame_stats(arr)
    if stats['finite_fraction'] < 0.5:
        return {'error': 'field mostly outside this exposure', 'path': path}
    prov = obs.meta.get('provenance', {})
    pid = prov.get('product_id', obs.product_id)
    out = Path(out_dir) / f'{pid}.bin'
    out.parent.mkdir(parents=True, exist_ok=True)
    arr.astype('<f2' if dtype == 'float16' else '<f4').tofile(out)
    xc, yc = obs.wcs.world_to_pixel_values(ra0, dec0)
    lam, bw = obs.wavelength_at(float(xc), float(yc))
    finite_w = obs.wave[np.isfinite(obs.wave)]
    return {
        'id': pid, 'obs_id': obs.obs_id, 'detector': obs.detector, 'release': obs.release or prov.get('release'),
        'processing_version': prov.get('processing_version'), 'mjd': obs.mjd, 'time_utc': mjd_to_iso(obs.mjd),
        'visit': visit, 'wavelength_um': lam if math.isfinite(lam) else None, 'bandwidth_um': bw if math.isfinite(bw) else None,
        'wavelength_range_um': [float(finite_w.min()), float(finite_w.max())] if finite_w.size else None,
        'file': out.name, 'stats': stats, 'flags_at_center': obs.flags_near(float(xc), float(yc), 1.5),
        'archive_url': prov.get('archive_url'), 'cutout_url': prov.get('cutout_url'), 'sha256': prov.get('sha256'),
    }


def make_frames(paths, ra0, dec0, fov, out_dir, *, visits=None, dtype='float16', workers=6):
    visits = visits or {}
    jobs = [(str(p), ra0, dec0, fov, str(out_dir), dtype, visits.get(Path(p).stem)) for p in paths]
    if workers <= 1 or len(jobs) < 6:
        results = [make_frame(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(make_frame, jobs, chunksize=4))
    frames = sorted([r for r in results if 'error' not in r], key=lambda r: r['mjd'])
    errors = [r for r in results if 'error' in r]
    return frames, errors
