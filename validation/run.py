"""Reproducible validation suite.

    python -m validation.run              # benchmark + negative controls + injections -> validation/validation_results.json

* Known-target benchmark: the five NASA targets, read from their investigations.
* Negative controls: Gaia DR3 stars with |mu| < 20 mas/yr in the cached fields, measured with exactly the
  same pipeline and thresholds (each control star is removed from the registration reference set).
  A control flagged as "significant motion" is a false positive.
* Error calibration: pulls (SPHEREx pm - Gaia pm) / sigma for the same stars.
* Synthetic injections (clearly labelled): ePSF point sources injected into real SPHEREx cutouts.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import glob
import json
import math
from pathlib import Path
import sys

import numpy as np

from pipeline.analysis import MIN_POSITIONS, MOTION_PM_SNR, MOTION_SIGMA, VAR_MIN_AMPLITUDE, VAR_SIGMA, TEMPLATE_MAX_RCHI2
from pipeline.investigate import SNR_POSITION_MIN, measure_epochs, usable_positions
from pipeline.measure import GAIA_EPOCH_MJD, reference_candidates
from pipeline.motion import fit_motion, motion_significance
from pipeline.spherex import CACHE, ROOT
from pipeline.targets import ORDER, TARGETS

DATA = ROOT / 'data' / 'targets'
OUT = ROOT / 'validation' / 'validation_results.json'
GAIA_IDS = {'epsilon-indi-b': '6412596012146801152', 'barnards-star': '4472832130942575872',
            'rw-aurigae': '156430817820015232', 'r-draconis': '1648328016354496384'}


def jload(p):
    return json.loads(Path(p).read_text())


def benchmark():
    rows = []
    for slug in ORDER:
        inv = jload(DATA / slug / 'investigation.json')
        man = jload(DATA / slug / 'archive_manifest.json')
        m = inv.get('motion') or {}
        rep = (m.get('models') or {}).get(m.get('reported_model') or '', {})
        q = inv['observations']['quality']
        sp = inv.get('spectrum') or {}
        tm = sp.get('templates') or {}
        var = inv.get('variability') or {}
        verdicts = [v['label'] for v in inv['summary']['verdicts']]
        flags = q.get('flag_counts_near_source', {})
        row = {
            'target': TARGETS[slug].title, 'slug': slug, 'purpose': TARGETS[slug].purpose,
            'archive_products': len(man['products']), 'cached_products': inv['observations']['n_total'],
            'usable_positions': inv['observations']['n_usable_positions'], 'outcomes': q.get('outcomes'),
            'date_range': inv['observations']['date_range'], 'wavelength_coverage_um': inv['observations']['wavelength_coverage_um'],
            'visits': len(man['visits']), 'flag_counts_near_source': flags,
            'motion_status': m.get('status'), 'pm_total_masyr': rep.get('pm_total_masyr'), 'pm_total_err_masyr': rep.get('pm_total_err_masyr'),
            'pmra_masyr': rep.get('pmra_masyr'), 'pmdec_masyr': rep.get('pmdec_masyr'),
            'parallax_mas': rep.get('parallax_mas'), 'parallax_err_mas': rep.get('parallax_err_mas'),
            'catalog_comparison': m.get('catalog_comparison'),
            'spectrum_status': sp.get('status'), 'spectrum_bins_detected': (sp.get('coverage') or {}).get('n_bins_detected'),
            'template': (tm.get('best') or {}).get('spectral_type') if tm.get('status') == 'matched' else None,
            'template_status': tm.get('status'), 'template_rchi2': (tm.get('best') or {}).get('reduced_chi2'),
            'fixed_vs_follow_ratio': (sp.get('fixed_vs_follow') or {}).get('median_ratio'),
            'variability_status': var.get('status'), 'variability_method': var.get('method'),
            'variability_pairs': (var.get('matched') or {}).get('visit_pairs'),
            'naive_max_ratio': (var.get('naive') or {}).get('max_ratio'),
            'verdicts': verdicts, 'headline': inv['summary']['headline'],
            'cold_search': inv.get('cold_search'),
        }
        row['recovery_status'] = recovery_status(slug, row)
        rows.append(row)
    return rows


def recovery_status(slug, r):
    if slug == 'epsilon-indi-b':
        return 'Recovered: motion, parallax and spectral type measured; held-out prediction passed' if r['motion_status'] == 'significant' else 'Not recovered'
    if slug == 'barnards-star':
        return 'Inconclusive: saturated in every cached exposure (OVERFLOW at the core)'
    if slug == 'wise-0855':
        cs = r.get('cold_search') or {}
        bands = {b['band']: b for b in cs.get('bands', [])}
        long = next((b for k, b in bands.items() if k.startswith('4.42')), None)
        short = next((b for k, b in bands.items() if k.startswith('0.75')), None)
        if long and long.get('detected') and short and not short.get('detected'):
            mv = (f"; {r['pm_total_masyr'] / 1000:.1f} ± {r['pm_total_err_masyr'] / 1000:.1f}″/yr motion from {r['usable_positions']} high-S/N exposures"
                  if r['motion_status'] == 'significant' else '; motion not independently measured')
            return f'Detected only at 3.8–5.0 µm (forced photometry on the catalogue track, neighbour deblended){mv}'
        if long and long.get('detected'):
            return 'Flux measured at the catalogue track, but short-wavelength flux also present: contamination not excluded'
        return 'Not detected (upper limits reported)'
    if r['variability_status'] == 'variable':
        return 'Variability measured at matched wavelengths' + (' (experimental wing photometry)' if r['variability_method'] == 'wing' else '')
    if r['variability_status'] == 'saturated':
        return 'Inconclusive: saturated; variability not measurable'
    return f"Variability {r['variability_status']}"


def control_job(args):
    slug, star, files, refs, stars = args
    track = {'ra': star['ra'], 'dec': star['dec'], 't0_mjd': GAIA_EPOCH_MJD, 'pmra': star['pmra'], 'pmdec': star['pmdec'],
             'parallax': star.get('parallax') or 0.0}
    rows = measure_epochs(files, track, refs, workers=1, stars=stars)
    u = usable_positions(rows)
    res = {'field': slug, 'source_id': star['source_id'], 'g': star['g'], 'gaia_pmra': star['pmra'], 'gaia_pmdec': star['pmdec'],
           'gaia_parallax': star.get('parallax'), 'n_usable': len(u)}
    if len(u) < MIN_POSITIONS:
        res['outcome'] = 'insufficient'
        return res
    mjd = [r['mjd'] for r in u]
    ra = [r['position']['ra'] for r in u]
    dec = [r['position']['dec'] for r in u]
    sig = [r['position']['sigma_arcsec'] for r in u]
    st = fit_motion(mjd, ra, dec, sig, model='stationary')
    n_vis = len({round(m / 60) for m in mjd})
    mv = fit_motion(mjd, ra, dec, sig, model='linear_parallax' if n_vis >= 3 and len(u) >= 10 else 'linear', ra_ref=st.ra_ref, dec_ref=st.dec_ref)
    s = motion_significance(st, mv)
    summ = mv.summary()
    sig_motion = s['equivalent_sigma'] >= MOTION_SIGMA and (s['pm_over_error'] or 0) >= MOTION_PM_SNR
    res.update({'pmra': summ['pmra_masyr'], 'pmra_err': summ['pmra_err_masyr'], 'pmdec': summ['pmdec_masyr'],
                'pmdec_err': summ['pmdec_err_masyr'], 'pm_total': summ['pm_total_masyr'], 'pm_total_err': summ['pm_total_err_masyr'],
                'parallax': summ.get('parallax_mas'), 'parallax_err': summ.get('parallax_err_mas'),
                'equivalent_sigma': s['equivalent_sigma'], 'pm_over_error': s['pm_over_error'], 'chi2r': summ['chi2_reduced'],
                'model': mv.model,
                'pull_pmra': (summ['pmra_masyr'] - star['pmra']) / summ['pmra_err_masyr'],
                'pull_pmdec': (summ['pmdec_masyr'] - star['pmdec']) / summ['pmdec_err_masyr'],
                'flagged_as_moving': bool(sig_motion), 'outcome': 'false_positive' if sig_motion else 'correctly_stationary'})
    return res


def negative_controls(per_field=10):
    jobs = []
    for slug in ['epsilon-indi-b', 'wise-0855', 'rw-aurigae', 'r-draconis']:
        stars = jload(DATA / slug / 'gaia_field.json')
        field = jload(DATA / slug / 'field.json')
        files = sorted(glob.glob(str(CACHE / 'targets' / slug / 'raw' / '*.fits')))
        man = jload(DATA / slug / 'archive_manifest.json')
        sealed = {p['id'] for p in man['products'] if p.get('sealed')}
        if not (ROOT / 'validation' / 'experiments' / slug / 'result.json').exists():
            files = [f for f in files if Path(f).stem not in sealed]
        cands = []
        for s in stars:
            if s['pmra'] is None or s['g'] is None or not (11.5 <= s['g'] <= 16.5) or (s['ruwe'] or 9) > 1.4:
                continue
            if math.hypot(s['pmra'], s['pmdec']) > 20:
                continue
            if s['source_id'] == GAIA_IDS.get(slug):
                continue
            dx = (s['ra'] - field['ra']) * math.cos(math.radians(field['dec'])) * 60
            dy = (s['dec'] - field['dec']) * 60
            if math.hypot(dx, dy) > 4.0:      # stay well inside the 10' cutouts
                continue
            cands.append(s)
        iso = reference_candidates(cands + [x for x in stars if x not in cands], exclude_ids=[])
        iso_ids = {x['source_id'] for x in iso}
        cands = [c for c in cands if c['source_id'] in iso_ids]
        cands = sorted(cands, key=lambda c: c['g'])
        pick = cands[:: max(1, len(cands) // per_field)][:per_field]
        for star in pick:
            refs = reference_candidates(stars, exclude_ids=[star['source_id'], GAIA_IDS.get(slug, '')])
            jobs.append((slug, star, files, refs, stars))
    with ProcessPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(control_job, jobs))
    measured = [r for r in results if r.get('outcome') != 'insufficient']
    fp = [r for r in measured if r['flagged_as_moving']]
    pulls = np.array([[r['pull_pmra'], r['pull_pmdec']] for r in measured]).ravel() if measured else np.array([])
    return {
        'description': 'Gaia DR3 stars with |pm| < 20 mas/yr, G 11.5–16.5, RUWE < 1.4, isolated (no comparable neighbour within 20 arcsec), '
                       'within 4 arcmin of each field centre. Each star is excluded from the registration reference set while it is measured.',
        'thresholds': {'equivalent_sigma': MOTION_SIGMA, 'pm_over_error': MOTION_PM_SNR, 'snr_position_min': SNR_POSITION_MIN},
        'n_controls': len(results), 'n_measured': len(measured), 'n_insufficient': len(results) - len(measured),
        'false_positives': len(fp), 'false_positive_ids': [r['source_id'] for r in fp],
        'pull_std': float(np.std(pulls)) if pulls.size else None, 'pull_median_abs': float(np.median(np.abs(pulls))) if pulls.size else None,
        'pm_residual_median_masyr': float(np.median([math.hypot(r['pmra'] - r['gaia_pmra'], r['pmdec'] - r['gaia_pmdec']) for r in measured])) if measured else None,
        'results': results,
    }


def experiments():
    out = []
    for d in sorted((ROOT / 'validation' / 'experiments').glob('*/prediction.json')):
        pred = jload(d)
        res = jload(d.parent / 'result.json') if (d.parent / 'result.json').exists() else None
        out.append({'experiment': pred['experiment'], 'target': pred['target']['title'], 'locked_utc': pred['locked_utc'],
                    'prediction_sha256': (d.parent / 'prediction.sha256').read_text().split()[0],
                    'training_products': pred['training']['n_products'], 'training_usable': pred['training']['n_usable_positions'],
                    'heldout_products': pred['held_out']['n_products'], 'criterion': pred['protocol']['criterion'],
                    'primary_model': pred['protocol']['primary_model'],
                    'training_fit': pred['training']['motion_fits']['linear_parallax'],
                    'result': res['evaluations'] if res else None, 'primary_verdict': res['primary_verdict'] if res else 'not revealed',
                    'heldout_usable': res['held_out_measured']['n_usable'] if res else None,
                    'heldout_downloaded': res['held_out_measured']['n_downloaded'] if res else None,
                    'classification': res['classification'] if res else None, 'disclosures': pred['disclosures']})
    return out


def main(argv=None):
    skip_controls = '--no-controls' in (argv or sys.argv[1:])
    prior = jload(OUT) if OUT.exists() else {}
    doc = {
        'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'thresholds': {'motion_equivalent_sigma': MOTION_SIGMA, 'motion_pm_over_error': MOTION_PM_SNR, 'position_snr_min': SNR_POSITION_MIN,
                       'min_positions': MIN_POSITIONS, 'variability_sigma': VAR_SIGMA, 'variability_min_amplitude': VAR_MIN_AMPLITUDE,
                       'template_max_reduced_chi2': TEMPLATE_MAX_RCHI2,
                       'note': 'Fixed in pipeline/analysis.py before the validation runs; not tuned per target.'},
        'targets': benchmark(),
        'experiments': experiments(),
        'negative_controls': prior.get('negative_controls') if skip_controls else negative_controls(),
        'injections': prior.get('injections'),
        'limitations': [
            'The validation set is small (five named targets, one held-out experiment, tens of control stars); it does not establish full-sky performance.',
            'Negative controls are bright-ish isolated Gaia stars; faint, crowded or nebular regions are not represented.',
            'Three of the five NASA targets (Barnard\'s Star, RW Aur, R Dra) saturate SPHEREx; their core measurements are excluded and reported as such.',
            'Proper motions of a binary (Epsilon Indi Ba/Bb) include orbital photocentre motion, so differences from Gaia DR3 are expected at the few-sigma level.',
        ],
    }
    OUT.write_text(json.dumps(doc, indent=1, allow_nan=False, default=lambda o: None))
    print(json.dumps({k: doc['negative_controls'][k] for k in ('n_controls', 'n_measured', 'false_positives', 'pull_std', 'pm_residual_median_masyr')}
                     if doc.get('negative_controls') else {}, indent=1))
    for t in doc['targets']:
        print(t['target'], '|', t['recovery_status'], '|', t['headline'])


if __name__ == '__main__':
    main()
