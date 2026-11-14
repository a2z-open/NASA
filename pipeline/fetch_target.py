"""Discover and cache real SPHEREx cutouts for a curated target.

Usage:
    python -m pipeline.fetch_target epsilon-indi-b --seal-last-visit
    python -m pipeline.fetch_target rw-aurigae --per-detector-visit 8

`--seal-last-visit` withholds every product of the chronologically last visit
(the held-out set) from download.  Only metadata (times, IDs, URLs) of sealed
products is written, so the prediction can be locked before any held-out pixel
is read.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

from .astrometry import propagate_target, mjd_to_iso
from .spherex import CACHE, ROOT, fetch_many, group_visits, search
from .targets import TARGETS

DATA = ROOT / 'data' / 'targets'


def field_center(target, mjd=61040.0):
    """Target position near the middle of the SPHEREx survey (2026.0)."""
    p = propagate_target(target.astrometry, [mjd])
    return float(p.ra[0]), float(p.dec[0])


def select_subset(visit, per_detector):
    if per_detector is None:
        return list(visit)
    out = []
    for det in range(1, 7):
        items = [p for p in visit if p.detector == det]
        if len(items) <= per_detector:
            out += items
        else:
            idx = np.linspace(0, len(items) - 1, per_detector).round().astype(int)
            out += [items[i] for i in sorted(set(idx))]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('slug')
    ap.add_argument('--seal-last-visit', action='store_true')
    ap.add_argument('--unseal', action='store_true', help='download the sealed visit (only after the prediction is locked)')
    ap.add_argument('--per-detector-visit', type=int, default=None)
    ap.add_argument('--detectors', type=str, default=None, help='comma list, e.g. 5,6 to fetch all of these detectors')
    ap.add_argument('--size', type=float, default=10.0)
    ap.add_argument('--workers', type=int, default=5)
    args = ap.parse_args(argv)
    target = TARGETS[args.slug]
    ra, dec = field_center(target)
    folder = CACHE / 'targets' / args.slug / 'raw'
    out_dir = DATA / args.slug
    out_dir.mkdir(parents=True, exist_ok=True)

    products = search(ra, dec)
    visits = group_visits(products)
    print(f'{target.title}: {len(products)} products in {len(visits)} visits at ({ra:.6f}, {dec:.6f})', flush=True)
    sealed_ids = set()
    if args.seal_last_visit and len(visits) >= 2 and not args.unseal:
        sealed_ids = {p.id for p in visits[-1]}
    wanted = []
    full_dets = {int(x) for x in args.detectors.split(',')} if args.detectors else set()
    for i, v in enumerate(visits):
        if args.unseal:
            if i != len(visits) - 1:
                continue
            chosen = list(v)
        else:
            chosen = select_subset(v, args.per_detector_visit)
            chosen += [p for p in v if p.detector in full_dets and p not in chosen]
        wanted += [p for p in chosen if p.id not in sealed_ids]

    manifest = {
        'target': args.slug,
        'field_center': {'ra': ra, 'dec': dec, 'epoch_note': 'catalogue astrometry propagated to MJD 61040 (2026.0)'},
        'field_size_arcmin': args.size,
        'queried_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'collections': sorted({p.collection for p in products}),
        'visits': [
            {'id': f'visit-{i + 1}', 'n_products': len(v), 'start_utc': mjd_to_iso(v[0].t_min), 'end_utc': mjd_to_iso(v[-1].t_max),
             'mjd_start': v[0].t_min, 'mjd_end': v[-1].t_max,
             'releases': sorted({p.release for p in v}),
             'per_detector': {f'D{d}': sum(1 for p in v if p.detector == d) for d in range(1, 7)},
             'sealed': bool(sealed_ids) and i == len(visits) - 1}
            for i, v in enumerate(visits)
        ],
        'products': [dict(p.to_dict(), visit=f'visit-{i + 1}', sealed=p.id in sealed_ids)
                     for i, v in enumerate(visits) for p in v],
    }
    name = 'archive_manifest.json' if not args.unseal else 'archive_manifest_unsealed.json'
    (out_dir / name).write_text(json.dumps(manifest, indent=1))
    print(f'downloading {len(wanted)} cutouts ({len(sealed_ids)} sealed, not downloaded)', flush=True)

    def progress(n, total):
        if n % 10 == 0 or n == total:
            print(f'  {n}/{total}', flush=True)

    done, failures = fetch_many(wanted, ra, dec, args.size, folder, workers=args.workers, progress=progress)
    print(f'done: {len(done)} ok, {len(failures)} failed', flush=True)
    log = out_dir / ('fetch_log.json' if not args.unseal else 'fetch_log_unsealed.json')
    log.write_text(json.dumps({'ok': len(done), 'failures': failures, 'finished_utc': datetime.now(timezone.utc).isoformat(timespec='seconds')}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
