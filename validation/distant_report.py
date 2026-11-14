"""Collect the distant-world results into one file for the app and the documents.

    python -m validation.distant_report

Reads each body's locked blind.json and its result.json.  The "diagnostic" block is computed AFTER scoring, with
the ephemeris, to explain a miss.  It is labelled as after-the-fact everywhere it is shown.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from pipeline import distant, ephem
from pipeline.astrometry import JULIAN_YEAR_DAYS, earth_barycentric_au
from validation import ledger

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation' / 'distant'


# What earlier work found on each surface, and where that ice absorbs (micrometres).  Band centres are the
# strong near-infrared bands of solid methane (Grundy et al. 2002) and of water ice; they are drawn as guides only.
SURFACE = {
    'makemake': {'ice': 'methane ice', 'bands_um': [1.16, 1.33, 1.67, 1.72, 1.80, 2.20, 2.32], 'reference': 'Licandro et al. 2006, A&A 445, L35'},
    'eris': {'ice': 'methane ice', 'bands_um': [1.16, 1.33, 1.67, 1.72, 1.80, 2.20, 2.32], 'reference': 'Brown, Trujillo & Rabinowitz 2005, ApJ 635, L97'},
    'pluto': {'ice': 'methane ice', 'bands_um': [1.16, 1.33, 1.67, 1.72, 1.80, 2.20, 2.32], 'reference': 'Owen et al. 1993, Science 261, 745'},
    'haumea': {'ice': 'water ice', 'bands_um': [1.50, 1.65, 2.00], 'reference': 'Trujillo et al. 2007, ApJ 655, 1172'},
}


def _offsets(ra, dec, ra0, dec0):
    return (((np.asarray(ra) - ra0 + 180) % 360) - 180) * math.cos(math.radians(dec0)), np.asarray(dec) - dec0


def one(body: str) -> dict | None:
    folder = OUT / body
    if not (folder / 'result.json').is_file():
        return None
    res = json.loads((folder / 'result.json').read_text())
    blind = json.loads((folder / 'blind.json').read_text())
    orph = json.loads((folder / 'orphans.json').read_text())
    plan = json.loads((folder / 'plan.json').read_text())
    spec = ephem.BODIES[body]
    out = {'body': body, 'title': spec['title'], 'kind': spec['kind'], 'vmag': res['vmag'], 'passed': res['passed'], 'recovered': res['recovered'],
           'other_objects': res['other_objects'], 'n_fields': len(plan['bins']), 'field_arcmin': plan['size_arcmin'],
           'n_exposures': orph['n_exposures'], 'n_registered': orph['n_registered'], 'n_peaks': orph['n_peaks'],
           'n_explained': orph['n_explained'], 'n_orphans': orph['n_orphans'], 'n_tracklets': len(blind['tracklets']),
           'wise_catalogue': sorted({b.get('wise_catalogue') for b in orph['bins'] if b.get('wise_catalogue')}),
           'locked': {'entry': res['locked_entry'], 'hash': res['locked_hash'], 'time_utc': res['locked_time_utc']},
           'pass_rule': res['pass_rule'], 'match': res['match']}
    out['method'] = 'tracklets' if res['recovered'] else None
    obj = next((o for o in blind['objects'] if o['accepted']), None) if res['recovered'] else None
    # the deeper search: shift-and-stack (pipeline/shiftstack.py), scored only after its own lock
    ssr = sorted(folder.glob('shiftstack_result_v*.json'))
    if not res['recovered'] and ssr:
        ss = json.loads(ssr[-1].read_text())
        v = ss.get('version', 1)
        ssb = json.loads((folder / f'shiftstack_blind_v{v}.json').read_text())
        if ss.get('recovered'):
            sso = next(o for o in ssb['objects'] if o['accepted'])
            n_used = sum(vv.get('n_exposures', 0) for vv in ssb['visits'] if not vv.get('skipped'))
            out.update({'method': 'shift-and-stack', 'recovered': True, 'passed': ss['passed'], 'other_objects': ss['other_objects'],
                        'locked': {'entry': ss['locked_entry'], 'hash': ss['locked_hash'], 'time_utc': ss['locked_time_utc']},
                        'shiftstack': {'version': v, 'n_exposures_stacked': n_used, 'n_trials': [vv.get('n_trials') for vv in ssb['visits']],
                                       'snr': [m['snr'] for m in sso['members']], 'rate_arcsec_day': [m['rate_arcsec_day'] for m in sso['members']],
                                       'versions_on_record': len(list(folder.glob('shiftstack_blind_v*.json')))},
                        'match': ss['match'] | {'n_detections': len(sso['members']), 'n_visits': len(sso['visits'])}})
            obj = {'orbit': sso['orbit'], 'detections': [dict(d, snr=m['snr'], wavelength_um=None, flux_ujy=None, flux_err_ujy=None, detector=0)
                                                          for d, m in zip(sso['detections'], sso['members'])],
                   'n_visits': len(sso['visits']), 'mirror_ratio': sso['mirror_ratio'], 'reflectance': []}
    if obj:
        ob = obj['orbit']
        dets = obj['detections']
        p = np.array(ob['params'])
        ra0, dec0 = math.degrees(p[0]) % 360, math.degrees(p[1])
        mjd = np.array([d['mjd'] for d in dets])
        vid = distant.split_visits(mjd)
        dx, dy = _offsets([d['ra'] for d in dets], [d['dec'] for d in dets], ra0, dec0)
        grid = np.arange(mjd.min() - 25, mjd.max() + 25, 3.0)
        cra, cdec, _ = distant.predict(p, (grid - ob['t0_mjd']) / JULIAN_YEAR_DAYS, earth_barycentric_au(grid))
        cx, cy = _offsets(cra, cdec, ra0, dec0)
        # the same orbit seen from the Sun: no parallax, only the body's own motion
        sra, sdec, _ = distant.predict(p, (grid - ob['t0_mjd']) / JULIAN_YEAR_DAYS, np.zeros((len(grid), 3)))
        sx, sy = _offsets(sra, sdec, ra0, dec0)
        out['object'] = {
            'r_au': ob['r_au'], 'r_err_au': ob['r_err_au'], 'a_au': ob['a_au'], 'inclination_deg': ob['inclination_deg'],
            'chi2r': ob['chi2r'], 'rms_arcsec': ob['rms_arcsec'], 'n': ob['n'], 'n_visits': obj['n_visits'],
            'parallax_arcsec': ob['parallax_arcsec'], 'tangential_arcsec_yr': ob['tangential_arcsec_yr'],
            'mirror_ratio': obj['mirror_ratio'], 'ra0_deg': ra0, 'dec0_deg': dec0, 't0_mjd': ob['t0_mjd'],
            'jump_deg': float(np.hypot(cx.max() - cx.min(), cy.max() - cy.min())),
            'detections': [{'mjd': d['mjd'], 'dx_deg': float(a), 'dy_deg': float(b), 'snr': d['snr'], 'visit': int(v),
                            'wavelength_um': d['wavelength_um'], 'flux_ujy': d['flux_ujy'], 'flux_err_ujy': d['flux_err_ujy'], 'detector': d['detector']}
                           for d, a, b, v in zip(dets, dx, dy, vid)],
            'curve': [{'mjd': float(t), 'dx_deg': float(a), 'dy_deg': float(b)} for t, a, b in zip(grid, cx, cy)],
            'from_sun': [{'mjd': float(t), 'dx_deg': float(a), 'dy_deg': float(b)} for t, a, b in zip(grid, sx, sy)],
            'reflectance': obj.get('reflectance') or [],
        }
        sp = folder / 'spectrum.json'
        if sp.is_file():
            spec_doc = json.loads(sp.read_text())
            out['object']['spectrum'] = spec_doc['reflectance']
            out['object']['spectrum_exposures'] = spec_doc['n_exposures_used']
        out['object']['surface'] = SURFACE.get(body)
    # ---- after-the-fact diagnostic (uses the ephemeris; never feeds back into the blind result) ----
    eph = ephem.horizons(spec['command'], '2025-04-20', '2026-11-05', '6 h')
    dets = sorted(orph['orphans'], key=lambda d: d['mjd'])
    diag = {'label': 'After the fact, using the ephemeris. Not part of the blind test.', 'visits': []}
    if dets:
        mjd = np.array([d['mjd'] for d in dets])
        era, edec, _, _ = ephem.at(eph, mjd)
        sep = np.hypot((np.array([d['ra'] for d in dets]) - era) * np.cos(np.radians(edec)), np.array([d['dec'] for d in dets]) - edec) * 3600
        vid = distant.split_visits(mjd)
        emjd = np.array([e['mjd'] for e in orph['exposures']])
        for v in sorted(set(vid.tolist())):
            s = vid == v
            diag['visits'].append({'mjd_start': float(mjd[s].min()), 'mjd_end': float(mjd[s].max()),
                                   'n_exposures': int(np.sum((emjd > mjd[s].min() - 20) & (emjd < mjd[s].max() + 20))),
                                   'n_detections_of_body': int(np.sum(s & (sep < 12))),
                                   'nights': int(len(set(np.floor(mjd[s & (sep < 12)]).astype(int))))})
        if not res['recovered']:
            tr = distant.tracklets([d for d, k in zip(dets, vid) if k == int(np.bincount(vid[sep < 12]).argmax())]) if (sep < 12).any() else []
            if tr:
                vdets = [d for d, k in zip(dets, vid) if k == int(np.bincount(vid[sep < 12]).argmax())]
                members = [vdets[i] for i in tr[0]['members']]
                orb = distant.fit_orbit(members)
                if orb:
                    r_true = float(np.interp(orb['t0_mjd'], eph['mjd'], eph['r_au']))
                    diag['one_visit_fit'] = {'n': orb['n'], 'span_days': tr[0]['span_days'], 'nights': tr[0]['nights'], 'r_au': orb['r_au'],
                                             'r_err_au': orb['r_err_au'], 'r_true_au': r_true, 'chi2r': orb['chi2r'],
                                             'rate_arcsec_day': tr[0]['rate_arcsec_day']}
            n_with = sum(1 for v in diag['visits'] if v['n_detections_of_body'] >= distant.TRACKLET_MIN)
            diag['why_missed'] = ('Only one visit holds enough detections of the body, and the rule needs two.' if n_with == 1
                                  else 'No visit holds enough detections of the body.' if n_with == 0
                                  else 'Tracklets exist in two or more visits but no orbit joined them within the limits.')
    # how crowded the fields are: catalogued sources inside one rejection circle (1.3 pixels), on average
    cone_arcsec2 = math.pi * (0.21 * 3600) ** 2
    circle_arcsec2 = math.pi * (distant.STAR_RADIUS_PX * 6.15) ** 2
    per_circle = [(b.get('n_gaia', 0) + b.get('n_wise', 0)) / cone_arcsec2 * circle_arcsec2 for b in orph['bins']]
    diag['catalogue_sources_per_rejection_circle'] = float(np.median(per_circle)) if per_circle else None
    if not res['recovered'] and per_circle and np.median(per_circle) >= 1.0:
        diag['why_missed'] = (f"The field is too crowded: on average {np.median(per_circle):.1f} catalogued stars lie inside each rejection circle, "
                              'so the catalogue step removes nearly every source, the body included.')
    elif not res['recovered'] and not dets:
        diag['why_missed'] = 'No uncatalogued detection at all.'
    elif not res['recovered'] and dets and not (sep < 12).any() and res.get('vmag') and res['vmag'] > 18:
        diag['why_missed'] = f"Too faint for one exposure (magnitude {res['vmag']:.1f}): it never reaches the detection limit, so there is nothing to link."

    out['diagnostic'] = diag
    return out


def build(log=print) -> dict:
    bodies = [b for b in (one(name) for name in ephem.BODIES) if b]
    ok, problems = ledger.verify()
    rec = [b for b in bodies if b['passed']]
    errs = [100 * b['match']['distance_error_fraction'] for b in rec]
    doc = {'bodies': bodies, 'n_tested': len(bodies), 'n_passed': len(rec), 'n_recovered': sum(b['recovered'] for b in bodies),
           'false_objects': sum(b['other_objects'] for b in bodies), 'max_distance_error_percent': max(errs) if errs else None,
           'thresholds': distant.thresholds(), 'ledger_ok': ok, 'ledger_problems': problems,
           'method': 'Fields were chosen from the JPL Horizons ephemeris. Detection, linking and the orbit fit used images, Gaia DR3 and '
                     'a WISE catalogue only. Each blind result was hashed into validation/ledger.jsonl before it was scored.'}
    (ROOT / 'validation' / 'distant_results.json').write_text(json.dumps(doc, indent=1))
    for b in bodies:
        m = b['match']
        log(f"{b['title']:9s} V {b['vmag']:.1f}  " + (f"recovered: {m['r_fit_au']:.2f} ± {m['r_err_au']:.2f} AU (JPL {m['r_true_au']:.2f}), pass {b['passed']}" if m
                                                      else 'not recovered: ' + b['diagnostic'].get('why_missed', '')))
    return doc


if __name__ == '__main__':
    build()
