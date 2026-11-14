"""Shift-and-stack search on the distant-world fields: blind, locked, then scored.

    python -m validation.shiftstack_run lock          # hash the method and protocol before any run
    python -m validation.shiftstack_run search eris   # blind: images, Gaia DR3 only; writes and locks shiftstack_blind.json
    python -m validation.shiftstack_run score eris    # refuses if the blind file changed; then opens JPL Horizons
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

from pipeline import distant, shiftstack
from pipeline.measure import reference_candidates
from validation import ledger

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation' / 'distant'
CACHE = ROOT / '.parallax-cache' / 'distant'
PASS = {'position_arcsec': 15.0, 'distance_fraction': 0.10, 'max_other_objects': 0}


def _visits(bins):
    bins = sorted(bins, key=lambda b: b['t_mjd'])
    groups = []
    for b in bins:
        if not groups or b['t_mjd'] - groups[-1][-1]['t_mjd'] > 20:
            groups.append([])
        groups[-1].append(b)
    return groups


def search(body: str, log=print) -> dict:
    plan = json.loads((OUT / body / 'plan.json').read_text())
    visits = []
    for g in _visits(plan['bins']):
        files, gaia = [], {}
        for b in g:
            folder = CACHE / body / b['id']
            files += sorted(folder.glob('*.fits'))
            if (folder / 'gaia_all.json').is_file():
                for s in json.loads((folder / 'gaia_all.json').read_text()):
                    gaia[s['source_id']] = s
        if len(files) < 8:
            log(f'  visit with {len(files)} exposures: too few to stack, skipped')
            visits.append({'n_exposures': len(files), 'skipped': True, 'candidates': []})
            continue
        ra0 = float(np.degrees(np.arctan2(np.mean(np.sin(np.radians([b['ra'] for b in g]))), np.mean(np.cos(np.radians([b['ra'] for b in g])))))) % 360
        dec0 = float(np.mean([b['dec'] for b in g]))
        refs = reference_candidates([s for s in gaia.values() if s.get('g') is not None and s['g'] < 18.5])
        items, errors = shiftstack.prepare(files, ra0, dec0, plan['size_arcmin'], refs)
        res = shiftstack.search_visit(items)
        cands = shiftstack.to_sky(res['peaks'], ra0, dec0, plan['size_arcmin'], res['t0_mjd'], res['span_days'])
        visits.append({'n_exposures': len(items), 'n_failed': len(errors), 't0_mjd': res['t0_mjd'], 'span_days': res['span_days'],
                       'n_trials': res['n_trials'], 'masked_fraction': res['masked_fraction'],
                       'candidates': [{k: c[k] for k in ('ra', 'dec', 'snr', 'rate_arcsec_day', 'vx_px_day', 'vy_px_day', 'pseudo')} for c in cands]})
        log(f'  visit: {len(items)} exposures over {res["span_days"]:.1f} days, {res["n_trials"]} trial motions, {len(cands)} candidate(s) >= {shiftstack.THRESH} sigma'
            + (f' (best {cands[0]["snr"]:.1f} sigma at {cands[0]["rate_arcsec_day"]:.1f}"/day)' if cands else ''))
    linked = shiftstack.link([v['candidates'] for v in visits])
    objects = [{'visits': o['visits'], 'members': o['members'], 'r_au': o['orbit']['r_au'], 'r_err_au': o['orbit']['r_err_au'],
                'chi2r': o['orbit']['chi2r'], 'mirror_ratio': o['mirror_ratio'], 'passes_mirror_test': o['passes_mirror_test'],
                'a_au': o['orbit']['a_au'], 'inclination_deg': o['orbit']['inclination_deg'], 'orbit': o['orbit'], 'detections': o['detections'],
                'accepted': bool(o['passes_mirror_test'] and len(o['visits']) >= 2)} for o in linked]
    doc = {'body_field_set': body, 'method': 'shift-and-stack', 'thresholds': shiftstack.thresholds(), 'visits': visits, 'objects': objects,
           'statement': 'Produced from image files and Gaia DR3 only. No ephemeris was read.'}
    path = OUT / body / f"shiftstack_blind_v{shiftstack.thresholds().get('version', 1)}.json"
    path.write_text(json.dumps(doc, indent=1))
    e = ledger.append(f"shiftstack-blind-v{shiftstack.thresholds().get('version', 1)}:{body}", [path], note='Shift-and-stack blind result, locked before the ephemeris is opened.')
    acc = [o for o in objects if o['accepted']]
    log(f'{body}: {len(objects)} linked, {len(acc)} accepted; locked as ledger entry {e["seq"]} ({e["hash"][:12]})')
    for o in acc:
        log(f"   object: visits {o['visits']}, r = {o['r_au']:.2f} ± {o['r_err_au'] or float('nan'):.2f} AU, chi2r {o['chi2r']:.2f}, mirror ratio {o['mirror_ratio'] and round(o['mirror_ratio'])}")
    return doc


def score(body: str, log=print) -> dict:
    from pipeline import ephem
    v = shiftstack.thresholds().get('version', 1)
    path = OUT / body / f'shiftstack_blind_v{v}.json'
    lock = ledger.locked(f'shiftstack-blind-v{v}:{body}', path)
    blind = json.loads(path.read_text())
    eph = ephem.horizons(ephem.BODIES[body]['command'], '2025-04-20', '2026-11-05', '6 h')
    rows = []
    for o in [o for o in blind['objects'] if o['accepted']]:
        mj = np.array([m['mjd'] for m in o['detections']])
        ra, dec, _, _ = ephem.at(eph, mj)
        sep = np.hypot((np.array([m['ra'] for m in o['detections']]) - ra) * np.cos(np.radians(dec)), np.array([m['dec'] for m in o['detections']]) - dec) * 3600
        r_true = float(np.interp(o['orbit']['t0_mjd'], eph['mjd'], eph['r_au']))
        rows.append({'median_sep_arcsec': float(np.median(sep)), 'max_sep_arcsec': float(sep.max()), 'r_fit_au': o['r_au'], 'r_err_au': o['r_err_au'],
                     'r_true_au': r_true, 'distance_error_fraction': abs(o['r_au'] - r_true) / r_true, 'n_visits': len(o['visits']),
                     'is_body': bool(np.median(sep) <= PASS['position_arcsec'])})
    match = next((r for r in rows if r['is_body']), None)
    others = sum(1 for r in rows if not r['is_body'])
    # after the fact: how strong was the body in each visit's stack? (position from JPL; diagnostic only)
    res = {'body': body, 'method': 'shift-and-stack', 'pass_rule': PASS, 'locked_entry': lock['seq'], 'locked_hash': lock['hash'],
           'locked_time_utc': lock['time_utc'], 'recovered': bool(match), 'match': match, 'other_objects': others, 'objects_scored': rows,
           'passed': bool(match and match['distance_error_fraction'] <= PASS['distance_fraction'] and others <= PASS['max_other_objects'])}
    res['version'] = v
    (OUT / body / f'shiftstack_result_v{v}.json').write_text(json.dumps(res, indent=1))
    if match:
        log(f"{body}: RECOVERED by shift-and-stack. {match['r_fit_au']:.2f} ± {match['r_err_au'] or float('nan'):.2f} AU vs JPL {match['r_true_au']:.2f} "
            f"({100 * match['distance_error_fraction']:.1f}% off), median offset {match['median_sep_arcsec']:.1f}\", other objects {others}, PASS={res['passed']}")
    else:
        log(f'{body}: not recovered by shift-and-stack ({len(rows)} accepted object(s))')
    return res


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'lock':
        e = ledger.append(f"shiftstack-protocol-v{shiftstack.thresholds().get('version', 1)}", [ROOT / 'pipeline' / 'shiftstack.py', Path(__file__), OUT / 'PROTOCOL_SHIFTSTACK.md'],
                          note='Shift-and-stack method, thresholds and pass rule, locked before the first run on real data.')
        print(f'locked as ledger entry {e["seq"]}')
    else:
        for name in sys.argv[2:]:
            {'search': search, 'score': score}[cmd](name)
