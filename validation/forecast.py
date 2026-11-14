"""Forward predictions: where each mover will be in SPHEREx images that do not exist yet.

The held-out experiments (validation/experiment.py) sealed a visit that was already in the archive.
A forecast goes one step further: it is fitted to ALL SPHEREx data available today and predicts
positions on future dates.  At lock time the archive is queried and the date of its latest
exposure of the field is recorded, so anyone can see that the data being predicted did not exist.

    python -m validation.forecast            # write validation/forecasts/<slug>.json and .sha256
    git add validation/forecasts && git commit   # the commit is the lock

The pass rule is the one pre-registered for the held-out experiments.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import sys

import numpy as np
from astropy.time import Time

from pipeline.astrometry import mjd_to_iso
from pipeline.investigate import usable_positions
from pipeline.motion import fit_motion
from pipeline.spherex import CACHE, ROOT, search
from pipeline.targets import TARGETS

OUT = ROOT / 'validation' / 'forecasts'
DATES = [f'{y}-{m:02d}-01' for y, m in [(2026, 12)] + [(2027, k) for k in range(1, 13)]]
# slug -> (model, note)
PLAN = {
    'epsilon-indi-b': ('linear_parallax', 'SPHEREx only: proper motion and parallax fitted to all four visits. The orbital motion of the '
                                          'unresolved binary (Ba/Bb) is not modelled, which is the main risk to this forecast.'),
    'j0415-0935': ('linear_parallax', 'SPHEREx only: proper motion and parallax fitted to all three visits.'),
}
# WISE 0855 is deliberately not forecast: only 12 single-exposure positions are usable and its SPHEREx motion
# (about 10 arcsec/yr) is 2-3 sigma above the catalogue value, so a forecast would test a fit we already distrust.
CRITERION = ('PASS if the inverse-variance-weighted mean residual (measured - predicted) over the usable exposures of the next visit has '
             'Mahalanobis distance d^2 < 11.83 (the 99.73 % region for 2 degrees of freedom) under Sigma = Sigma_prediction(mean epoch) + '
             'Sigma_measurement. INCONCLUSIVE if fewer than 10 usable exposures. Otherwise FAIL. Identical to the held-out experiments.')


def forecast(slug):
    t = TARGETS[slug]
    model, note = PLAN[slug]
    rows = json.loads((CACHE / 'targets' / slug / 'rows.json').read_text())['rows']
    u = usable_positions(rows)
    mjd = np.array([r['mjd'] for r in u])
    ra = np.array([r['position']['ra'] for r in u])
    dec = np.array([r['position']['dec'] for r in u])
    sig = np.array([r['position']['sigma_arcsec'] for r in u])
    kw = {'fixed_parallax_mas': t.astrometry.parallax_mas} if model == 'linear_fixed_parallax' else {}
    fit = fit_motion(mjd, ra, dec, sig, model=model, **kw)
    when = np.array([Time(d + 'T00:00:00', scale='utc').mjd for d in DATES])
    pr = fit.predict(when)
    # "stays here" null: the weighted mean position of the latest visit
    last = mjd > mjd.max() - 45
    w = 1 / sig[last] ** 2
    null = {'ra_deg': float(np.sum(w * ra[last]) / w.sum()), 'dec_deg': float(np.sum(w * dec[last]) / w.sum()),
            'note': 'mean position in the latest visit: where the source would be if it did not move'}
    products = search(float(ra.mean()), float(dec.mean()))
    latest = max(p.t_max for p in products)
    doc = {
        'kind': 'forward_prediction', 'target': slug, 'title': t.title,
        'locked_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'statement': 'Predicted positions of this source on future dates, fitted to every SPHEREx exposure of the field available at lock time.',
        'model': model, 'model_note': note,
        'data_used': {'n_usable_positions': int(len(u)), 'first_observation_utc': mjd_to_iso(float(mjd.min())),
                      'last_observation_utc': mjd_to_iso(float(mjd.max()))},
        'archive_at_lock': {'service': 'IRSA SIA2 (spherex_dr1, spherex_qr3)', 'n_products_covering_the_source': len(products),
                            'latest_exposure_utc': mjd_to_iso(float(latest)),
                            'note': 'No exposure later than this was listed by the archive when the forecast was locked.'},
        'fit': fit.summary(), 'reference': {'ra_deg': fit.ra_ref, 'dec_deg': fit.dec_ref, 't0_mjd': fit.t0_mjd},
        'params': fit.params, 'param_cov': np.asarray(fit.cov).tolist(),
        'fixed_parallax_arcsec': fit.fixed_parallax_arcsec,
        'criterion': CRITERION, 'stays_here_null': null,
        'predictions': [{'date_utc': d + 'T00:00:00Z', 'mjd': float(m), 'ra_deg': float(a), 'dec_deg': float(b),
                         'sigma_ra_arcsec': float(math.sqrt(c[0][0])), 'sigma_dec_arcsec': float(math.sqrt(c[1][1])),
                         'cov_arcsec2': np.asarray(c).tolist(),
                         'offset_from_stays_here_arcsec': float(math.hypot((a - null['ra_deg']) * math.cos(math.radians(b)), b - null['dec_deg']) * 3600)}
                        for d, m, a, b, c in zip(DATES, when, pr['ra'], pr['dec'], pr['cov'])],
        'how_to_check': 'When IRSA releases a later visit of this field, measure the source with pipeline/investigate.py (same code), take the '
                        'weighted mean position and epoch, interpolate this table to that epoch with the stored parameters, and apply the criterion.',
    }
    OUT.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(doc, indent=1, sort_keys=True).encode()
    (OUT / f'{slug}.json').write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    (OUT / f'{slug}.sha256').write_text(f'{digest}  {slug}.json\n')
    s = doc['fit']
    print(f"{slug}: {len(u)} positions, pm {s['pm_total_masyr']:.0f} +- {s['pm_total_err_masyr']:.0f} mas/yr; archive latest {doc['archive_at_lock']['latest_exposure_utc'][:10]}; "
          f"2027-04-01 -> {doc['predictions'][4]['ra_deg']:.6f}, {doc['predictions'][4]['dec_deg']:.6f} "
          f"+- {doc['predictions'][4]['sigma_ra_arcsec']:.2f}\", {doc['predictions'][4]['sigma_dec_arcsec']:.2f}\"; sha256 {digest[:16]}")
    return doc


if __name__ == '__main__':
    for slug in (sys.argv[1:] or list(PLAN)):
        forecast(slug)
