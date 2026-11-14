"""Planet Nine mode: the distant-world search at 200 to 20,000 AU.

A planet hundreds of AU away barely moves during one SPHEREx visit, so it shows up as an ordinary point source
in that visit's stacked image.  Six months later the Earth is on the other side of the Sun and the planet has
jumped by 2 x 206265 / r arcseconds (14 arcminutes at 500 AU); six months after that it is back.  The search
therefore looks for sources that are present in ONE visit only, and asks whether three of them, one per visit,
lie on one bound orbit.

    python -m validation.planet_nine lock      # hash this file and the protocol into the ledger
    python -m validation.planet_nine search    # the 25 hunt fields (2.3 square degrees)
    python -m validation.planet_nine inject    # SYNTHETIC planets hidden in a blank field: what can be found?
    python -m validation.planet_nine report    # merge everything into validation/planet_nine.json

Honest scope: these fields were downloaded for other reasons, they cover a tiny area, and their depth is about
100 microjansky.  The nominal Planet Nine is about 7 microjansky.  This is a method test and a limit, not a
serious chance of discovery.
"""
from __future__ import annotations

import json
import math
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

from pipeline import distant, hunt
from pipeline.astrometry import JULIAN_YEAR_DAYS, parallax_factors
from pipeline.frames import display_wcs
from pipeline.measure import reference_candidates
from validation import ledger

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation' / 'distant'
RAD_ARCSEC = 206264.806

# ---- thresholds, locked in the ledger before the search was run ----
ORPHAN_SNR = 5.0                     # a single-visit source must reach this in its visit stack
R_LO, R_HI = 200.0, 20000.0          # AU
POS_TOL_ARCSEC = 6.0                 # slack on stack positions (one native pixel)
STACK_SIGMA_FLOOR = 2.0              # arcsec: a stack blurs a body that drifts during the visit (protocol v2)
FLUX_RATIO_MAX = 2.5                 # the same body cannot change brightness by more than this between visits
TRIPLE_CHI2R_MAX = 4.0               # one degree of freedom
MIRROR_RATIO_MIN = 9.0
BRIGHT_FACTOR = 10.0                 # a candidate this many times brighter than a Jupiter twin at its distance is not a planet (v4)

# ---- synthetic test ----
INJ_FIELD = 'control-uds'
INJ_R_AU = [500.0, 800.0, 1200.0, 2000.0]
INJ_FLUX_UJY = [150.0, 300.0, 600.0, 1200.0]     # flat in f_nu from 0.75 to 2.42 um (reflected sunlight)

# ---- reference numbers for the reach table (docs/PLANET_NINE_RESEARCH.md) ----
P9_V, P9_R_AU = 22.0, 550.0          # Brown, Holman & Batygin 2024: population not yet excluded
P9_V_RANGE = (20.6, 23.1)


def thresholds() -> dict:
    return {'orphan_snr': ORPHAN_SNR, 'r_lo_au': R_LO, 'r_hi_au': R_HI, 'pos_tol_arcsec': POS_TOL_ARCSEC,
            'flux_ratio_max': FLUX_RATIO_MAX, 'bright_factor': BRIGHT_FACTOR, 'stack_sigma_floor_arcsec': STACK_SIGMA_FLOOR, 'triple_chi2r_max': TRIPLE_CHI2R_MAX, 'mirror_ratio_min': MIRROR_RATIO_MIN}


def v_to_ujy(v: float) -> float:
    """V magnitude to microjansky near 1 um for a body with a flat (grey) albedo: the Sun is 0.25 mag brighter
    in AB at 1 um than in V."""
    return 3631e6 * 10 ** (-0.4 * (v - 0.25))


def mu_max_arcsec_yr(r_au: float) -> float:
    """Fastest sky motion of a body bound to the Sun at r AU, seen from the Sun."""
    return math.sqrt(2.0) * (2.0 * math.pi / math.sqrt(r_au)) / r_au * RAD_ARCSEC


# =====================================================================================
# linking single-visit sources
# =====================================================================================

def _xy(p, ra0, dec0):
    return (((p['ra'] - ra0 + 180) % 360) - 180) * math.cos(math.radians(dec0)) * 3600.0, (p['dec'] - dec0) * 3600.0


