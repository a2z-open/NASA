"""Stacking along known asteroid paths: does adding images together show asteroids too faint for one image?

    python -m validation.asteroids_stack

For every known asteroid (IMCCE SkyBoT, V up to 21.5) in the asteroid-hunt patches, the matched-filter S/N is read at its
EXACT predicted position in every image where it should be: no search and no peak picking, so there is no bias.  From each
value the median S/N of the same sky spot in images taken more than 6 hours away is subtracted (by then the asteroid has
moved on), which removes stars and galaxies that sit under its path.  The values along the path are added: the stacked
S/N is their sum divided by the square root of their number.

The same is done along four CONTROL paths: the asteroid's own path moved 60" east, west, north or south, where there is no
asteroid but the same kind of sky.  The threshold is the stacked S/N reached by only 1 in 100 control paths.  An asteroid
counts as seen in the stack if it reaches that threshold.  The comparison is the single-image search of the same asteroids
in the same images (validation/asteroids/seen.json).  This measures what stacking adds; it discovers nothing.
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from validation.asteroids_seen import SETS, _untangent

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation' / 'asteroids'
V_MAX = 21.5
AWAY_H = 6.0
CONTROL_SHIFTS = [(60.0, 0.0), (-60.0, 0.0), (0.0, 60.0), (0.0, -60.0)]   # arcsec east, north
FALSE_RATE = 0.01
MIN_IMAGES = 3


def _forced(args):
    """The S/N map of one image, read (bilinear, no search) at every requested sky position."""
    path, keys, radec = args
    from scipy.ndimage import map_coordinates
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
        x, y = obs.wcs.world_to_pixel_values(radec[:, 0], radec[:, 1])
        x, y = np.asarray(x) + reg.dx, np.asarray(y) + reg.dy
        inside = (x >= 3) & (x < nx - 3) & (y >= 3) & (y < ny - 3)
        vals = map_coordinates(np.nan_to_num(snr, nan=np.nan), [y, x], order=1, mode='constant', cval=np.nan)
        vals = np.where(inside, vals, np.nan)
        return path, {'mjd': obs.mjd, 'values': vals.astype(np.float32)}
    except Exception:  # noqa: BLE001
        return path, None


def _field(tag, cache, folder, f, known):
    from pipeline.spherex import load_observation
    files = sorted((cache / f['id']).glob('*.fits'))
    mjds = {}
    for p in files:
        try:
            mjds[str(p)] = load_observation(p).mjd
        except Exception:  # noqa: BLE001
            pass
    bodies = {}
    for e in known[f['id']]:
        for b in e['bodies']:
            try:
                v = float(b['V'])
            except (TypeError, ValueError):
                continue
            if v <= V_MAX:
                bodies.setdefault(b['name'], {'V': v, 'class': b['class'], 'track': []})['track'].append((e['mjd'], b))
    # every (body, image, path) position: the asteroid itself (path 0) and four control paths
    keys, radec = [], []
    for name, info in bodies.items():
        for p, m in mjds.items():
            em, b = min(info['track'], key=lambda t: abs(t[0] - m))
            if abs(em - m) > 0.5:
                continue
            dh = (m - em) * 24
            x = b['x'] + (b['rate_ra'] or 0) * dh
            y = b['y'] + (b['rate_dec'] or 0) * dh
            for k, (dx, dy) in enumerate([(0.0, 0.0)] + CONTROL_SHIFTS):
                keys.append((name, p, k))
                radec.append(_untangent(x + dx, y + dy, f['ra'], f['dec']))
    if not keys:
        return []
    radec = np.array(radec)
    with ProcessPoolExecutor(max_workers=8) as ex:
        got = dict(ex.map(_forced, [(p, None, radec) for p in mjds], chunksize=1))
    paths = [p for p in mjds if got.get(p)]
    V = np.stack([got[p]['values'] for p in paths])          # (images, positions): every position read in every image
    t = np.array([got[p]['mjd'] for p in paths])
    col = {p: i for i, p in enumerate(paths)}
    rows = {}
    for j, (name, p, k) in enumerate(keys):
        if p not in col:
            continue
        i = col[p]
        here = V[i, j]
        away = V[np.abs(t - t[i]) * 24 > AWAY_H, j]
        away = away[np.isfinite(away)]
        if not np.isfinite(here) or away.size < 3:
            continue
        rows.setdefault((name, k), []).append(float(here - np.median(away)))
    out = []
    for name, info in bodies.items():
        r = rows.get((name, 0), [])
        if len(r) < MIN_IMAGES:
            continue
        ctrl = [rows.get((name, k), []) for k in range(1, 5)]
        out.append({'set': tag, 'field': f['id'], 'name': name, 'V': info['V'], 'class': info['class'], 'n_images': len(r),
                    'stack_snr': round(float(np.sum(r) / math.sqrt(len(r))), 2), 'best_single_snr': round(float(max(r)), 2),
                    'controls': [round(float(np.sum(c) / math.sqrt(len(c))), 2) for c in ctrl if len(c) >= MIN_IMAGES]})
    return out


STAMP_PX = 7          # picture half-width in native pixels (6.15")


def _stamps(tag, cache, f, known, name):
    """Real pictures for one asteroid: the S/N map around its predicted position in every image (fixed sky removed the same way),
    and the running stack after 1, 2, 4, 8, 16 and all images.  Also the same for one control path 60" east."""
    from pipeline.spherex import load_observation
    files = sorted((cache / f['id']).glob('*.fits'))
    mjds = {str(p): load_observation(p).mjd for p in files}
    track = []
    for e in known[f['id']]:
        for b in e['bodies']:
            if b['name'] == name:
                track.append((e['mjd'], b))
    k = np.arange(-STAMP_PX, STAMP_PX + 1) * 6.15
    gx, gy = np.meshgrid(k, k)
    order, radec = [], []
    for p, m in sorted(mjds.items(), key=lambda t: t[1]):
        em, b = min(track, key=lambda t: abs(t[0] - m))
        if abs(em - m) > 0.5:
            continue
        dh = (m - em) * 24
        x = b['x'] + (b['rate_ra'] or 0) * dh
        y = b['y'] + (b['rate_dec'] or 0) * dh
        for dx in (0.0, 60.0):
            order.append((p, dx))
            radec += [_untangent(x + dx + a, y + c, f['ra'], f['dec']) for a, c in zip(gx.ravel(), gy.ravel())]
    radec = np.array(radec)
    with ProcessPoolExecutor(max_workers=8) as ex:
        got = dict(ex.map(_forced, [(p, None, radec) for p in mjds], chunksize=1))
    paths = [p for p in mjds if got.get(p)]
    t = np.array([got[p]['mjd'] for p in paths])
    col = {p: i for i, p in enumerate(paths)}
    npx = gx.size
    out = {}
    for dx in (0.0, 60.0):
        pics = []
        for j, (p, d) in enumerate(order):
            if d != dx or p not in col:
                continue
            i = col[p]
            sl = slice(j * npx, (j + 1) * npx)
            here = got[p]['values'][sl]
            away = np.stack([got[q]['values'][sl] for q in paths if abs(got[q]['mjd'] - t[i]) * 24 > AWAY_H])
            pic = (here - np.nanmedian(away, axis=0)).reshape(gx.shape) if away.shape[0] >= 3 else None
            c = STAMP_PX
            if pic is None or not np.isfinite(pic[c - 1:c + 2, c - 1:c + 2]).all():
                continue                                   # the centre must be measured; masked edge pixels are shown as empty sky
            pics.append(np.nan_to_num(pic, nan=0.0))
        if not pics:
            return None
        pics = np.array(pics)
        steps = sorted({n for n in (1, 2, 4, 8, 16, len(pics)) if n <= len(pics)})
        out['path' if dx == 0 else 'control'] = {
            'single': [np.round(pk, 1).tolist() for pk in pics[:3]],
            'running': [{'n': n, 'snr': np.round(pics[:n].sum(axis=0) / math.sqrt(n), 1).tolist()} for n in steps]}
    return out


