"""Blind recovery of known distant bodies, as the test of the distant-world search.

    python -m validation.distant_run detect makemake     # stage A+B on every downloaded exposure
    python -m validation.distant_run link makemake       # stages C-E; writes blind.json and LOCKS it
    python -m validation.distant_run score makemake      # only now opens the JPL ephemeris and scores

`detect` and `link` read image files, Gaia DR3 and CatWISE2020.  They never read an ephemeris.
"""
from __future__ import annotations

import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from pipeline import distant
from pipeline.measure import gaia_field
from validation import ledger

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation' / 'distant'
CACHE = ROOT / '.parallax-cache' / 'distant'
CONE_DEG = 0.21

# ---- pass rule, written before any body was scored (see validation/distant/PROTOCOL.md) ----
PASS = {'position_arcsec': 12.0, 'min_fraction_on_track': 0.9, 'distance_fraction': 0.05, 'max_other_objects': 0}


def detect(body: str, log=print) -> dict:
    plan = json.loads((OUT / body / 'plan.json').read_text())
    jobs, bins = [], []
    for b in plan['bins']:
        folder = CACHE / body / b['id']
        files = sorted(folder.glob('*.fits'))
        if not files:
            continue
        gaia = gaia_field(b['ra'], b['dec'], CONE_DEG, gmax=21.5, cache=folder / 'gaia_all.json')
        wise = distant.catwise_field(b['ra'], b['dec'], CONE_DEG, cache=folder / 'catwise.json')
        bins.append({'id': b['id'], 'n_files': len(files), 'n_gaia': len(gaia), 'n_wise': len(wise), 'wise_catalogue': wise[0]['cat'] if wise else None})
        jobs += [(str(f), gaia, wise) for f in files]
    log(f'{body}: {len(jobs)} exposures in {len(bins)} fields')
    with ProcessPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(distant.detect_file, jobs, chunksize=2))
    orphans = [o for r in results for o in r['orphans']]
    ok = [r for r in results if r['ok']]
    doc = {'body': body, 'n_exposures': len(results), 'n_registered': len(ok), 'n_peaks': sum(r['n_peaks'] for r in results),
           'n_explained': sum(r['n_explained'] for r in results), 'n_orphans': len(orphans),
           'failed': [{'path': Path(r['path']).name, 'reason': r.get('reason')} for r in results if not r['ok']][:40],
           'exposures': [{'product_id': r['product_id'], 'mjd': r['mjd'], 'detector': r['detector'], 'n_orphans': len(r['orphans'])} for r in ok],
           'bins': bins, 'orphans': orphans}
    (OUT / body / 'orphans.json').write_text(json.dumps(doc))
    log(f'{body}: {len(ok)}/{len(results)} registered, {doc["n_peaks"]} peaks, {doc["n_explained"]} explained by catalogues, {len(orphans)} orphans')
    return doc


def link(body: str, log=print) -> dict:
    doc = json.loads((OUT / body / 'orphans.json').read_text())
    dets = sorted(doc['orphans'], key=lambda d: d['mjd'])
    vid = distant.split_visits([d['mjd'] for d in dets]) if dets else np.array([], int)
    tracks, visit_of = [], []
    for v in sorted(set(vid.tolist())):
        idx = np.where(vid == v)[0]
        for t in distant.tracklets([dets[i] for i in idx]):
            t['members'] = [int(idx[k]) for k in t['members']]
            t['visit'] = int(v)
            tracks.append(t)
            visit_of.append(int(v))
    objects = distant.link_orbits(dets, tracks, visit_of)
    for o in objects:
        o['detections'] = [dets[m] for m in o['members']]
        o['reflectance'] = distant.reflectance(o['detections'])
        o['accepted'] = bool(o['passes_mirror_test'] and o['n_visits'] >= 2)
    blind = {'body_field_set': body, 'thresholds': distant.thresholds(), 'n_exposures': doc['n_exposures'], 'n_orphans': len(dets),
             'n_visits': int(len(set(vid.tolist()))), 'visits': [{'visit': int(v), 'n_orphans': int((vid == v).sum()),
                                                                 'mjd_start': float(min(d['mjd'] for d, w in zip(dets, vid) if w == v)),
                                                                 'mjd_end': float(max(d['mjd'] for d, w in zip(dets, vid) if w == v))} for v in sorted(set(vid.tolist()))],
             'tracklets': [{k: t[k] for k in ('visit', 'n', 'nights', 'span_days', 'rate_arcsec_day', 'rms_arcsec', 't_mid_mjd')} for t in tracks],
             'objects': objects,
             'statement': 'Produced from image files, Gaia DR3 and CatWISE2020 only. No ephemeris was read.'}
    path = OUT / body / 'blind.json'
    path.write_text(json.dumps(blind, indent=1))
    e = ledger.append(f'distant-blind:{body}', [path], note='Blind linking result, locked before the ephemeris is opened for scoring.')
    log(f'{body}: {len(tracks)} tracklets, {len(objects)} linked object(s); locked as ledger entry {e["seq"]} ({e["hash"][:12]})')
    for o in objects:
        ob = o['orbit']
        log(f'   object: {o["n_visits"]} visits, {ob["n"]} detections, r = {ob["r_au"]:.2f} ± {ob["r_err_au"] or float("nan"):.2f} AU, chi2r {ob["chi2r"]:.2f}, '
            f'mirror ratio {o["mirror_ratio"] and round(o["mirror_ratio"])}, accepted {o["accepted"]}')
    return blind


