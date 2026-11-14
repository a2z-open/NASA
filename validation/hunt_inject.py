"""SYNTHETIC blind injection-recovery for the Planet X hunt (clearly not real sources).

Cold moving point sources (no flux below 3.8 um, like WISE 0855) are added to the real exposures of a
blank control field, built from each exposure's own ePSF.  The blind search is then run on the result
exactly as on real data, with no knowledge of where the injections are.  Only afterwards are its movers
compared with the injected list.  This measures how faint and how slow a cold mover the search can find,
and whether stationary injections are wrongly called movers.

    python -m validation.hunt_inject [field]        # default: control-cosmos
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import sys

import numpy as np

from pipeline import hunt
from pipeline.spherex import ROOT, load_observation

OUT = ROOT / 'validation' / 'hunt_injection.json'
SPEEDS = [0.0, 1.0, 3.0, 8.0]            # arcsec / yr
FLUXES = [150.0, 300.0, 600.0, 1200.0]   # uJy at 3.8-5.0 um
MIN_UM = 3.8


def main(field='control-cosmos'):
    man = json.loads((hunt.HUNT_DATA / field / 'manifest.json').read_text())
    files = sorted((hunt.HUNT_CACHE / field / 'raw').glob('*.fits'))
    ra0, dec0, fov = man['ra'], man['dec'], float(man['fov_arcmin'])
    gaia = hunt.gaia_field(ra0, dec0, fov / 60 * 0.75, cache=hunt.HUNT_CACHE / field / 'gaia_field.json')
    mjds = [load_observation(f, keep_epsf_zones=0).mjd for f in files[::6]]
    t0 = float(np.median(mjds))
    rng = np.random.default_rng(20261114)
    cosd = math.cos(math.radians(dec0))
    inj = []
    # a 4 x 4 grid, 3 arcmin apart, nudged away from Gaia stars
    for i, speed in enumerate(SPEEDS):
        for j, flux in enumerate(FLUXES):
            for _ in range(60):
                dx = (j - 1.5) * 3.0 + rng.uniform(-0.6, 0.6)      # arcmin east
                dy = (i - 1.5) * 3.0 + rng.uniform(-0.6, 0.6)      # arcmin north
                ra, dec = ra0 + dx / 60 / cosd, dec0 + dy / 60
                near = min(math.hypot((s['ra'] - ra) * cosd, s['dec'] - dec) * 3600 for s in gaia) if gaia else 999
                if near > 45:
                    break
            ang = rng.uniform(0, 2 * math.pi)
            inj.append({'ra': ra, 'dec': dec, 't0': t0, 'pmra': speed * math.sin(ang), 'pmdec': speed * math.cos(ang),
                        'flux_ujy': flux, 'min_um': MIN_UM})
    doc = hunt.run_field(f'_injection-{field}', files, ra0, dec0, fov, title=f'SYNTHETIC injections in {field}', gaia=gaia,
                         kind='injection', external=False, injections=inj, out_dir=ROOT / '.parallax-cache' / 'hunt' / f'_injection-{field}' / 'out')
    res = doc['injections']
    out = {
        'label': 'SYNTHETIC: these are not real sources',
        'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'description': ('Sixteen cold point sources (no flux below %.1f um) were added to the real exposures of the blank field %s, from each '
                        "exposure's own ePSF, and the blind search was run without being told where they are. Real background and "
                        'read noise are present; source photon noise is not simulated.') % (MIN_UM, field),
        'field': field, 'n_exposures': doc['n_exposures'], 'n_visits': len(doc['visits']), 'baseline_days': doc['baseline_days'],
        'depth_5sigma_ujy': doc['depth_5sigma_ujy'], 'speeds_arcsec_yr': SPEEDS, 'fluxes_ujy': FLUXES, 'results': res,
        'other_movers_reported': sum(1 for s in doc['sources'] if s['class'] in ('candidate', 'stack_candidate', 'two_visit_candidate')
                                     and 'injected' not in s),
    }
    OUT.write_text(json.dumps(out, indent=1, default=float))
    for r in res:
        print(f"  {r['speed_arcsec_yr']:4.1f}\"/yr  {r['flux_ujy']:6.0f} uJy -> {r['outcome']:16s} class={r['class']} pm={r['measured_pm_arcsec_yr']} "
              f"npos={r['n_native_positions']} snr={r['stack_snr']}")
    print('other movers reported in the injected field:', out['other_movers_reported'])


if __name__ == '__main__':
    main(*sys.argv[1:2])
