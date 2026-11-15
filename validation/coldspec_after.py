"""Cold-world spectra, after the lock: literature vetting and the queue of objects for people to check.

    python -m validation.coldspec_after vet      # 6. compare flagged and scored objects with published spectral types
    python -m validation.coldspec_after check    # 7. build the queue for the "Check a candidate" page

These steps were written after the scores were locked (ledger entries coldspec:protocol and coldspec:results), so they
live in their own file: validation/coldspec.py stays byte-identical to its locked copy.  Nothing here changes a score.
(validation/coldspec.py still contains an earlier `check_queue`; the one below replaces it.)
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import numpy as np
import requests

from validation.coldspec import EDGES, OUT, SEED, VIZIER, _band, _binned, _num, _sep, load, numeric_type


# ---------------------------------------------------------------------------
# Step 6: vetting against the literature.  "No spectral type in SIMBAD" does not mean nobody has typed the object.
# Best et al. 2020 (AJ 159, 257; VizieR J/AJ/159/257, table 1) lists spectral types for the L0-T8 dwarfs of the
# Hawaii Infrared Parallax Program.  It was consulted only AFTER the scores were locked into the ledger.
# ---------------------------------------------------------------------------

def vet(log=print) -> dict:
    from validation import ledger
    res = json.loads((OUT / 'results.json').read_text())
    ledger.locked('coldspec:results', OUT / 'results.json')
    path = OUT / 'best2020_table1.json'
    if path.is_file():
        table = json.loads(path.read_text())
    else:
        params = [('-source', 'J/AJ/159/257/table1'), ('-out.max', '9999')] + [('-out', c) for c in ('Name', 'SpT-op', 'SpT-ir', '_RA', '_DE')]
        r = requests.get(VIZIER, params=params, timeout=180)
        lines = [ln for ln in r.text.splitlines() if ln and not ln.startswith('#')]
        cols = lines[0].split('\t')
        table = [dict(zip(cols, (v.strip() for v in ln.split('\t')))) for ln in lines[3:]]
        path.write_text(json.dumps(table, indent=0))
    lit = [{'name': t['Name'], 'ra': _num(t['_RA']), 'dec': _num(t['_DE']), 'sp': (t.get('SpT-ir') or t.get('SpT-op') or '').strip()} for t in table]
    lit = [t for t in lit if t['ra'] is not None and t['sp']]
    located = json.loads((OUT / 'positions.json').read_text()) if (OUT / 'positions.json').is_file() else {}
    objs = {o['name']: o for o in json.loads((OUT / 'objects.json').read_text())['objects']}

    def published(name):
        o = objs[name]
        spots = [(o['ra'], o['dec'])] + [(v['ra'], v['dec']) for k in ('allwise', 'twomass') if (v := (located.get(o['oid']) or {}).get(k))]
        best = None
        for t in lit:
            d = min(_sep(t['ra'], t['dec'], ra, dec) for ra, dec in spots)
            if d <= 12 and (best is None or d < best[0]):
                best = (d, t)
        return best[1] if best else None

    flagged = {c['name'] for c in res['candidates']}
    rows = []
    for c in list(res['candidates']) + [t for t in res['typed'] if t['name'] not in flagged]:
        t = published(c['name'])
        if t:
            rows.append({'name': c['name'], 'published_name': t['name'], 'published_type': t['sp'], 'published_num': numeric_type(re.sub(r'\s*\(.*', '', t['sp'])),
                         'model_type': c['pred_type'], 'model_num': c.get('pred_type_num') or {'M': 0, 'L': 10, 'T': 20, 'Y': 30}[c['pred_type'][0]] + float(c['pred_type'][1:]),
                         'p_T': c['p_T'], 'flagged': c['name'] in flagged})
    ok = [r for r in rows if r['published_num'] is not None]
    err = np.array([r['model_num'] - r['published_num'] for r in ok])
    is_t = np.array([r['published_num'] >= 20 for r in ok])
    fl = np.array([r['flagged'] for r in ok])
    cands = []
    for c in res['candidates']:
        m = next((r for r in rows if r['name'] == c['name']), None)
        cands.append({'name': c['name'], 'model_type': c['pred_type'], 'p_T': c['p_T'], 'published_type': m['published_type'] if m else None,
                      'published_name': m['published_name'] if m else None,
                      'verdict': 'already typed in the literature' if m else c['verdict']})
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
           'source': 'Best et al. 2020, AJ 159, 257, table 1 (VizieR J/AJ/159/257), consulted after the scores were locked',
           'n_unclassified_scored': len(res['typed']) + sum(1 for c in res['candidates'] if c['name'] not in {t['name'] for t in res['typed']}),
           'n_with_published_type': len(ok), 'type_rms_subtypes': round(float(np.sqrt(np.mean(err ** 2))), 2) if len(ok) else None,
           'type_median_abs_subtypes': round(float(np.median(np.abs(err))), 2) if len(ok) else None,
           'published_T': int(is_t.sum()), 'published_T_flagged': int((is_t & fl).sum()), 'published_not_T': int((~is_t).sum()), 'published_not_T_flagged': int((~is_t & fl).sum()),
           'candidates': cands, 'n_new_candidates': sum(1 for c in cands if c['verdict'].startswith('new candidate')),
           'matches': sorted(ok, key=lambda r: -r['published_num']),
           'statement': ('Every object the model flagged turned out to have a published T-dwarf type that SIMBAD does not carry. No new candidate remains. '
                         'This is a blind test the model passed, not a discovery.') if all(c['verdict'].startswith('already') for c in cands) and cands else None}
    (OUT / 'vetting.json').write_text(json.dumps(doc, indent=1))
    ledger.append('coldspec:vetting', [OUT / 'vetting.json', path], note='Flagged and scored unclassified objects compared with published spectral types (Best et al. 2020).')
    log(f"published types found for {len(ok)} scored objects: model vs published RMS {doc['type_rms_subtypes']} subtypes; "
        f"published T dwarfs flagged {doc['published_T_flagged']}/{doc['published_T']}; published non-T flagged {doc['published_not_T_flagged']}/{doc['published_not_T']}; "
        f"new candidates left: {doc['n_new_candidates']}")
    for c in cands:
        log(f"  {c['name']:30s} model {c['model_type']:6s} published {c['published_type']} ({c['published_name']}) -> {c['verdict']}")
    return doc


# ---------------------------------------------------------------------------
# A queue of real objects for people to check by eye ("does the light vanish in the methane bands?").
# Known objects are mixed in so that a volunteer gets feedback; flagged and unclassified objects are the real task.
# ---------------------------------------------------------------------------

def check_queue(log=print) -> dict:
    res = json.loads((OUT / 'results.json').read_text())
    cv = json.loads((OUT / 'cv.json').read_text())
    rows, spec = load()
    by_oid = {o['oid']: o for o in rows}
    by_name = {o['name']: o for o in rows}
    rng = np.random.default_rng(SEED + 7)

    def spectrum_of(o):
        return _binned(spec['wave'], spec['flux'][o['i']].astype(float), spec['err'][o['i']].astype(float))

    def shape(objs):
        """Median spectrum of a group, each scaled to its own 1.0-2.4 micron mean."""
        stack = []
        for o in objs:
            f, e = spec['flux'][o['i']].astype(float), spec['err'][o['i']].astype(float)
            nir = _band(spec['wave'], f, e, 1.0, 2.4)[0]
            if nir and nir > 0:
                stack.append([_band(spec['wave'], f, e, a, b)[0] / nir for a, b in zip(EDGES[:-1], EDGES[1:])])
        med = np.nanmedian(np.array(stack), axis=0)
        return [{'um': round((a + b) / 2, 3), 'v': round(float(v), 3)} for a, b, v in zip(EDGES[:-1], EDGES[1:], med) if np.isfinite(v)]

    known = [o for o in rows if o['type_num'] is not None and o['pass']]
    cold = [o for o in known if 23 <= o['type_num'] < 30]                 # T3 and later: clear methane
    warm = [o for o in known if o['type_num'] < 16]                       # M and early L: none
    pcv = {p['name']: p for p in cv['points']}

    def short(sp):
        m = re.match(r'^[MLTY]\d(?:\.\d)?', (sp or '').strip())
        return m.group(0) if m else (sp or '').strip()

    def item(o, kind, truth=None, truth_label=None, model=None):
        return {'id': f"o{o['oid']}", 'kind': kind, 'name': o['name'], 'truth': truth, 'truth_label': truth_label, 'model': model,
                'snr': round(o['snr_J'], 1), 'ra': o['ra'], 'dec': o['dec'], 'spectrum': spectrum_of(o)}

    def pick(pool, n, lo=8.0, hi=60.0):
        pool = [o for o in pool if lo <= o['snr_J'] <= hi] or pool
        return [pool[i] for i in rng.permutation(len(pool))[:n]]

    def model_of(o):
        p = pcv.get(o['name'])
        return {'type': f"{'MLTY'[min(int(p['pred']) // 10, 3)]}{p['pred'] % 10:.1f}", 'p_T': p['p_T']} if p else None

    # two clear warm-ups, then everything else shuffled
    warmup = [item(o, 'known', 'dips', f"a type {short(o['sp_type'])} dwarf: a cold world with methane", model_of(o)) for o in pick(cold, 1, 20, 200)]
    warmup += [item(o, 'known', 'smooth', f"a type {short(o['sp_type'])} dwarf: warmer, with no methane", model_of(o)) for o in pick(warm, 1, 20, 200)]
    used = {w['id'] for w in warmup}
    vetting = json.loads((OUT / 'vetting.json').read_text()) if (OUT / 'vetting.json').is_file() else {'candidates': [], 'matches': []}
    pub = {c['name']: c['published_type'] for c in vetting['candidates'] if c.get('published_type')}
    in_literature = {m['name'] for m in vetting['matches']}
    rest = []
    for c in res['candidates']:                                               # every object the model flagged
        o = by_oid[c['oid']]
        typed = pub.get(c['name']) or (c['simbad_types'][0]['sptype'] if c['simbad_types'] else None)
        rest.append(item(o, 'known' if typed else 'unknown', ('dips' if typed and typed.strip().startswith(('T', 'Y')) else 'smooth') if typed else None,
                         f"a type {short(typed)} dwarf in the literature. Our model flagged it without being told" if typed else None, {'type': c['pred_type'], 'p_T': c['p_T']}))
        rest[-1]['flagged'] = True
    # the real task: objects nobody has typed.  The six the model found most methane-like but did not flag, then ten at random.
    typed_unknown = {t['name']: t for t in res['typed'] if t['name'] not in in_literature and t['name'] in by_name}
    taken = {r['id'] for r in rest}
    ranked = sorted(typed_unknown.values(), key=lambda t: -t['p_T'])
    chosen = [by_name[t['name']] for t in ranked[:6]]
    others = [by_name[n] for n in typed_unknown if by_name[n] not in chosen]
    for o in chosen + pick(others, 10):
        if f"o{o['oid']}" in taken:
            continue
        t = typed_unknown[o['name']]
        rest.append(item(o, 'unknown', None, None, {'type': t['pred_type'], 'p_T': t['p_T']}))
    for o in pick([o for o in cold if f"o{o['oid']}" not in used], 6):        # hidden known answers
        rest.append(item(o, 'known', 'dips', f"a type {short(o['sp_type'])} dwarf: a cold world with methane", model_of(o)))
    for o in pick([o for o in warm if f"o{o['oid']}" not in used], 6):
        rest.append(item(o, 'known', 'smooth', f"a type {short(o['sp_type'])} dwarf: warmer, with no methane", model_of(o)))
    rest = [rest[i] for i in rng.permutation(len(rest))]
    # the wider search: objects it flagged come first.  Those with no published spectrum are the most useful to check.
    wide_first = []
    if (OUT / 'wide' / 'vetting.json').is_file():
        for f in json.loads((OUT / 'wide' / 'vetting.json').read_text())['flagged']:
            pub = f['published_type']
            wide_first.append({'id': f['oid'], 'kind': 'known' if pub else 'unknown', 'name': f['name'],
                               'truth': ('dips' if pub.strip().startswith(('T', 'Y')) else 'smooth') if pub else None,
                               'truth_label': f"a type {short(pub)} dwarf in the literature. Our model flagged it without being told" if pub else None,
                               'model': {'type': f['pred_type'], 'p_T': f['p_T']}, 'snr': f['snr_J'], 'ra': f['ra'], 'dec': f['dec'], 'spectrum': f['spectrum'],
                               'flagged': True, 'first_spectrum': not pub})
        wide_first.sort(key=lambda it: it['kind'] != 'unknown')
    rest = wide_first[:14] + rest
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
           'question': 'Does the light almost vanish inside the two grey bands?',
           'reference': {'cold': shape(cold), 'warm': shape(warm)}, 'bands_um': [[1.63, 1.78], [3.10, 3.45]],
           'items': warmup + rest,
           'note': 'Spectra: SPHEREx DR1 all-sky cube. Known answers are spectral types from SIMBAD. A check is a human opinion on a real object; it does not confirm anything by itself.'}
    (OUT / 'check_queue.json').write_text(json.dumps(doc, indent=1))
    log(f"check queue: {len(doc['items'])} objects ({sum(1 for i in doc['items'] if i['kind'] == 'unknown')} with no known answer, "
        f"{sum(1 for i in doc['items'] if i.get('flagged'))} flagged by the model)")
    return doc



# ---------------------------------------------------------------------------
# The wider search.  The first search only covered objects that SIMBAD lists.  This one takes objects that other
# surveys picked out from their COLOURS alone (photometric candidates) and fainter SIMBAD candidates, and gives them
# a SPHEREx spectrum.  The model, the cuts and the decision rule are the locked ones (ledger entry coldspec:protocol):
# nothing is refitted or retuned here.
#
#   python -m validation.coldspec_after wide_lists | wide_positions | wide_extract | wide_apply | wide_vet
# ---------------------------------------------------------------------------

WIDE = OUT / 'wide'
J_FAINT = 18.3                  # fainter than this, the J-band peak of a T dwarf is below S/N 5 in the cube
SOURCES = {
    'des_y6': ('J/MNRAS/522/1951/table', ['CoadID', 'RAJ2000', 'DEJ2000', 'SPType', 'Jap3mag', 'Ksap3mag'], 'Dal Ponte et al. 2023 (DES Y6 ultracool candidates)'),
    'des_y3': ('J/MNRAS/489/5301/desy3-lt', ['ID', 'RAJ2000', 'DEJ2000', 'SpTypePh', 'Jap3', 'Ksap3'], 'Carnero Rosell et al. 2019 (DES Y3 L and T candidates)'),
    'ukidss_T': ('J/A+A/589/A49/table4', ['ULAS', 'Jmag', 'Kmag', 'PhType', 'SpType', '_RA', '_DE'], 'Skrzypek et al. 2016 (photometric T dwarfs)'),
    'ukidss_L': ('J/A+A/589/A49/table3', ['ULAS', 'Jmag', 'Kmag', 'PhType', 'SpType', '_RA', '_DE'], 'Skrzypek et al. 2016 (photometric L dwarfs)'),
}
PHOT_MIN = 16.0                 # photometric type L6 or later: where the methane dwarfs and the L/T transition are


def _table(source: str, cols: list[str], cache: str) -> list[dict]:
    path = WIDE / f'{cache}.json'
    if path.is_file():
        return json.loads(path.read_text())
    r = requests.get(VIZIER, params=[('-source', source), ('-out.max', '99999')] + [('-out', c) for c in cols], timeout=600)
    lines = [ln for ln in r.text.splitlines() if ln and not ln.startswith('#')]
    names = lines[0].split('\t')
    rows = [dict(zip(names, (v.strip() for v in ln.split('\t')))) for ln in lines[3:]]
    WIDE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows))
    return rows


def _phot_num(t: str) -> float | None:
    v = _num(t)
    if v is not None:
        return v                                         # the DES tables give the type as a number: 10 = L0, 20 = T0
    m = re.match(r'^([LT])(\d+(?:\.\d)?)', t or '')
    return ({'L': 10, 'T': 20}[m.group(1)] + float(m.group(2))) if m else None


def wide_lists(log=print) -> dict:
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    from validation.coldspec import B_MIN, J_MIN, tap
    pool = []
    for key, (source, cols, cite) in SOURCES.items():
        for r in _table(source, cols, key):
            ra, dec = _num(r.get('RAJ2000') or r.get('_RA')), _num(r.get('DEJ2000') or r.get('_DE'))
            j, k = _num(r.get('Jap3mag') or r.get('Jap3') or r.get('Jmag')), _num(r.get('Ksap3mag') or r.get('Ksap3') or r.get('Kmag'))
            pt = _phot_num(r.get('SPType') or r.get('SpTypePh') or r.get('PhType') or '')
            if ra is None or dec is None or j is None or pt is None or pt < PHOT_MIN or not (J_MIN < j < J_FAINT):
                continue
            name = ('DES ' + (r.get('CoadID') or r.get('ID'))) if key.startswith('des') else 'ULAS ' + r['ULAS']
            pool.append({'name': name, 'group': key, 'cite': cite, 'ra': ra, 'dec': dec, 'J': j, 'K': k, 'phot_type_num': pt,
                         'spec_type_in_source': (r.get('SpType') or '').strip() or None})
    q = ("SELECT b.oid, b.main_id, b.ra, b.dec, b.pmra, b.pmdec, f.J, f.K FROM basic AS b JOIN allfluxes AS f ON f.oidref = b.oid "
         f"WHERE b.otype = 'BD?' AND (b.sp_type IS NULL OR b.sp_type = '') AND f.J >= 17.2 AND f.J < {J_FAINT}")
    for r in tap(q):
        ra, dec, j = _num(r['ra']), _num(r['dec']), _num(r['J'])
        if ra is None or dec is None or j is None:
            continue
        pool.append({'name': r['main_id'].strip('"'), 'group': 'simbad_faint', 'cite': 'SIMBAD brown-dwarf candidate with no spectral type, J 17.2 to 18.3',
                     'ra': ra, 'dec': dec, 'J': j, 'K': _num(r['K']), 'phot_type_num': None, 'spec_type_in_source': None,
                     'pmra': _num(r['pmra']), 'pmdec': _num(r['pmdec'])})
    first = json.loads((OUT / 'objects.json').read_text())['objects']
    kept, counts = [], {}
    for o in pool:
        b = float(SkyCoord(o['ra'] * u.deg, o['dec'] * u.deg).galactic.b.deg)
        if abs(b) < B_MIN:
            continue
        near = lambda lst: any(abs(x['dec'] - o['dec']) < 0.002 and _sep(x['ra'], x['dec'], o['ra'], o['dec']) < 4 for x in lst)      # noqa: E731
        if near(kept) or near(first):
            continue                                        # already in this list, or already scored in the first search
        o.setdefault('pmra', None)
        o.setdefault('pmdec', None)
        o.update({'oid': f'w{len(kept):04d}', 'gal_b': round(b, 2), 'type_num': None, 'sp_type': None, 'otype': 'candidate'})
        kept.append(o)
        counts[o['group']] = counts.get(o['group'], 0) + 1
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'cuts': {'J_min': J_MIN, 'J_max': J_FAINT, 'abs_gal_b_min': B_MIN, 'phot_type_min': PHOT_MIN},
           'sources': {k: {'vizier': v[0], 'cite': v[2]} for k, v in SOURCES.items()}, 'counts': counts, 'objects': kept}
    WIDE.mkdir(parents=True, exist_ok=True)
    (WIDE / 'objects.json').write_text(json.dumps(doc, indent=1))
    log(f"wide list: {len(kept)} objects {counts}; {sum(1 for o in kept if o['spec_type_in_source'])} already have a spectroscopic type in their source table")
    return doc


def wide_positions(log=print, workers: int = 6) -> dict:
    from concurrent.futures import ThreadPoolExecutor
    from validation.coldspec import _locate
    objs = json.loads((WIDE / 'objects.json').read_text())['objects']
    path = WIDE / 'positions.json'
    have = json.loads(path.read_text()) if path.is_file() else {}

    def one(o):
        prev = have.get(o['oid'])
        if prev and 'error' not in prev and (prev.get('n_2mass') or prev.get('n_allwise')):
            return o['oid'], prev
        try:
            return o['oid'], _locate(o)
        except Exception as error:  # noqa: BLE001
            return o['oid'], {'error': f'{type(error).__name__}: {error}'[:100]}

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for oid, c in ex.map(one, objs):
            have[oid] = c
            done += 1
            if done % 200 == 0:
                path.write_text(json.dumps(have))
                log(f'{done}/{len(objs)} position lookups')
    path.write_text(json.dumps(have))
    log(f"AllWISE counterpart for {sum(1 for v in have.values() if 'allwise' in v)} of {len(objs)} objects")
    return {'n': len(objs)}


def wide_extract(log=print, workers: int = 5) -> dict:
    from concurrent.futures import ThreadPoolExecutor
    from pipeline import cubespec
    objs = json.loads((WIDE / 'objects.json').read_text())['objects']
    located = json.loads((WIDE / 'positions.json').read_text()) if (WIDE / 'positions.json').is_file() else {}

    def one(o):
        try:
            alts = []
            c = located.get(o['oid']) or {}
            if 'allwise' in c:
                alts.append((c['allwise']['ra'], c['allwise']['dec']))          # where it was in 2010.56
            if 'expected' in c:
                alts.append(tuple(c['expected']))                                # moved on to the cube's epoch, if a motion is known
            s = cubespec.spectrum(o['ra'], o['dec'], key=o['oid'], alternatives=alts or None)
            return o['oid'], {'ok': True, 's': s}
        except Exception as error:  # noqa: BLE001
            return o['oid'], {'ok': False, 'why': f'{type(error).__name__}: {error}'[:100]}

    res, done = {}, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for oid, r in ex.map(one, objs):
            res[oid] = r
            done += 1
            if done % 100 == 0:
                log(f"{done}/{len(objs)} spectra, {sum(1 for v in res.values() if v['ok'])} ok")
    ok = [o for o in objs if res[o['oid']]['ok']]
    g = lambda k: np.array([res[o['oid']]['s'][k] for o in ok], np.float32)          # noqa: E731
    np.savez_compressed(WIDE / 'spectra.npz', oid=np.array([o['oid'] for o in ok]), wave_um=cubespec.WAVES, flux_ujy=g('flux_ujy'), err_ujy=g('err_ujy'),
                        offset_pix=g('offset_pix'), near_rival=g('near_rival'), resid=g('resid'))
    fails = {}
    for v in res.values():
        if not v['ok']:
            fails[v['why'].split(':')[-1].strip()[:40]] = fails.get(v['why'].split(':')[-1].strip()[:40], 0) + 1
    summary = {'n_objects': len(objs), 'n_spectra': len(ok), 'failures': fails}
    (WIDE / 'extract.json').write_text(json.dumps(summary, indent=1))
    log(json.dumps(summary))
    return summary


def _wide_rows() -> tuple[list[dict], dict]:
    """The wide objects with features and the same pass/fail as the first search (validation.coldspec.load, for another list)."""
    from validation.coldspec import CUTS, features
    objs = {o['oid']: o for o in json.loads((WIDE / 'objects.json').read_text())['objects']}
    d = np.load(WIDE / 'spectra.npz')
    rows = []
    for i, oid in enumerate(d['oid']):
        o = dict(objs[str(oid)])
        f, e = d['flux_ujy'][i].astype(float), d['err_ujy'][i].astype(float)
        x, meta = features(d['wave_um'], f, e)
        o.update(meta)
        o['J_ratio'] = (meta['J_ujy'] / (1594e6 * 10 ** (-0.4 * o['J']))) if meta['J_ujy'] and o['J'] else None
        o.update({'i': i, 'x': x, 'offset_pix': float(d['offset_pix'][i]), 'near_rival': float(d['near_rival'][i]), 'resid': float(d['resid'][i])})
        o['pass'] = bool(o['valid_fraction'] >= CUTS['min_valid_fraction'] and o['offset_pix'] <= CUTS['max_offset_pix'] and o['snr_J'] >= CUTS['min_snr_J']
                         and o['near_rival'] <= CUTS['max_near_rival'] and o['resid'] <= CUTS['max_resid'] and np.isfinite(x).all()
                         and o['J_ratio'] is not None and CUTS['J_ratio_range'][0] <= o['J_ratio'] <= CUTS['J_ratio_range'][1])
        rows.append(o)
    return rows, {'wave': d['wave_um'], 'flux': d['flux_ujy'], 'err': d['err_ujy']}


def wide_apply(log=print) -> dict:
    import joblib
    from validation import ledger
    from validation.coldspec import _nn_distance
    ledger.locked('coldspec:protocol', OUT / 'protocol.json')
    ledger.locked('coldspec:protocol', OUT / 'model.joblib')            # the very model that was locked: not refitted
    thr = json.loads((OUT / 'protocol.json').read_text())['threshold_p_T']
    m = joblib.load(OUT / 'model.joblib')
    rows, spec = _wide_rows()
    ok = [o for o in rows if o['pass']]
    X = np.array([o['x'] for o in ok])
    lim = float(np.quantile(_nn_distance(m['train_X'], m['train_X'], leave_one_out=True), 0.99))
    pred, prob, dist = m['reg'].predict(X), m['clf'].predict_proba(X)[:, 1], _nn_distance(m['train_X'], X)
    located = json.loads((WIDE / 'positions.json').read_text()) if (WIDE / 'positions.json').is_file() else {}
    name_of = lambda t: f"{'MLTY'[min(int(max(t, 0)) // 10, 3)]}{max(t, 0) % 10:.1f}"          # noqa: E731
    scored = []
    for o, p, q, dd in zip(ok, pred, prob, dist):
        w = (located.get(o['oid']) or {}).get('allwise')
        scored.append({'oid': o['oid'], 'name': o['name'], 'group': o['group'], 'cite': o['cite'], 'ra': o['ra'], 'dec': o['dec'], 'J': o['J'],
                       'phot_type': name_of(o['phot_type_num']) if o['phot_type_num'] is not None else None, 'spec_type_in_source': o['spec_type_in_source'],
                       'snr_J': round(o['snr_J'], 1), 'pred_type_num': round(float(p), 2), 'pred_type': name_of(float(p)), 'p_T': round(float(q), 3),
                       'outlier': bool(dd > lim), 'flagged': bool(q >= thr and p >= 20 and dd <= lim),
                       'wise': {'W1': w['W1'], 'W2': w['W2'], 'W1_W2': round(w['W1'] - w['W2'], 2) if w['W1'] is not None and w['W2'] is not None else None} if w else None,
                       'spectrum': _binned(spec['wave'], spec['flux'][o['i']].astype(float), spec['err'][o['i']].astype(float))})
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'threshold_p_T': thr, 'n_objects': len(rows), 'n_pass_quality': len(ok),
           'n_outliers': int(sum(s['outlier'] for s in scored)), 'n_flagged': int(sum(s['flagged'] for s in scored)),
           'by_group': {g: {'passed': sum(1 for s in scored if s['group'] == g), 'flagged': sum(1 for s in scored if s['group'] == g and s['flagged'])} for g in sorted({s['group'] for s in scored})},
           'scored': scored}
    (WIDE / 'results.json').write_text(json.dumps(doc, indent=1))
    e = ledger.append('coldspec:wide-results', [WIDE / 'results.json', WIDE / 'objects.json', WIDE / 'spectra.npz'], note='Wider search scored with the locked model and rule, before vetting.')
    log(f"wide search: {len(rows)} spectra, {len(ok)} pass the quality cuts, {doc['n_outliers']} outliers, {doc['n_flagged']} flagged as T dwarfs; ledger entry {e['seq']}; by group {doc['by_group']}")
    return doc



# Published spectral types to vet against.  (VizieR table, name column, type columns in order of preference, citation)
REFERENCES = {
    'best2018': ('J/ApJS/234/1/dwarfs', 'Name', ['SpT', 'SpTnir', 'SpTopt'], 'Best et al. 2018, ApJS 234, 1'),
    'best2020': ('J/AJ/159/257/table1', 'Name', ['SpT-ir', 'SpT-op'], 'Best et al. 2020, AJ 159, 257'),
    'best2021': ('J/AJ/161/42/table1', 'Object', ['SpT-nir', 'SpT-opt'], 'Best et al. 2021, AJ 161, 42'),
    'kirkpatrick2021': ('J/ApJS/253/7/tablea1', 'Name', ['SpTIR', 'SpTO'], 'Kirkpatrick et al. 2021, ApJS 253, 7'),
}


def _references(log=print) -> list[dict]:
    out = []
    for key, (source, name_col, type_cols, cite) in REFERENCES.items():
        rows = _table(source, [name_col] + type_cols + ['_RA', '_DE'], f'ref_{key}')
        n = 0
        for r in rows:
            ra, dec = _num(r.get('_RA') or r.get('_RAJ2000')), _num(r.get('_DE') or r.get('_DEJ2000'))
            sp = next((r[c].strip() for c in type_cols if r.get(c, '').strip()), '')
            if ra is None or dec is None or not sp:
                continue
            v = _num(sp)
            if key == 'kirkpatrick2021' and v is not None:          # that table codes types as numbers: L0 = 0, T0 = 10, Y0 = 20
                sp = f"{'LTY'[min(int(v // 10), 2)]}{v % 10:g}"
            out.append({'ra': ra, 'dec': dec, 'name': r[name_col], 'sp': sp, 'cite': cite})
            n += 1
        log(f'  reference {key}: {n} typed objects')
    return out


def _simbad_near(ra: float, dec: float, radius_arcsec: float = 12.0) -> list[dict]:
    """Any object with a spectral type, in SIMBAD's main table or its measurement table, near this position."""
    from validation.coldspec import tap
    r = radius_arcsec / 3600
    found = []
    try:
        cone = f"CONTAINS(POINT('ICRS', b.ra, b.dec), CIRCLE('ICRS', {ra:.6f}, {dec:.6f}, {r:.6f})) = 1"
        for x in tap(f"SELECT b.main_id, b.sp_type, b.otype FROM basic AS b WHERE {cone}"):
            if x['sp_type'].strip('" '):
                found.append({'name': x['main_id'].strip('"'), 'sp': x['sp_type'].strip('"'), 'cite': 'SIMBAD'})
        for x in tap(f"SELECT b.main_id, m.sptype, m.bibcode FROM basic AS b JOIN mesSpT AS m ON m.oidref = b.oid WHERE {cone}"):
            found.append({'name': x['main_id'].strip('"'), 'sp': x['sptype'].strip('"'), 'cite': 'SIMBAD measurements, ' + x['bibcode'].strip('"')})
    except Exception as error:  # noqa: BLE001
        found.append({'name': '', 'sp': '', 'cite': f'SIMBAD lookup failed: {type(error).__name__}'})
    return found


