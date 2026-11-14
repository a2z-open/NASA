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
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
           'question': 'Does the light almost vanish inside the two grey bands?',
           'reference': {'cold': shape(cold), 'warm': shape(warm)}, 'bands_um': [[1.63, 1.78], [3.10, 3.45]],
           'items': warmup + rest,
           'note': 'Spectra: SPHEREx DR1 all-sky cube. Known answers are spectral types from SIMBAD. A check is a human opinion on a real object; it does not confirm anything by itself.'}
    (OUT / 'check_queue.json').write_text(json.dumps(doc, indent=1))
    log(f"check queue: {len(doc['items'])} objects ({sum(1 for i in doc['items'] if i['kind'] == 'unknown')} with no known answer, "
        f"{sum(1 for i in doc['items'] if i.get('flagged'))} flagged by the model)")
    return doc


if __name__ == '__main__':
    {'vet': vet, 'check': check_queue}[sys.argv[1] if len(sys.argv) > 1 else 'vet']()
