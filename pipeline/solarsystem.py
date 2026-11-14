"""Is there a known asteroid or comet at this position at the times it was observed?

Uses the IMCCE SkyBoT cone search (Berthier et al. 2006), which returns every known solar-system
body inside a cone at a given instant.  The observer is taken at the geocentre: SPHEREx is in
low Earth orbit, so the parallax error for a main-belt asteroid is below ten arcseconds, well
inside the search radius.
"""

from __future__ import annotations

import math

import numpy as np
import requests

from .astrometry import mjd_to_iso

SKYBOT = 'https://ssp.imcce.fr/webservices/skybot/api/conesearch.php'
RADIUS_ARCSEC = 60.0
MAX_EPOCHS = 8


def known_bodies(ra, dec, mjd, radius_arcsec=RADIUS_ARCSEC, timeout=30, session=None):
    """Known solar-system bodies within radius_arcsec of (ra, dec) at this MJD.  [] if none."""
    http = session or requests
    params = {'-ep': mjd_to_iso(mjd).rstrip('Z'), '-ra': f'{ra:.6f}', '-dec': f'{dec:.6f}', '-rd': f'{radius_arcsec / 3600:.5f}',
              '-mime': 'json', '-output': 'basic', '-loc': '500', '-from': 'spherex-viewer'}
    r = http.get(SKYBOT, params=params, timeout=timeout)
    if r.status_code == 204 or not r.text.strip():
        return []
    r.raise_for_status()
    out = []
    for x in r.json():
        out.append({'name': x.get('Name'), 'number': x.get('Num'), 'class': x.get('Class'), 'vmag': x.get('VMag (mag)'),
                    'sep_arcsec': x.get('d (arcsec)'),
                    'rate_arcsec_per_hour': float(math.hypot(x.get('dRA (arcsec/h)') or 0.0, x.get('dDEC (arcsec/h)') or 0.0))})
    return out


def check(ra, dec, mjds, radius_arcsec=RADIUS_ARCSEC, max_epochs=MAX_EPOCHS):
    """Sample up to max_epochs observation times evenly and query each one."""
    mjds = sorted(float(m) for m in mjds if m is not None and math.isfinite(m))
    doc = {'service': 'IMCCE SkyBoT cone search', 'observer': 'geocentre', 'radius_arcsec': radius_arcsec,
           'n_observations': len(mjds), 'n_epochs_checked': 0, 'epochs': [], 'matches': [], 'status': 'not_checked'}
    if not mjds:
        return doc
    idx = sorted(set(np.linspace(0, len(mjds) - 1, min(max_epochs, len(mjds))).round().astype(int)))
    s = requests.Session()
    for i in idx:
        try:
            found = known_bodies(ra, dec, mjds[i], radius_arcsec, session=s)
        except (requests.RequestException, ValueError) as error:
            doc['error'] = str(error)[:160]
            continue
        doc['n_epochs_checked'] += 1
        doc['epochs'].append(mjd_to_iso(mjds[i]))
        for f in found:
            doc['matches'].append(dict(f, time_utc=mjd_to_iso(mjds[i])))
    if doc['n_epochs_checked'] == 0:
        doc['status'] = 'unavailable'
    else:
        doc['status'] = 'found' if doc['matches'] else 'none_found'
    return doc