def score(body: str, log=print) -> dict:
    from pipeline import ephem                       # the ephemeris is imported here and nowhere above
    path = OUT / body / 'blind.json'
    lock = ledger.locked(f'distant-blind:{body}', path)
    blind = json.loads(path.read_text())
    spec = ephem.BODIES[body]
    eph = ephem.horizons(spec['command'], '2025-04-20', '2026-11-05', '6 h')
    accepted = [o for o in blind['objects'] if o['accepted']]
    rows = []
    for o in accepted:
        mjd = np.array([d['mjd'] for d in o['detections']])
        ra, dec, r_true, _ = ephem.at(eph, mjd)
        sep = np.hypot((np.array([d['ra'] for d in o['detections']]) - ra) * np.cos(np.radians(dec)), np.array([d['dec'] for d in o['detections']]) - dec) * 3600
        t0 = o['orbit']['t0_mjd']
        r0 = float(np.interp(t0, eph['mjd'], eph['r_au']))
        rows.append({'on_track_fraction': float(np.mean(sep <= PASS['position_arcsec'])), 'median_sep_arcsec': float(np.median(sep)),
                     'r_fit_au': o['orbit']['r_au'], 'r_err_au': o['orbit']['r_err_au'], 'r_true_au': r0,
                     'distance_error_fraction': abs(o['orbit']['r_au'] - r0) / r0,
                     'distance_error_sigma': (abs(o['orbit']['r_au'] - r0) / o['orbit']['r_err_au']) if o['orbit']['r_err_au'] else None,
                     'n_visits': o['n_visits'], 'n_detections': o['orbit']['n'], 'a_au': o['orbit']['a_au'], 'inclination_deg': o['orbit']['inclination_deg'],
                     'is_body': bool(np.mean(sep <= PASS['position_arcsec']) >= PASS['min_fraction_on_track'])})
    match = next((r for r in rows if r['is_body']), None)
    others = sum(1 for r in rows if not r['is_body'])
    vmag = float(np.nanmedian(eph['vmag']))
    result = {'body': body, 'title': spec['title'], 'kind': spec['kind'], 'pass_rule': PASS, 'locked_entry': lock['seq'], 'locked_hash': lock['hash'],
              'locked_time_utc': lock['time_utc'], 'vmag': vmag if math.isfinite(vmag) else None,
              'recovered': bool(match), 'match': match, 'other_objects': others, 'objects_scored': rows,
              'passed': bool(match and match['distance_error_fraction'] <= PASS['distance_fraction'] and others <= PASS['max_other_objects']),
              'truth_source': 'JPL Horizons, geocentric astrometric positions'}
    (OUT / body / 'result.json').write_text(json.dumps(result, indent=1))
    if match:
        log(f'{body}: RECOVERED. distance {match["r_fit_au"]:.2f} ± {match["r_err_au"] or float("nan"):.2f} AU vs JPL {match["r_true_au"]:.2f} AU '
            f'({100 * match["distance_error_fraction"]:.2f}% off), median offset {match["median_sep_arcsec"]:.1f}", other objects {others}, PASS={result["passed"]}')
    else:
        log(f'{body}: not recovered ({len(rows)} accepted object(s), none on the ephemeris)')
    return result


if __name__ == '__main__':
    cmd, names = sys.argv[1], sys.argv[2:]
    for name in names:
        {'detect': detect, 'link': link, 'score': score}[cmd](name)
