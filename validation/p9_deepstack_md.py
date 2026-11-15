"""Write the Planet Nine deep-stack section of the documents from the result files.

    python -m validation.p9_deepstack_md

Fills <!-- P9DEEP --> ... <!-- /P9DEEP --> in VALIDATION.md and <!-- P9DEEP_LINE --> in README.md and RESULTS_LOG.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from validation.coldspec_md import _put

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'validation' / 'p9_deepstack'


def _ledger(label: str) -> int | None:
    from validation import ledger
    seqs = [e['seq'] for e in ledger.entries() if e['label'] == label]
    return seqs[-1] if seqs else None


def _depth50(inj):
    at = sorted([r for r in inj['results'] if r['distance_au'] == 550.0 and r['n_measured']], key=lambda r: r['flux_ujy'])
    ok = [r for r in at if r['n_recovered'] / r['n_measured'] >= 0.5]
    return ok[0]['flux_ujy'] if ok else None


def section() -> tuple[str, str]:
    p9 = json.loads((ROOT / 'validation' / 'planet_nine.json').read_text())['nominal']
    patches = []
    for f in sorted(BASE.glob('*/search.json')):
        d = json.loads(f.read_text())
        inj = json.loads(f.with_name('injection.json').read_text()) if f.with_name('injection.json').is_file() else None
        vet = json.loads(f.with_name('vet.json').read_text()) if f.with_name('vet.json').is_file() else None
        if vet and f.with_name('cross.json').is_file():
            cr = {(r['visit'], r['ra'], r['dec']): r for r in json.loads(f.with_name('cross.json').read_text())['candidates']}
            for c in vet['candidates']:
                c['cross'] = cr.get((c['visit'], c['ra'], c['dec']))
        fe = json.loads(f.with_name('fetch.json').read_text())
        patches.append((f.parent.name, d, inj, vet, fe))
    from validation import p9_deepstack as P          # the settings live in the locked code (hashed with each search)
    s0 = {'star_mask_ujy': P.STAR_UJY, 'hole_mask_sigma': P.HOLE_SIGMA, 'hole_mask_ujy': P.HOLE_UJY, 'clip_sigma': P.CLIP, 'motion_margin': P.MOTION_MARGIN}
    L = ['## 14. Planet Nine: adding up one visit along its parallax (fifth session)\n']
    L.append(f"**Why.** One SPHEREx photo reaches about {min(v['noise']['single_5sigma_ujy'] for _, d, *_ in patches for v in d['visits']):.0f} µJy "
             f"(5 sigma, 0.75–1.6 µm, in these patches). Planet Nine is predicted at {p9['flux_ujy']:.1f} µJy (V {p9['v']} at {p9['r_au']:.0f} AU; "
             f"Brown, Holman & Batygin 2024), and at most {p9['flux_range_ujy'][1]:.0f} µJy. Adding N photos lowers the noise by the square root of N, "
             'but only if each photo is shifted so that the planet lands on the same spot. Over one SPHEREx visit (one to four weeks) a body '
             '150–1500 AU away moves almost only because the Earth moves, so its path is set by its distance; its own orbital motion is '
             'allowed for along the predicted track.\n')
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    L.append('| Patch | RA, Dec | Galactic latitude | Photos (0.75–1.6 µm) | Visits |\n|---|---|---:|---:|---:|')
    for fid, d, inj, vet, fe in patches:
        b = SkyCoord(d['field']['ra'] * u.deg, d['field']['dec'] * u.deg).galactic.b.deg
        L.append(f"| {fid} | {d['field']['ra']}°, {d['field']['dec']}° | {b:.0f}° | {fe['n_downloaded']} | {len(fe['visits'])} |")
    L.append('')
    L.append('Both patches sit on the predicted Planet Nine track. p9-074+16 had the most photos in one visit of the track points checked, '
             'but lies near the Milky Way, where stars are crowded; p9-033-02 is far from it.')
    L.append('')
    L.append('**Method.** (1) Each photo is registered to Gaia and filtered with its own point-spread function at 3 × 3 sub-pixel offsets (the '
             'SPHEREx PSF is sharp and undersampled), then resampled to a common 4″ sky grid. (2) The fixed sky (stars, galaxies) is fitted at every '
             'grid pixel as a quadratic in wavelength from the OTHER visits only, months away, when a distant planet is somewhere else, so it '
             'cannot subtract itself. Each photo\'s flux scale and noise are measured against that template. (3) Masked: SPHEREx\'s own artifact '
             f"flags (CROSSTALK and GHOST widened by one pixel), sky brighter than {s0['star_mask_ujy']:.0f} µJy (with a 12″ border), dark holes in the "
             f"template ({s0['hole_mask_sigma']:g} sigma below the ring around them and {s0['hole_mask_ujy']:g} µJy below the field), and a disc around "
             f"every {s0['clip_sigma']:g}-sigma outlier in each photo. (4) The photos are added along the path of every trial distance from 150 to 1500 AU, "
             'spaced so that no photo\'s predicted position moves by more than half a pixel between trials. (5) The same is done twice more with '
             'motions no distant body can have: the parallax reversed, and the parallax turned by 90°. A peak is planet-like only if it beats both '
             f"at the same spot by {s0.get('motion_margin', 1.5)} in S/N; a still source scores the same in all three. The threshold is the highest "
             'planet-like peak of the two controls.\n')
    L.append('**How the method was set (before the locked runs).** It was developed on patch p9-074+16 looking only at the controls and at synthetic '
             'planets, never at the real search map. A Gaussian filter recovered about half the flux of synthetic planets; the sub-pixel PSF filter '
             'about 70%. Most false control peaks were dark crosstalk echoes in the August visits (flagged by SPHEREx as CROSSTALK): subtracting a '
             'dark spot leaves a bright one. Masking the flags, the dark holes and the outlier discs brought the control peaks above S/N 5 from 33 '
             'to a few. Patch p9-033-02 was then run with the method frozen.\n')
    L.append('| Patch | Visit | Photos searched | Area (deg²) | One photo, 5σ (µJy) | Threshold S/N | Planet-like candidates | Still changes |\n'
             '|---|---:|---:|---:|---:|---:|---:|---:|')
    for fid, d, *_ in patches:
        for v in d['visits']:
            L.append(f"| {fid} | {v['visit']} | {v['images']['n_target']} | {v['area_deg2']:.3f} | {v['noise']['single_5sigma_ujy']:.0f} | "
                     f"{v['threshold_snr']} | {len(v['candidates'])} | {len(v['still_changes'])} |")
    L.append('')
    locks = ', '.join(f"{fid}: entry {_ledger('p9:deepstack:search:' + fid)}" for fid, *_ in patches)
    L.append(f"Every candidate list was written and hashed into the ledger before any check ({locks}).\n")
    L.append('**Depth: synthetic planets (SYNTHETIC, never real).** Planets built from each photo\'s own PSF were added to every real photo, at the '
             'place their distance puts them, and the largest visit of each patch was searched again with exactly the same steps.\n')
    L.append('| Patch | Distance (AU) | Brightness (µJy) | Found / tried |\n|---|---:|---:|---:|')
    depths = {}
    for fid, d, inj, *_ in patches:
        if not inj:
            continue
        depths[fid] = _depth50(inj)
        for r in inj['results']:
            L.append(f"| {fid} | {r['distance_au']:.0f} | {r['flux_ujy']:g} | {r['n_recovered']} / {r['n_measured']} |")
    L.append('')
    best = min((v for v in depths.values() if v), default=None)
    if best:
        bp = next(d for fid, d, *_ in patches if depths.get(fid) == best)
        L.append(f"Half of the synthetic planets at 550 AU are found down to {best:g} µJy in the better patch: about {round(min(v['noise']['single_5sigma_ujy'] for v in bp['visits']) / best, 1)} "
                 f"times fainter than one photo reaches, and {best / p9['flux_ujy']:.0f} times brighter than the predicted Planet Nine.\n")
    cands = [(fid, c) for fid, _, _, vet, _ in patches for c in (vet['candidates'] if vet else [])]
    exp = sum(round(len(d['visits']) / 3, 2) for _, d, *_ in patches)
    n_c = sum(d['n_candidates'] for _, d, *_ in patches)
    L.append(f"**The candidates.** {n_c} planet-like peak(s) passed the locked rule. With no planet at all, the real search and its two controls "
             'are alike, so the real map\'s top peak beats both controls\' top peaks one time in three: the rule expects about '
             f"{exp:.1f} chance candidates in these {sum(len(d['visits']) for _, d, *_ in patches)} visits. After the lock, each candidate was "
             'checked: a real source shows in both halves of its visit and in both detectors, and does not rest on one photo.\n')
    if cands:
        L.append('| Patch | Visit | S/N | Margin | Best distance (AU) | First / second half | Detector 1 / 2 | Largest one-photo drop | Passes |\n'
                 '|---|---:|---:|---:|---:|---|---|---:|---|')
        for fid, c in cands:
            k = c['checks']
            ok = k['passes_split_tests'] and not k['rests_on_one_image']
            L.append(f"| {fid} | {c['visit']} | {c['snr']} | {c['margin_over_controls']} | {c['distance_au']:.0f} | {k['snr_first_half']} / {k['snr_second_half']} | "
                     f"{k['snr_detector_1']} / {k['snr_detector_2']} | {k['largest_drop_removing_one_image']} | {'yes' if ok else 'no'} |")
        L.append('')
        for fid, c in cands:
            x = c.get('cross')
            if not x:
                continue
            for o in x['other_visits']:
                if o.get('checkable'):
                    L.append(f"The {fid} visit-{c['visit']} candidate, looked for in visit {o['visit']} where its distance and speed put it: highest S/N "
                             f"there {o['max_snr_there']} ({o['unmasked_fraction']:.0%} of those places searchable); the same shape at {o['n_random_shapes']} "
                             f"random places gives as much {o['chance_of_as_much']:.0%} of the time. Verdict: {x['verdict']}.")
            L.append('')
        L.append('Visit 1 and visit 4 of p9-033-02 are one year apart, so the Earth was in nearly the same place and parallax cancels; only the '
                 'body\'s own motion along its orbit moves it, which keeps it inside the patch. The other visits put a body this close tens of '
                 'arcminutes away, outside these patches.\n')
        L.append('**Disclosed approximation.** The direction of a body\'s own orbital motion was taken from the predicted track between RA 60° '
                 'and 90° in both patches. Projected onto p9-033-02 (RA 33°), it differs from the local track direction by 0.5°, which changes '
                 'nothing measurable; it was noticed after the lock and is left as it was.\n')
    still = sum(len(d.get('still_changes', [])) for _, d, *_ in patches)
    L.append(f"**Still changes.** {still} still sources were brighter in one visit than in the others (S/N 7 or more). They are not planet "
             'candidates: a still source scores the same in all three searches. All of them sit next to masked bright stars.\n')
    area = sum(v['area_deg2'] for _, d, *_ in patches for v in d['visits']) / max(1, sum(len(d['visits']) for _, d, *_ in patches))
    L.append(f"**What this is and is not.** A method that reaches several times deeper than one photo, with its depth measured, its false alarms "
             f"counted by controls, and its candidates locked before checking. It covered about {area:.2f} deg² per visit in {len(patches)} patches, "
             'a tiny part of the region where Planet Nine is predicted, and its depth is still above the predicted brightness. It is not a '
             'search that could have found the predicted Planet Nine, and nothing found here is reported as a planet. Nothing has been sent to '
             'anyone.\n')
    L.append('**Reproduce.** `python -m validation.p9_deepstack fetch|stack|inject|vet|cross <patch>`, then `python -m validation.p9_deepstack_md`.')
    line = (f"Planet Nine deep stack: {len(patches)} patches on the predicted track, "
            f"{sum(fe['n_downloaded'] for *_, fe in patches)} photos; one visit added along parallax reaches "
            f"{best:g} µJy (synthetic planets, 50% found at 550 AU) against {p9['flux_ujy']:.1f} µJy predicted; " if best else
            f"Planet Nine deep stack: {len(patches)} patches on the predicted track; ")
    line += f"{n_c} planet-like candidate(s) against about {exp:.1f} expected by chance"
    passed = sum(1 for _, c in cands if c['checks']['passes_split_tests'] and not c['checks']['rests_on_one_image']
                 and not (c.get('cross') and c['cross']['verdict'].startswith('not seen')))
    line += f"; {passed} survive the checks (split halves, detectors, and the other visits)." if cands else '.'
    return '\n'.join(L), line


def main():
    text, line = section()
    _put(ROOT / 'VALIDATION.md', 'P9DEEP', text)
    _put(ROOT / 'README.md', 'P9DEEP_LINE', '- ' + line + ' See VALIDATION.md, section 14.', heading='## Planet Nine deep stack (fifth session)')
    _put(ROOT / 'RESULTS_LOG.md', 'P9DEEP_LINE', '- ' + line, heading='## Planet Nine deep stack (15 Nov 2026)')
    print(line)


if __name__ == '__main__':
    main()
