"""Write the cold-world spectra section of the documents from the result files, so the text cannot drift from the numbers.

    python -m validation.coldspec_md

Fills the block between <!-- COLDSPEC --> and <!-- /COLDSPEC --> in VALIDATION.md, and the one-line summary between
<!-- COLDSPEC_LINE --> and <!-- /COLDSPEC_LINE --> in README.md and RESULTS_LOG.md (a block is appended if missing).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation' / 'coldspec'


def _load(name):
    p = OUT / name
    return json.loads(p.read_text()) if p.is_file() else None


def section() -> tuple[str, str]:
    objs, ext, q, cv, proto, res, vet = (_load(n) for n in ('objects.json', 'extract.json', 'quality.json', 'cv.json', 'protocol.json', 'results.json', 'vetting.json'))
    c = objs['counts']
    known = sum(c[k]['kept'] for k in ('T', 'L', 'M_late', 'M_mid'))
    unknown = c['U_bd']['kept'] + c['U_pm']['kept']
    h, hf = cv['held_out'], cv['held_out_faint']
    L = []
    L.append('## 12. Cold-world spectra: reading spectral types from 102 colours (fourth session)\n')
    L.append('**Question.** SPHEREx measures every source in 102 infrared colours. Can a model read a spectral type from that alone, '
             'and does it flag anything among objects that have no spectral type?\n')
    L.append('**Data.** Spectra come from the SPHEREx DR1 all-sky data cube at IRSA (HEALPix tiles, 12.9″ pixels, 102 planes), read with HTTP byte '
             'ranges so that only an 11 × 11 pixel window per object is downloaded (`pipeline/cubespec.py`). Object lists and spectral types come from '
             f"SIMBAD ({objs['generated_utc'][:10]}). Positions in 2MASS and AllWISE (VizieR, CfA mirror) say where to look.\n")
    L.append('| Set | From SIMBAD | Kept |\n|---|---:|---:|')
    for k, name in (('T', 'Known T and Y dwarfs, J < 17.2'), ('L', 'Known L dwarfs, J < 16.5 (36 per subtype)'), ('M_late', 'Known M6 to M9 dwarfs, moving over 0.1″/yr (60 per subtype)'),
                    ('M_mid', 'Known M3 to M5 dwarfs, moving over 0.2″/yr (30 per subtype)'), ('U_bd', 'Brown-dwarf candidates with no spectral type'),
                    ('U_pm', 'Fast-moving red objects with no spectral type (over 0.2″/yr, J − K > 1)')):
        L.append(f"| {name} | {c[k]['from_simbad']:,} | {c[k]['kept']:,} |")
    L.append(f"\nKept means: brighter limit J > {objs['cuts']['J_min']:.0f} (SPHEREx saturates), more than {objs['cuts']['abs_gal_b_min']:.0f}° from the Galactic plane, "
             f"and a usable spectral type for the known sets. {known:,} known objects, {unknown:,} unclassified. "
             f"A spectrum was extracted for {ext['n_spectra']:,} of {ext['n_objects']:,}.\n")
    if q:
        L.append('**Is the photometry right?** Checked on known objects only, against catalogues the model never sees. '
                 f"SPHEREx's K/J flux ratio agrees with 2MASS's to {q['scatter_passing_cuts_dex']:.3f} dex (about {round((10 ** q['scatter_passing_cuts_dex'] - 1) * 100)} %) "
                 f"for the {q['n_passing']} objects that pass the quality cuts, and {q['scatter_all_dex']:.3f} dex before the cuts."
                 + (f" Its 4.6/3.4 µm ratio agrees with AllWISE's W2/W1 to {q['wise_check']['scatter_dex']:.3f} dex (median offset {q['wise_check']['median_dex']:+.3f} dex, {q['wise_check']['n']} objects)." if q.get('wise_check') else '')
                 + ' The cuts were placed where that agreement breaks down: '
                 f"source found within {q['cuts']['max_offset_pix']} pixel of where it was expected, no pixel brighter than {q['cuts']['max_near_rival']:.0f} × the source within 3.2 pixels, "
                 f"profile misfit under {q['cuts']['max_resid']}, J-band signal-to-noise of at least {q['cuts']['min_snr_J']:.0f}. "
                 'The absolute flux scale is not calibrated (at 1.28 µm it reads about 1.4 times the 2MASS J flux for M dwarfs); only the shape of each spectrum is used.\n')
    L.append(f"**Model.** Gradient-boosted trees on {len(cv['features'])} features that describe the shape of the spectrum only (22 normalised bands and 8 band differences); "
             'brightness is left out, and every training spectrum is also degraded to fainter levels, so that "faint" cannot stand in for "cold". '
             f"Five-fold cross-validation, split by object, on {cv['n_used']} known dwarfs ({cv['by_class']['M']} M, {cv['by_class']['L']} L, {cv['by_class']['T']} T).\n")
    L.append('| Held-out test | Type error (RMS, subtypes) | M | L | T | T dwarfs recognised | Warmer dwarfs called T |\n|---|---:|---:|---:|---:|---:|---:|')
    for name, d in (('As observed', h), ('Degraded to S/N 6 to 10', hf)):
        L.append(f"| {name} | {d['rms_subtypes']:.2f} | {d['rms_M']:.2f} | {d['rms_L']:.2f} | {d['rms_T']:.2f} | {d['T_found']} of {d['T_total']} | {d['false_T']} of {d['not_T_total']} |")
    L.append(f"\nA plain rule that uses only the depth of the 1.7 µm methane band separates T dwarfs with an AUC of {cv['baseline_methane_index_auc']:.3f}; the model reaches {h['auc_T']:.3f}. "
             'So most of the signal is the methane band itself; the model adds a little and gives a type.\n')
    if proto:
        L.append(f"**Lock.** Model, cuts, feature list and decision rule were written to `validation/coldspec/protocol.json` and hashed into the ledger on {proto['locked_utc'][:19]}Z, "
                 f"before any unclassified object was scored. Rule: {proto['rule']}\n")
    line = f"Cold-world spectra: the model reads types to ±{h['rms_subtypes']:.1f} subtypes and recognises {h['T_found']} of {h['T_total']} known T dwarfs with {h['false_T']} false alarms"
    if res:
        verdict = {c['name']: c for c in (vet['candidates'] if vet else [])}
        v_of = lambda x: verdict.get(x['name'], x)['verdict']                 # noqa: E731
        fresh = [x for x in res['candidates'] if v_of(x).startswith('new candidate')]
        known_c = [x for x in res['candidates'] if v_of(x).startswith('already')]
        doubt = [x for x in res['candidates'] if v_of(x).startswith('doubtful')]
        L.append(f"**Result.** Of {res['n_unclassified']:,} unclassified objects with a spectrum, {res['n_pass_quality']:,} pass the quality cuts. "
                 f"{res['n_outliers']} look unlike anything in the training set and get no answer. The model reads {res['typed_by_class'].get('M', 0)} as M, "
                 f"{res['typed_by_class'].get('L', 0)} as L and {res['typed_by_class'].get('T', 0)} as T. "
                 f"**{res['n_candidates']} meet the locked rule for a T-dwarf candidate.** The scores were hashed into the ledger before any vetting.\n")
        if res['candidates']:
            L.append('| Object (SIMBAD name) | Model type | P(T) | J-band S/N | W1 − W2 | Published type | Verdict |\n|---|---|---:|---:|---:|---|---|')
            for x in res['candidates']:
                w = x.get('wise') or {}
                pub = verdict.get(x['name'], {})
                L.append(f"| {x['name']} | {x['pred_type']} | {x['p_T']:.2f} | {x['snr_J']:.0f} | {w.get('W1_W2') if w.get('W1_W2') is not None else '—'} | "
                         f"{(pub.get('published_type') + ' (' + pub.get('published_name') + ')') if pub.get('published_type') else 'none found'} | {v_of(x)} |")
            L.append('')
        if vet:
            L.append(f"**Vetting against the literature (after the lock).** \"No spectral type in SIMBAD\" does not mean nobody has typed an object. {vet['source']}. "
                     f"{vet['n_with_published_type']} of the scored unclassified objects have a published type there. "
                     f"Of the {vet['published_T']} published T dwarfs among them, the model flagged {vet['published_T_flagged']}; of the {vet['published_not_T']} published warmer dwarf(s), it flagged {vet['published_not_T_flagged']}. "
                     f"Model type against published type: median error {vet['type_median_abs_subtypes']} subtypes, RMS {vet['type_rms_subtypes']} (the RMS is dominated by the one miss).\n")
            L.append('| Object | Published | Model | Flagged |\n|---|---|---|---|')
            for m in vet['matches']:
                L.append(f"| {m['name']} | {m['published_type']} | {m['model_type']} | {'yes' if m['flagged'] else 'no'} |")
            L.append('')
            miss = [m for m in vet['matches'] if m['published_num'] >= 20 and not m['flagged']]
            if miss:
                L.append(f"The miss, {miss[0]['name']}, was read as {miss[0]['model_type']}. Its SPHEREx signal is far stronger than its catalogue J magnitude allows, so the light is probably blended with a neighbour at 12.9″ per pixel. We count it as a miss.\n")
        L.append(f"**Conclusion: {len(fresh)} new candidate{'s' if len(fresh) != 1 else ''}.** "
                 + ('Every object the model flagged is a T dwarf that astronomers had already typed; SIMBAD simply does not carry the type. So this search found no new cold world. '
                    'What it gives instead is a blind test: the model had never been told what these objects are, and the truth was looked up only after its answers were locked. ' if not fresh and known_c else '')
                 + 'No claim of discovery is made, and nothing has been sent to anyone.\n')
        line += (f"; applied under a locked rule to {res['n_pass_quality']:,} unclassified objects, it flagged {res['n_candidates']}: "
                 f"{len(known_c)} are T dwarfs already typed in the literature (a blind test passed), {len(doubt)} doubtful, {len(fresh)} new candidate{'s' if len(fresh) != 1 else ''}."
                 + (f" It missed {vet['published_T'] - vet['published_T_flagged']} of {vet['published_T']} published T dwarfs hidden in the list." if vet else ''))
    else:
        line += '. The unclassified objects have not been scored yet.'
    wide = OUT / 'wide'
    if (wide / 'vetting.json').is_file():
        wl, wr, wv = (json.loads((wide / n).read_text()) for n in ('objects.json', 'results.json', 'vetting.json'))
        b = wv['blind_test']
        fresh = [f for f in wv['flagged'] if f['verdict'].startswith('no published spectrum')]
        L.append('### 12b. The wider search\n')
        L.append('The first search only covered objects that SIMBAD lists. The wider search takes objects that other surveys picked out from their colours alone '
                 '(photometric candidates, most never observed with a spectrograph) and fainter SIMBAD candidates. **The model, the cuts and the decision rule are the locked ones**: '
                 '`wide_apply` refuses to run unless `protocol.json` and `model.joblib` still match ledger entry `coldspec:protocol`. Nothing was refitted or retuned.\n')
        L.append('| Pool | Objects kept |\n|---|---:|')
        names = {'des_y6': 'DES Y6 ultracool candidates (Dal Ponte et al. 2023), photometric type L6 or later', 'des_y3': 'DES Y3 L and T candidates (Carnero Rosell et al. 2019), L6 or later, not already above',
                 'ukidss_T': 'UKIDSS photometric T dwarfs (Skrzypek et al. 2016)', 'ukidss_L': 'UKIDSS photometric L dwarfs, L6 or later (Skrzypek et al. 2016)',
                 'simbad_faint': 'SIMBAD brown-dwarf candidates with no spectral type, J 17.2 to 18.3'}
        for k, n in wl['counts'].items():
            L.append(f"| {names.get(k, k)} | {n:,} |")
        L.append(f"\nKept means: J between {wl['cuts']['J_min']:.0f} and {wl['cuts']['J_max']}, more than {wl['cuts']['abs_gal_b_min']:.0f}° from the Galactic plane, and not already scored in the first search. "
                 f"{len(wl['objects']):,} objects; a spectrum was extracted for {wr['n_objects']:,}; {wr['n_pass_quality']:,} pass the quality cuts; {wr['n_outliers']} are outliers and get no answer. "
                 f"**The model flagged {wr['n_flagged']}.** The scores were hashed into the ledger (`coldspec:wide-results`) before vetting.\n")
        L.append(f"**Vetting.** Each scored object was compared with published spectral types: {'; '.join(wv['references'])}. "
                 f"{b['n_with_published_type']} scored objects have a published type. Blind test on those: the model flagged {b['published_T_flagged']} of {b['published_T']} published T dwarfs "
                 f"and {b['published_not_T_flagged']} of {b['published_not_T']} published warmer dwarfs; median type error {b['type_median_abs_subtypes']} subtypes.\n")
        L.append(f"Of the {wr['n_flagged']} flagged: **{wv['n_already_typed']} already have a published type, {wv['n_doubtful']} are doubtful (WISE colour), "
                 f"and {wv['n_no_published_spectrum']} have no published spectrum that we could find.**\n")
        if wv['flagged']:
            L.append('| Object | Pool | J | Survey\'s photometric type | Model type | P(T) | J-band S/N | W1 − W2 | Published type | Verdict |\n|---|---|---:|---|---|---:|---:|---:|---|---|')
            for f in wv['flagged']:
                w = (f.get('wise') or {}).get('W1_W2')
                L.append(f"| {f['name']} | {f['group']} | {f['J']:.2f} | {f['phot_type'] or '—'} | {f['pred_type']} | {f['p_T']:.2f} | {f['snr_J']:.0f} | {w if w is not None else '—'} | "
                         f"{(f['published_type'] + ' (' + f['published_in'] + ')') if f['published_type'] else 'none found'} | {f['verdict']} |")
            L.append('')
        if (wide / 'candidates.json').is_file():
            wc = json.loads((wide / 'candidates.json').read_text())
            L.append(f"**Grading by methane depth (after vetting).** {wc['rule']} Limits from known dwarfs: 1.7 µm index below {wc['limits']['methane_1p7_warm_1st_percentile']}, "
                     f"3.3/4.5 µm index below {wc['limits']['methane_3p3_warm_1st_percentile']}. **{wc['n_strong']} of {wc['n']} are strong.** None of the {wc['n']} has any entry in SIMBAD within 15″.\n")
            L.append('| Object | Grade | Model type | 1.7 µm index | 3.3/4.5 µm index | J-band S/N | W1 − W2 |\n|---|---|---|---:|---:|---:|---:|')
            for c in wc['candidates']:
                L.append(f"| {c['name']} (RA {c['ra']:.5f}, Dec {c['dec']:+.5f}) | {c['grade']} | {c['pred_type']} | {c['methane_1p7']} | {c['methane_3p3']} | {c['snr_J']:.0f} | {(c['wise'] or {}).get('W1_W2', '—')} |")
            L.append('')
            L.append('**What this is.** ' + wc['what_it_is'] + '\n')
        L.append('**What the wider search does and does not show.** ' + wv['caveat'] + ' No claim has been sent to anyone.\n')
        line += (f" Wider search (same locked model, {wr['n_pass_quality']:,} more objects from DES, UKIDSS and SIMBAD): {wr['n_flagged']} flagged; {wv['n_already_typed']} already typed, "
                 f"{wv['n_doubtful']} doubtful, {len(fresh)} with no published spectrum found (candidates for a first spectroscopic type, not new objects).")
    L.append('**Reproduce.** `python -m validation.coldspec lists | positions | extract | quality | train | lock | apply`, then `python -m validation.coldspec_after vet | wide_lists | wide_positions | wide_extract | wide_apply | wide_vet | wide_grade | check`, then `python -m validation.coldspec_md`. '
             'Files: `validation/coldspec/` (`objects.json`, `positions.json`, `spectra.npz`, `quality.json`, `cv.json`, `protocol.json`, `model.joblib`, `results.json`, `vetting.json`, `check_queue.json`).')
    return '\n'.join(L), line


def _put(path: Path, tag: str, text: str, heading: str | None = None):
    s = path.read_text()
    block = f'<!-- {tag} -->\n{text}\n<!-- /{tag} -->'
    pat = re.compile(rf'<!-- {tag} -->.*?<!-- /{tag} -->', re.S)
    s = pat.sub(lambda m: block, s) if pat.search(s) else s.rstrip('\n') + '\n\n' + (heading + '\n\n' if heading else '') + block + '\n'
    path.write_text(s)


def main():
    text, line = section()
    _put(ROOT / 'VALIDATION.md', 'COLDSPEC', text)
    _put(ROOT / 'README.md', 'COLDSPEC_LINE', '- ' + line + ' See VALIDATION.md, section 12.', heading='## Cold-world spectra (fourth session)')
    _put(ROOT / 'RESULTS_LOG.md', 'COLDSPEC_LINE', '- ' + line, heading='## Cold-world spectra (14 Nov 2026)')
    print(line)


if __name__ == '__main__':
    main()
