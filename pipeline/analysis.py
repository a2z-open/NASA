"""Turn per-exposure measurements into a scientific investigation document.

Thresholds below are fixed in code (and documented in VALIDATION.md); they were
set before the validation runs and are not tuned per target.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math

import numpy as np

from .astrometry import from_tangent, mjd_to_iso, propagate, to_tangent
from .investigate import SNR_POSITION_MIN, quality_summary, usable_positions
from .motion import fit_motion, motion_significance

# ---- Pre-declared decision thresholds -------------------------------------------------
MOTION_SIGMA = 5.0            # likelihood-ratio equivalent sigma for "significant motion"
MOTION_PM_SNR = 5.0           # and |mu| / sigma_mu
MOTION_TENTATIVE_SIGMA = 3.0
MIN_POSITIONS = 6             # usable positions for any motion fit
MIN_VISITS_PARALLAX = 3       # visits needed before parallax is fitted
VAR_SIGMA = 5.0               # wavelength-matched visit-to-visit change significance
VAR_MIN_AMPLITUDE = 0.05      # and at least 5 % in flux (absorbs calibration systematics)
TEMPLATE_MAX_RCHI2 = 3.0      # SPIFF 10%-floor capped reduced chi-square for an acceptable match
TEMPLATE_MIN_BINS = 15
SATURATION_FRACTION = 0.5
DETECTION_SNR = 5.0
SPEED_OF_LIGHT = 299792458.0

ULTRACOOL_PREFIXES = ('M7', 'M8', 'M9', 'L', 'T', 'Y', 'd/sd', 'sd', 'esd')


def _f(v):
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def visit_of(mjd, visits):
    for v in visits or []:
        if v['mjd_start'] - 1 <= mjd <= v['mjd_end'] + 1:
            return v['id']
    return 'visit-?'


# ---------------------------------------------------------------------------
# Detections
# ---------------------------------------------------------------------------

def detections_table(rows, visits, used_ids):
    out = []
    for r in sorted(rows, key=lambda r: r.get('mjd') or 0):
        if r.get('status') == 'unreadable':
            continue
        c = r.get('centroid') or {}
        pos = r.get('position') or {}
        fol = r.get('follow') or {}
        fix = r.get('fixed') or {}
        outcome = r.get('status') if r.get('status') != 'measured' else (c.get('reason') if not c.get('ok') else 'ok')
        if outcome == 'ok' and (c.get('snr') or 0) < SNR_POSITION_MIN:
            outcome = 'low_snr'
        if outcome == 'ok' and any(f in (r.get('flags') or []) for f in ('OVERFLOW', 'NONLINEAR')):
            outcome = 'saturation_flag_near_core'
        out.append({
            'product_id': r.get('product_id'), 'mjd': r.get('mjd'), 'time_utc': mjd_to_iso(r['mjd']) if r.get('mjd') else None,
            'visit': visit_of(r.get('mjd') or 0, visits), 'detector': r.get('detector'), 'release': r.get('release'),
            'wavelength_um': _f(r.get('wavelength_um')), 'bandwidth_um': _f(r.get('bandwidth_um')),
            'ra': _f(pos.get('ra')), 'dec': _f(pos.get('dec')), 'sigma_arcsec': _f(pos.get('sigma_arcsec')),
            'snr': _f(c.get('snr')), 'flux_ujy': _f(fol.get('flux_ujy')), 'flux_err_ujy': _f(fol.get('flux_err_ujy')),
            'fixed_flux_ujy': _f(fix.get('flux_ujy')), 'fixed_flux_err_ujy': _f(fix.get('flux_err_ujy')),
            'flags': r.get('flags') or [], 'used_for_motion': r.get('product_id') in used_ids, 'outcome': outcome,
            'registration_stars': (r.get('registration') or {}).get('n_stars'),
            'archive_url': r.get('archive_url'), 'sha256': r.get('sha256'),
        })
    return out


# ---------------------------------------------------------------------------
# Motion
# ---------------------------------------------------------------------------

def analyse_motion(rows, visits, catalog=None):
    u = usable_positions(rows)
    if len(u) < MIN_POSITIONS:
        return {'status': 'insufficient', 'reason': f'{len(u)} usable positions (need {MIN_POSITIONS})',
                'models': {}, 'points': [], 'track': [], 'baseline_days': None, 'preferred_model': None,
                'significance': None, 'catalog_comparison': None}, u
    mjd = np.array([r['mjd'] for r in u])
    ra = np.array([r['position']['ra'] for r in u])
    dec = np.array([r['position']['dec'] for r in u])
    sig = np.array([r['position']['sigma_arcsec'] for r in u])
    n_visits = len({visit_of(m, visits) for m in mjd})
    fits = {'stationary': fit_motion(mjd, ra, dec, sig, model='stationary')}
    ref = fits['stationary']
    fits['linear'] = fit_motion(mjd, ra, dec, sig, model='linear', ra_ref=ref.ra_ref, dec_ref=ref.dec_ref)
    if n_visits >= MIN_VISITS_PARALLAX and len(u) >= 10:
        fits['linear_parallax'] = fit_motion(mjd, ra, dec, sig, model='linear_parallax', ra_ref=ref.ra_ref, dec_ref=ref.dec_ref,
                                             t0_mjd=fits['linear'].t0_mjd)
    if catalog and catalog.get('parallax_mas'):
        fits['linear_fixed_parallax'] = fit_motion(mjd, ra, dec, sig, model='linear_fixed_parallax', ra_ref=ref.ra_ref,
                                                   dec_ref=ref.dec_ref, t0_mjd=fits['linear'].t0_mjd,
                                                   fixed_parallax_mas=catalog['parallax_mas'])
    moving = fits.get('linear_parallax') or fits['linear']
    signif = motion_significance(fits['stationary'], moving)
    # Model preference by BIC among the SPHEREx-only models
    candidates = {k: v for k, v in fits.items() if k != 'linear_fixed_parallax'}
    preferred = min(candidates, key=lambda k: candidates[k].bic)
    if signif['equivalent_sigma'] >= MOTION_SIGMA and (signif['pm_over_error'] or 0) >= MOTION_PM_SNR:
        status = 'significant'
    elif signif['equivalent_sigma'] >= MOTION_TENTATIVE_SIGMA:
        status = 'tentative'
    else:
        status = 'not_significant'
    best = fits[preferred] if preferred != 'stationary' else moving
    # Plot data: tangent plane about the preferred model's reference point
    xi, eta = to_tangent(ra, dec, best.ra_ref, best.dec_ref)
    points = [{'mjd': float(m), 'xi': float(a), 'eta': float(b), 'sigma': float(s), 'visit': visit_of(m, visits),
               'product_id': r['product_id']} for m, a, b, s, r in zip(mjd, xi, eta, sig, u)]
    tt = np.linspace(mjd.min() - 15, mjd.max() + 15, 240)
    pr = best.predict(tt)
    track = [{'mjd': float(t), 'xi': float(a), 'eta': float(b)} for t, a, b in zip(tt, pr['xi'], pr['eta'])]
    comp = None
    s = best.summary()
    if catalog and catalog.get('pmra_masyr') is not None and 'pmra_masyr' in s:
        def dsig(a, b, ea, eb):
            if a is None or b is None or ea is None:
                return None
            return (a - b) / math.hypot(ea or 0, eb or 0) if (ea or eb) else None
        comp = {'source': catalog.get('source'), 'pmra_masyr': catalog['pmra_masyr'], 'pmdec_masyr': catalog['pmdec_masyr'],
                'parallax_mas': catalog.get('parallax_mas'),
                'd_pmra_sigma': dsig(s['pmra_masyr'], catalog['pmra_masyr'], s['pmra_err_masyr'], catalog.get('pmra_err')),
                'd_pmdec_sigma': dsig(s['pmdec_masyr'], catalog['pmdec_masyr'], s['pmdec_err_masyr'], catalog.get('pmdec_err')),
                'd_parallax_sigma': dsig(s.get('parallax_mas'), catalog.get('parallax_mas'), s.get('parallax_err_mas'), catalog.get('parallax_err'))
                if 'parallax_mas' in s else None}
    return {
        'status': status, 'preferred_model': preferred, 'reported_model': best.model,
        'models': {k: v.summary() for k, v in fits.items()}, 'significance': signif,
        'catalog_comparison': comp, 'points': points, 'track': track,
        'baseline_days': float(mjd.max() - mjd.min()), 'n_visits': n_visits,
        'thresholds': {'equivalent_sigma': MOTION_SIGMA, 'pm_over_error': MOTION_PM_SNR},
    }, u


def track_from_motion(motion):
    if not motion or motion.get('status') not in ('significant', 'tentative'):
        return None
    m = motion['models'][motion['reported_model']]
    p = m
    ref = m['reference']
    # xi0/eta0 are not in the summary; recover via the plotted track at t0 instead
    return None if 'pmra_masyr' not in p else {'ref': ref, 'pmra': p['pmra_masyr'], 'pmdec': p['pmdec_masyr'],
                                               'parallax': p.get('parallax_mas', p.get('fixed_parallax_mas', 0.0)) or 0.0}


# ---------------------------------------------------------------------------
# Spectrum
# ---------------------------------------------------------------------------

def load_bins():
    try:
        from spiff.spherex_binning import load_spherex_bins
        b = load_spherex_bins()
        return b['wavelength_um'].to_numpy(float), b['wavelength_wid_um'].to_numpy(float)
    except Exception:  # noqa: BLE001 - SPIFF optional; fall back to the same 102-bin table shape
        centers = []
        for lo, hi, n in ((0.75, 1.09, 17), (1.10, 1.62, 17), (1.63, 2.41, 17), (2.42, 3.82, 17), (3.83, 4.41, 17), (4.42, 5.00, 17)):
            e = np.geomspace(lo, hi, n + 1)
            centers += list(np.sqrt(e[1:] * e[:-1]))
        c = np.array(centers)
        return c, np.gradient(c)


def _bin(points_w, points_f, points_e, centers):
    idx = np.clip(np.searchsorted(centers, points_w), 1, len(centers) - 1)
    left = idx - 1
    use_right = np.abs(centers[idx] - points_w) < np.abs(centers[left] - points_w)
    nearest = np.where(use_right, idx, left)
    out = []
    for i in range(len(centers)):
        sel = nearest == i
        n = int(sel.sum())
        if n == 0:
            out.append((0, None, None))
            continue
        f, e = points_f[sel], points_e[sel]
        w = 1 / e ** 2
        mean = float(np.sum(w * f) / np.sum(w))
        err = float(1 / math.sqrt(np.sum(w)))
        if n >= 3:
            chi2r = float(np.sum(w * (f - mean) ** 2) / (n - 1))
            err *= math.sqrt(max(chi2r, 1.0))
        out.append((n, mean, err))
    return out


def ujy_to_flambda(w_um, f_ujy):
    w_m = np.asarray(w_um) * 1e-6
    return np.asarray(f_ujy) * 1e-6 * 1e-32 * SPEED_OF_LIGHT / w_m ** 2 * 1e-10


def flambda_to_ujy(w_um, fl):
    w_m = np.asarray(w_um) * 1e-6
    return np.asarray(fl) / (1e-6 * 1e-32 * SPEED_OF_LIGHT / w_m ** 2 * 1e-10)


def template_match(binned):
    """SPIFF (Gagne et al. 2026) template comparison on the 102-bin spectrum."""
    try:
        import pandas as pd
        import spiff.autotype as at
    except Exception as error:  # noqa: BLE001
        return {'status': 'insufficient', 'library': 'SPIFF templates unavailable', 'best': None, 'alternatives': [],
                'model_curve': None, 'reason': f'SPIFF not importable: {error}'}
    rows = [b for b in binned if b['flux_ujy'] is not None and b['flux_ujy'] > 0 and b['flux_err_ujy']]
    library = 'SPIFF SPHEREx templates (Gagné et al. 2026; M4–Y0 field, low-gravity and subdwarf grids)'
    if len(rows) < TEMPLATE_MIN_BINS:
        return {'status': 'insufficient', 'library': library, 'best': None, 'alternatives': [], 'model_curve': None,
                'reason': f'{len(rows)} spectral bins with positive flux (need {TEMPLATE_MIN_BINS}).'}
    w = np.array([b['center_um'] for b in rows])
    f = np.array([b['flux_ujy'] for b in rows])
    e = np.array([b['flux_err_ujy'] for b in rows])
    df = pd.DataFrame({'wavelength_angstrom': w * 1e4, 'flux_flambda': ujy_to_flambda(w, f),
                       'flux_flambda_unc': ujy_to_flambda(w, e)})
    templates = at._load_templates()
    res = at._autotype(df, templates, drop_worst_n=5, chi2_sigma_cap=5.0, nonfield_odds_k=500.0,
                       nonfield_extreme_odds_k=500000.0)
    res = res[res['selection_score'].notna()]
    if res.empty:
        return {'status': 'insufficient', 'library': library, 'best': None, 'alternatives': [], 'model_curve': None,
                'reason': 'No template overlapped the measured wavelengths.'}
    top = res.iloc[0]
    rchi2 = float(top['reduced_chi2_10pct_cap'])
    best = {'spectral_type': str(top['spectral_type']), 'grid_type': str(top['grid_type']), 'reduced_chi2': rchi2,
            'n_used': int(top['n_used']), 'scale': float(top['scale_s']), 'template_id': int(top['template_id'])}
    alts = [{'spectral_type': str(r['spectral_type']), 'grid_type': str(r['grid_type']),
             'reduced_chi2': float(r['reduced_chi2_10pct_cap'])} for _, r in res.iloc[1:6].iterrows()]
    t = templates[best['template_id']]
    tw = np.asarray(t['wavelength_angstrom'], float) / 1e4
    tf = np.asarray(t['flux_flambda'], float) * best['scale']
    curve = [{'wavelength_um': float(a), 'flux_ujy': float(b)} for a, b in zip(tw, flambda_to_ujy(tw, tf)) if np.isfinite(b)]
    ultracool = best['spectral_type'].startswith(ULTRACOOL_PREFIXES)
    coldest = max((v for v in templates.values() if str(v['spectral_type']).startswith('Y')),
                  key=lambda v: v['spectral_type_number'], default=None)
    at_cold_edge = coldest is not None and best['spectral_type'] == str(coldest['spectral_type'])
    best['at_library_cold_limit'] = at_cold_edge
    if rchi2 <= TEMPLATE_MAX_RCHI2 and best['n_used'] >= TEMPLATE_MIN_BINS:
        status = 'matched' if ultracool else 'out_of_domain'
        reason = (f"Best template {best['spectral_type']} ({best['grid_type']}) with reduced chi-square {rchi2:.2f} over {best['n_used']} bins."
                  if ultracool else f"Closest library template is {best['spectral_type']}, which is outside the ultracool-dwarf domain this library is built for; treat as indicative only.")
        if at_cold_edge:
            reason += (f" {best['spectral_type']} is the coldest template in the library, so the true type may be later (colder): "
                       f"read this as 'at least as cold as {best['spectral_type']}', not as a precise type.")
    else:
        status = 'poor_fit'
        reason = (f"No template fits well: best is {best['spectral_type']} with reduced chi-square {rchi2:.1f} "
                  f"(threshold {TEMPLATE_MAX_RCHI2}). The library covers M4–Y dwarfs only; ordinary stars, giants and "
                  f"blended sources are expected to fit poorly.")
    return {'status': status, 'library': library, 'best': best, 'alternatives': alts, 'model_curve': curve, 'reason': reason,
            'threshold_reduced_chi2': TEMPLATE_MAX_RCHI2}


def analyse_spectrum(rows, visits):
    pts = []
    sat = 0
    measured = 0
    wing_pts = []
    for r in rows:
        w = r.get('wing') or {}
        if r.get('status') == 'measured' and w.get('ok') and r.get('wavelength_um') is not None and w.get('flux_err_ujy') \
                and (w.get('chi2r') or 0) < 50:
            wing_pts.append({'wavelength_um': r['wavelength_um'], 'bandwidth_um': r.get('bandwidth_um'), 'flux_ujy': w['flux_ujy'],
                             'flux_err_ujy': w['flux_err_ujy'], 'detector': r['detector'], 'mjd': r['mjd'],
                             'visit': visit_of(r['mjd'], visits), 'product_id': r['product_id'], 'method': 'wing',
                             'fixed_flux_ujy': None, 'fixed_flux_err_ujy': None})
        if r.get('status') != 'measured':
            continue
        measured += 1
        flags = r.get('flags') or []
        if any(x in flags for x in ('OVERFLOW', 'NONLINEAR')):
            sat += 1
            continue
        fol = r.get('follow') or {}
        if not fol.get('ok') or r.get('wavelength_um') is None or not fol.get('flux_err_ujy'):
            continue
        if fol.get('chi2r') and fol['chi2r'] > 50:
            continue
        pts.append({'wavelength_um': r['wavelength_um'], 'bandwidth_um': r.get('bandwidth_um'), 'flux_ujy': fol['flux_ujy'],
                    'flux_err_ujy': fol['flux_err_ujy'], 'detector': r['detector'], 'mjd': r['mjd'],
                    'visit': visit_of(r['mjd'], visits), 'product_id': r['product_id'],
                    'fixed_flux_ujy': (r.get('fixed') or {}).get('flux_ujy'),
                    'fixed_flux_err_ujy': (r.get('fixed') or {}).get('flux_err_ujy')})
    wing_rows = [r.get('wing') for r in rows if r.get('wing')]
    wing_attempt = None
    if wing_rows:
        conv = [w for w in wing_rows if w.get('ok')]
        chis = [w['chi2r'] for w in conv if w.get('chi2r') is not None]
        med = float(np.median(chis)) if chis else None
        wing_attempt = {'n_attempted': len(wing_rows), 'n_converged': len(conv), 'n_accepted': len(wing_pts),
                        'median_chi2r': med, 'acceptance': 'reduced chi-square < 50',
                        'summary': (f'Experimental wing photometry was attempted on {len(wing_rows)} saturated exposures; '
                                    f'{len(conv)} had enough unflagged pixels to fit, but the release ePSF describes the wings poorly '
                                    f'(median reduced chi-square {med:.0f}), so {len(wing_pts)} passed the acceptance cut.')
                        if med is not None else f'Experimental wing photometry was attempted on {len(wing_rows)} saturated exposures; '
                                                f'none had enough unflagged pixels inside the ePSF footprint (±3.3 px).'}
    centers, widths = load_bins()
    method = ('Forced ePSF photometry on native pixels at the motion-corrected (followed) position in every exposure; '
              'wavelength from the spectral WCS at that pixel; inverse-variance means in the 102 SPHEREx/SPIFF bins.')
    wing_mode = False
    if sat >= SATURATION_FRACTION * max(measured, 1) and len(wing_pts) >= 10:
        # Saturation-dominated source: use PSF-wing photometry (experimental) instead of the core.
        pts = wing_pts
        wing_mode = True
        method = ('EXPERIMENTAL saturated-core wing photometry: the release ePSF is fitted only to unflagged pixels around a '
                  'saturated core (OVERFLOW, NONLINEAR, SUR_ERROR, BLOOM and TRANSIENT pixels excluded), with the position fixed '
                  'at the catalogue track. Absolute fluxes carry PSF-model systematics; same-wavelength ratios between visits are more robust.')
    if len(pts) < 5:
        return {'status': 'insufficient' if sat < SATURATION_FRACTION * max(measured, 1) else 'saturated',
                'method': method, 'points': pts, 'binned': [],
                'coverage': {'n_bins_filled': 0, 'n_bins_total': len(centers), 'range_um': None},
                'fixed_vs_follow': None, 'templates': None, 'n_saturated': sat, 'n_measured': measured, 'wing_mode': wing_mode,
                'wing_attempt': wing_attempt}
    w = np.array([p['wavelength_um'] for p in pts])
    f = np.array([p['flux_ujy'] for p in pts])
    e = np.array([p['flux_err_ujy'] for p in pts])
    fol_b = _bin(w, f, e, centers)
    fx = [(p['wavelength_um'], p['fixed_flux_ujy'], p['fixed_flux_err_ujy']) for p in pts if p['fixed_flux_ujy'] is not None and p['fixed_flux_err_ujy']]
    fix_b = _bin(np.array([a for a, _, _ in fx]), np.array([b for _, b, _ in fx]), np.array([c for _, _, c in fx]), centers) if fx else [(0, None, None)] * len(centers)
    binned = []
    for i, (c, wd) in enumerate(zip(centers, widths)):
        n, m, er = fol_b[i]
        _, fm, fe = fix_b[i]
        binned.append({'bin': i + 1, 'center_um': float(c), 'width_um': float(wd), 'n': n, 'flux_ujy': m, 'flux_err_ujy': er,
                       'fixed_flux_ujy': fm, 'fixed_flux_err_ujy': fe})
    filled = [b for b in binned if b['n'] > 0]
    ratios = [b['fixed_flux_ujy'] / b['flux_ujy'] for b in filled
              if b['fixed_flux_ujy'] is not None and b['flux_ujy'] and b['flux_ujy'] > 5 * (b['flux_err_ujy'] or 1e9)]
    fvf = None
    if ratios:
        med = float(np.median(ratios))
        fvf = {'median_ratio': med, 'n_bins': len(ratios),
               'note': (f'Measured at one fixed sky position, the source keeps {100 * med:.0f}% of the flux recovered by '
                        f'following its motion (median over {len(ratios)} bins).')}
    snr_bins = sum(1 for b in filled if b['flux_ujy'] and b['flux_err_ujy'] and b['flux_ujy'] / b['flux_err_ujy'] >= DETECTION_SNR)
    status = 'measured' if snr_bins >= 30 else ('partial' if snr_bins >= 5 else 'insufficient')
    if wing_mode:
        templates = {'status': 'out_of_domain', 'library': 'SPIFF SPHEREx templates', 'best': None, 'alternatives': [], 'model_curve': None,
                     'reason': 'Template typing is not attempted on saturated-core wing photometry.'}
    elif status != 'insufficient':
        templates = template_match(binned)
    else:
        templates = {'status': 'insufficient', 'library': 'SPIFF SPHEREx templates', 'best': None, 'alternatives': [], 'model_curve': None,
                     'reason': f'Only {snr_bins} bins detected at S/N >= {DETECTION_SNR}.'}
    return {'status': status, 'method': method, 'wing_mode': wing_mode, 'wing_attempt': wing_attempt,
            'points': pts, 'binned': binned,
            'coverage': {'n_bins_filled': len(filled), 'n_bins_detected': snr_bins, 'n_bins_total': len(centers),
                         'range_um': [float(w.min()), float(w.max())]},
            'fixed_vs_follow': fvf, 'templates': templates, 'n_saturated': sat, 'n_measured': measured}


# ---------------------------------------------------------------------------
# Variability (wavelength-matched)
# ---------------------------------------------------------------------------

def analyse_variability(spectrum, visits):
    pts = spectrum.get('points') or []
    n_sat = spectrum.get('n_saturated', 0)
    n_meas = spectrum.get('n_measured', 0)
    lc = [{'mjd': p['mjd'], 'flux_ujy': p['flux_ujy'], 'flux_err_ujy': p['flux_err_ujy'], 'wavelength_um': p['wavelength_um'],
           'detector': p['detector'], 'visit': p['visit']} for p in pts]
    if n_meas and n_sat >= SATURATION_FRACTION * n_meas and not spectrum.get('wing_mode'):
        wa = (spectrum.get('wing_attempt') or {}).get('summary')
        return {'status': 'saturated', 'reason': f'{n_sat} of {n_meas} exposures are saturated or nonlinear at the source.' + (f' {wa}' if wa else ''),
                'naive': None, 'matched': None, 'light_curve': lc}
    if len(pts) < 6:
        return {'status': 'insufficient', 'reason': 'Too few unsaturated photometric measurements.', 'naive': None, 'matched': None, 'light_curve': lc}
    f = np.array([p['flux_ujy'] for p in pts])
    e = np.array([p['flux_err_ujy'] for p in pts])
    good = (f > 0) & (f >= 10 * e)      # high-S/N points only, so the ratio is not driven by noise near zero
    naive = {'description': 'Every exposure in time order, regardless of wavelength. Because SPHEREx sees a different '
                            'wavelength in each exposure, most of this apparent change is the source spectrum, not time variability.',
             'max_ratio': float(f[good].max() / f[good].min()) if good.sum() >= 2 else None,
             'max_ratio_basis': 'brightest / faintest exposure among those with S/N >= 10',
             'points': [{'mjd': p['mjd'], 'flux_ujy': p['flux_ujy'], 'wavelength_um': p['wavelength_um']} for p in pts]}
    centers, _ = load_bins()
    idx = np.clip(np.searchsorted(centers, [p['wavelength_um'] for p in pts]), 1, len(centers) - 1)
    wv = np.array([p['wavelength_um'] for p in pts])
    nearest = np.where(np.abs(centers[idx] - wv) < np.abs(centers[idx - 1] - wv), idx, idx - 1)
    vids = sorted({p['visit'] for p in pts})
    comps = []
    for i in range(len(vids) - 1):
        a, b = vids[i], vids[i + 1]
        for k in sorted(set(nearest)):
            sa = [p for p, n in zip(pts, nearest) if n == k and p['visit'] == a]
            sb = [p for p, n in zip(pts, nearest) if n == k and p['visit'] == b]
            if not sa or not sb:
                continue
            def wm(ss):
                ww = np.array([1 / s['flux_err_ujy'] ** 2 for s in ss])
                ff = np.array([s['flux_ujy'] for s in ss])
                return float(np.sum(ww * ff) / ww.sum()), float(1 / math.sqrt(ww.sum()))
            fa, ea = wm(sa)
            fb, eb = wm(sb)
            if fa <= 0 or fb <= 0 or fa < 5 * ea or fb < 5 * eb:
                continue
            ratio = fb / fa
            rerr = ratio * math.hypot(ea / fa, eb / fb)
            comps.append({'center_um': float(centers[k]), 'visit_a': a, 'visit_b': b, 'ratio': ratio, 'ratio_err': rerr,
                          'sigma': (ratio - 1) / rerr if rerr > 0 else None, 'n_a': len(sa), 'n_b': len(sb)})
    if len(comps) < 3:
        return {'status': 'insufficient', 'reason': 'Fewer than 3 wavelength bins were observed in two different visits at S/N >= 5.',
                'naive': naive, 'matched': {'description': 'Same wavelength bin, different visits.', 'comparisons': comps,
                                             'median_log_ratio': None, 'chi2_reduced': None}, 'light_curve': lc}
    pairs = {}
    for c in comps:
        pairs.setdefault((c['visit_a'], c['visit_b']), []).append(c)
    pair_summ = []
    variable = False
    for (a, b), cs in pairs.items():
        lr = np.array([math.log(c['ratio']) for c in cs])
        le = np.array([c['ratio_err'] / c['ratio'] for c in cs])
        w = 1 / le ** 2
        mean = float(np.sum(w * lr) / w.sum())
        err = float(1 / math.sqrt(w.sum()))
        chi2r = float(np.sum(w * (lr - mean) ** 2) / max(len(lr) - 1, 1))
        err_eff = err * math.sqrt(max(chi2r, 1.0))
        # robust alternative: median with bootstrap-free MAD error
        med = float(np.median(lr))
        mad_err = float(1.4826 * np.median(np.abs(lr - med)) / math.sqrt(len(lr))) if len(lr) > 2 else err_eff
        sig = abs(mean) / err_eff if err_eff > 0 else 0
        is_var = sig >= VAR_SIGMA and abs(math.exp(mean) - 1) >= VAR_MIN_AMPLITUDE
        variable |= is_var
        pair_summ.append({'visit_a': a, 'visit_b': b, 'n_bins': len(cs), 'mean_ratio': math.exp(mean),
                          'mean_ratio_err': math.exp(mean) * err_eff, 'median_ratio': math.exp(med),
                          'median_ratio_err': math.exp(med) * mad_err, 'significance_sigma': sig,
                          'bin_scatter_chi2r': chi2r, 'variable': is_var})
    all_lr = np.array([math.log(c['ratio']) for c in comps])
    return {
        'status': 'variable' if variable else 'not_detected',
        'method': 'wing' if spectrum.get('wing_mode') else 'core',
        'thresholds': {'sigma': VAR_SIGMA, 'min_amplitude': VAR_MIN_AMPLITUDE},
        'naive': naive,
        'matched': {'description': 'Flux in the same SPHEREx wavelength bin compared between visits. Only this comparison can reveal true time variability.',
                    'comparisons': comps, 'visit_pairs': pair_summ, 'median_log_ratio': float(np.median(all_lr)),
                    'chi2_reduced': None},
        'light_curve': lc,
    }


# ---------------------------------------------------------------------------
# Evidence model
# ---------------------------------------------------------------------------

def neighbours(catalog_stars, ra, dec, mjd, radius_arcsec=12.0):
    out = []
    for s in catalog_stars or []:
        if s.get('ra') is None:
            continue
        if s.get('pmra') is not None:
            p = propagate(s['ra'], s['dec'], 57388.5, s['pmra'], s['pmdec'], s.get('parallax') or 0, [mjd])
            sra, sdec = float(p.ra[0]), float(p.dec[0])
        else:
            sra, sdec = s['ra'], s['dec']
        xi, eta = to_tangent(sra, sdec, ra, dec)
        d = float(math.hypot(xi, eta))
        if d <= radius_arcsec:
            out.append({'source_id': s['source_id'], 'sep_arcsec': d, 'g': s.get('g'), 'pmra': s.get('pmra'), 'pmdec': s.get('pmdec'),
                        'parallax': s.get('parallax')})
    return sorted(out, key=lambda x: x['sep_arcsec'])


def evaluate(doc, *, identification=None, catalog_stars=None, known_blend=None):
    """Rule-based, inspectable evaluation of competing hypotheses H0-H6."""
    obs = doc['observations']
    motion = doc.get('motion') or {}
    spec = doc.get('spectrum') or {}
    var = doc.get('variability') or {}
    dets = doc.get('detections') or []
    n_use = obs['n_usable_positions']
    n_vis = len({d['visit'] for d in dets if d['outcome'] == 'ok'})
    n_sat = sum(1 for d in dets if d['outcome'] in ('core_saturated', 'saturation_flag_near_core'))
    n_meas = sum(1 for d in dets if d['outcome'] not in ('outside_cutout',))
    H = []
    halo = doc.get('halo_variability') or {}
    ss = doc.get('solar_system') or {}
    ms = motion.get('status')
    sig = (motion.get('significance') or {})
    rep = (motion.get('models') or {}).get(motion.get('reported_model') or '', {})
    saturated = n_meas and n_sat >= SATURATION_FRACTION * n_meas

    # H6 insufficient evidence
    insufficient = n_use < MIN_POSITIONS or n_vis < 2
    H.append({'id': 'H6', 'name': 'Insufficient evidence', 'status': 'supported' if insufficient else 'disfavored',
              'evidence': [f'{n_use} usable position measurements across {n_vis} visit(s).'] +
                          ([f'{n_sat} of {n_meas} exposures are saturated at the source core.'] if saturated else [])})
    # H0 stationary / H1 moving
    if saturated and ms in ('significant', 'tentative', 'not_significant'):
        note = (f'{n_sat} of {n_meas} exposures are saturated at the core; the {n_use} remaining positions come from the '
                f'faintest wavelengths and sit beside saturated wings, so systematic errors dominate. Motion is not evaluated.')
        H.append({'id': 'H0', 'name': 'Stationary astronomical source', 'status': 'not_testable', 'evidence': [note]})
        H.append({'id': 'H1', 'name': 'Moving astronomical source', 'status': 'not_testable', 'evidence': [note]})
        ms = 'saturated'
    elif ms == 'significant':
        pm = rep.get('pm_total_masyr')
        H.append({'id': 'H0', 'name': 'Stationary astronomical source', 'status': 'disfavored',
                  'evidence': [f"A stationary model is rejected: delta chi-square {sig.get('delta_chi2', 0):.0f} "
                               f"(about {sig.get('equivalent_sigma', 0):.0f} sigma if the per-point errors are realistic)."]})
        H.append({'id': 'H1', 'name': 'Moving astronomical source', 'status': 'supported',
                  'evidence': [f"Proper motion {pm:.0f} ± {rep.get('pm_total_err_masyr', 0):.0f} mas/yr from {n_use} exposures over "
                               f"{motion.get('baseline_days', 0):.0f} days; model reduced chi-square {rep.get('chi2_reduced', 0):.2f}."]
                  + ([f"Parallax {rep['parallax_mas']:.0f} ± {rep['parallax_err_mas']:.0f} mas measured from SPHEREx alone."] if 'parallax_mas' in rep else [])})
    elif ms == 'tentative':
        H.append({'id': 'H0', 'name': 'Stationary astronomical source', 'status': 'possible',
                  'evidence': [f"Motion model preferred at {sig.get('equivalent_sigma', 0):.1f} sigma with proper motion "
                               f"{(sig.get('pm_over_error') or 0):.1f} times its error; the thresholds are {MOTION_SIGMA:.0f} sigma and "
                               f"{MOTION_PM_SNR:.0f} times."]})
        H.append({'id': 'H1', 'name': 'Moving astronomical source', 'status': 'possible', 'evidence': ['Tentative motion; more epochs needed.']})
    elif ms == 'not_significant':
        lim = rep.get('pm_total_err_masyr')
        H.append({'id': 'H0', 'name': 'Stationary astronomical source', 'status': 'supported',
                  'evidence': [f"No significant motion ({sig.get('equivalent_sigma', 0):.1f} sigma)" + (f"; 3-sigma limit about {3 * lim:.0f} mas/yr." if lim else '.')]})
        H.append({'id': 'H1', 'name': 'Moving astronomical source', 'status': 'disfavored',
                  'evidence': ['Measured positions are consistent with no motion at the achieved precision.']})
    else:
        H.append({'id': 'H0', 'name': 'Stationary astronomical source', 'status': 'not_testable', 'evidence': [motion.get('reason', 'Too few usable positions.')]})
        H.append({'id': 'H1', 'name': 'Moving astronomical source', 'status': 'not_testable', 'evidence': [motion.get('reason', 'Too few usable positions.')]})
    # H2 variability
    vs = var.get('status')
    if vs == 'variable':
        best = max((var['matched']['visit_pairs']), key=lambda p: p['significance_sigma'])
        H.append({'id': 'H2', 'name': 'Variable astronomical source', 'status': 'supported',
                  'evidence': [f"Wavelength-matched flux changed by a factor {best['mean_ratio']:.2f} ± {best['mean_ratio_err']:.2f} between "
                               f"{best['visit_a']} and {best['visit_b']} ({best['significance_sigma']:.0f} sigma over {best['n_bins']} matched bins)."]
                  + (['Measured with experimental saturated-core wing photometry: treat as indicative.'] if var.get('method') == 'wing' else [])})
    elif vs == 'not_detected':
        pr = var['matched']['visit_pairs']
        H.append({'id': 'H2', 'name': 'Variable astronomical source', 'status': 'disfavored',
                  'evidence': [f"Wavelength-matched visit-to-visit ratios: " + ', '.join(f"{p['mean_ratio']:.3f} ± {p['mean_ratio_err']:.3f}" for p in pr) + '.']})
    elif halo.get('status') in ('variable', 'not_detected'):
        hv = [v for v in halo['visits'][1:] if v.get('sigma') is not None]
        txt = ', '.join(f"{v['visit']} / visit-1 = {v['ratio']:.2f} ± {v['ratio'] * v['err_vs_first']:.2f} ({v['sigma']:.1f} sigma)" for v in hv)
        H.append({'id': 'H2', 'name': 'Variable astronomical source', 'status': 'supported' if halo['status'] == 'variable' else 'disfavored',
                  'evidence': [f"The core is saturated, so brightness was measured from the unsaturated halo ({halo['ring_pixels'][0]:.0f}-{halo['ring_pixels'][1]:.0f} "
                               f"pixels from the star) at matched wavelength: {txt}.",
                               'Experimental method. On control stars that are not large-amplitude variables the same measurement stays flat '
                               '(see validation/halo_results.json).']})
    else:
        H.append({'id': 'H2', 'name': 'Variable astronomical source', 'status': 'not_testable',
                  'evidence': [var.get('reason', 'Variability not measured.')]})
    # H3 blending
    blend_ev = []
    blend = 'disfavored'
    src = doc['source']
    mjd_ref = (motion.get('models') or {}).get(motion.get('reported_model') or '', {}).get('reference', {}).get('t0_mjd') or 61000.0
    nb = [n for n in neighbours(catalog_stars, src['ra'], src['dec'], mjd_ref, 12.0) if n['sep_arcsec'] > 0.5]
    if known_blend:
        blend = 'supported'
        blend_ev.append(known_blend)
    if nb:
        blend = 'possible' if blend != 'supported' else blend
        blend_ev.append(f"{len(nb)} Gaia DR3 source(s) within 12 arcsec (2 SPHEREx pixels); nearest {nb[0]['sep_arcsec']:.1f} arcsec, G = {nb[0]['g'] or float('nan'):.1f}.")
    chi = [d for d in dets if d['outcome'] == 'ok']
    if not blend_ev:
        blend_ev.append('No Gaia DR3 neighbour within 2 SPHEREx pixels.')
    H.append({'id': 'H3', 'name': 'Blended or overlapping sources', 'status': blend, 'evidence': blend_ev})
    # H4 artifact
    if n_use >= 5 and n_vis >= 2:
        H.append({'id': 'H4', 'name': 'Instrumental or processing artifact', 'status': 'disfavored',
                  'evidence': [f'Detected in {n_use} independent exposures across {n_vis} visits, on multiple detectors and wavelengths.']})
    elif n_use >= 1:
        H.append({'id': 'H4', 'name': 'Instrumental or processing artifact', 'status': 'possible',
                  'evidence': ['Detected in too few independent exposures to rule out an artifact.']})
    else:
        H.append({'id': 'H4', 'name': 'Instrumental or processing artifact', 'status': 'not_testable', 'evidence': ['No usable detections.']})
    # H5 solar-system object
    stellar = ms == 'significant' and rep.get('chi2_reduced', 99) < 3 and (motion.get('baseline_days') or 0) > 150
    ev5 = []
    if stellar:
        model_txt = 'proper motion plus annual parallax' if 'parallax_mas' in rep else 'linear proper motion'
        ev5.append(f"Positions over {motion.get('baseline_days', 0):.0f} days follow {model_txt} of a few arcsec per year "
                   f"(reduced chi-square {rep.get('chi2_reduced', 0):.2f}); solar-system bodies move arcseconds to arcminutes per hour "
                   f"and would not repeat a stellar track across visits.")
    if ss.get('status') == 'none_found':
        ev5.append(f"No known asteroid or comet lies within {ss['radius_arcsec']:.0f} arcsec of the source at any of the "
                   f"{ss['n_epochs_checked']} observation times checked ({ss['service']}).")
        st5 = 'disfavored'
    elif ss.get('status') == 'found':
        names = sorted({m['name'] for m in ss['matches'] if m.get('name')})
        ev5.append(f"Known solar-system bodies passed within {ss['radius_arcsec']:.0f} arcsec during {len(ss['matches'])} of the checked times: "
                   + ', '.join(names[:5]) + '. Detections at those times may be the asteroid, not the source.')
        st5 = 'disfavored' if stellar else 'possible'
    elif stellar:
        st5 = 'disfavored'
    else:
        st5 = 'not_testable'
        ev5.append('The solar-system catalogue (IMCCE SkyBoT) was not queried or could not be reached; not evaluated.')
    H.append({'id': 'H5', 'name': 'Known solar-system object', 'status': st5, 'evidence': ev5})
    H.sort(key=lambda h: h['id'])

    verdicts = []
    if saturated:
        verdicts.append({'code': 'saturated', 'label': 'Saturated: core measurements unreliable', 'strength': 'supported'})
    if identification and ms in ('significant', 'not_significant') and not saturated:
        comp = motion.get('catalog_comparison')
        verdicts.append({'code': 'known_source_recovered', 'label': f"Known source recovered ({identification})", 'strength': 'supported'})
    if ms == 'significant':
        verdicts.append({'code': 'motion_supported', 'label': 'Evidence supports astronomical motion', 'strength': 'supported'})
    elif ms == 'tentative':
        verdicts.append({'code': 'motion_supported', 'label': 'Tentative motion', 'strength': 'tentative'})
    if vs == 'variable':
        wing = var.get('method') == 'wing'
        verdicts.append({'code': 'variability_supported',
                         'label': 'Evidence supports temporal variability' + (' (wing photometry, experimental)' if wing else ''),
                         'strength': 'tentative' if wing else 'supported'})
    if halo.get('status') == 'variable' and vs != 'variable':
        verdicts.insert(0, {'code': 'variability_supported', 'label': 'Brightness changed between visits (measured from the unsaturated halo, experimental)',
                            'strength': 'supported'})
    if blend in ('possible', 'supported'):
        verdicts.append({'code': 'possible_blend', 'label': 'Possible blended source' if blend == 'possible' else 'Blended source',
                         'strength': 'tentative' if blend == 'possible' else 'supported'})
    tm = (spec.get('templates') or {})
    if tm.get('status') == 'matched':
        verdicts.append({'code': 'ultracool_candidate', 'label': f"Spectrum consistent with an ultracool dwarf ({tm['best']['spectral_type']})",
                         'strength': 'supported' if tm['best']['reduced_chi2'] < 2 else 'tentative'})
    if not identification and doc['kind'] == 'user' and not nb and n_use >= 5:
        verdicts.append({'code': 'catalog_unmatched_followup', 'label': 'No Gaia DR3 counterpart: needs follow-up (not a discovery)', 'strength': 'tentative'})
    if insufficient and not any(v['code'] == 'saturated' for v in verdicts):
        verdicts.append({'code': 'insufficient_evidence', 'label': 'Insufficient evidence', 'strength': 'supported'})
    return H, verdicts


def headline(doc):
    v = {x['code']: x for x in doc['summary']['verdicts']}
    motion = doc.get('motion') or {}
    rep = (motion.get('models') or {}).get(motion.get('reported_model') or '', {})
    spec = doc.get('spectrum') or {}
    parts = []
    if 'motion_supported' in v and v['motion_supported']['strength'] == 'supported':
        parts.append(f"Moves {rep.get('pm_total_masyr', 0) / 1000:.2f}″/yr across {doc['observations']['n_usable_positions']} SPHEREx exposures")
    halo = doc.get('halo_variability') or {}
    hv = [x for x in (halo.get('visits') or [])[1:] if x.get('sigma') is not None]
    if halo.get('status') == 'variable' and hv:
        big = max(hv, key=lambda x: abs(x['ratio'] - 1))
        word = 'faded' if big['ratio'] < 1 else 'brightened'
        parts.append(f"{word} by {abs(big['ratio'] - 1) * 100:.0f}% between visits, measured from its unsaturated halo")
    elif 'variability_supported' in v:
        parts.append('brightness changes at matched wavelengths')
    if 'ultracool_candidate' in v:
        parts.append(f"spectrum matches a {spec['templates']['best']['spectral_type']} template")
    if 'saturated' in v:
        if halo.get('status') == 'variable':
            parts.append('its core is saturated')
        elif halo.get('status') == 'not_detected' and hv:
            parts.append(f"too bright: SPHEREx cores are saturated; halo brightness steady within {max(abs(x['ratio'] - 1) for x in hv) * 100:.0f}%")
        else:
            parts.append('too bright: SPHEREx cores are saturated')
    if 'insufficient_evidence' in v and not parts:
        parts.append('not enough clean measurements for a conclusion')
    if not parts:
        parts.append('no significant motion or variability detected')
    text = '; '.join(parts)
    return text[0].upper() + text[1:] + '.'


def build_investigation(rows, *, inv_id, kind, title, field_id, source, visits, identification=None, catalog=None,
                        catalog_stars=None, known_blend=None, extra_limitations=(), provenance=None, solar_system=None, halo=None):
    motion, used = analyse_motion(rows, visits, catalog)
    used_ids = {r['product_id'] for r in used}
    dets = detections_table(rows, visits, used_ids)
    spectrum = analyse_spectrum(rows, visits)
    variability = analyse_variability(spectrum, visits)
    measured = [d for d in dets if d['outcome'] != 'outside_cutout']
    wl = [d['wavelength_um'] for d in measured if d['wavelength_um']]
    times = [d['mjd'] for d in measured if d['mjd']]
    doc = {
        'id': inv_id, 'kind': kind, 'title': title, 'field_id': field_id,
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'status': 'ready', 'message': None,
        'source': source,
        'observations': {'n_total': len(rows), 'n_measured': len(measured), 'n_usable_positions': len(used),
                         'date_range': [mjd_to_iso(min(times)), mjd_to_iso(max(times))] if times else None,
                         'wavelength_coverage_um': [min(wl), max(wl)] if wl else None,
                         'visits': visits, 'quality': quality_summary(rows)},
        'detections': dets, 'motion': motion, 'spectrum': spectrum, 'variability': variability,
    }
    if solar_system is not None:
        doc['solar_system'] = solar_system
    if halo is not None:
        doc['halo_variability'] = halo
    hyps, verdicts = evaluate(doc, identification=identification, catalog_stars=catalog_stars, known_blend=known_blend)
    doc['hypotheses'] = hyps
    doc['summary'] = {'verdicts': verdicts}
    doc['summary']['headline'] = headline(doc)
    doc['summary']['one_liner'] = one_liner(doc)
    doc['limitations'] = limitations(doc) + list(extra_limitations)
    doc['follow_up'] = follow_up(doc)
    doc['provenance'] = provenance or {}
    return doc


def one_liner(doc):
    v = {x['code'] for x in doc['summary']['verdicts']}
    halo = doc.get('halo_variability') or {}
    hv = [x for x in (halo.get('visits') or [])[1:] if x.get('sigma') is not None]
    if halo.get('status') == 'variable' and hv:
        big = max(hv, key=lambda x: abs(x['ratio'] - 1))
        return (f"The core saturates the detector, so brightness is measured from the unsaturated ring of light around the star: "
                f"it {'faded' if big['ratio'] < 1 else 'brightened'} by {abs(big['ratio'] - 1) * 100:.0f}% between visits "
                f"({big['sigma']:.1f} sigma). An experimental method, checked on stars that do not vary.")
    spec = doc.get('spectrum') or {}
    tm = spec.get('templates') or {}
    s = []
    n = doc['observations']['n_usable_positions']
    if 'motion_supported' in v:
        s.append(f'Detected in {n} independent exposures with a coherent position change.')
    elif doc['motion'] and doc['motion'].get('status') == 'not_significant':
        s.append(f'Measured in {n} exposures with no significant position change.')
    if tm.get('status') == 'matched':
        edge = ' (the coldest template available, so the object may be colder still)' if tm['best'].get('at_library_cold_limit') else ''
        s.append(f"The motion-corrected spectrum is consistent with a {tm['best']['spectral_type']} template{edge} "
                 f"(reduced chi-square {tm['best']['reduced_chi2']:.1f}), which supports but does not prove an ultracool-dwarf classification.")
    elif tm.get('status') in ('poor_fit', 'out_of_domain'):
        s.append('No ultracool-dwarf template fits well, as expected for an ordinary star.' if tm.get('status') == 'out_of_domain' else tm.get('reason', ''))
    if 'possible_blend' in v:
        s.append('Nearby sources may contribute light within the 6.15-arcsec pixels.')
    if 'saturated' in v:
        s.append('The source saturates the detector, so core positions and fluxes are excluded rather than forced.')
    if 'insufficient_evidence' in v:
        s.append('More or cleaner observations are required before drawing a conclusion.')
    return ' '.join(x for x in s if x)


def limitations(doc):
    out = ['SPHEREx pixels are 6.15 arcsec; sources closer than about 1 pixel are measured as one blend.',
           'Positions are registered to Gaia DR3 field stars with a pure shift per exposure; residual distortion is absorbed into an empirical error floor.',
           'Fluxes use the median pixel solid angle (OMEGA_MEDIAN) and the release ePSF; absolute calibration uncertainties of a few percent are not propagated.']
    m = doc.get('motion') or {}
    rep = (m.get('models') or {}).get(m.get('reported_model') or '', {})
    if m.get('status') == 'significant' and 'parallax_mas' not in rep:
        out.append('Parallax was not fitted (fewer than three visits); the motion is a linear approximation.')
    if (doc.get('spectrum') or {}).get('templates', {}) and (doc['spectrum']['templates'] or {}).get('status') == 'matched':
        out.append('A template match constrains spectral type only; it does not establish mass, age or formation history.')
    return out


def follow_up(doc):
    v = {x['code'] for x in doc['summary']['verdicts']}
    out = []
    if 'insufficient_evidence' in v:
        out.append('Wait for additional SPHEREx visits (new releases are picked up automatically) or stack more exposures.')
    if 'saturated' in v:
        out.append('Use catalogue astrometry (Gaia) or a PSF-wing fit for this bright source; SPHEREx cores are unusable.')
    if 'possible_blend' in v:
        out.append('Check higher-resolution imaging (e.g. unWISE, 2MASS, Gaia) to separate contributors.')
    if 'catalog_unmatched_followup' in v:
        out.append('Cross-check CatWISE, 2MASS and VizieR at the propagated epoch before any novelty claim; request spectroscopy only after independent confirmation.')
    if 'motion_supported' in v:
        out.append('Extend the baseline with archival WISE/NEOWISE epochs to tighten proper motion and parallax.')
    if not out:
        out.append('No follow-up required for this known source.')
    return out
