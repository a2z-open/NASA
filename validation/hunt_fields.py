"""The Planet X hunt: which fields were searched, how they were fetched, and the summary.

Three kinds of field:
  validation  the curated targets already cached (the search is never told where the target is)
  recovery    sky around a known nearby cold brown dwarf or planetary-mass object.  The field centre is
              offset by a pseudo-random amount, and the object's catalogue position is used ONLY after
              the search, to score whether the blind search found it.
  control     well-studied "blank" extragalactic fields.  Any mover here must be a known star,
              otherwise it is a false positive.

Usage:
    python -m validation.hunt_fields resolve          # names -> coordinates (Sesame/SIMBAD), cached
    python -m validation.hunt_fields fetch            # download cutouts for recovery + control fields
    python -m validation.hunt_fields run cached|new|all [names...]
    python -m validation.hunt_fields index            # write data/hunt/index.json
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
import requests

from pipeline import hunt
from pipeline.astrometry import mjd_to_iso
from pipeline.spherex import fetch_many, group_visits, search

HERE = Path(__file__).resolve().parent
RESOLVED = HERE / 'hunt_fields.json'
SESAME = 'https://vizier.cfa.harvard.edu/viz-bin/nph-sesame/-oI/SNV?'
FOV_ARCMIN = 20.0
PER_VISIT = ((2, 4), (5, 10), (6, 16))      # (detector, max exposures per visit)

CACHED = ['epsilon-indi-b', 'j0415-0935', 'wise-0855', 'barnards-star', 'rw-aurigae', 'r-draconis']

# (field name, SIMBAD identifier, short description)
RECOVERY = [
    ('simp-0136', 'SIMP J013656.5+093347.3', 'free-floating planetary-mass object, T2.5'),
    ('2mass-0939', '2MASS J09393548-2448279', 'T8 brown dwarf'),
    ('ugps-0722', 'UGPS J072227.51-054031.2', 'T9 brown dwarf'),
    ('wise-1741', 'WISEP J174124.26+255319.5', 'T9 brown dwarf'),
    ('wise-1506', 'WISEP J150649.97+702736.0', 'T6 brown dwarf'),
    ('wise-0254', 'WISEP J025409.45+022359.1', 'T8 brown dwarf'),
    ('denis-0255', 'DENIS J025503.3-470049', 'L9 brown dwarf'),
    ('2mass-0348', '2MASS J03480772-6022270', 'T7 brown dwarf'),
    ('luhman-16', 'WISE J104915.57-531906.1', 'L7.5 + T0.5 binary, third-nearest system'),
    ('2mass-0727', '2MASSI J0727182+171001', 'T7 brown dwarf'),
    ('2mass-1217', '2MASS J12171110-0311131', 'T7.5 brown dwarf'),
    ('2mass-0559', '2MASS J05591914-1404488', 'T4.5 brown dwarf'),
    ('wise-1639', 'WISE J163940.83-684738.6', 'Y0 brown dwarf'),
    ('wise-1405', 'WISEP J140518.40+553421.4', 'Y0.5 brown dwarf'),
    ('wise-0410', 'WISEP J041022.71+150248.5', 'Y0 brown dwarf'),
    ('wise-2056', 'WISEP J205628.90+145953.3', 'Y0 brown dwarf'),
]
CONTROL = [
    ('control-cosmos', 150.119, 2.206, 'COSMOS field'),
    ('control-cdfs', 53.125, -27.806, 'Chandra Deep Field South'),
    ('control-goodsn', 189.229, 62.238, 'GOODS-North'),
    ('control-uds', 34.400, -5.200, 'UKIDSS Ultra Deep Survey field'),
]


def sesame(name):
    r = requests.get(SESAME + requests.utils.quote(name), timeout=40)
    r.raise_for_status()
    out = {'query': name}
    for line in r.text.splitlines():
        p = line.split()
        if line.startswith('%J ') and len(p) >= 3:
            out['ra'], out['dec'] = float(p[1]), float(p[2])
        elif line.startswith('%P ') and len(p) >= 3:
            out['pmra'], out['pmdec'] = float(p[1]), float(p[2])
        elif line.startswith('%X ') and len(p) >= 2:
            out['parallax'] = float(p[1])
        elif line.startswith('%S ') and len(p) >= 2:
            out['spectral_type'] = p[1]
        if line.startswith('%J ') and ' C ' in line:
            out['position_ref'] = line.split(' C ')[-1].strip()
    return out if 'ra' in out else None


def _offset(name):
    """Deterministic pseudo-random field offset (up to ~4 arcmin) so the object is not at the centre."""
    h = hashlib.sha256(name.encode()).digest()
    return (h[0] / 255 - 0.5) * 8.0, (h[1] / 255 - 0.5) * 8.0     # arcmin east, north


def resolve():
    done = json.loads(RESOLVED.read_text()) if RESOLVED.is_file() else {}
    for name, ident, desc in RECOVERY:
        if name in done:
            continue
        try:
            s = sesame(ident)
        except requests.RequestException as error:
            print(f'{name}: resolver error {error}')
            continue
        if not s or 'pmra' not in s:
            print(f'{name}: not resolved ({ident})')
            continue
        de, dn = _offset(name)
        s.update({'name': name, 'identifier': ident, 'description': desc, 'kind': 'recovery',
                  'field_ra': s['ra'] + de / 60 / math.cos(math.radians(s['dec'])), 'field_dec': s['dec'] + dn / 60,
                  'offset_arcmin': [round(de, 2), round(dn, 2)],
                  'resolved_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  'resolver': 'CDS Sesame / SIMBAD via the CfA mirror'})
        done[name] = s
        print(f"{name}: {s['ra']:.5f} {s['dec']:.5f} pm=({s['pmra']:.0f},{s['pmdec']:.0f}) mas/yr {s.get('spectral_type')}")
        time.sleep(0.3)
    for name, ra, dec, desc in CONTROL:
        done.setdefault(name, {'name': name, 'kind': 'control', 'description': desc, 'field_ra': ra, 'field_dec': dec})
    RESOLVED.write_text(json.dumps(done, indent=1))
    return done


def fetch(names=None, workers=8):
    fields = json.loads(RESOLVED.read_text())
    for name in (names or list(fields)):
        f = fields[name]
        out = hunt.HUNT_DATA / name
        if (out / 'manifest.json').is_file():
            continue
        folder = hunt.HUNT_CACHE / name / 'raw'
        try:
            products = search(f['field_ra'], f['field_dec'])
        except Exception as error:  # noqa: BLE001
            print(f'{name}: archive search failed: {error}', flush=True)
            continue
        visits = group_visits(products)
        wanted = []
        for v in visits:
            for det, cap in PER_VISIT:
                items = [p for p in v if p.detector == det]
                if len(items) > cap:
                    idx = sorted(set(np.linspace(0, len(items) - 1, cap).round().astype(int)))
                    items = [items[i] for i in idx]
                wanted += items
        t0 = time.time()
        have = len(list(folder.glob('*.fits'))) if folder.is_dir() else 0
        if have >= 60:        # an earlier, larger selection was already downloaded for this field: use it as is
            wanted = [p for v in visits for p in v if (folder / f'{p.id}.fits').is_file()]
        done, failures = fetch_many(wanted, f['field_ra'], f['field_dec'], FOV_ARCMIN, folder, workers=workers)
        out.mkdir(parents=True, exist_ok=True)
        (out / 'manifest.json').write_text(json.dumps({
            'field': name, 'ra': f['field_ra'], 'dec': f['field_dec'], 'fov_arcmin': FOV_ARCMIN,
            'queried_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'n_products_available': len(products), 'n_requested': len(wanted), 'n_downloaded': len(done),
            'failures': failures, 'selection': 'per visit: up to 4 x D2, 10 x D5, 16 x D6, evenly spaced in time (simp-0136: an earlier, larger selection)',
            'visits': [{'id': f'visit-{i + 1}', 'start_utc': mjd_to_iso(v[0].t_min), 'end_utc': mjd_to_iso(v[-1].t_max),
                        'n_products': len(v)} for i, v in enumerate(visits)]}, indent=1))
        print(f'{name}: {len(done)}/{len(wanted)} cutouts in {len(visits)} visits ({time.time() - t0:.0f}s, {len(failures)} failed)', flush=True)


def run(which, names=None, workers=8):
    if which in ('cached', 'all'):
        for slug in CACHED:
            if names and slug not in names:
                continue
            f = hunt.curated_field(slug)
            try:
                hunt.run_field(f['name'], f['files'], f['ra'], f['dec'], f['fov'], title=f['title'], workers=workers,
                               truth=f['truth'], gaia=f['gaia'], kind='validation')
            except Exception as error:  # noqa: BLE001
                print(f'{slug}: FAILED {error!r}', flush=True)
    if which in ('new', 'all'):
        fields = json.loads(RESOLVED.read_text())
        for name, f in fields.items():
            if names and name not in names:
                continue
            files = sorted((hunt.HUNT_CACHE / name / 'raw').glob('*.fits'))
            if len(files) < 12:
                print(f'{name}: only {len(files)} cutouts, skipped', flush=True)
                continue
            truth = None
            if f['kind'] == 'recovery':
                truth = {'name': f['identifier'], 'ra': f['ra'], 'dec': f['dec'], 'epoch_mjd': 51544.5, 'pmra': f['pmra'],
                         'pmdec': f['pmdec'], 'parallax': f.get('parallax', 0.0), 'spectral_type': f.get('spectral_type'),
                         'source': 'SIMBAD via Sesame (' + f.get('position_ref', 'ref. not given') + ')'}
            try:
                hunt.run_field(name, files, f['field_ra'], f['field_dec'], FOV_ARCMIN, title=f.get('identifier') or f['description'],
                               workers=workers, truth=truth, kind=f['kind'], notes=f['description'])
            except Exception as error:  # noqa: BLE001
                print(f'{name}: FAILED {error!r}', flush=True)


def index():
    rows, totals = [], {'fields': 0, 'area_deg2': 0.0, 'exposures': 0, 'sources': 0, 'motion_tested': 0}
    classes = {}
    for path in sorted(hunt.HUNT_DATA.glob('*/hunt.json')):
        d = json.loads(path.read_text())
        movers = [s for s in d['sources'] if s['class'] in ('candidate', 'stack_candidate', 'two_visit_candidate', 'known_mover', 'suspect')]
        rows.append({'field_id': d['field_id'], 'title': d['title'], 'kind': d['kind'], 'notes': d.get('notes'), 'ra': d['ra'], 'dec': d['dec'],
                     'fov_arcmin': d['fov_arcmin'], 'area_deg2': d['area_deg2'], 'n_visits': len(d['visits']),
                     'baseline_days': d['baseline_days'], 'n_exposures': d['n_exposures'], 'n_sources': d['n_sources'],
                     'n_motion_tested': d['n_motion_tested'], 'counts': d['counts'], 'depth_5sigma_ujy': d['depth_5sigma_ujy'],
                     'truth': d.get('truth'), 'generated_utc': d['generated_utc'],
                     'movers': [{k: s.get(k) for k in ('id', 'class', 'ra', 'dec', 'pm_arcsec_yr', 'sigma', 'pm_over_error', 'stack_snr',
                                                       'best_band', 'cold_only', 'flags', 'truth_match', 'gaia', 'stack_motion',
                                                       'n_native_positions', 'parallax_mas', 'parallax_err_mas')} for s in movers]})
        totals['fields'] += 1
        totals['area_deg2'] += d['area_deg2']
        totals['exposures'] += d['n_exposures']
        totals['sources'] += d['n_sources']
        totals['motion_tested'] += d['n_motion_tested']
        for k, v in d['counts'].items():
            classes[k] = classes.get(k, 0) + v
    truths = [r['truth'] | {'field_id': r['field_id']} for r in rows if r.get('truth')]
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'totals': totals | {'area_deg2': round(totals['area_deg2'], 3)},
           'classes': classes,
           'recovery': {'n_known': len(truths), 'n_detected': sum(1 for t in truths if t['detected']),
                        'n_recovered': sum(1 for t in truths if t['recovered'])},
           'unexplained': [m | {'field_id': r['field_id']} for r in rows for m in r['movers']
                           if m['class'] in ('candidate', 'stack_candidate', 'two_visit_candidate') and not m.get('truth_match')],
           'thresholds': json.loads(next(iter(sorted(hunt.HUNT_DATA.glob('*/hunt.json')))).read_text())['thresholds'] if rows else {},
           'fields': rows}
    (hunt.HUNT_DATA / 'index.json').write_text(json.dumps(doc, indent=1))
    print(json.dumps({k: doc[k] for k in ('totals', 'classes', 'recovery')}, indent=1))
    print('unexplained:', len(doc['unexplained']))
    return doc


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'index'
    if cmd == 'resolve':
        resolve()
    elif cmd == 'fetch':
        fetch(sys.argv[2:] or None)
    elif cmd == 'run':
        run(sys.argv[2], sys.argv[3:] or None)
    else:
        index()