def run(log=print) -> dict:
    from validation import ledger
    rows = []
    for tag, cache, folder in SETS:
        plan = json.loads((folder / 'plan.json').read_text())
        known = json.loads((folder / 'known.json').read_text())
        for f in plan['fields']:
            got = _field(tag, cache, folder, f, known)
            rows += got
            log(f"{tag} {f['id']}: {len(got)} known asteroids with {MIN_IMAGES}+ images")
    ctrl = np.array([c for r in rows for c in r['controls']])
    thresh = float(np.quantile(ctrl, 1 - FALSE_RATE))
    single_seen = {(s['set'], s['field'], s['name']) for s in json.loads((OUT / 'seen.json').read_text())['seen']}
    for r in rows:
        r['seen_single'] = (r['set'], r['field'], r['name']) in single_seen
        r['seen_stack'] = r['stack_snr'] >= thresh
    bins = [(0, 17), (17, 18), (18, 19), (19, 20), (20, 21.51)]
    table = [{'V': f'{a:g}-{b:g}' if b < 21 else f'{a:g}-21.5', 'n': sum(1 for r in rows if a <= r['V'] < b),
              'single': sum(1 for r in rows if a <= r['V'] < b and r['seen_single']),
              'stack': sum(1 for r in rows if a <= r['V'] < b and r['seen_stack'])} for a, b in bins]
    examples = []
    picks = sorted([r for r in rows if r['seen_stack'] and not r['seen_single'] and r['n_images'] >= 8], key=lambda r: -r['V'])[:2]
    picks += sorted([r for r in rows if r['seen_single'] and r['n_images'] >= 8], key=lambda r: -r['V'])[:1]
    for r in picks:
        tag, cache, folder = next(x for x in SETS if x[0] == r['set'])
        plan = json.loads((folder / 'plan.json').read_text())
        f = next(x for x in plan['fields'] if x['id'] == r['field'])
        pics = _stamps(tag, cache, f, json.loads((folder / 'known.json').read_text()), r['name'])
        if pics:
            examples.append({'name': r['name'], 'V': r['V'], 'class': r['class'], 'n_images': r['n_images'], 'stack_snr': r['stack_snr'],
                             'best_single_snr': r['best_single_snr'], 'seen_single': r['seen_single'], 'pixel_arcsec': 6.15, **pics})
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'n_asteroids': len(rows), 'n_control_paths': int(ctrl.size),
           'threshold_stack_snr': round(thresh, 2), 'control_false_rate': FALSE_RATE,
           'control_snr_spread': {'median': round(float(np.median(ctrl)), 2), 'mad': round(float(1.4826 * np.median(np.abs(ctrl - np.median(ctrl)))), 2)},
           'by_V': table, 'n_seen_single': sum(r['seen_single'] for r in rows), 'n_seen_stack': sum(r['seen_stack'] for r in rows),
           'rule': {'v_max': V_MAX, 'away_hours': AWAY_H, 'control_shifts_arcsec': CONTROL_SHIFTS, 'min_images': MIN_IMAGES},
           'asteroids': sorted(rows, key=lambda r: (r['V'], r['name'])), 'examples': examples,
           'what_it_is': ('Known asteroids, measured where IMCCE SkyBoT says they were, with no search. Adding the images along each path is '
                          'compared with single images, and with control paths 60" away. It measures how much deeper stacking reaches. '
                          'It discovers nothing.')}
    (OUT / 'stack.json').write_text(json.dumps(doc, indent=1))
    e = ledger.append('asteroids:stack', [OUT / 'stack.json', Path(__file__)], note='Known asteroids: stacked along their paths versus single images.')
    log(f"threshold {thresh:.2f} (1% of {ctrl.size} control paths); seen in single images {doc['n_seen_single']}, in stacks {doc['n_seen_stack']} of "
        f"{len(rows)}; by V: " + ', '.join(f"{t['V']}: {t['single']}->{t['stack']}/{t['n']}" for t in table) + f"; ledger entry {e['seq']}")
    return doc


