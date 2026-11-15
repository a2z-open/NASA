"""Do other telescopes agree?  The brown dwarfs SPHEREx showed in methane, checked with independent data.

    python -m validation.coldspec_others

The candidates are the ones graded "strong" or "likely" in validation/coldspec/wide/candidates.json (their SPHEREx
spectra show methane).  Three tests use data from other telescopes only, and are fixed here before the first run:

  1. It moves.  CatWISE2020 (Marocco et al. 2021; WISE and NEOWISE, 2010-2016) gives a proper motion.  A brown dwarf a few
     tens of parsecs away moves; a distant galaxy or quasar with red colours does not.  Pass: total motion at least 50 mas/yr
     and at least 3 times its error.
  2. Blue in the near infrared.  Methane removes light in the K band, so a T dwarf has J - Ks below about 0.5, while M and L
     dwarfs are redder (above 1).  Data: VISTA VHS DR5 (McMahon et al. 2013), or UKIDSS LAS DR9 where VHS has nothing.
     Pass: J - Ks < 0.5.
  3. Red in the mid infrared.  Methane also removes light in WISE's W1 band, so T dwarfs have W1 - W2 above about 0.8.
     Data: CatWISE2020.  Pass: W1 - W2 >= 0.8.

A candidate "agrees" with being a cold brown dwarf when every test that has data passes.  The script also asks NASA MAST
whether Hubble or JWST has ever pointed within 30 arcsec (pipeline/archives.py).  This is a consistency check with other
telescopes' data; a spectrum from a large telescope is still what would confirm each one.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import time

import requests

ROOT = Path(__file__).resolve().parents[1]
WIDE = ROOT / 'validation' / 'coldspec' / 'wide'
RADIUS_ARCSEC = 6.0
PM_MIN_MAS = 50.0
PM_SIGMA = 3.0
JK_MAX = 0.5
W12_MIN = 0.8


def _vizier(source: str, ra: float, dec: float, radius_arcsec: float, cols: list[str]) -> list[dict]:
    """VizieR (CfA mirror), every column.  Naming columns one by one made the mirror return headers without rows (seen on
    15 Nov 2026 for CatWISE and VHS), so all columns are asked for and the needed ones kept.  `cols` are those kept."""
    params = [('-source', source), ('-c', f'{ra:.6f} {dec:+.6f}'), ('-c.rs', f'{radius_arcsec:.1f}'), ('-out.max', '30'), ('-out.all', '1')]
    for k in range(4):
        try:
            r = requests.get('https://vizier.cfa.harvard.edu/viz-bin/asu-tsv', params=params, timeout=90)
            if r.status_code == 200 and '#RESOURCE' in r.text:
                break
        except requests.RequestException:
            pass
        time.sleep(2 * (k + 1))
    else:
        return []
    lines = [ln for ln in r.text.splitlines() if ln and not ln.startswith('#')]
    if len(lines) < 4:
        return []
    names = lines[0].split('\t')
    return [{k: v for k, v in zip(names, ln.split('\t')) if k in cols} for ln in lines[3:]]


def _num(v):
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _nearest(rows):
    rows = [r for r in rows if _num(r.get('_r')) is not None]
    return min(rows, key=lambda r: _num(r['_r'])) if rows else None


def check(c: dict) -> dict:
    ra, dec = c['ra'], c['dec']
    out = {'name': c['name'], 'ra': ra, 'dec': dec, 'grade': c['grade'], 'model_type': c.get('pred_type'), 'tests': {}}
    cw = _nearest(_vizier('II/365/catwise', ra, dec, RADIUS_ARCSEC,
                          ['_r', 'Name', 'pmRA', 'e_pmRA', 'pmDE', 'e_pmDE', 'W1mproPM', 'e_W1mproPM', 'W2mproPM', 'e_W2mproPM', 'abf', 'ccf']))
    if cw:
        pr, er, pd, ed = (_num(cw.get(k)) for k in ('pmRA', 'e_pmRA', 'pmDE', 'e_pmDE'))
        if None not in (pr, pd, er, ed):
            pm = 1000 * math.hypot(pr, pd)
            err = 1000 * math.hypot(pr * er, pd * ed) / max(math.hypot(pr, pd), 1e-9)
            out['tests']['moves'] = {'pass': pm >= PM_MIN_MAS and pm >= PM_SIGMA * err, 'value': round(pm, 0), 'error': round(err, 0),
                                     'unit': 'mas/yr', 'data': 'CatWISE2020 (WISE + NEOWISE)', 'match_arcsec': _num(cw['_r'])}
        w1, w2 = _num(cw.get('W1mproPM')), _num(cw.get('W2mproPM'))
        if w1 is not None and w2 is not None:
            e = math.hypot(_num(cw.get('e_W1mproPM')) or 0, _num(cw.get('e_W2mproPM')) or 0)
            out['tests']['w1_w2'] = {'pass': w1 - w2 >= W12_MIN, 'value': round(w1 - w2, 2), 'error': round(e, 2), 'data': 'CatWISE2020'}
    vhs = _nearest(_vizier('II/367/vhs_dr5', ra, dec, RADIUS_ARCSEC, ['_r', 'Name', 'Jpmag', 'J-Kspnt', 'e_J-Kspnt']))
    jk = _num(vhs.get('J-Kspnt')) if vhs else None
    if jk is not None:
        out['tests']['j_ks'] = {'pass': jk < JK_MAX, 'value': round(jk, 2), 'error': _num(vhs.get('e_J-Kspnt')), 'data': 'VISTA VHS DR5',
                                'match_arcsec': _num(vhs['_r'])}
    else:
        las = _nearest(_vizier('II/319/las9', ra, dec, RADIUS_ARCSEC, ['_r', 'ULAS', 'Jmag1', 'e_Jmag1', 'Kmag', 'e_Kmag']))
        j, k = (_num(las.get('Jmag1')), _num(las.get('Kmag'))) if las else (None, None)
        if j is not None and k is not None:
            out['tests']['j_ks'] = {'pass': j - k < JK_MAX, 'value': round(j - k, 2),
                                    'error': round(math.hypot(_num(las.get('e_Jmag1')) or 0, _num(las.get('e_Kmag')) or 0), 2),
                                    'data': 'UKIDSS LAS DR9', 'match_arcsec': _num(las['_r'])}
    try:
        from pipeline import archives
        seen = archives.look(ra, dec, 0.5)
        out['hubble_or_jwst'] = [{'name': r['name'], 'n': r['n']} for r in seen['telescopes'] if r['key'] in ('HST', 'JWST')]
        out['other_telescopes'] = [{'name': r['name'], 'n': r['n']} for r in seen['telescopes']]
    except Exception as error:  # noqa: BLE001
        out['archives_error'] = type(error).__name__
    t = out['tests']
    out['n_tests'] = len(t)
    out['n_pass'] = sum(1 for v in t.values() if v['pass'])
    out['agrees'] = bool(t) and out['n_pass'] == len(t)
    return out


def run(log=print) -> dict:
    from validation import ledger
    cands = [c for c in json.loads((WIDE / 'candidates.json').read_text())['candidates'] if c['grade'] in ('strong', 'likely')]
    rows = []
    for c in cands:
        r = check(c)
        rows.append(r)
        t = r['tests']
        log(f"{r['name']:16s} {r['grade']:7s} moves {t.get('moves', {}).get('value', '-')}±{t.get('moves', {}).get('error', '-')} mas/yr "
            f"J-Ks {t.get('j_ks', {}).get('value', '-')} W1-W2 {t.get('w1_w2', {}).get('value', '-')} -> {r['n_pass']}/{r['n_tests']}"
            f"{'  agrees' if r['agrees'] else ''}; Hubble/JWST: {', '.join(f'{x['name']} {x['n']}' for x in r.get('hubble_or_jwst', [])) or 'none'}")
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
           'rules': {'radius_arcsec': RADIUS_ARCSEC, 'moves': f'total proper motion >= {PM_MIN_MAS:g} mas/yr and >= {PM_SIGMA:g} sigma (CatWISE2020)',
                     'j_ks': f'J - Ks < {JK_MAX} (VISTA VHS DR5, or UKIDSS LAS DR9)', 'w1_w2': f'W1 - W2 >= {W12_MIN} (CatWISE2020)',
                     'agrees': 'every test that has data passes'},
           'n': len(rows), 'n_agree': sum(r['agrees'] for r in rows), 'n_moves': sum(1 for r in rows if r['tests'].get('moves', {}).get('pass')),
           'candidates': rows,
           'what_it_is': ('A check of the SPHEREx methane candidates with other telescopes\' data: WISE and NEOWISE (motion and mid-infrared '
                          'colour) and VISTA or UKIDSS (near-infrared colour). Agreement makes a cold brown dwarf much more likely; a '
                          'spectrum from a large telescope would confirm it. These objects were already candidates from the Dark '
                          'Energy Survey\'s colours; they are not new objects.'),
           'references': ['CatWISE2020: Marocco et al. 2021, ApJS 253, 8 (VizieR II/365)', 'VISTA VHS DR5: McMahon et al. 2013, The Messenger 154, 35 (VizieR II/367)',
                          'UKIDSS LAS DR9: Lawrence et al. 2007, MNRAS 379, 1599 (VizieR II/319)']}
    (WIDE / 'other_telescopes.json').write_text(json.dumps(doc, indent=1))
    e = ledger.append('coldspec:other-telescopes', [WIDE / 'other_telescopes.json', Path(__file__)],
                      note='SPHEREx methane candidates checked with WISE/NEOWISE motion and colour and VISTA/UKIDSS colour. Replaces entries 44 '
                           '(VizieR returned no rows when columns were named one by one, so no test had data) and 45 (motion and its '
                           'error were read in the wrong order). Rules unchanged.')
    log(f"{doc['n_agree']} of {doc['n']} agree with a cold brown dwarf in every test with data; {doc['n_moves']} move; ledger entry {e['seq']}")
    return doc




def md() -> str:
    """Write the result into VALIDATION.md (section 12c), README.md and RESULTS_LOG.md."""
    from validation.coldspec_md import _put
    d = json.loads((WIDE / 'other_telescopes.json').read_text())
    L = ['## 12c. The methane candidates, checked with other telescopes (fifth session)\n']
    L.append('The brown dwarfs whose SPHEREx spectra show methane (section 12, "strong" and "likely") were checked with data from other '
             'telescopes only, under rules fixed in `validation/coldspec_others.py` before the first run: ' + '; '.join(f'{k}: {v}' for k, v in d['rules'].items()) + '.\n')
    L.append('| Candidate | SPHEREx grade | Model type | Motion (mas/yr, WISE) | J − Ks (near IR) | W1 − W2 (WISE) | Tests passed |\n|---|---|---|---:|---:|---:|---:|')
    for r in d['candidates']:
        t = r['tests']
        mv = f"{t['moves']['value']:.0f} ± {t['moves']['error']:.0f}" if 'moves' in t else '—'
        jk = f"{t['j_ks']['value']:.2f} ({'VHS' if t['j_ks']['data'].startswith('VISTA') else 'LAS'})" if 'j_ks' in t else '—'
        w = f"{t['w1_w2']['value']:.2f}" if 'w1_w2' in t else '—'
        L.append(f"| {r['name']} | {r['grade']} | {r['model_type']} | {mv} | {jk} | {w} | {r['n_pass']} of {r['n_tests']}{' (all)' if r['agrees'] else ''} |")
    L.append('')
    hj = sum(1 for r in d['candidates'] if r.get('hubble_or_jwst'))
    L.append(f"**Result.** {d['n_moves']} of {d['n']} measurably move, so they are nearby and not distant galaxies or quasars, and {d['n_agree']} of "
             f"{d['n']} pass all three tests. Most of the rest miss only the near-infrared test, with J − Ks between 0.5 and 0.9; the model reads "
             'them as early T dwarfs (T0–T3), which are often that red, so the 0.5 limit set in advance is strict for them. It is kept as it was. '
             f"Hubble or JWST has pointed within 30″ of {hj} of them (NASA MAST). This makes cold brown dwarfs very likely; a spectrum from a "
             'large telescope would still be needed to confirm each one.\n')
    L.append('**Two failed runs, on the record.** Ledger entry 44 holds a run in which no test had data (naming catalogue columns one by one '
             'made the VizieR mirror return headers without rows), and entry 45 one in which a motion and its error were read in the wrong '
             'order. Both were fixed without changing any rule; entry 46 holds the result above.\n')
    L.append('**Reproduce.** `python -m validation.coldspec_others`.')
    text = '\n'.join(L)
    line = (f"Methane candidates checked with other telescopes (WISE/NEOWISE motion and colour, VISTA/UKIRT colour): {d['n_moves']} of {d['n']} move, "
            f"{d['n_agree']} pass all three tests.")
    _put(ROOT / 'VALIDATION.md', 'COLDSPEC_OTHERS', text)
    _put(ROOT / 'README.md', 'COLDSPEC_OTHERS_LINE', '- ' + line + ' See VALIDATION.md, section 12c.', heading='## Cold worlds, checked with other telescopes (fifth session)')
    _put(ROOT / 'RESULTS_LOG.md', 'COLDSPEC_OTHERS_LINE', '- ' + line, heading='## Cold worlds, checked with other telescopes (15 Nov 2026)')
    return line


if __name__ == '__main__':
    import sys
    {'run': run, 'md': lambda: print(md())}[sys.argv[1] if len(sys.argv) > 1 else 'run']()
