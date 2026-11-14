"""Lock - Predict - Reveal: a held-out motion prediction on real SPHEREx data.

Phase 1 (lock):    python -m validation.experiment lock epsilon-indi-b
    * measures only the training visits (the held-out visit was never downloaded),
    * fits motion models, writes prediction.json + its SHA-256,
    * refuses to run if any held-out pixel file exists locally.
    Commit prediction.json to git BEFORE phase 2.

Phase 2 (reveal):  python -m validation.experiment reveal epsilon-indi-b
    * verifies the prediction hash and that it is committed,
    * downloads the held-out visit, measures it with the same code and settings,
    * evaluates the pre-registered criterion and writes result.json.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import glob
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy import stats

from pipeline.astrometry import mjd_to_iso, to_tangent, propagate
from pipeline.investigate import (SNR_POSITION_MIN, measure_epochs, quality_summary, track_from_catalog,
                                  track_from_fit, usable_positions)
from pipeline.measure import gaia_field, reference_candidates
from pipeline.motion import fit_motion, motion_significance
from pipeline.spherex import CACHE, ROOT
from pipeline.targets import TARGETS

EXP = ROOT / 'validation' / 'experiments'
DATA = ROOT / 'data' / 'targets'
GAIA_IDS = {'epsilon-indi-b': '6412596012146801152', 'barnards-star': '4472832130942575872'}

PROTOCOL = {
    'version': 1,
    'question': 'Where will this source be in a SPHEREx visit that the model has never seen?',
    'held_out_rule': 'All products of the chronologically last visit (visits are separated by gaps > 30 days in IRSA SIA2 metadata).',
    'training_rule': 'All products of every earlier visit that downloaded and validated.',
    'measurement': {
        'centroid': 'release ePSF least-squares fit on native pixels, 7x7 stamp, hard flags masked',
        'registration': 'pure pixel shift from Gaia DR3 reference stars propagated (pm + parallax) to each exposure; target and stars within 20 arcsec of a brighter-or-similar neighbour excluded',
        'usable_position': f'centroid converged, S/N >= {SNR_POSITION_MIN}, no OVERFLOW/NONLINEAR within 1.5 px',
        'held_out_seed': 'free centroid search starts at the locked primary prediction (search box +/-1.5 px = +/-9.2 arcsec)',
    },
    'primary_model': 'linear_parallax (SPHEREx-only: position, proper motion and parallax all fitted to training data)',
    'comparison_models': {
        'catalog_parallax': 'linear proper motion fitted to SPHEREx, parallax fixed at the catalogue value (catalogue-assisted)',
        'catalog_full': 'catalogue astrometry propagated (catalogue-assisted; no SPHEREx fitting)',
        'stationary_null': 'the source stays at its mean position in the last training visit ("stays here")',
    },
    'criterion': ('PASS if the inverse-variance-weighted mean residual (measured - predicted) over usable held-out '
                  'exposures has Mahalanobis distance d^2 < 11.83 (the 99.73 % / "3 sigma" region for 2 dof) under '
                  'Sigma = Sigma_prediction(mean held-out epoch) + Sigma_measurement(mean). '
                  'INCONCLUSIVE if fewer than 10 usable held-out exposures. Otherwise FAIL.'),
    'pass_threshold_d2': 11.83,
    'min_heldout_exposures': 10,
}


def canonical(obj) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, allow_nan=False, default=float) + '\n').encode()


def git(*args) -> str:
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()


def field_setup(slug):
    t = TARGETS[slug]
    manifest = json.loads((DATA / slug / 'archive_manifest.json').read_text())
    c = manifest['field_center']
    stars = gaia_field(c['ra'], c['dec'], 0.13, cache=DATA / slug / 'gaia_field.json')
    refs = reference_candidates(stars, exclude_ids=[GAIA_IDS.get(slug, '')])
    return t, manifest, refs


def fit_all(rows, catalog_plx):
    u = usable_positions(rows)
    mjd = np.array([r['mjd'] for r in u])
    ra = np.array([r['position']['ra'] for r in u])
    dec = np.array([r['position']['dec'] for r in u])
    sig = np.array([r['position']['sigma_arcsec'] for r in u])
    fits = {m: fit_motion(mjd, ra, dec, sig, model=m) for m in ('stationary', 'linear', 'linear_parallax')}
    ref = fits['linear_parallax']
    fits['catalog_parallax'] = fit_motion(mjd, ra, dec, sig, model='linear_fixed_parallax', fixed_parallax_mas=catalog_plx,
                                          ra_ref=ref.ra_ref, dec_ref=ref.dec_ref, t0_mjd=ref.t0_mjd)
    return u, fits


def lock(slug):
    t, manifest, refs = field_setup(slug)
    sealed = [p for p in manifest['products'] if p.get('sealed')]
    if not sealed:
        raise SystemExit('No sealed visit in the archive manifest; run fetch_target with --seal-last-visit.')
    raw = CACHE / 'targets' / slug / 'raw'
    leaked = [p['id'] for p in sealed if (raw / f"{p['id']}.fits").exists()]
    if leaked:
        raise SystemExit(f'Refusing to lock: {len(leaked)} held-out files already exist locally ({leaked[:3]}...).')
    out = EXP / slug
    if (out / 'prediction.json').exists():
        raise SystemExit('A prediction is already locked for this target; it must not be overwritten.')
    files = sorted(glob.glob(str(raw / '*.fits')))
    rows = measure_epochs(files, track_from_catalog(t.astrometry), refs, workers=8)
    u, fits = fit_all(rows, t.astrometry.parallax_mas)
    primary = fits['linear_parallax']
    held_t = np.array([0.5 * (p['t_min'] + p['t_max']) for p in sealed])
    t_mean = float(held_t.mean())
    preds = {}
    for name, f in (('primary', primary), ('catalog_parallax', fits['catalog_parallax'])):
        p = f.predict([t_mean])
        preds[name] = {'model': f.model, 'ra_deg': float(p['ra'][0]), 'dec_deg': float(p['dec'][0]),
                       'cov_arcsec2': p['cov'][0].tolist(), 'track': track_from_fit(f),
                       'params': f.params, 'param_cov': f.cov.tolist(), 'summary': f.summary(),
                       'ra_ref': f.ra_ref, 'dec_ref': f.dec_ref, 't0_mjd': f.t0_mjd,
                       'fixed_parallax_arcsec': f.fixed_parallax_arcsec}
    cat = track_from_catalog(t.astrometry)
    pc = propagate(cat['ra'], cat['dec'], cat['t0_mjd'], cat['pmra'], cat['pmdec'], cat['parallax'], [t_mean])
    preds['catalog_full'] = {'ra_deg': float(pc.ra[0]), 'dec_deg': float(pc.dec[0]), 'track': cat,
                             'cov_arcsec2': [[(0.001) ** 2, 0], [0, (0.001) ** 2]],
                             'note': 'catalogue formal errors are negligible here; systematic photocentre differences are not included'}
    # Null: mean position of the last training visit
    last_visit = max(manifest['visits'][:-1], key=lambda v: v['mjd_start'])
    lv = [r for r in u if last_visit['mjd_start'] - 1 <= r['mjd'] <= last_visit['mjd_end'] + 1]
    w = np.array([1 / r['position']['sigma_arcsec'] ** 2 for r in lv])
    ra0 = float(np.sum(w * np.array([r['position']['ra'] for r in lv])) / w.sum())
    dec0 = float(np.sum(w * np.array([r['position']['dec'] for r in lv])) / w.sum())
    s0 = float(1 / math.sqrt(w.sum()))
    preds['stationary_null'] = {'ra_deg': ra0, 'dec_deg': dec0, 'cov_arcsec2': [[s0 ** 2, 0], [0, s0 ** 2]],
                                'track': {'ra': ra0, 'dec': dec0, 't0_mjd': t_mean, 'pmra': 0.0, 'pmdec': 0.0, 'parallax': 0.0}}
    training_ids = sorted(r['product_id'] for r in rows if r.get('product_id'))
    prediction = {
        'experiment': f'{slug}-heldout-v1',
        'target': {'slug': slug, 'title': t.title, 'catalogue': t.astrometry.source},
        'protocol': PROTOCOL,
        'locked_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'code_commit': git('rev-parse', 'HEAD'),
        'code_dirty': bool(git('status', '--porcelain', '--', 'pipeline', 'validation/experiment.py')),
        'training': {
            'n_products': len(rows), 'n_usable_positions': len(u),
            'visits': [v for v in manifest['visits'] if not v.get('sealed')],
            'product_ids_sha256': hashlib.sha256('\n'.join(training_ids).encode()).hexdigest(),
            'quality': quality_summary(rows),
            'motion_fits': {k: f.summary() for k, f in fits.items()},
            'motion_significance': motion_significance(fits['stationary'], primary),
        },
        'held_out': {
            'visit': next(v for v in manifest['visits'] if v.get('sealed')),
            'n_products': len(sealed), 'product_ids': sorted(p['id'] for p in sealed),
            'mean_epoch_mjd': t_mean, 'mean_epoch_utc': mjd_to_iso(t_mean),
            'pixels_inspected_before_lock': False,
            'note': 'Only SIA2 metadata (IDs, times, URLs) of the held-out products was read before the lock.',
        },
        'predictions': preds,
        'disclosures': [
            'Catalogue (Gaia DR3) astrometry was used to locate the source in training images (centroid search seed) and to register frames with field stars; the primary prediction itself uses only SPHEREx positions.',
            'The experimenter (an AI coding agent working for the team) had seen published Gaia DR3 values for this source before the experiment; it did not view any held-out pixel.',
            'Git commit timestamps are self-reported. An externally timestamped record (e.g. pushing the commit) is stronger evidence of when the prediction was frozen.',
        ],
    }
    out.mkdir(parents=True, exist_ok=True)
    blob = canonical(prediction)
    (out / 'prediction.json').write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()
    (out / 'prediction.sha256').write_text(f'{digest}  prediction.json\n')
    (out / 'training_measurements.json').write_bytes(canonical(rows))
    print(json.dumps({'sha256': digest, 'primary': preds['primary']['summary'], 'pred_ra': preds['primary']['ra_deg'],
                      'pred_dec': preds['primary']['dec_deg'], 'cov': preds['primary']['cov_arcsec2']}, indent=1, default=float))


def mahalanobis(r, cov):
    r = np.asarray(r, dtype=float)
    return float(r @ np.linalg.inv(np.asarray(cov, dtype=float)) @ r)


def reveal(slug):
    out = EXP / slug
    blob = (out / 'prediction.json').read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    recorded = (out / 'prediction.sha256').read_text().split()[0]
    if digest != recorded:
        raise SystemExit('prediction.json does not match its recorded SHA-256; refusing to reveal.')
    rel = str((out / 'prediction.json').relative_to(ROOT))
    commit = git('log', '-1', '--format=%H %cI', '--', rel)
    if not commit:
        raise SystemExit('prediction.json is not committed to git; commit it before revealing.')
    if git('status', '--porcelain', '--', rel):
        raise SystemExit('prediction.json has uncommitted changes.')
    pred = json.loads(blob)
    t, manifest, refs = field_setup(slug)
    # Download the held-out visit now (and only now).
    # Download exactly the locked held-out product IDs (not "whatever the last visit is today").
    from pipeline.spherex import search, fetch_many
    ids = pred['held_out']['product_ids']
    c = manifest['field_center']
    products = [p for p in search(c['ra'], c['dec']) if p.id in set(ids)]
    raw = CACHE / 'targets' / slug / 'raw'
    _, failures = fetch_many(products, c['ra'], c['dec'], manifest['field_size_arcmin'], raw, workers=6)
    if failures:
        print(f'{len(failures)} held-out downloads failed: {failures[:3]}')
    files = [str(raw / f'{i}.fits') for i in ids if (raw / f'{i}.fits').exists()]
    primary_track = pred['predictions']['primary']['track']
    rows = measure_epochs(files, primary_track, refs, workers=8)
    u = usable_positions(rows)
    results = {}
    from pipeline.motion import MotionFit
    for name in ('primary', 'catalog_parallax', 'catalog_full', 'stationary_null'):
        P = pred['predictions'][name]
        res, wts, covs = [], [], []
        for r in u:
            if name in ('primary', 'catalog_parallax'):
                f = MotionFit(P['model'], P['ra_ref'], P['dec_ref'], P['t0_mjd'], P['params'], np.array(P['param_cov']),
                              0, 1, 0, 0, P.get('fixed_parallax_arcsec'))
                pp = f.predict([r['mjd']])
                pra, pdec, pcov = float(pp['ra'][0]), float(pp['dec'][0]), pp['cov'][0]
            else:
                tr = P['track']
                pc = propagate(tr['ra'], tr['dec'], tr['t0_mjd'], tr['pmra'], tr['pmdec'], tr['parallax'], [r['mjd']])
                pra, pdec, pcov = float(pc.ra[0]), float(pc.dec[0]), np.array(P['cov_arcsec2'])
            xi, eta = to_tangent(r['position']['ra'], r['position']['dec'], pra, pdec)
            res.append([float(xi), float(eta)])
            wts.append(1 / r['position']['sigma_arcsec'] ** 2)
            covs.append(pcov)
        res = np.array(res)
        wts = np.array(wts)
        n = len(res)
        if n < PROTOCOL['min_heldout_exposures']:
            results[name] = {'verdict': 'INCONCLUSIVE', 'n_usable': n}
            continue
        mean = (res * wts[:, None]).sum(0) / wts.sum()
        chi2 = float(np.sum(((res - mean) ** 2).sum(1) * wts))
        chi2r = chi2 / max(2 * n - 2, 1)
        meas_var = (1 / wts.sum()) * max(chi2r, 1.0)
        pred_cov = np.mean(np.array(covs), axis=0)
        total = pred_cov + np.eye(2) * meas_var
        d2 = mahalanobis(mean, total)
        results[name] = {
            'n_usable': n, 'mean_residual_arcsec': {'dra_cosdec': float(mean[0]), 'ddec': float(mean[1])},
            'residual_arcsec': float(np.hypot(*mean)),
            'prediction_sigma_arcsec': float(math.sqrt(np.trace(pred_cov) / 2)),
            'measurement_sigma_arcsec': float(math.sqrt(meas_var)),
            'heldout_scatter_chi2r': chi2r, 'mahalanobis_d2': d2,
            'equivalent_sigma': float(stats.norm.isf(stats.chi2.sf(d2, 2) / 2)) if stats.chi2.sf(d2, 2) > 0 else 99.0,
            'verdict': 'PASS' if d2 < PROTOCOL['pass_threshold_d2'] else 'FAIL',
        }
    measured_mean = None
    if u:
        w = np.array([1 / r['position']['sigma_arcsec'] ** 2 for r in u])
        measured_mean = {'ra_deg': float(np.sum(w * np.array([r['position']['ra'] for r in u])) / w.sum()),
                         'dec_deg': float(np.sum(w * np.array([r['position']['dec'] for r in u])) / w.sum()),
                         'mean_mjd': float(np.sum(w * np.array([r['mjd'] for r in u])) / w.sum())}
    result = {
        'experiment': pred['experiment'], 'prediction_sha256': digest, 'prediction_commit': commit,
        'revealed_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'code_commit': git('rev-parse', 'HEAD'),
        'held_out_measured': {'n_products': len(ids), 'n_downloaded': len(files), 'n_usable': len(u),
                              'quality': quality_summary(rows), 'weighted_mean_position': measured_mean},
        'evaluations': results,
        'primary_verdict': results.get('primary', {}).get('verdict'),
        'classification': 'Independent held-out recovery (SPHEREx-only motion model; catalogue used to identify the source and register frames)',
    }
    (out / 'result.json').write_bytes(canonical(result))
    (out / 'heldout_measurements.json').write_bytes(canonical(rows))
    print(json.dumps(result, indent=1, default=float))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('phase', choices=['lock', 'reveal'])
    ap.add_argument('slug')
    a = ap.parse_args()
    (lock if a.phase == 'lock' else reveal)(a.slug)
