"""SYNTHETIC injection-recovery tests (clearly not real astronomical sources).

Point sources built from each exposure's own release ePSF are added to real SPHEREx
cutouts of the Epsilon Indi B field at an empty position, moving on a known track.
They are then measured with the production code (registration + ePSF centroids +
motion fit + pre-declared thresholds).  Only source photon noise is not simulated
(the real background and read noise are present).

    python -m validation.inject
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import glob
import json
import math

import numpy as np

from pipeline.analysis import MOTION_PM_SNR, MOTION_SIGMA
from pipeline.astrometry import propagate, to_tangent
from pipeline.investigate import SNR_POSITION_MIN
from pipeline.measure import epsf_values, measure_position, reference_candidates, register
from pipeline.motion import fit_motion, motion_significance
from pipeline.spherex import CACHE, ROOT, load_observation

DATA = ROOT / 'data' / 'targets'
OUT = ROOT / 'validation' / 'validation_results.json'


def empty_position(field, stars):
    """A point ~2.5' from the field centre with no Gaia star within 40 arcsec."""
    for ang in np.linspace(0, 2 * math.pi, 24, endpoint=False):
        ra = field['ra'] + 2.5 / 60 * math.cos(ang) / math.cos(math.radians(field['dec']))
        dec = field['dec'] + 2.5 / 60 * math.sin(ang)
        ok = True
        for s in stars:
            xi, eta = to_tangent(s['ra'], s['dec'], ra, dec)
            if math.hypot(float(xi), float(eta)) < 40:
                ok = False
                break
        if ok:
            return ra, dec
    raise RuntimeError('no empty position')


def one(args):
    path, track, flux_ujy, seed, refs = args
    obs = load_observation(path)
    p = propagate(track['ra'], track['dec'], track['t0'], track['pmra'], track['pmdec'], 0.0, [obs.mjd])
    x, y = obs.wcs.world_to_pixel_values(float(p.ra[0]), float(p.dec[0]))
    x, y = float(x), float(y)
    ny, nx = obs.shape
    if not (6 <= x < nx - 6 and 6 <= y < ny - 6):
        return None
    zone = obs.epsf_at(x, y)
    yy, xx = np.mgrid[int(y) - 5:int(y) + 6, int(x) - 5:int(x) + 6]
    obs.image[yy, xx] += (flux_ujy / obs.ujy_per_unit) * epsf_values(zone, xx - x, yy - y)
    reg, _ = register(obs, refs)
    sx, sy = obs.wcs.world_to_pixel_values(seed[0], seed[1])
    dx, dy = (reg.dx, reg.dy) if reg.ok else (0, 0)
    fit, pos = measure_position(obs, reg, float(sx) + dx, float(sy) + dy)
    if not pos or not fit.ok or fit.snr < SNR_POSITION_MIN or any(f in fit.flags for f in ('OVERFLOW', 'NONLINEAR')):
        return {'mjd': obs.mjd, 'ok': False}
    return {'mjd': obs.mjd, 'ok': True, 'ra': pos['ra'], 'dec': pos['dec'], 'sigma': pos['sigma_arcsec'], 'snr': fit.snr}


def run():
    field = json.loads((DATA / 'epsilon-indi-b' / 'field.json').read_text())
    stars = json.loads((DATA / 'epsilon-indi-b' / 'gaia_field.json').read_text())
    refs = reference_candidates(stars, exclude_ids=['6412596012146801152'])
    files = sorted(glob.glob(str(CACHE / 'targets' / 'epsilon-indi-b' / 'raw' / '*.fits')))[::3]
    ra0, dec0 = empty_position(field, stars)
    t0 = 61040.0
    scenarios = []
    for pm in (0, 300, 1000, 4000):
        for flux in (30, 100, 300, 1000):
            scenarios.append((pm, flux))
    results = []
    with ProcessPoolExecutor(max_workers=8) as ex:
        for pm, flux in scenarios:
            ang = math.radians(135)
            track = {'ra': ra0, 'dec': dec0, 't0': t0, 'pmra': pm * math.sin(ang), 'pmdec': pm * math.cos(ang)}
            rows = [r for r in ex.map(one, [(f, track, flux, (ra0, dec0), refs) for f in files], chunksize=4) if r]
            ok = [r for r in rows if r['ok']]
            res = {'injected_pm_masyr': pm, 'injected_flux_ujy': flux, 'n_frames': len(rows), 'n_detected': len(ok)}
            if len(ok) >= 6:
                mjd = [r['mjd'] for r in ok]
                st = fit_motion(mjd, [r['ra'] for r in ok], [r['dec'] for r in ok], [r['sigma'] for r in ok], model='stationary')
                mv = fit_motion(mjd, [r['ra'] for r in ok], [r['dec'] for r in ok], [r['sigma'] for r in ok], model='linear',
                                ra_ref=st.ra_ref, dec_ref=st.dec_ref)
                s = motion_significance(st, mv)
                sm = mv.summary()
                flagged = s['equivalent_sigma'] >= MOTION_SIGMA and (s['pm_over_error'] or 0) >= MOTION_PM_SNR
                res.update({'recovered_pm_masyr': sm['pm_total_masyr'], 'recovered_pm_err_masyr': sm['pm_total_err_masyr'],
                            'median_snr': float(np.median([r['snr'] for r in ok])), 'flagged_as_moving': bool(flagged),
                            'outcome': ('recovered' if flagged and pm > 0 else 'false_positive' if flagged and pm == 0 else
                                        'correctly_stationary' if pm == 0 else 'missed')})
            else:
                res['outcome'] = 'not_detected'
            print(res, flush=True)
            results.append(res)
    return {'label': 'SYNTHETIC INJECTIONS - not real astronomical sources',
            'description': 'ePSF point sources added to real SPHEREx cutouts (every third exposure of the Epsilon Indi B field, '
                           f'{len(files)} exposures, 4 visits) at an empty position, moving at position angle 135 deg. '
                           'Measured blind (stationary seed) with production code and thresholds. Source photon noise not simulated.',
            'position': {'ra': ra0, 'dec': dec0}, 'results': results}


if __name__ == '__main__':
    inj = run()
    doc = json.loads(OUT.read_text()) if OUT.exists() else {}
    doc['injections'] = inj
    OUT.write_text(json.dumps(doc, indent=1, allow_nan=False, default=lambda o: None))
