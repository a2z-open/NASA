"""Write the asteroid-hunt section of the documents from the result files.

    python -m validation.asteroids_md

Fills <!-- ASTEROIDS --> ... <!-- /ASTEROIDS --> in VALIDATION.md and <!-- ASTEROIDS_LINE --> in README.md and RESULTS_LOG.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from validation.coldspec_md import _put

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation' / 'asteroids'


def section() -> tuple[str, str]:
    plan = json.loads((OUT / 'plan.json').read_text())
    tracks = json.loads((OUT / 'tracks.json').read_text())
    res = json.loads((OUT / 'results.json').read_text()) if (OUT / 'results.json').is_file() else None
    st = tracks['settings']
    L = ['## 13. Asteroid hunt: things that move from night to night (fourth session)\n']
    L.append('**Method.** Patches of sky near the ecliptic (the path of the planets), away from the Milky Way, that SPHEREx imaged on several epochs within '
             'one week. In each epoch SPHEREx takes two images about 2 minutes apart. A dot counts only if it is in both images of an epoch '
             f"(within {st['same_night_arcsec']}″), which removes cosmic rays and noise. A dot that is also present at the same place on two or more other "
             'epochs is a fixed star or galaxy and is removed, so no catalogue is used to remove anything. What is left is joined into straight lines over '
             f"{st['track_nights']} or more epochs (speed {st['rate_arcsec_h'][0]:g} to {st['rate_arcsec_h'][1]:g}″ per hour, within {st['track_tol_arcsec']}″, "
             f"fit scatter under {st['track_rms_max']}″, brightness steady within a factor {st['flux_ratio_max']:g}).\n")
    L.append(f"**Blind, then checked.** The tracks were written to `validation/asteroids/tracks.json` and hashed into the ledger before any asteroid catalogue was "
             'consulted. Only then was IMCCE SkyBoT (Berthier et al. 2006) asked which known asteroids were in each patch at each epoch.\n')
    L.append('**Chance control.** Each patch was also linked ' + str(tracks.get('control', '')).split(' times')[0].split('linked ')[-1] +
             ' times after rotating each epoch\'s dots by a random angle about the patch centre. Real movers no longer line up; the density of dots stays the same.\n')
    L.append('| Patch | Ecliptic longitude | Epochs | Dots in both images | Fixed, removed | Left | Tracks | Chance tracks per run |\n|---|---:|---:|---:|---:|---:|---:|---:|')
    for f in plan['fields']:
        s = tracks['summary'].get(f['id'], {})
        L.append(f"| {f['id']} | {f['ecl_lon']:.0f}° | {s.get('epochs', '—')} | {s.get('paired_detections', '—')} | {s.get('fixed_sources_removed', '—')} | "
                 f"{s.get('night_detections', '—')} | {s.get('tracks', '—')} | {s.get('chance_tracks_per_run', '—')} |")
    L.append('')
    line = f"Asteroid hunt: {len(tracks['tracks'])} moving-object tracks from SPHEREx alone in {len(plan['fields'])} patches near the ecliptic"
    if res:
        L.append(f"**Result.** {res['n_tracks']} tracks. **{res['n_tracks_known']} are known asteroids**, recovered blind. "
                 f"{res['n_tracks_unmatched']} match no known asteroid ({res['n_unmatched_4plus']} on 4+ epochs); chance alone is expected to give "
                 f"{res['chance_tracks_expected']} tracks in total.\n")
        L.append('| Known asteroids in view on 4+ epochs, by V | In view | Found blind |\n|---|---:|---:|')
        for r in res['recovery_by_V']:
            if r['n']:
                L.append(f"| V {r['V']} | {r['n']} | {r['found']} |")
        L.append('')
        known = sorted([t for t in res['tracks'] if t['known']], key=lambda t: t['known']['V'] or 99)
        if known:
            L.append('Recovered: ' + ', '.join(f"{t['known']['name']} (V {t['known']['V']}, {t['known']['class']}, {t['rate_arcsec_h']}″/h, {t['n_nights']} epochs)" for t in known) + '.\n')
        un = [t for t in res['tracks'] if not t['known']]
        if un:
            L.append('| Unmatched track | Epochs | Speed (″/h) | Fit scatter (″) | Peak S/N |\n|---|---:|---:|---:|---:|')
            for t in un:
                L.append(f"| {t['id']} | {t['n_nights']} | {t['rate_arcsec_h']} | {t['rms_arcsec']} | {t['snr_max']} |")
            L.append('')
        L.append('**What this is and is not.** ' + res['note'] + ' Nothing has been sent to the Minor Planet Center or anyone else.\n')
        line += f": {res['n_tracks_known']} are known asteroids recovered blind, {res['n_tracks_unmatched']} match nothing known (chance expectation {res['chance_tracks_expected']})."
    v2 = OUT / 'v2_calibration' / 'results.json'
    if v2.is_file():
        c = json.loads(v2.read_text())
        rec = [t['known']['name'] + f" (V {t['known']['V']})" for t in c['tracks'] if t['known']]
        L.append(f"**Calibration patches (version 2, not counted above).** {c['n_tracks']} track(s), all known asteroids: {', '.join(rec) or 'none'}. "
                 'Recovery by V: ' + ', '.join(f"V {r['V']}: {r['found']}/{r['n']}" for r in c['recovery_by_V'] if r['n']) + '. '
                 'The linker was then tuned on these patches (version 3) and, on them, recovered 2 of the 3 known asteroids brighter than V 17.\n')
    L.append('**Conclusion.** Single SPHEREx images, linked this way, catch only asteroids brighter than about magnitude 17, and only some of those. '
             'Every asteroid that bright was catalogued long ago, so this channel cannot find a new asteroid. It is reported as a measured limit, not a discovery.\n')
    if tracks.get('history'):
        L.append('**History.** ' + tracks['history'] + ' A one-line fix to the report step (brightness values given as text) is recorded as its own ledger entry.\n')
    L.append('**Reproduce.** `python -m validation.asteroids plan | fetch | detect | link | known | report`, then `python -m validation.asteroids_md`.')
    return '\n'.join(L), line


def main():
    text, line = section()
    _put(ROOT / 'VALIDATION.md', 'ASTEROIDS', text)
    _put(ROOT / 'README.md', 'ASTEROIDS_LINE', '- ' + line + ' See VALIDATION.md, section 13.', heading='## Asteroid hunt (fourth session)')
    _put(ROOT / 'RESULTS_LOG.md', 'ASTEROIDS_LINE', '- ' + line, heading='## Asteroid hunt (14 Nov 2026)')
    print(line)


if __name__ == '__main__':
    main()