def wide_vet(log=print) -> dict:
    from validation import ledger
    ledger.locked('coldspec:wide-results', WIDE / 'results.json')
    res = json.loads((WIDE / 'results.json').read_text())
    located = json.loads((WIDE / 'positions.json').read_text()) if (WIDE / 'positions.json').is_file() else {}
    refs = _references(log)

    def published(s):
        spots = [(s['ra'], s['dec'])]
        w = (located.get(s['oid']) or {}).get('allwise')
        if w:
            spots.append((w['ra'], w['dec']))
        hits = []
        for t in refs:
            if abs(t['dec'] - s['dec']) > 0.01:
                continue
            d = min(_sep(t['ra'], t['dec'], ra, dec) for ra, dec in spots)
            if d <= 12:
                hits.append((d, t))
        return [t for _, t in sorted(hits, key=lambda h: h[0])]

    clean = lambda sp: numeric_type(re.sub(r'[\s(\[].*', '', sp.replace(':', '')))          # noqa: E731
    rows, flagged = [], []
    for s in res['scored']:
        lit = published(s)
        if s['spec_type_in_source']:
            lit.insert(0, {'name': s['name'], 'sp': s['spec_type_in_source'], 'cite': 'spectroscopic type quoted in its source table'})
        if s['flagged'] and not lit:
            lit = [h for h in _simbad_near(s['ra'], s['dec']) if h['sp']]                      # a last look, for flagged objects only
        pub = next((h for h in lit if clean(h['sp']) is not None), None)
        if pub:
            rows.append({'name': s['name'], 'group': s['group'], 'published_type': pub['sp'], 'published_num': clean(pub['sp']), 'published_in': pub['cite'],
                         'published_name': pub['name'], 'model_type': s['pred_type'], 'model_num': s['pred_type_num'], 'p_T': s['p_T'], 'flagged': s['flagged'], 'outlier': s['outlier']})
        if s['flagged']:
            w = (s.get('wise') or {}).get('W1_W2')
            verdict = ('already typed in the literature' if pub else
                       'no published spectrum found; WISE colour agrees' if w is not None and w >= 0.5 else
                       'no published spectrum found; no WISE colour' if w is None else
                       'doubtful: WISE colour is not that of a T dwarf')
            flagged.append({**{k: s[k] for k in ('oid', 'name', 'group', 'cite', 'ra', 'dec', 'J', 'phot_type', 'snr_J', 'pred_type', 'p_T', 'wise', 'spectrum')},
                            'published_type': pub['sp'] if pub else None, 'published_in': pub['cite'] if pub else None, 'published_name': pub['name'] if pub else None,
                            'verdict': verdict})
    use = [r for r in rows if not r['outlier']]
    err = np.array([r['model_num'] - r['published_num'] for r in use]) if use else np.array([])
    is_t = np.array([r['published_num'] >= 20 for r in use], bool)
    fl = np.array([r['flagged'] for r in use], bool)
    fresh = [f for f in flagged if f['verdict'].startswith('no published spectrum')]
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
           'references': [v[3] for v in REFERENCES.values()] + ['spectroscopic types quoted in the candidate tables', 'SIMBAD main and measurement tables within 12 arcsec (flagged objects)'],
           'n_scored': res['n_pass_quality'], 'n_flagged': len(flagged),
           'blind_test': {'n_with_published_type': len(use), 'type_median_abs_subtypes': round(float(np.median(np.abs(err))), 2) if len(use) else None,
                          'type_rms_subtypes': round(float(np.sqrt(np.mean(err ** 2))), 2) if len(use) else None,
                          'published_T': int(is_t.sum()), 'published_T_flagged': int((is_t & fl).sum()),
                          'published_not_T': int((~is_t).sum()), 'published_not_T_flagged': int((~is_t & fl).sum())},
           'flagged': sorted(flagged, key=lambda f: (not f['verdict'].startswith('no published'), -f['p_T'])),
           'n_already_typed': sum(1 for f in flagged if f['verdict'].startswith('already')), 'n_doubtful': sum(1 for f in flagged if f['verdict'].startswith('doubtful')),
           'n_no_published_spectrum': len(fresh),
           'matches': sorted(use, key=lambda r: -r['published_num']),
           'caveat': ('"No published spectrum found" means: none in the four compilations listed, none quoted by the candidate\'s own source table, and none in SIMBAD within 12 arcsec. '
                      'It does not prove that no spectrum exists. These objects were already picked out by other surveys from their colours; what SPHEREx adds is a spectrum that shows methane. '
                      'They are candidates for a first spectroscopic type, not new discoveries of objects.')}
    (WIDE / 'vetting.json').write_text(json.dumps(doc, indent=1))
    ledger.append('coldspec:wide-vetting', [WIDE / 'vetting.json'], note='Wider search: flagged objects compared with published spectral types.')
    b = doc['blind_test']
    log(f"wide vetting: {len(flagged)} flagged; {doc['n_already_typed']} already typed, {doc['n_doubtful']} doubtful, {len(fresh)} with no published spectrum found")
    log(f"blind test on {b['n_with_published_type']} scored objects with published types: median error {b['type_median_abs_subtypes']} subtypes; "
        f"published T flagged {b['published_T_flagged']}/{b['published_T']}; published non-T flagged {b['published_not_T_flagged']}/{b['published_not_T']}")
    for f in doc['flagged']:
        log(f"  {f['name']:28s} {f['group']:12s} J {f['J']:.2f} phot {f['phot_type']} | model {f['pred_type']} P {f['p_T']:.2f} S/N {f['snr_J']:.0f} | W1-W2 {(f['wise'] or {}).get('W1_W2')} | "
            f"published {f['published_type']} ({f['published_in']}) -> {f['verdict']}")
    return doc



