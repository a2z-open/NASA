"""Where to look for known distant bodies, and the downloads.

A distant body moves by degrees between SPHEREx visits, so no fixed patch of sky contains it twice.
This script uses the JPL Horizons ephemeris ONLY to choose the patches to download: for each two-day
bin in which SPHEREx imaged the body's neighbourhood, one cutout field centred where the body was at
the middle of that bin.  The detection and linking code (pipeline/distant.py) is then given the image
files and nothing else.

    python -m validation.distant_fields plan makemake
    python -m validation.distant_fields fetch makemake
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from pipeline import ephem, spherex

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation' / 'distant'
CACHE = spherex.CACHE / 'distant'
START, STOP = '2025-04-20', '2026-11-05'
ELONG_HALF_WINDOW = 18.0      # SPHEREx looks near 90 deg from the Sun; search this far either side
BIN_DAYS = 2.0
SIZE_ARCMIN = 16.0
DETECTORS = (1, 2, 3)         # 0.75-2.4 um: reflected sunlight
MAX_PER_BIN = 40


def plan(body: str, log=print) -> dict:
    spec = ephem.BODIES[body]
    eph = ephem.horizons(spec['command'], START, STOP, '6 h')
    near = np.abs(eph['elong_deg'] - 90.0) <= ELONG_HALF_WINDOW
    t0, t1 = eph['mjd'][0], eph['mjd'][-1]
    centres = [t for t in np.arange(t0 + BIN_DAYS / 2, t1, BIN_DAYS) if np.interp(t, eph['mjd'], near.astype(float)) > 0.5]
    log(f'{body}: {len(centres)} two-day bins near quadrature to query')

    def one(t):
        ra, dec, _, _ = ephem.at(eph, t)
        try:
            prods = spherex.search(float(ra[0]), float(dec[0]))
        except Exception as error:  # noqa: BLE001
            return t, float(ra[0]), float(dec[0]), None, str(error)[:200]
        keep = [p for p in prods if abs(p.t_mid - t) <= BIN_DAYS / 2 and p.detector in DETECTORS]
        return t, float(ra[0]), float(dec[0]), keep, None

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(one, centres))
    bins, failed = [], 0
    for t, ra, dec, keep, error in results:
        if keep is None:
            failed += 1
            continue
        if not keep:
            continue
        keep = sorted(keep, key=lambda p: p.t_min)[:MAX_PER_BIN]
        bins.append({'id': f'b{int(round(t * 10)):06d}', 't_mjd': round(float(t), 3), 'ra': round(ra, 6), 'dec': round(dec, 6),
                     'products': [p.to_dict() for p in keep]})
    doc = {'body': body, 'title': spec['title'], 'kind': spec['kind'], 'size_arcmin': SIZE_ARCMIN, 'detectors': list(DETECTORS),
           'bin_days': BIN_DAYS, 'queries_failed': failed, 'bins': bins,
           'note': 'Field centres come from JPL Horizons. Nothing else from the ephemeris is passed to the search.'}
    (OUT / body).mkdir(parents=True, exist_ok=True)
    (OUT / body / 'plan.json').write_text(json.dumps(doc, indent=1))
    log(f'{body}: {len(bins)} bins with images, {sum(len(b["products"]) for b in bins)} exposures, {failed} queries failed')
    return doc


def fetch(body: str, log=print) -> None:
    doc = json.loads((OUT / body / 'plan.json').read_text())
    n_ok = n_bad = 0
    for b in doc['bins']:
        prods = [spherex.Product(**{k: v for k, v in p.items() if k not in ('id', 'processing_version')}) for p in b['products']]
        done, failures = spherex.fetch_many(prods, b['ra'], b['dec'], doc['size_arcmin'], CACHE / body / b['id'], workers=6)
        n_ok += len(done)
        n_bad += len(failures)
    log(f'{body}: {n_ok} cutouts on disk, {n_bad} failed')


if __name__ == '__main__':
    cmd, names = sys.argv[1], sys.argv[2:]
    for name in names:
        (plan if cmd == 'plan' else fetch)(name)
