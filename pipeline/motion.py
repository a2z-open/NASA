"""Weighted tangent-plane motion fits: stationary, linear proper motion, and proper motion + parallax.

Positions are projected to a tangent plane (xi, eta) in arcsec about a fixed
reference point.  The model for each coordinate is
    xi(t)  = xi0  + mu_a* (t - t0) + plx * P_a(t)
    eta(t) = eta0 + mu_d  (t - t0) + plx * P_d(t)
with t in Julian years and P the parallax factors (astrometry.parallax_factors).
Covariances are scaled by max(1, reduced chi-square), so an underestimated
per-point error inflates the reported uncertainty instead of hiding it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np
from scipy import stats

from .astrometry import JULIAN_YEAR_DAYS, from_tangent, parallax_factors, to_tangent

MODELS = {
    'stationary': ['xi0', 'eta0'],
    'linear': ['xi0', 'eta0', 'pmra', 'pmdec'],
    'linear_parallax': ['xi0', 'eta0', 'pmra', 'pmdec', 'parallax'],
    'linear_fixed_parallax': ['xi0', 'eta0', 'pmra', 'pmdec'],   # parallax held at a catalogue value
}


@dataclass
class MotionFit:
    model: str
    ra_ref: float
    dec_ref: float
    t0_mjd: float
    params: dict                     # arcsec and arcsec/yr (pm), arcsec (parallax)
    cov: np.ndarray
    chi2: float
    dof: int
    n_points: int
    n_rejected: int
    fixed_parallax_arcsec: float | None = None
    residuals_arcsec: list = field(default_factory=list)   # (dxi, deta) per used point
    used: list = field(default_factory=list)

    @property
    def chi2r(self) -> float:
        return self.chi2 / self.dof if self.dof > 0 else math.nan

    @property
    def bic(self) -> float:
        return self.chi2 + len(MODELS[self.model]) * math.log(max(2 * self.n_points, 1))

    def errors(self) -> dict:
        names = MODELS[self.model]
        return {n: float(math.sqrt(max(self.cov[i, i], 0))) for i, n in enumerate(names)}

    def predict(self, mjd) -> dict:
        """Predicted (ra, dec) and 1-sigma covariance (arcsec^2) at the given epochs."""
        mjd = np.atleast_1d(np.asarray(mjd, dtype=float))
        A_xi, A_eta = design(self.model, mjd, self.t0_mjd, self.ra_ref, self.dec_ref)
        p = np.array([self.params[n] for n in MODELS[self.model]])
        xi = A_xi @ p
        eta = A_eta @ p
        if self.model == 'linear_fixed_parallax' and self.fixed_parallax_arcsec:
            pa, pd = parallax_factors(self.ra_ref, self.dec_ref, mjd)
            xi = xi + self.fixed_parallax_arcsec * pa
            eta = eta + self.fixed_parallax_arcsec * pd
        cxx = np.einsum('ij,jk,ik->i', A_xi, self.cov, A_xi)
        cyy = np.einsum('ij,jk,ik->i', A_eta, self.cov, A_eta)
        cxy = np.einsum('ij,jk,ik->i', A_xi, self.cov, A_eta)
        ra, dec = from_tangent(xi, eta, self.ra_ref, self.dec_ref)
        return {'ra': np.atleast_1d(ra), 'dec': np.atleast_1d(dec), 'xi': xi, 'eta': eta,
                'cov': np.stack([np.stack([cxx, cxy], -1), np.stack([cxy, cyy], -1)], -2)}

    def summary(self) -> dict:
        e = self.errors()
        out = {
            'model': self.model, 'reference': {'ra_deg': self.ra_ref, 'dec_deg': self.dec_ref,
                                               't0_mjd': self.t0_mjd},
            'n_points': self.n_points, 'n_rejected': self.n_rejected, 'chi2': self.chi2, 'dof': self.dof,
            'chi2_reduced': self.chi2r, 'bic': self.bic,
        }
        if 'pmra' in self.params:
            pmra, pmdec = self.params['pmra'] * 1000, self.params['pmdec'] * 1000
            spmra, spmdec = e['pmra'] * 1000, e['pmdec'] * 1000
            total = math.hypot(pmra, pmdec)
            stotal = math.sqrt((pmra * spmra) ** 2 + (pmdec * spmdec) ** 2) / total if total > 0 else math.nan
            out.update({'pmra_masyr': pmra, 'pmra_err_masyr': spmra, 'pmdec_masyr': pmdec, 'pmdec_err_masyr': spmdec,
                        'pm_total_masyr': total, 'pm_total_err_masyr': stotal,
                        'pm_position_angle_deg': math.degrees(math.atan2(pmra, pmdec)) % 360})
        if 'parallax' in self.params:
            out.update({'parallax_mas': self.params['parallax'] * 1000, 'parallax_err_mas': e['parallax'] * 1000})
        if self.fixed_parallax_arcsec is not None:
            out['fixed_parallax_mas'] = self.fixed_parallax_arcsec * 1000
        return out


def design(model: str, mjd, t0_mjd: float, ra_ref: float, dec_ref: float):
    mjd = np.atleast_1d(np.asarray(mjd, dtype=float))
    n = mjd.size
    dt = (mjd - t0_mjd) / JULIAN_YEAR_DAYS
    one, zero = np.ones(n), np.zeros(n)
    cols_xi = [one, zero]
    cols_eta = [zero, one]
    if model in ('linear', 'linear_parallax', 'linear_fixed_parallax'):
        cols_xi += [dt, zero]
        cols_eta += [zero, dt]
    if model == 'linear_parallax':
        pa, pd = parallax_factors(ra_ref, dec_ref, mjd)
        cols_xi.append(pa)
        cols_eta.append(pd)
    return np.stack(cols_xi, -1), np.stack(cols_eta, -1)


def fit_motion(mjd, ra, dec, sigma_arcsec, *, model='linear', ra_ref=None, dec_ref=None, t0_mjd=None,
               fixed_parallax_mas=None, clip_sigma=4.0, max_iter=5) -> MotionFit:
    mjd = np.asarray(mjd, dtype=float)
    ra = np.asarray(ra, dtype=float)
    dec = np.asarray(dec, dtype=float)
    sig = np.asarray(sigma_arcsec, dtype=float)
    if ra_ref is None:
        w = 1 / sig ** 2
        ra_ref = float(np.degrees(np.arctan2(np.sum(w * np.sin(np.radians(ra))), np.sum(w * np.cos(np.radians(ra))))) % 360)
        dec_ref = float(np.sum(w * dec) / np.sum(w))
    if t0_mjd is None:
        t0_mjd = float(np.sum(mjd / sig ** 2) / np.sum(1 / sig ** 2))
    xi, eta = to_tangent(ra, dec, ra_ref, dec_ref)
    fixed = (fixed_parallax_mas or 0.0) / 1000.0 if model == 'linear_fixed_parallax' else None
    if fixed:
        pa, pd = parallax_factors(ra_ref, dec_ref, mjd)
        xi = xi - fixed * pa
        eta = eta - fixed * pd
    A_xi, A_eta = design(model, mjd, t0_mjd, ra_ref, dec_ref)
    names = MODELS[model]

    def solve(keep):
        A = np.vstack([A_xi[keep], A_eta[keep]])
        b = np.concatenate([xi[keep], eta[keep]])
        w = np.concatenate([1 / sig[keep] ** 2, 1 / sig[keep] ** 2])
        AtW = A.T * w
        cov0 = np.linalg.inv(AtW @ A)
        p = cov0 @ (AtW @ b)
        rx = xi - A_xi @ p
        ry = eta - A_eta @ p
        chi2 = float(np.sum((rx[keep] ** 2 + ry[keep] ** 2) / sig[keep] ** 2))
        dof = int(2 * keep.sum() - len(names))
        return p, cov0, rx, ry, chi2, dof

    keep = np.ones(mjd.size, bool)
    if keep.sum() * 2 <= len(names):
        raise ValueError('not enough positions for this motion model')
    for _ in range(max_iter):
        p, cov0, rx, ry, chi2, dof = solve(keep)
        if not clip_sigma:
            break
        scale = math.sqrt(max(chi2 / max(dof, 1), 1.0))
        new_keep = keep & (np.hypot(rx, ry) / sig < clip_sigma * scale * math.sqrt(2))
        if new_keep.sum() == keep.sum() or 2 * new_keep.sum() <= len(names) + 1:
            break
        keep = new_keep
    p, cov0, rx, ry, chi2, dof = solve(keep)
    cov = cov0 * max(chi2 / max(dof, 1), 1.0)
    params = {n: float(v) for n, v in zip(names, p)}
    return MotionFit(model, ra_ref, dec_ref, t0_mjd, params, cov, chi2, dof, int(keep.sum()), int((~keep).sum()),
                     fixed, [[float(a), float(b)] for a, b in zip(rx, ry)], [bool(k) for k in keep])


def motion_significance(stationary: MotionFit, moving: MotionFit) -> dict:
    """Likelihood-ratio comparison of the stationary and moving models on the same points.

    Valid only when the per-point errors are realistic; the caller must report
    the reduced chi-square of both fits alongside this number.
    """
    dchi2 = stationary.chi2 - moving.chi2
    k = len(MODELS[moving.model]) - len(MODELS[stationary.model])
    p = float(stats.chi2.sf(max(dchi2, 0), k)) if k > 0 else math.nan
    sigma = float(stats.norm.isf(p / 2)) if p > 0 else float('inf')
    e = moving.errors()
    pm_snr = None
    if 'pmra' in moving.params:
        pm = math.hypot(moving.params['pmra'], moving.params['pmdec'])
        spm = math.sqrt((moving.params['pmra'] * e['pmra']) ** 2 + (moving.params['pmdec'] * e['pmdec']) ** 2) / pm if pm > 0 else math.nan
        pm_snr = pm / spm if spm and spm > 0 else math.nan
    return {'delta_chi2': dchi2, 'extra_params': k, 'p_value': p, 'equivalent_sigma': min(sigma, 99.0),
            'pm_over_error': pm_snr, 'delta_bic': stationary.bic - moving.bic}