def examples(log=print) -> dict:
    """Re-pick the picture examples (after the lock of the measurements, which are not changed): asteroids that are clear when the
    photos are added (stacked S/N 5 or more) but under S/N 4 in every single photo, with 8 or more photos, faintest first.  The first
    pick (faintest that reached the 1% threshold) chose cases where one photo was brighter than the whole stack: an artefact in
    that photo, not a good illustration."""
    import sys as _sys
    from validation import ledger
    doc = json.loads((OUT / 'stack.json').read_text())
    rows = doc['asteroids']
    picks = sorted([r for r in rows if r['stack_snr'] >= 5 and r['best_single_snr'] < 4 and r['n_images'] >= 8], key=lambda r: -r['V'])[:2]
    out = []
    for r in picks:
        tag, cache, folder = next(x for x in SETS if x[0] == r['set'])
        plan = json.loads((folder / 'plan.json').read_text())
        f = next(x for x in plan['fields'] if x['id'] == r['field'])
        pics = _stamps(tag, cache, f, json.loads((folder / 'known.json').read_text()), r['name'])
        if pics:
            out.append({'name': r['name'], 'V': r['V'], 'class': r['class'], 'n_images': r['n_images'], 'stack_snr': r['stack_snr'],
                        'best_single_snr': r['best_single_snr'], 'seen_single': r['seen_single'], 'pixel_arcsec': 6.15, **pics})
    doc['examples'] = out
    doc['examples_rule'] = 'stacked S/N 5 or more, every single photo under S/N 4, 8 or more photos, faintest first (re-picked after the lock)'
    (OUT / 'stack.json').write_text(json.dumps(doc, indent=1))
    e = ledger.append('asteroids:stack:examples', [OUT / 'stack.json', Path(__file__)],
                      note='Picture examples re-picked (stacked S/N 5+, every single photo under 4); a photo is kept in the pictures if its centre '
                           'is measured (masked edge pixels shown as empty). Measurements unchanged.')
    said = ', '.join(f"{x['name']} (V {x['V']}, stack {x['stack_snr']}, best single {x['best_single_snr']})" for x in out)
    log(f"examples: {said}; ledger entry {e['seq']}")
    return doc


if __name__ == '__main__':
    import sys
    {'run': run, 'examples': examples}[sys.argv[1] if len(sys.argv) > 1 else 'run']()
