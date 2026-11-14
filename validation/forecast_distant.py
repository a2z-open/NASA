"""Forecast where a distant world found blind will be, for SPHEREx images that do not exist yet, and lock it.

    python -m validation.forecast_distant makemake

The orbit is the one the blind search fitted (validation/distant/<body>/blind.json).  The uncertainty comes from
refitting that orbit many times with every detection moved by its own measurement error (a Monte Carlo).  No JPL
ephemeris is used anywhere in this file.  The forecast is written in the same format as validation/forecast.py and
hashed into validation/ledger.jsonl.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from astropy.coordinates import get_body_barycentric
from astropy.time import Time

from pipeline import distant, spherex
from pipeline.astrometry import JULIAN_YEAR_DAYS, earth_barycentric_au
from validation import ledger

ROOT = Path(__file__).resolve().parents[1]
N_MC = 60
ELONG_WINDOW = 12.0        # SPHEREx looks close to 90 degrees from the Sun


def _sun_bary_au(mjd):
    t = Time(np.atleast_1d(mjd), format='mjd', scale='utc')
    p = get_body_barycentric('sun', t)
    return np.vstack([p.x.to_value('au'), p.y.to_value('au'), p.z.to_value('au')]).T


def _positions(p, t0, mjd):
    ra, dec, rho = distant.predict(np.asarray(p), (np.asarray(mjd) - t0) / JULIAN_YEAR_DAYS, earth_barycentric_au(mjd))
    return ra, dec


def elongation(ra, dec, mjd):
    """Angle Sun - Earth - body, degrees."""
    e = earth_barycentric_au(mjd)
    s = _sun_bary_au(mjd) - e
    a, d = np.radians(ra), np.radians(dec)
    u = np.stack([np.cos(d) * np.cos(a), np.cos(d) * np.sin(a), np.sin(d)], axis=-1)
    s = s / np.linalg.norm(s, axis=1)[:, None]
    return np.degrees(np.arccos(np.clip(np.sum(u * s, axis=1), -1, 1)))


def forecast(body: str, log=print) -> dict:
    blind = json.loads((ROOT / 'validation' / 'distant' / body / 'blind.json').read_text())
    ledger.locked(f'distant-blind:{body}', ROOT / 'validation' / 'distant' / body / 'blind.json')
    obj = next(o for o in blind['objects'] if o['accepted'])
    dets = obj['detections']
    base = distant.fit_orbit(dets)
    p0, t0 = np.array(base['params']), base['t0_mjd']
    # dates: the first of each month for a year, plus every day inside SPHEREx's viewing windows
    now = Time(datetime.now(timezone.utc)).mjd
    grid = np.arange(math.ceil(now) + 1, now + 400, 1.0)
    gra, gdec = _positions(p0, t0, grid)
    el = elongation(gra, gdec, grid)
    window = np.abs(el - 90.0) <= ELONG_WINDOW
    windows = []
    for m, w in zip(grid, window):
        if w and (not windows or m - windows[-1][1] > 2):
            windows.append([m, m])
        elif w:
            windows[-1][1] = m
    months = [Time(f'{y}-{mo:02d}-01T00:00:00', scale='utc').mjd for y, mo in
              [(2026 + (11 + k) // 12, (11 + k) % 12 + 1) for k in range(1, 14)]]
    in_window = [float(np.mean(w)) for w in windows]
    dates = sorted(set([round(m, 3) for m in months] + [round(m, 3) for m in in_window]))
    # Monte Carlo: refit with each detection moved by its own error
    rng = np.random.default_rng(20261114)
    sims = []
    for _ in range(N_MC):
        pert = []
        for d in dets:
            s = d['sigma_arcsec']
            dd = dict(d)
            dd['ra'] = d['ra'] + rng.normal(0, s) / 3600 / math.cos(math.radians(d['dec']))
            dd['dec'] = d['dec'] + rng.normal(0, s) / 3600
            pert.append(dd)
        o = distant.fit_orbit(pert, t0_mjd=t0)
        if o and o['bound']:
            sims.append(_positions(o['params'], t0, dates))
    ra, dec = _positions(p0, t0, dates)
    last = max(dets, key=lambda d: d['mjd'])
    preds = []
    for i, m in enumerate(dates):
        cosd = math.cos(math.radians(dec[i]))
        sra = [((s[0][i] - ra[i] + 180) % 360 - 180) * cosd * 3600 for s in sims]
        sde = [(s[1][i] - dec[i]) * 3600 for s in sims]
        stay = math.hypot(((last['ra'] - ra[i] + 180) % 360 - 180) * cosd, last['dec'] - dec[i]) * 3600
        preds.append({'date_utc': Time(m, format='mjd').isot[:19] + 'Z', 'mjd': m, 'ra_deg': float(ra[i]), 'dec_deg': float(dec[i]),
                      'sigma_ra_arcsec': float(np.std(sra)), 'sigma_dec_arcsec': float(np.std(sde)),
                      'offset_from_stays_here_arcsec': float(stay),
                      'elongation_deg': float(elongation([ra[i]], [dec[i]], [m])[0]),
                      'in_spherex_window': bool(any(a - 0.5 <= m <= b + 0.5 for a, b in windows))})
    # what the archive held at lock time, at the first predicted viewing position
    first = next((p for p in preds if p['in_spherex_window']), preds[0])
    try:
        prods = spherex.search(first['ra_deg'], first['dec_deg'], radius_deg=0.01)
        latest = max((p.t_max for p in prods), default=None)
        archive = {'service': 'IRSA SIA2 (spherex_dr1, spherex_qr3)', 'n_products_at_first_window_position': len(prods),
                   'latest_exposure_utc': Time(latest, format='mjd').isot + 'Z' if latest else None,
                   'note': 'No SPHEREx exposure of the first predicted position was taken after this time when the forecast was locked.'}
    except Exception as error:  # noqa: BLE001
        archive = {'service': 'IRSA SIA2', 'error': str(error)[:160]}
    sig = [math.hypot(p['sigma_ra_arcsec'], p['sigma_dec_arcsec']) for p in preds if p['in_spherex_window']]
    doc = {
        'target': body, 'title': body.capitalize(), 'kind': 'forward_prediction_distant_world',
        'locked_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'model': 'heliocentric_orbit', 'model_note': ('The orbit the blind search fitted to its own SPHEREx detections (6 parameters, the Sun\'s '
                                                      'gravity, light-travel time). No JPL ephemeris was used. Uncertainty from refitting it '
                                                      f'{len(sims)} times with every detection moved by its own error.'),
        'data_used': {'n_usable_positions': len(dets), 'first_observation_utc': Time(min(d['mjd'] for d in dets), format='mjd').isot + 'Z',
                      'last_observation_utc': Time(last['mjd'], format='mjd').isot + 'Z'},
        'archive_at_lock': archive,
        'fit': {'r_au': base['r_au'], 'r_err_au': base['r_err_au'], 'chi2_reduced': base['chi2r'], 'n_points': base['n']},
        'criterion': ('PASS if the mean position measured in the next SPHEREx visit lies within 3 sigma of the forecast for that date, where '
                      'sigma combines the forecast spread and the measurement error, with a floor of 2 arcseconds.'),
        'stays_here_null': {'ra_deg': last['ra'], 'dec_deg': last['dec'], 'note': 'the last measured position: where it would be if it did not move'},
        'spherex_windows': [{'start_utc': Time(a, format='mjd').isot[:10], 'end_utc': Time(b, format='mjd').isot[:10]} for a, b in windows],
        'predictions': preds,
        'how_to_check': ('python -m pipeline.watch finds new SPHEREx exposures at the predicted positions. Measure the body there and compare '
                         'with the prediction for that date. The JPL Horizons ephemeris can be used afterwards as an independent check.'),
        'statement': f'Predicted positions of {body.capitalize()} for SPHEREx images that did not exist when this was locked.',
        'typical_uncertainty_arcsec': float(np.median(sig)) if sig else None,
    }
    path = ROOT / 'validation' / 'forecasts' / f'{body}.json'
    path.write_text(json.dumps(doc, indent=1))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix('.sha256').write_text(f'{digest}  {path.name}\n')
    e = ledger.append(f'forecast:{body}', [path], note='Forecast for SPHEREx images that do not exist yet, from the blind orbit only.')
    log(f'{body}: {len(preds)} dates, SPHEREx windows {doc["spherex_windows"]}, typical uncertainty {doc["typical_uncertainty_arcsec"]:.1f}", '
        f'{len(sims)} Monte Carlo fits; locked as ledger entry {e["seq"]}')
    return doc


if __name__ == '__main__':
    for name in sys.argv[1:] or ['makemake']:
        forecast(name)
