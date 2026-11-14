"""JPL Horizons ephemerides for known solar-system bodies.

PARALLAX uses an ephemeris for two things only:
  1. to decide WHERE to download images of a known body (the body moves by degrees between visits);
  2. afterwards, to SCORE a blind result against the truth.
The detection, linking and orbit-fit code in `pipeline/distant.py` never receives an ephemeris.

Service: https://ssd.jpl.nasa.gov/api/horizons.api (Giorgini et al. 1996).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import requests

from .spherex import CACHE, USER_AGENT

HORIZONS_URL = 'https://ssd.jpl.nasa.gov/api/horizons.api'

# COMMAND strings: a trailing semicolon means "small-body lookup by number".
BODIES = {
    'pluto': {'command': '999', 'title': 'Pluto', 'kind': 'dwarf planet'},
    'makemake': {'command': '136472;', 'title': 'Makemake', 'kind': 'dwarf planet'},
    'haumea': {'command': '136108;', 'title': 'Haumea', 'kind': 'dwarf planet'},
    'eris': {'command': '136199;', 'title': 'Eris', 'kind': 'dwarf planet'},
    'quaoar': {'command': '50000;', 'title': 'Quaoar', 'kind': 'trans-Neptunian object'},
    'orcus': {'command': '90482;', 'title': 'Orcus', 'kind': 'trans-Neptunian object'},
}


def _num(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return float('nan')


def horizons(command: str, start: str, stop: str, step: str = '6 h', *, cache: bool = True) -> dict:
    """Geocentric astrometric ephemeris. Returns arrays: mjd, ra, dec (deg, ICRF), vmag, r_au (heliocentric),
    delta_au (geocentric), elong_deg (Sun-observer-target angle)."""
    key = re.sub(r'[^A-Za-z0-9]+', '_', f'{command}_{start}_{stop}_{step}').strip('_')
    path = CACHE / 'horizons' / f'{key}.json'
    if cache and path.is_file():
        d = json.loads(path.read_text())
        return {k: (np.asarray(v, float) if isinstance(v, list) else v) for k, v in d.items()}
    params = {
        'format': 'text', 'COMMAND': f"'{command}'", 'OBJ_DATA': 'NO', 'MAKE_EPHEM': 'YES', 'EPHEM_TYPE': 'OBSERVER',
        'CENTER': "'500@399'", 'START_TIME': f"'{start}'", 'STOP_TIME': f"'{stop}'", 'STEP_SIZE': f"'{step}'",
        'QUANTITIES': "'1,9,19,20,23'", 'ANG_FORMAT': 'DEG', 'CAL_FORMAT': 'JD', 'CSV_FORMAT': 'YES', 'EXTRA_PREC': 'YES',
    }
    r = requests.get(HORIZONS_URL, params=params, timeout=120, headers={'User-Agent': USER_AGENT})
    r.raise_for_status()
    text = r.text
    if '$$SOE' not in text:
        raise RuntimeError('Horizons returned no ephemeris: ' + text[:300].replace('\n', ' '))
    name = re.search(r'Target body name:\s*(.+?)\s{2,}', text)
    rows = []
    for line in text.split('$$SOE', 1)[1].split('$$EOE', 1)[0].strip().splitlines():
        c = [x.strip() for x in line.split(',')]
        if len(c) < 12:
            continue
        rows.append((_num(c[0]) - 2400000.5, _num(c[3]), _num(c[4]), _num(c[5]), _num(c[7]), _num(c[9]), _num(c[11])))
    a = np.array(rows, float)
    out = {'target': name.group(1) if name else command, 'source': 'JPL Horizons', 'mjd': a[:, 0], 'ra': a[:, 1], 'dec': a[:, 2],
           'vmag': a[:, 3], 'r_au': a[:, 4], 'delta_au': a[:, 5], 'elong_deg': a[:, 6]}
    if cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in out.items()}))
    return out


def at(eph: dict, mjd):
    """Interpolate RA, Dec (deg) and heliocentric / geocentric distance (AU) to the given MJD(s)."""
    mjd = np.atleast_1d(np.asarray(mjd, float))
    ra = np.unwrap(np.radians(eph['ra']))
    return (np.degrees(np.interp(mjd, eph['mjd'], ra)) % 360.0, np.interp(mjd, eph['mjd'], eph['dec']),
            np.interp(mjd, eph['mjd'], eph['r_au']), np.interp(mjd, eph['mjd'], eph['delta_au']))
