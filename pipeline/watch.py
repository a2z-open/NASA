"""The SPHEREx watcher: check NASA's archive for new images of everything PARALLAX has made a prediction about.

    python -m pipeline.watch            # one check (takes about a minute); run it after each weekly SPHEREx release

NASA/IPAC publishes new SPHEREx images every week.  Real-time systems for moving objects exist for optical surveys
(ZTF and Rubin alert brokers such as Fink and SNAPS); we found none that watches SPHEREx.  This watcher asks the archive,
for each locked forecast and each NASA target, whether images newer than the last check exist at the right place and
time, and records the answer in data/watch/status.json (shown in the app) and data/watch/history.jsonl.

It only reads the archive's index; it does not download or score anything by itself.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from astropy.time import Time

from . import spherex

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'watch'
FORECASTS = ROOT / 'validation' / 'forecasts'
TARGETS = ROOT / 'data' / 'targets'


def _iso(mjd):
    return Time(mjd, format='mjd').isot[:19] + 'Z' if mjd else None


def _mjd(iso):
    return Time(iso.rstrip('Z'), format='isot', scale='utc').mjd if iso else None


def check_forecast(path: Path, now_mjd: float) -> dict:
    f = json.loads(path.read_text())
    lock_mjd = _mjd(f['locked_utc'].replace('+00:00', ''))
    latest_at_lock = _mjd((f.get('archive_at_lock') or {}).get('latest_exposure_utc'))
    preds = f['predictions']
    moving = f.get('kind') == 'forward_prediction_distant_world'
    # where to look: a star barely moves, so its first predicted position; a distant world, each date in a viewing window
    spots = [p for p in preds if p.get('in_spherex_window')] if moving else preds[:1]
    new, n_total = [], 0
    for p in spots[:6]:
        prods = spherex.search(p['ra_deg'], p['dec_deg'], radius_deg=0.003)
        n_total += len(prods)
        for q in prods:
            after = q.t_min > max(lock_mjd, latest_at_lock or 0)
            near = (not moving) or abs(q.t_mid - p['mjd']) <= 20
            if after and near:
                new.append({'id': q.id, 'time_utc': _iso(q.t_mid), 'release': q.release})
    upcoming = [p for p in preds if p['mjd'] > now_mjd]
    nxt = next((w for w in f.get('spherex_windows', []) if _mjd(w['end_utc'] + 'T23:59:59') > now_mjd), None)
    return {'name': f['title'], 'kind': 'forecast', 'target': f['target'], 'locked_utc': f['locked_utc'],
            'status': 'new_data' if new else 'waiting', 'n_new': len({n['id'] for n in new}), 'new': new[:12],
            'n_archive_products_checked': n_total,
            'next_window': nxt, 'next_prediction_utc': upcoming[0]['date_utc'] if upcoming else None,
            'note': ('New SPHEREx images exist where and when the forecast says to look: ready to score.' if new else
                     (f"No images yet. SPHEREx should next see it between {nxt['start_utc']} and {nxt['end_utc']}." if nxt else
                      'No images newer than the lock yet.'))}


def check_target(folder: Path) -> dict | None:
    f = folder / 'field.json'
    m = folder / 'archive_manifest.json'
    if not f.is_file() or not m.is_file():
        return None
    tg = json.loads(f.read_text())
    man = json.loads(m.read_text())
    ra, dec = tg.get('ra'), tg.get('dec')
    if ra is None:
        return None
    known = {p.get('id') or f"{p['obs_id']}-D{p['detector']}" for p in man.get('products', [])}
    newest_cached = max((float(p['t_max']) for p in man.get('products', []) if p.get('t_max') is not None), default=0.0)
    prods = spherex.search(ra, dec, radius_deg=0.003)
    missing = [p for p in prods if p.id not in known]
    fresh = [p for p in missing if p.t_min > newest_cached]          # released after our cache: genuinely new
    older = [p for p in missing if p.t_min <= newest_cached]         # older, not loaded (usually at the edge of the field)
    note = (f'{len(fresh)} new exposure(s) since this app last loaded the field.' if fresh else 'No new exposures since this app last loaded the field.')
    if older:
        note += f' {len(older)} older exposure(s) are in the archive but not loaded.'
    return {'name': tg.get('title', folder.name), 'kind': 'target', 'target': folder.name, 'status': 'new_data' if fresh else 'up_to_date',
            'n_new': len(fresh), 'n_older_not_loaded': len(older), 'n_in_archive': len(prods), 'n_cached': len(known),
            'newest_cached_utc': _iso(newest_cached or None), 'latest_utc': _iso(max((p.t_mid for p in prods), default=None)),
            'new': [{'id': p.id, 'time_utc': _iso(p.t_mid), 'release': p.release} for p in sorted(fresh, key=lambda p: p.t_min)[-12:]],
            'note': note}


def run(log=print) -> dict:
    now = datetime.now(timezone.utc)
    now_mjd = Time(now).mjd
    items, errors = [], []
    for p in sorted(FORECASTS.glob('*.json')):
        if p.name.endswith('-vs-jpl.json'):
            continue
        try:
            items.append(check_forecast(p, now_mjd))
        except Exception as error:  # noqa: BLE001
            errors.append({'item': p.stem, 'error': str(error)[:200]})
    for folder in sorted(TARGETS.iterdir()):
        try:
            r = check_target(folder) if folder.is_dir() else None
            if r:
                items.append(r)
        except Exception as error:  # noqa: BLE001
            errors.append({'item': folder.name, 'error': str(error)[:200]})
    doc = {'checked_utc': now.isoformat(timespec='seconds'), 'archive': 'NASA/IPAC IRSA, SPHEREx DR1 and QR3 (SIA2)',
           'items': items, 'errors': errors, 'n_new_total': sum(i['n_new'] for i in items),
           'how': 'python -m pipeline.watch, run after each weekly SPHEREx release.'}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'status.json').write_text(json.dumps(doc, indent=1))
    with (OUT / 'history.jsonl').open('a') as fh:
        fh.write(json.dumps({'checked_utc': doc['checked_utc'], 'n_new_total': doc['n_new_total'],
                             'items': {i['target'] + ':' + i['kind']: i['n_new'] for i in items}, 'errors': len(errors)}) + '\n')
    for i in items:
        log(f"{i['kind']:8s} {i['name']:22s} {i['status']:11s} new {i['n_new']:3d}  {i['note']}")
    for e in errors:
        log('ERROR', e)
    return doc


if __name__ == '__main__':
    sys.exit(0 if run() else 1)
