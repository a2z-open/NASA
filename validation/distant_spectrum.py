"""Spectrum of a recovered distant body, measured along the orbit the blind search fitted.

    python -m validation.distant_spectrum makemake

For every exposure, the fitted orbit says where the body was; the ePSF is fitted there with the position held
fixed (forced photometry), so wavelengths where the body is too faint to detect still contribute.  The fluxes
are divided by a 5772 K black body as a stand-in for sunlight, giving a relative reflectance.

This step runs after the blind result is locked and uses only that result: no ephemeris.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

from pipeline import distant
from pipeline.astrometry import JULIAN_YEAR_DAYS, earth_barycentric_au
from pipeline.measure import fit_source, gaia_positions, reference_candidates, register
from pipeline.spherex import load_observation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation' / 'distant'
CACHE = ROOT / '.parallax-cache' / 'distant'
BLEND_PX = 2.0          # skip an exposure when a Gaia star sits this close to the body


def run(body: str, log=print) -> dict | None:
    blind = json.loads((OUT / body / 'blind.json').read_text())
    obj = next((o for o in blind['objects'] if o['accepted']), None)
    if obj is None:
        log(f'{body}: no accepted object, no spectrum')
        return None
    p, t0 = np.array(obj['orbit']['params']), obj['orbit']['t0_mjd']
    plan = json.loads((OUT / body / 'plan.json').read_text())
    rows, skipped = [], {'off_image': 0, 'not_registered': 0, 'blended': 0, 'fit_failed': 0}
    for b in plan['bins']:
        folder = CACHE / body / b['id']
        gaia = json.loads((folder / 'gaia_all.json').read_text()) if (folder / 'gaia_all.json').is_file() else []
        refs = reference_candidates([s for s in gaia if s.get('g') is not None and s['g'] < 18.5])
        for f in sorted(folder.glob('*.fits')):
            obs = load_observation(f)
            reg, _ = register(obs, refs)
            if not reg.ok:
                skipped['not_registered'] += 1
                continue
            ra, dec, _ = distant.predict(p, np.array([(obs.mjd - t0) / JULIAN_YEAR_DAYS]), earth_barycentric_au([obs.mjd]))
            x, y = (float(v) for v in obs.wcs.world_to_pixel_values(ra[0], dec[0]))
            x, y = x + reg.dx, y + reg.dy
            ny, nx = obs.shape
            if not (5 <= x < nx - 5 and 5 <= y < ny - 5):
                skipped['off_image'] += 1
                continue
            if gaia:
                gra, gdec = gaia_positions(gaia, obs.mjd)
                gx, gy = obs.wcs.world_to_pixel_values(gra, gdec)
                if np.min(np.hypot(gx + reg.dx - x, gy + reg.dy - y)) < BLEND_PX:
                    skipped['blended'] += 1
                    continue
            fit = fit_source(obs, x, y, fix_position=True)
            lam, _ = obs.wavelength_at(x, y)
            if not fit.ok or not math.isfinite(fit.flux) or not math.isfinite(fit.flux_err) or fit.flux_err <= 0 or not math.isfinite(lam):
                skipped['fit_failed'] += 1
                continue
            rows.append({'mjd': obs.mjd, 'detector': obs.detector, 'wavelength_um': float(lam), 'flux_ujy': float(fit.flux * obs.ujy_per_unit),
                         'flux_err_ujy': float(fit.flux_err * obs.ujy_per_unit), 'product_id': obs.product_id})
    rows.sort(key=lambda r: r['wavelength_um'])
    doc = {'body': body, 'n_exposures_used': len(rows), 'skipped': skipped, 'rows': rows, 'reflectance': distant.reflectance(rows, bins=26),
           'method': 'Forced ePSF photometry at the position given by the blind orbit fit. Reflectance is flux divided by a 5772 K black '
                     'body and scaled to a median of 1. Indicative: the black body is only an approximation to sunlight.'}
    (OUT / body / 'spectrum.json').write_text(json.dumps(doc, indent=1))
    log(f'{body}: {len(rows)} exposures measured, skipped {skipped}')
    for r in doc['reflectance']:
        log(f"   {r['wavelength_um']:.2f} um  reflectance {r['value']:5.2f} ± {r['err']:.2f}  (n={r['n']}, flux {r['flux_ujy']:.0f} uJy)")
    return doc


if __name__ == '__main__':
    for name in sys.argv[1:]:
        run(name)