def wide_grade(log=print) -> dict:
    """Grade the wide-search objects that have no published spectrum, by the depth of the two methane bands compared with
    known dwarfs, and record the SIMBAD check.  Writes wide/candidates.json; the locked files are not touched."""
    from validation import ledger
    from validation.coldspec import FEATURES, load
    ledger.locked('coldspec:wide-vetting', WIDE / 'vetting.json')
    v = json.loads((WIDE / 'vetting.json').read_text())
    i1, i2 = FEATURES.index('ch4_H'), FEATURES.index('f33_over_f45')
    rows, _ = load()
    known = [o for o in rows if o['type_num'] is not None and o['pass']]
    warm = [o for o in known if o['type_num'] < 20]
    lim1 = float(np.percentile([o['x'][i1] for o in warm], 1))          # the deepest 1.7 um "dip" among 1 % of M and L dwarfs
    lim2 = float(np.percentile([o['x'][i2] for o in warm], 1))
    wrows, _ = _wide_rows()
    by = {o['oid']: o for o in wrows}
    simbad = json.loads((WIDE / 'simbad_check.json').read_text()) if (WIDE / 'simbad_check.json').is_file() else {}
    out = []
    for f in v['flagged']:
        if not f['verdict'].startswith('no published'):
            continue
        o = by[f['oid']]
        m1, m2 = float(o['x'][i1]), float(o['x'][i2])
        grade = 'strong' if (m1 < lim1 and m2 < lim2) else 'likely'
        out.append({**{k: f[k] for k in ('oid', 'name', 'group', 'cite', 'ra', 'dec', 'J', 'phot_type', 'snr_J', 'pred_type', 'p_T', 'wise', 'spectrum')},
                    'methane_1p7': round(m1, 2), 'methane_3p3': round(m2, 2), 'grade': grade, 'in_simbad': bool(simbad.get(f['name']))})
    out.sort(key=lambda c: (c['grade'] != 'strong', c['methane_1p7']))
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
           'limits': {'methane_1p7_warm_1st_percentile': round(lim1, 2), 'methane_3p3_warm_1st_percentile': round(lim2, 2)},
           'rule': ('strong: both methane indices deeper than 99 % of known M and L dwarfs; likely: flagged by the locked model but not past both limits. '
                    'Indices are band differences of the normalised spectrum (pipeline: validation.coldspec.features).'),
           'n': len(out), 'n_strong': sum(1 for c in out if c['grade'] == 'strong'), 'candidates': out,
           'what_it_is': ('Objects that the Dark Energy Survey listed as T-dwarf candidates from colours alone (Dal Ponte et al. 2023; Carnero Rosell et al. 2019). '
                          'We found no published spectrum of them in four compilations, in their source tables or in SIMBAD (where they have no entry at all). '
                          'Their SPHEREx spectra show methane absorption. This is a first spectroscopic confirmation of their nature at SPHEREx resolution, '
                          'not the discovery of new objects, and it should be checked with a proper spectrum before it is published.')}
    (WIDE / 'candidates.json').write_text(json.dumps(doc, indent=1))
    ledger.append('coldspec:wide-candidates', [WIDE / 'candidates.json', WIDE / 'simbad_check.json'], note='Wide-search objects with no published spectrum, graded by methane depth.')
    log(f"{len(out)} objects with no published spectrum: {doc['n_strong']} strong (both methane bands deeper than 99 % of warm dwarfs: {lim1:.2f}, {lim2:.2f})")
    return doc

if __name__ == '__main__':
    {'vet': vet, 'check': check_queue, 'wide_lists': wide_lists, 'wide_positions': wide_positions, 'wide_extract': wide_extract,
     'wide_apply': wide_apply, 'wide_vet': wide_vet, 'wide_grade': wide_grade}[sys.argv[1] if len(sys.argv) > 1 else 'vet']()