def pair_range(a: dict, b: dict, ra0: float, dec0: float, r_grid: np.ndarray) -> tuple[float, float] | None:
    """Distances r at which a (earlier visit) and b (later visit) could be the same bound body."""
    xa, ya = _xy(a, ra0, dec0)
    xb, yb = _xy(b, ra0, dec0)
    pa, pd = parallax_factors(ra0, dec0, [a['mjd'], b['mjd']])
    dpx, dpy = pa[1] - pa[0], pd[1] - pd[0]
    dt = abs(b['mjd'] - a['mjd']) / JULIAN_YEAR_DAYS
    plx = RAD_ARCSEC / r_grid
    miss = np.hypot(xb - xa - plx * dpx, yb - ya - plx * dpy)
    allowed = np.array([mu_max_arcsec_yr(r) for r in r_grid]) * dt + POS_TOL_ARCSEC + 3 * math.hypot(a['sigma_arcsec'], b['sigma_arcsec'])
    ok = miss <= allowed
    if not ok.any():
        return None
    return float(r_grid[ok].min()), float(r_grid[ok].max())


def _flux_ok(*ps) -> bool:
    f = [p['flux_ujy'] for p in ps if p.get('flux_ujy')]
    return len(f) < 2 or (min(f) > 0 and max(f) / min(f) <= FLUX_RATIO_MAX)


def search_points(points: list[dict], ra0: float, dec0: float) -> dict:
    """points: single-visit sources with keys visit, mjd, ra, dec, sigma_arcsec, flux_ujy, band, snr."""
    by_visit: dict[int, list[dict]] = {}
    for p in points:
        by_visit.setdefault(p['visit'], []).append(p)
    visits = sorted(by_visit)
    r_grid = np.geomspace(R_LO, R_HI, 90)
    pairs = []
    for va, vb in combinations(visits, 2):
        for a in by_visit[va]:
            for b in by_visit[vb]:
                if not _flux_ok(a, b):
                    continue
                rng = pair_range(a, b, ra0, dec0, r_grid)
                if rng:
                    pairs.append((a, b, rng))
    triples = []
    if len(visits) >= 3:
        seen = set()
        for a, b, _ in pairs:
            for vc in visits:
                if vc in (a['visit'], b['visit']):
                    continue
                for c in by_visit[vc]:
                    key = tuple(sorted((a['id'], b['id'], c['id'])))
                    if key in seen or not _flux_ok(a, b, c):
                        continue
                    # cheap gate: c must also pair with both a and b
                    lo, hi = (a, c) if a['mjd'] < c['mjd'] else (c, a)
                    lo2, hi2 = (b, c) if b['mjd'] < c['mjd'] else (c, b)
                    if pair_range(lo, hi, ra0, dec0, r_grid) is None or pair_range(lo2, hi2, ra0, dec0, r_grid) is None:
                        continue
                    seen.add(key)
                    trio = sorted((a, b, c), key=lambda p: p['mjd'])
                    orb = distant.fit_orbit(trio, fix_radial=True)
                    if not orb or orb['chi2r'] > TRIPLE_CHI2R_MAX or not orb['bound'] or not (R_LO <= orb['r_au'] <= R_HI):
                        continue
                    mir = distant.fit_orbit(trio, fix_radial=True, mirror=True)
                    ratio = (mir['chi2r'] / max(orb['chi2r'], 1e-3)) if mir else None
                    flux = float(np.median([p['flux_ujy'] for p in trio if p.get('flux_ujy')] or [0.0]))
                    jup = v_to_ujy(-2.7) * (5.2 / orb['r_au']) ** 4      # reflected light of a Jupiter twin at that distance
                    triples.append({'flux_ujy': flux, 'jupiter_twin_ujy': jup, 'too_bright_for_a_planet': bool(flux > BRIGHT_FACTOR * jup),
                                    'members': [p['id'] for p in trio], 'points': trio, 'r_au': orb['r_au'], 'r_err_au': orb['r_err_au'],
                                    'chi2r': orb['chi2r'], 'tangential_arcsec_yr': orb['tangential_arcsec_yr'],
                                    'inclination_deg': orb['inclination_deg'], 'mirror_ratio': ratio,
                                    'passes_mirror_test': bool(ratio is None or ratio >= MIRROR_RATIO_MIN)})
    return {'n_points': len(points), 'n_visits': len(visits), 'per_visit': {str(v): len(by_visit[v]) for v in visits},
            'n_pairs': len(pairs), 'triples': triples}


# =====================================================================================
# the 25 hunt fields
# =====================================================================================

def _band_of(detector: int) -> str:
    return next(b for b, dets in hunt.BANDS.items() if detector in dets)


