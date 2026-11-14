"""Fill the {{TOKENS}} in the Markdown documents from the result files, so the prose cannot drift from the numbers.

    python -m validation.fill_docs
"""
from __future__ import annotations

import json
import re
import sys

from pipeline.spherex import ROOT

DOCS = ['README.md', 'VALIDATION.md', 'SUBMISSION.md', 'DEMO_SCRIPT.md']


def main():
    idx = json.loads((ROOT / 'data' / 'hunt' / 'index.json').read_text())
    halo = json.loads((ROOT / 'validation' / 'halo_results.json').read_text())
    t, r, cs = idx['totals'], idx['recovery'], halo['control_summary']
    unexpl, susp = len(idx['unexplained']), idx['classes'].get('suspect', 0)
    names = [f['truth']['name'] for f in idx['fields'] if f.get('truth') and f['truth']['recovered']]
    simp = any('SIMP' in n for n in names)
    hunt_sentence = (f"Across {t['fields']} fields ({t['area_deg2']:.1f} square degrees, {t['exposures']:,} exposures) the search tested "
                     f"**{t['motion_tested']:,} sources** for motion without being told which ones move (Gaia is used only to line the images up). It found **{r['n_recovered']} of {r['n_known']} "
                     f"known fast movers** on its own" + (', including the free-floating planetary-mass object SIMP 0136' if simp else '') +
                     f", flagged **{unexpl} mover{'s' if unexpl != 1 else ''} that no catalogue explains**, and rejected {susp} false "
                     f"alarm{'s' if susp != 1 else ''} with its vetting tests. Hidden synthetic cold sources were recovered down to 600 µJy at 3–8″/yr, "
                     f"with no stationary one called a mover.")
    if cs['n_with_comparison']:
        halo_sentence = (f"Of {cs['n_with_comparison']} other bright stars measured the same way ({cs['n_comparisons']} visit comparisons), "
                         f"{cs['n_flagged_variable']} {'was' if cs['n_flagged_variable'] == 1 else 'were'} flagged variable; their median change was "
                         f"{cs['median_abs_change'] * 100:.0f} % and the largest {cs['max_abs_change'] * 100:.0f} %.")
    else:
        halo_sentence = "No other star in the cached fields was bright enough for the same comparison, so Barnard's Star is the only control."
    tokens = {
        'HUNT_FIELDS': str(t['fields']), 'HUNT_AREA': f"{t['area_deg2']:.1f}", 'HUNT_EXPOSURES': f"{t['exposures']:,}",
        'HUNT_SOURCES': f"{t['sources']:,}", 'HUNT_TESTED': f"{t['motion_tested']:,}", 'HUNT_KNOWN': str(r['n_known']),
        'HUNT_DETECTED': str(r['n_detected']), 'HUNT_RECOVERED': str(r['n_recovered']), 'HUNT_UNEXPLAINED': str(unexpl),
        'HUNT_SUSPECT': str(susp), 'HUNT_DEPTH': f"{idx['reach']['median_depth_ujy']:.0f}" if idx.get('reach') else 'n/a',
        'HUNT_REACH': f"{idx['reach']['reach_ly']:.0f}" if idx.get('reach') else 'n/a',
        'HALO_N': str(cs['n_with_comparison']), 'HALO_FLAGGED': str(cs['n_flagged_variable']),
        'HUNT_SENTENCE': hunt_sentence, 'HALO_SENTENCE': halo_sentence,
    }
    for name in DOCS:
        p = ROOT / name
        s = p.read_text()
        left = set(re.findall(r'\{\{([A-Z_]+)\}\}', s))
        for k, v in tokens.items():
            s = s.replace('{{' + k + '}}', v)
        missing = set(re.findall(r'\{\{([A-Z_]+)\}\}', s))
        p.write_text(s)
        print(f'{name}: filled {len(left) - len(missing)} token kinds' + (f', UNKNOWN {sorted(missing)}' if missing else ''))
    print(json.dumps({k: v for k, v in tokens.items() if 'SENTENCE' not in k}))


if __name__ == '__main__':
    sys.exit(main())
