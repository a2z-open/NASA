"""Write the distant-world, Planet Nine and Barnard's Star summaries into README.md, SUBMISSION.md, VALIDATION.md and
DEMO_SCRIPT.md, between marker comments, from the result files.  Safe to re-run: it replaces what is between the markers.

    python -m validation.fill_distant_docs
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def block(text: str, name: str, body: str) -> str:
    a, b = f'<!-- {name}:start -->', f'<!-- {name}:end -->'
    if a not in text:
        raise SystemExit(f'marker {name} missing')
    return re.sub(re.escape(a) + r'.*?' + re.escape(b), a + '\n' + body.strip('\n') + '\n' + b, text, flags=re.S)


def main() -> None:
    d = json.loads((ROOT / 'validation' / 'distant_results.json').read_text())
    p9 = json.loads((ROOT / 'validation' / 'planet_nine.json').read_text())
    bh = json.loads((ROOT / 'validation' / 'experiments' / 'barnards-star-halo' / 'result.json').read_text())
    van = json.loads((ROOT / 'validation' / 'vanished.json').read_text())
    ml = json.loads((ROOT / 'validation' / 'ml_realbogus.json').read_text())
    watch = json.loads((ROOT / 'data' / 'watch' / 'status.json').read_text())
    mk = json.loads((ROOT / 'validation' / 'forecasts' / 'makemake.json').read_text())
    mkj = json.loads((ROOT / 'validation' / 'forecasts' / 'makemake-vs-jpl.json').read_text())
    gone_objects = sorted({f.get('mover_track') or f['name'] for f in van['flagged']})
    gone = (f"Of {van['n_tested']:,} bright sources WISE saw around 2015 in our fields, the ones SPHEREx no longer sees at those spots are "
            f"{len(gone_objects)} known brown dwarfs ({', '.join(gone_objects)}): each one's SPHEREx motion, run back to the WISE years, passes through "
            f"the empty spot. {van['counts']['faded'] + van['counts']['vanished']} faded or vanished without an explanation.")
    win = mk['spherex_windows'][0] if mk.get('spherex_windows') else None
    jw = next((r for r in mkj['rows'] if r['in_spherex_window']), None)
    live = (f"A watcher checks NASA's archive for new SPHEREx images of every locked prediction (python -m pipeline.watch). "
            f"Makemake's next position is locked from the blind orbit alone; SPHEREx should next see it between {win['start_utc']} and {win['end_utc']}"
            + (f", and JPL's ephemeris, checked after locking, agrees to {jw['offset_from_jpl_arcsec']:.0f}″." if jw else '.') if win else '')
    mlt = (f"A machine-learning real/artefact model, trained on synthetic stars in real SPHEREx images and tested on the real detections of four dwarf planets it never saw, "
           f"ranks them with AUC {ml['mean_auc_real_body']:.2f}; signal-to-noise alone gives {ml['mean_auc_real_body_snr_only']:.2f}. "
           + ('It helps, a little.' if ml['mean_auc_real_body'] > ml['mean_auc_real_body_snr_only'] + 0.02 else 'It does not beat the simple rule yet, so it is not used in any result.'))
    found = [b for b in d['bodies'] if b['passed']]
    missed = [b for b in d['bodies'] if not b['passed']]
    names = ', '.join(f"{b['title']} ({b['match']['r_fit_au']:.2f} ± {b['match']['r_err_au']:.2f} AU; JPL {b['match']['r_true_au']:.2f})" for b in found)
    miss = '; '.join(f"{b['title']} ({b['diagnostic'].get('why_missed', 'not linked').rstrip('.').lower()})" for b in missed) + '.'
    s, inj = p9['search'], p9['injection']
    n_inj = sum(r['outcome'] == 'recovered' for r in inj['results'])
    worst = max(100 * b['match']['distance_error_fraction'] for b in found) if found else None
    worlds = (f"**{d['n_passed']} of {d['n_tested']} known distant worlds found blind and placed at the right distance**: {names}. "
              f"{d['false_objects']} false objects were linked." + (f" Missed: {miss}" if missed else '')
              + f" The largest distance error among those found is {'under 0.1' if worst is not None and worst < 0.1 else f'{worst:.1f}'} %.")
    nine = (f"The same search for a body at 200 to 20,000 AU in the {s['n_fields_three_visits']} fields with three or more visits "
            f"({s['area_deg2_three_visits']:.1f} square degrees): **no detection**. {len(s['candidates'])} geometric candidates were raised and both were rejected as "
            f"thousands of times too bright to be planets; one is a reflection of a saturated star that imitates parallax. Synthetic planets are recovered "
            f"down to {p9['faintest_synthetic_recovered_ujy']:.0f} µJy ({n_inj} of {len(inj['results'])}); the predicted Planet Nine is about {p9['nominal']['flux_ujy']:.0f} µJy, "
            f"so these images could not have found it.")
    barnard = (f"Its core is saturated, so we tracked the centre of its halo. In a visit that had been sealed, the halo had moved **{bh['measured_total_arcsec']:.2f}″ in "
               f"{bh['years_between']:.2f} years; Gaia says {bh['predicted_total_arcsec']:.2f}″** (they differ by {bh['difference_arcsec']:.2f}″; limit set in advance 1.5″). "
               f"{'PASS' if bh['passed'] else 'FAIL'}.")
    makemake = next((b for b in found if b['body'] == 'makemake'), found[0] if found else None)
    lead = (f"{makemake['title']}'s distance from SPHEREx images alone: {makemake['match']['r_fit_au']:.2f} AU. NASA's JPL says {makemake['match']['r_true_au']:.2f} AU"
            if makemake else 'a dwarf planet found by its parallax')

    p = ROOT / 'README.md'
    t = p.read_text()
    t = block(t, 'DISTANT_ROWS',
              f"| **Distant worlds, found by their parallax** | {worlds} Each blind result was hashed into a local lock record before JPL's positions were opened. "
              f"Makemake's spectrum along the fitted orbit shows the dips of methane ice, which is what its surface is known to be. |\n"
              f"| **Planet Nine** | {nine} |\n"
              f"| **Barnard's Star** | {barnard} |\n"
              f"| **What disappeared since WISE** | {gone} |\n"
              f"| **Waiting for the next images** | {live} |\n"
              f"| **Machine learning, tested honestly** | {mlt} |")
    p.write_text(t)

    p = ROOT / 'SUBMISSION.md'
    t = p.read_text()
    t = block(t, 'DISTANT_LIST',
              f"9. **Distant worlds by parallax (out of sample).** {worlds}\n"
              f"10. **Planet Nine mode.** {nine}\n"
              f"11. **Barnard's Star, on sealed images.** {barnard}\n"
              f"12. **What disappeared since WISE.** {gone}\n"
              f"13. **Live forecasts.** {live}\n"
              f"14. **Machine learning.** {mlt}")
    p.write_text(t)

    p = ROOT / 'VALIDATION.md'
    t = p.read_text()
    t = block(t, 'DISTANT_SECTION',
              "## 11. Distant worlds, Planet Nine mode and Barnard's Star (third session)\n\n"
              "Full tables: [docs/DISTANT_WORLDS.md](docs/DISTANT_WORLDS.md). Protocols: `validation/distant/PROTOCOL.md`, `validation/distant/PROTOCOL_P9.md`, "
              "`validation/experiments/barnards-star-halo/protocol.json`. Lock record: `validation/ledger.jsonl` (`python -m validation.ledger verify`).\n\n"
              f"- **Blind recovery of known distant worlds.** {worlds} The pass rule (within 12″ of JPL's track, distance within 5 %, no second object) was written first. "
              "These fields were never used to tune the search, so unlike the hunt in section 6 this score is out of sample.\n"
              f"- **Planet Nine mode.** {nine} The thresholds went through four locked versions in one day; versions 2 and 3 were driven by synthetic planets, and "
              "version 4 added a brightness rule after the two real candidates had been seen. That last rule is therefore not blind.\n"
              f"- **Barnard's Star.** {barnard} Gaia supplies the expected motion, so this tests the halo method. A visit in the opposite season is 1.7″ off in RA and was left out.\n"
              f"- **Shift-and-stack.** Eris was found only by adding exposures along trial paths. The way visits are joined went through three locked versions before it worked (`validation/distant/PROTOCOL_SHIFTSTACK.md`); none used JPL's positions, but the last was written after seeing which candidates fit.\n"
              f"- **What disappeared since WISE.** {gone} The rules that skip WISE artefacts and the glare of saturated stars were added after the first run (`validation/vanished.py`).\n"
              f"- **Live forecasts.** {live}\n"
              f"- **Machine learning.** {mlt} Results in `validation/ml_realbogus.json`.\n"
              "- **What this does not show.** It does not show that SPHEREx can find Planet Nine: the predicted planet is about 40 times fainter than the faintest "
              "synthetic planet recovered. It does not show discovery power for unknown worlds either: every field was chosen because a known body is in it.")
    p.write_text(t)

    p = ROOT / 'DEMO_SCRIPT.md'
    t = p.read_text()
    eris_b = next((b for b in found if b['body'] == 'eris'), None)
    t = block(t, 'DISTANT_PITCH',
              f"**2:35–3:20 Proof 2: the Planet X hunt.** Sky map first: \"This is the whole sky as NASA's SPHEREx sees it.\" Slide the colour bar. "
              f"Then the Hunt page. \"We let the search find dwarf planets on its own. {lead}.\" "
              + (f"\"Eris is too faint to see in any single image. Adding {eris_b['shiftstack']['n_exposures_stacked']} images along thousands of possible paths, "
                 f"it appeared: {eris_b['match']['r_fit_au']:.2f} AU. JPL says {eris_b['match']['r_true_au']:.2f}.\" " if eris_b and eris_b.get('shiftstack') else '')
              + f"\"That jump between visits is parallax, and it is where our name comes from.\" Then: \"We pointed the same search at Planet Nine. It found nothing, and "
              f"we can show you why: Planet Nine is about {round(p9['faintest_synthetic_recovered_ujy'] / p9['nominal']['flux_ujy'])} times fainter than these images can reach. "
              f"And we have locked where Makemake will be in January, before NASA takes the images.\"")
    p.write_text(t)
    print('README, SUBMISSION, VALIDATION and DEMO_SCRIPT updated')


if __name__ == '__main__':
    main()