def band_epochs(exposures: list[tuple[float, int]], visit_mids: list[float]) -> dict:
    """Median time of the exposures that went into each (visit, band) stack.  A stack's position belongs to THAT
    time, not to the middle of the visit: the two can differ by days, and a body at 500 AU drifts arcseconds a day."""
    acc: dict = {}
    for mjd, det in exposures:
        v = int(np.argmin([abs(mjd - m) for m in visit_mids]))
        acc.setdefault((v, _band_of(det)), []).append(mjd)
    return {k: float(np.median(t)) for k, t in acc.items()}      # median: one stray exposure must not move the date


def _orphans_from_hunt(doc: dict) -> list[dict]:
    mids = [v['mjd_mid'] for v in doc['visits']]
    vt = {v['id']: i for i, v in enumerate(doc['visits'])}
    epochs = band_epochs([(e['mjd'], e['detector']) for e in doc['exposures']], mids)
    out = []
    for s in doc['sources']:
        vd = s.get('visits_detected') or []
        if (s.get('stack_snr') or 0) < ORPHAN_SNR:
            continue
        # one visit only, or a chain of single-visit sources the hunt joined as a slow mover: each knot is a point
        if not (len(vd) == 1 or s.get('linked_orphans')):
            continue
        if any(f in (s.get('flags') or []) for f in ('near_saturated_star', 'beside_bright_source')):
            continue
        g = s.get('gaia') or {}
        if isinstance(g, dict) and g.get('sep_arcsec') is not None and g['sep_arcsec'] < 5.0:
            continue                                # a catalogued star that was too faint in the other visits
        band = s.get('best_band')
        knots = s.get('track') if s.get('linked_orphans') and s.get('track') else [{'visit': vd[0], 'ra': s['ra'], 'dec': s['dec']}]
        for n, kn in enumerate(knots):
            i = vt[kn['visit']]
            out.append({'id': f"{s['id']}.{n}", 'visit': i, 'mjd': epochs.get((i, band), mids[i]), 'ra': kn['ra'], 'dec': kn['dec'],
                        'snr': s['stack_snr'], 'band': band, 'flux_ujy': (s.get('flux_ujy') or {}).get(band),
                        'sigma_arcsec': math.hypot(1.2 * 8.8 / s['stack_snr'], STACK_SIGMA_FLOOR)})
    return out


def search(log=print) -> dict:
    fields, cands = [], []
    for path in sorted((ROOT / 'data' / 'hunt').glob('*/hunt.json')):
        doc = json.loads(path.read_text())
        pts = _orphans_from_hunt(doc)
        res = search_points(pts, doc['ra'], doc['dec'])
        fields.append({'field_id': doc['field_id'], 'title': doc['title'], 'area_deg2': doc['area_deg2'], 'n_visits': len(doc['visits']),
                       'n_single_visit_sources': res['n_points'], 'n_pairs': res['n_pairs'], 'n_triples': len(res['triples']),
                       'depth_5sigma_ujy': doc.get('depth_5sigma_ujy'), 'capped': doc.get('n_sources_before_cap', 0) > doc.get('n_sources', 0)})
        for t in res['triples']:
            cands.append({'field_id': doc['field_id']} | t)
        log(f"{doc['field_id']:16s} visits {len(doc['visits'])}  single-visit sources {res['n_points']:3d}  pairs {res['n_pairs']:4d}  triples {len(res['triples'])}")
    three = [f for f in fields if f['n_visits'] >= 3]
    depth = [f['depth_5sigma_ujy'].get('short') for f in three if (f['depth_5sigma_ujy'] or {}).get('short')]
    out = {'thresholds': thresholds(), 'fields': fields, 'candidates': cands,
           'area_deg2_three_visits': round(sum(f['area_deg2'] for f in three), 3), 'n_fields_three_visits': len(three),
           'median_depth_short_ujy': float(np.median(depth)) if depth else None,
           'accepted': [c for c in cands if c['passes_mirror_test'] and not c['too_bright_for_a_planet']]}
    (OUT / 'p9_search.json').write_text(json.dumps(out, indent=1))
    log(f"{len(three)} fields with 3+ visits ({out['area_deg2_three_visits']} deg2): {len(cands)} geometric triple(s), {len(out['accepted'])} left after the brightness check")
    return out


# =====================================================================================
# synthetic planets in a blank field
# =====================================================================================

