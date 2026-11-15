"""Which known asteroids did SPHEREx actually catch?  Look where each one should be, and measure.

    python -m validation.asteroids_seen

For every image in the asteroid-hunt patches (versions 2 and 3), every known asteroid from IMCCE SkyBoT that should be
inside the image is looked for at its predicted position: the matched-filter signal-to-noise is read at that pixel
(best within 1.5 pixels, because a SkyBoT position at the epoch mid-time is moved to the image time with its rate).

A detection counts only if (1) S/N >= 5 at the predicted position, and (2) the same patch of sky is EMPTY (S/N < 3) in
an image from another epoch, when the asteroid had moved away.  Condition 2 rejects a star or galaxy that happens to sit
on the asteroid's path.  This is a forced search for known objects: it shows what SPHEREx sees, it discovers nothing.
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation' / 'asteroids'
SETS = [('v2_calibration', ROOT / '.parallax-cache' / 'asteroids60', OUT / 'v2_calibration'),
        ('v3_blind', ROOT / '.parallax-cache' / 'asteroids60v3', OUT)]
V_MAX = 20.0
SNR_DET, SNR_EMPTY = 5.0, 3.0
SEARCH_PX = 1.5


def _untangent(xi, eta, ra0, dec0):
    xi, eta = math.radians(xi / 3600), math.radians(eta / 3600)
    ra0r, dec0r = math.radians(ra0), math.radians(dec0)
    rho = math.hypot(xi, eta)
    c = math.atan(rho)
    if rho == 0:
        return ra0, dec0
    dec = math.asin(math.cos(c) * math.sin(dec0r) + eta * math.sin(c) * math.cos(dec0r) / rho)
    ra = ra0r + math.atan2(xi * math.sin(c), rho * math.cos(dec0r) * math.cos(c) - eta * math.sin(dec0r) * math.sin(c))
    return math.degrees(ra) % 360, math.degrees(dec)


def _one(args):
    """S/N map of one image and the pixel of every requested sky position."""
    path, positions = args
    from pipeline.distant import _snr_map
    from pipeline.measure import reference_candidates, register
    from pipeline.spherex import load_observation
    try:
        obs = load_observation(path)
        gaia = json.loads((Path(path).parent / 'gaia_all.json').read_text())
        reg, _ = register(obs, reference_candidates([g for g in gaia if g.get('g') is not None and g['g'] < 18.5]))
        if not reg.ok:
            return path, None
        snr, _ = _snr_map(obs)
        if snr is None:
            return path, None
        ny, nx = snr.shape
        out = {}
        for key, (ra, dec) in positions.items():
            x, y = obs.wcs.world_to_pixel_values(ra, dec)
            x, y = float(x) + reg.dx, float(y) + reg.dy
            if not (5 <= x < nx - 5 and 5 <= y < ny - 5):
                continue
            xi, yi = int(round(x)), int(round(y))
            r = int(math.ceil(SEARCH_PX))
            win = snr[yi - r:yi + r + 1, xi - r:xi + r + 1]
            yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
            win = np.where(np.hypot(xx + xi - x, yy + yi - y) <= SEARCH_PX, win, np.nan)
            if np.all(np.isnan(win)):
                continue
            out[key] = float(np.nanmax(win))
        return path, {'mjd': obs.mjd, 'detector': obs.detector, 'values': out}
    except Exception:  # noqa: BLE001
        return path, None


def run(log=print) -> dict:
    from validation import ledger
    results, total_images = [], 0
    for tag, cache, folder in SETS:
        plan = json.loads((folder / 'plan.json').read_text())
        known = json.loads((folder / 'known.json').read_text())
        for f in plan['fields']:
            files = sorted((cache / f['id']).glob('*.fits'))
            if not files:
                continue
            from pipeline.spherex import load_observation
            mjds = {}
            for p in files:
                try:
                    mjds[str(p)] = load_observation(p).mjd
                except Exception:  # noqa: BLE001
                    pass
            epochs = known[f['id']]
            bodies = {}
            for e in epochs:
                for b in e['bodies']:
                    try:
                        v = float(b['V'])
                    except (TypeError, ValueError):
                        continue
                    if v <= V_MAX:
                        bodies.setdefault(b['name'], {'V': v, 'class': b['class'], 'delta_au': b.get('delta_au'), 'track': []})['track'].append((e['mjd'], b))
            # every (body, image) pair: where it should be; and the same sky position, for an "empty" check in other images
            jobs = []
            for p, m in mjds.items():
                pos = {}
                for name, info in bodies.items():
                    em, b = min(info['track'], key=lambda t: abs(t[0] - m))
                    if abs(em - m) > 0.5:
                        continue
                    dh = (m - em) * 24
                    x = b['x'] + (b['rate_ra'] or 0) * dh
                    y = b['y'] + (b['rate_dec'] or 0) * dh
                    pos[name] = _untangent(x, y, f['ra'], f['dec'])
                jobs.append((p, pos))
            # the same positions in every other image, for the "empty sky" test
            all_pos = {}
            for p, pos in jobs:
                for name, rd in pos.items():
                    all_pos[f'{name}|{p}'] = rd
            with ProcessPoolExecutor(max_workers=8) as ex:
                measured = dict(ex.map(_one, [(p, pos) for p, pos in jobs], chunksize=1))
                empty = dict(ex.map(_one, [(p, all_pos) for p in mjds], chunksize=1))
            total_images += len(files)
            for name, info in bodies.items():
                hits, tried = [], 0
                for p, m in mjds.items():
                    r = measured.get(p)
                    if not r or name not in r['values']:
                        continue
                    tried += 1
                    s = r['values'][name]
                    if s < SNR_DET:
                        continue
                    # the same sky position in images taken at least 6 hours away (the asteroid is long gone)
                    others = [empty[q]['values'].get(f'{name}|{p}') for q, mq in mjds.items() if abs(mq - m) * 24 > 6 and empty.get(q)]
                    others = [o for o in others if o is not None]
                    if not others or np.median(others) >= SNR_EMPTY:
                        continue
                    hits.append({'mjd': m, 'snr': round(s, 1), 'empty_elsewhere_snr': round(float(np.median(others)), 1), 'n_other_images': len(others)})
                if tried:
                    results.append({'set': tag, 'field': f['id'], 'name': name, 'V': info['V'], 'class': info['class'], 'delta_au': info['delta_au'],
                                    'images_in_view': tried, 'detections': len(hits), 'max_snr': max((h['snr'] for h in hits), default=None), 'hits': hits})
            n_seen = sum(1 for r in results if r['field'] == f['id'] and r['set'] == tag and r['detections'] >= 2)
            log(f"{tag} {f['id']}: {len(files)} images, {len(bodies)} known asteroids to V {V_MAX:g}, {n_seen} seen in 2+ images")
    seen = [r for r in results if r['detections'] >= 2]
    bins = [(0, 16), (16, 17), (17, 18), (18, 19), (19, 20.01)]
    table = [{'V': f'{a}-{b:g}' if b < 20 else f'{a}-20', 'in_view': sum(1 for r in results if a <= r['V'] < b),
              'seen': sum(1 for r in seen if a <= r['V'] < b)} for a, b in bins]
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'n_images': total_images, 'n_in_view': len(results),
           'n_seen': len(seen), 'by_V': table, 'rule': {'snr_detect': SNR_DET, 'snr_empty_elsewhere': SNR_EMPTY, 'search_px': SEARCH_PX, 'min_images': 2, 'V_max': V_MAX},
           'seen': sorted(seen, key=lambda r: (r['V'], r['name'])),
           'what_it_is': ('A forced search for KNOWN asteroids: each was looked for where the IMCCE SkyBoT service says it was. A detection needs S/N 5 or more at '
                          'that spot in at least two images, with the same spot empty in images from other epochs. It shows which asteroids SPHEREx caught and '
                          'measured. It discovers nothing.')}
    (OUT / 'seen.json').write_text(json.dumps(doc, indent=1))
    e = ledger.append('asteroids:seen', [OUT / 'seen.json', Path(__file__)], note='Known asteroids measured at their predicted positions in the hunt images.')
    log(f"{len(seen)} known asteroids seen in 2+ images, of {len(results)} in view, in {total_images} images; by V: " +
        ', '.join(f"{t['V']}: {t['seen']}/{t['in_view']}" for t in table) + f"; ledger entry {e['seq']}")
    return doc


if __name__ == '__main__':
    run()
