"""Controls for the halo-brightness method: bright stars that are not known large-amplitude variables.

For every cached field, every Gaia star brighter than G = 10 (other than the field's target) is run
through exactly the same ring photometry and matched-wavelength comparison as RW Aur and R Dra.
The spread of their visit-to-visit ratios is the method's systematic floor.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import sys

import numpy as np

from pipeline import halo
from pipeline.spherex import CACHE, ROOT
from pipeline.build_curated import GAIA_IDS

OUT = ROOT / 'validation' / 'halo_results.json'
FIELDS = ['r-draconis', 'rw-aurigae', 'barnards-star', 'epsilon-indi-b', 'j0415-0935', 'wise-0855']
TARGETS = ['r-draconis', 'rw-aurigae', 'barnards-star']


def main():
    out = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'method': halo.__doc__.strip().split('\n\n')[0],
           'thresholds': {'sigma': halo.VAR_SIGMA, 'min_amplitude': halo.VAR_MIN_AMPLITUDE}, 'targets': {}, 'controls': []}
    for slug in TARGETS:
        doc, _ = halo.run_target(slug)
        out['targets'][slug] = doc
        print(slug, doc.get('status'), [(v['visit'], round(v['ratio'], 3), v.get('sigma')) for v in doc.get('visits', [])], flush=True)
    # every cached field: the curated ones (10 arcmin) and the hunt fields (20 arcmin)
    fields = []
    for slug in FIELDS:
        man = json.loads((ROOT / 'data' / 'targets' / slug / 'archive_manifest.json').read_text())
        fields.append((slug, sorted((CACHE / 'targets' / slug / 'raw').glob('*.fits')), ROOT / 'data' / 'targets' / slug / 'gaia_field.json',
                       man['field_center']['ra'], man['field_center']['dec'], float(man['field_size_arcmin']), str(GAIA_IDS.get(slug, ''))))
    for gf in sorted((CACHE / 'hunt').glob('*/gaia_field.json')):
        name = gf.parent.name
        man = ROOT / 'data' / 'hunt' / name / 'manifest.json'
        if not man.is_file():
            continue
        m = json.loads(man.read_text())
        fields.append((name, sorted((gf.parent / 'raw').glob('*.fits')), gf, m['ra'], m['dec'], float(m['fov_arcmin']), ''))
    for slug, files, gf, ra0, dec0, fov, own in fields:
        gaia = json.loads(gf.read_text())
        lim = 0.5 * fov / 60 * 0.72       # stay well inside the cutout so the rings and background fit
        inside = [s for s in gaia if s.get('g') is not None and s['g'] < 9.5 and str(s['source_id']) != own
                  and abs(s['dec'] - dec0) < lim and abs((s['ra'] - ra0) * math.cos(math.radians(dec0))) < lim]
        for s in sorted(inside, key=lambda s: s['g'])[:4]:
            doc, _ = halo.run_files(files, gaia, halo.star_track(s), f"Gaia DR3 {s['source_id']}")
            vis = [v for v in doc.get('visits', [])[1:] if v.get('sigma') is not None and v['n'] >= 5]
            row = {'field': slug, 'source_id': s['source_id'], 'g': s['g'], 'status': doc.get('status'), 'ring': doc.get('ring'),
                   'n_used': doc.get('n_used'), 'n_core_saturated': doc.get('n_core_saturated'),
                   'visits': [{'visit': v['visit'], 'ratio': v['ratio'], 'sigma': v['sigma'], 'n': v['n']} for v in vis]}
            out['controls'].append(row)
            print('  control', slug, s['source_id'], 'G=%.1f' % s['g'], doc.get('status'), doc.get('ring'),
                  [(v['visit'], round(v['ratio'], 3), round(v['sigma'], 1)) for v in vis], flush=True)
    rat = [v['ratio'] for c in out['controls'] for v in c['visits']]
    flagged = [c for c in out['controls'] if c['status'] == 'variable']
    out['control_summary'] = {'n_stars': len(out['controls']), 'n_with_comparison': sum(1 for c in out['controls'] if c['visits']),
                              'n_comparisons': len(rat), 'n_flagged_variable': len(flagged),
                              'median_abs_change': float(np.median([abs(r - 1) for r in rat])) if rat else None,
                              'max_abs_change': float(max((abs(r - 1) for r in rat), default=0.0)) if rat else None}
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out['control_summary'], indent=1))


if __name__ == '__main__':
    sys.exit(main())