def inject(log=print) -> dict:
    field = INJ_FIELD
    man = json.loads((hunt.HUNT_DATA / field / 'manifest.json').read_text())
    files = sorted((hunt.HUNT_CACHE / field / 'raw').glob('*.fits'))
    ra0, dec0, fov = man['ra'], man['dec'], float(man['fov_arcmin'])
    gaia = hunt.gaia_field(ra0, dec0, fov / 60 * 0.75, cache=hunt.HUNT_CACHE / field / 'gaia_field.json')
    refs = reference_candidates(gaia)
    cosd = math.cos(math.radians(dec0))
    truth = []
    rows = len(INJ_R_AU) * len(INJ_FLUX_UJY)
    k = 0
    for r in INJ_R_AU:
        mu = (2 * math.pi / math.sqrt(r)) / r * RAD_ARCSEC          # circular orbit, arcsec / yr
        for flux in INJ_FLUX_UJY:
            dy = (k - (rows - 1) / 2) * 0.72                         # arcmin north: one row per synthetic planet
            truth.append({'ra': ra0, 'dec': dec0 + dy / 60, 't0': 61000.0, 'pmra': mu * 0.94, 'pmdec': mu * 0.34, 'flux_ujy': flux,
                          'r_au': r, 'max_um': 2.42})
            k += 1
    log(f'{field}: {len(files)} exposures, {len(truth)} SYNTHETIC planets')
    items, visits, _ = hunt.build_stacks(files, ra0, dec0, fov, refs, workers=8, nz=16, log=log, injections=truth)
    per_visit = [hunt.detect_visit(v, i) for i, v in enumerate(visits)]
    objs = hunt.link(visits, per_visit)
    gw, _ = display_wcs(ra0, dec0, fov, hunt.GRID_ARCSEC)
    mids = [v['mjd_mid'] for v in visits]
    epochs = band_epochs([(i['mjd'], i['detector']) for i in items], mids)
    pts = []
    for n, o in enumerate(objs):
        if o['best_snr'] < ORPHAN_SNR or o['near_saturation'] or not (len(o['visits_detected']) == 1 or o['linked_orphans']):
            continue
        for m, (t, x, y) in enumerate(zip(o['knots_t'], o['knots_x'], o['knots_y'])):
            ra, dec = gw.pixel_to_world_values(x, y)
            v = int(np.argmin([abs(t - q) for q in mids])) if len(o['knots_t']) > 1 else int(o['visits_detected'][0])
            pts.append({'id': f'o{n}.{m}', 'visit': v, 'mjd': epochs.get((v, o['best_band']), mids[v]), 'ra': float(ra), 'dec': float(dec),
                        'snr': o['best_snr'], 'band': o['best_band'], 'flux_ujy': o['flux_ujy'].get(o['best_band']),
                        'sigma_arcsec': math.hypot(1.2 * 8.8 / o['best_snr'], STACK_SIGMA_FLOOR)})
    # drop single-visit sources that Gaia explains (as the hunt does)
    gra, gdec = np.array([s['ra'] for s in gaia]), np.array([s['dec'] for s in gaia])
    pts = [p for p in pts if not gaia or np.min(np.hypot((gra - p['ra']) * cosd, gdec - p['dec'])) * 3600 > 5.0]
    res = search_points(pts, ra0, dec0)

    def apparent(t, mjd):
        dt = (mjd - t['t0']) / JULIAN_YEAR_DAYS
        pa, pd = parallax_factors(t['ra'], t['dec'], [mjd])
        plx = RAD_ARCSEC / t['r_au']
        return (t['ra'] + (t['pmra'] * dt + plx * pa[0]) / 3600 / cosd, t['dec'] + (t['pmdec'] * dt + plx * pd[0]) / 3600)

    half = fov * 30 - 45
    results, matched = [], set()
    for t in truth:
        where = [apparent(t, epochs.get((i, 'short'), v['mjd_mid'])) for i, v in enumerate(visits)]
        inside = [abs((a - ra0) * cosd * 3600) < half and abs((d - dec0) * 3600) < half for a, d in where]
        seen = [any(p['visit'] == i and math.hypot((p['ra'] - a) * cosd, p['dec'] - d) * 3600 < 8 for p in pts) for i, (a, d) in enumerate(where)]
        hit = None
        for j, tr in enumerate(res['triples']):
            if all(any(p['visit'] == i and math.hypot((p['ra'] - a) * cosd, p['dec'] - d) * 3600 < 8 for p in tr['points']) for i, (a, d) in enumerate(where[:3])):
                hit = tr
                matched.add(j)
        outcome = ('outside_field' if not all(inside) else 'recovered' if hit and hit['passes_mirror_test'] and abs(hit['r_au'] - t['r_au']) / t['r_au'] <= 0.2
                   else 'wrong_distance' if hit else 'seen_not_linked' if all(seen) else 'too_faint')
        results.append({'r_au': t['r_au'], 'flux_ujy': t['flux_ujy'], 'outcome': outcome, 'visits_seen': int(sum(seen)),
                        'r_fit_au': hit['r_au'] if hit else None, 'r_err_au': hit['r_err_au'] if hit else None,
                        'chi2r': hit['chi2r'] if hit else None})
        log(f"  r {t['r_au']:6.0f} AU  flux {t['flux_ujy']:6.0f} uJy  ->  {outcome}" + (f"  (fit {hit['r_au']:.0f} AU)" if hit else f"  (seen in {sum(seen)}/{len(visits)} visits)"))
    false = [tr for j, tr in enumerate(res['triples']) if j not in matched and tr['passes_mirror_test']]
    out = {'synthetic': True, 'field': field, 'n_exposures': len(files), 'n_visits': len(visits), 'r_au': INJ_R_AU, 'fluxes_ujy': INJ_FLUX_UJY,
           'band': '0.75-2.42 um, flat spectrum', 'results': results, 'n_single_visit_sources': len(pts), 'n_pairs': res['n_pairs'],
           'false_triples': len(false), 'depth_5sigma_ujy': {b: float(np.nanmedian(5 * v['bands'][b]['err'] * v['bands'][b]['to_ujy']))
                                                              for v in visits[:1] for b in v['bands']},
           'note': 'SYNTHETIC planets built from each exposure\'s own ePSF and added to real images of a blank field. Never real.'}
    (OUT / 'p9_injection.json').write_text(json.dumps(out, indent=1))
    log(f"{sum(r['outcome'] == 'recovered' for r in results)} of {len(results)} recovered; {len(false)} false triple(s)")
    return out


# =====================================================================================
# report
# =====================================================================================

def reach(limit_ujy: float) -> list[dict]:
    """How far away each kind of world could be and still reach `limit_ujy` in reflected sunlight near 1 um.
    Reflected flux falls as 1 / r^4.  Reference brightnesses: see the note on each row."""
    rows = []
    for name, v_ref, r_ref, note in [
        ('Planet Nine, as predicted', P9_V, P9_R_AU, 'V 22.0 at 550 AU (Brown, Holman & Batygin 2024)'),
        ('Planet Nine, brightest allowed', P9_V_RANGE[0], P9_R_AU, 'V 20.6 at 550 AU, the bright end of the same prediction'),
        ('A twin of Neptune', 7.8, 30.1, 'Neptune is V 7.8 at 30 AU'),
        ('A twin of Jupiter', -2.7, 5.2, 'Jupiter is V -2.7 at 5.2 AU; WISE already rules this out to 82,000 AU (Luhman 2014)'),
    ]:
        f_ref = v_to_ujy(v_ref)
        rows.append({'world': name, 'reference': note, 'flux_at_550au_ujy': f_ref * (r_ref / 550.0) ** 4,
                     'max_distance_au': r_ref * (f_ref / limit_ujy) ** 0.25})
    return rows


def report(log=print) -> dict:
    s = json.loads((OUT / 'p9_search.json').read_text())
    inj = json.loads((OUT / 'p9_injection.json').read_text()) if (OUT / 'p9_injection.json').is_file() else None
    ok = [r for r in (inj['results'] if inj else []) if r['outcome'] == 'recovered']
    limit = min((r['flux_ujy'] for r in ok), default=None)
    doc = {'generated_from': ['validation/distant/p9_search.json', 'validation/distant/p9_injection.json'], 'search': s, 'injection': inj,
           'faintest_synthetic_recovered_ujy': limit, 'reach': reach(limit) if limit else None,
           'nominal': {'v': P9_V, 'r_au': P9_R_AU, 'flux_ujy': v_to_ujy(P9_V), 'v_range': list(P9_V_RANGE),
                       'flux_range_ujy': [v_to_ujy(P9_V_RANGE[1]), v_to_ujy(P9_V_RANGE[0])]},
           'statement': 'A method test and an upper limit on a very small area. Not a detection, and not a realistic chance of one.'}
    (ROOT / 'validation' / 'planet_nine.json').write_text(json.dumps(doc, indent=1))
    log(f"report written; faintest synthetic planet recovered: {limit} uJy; nominal Planet Nine: {v_to_ujy(P9_V):.1f} uJy")
    return doc


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'lock':
        e = ledger.append('planet-nine-protocol-v4', [Path(__file__), OUT / 'PROTOCOL_P9.md'], note='Version 4: brightness check added after two real triples were examined. See PROTOCOL_P9.md.')
        print(f'locked as ledger entry {e["seq"]} ({e["hash"][:12]})')
    else:
        {'search': search, 'inject': inject, 'report': report}[cmd]()
