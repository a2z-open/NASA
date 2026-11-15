"""Tests for coordinates, motion fitting, ePSF measurement, flags, dedupe and evidence.

All fixtures here are SYNTHETIC with known answers; none of them is real astronomical data.
"""

import json
import math

import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import GCRS, Distance, SkyCoord
from astropy.time import Time
from astropy.wcs import WCS

from pipeline.astrometry import (CoordinateError, format_sexagesimal, from_tangent, parallax_factors, parse_dec, parse_position,
                                 parse_ra, propagate, to_tangent)
from pipeline.motion import fit_motion, motion_significance
from pipeline.spherex import EpsfZone, Observation, Product, decode_flags, dedupe, flag_mask, group_visits
from pipeline import spherex


def test_viewer_search_keeps_available_release_and_reports_outage(monkeypatch):
    from types import SimpleNamespace

    def get(url, *, params, timeout):
        if params['COLLECTION'] == 'spherex_dr1':
            raise spherex.ArchiveUnavailable('HTTP 502')
        return SimpleNamespace(content=b'qr3')

    product = Product('obs', 5, 'spherex_qr3', 'QR3', 'https://example.org/test.fits',
                      61000., 61000.001, 10., 20., None, None)
    monkeypatch.setattr(spherex, '_get', get)
    monkeypatch.setattr(spherex, 'parse_sia', lambda content, collection: [product])
    outages = []
    assert spherex.search(10., 20., on_unavailable=outages.append) == [product]
    assert outages == ['spherex_dr1']
    with pytest.raises(spherex.ArchiveUnavailable):
        spherex.search(10., 20.)
    with pytest.raises(spherex.ArchiveUnavailable):
        spherex.search(10., 20., collections=['spherex_dr1'], on_unavailable=outages.append)


def test_horizons_requests_are_serialized(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from time import sleep
    from types import SimpleNamespace

    from pipeline import ephem

    gate = Barrier(2)
    simultaneous = 0

    def request(*args, **kwargs):
        nonlocal simultaneous
        simultaneous += 1
        try:
            sleep(.025)
            assert simultaneous == 1
        finally:
            simultaneous -= 1
        return SimpleNamespace(raise_for_status=lambda: None)

    def lookup():
        gate.wait(timeout=2)
        ephem._request_horizons({}, timeout=1)

    monkeypatch.setattr(ephem, 'CACHE', tmp_path)
    monkeypatch.setattr(ephem.requests, 'get', request)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(lookup) for _ in range(2)]
        for future in futures:
            future.result(timeout=2)


# ---------------------------------------------------------------- coordinates

def test_parse_decimal_and_sexagesimal():
    assert parse_ra('133.79513') == pytest.approx(133.79513)
    assert parse_ra('08h55m10.831s') == pytest.approx(133.7951292, abs=1e-6)
    assert parse_ra('08:55:10.831') == pytest.approx(133.7951292, abs=1e-6)
    assert parse_dec('-07d14m42.53s') == pytest.approx(-7.2451472, abs=1e-6)
    assert parse_dec('−07:14:42.53') == pytest.approx(-7.2451472, abs=1e-6)
    ra, dec = parse_position('22h04m23.2s -56d48m02s')
    assert ra == pytest.approx(331.0966667, abs=1e-6) and dec == pytest.approx(-56.8005556, abs=1e-6)
    ra, dec = parse_position('331.0966, -56.8005')
    assert (ra, dec) == (pytest.approx(331.0966), pytest.approx(-56.8005))


@pytest.mark.parametrize('bad', ['', 'abc', '400', '-1', 'nan'])
def test_invalid_ra(bad):
    with pytest.raises(CoordinateError):
        parse_ra(bad)


@pytest.mark.parametrize('bad', ['', '91', '-90.5', 'xyz'])
def test_invalid_dec(bad):
    with pytest.raises(CoordinateError):
        parse_dec(bad)


def test_ra_wraps_360_to_0_and_format():
    assert parse_ra('360') == 0.0
    s_ra, s_dec = format_sexagesimal(133.7951292, -7.2451472)
    assert s_ra.startswith('08h55m10.83') and s_dec.startswith('-07d14m42.5')


def test_tangent_plane_round_trip_across_ra_zero():
    ra0, dec0 = 359.999, 30.0
    ra = np.array([359.99, 0.005, 0.01])
    dec = np.array([30.0, 30.001, 29.999])
    xi, eta = to_tangent(ra, dec, ra0, dec0)
    assert np.all(np.abs(xi) < 60)          # no 360-degree jump
    back_ra, back_dec = from_tangent(xi, eta, ra0, dec0)
    assert np.allclose(((back_ra - ra + 180) % 360) - 180, 0, atol=1e-9)
    assert np.allclose(back_dec, dec, atol=1e-9)


def test_parallax_factor_sign_matches_astropy():
    ra, dec, plx = 331.0, -56.8, 270.0
    for mjd in (60800.0, 61000.0):
        t = Time(mjd, format='mjd')
        near = SkyCoord(ra * u.deg, dec * u.deg, distance=Distance(parallax=plx * u.mas)).transform_to(GCRS(obstime=t))
        far = SkyCoord(ra * u.deg, dec * u.deg, distance=1e9 * u.pc).transform_to(GCRS(obstime=t))
        xi, eta = to_tangent(near.ra.deg, near.dec.deg, far.ra.deg, far.dec.deg)
        pa, pd = parallax_factors(ra, dec, mjd)
        assert float(xi) * 1000 == pytest.approx(pa[0] * plx, abs=0.2)
        assert float(eta) * 1000 == pytest.approx(pd[0] * plx, abs=0.2)


def test_proper_motion_uses_cos_dec_convention():
    # 3600 mas/yr in mu_alpha* is 3.6 arcsec on the sky per year, i.e. 3.6/cos(60) = 7.2 arcsec of RA at dec 60
    p = propagate(10.0, 60.0, 60000.0, 3600.0, 0.0, 0.0, [60000.0 + 365.25])
    xi, eta = to_tangent(p.ra[0], p.dec[0], 10.0, 60.0)
    assert float(xi) == pytest.approx(3.6, abs=1e-3)
    assert (p.ra[0] - 10.0) * 3600 == pytest.approx(3.6 / math.cos(math.radians(60)), rel=1e-3)


# ---------------------------------------------------------------- motion

def synthetic_track(pmra=4000.0, pmdec=-2500.0, plx=270.0, n=120, sigma=0.15, seed=1):
    rng = np.random.default_rng(seed)
    mjd = np.sort(np.concatenate([rng.uniform(60790, 60840, n // 3), rng.uniform(60950, 61000, n // 3), rng.uniform(61150, 61190, n - 2 * (n // 3))]))
    p = propagate(331.1, -56.8, 61000.0, pmra, pmdec, plx, mjd)
    xi = p.xi + rng.normal(0, sigma, mjd.size)
    eta = p.eta + rng.normal(0, sigma, mjd.size)
    ra, dec = from_tangent(xi, eta, 331.1, -56.8)
    return mjd, ra, dec, np.full(mjd.size, sigma)


def test_motion_fit_recovers_pm_and_parallax():
    mjd, ra, dec, sig = synthetic_track()
    f = fit_motion(mjd, ra, dec, sig, model='linear_parallax')
    s = f.summary()
    assert s['pmra_masyr'] == pytest.approx(4000, abs=4 * s['pmra_err_masyr'])
    assert s['pmdec_masyr'] == pytest.approx(-2500, abs=4 * s['pmdec_err_masyr'])
    assert s['parallax_mas'] == pytest.approx(270, abs=4 * s['parallax_err_mas'])
    assert 0.6 < s['chi2_reduced'] < 1.5


def test_stationary_source_not_flagged_and_mover_flagged():
    mjd, ra, dec, sig = synthetic_track(pmra=0, pmdec=0, plx=0, seed=3)
    st = fit_motion(mjd, ra, dec, sig, model='stationary')
    mv = fit_motion(mjd, ra, dec, sig, model='linear', ra_ref=st.ra_ref, dec_ref=st.dec_ref)
    assert motion_significance(st, mv)['equivalent_sigma'] < 5
    mjd, ra, dec, sig = synthetic_track(pmra=500, pmdec=0, plx=0, seed=4)
    st = fit_motion(mjd, ra, dec, sig, model='stationary')
    mv = fit_motion(mjd, ra, dec, sig, model='linear', ra_ref=st.ra_ref, dec_ref=st.dec_ref)
    assert motion_significance(st, mv)['equivalent_sigma'] > 5


def test_underestimated_errors_inflate_uncertainty():
    mjd, ra, dec, _ = synthetic_track(sigma=0.3, seed=5)
    honest = fit_motion(mjd, ra, dec, np.full(mjd.size, 0.3), model='linear_parallax').errors()['pmra']
    claimed = fit_motion(mjd, ra, dec, np.full(mjd.size, 0.03), model='linear_parallax').errors()['pmra']
    assert claimed == pytest.approx(honest, rel=0.25)     # scaled by sqrt(reduced chi2), not 10x smaller


def test_prediction_uncertainty_grows_with_extrapolation():
    mjd, ra, dec, sig = synthetic_track()
    f = fit_motion(mjd, ra, dec, sig, model='linear_parallax')
    near = f.predict([61000.0])['cov'][0]
    far = f.predict([62500.0])['cov'][0]
    assert np.trace(far) > np.trace(near)


# ---------------------------------------------------------------- ePSF measurement on a synthetic image

def gaussian_epsf(fwhm_px=1.5, ov=5):
    yy, xx = np.indices((33, 33))
    s = fwhm_px * ov / 2.355
    g = np.exp(-((xx - 16) ** 2 + (yy - 16) ** 2) / (2 * s ** 2))
    return g / g.sum()


def synthetic_observation(sources, shape=(41, 41), noise=0.05, seed=0, flags=None):
    from pipeline.measure import epsf_values
    rng = np.random.default_rng(seed)
    w = WCS(naxis=2)
    w.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    w.wcs.crval = [100.0, 10.0]
    w.wcs.crpix = [21, 21]
    w.wcs.cdelt = [-6.15 / 3600, 6.15 / 3600]
    zone = EpsfZone(0.0, 0.0, gaussian_epsf(), 5)
    img = np.full(shape, 1.0) + rng.normal(0, noise, shape)
    yy, xx = np.indices(shape)
    for x, y, f in sources:
        img += f * epsf_values(zone, xx - x, yy - y)
    return Observation('synthetic-D1', 'synthetic', 1, 'TEST', 61000.0, 61000.0, 61000.0, img, np.full(shape, noise ** 2),
                       np.zeros(shape, dtype=np.int64) if flags is None else flags, {1: 'OVERFLOW', 21: 'SOURCE'}, w,
                       np.full(shape, 1.0), np.full(shape, 0.02), 37.95, 9.0, (1.0, 1.0), [zone])


def test_epsf_fit_recovers_position_and_flux():
    from pipeline.measure import fit_source
    obs = synthetic_observation([(20.3, 19.6, 50.0)])
    f = fit_source(obs, 20.0, 20.0)
    assert f.ok
    assert f.x == pytest.approx(20.3, abs=0.03) and f.y == pytest.approx(19.6, abs=0.03)
    assert f.flux == pytest.approx(50.0, rel=0.03)


def test_deblending_neighbour_removes_contamination():
    from pipeline.measure import fit_source
    obs = synthetic_observation([(20.0, 20.0, 0.0), (21.3, 20.0, 200.0)], seed=2)   # empty target, bright star 1.3 px away
    naive = fit_source(obs, 20.0, 20.0, fix_position=True)
    joint = fit_source(obs, 20.0, 20.0, fix_position=True, others=[(21.3, 20.0)])
    assert abs(naive.flux) > 20                     # contaminated
    assert abs(joint.flux) < 3 * joint.flux_err     # consistent with zero


def test_saturated_core_is_refused_not_forced():
    from pipeline.measure import fit_source
    flags = np.zeros((41, 41), dtype=np.int64)
    flags[18:23, 18:23] = 1 << 1    # OVERFLOW
    obs = synthetic_observation([(20.0, 20.0, 500.0)], flags=flags)
    f = fit_source(obs, 20.0, 20.0)
    assert not f.ok and f.reason == 'core_saturated'


# ---------------------------------------------------------------- flags, dedupe, visits

def test_flag_decoding_uses_header_names():
    names = {1: 'OVERFLOW', 19: 'OUTLIER', 21: 'SOURCE'}
    assert decode_flags((1 << 1) | (1 << 21), names) == ['OVERFLOW', 'SOURCE']
    assert flag_mask(names, {'OUTLIER'}) == 1 << 19


def product(obs_id, det, release, t, version='l2b-v27-2026-200'):
    return Product(obs_id, det, f'spherex_{release.lower()}', release,
                   f'https://irsa.ipac.caltech.edu/ibe/data/spherex/{release.lower()}/level2/x/{version}/{det}/f.fits',
                   t, t + 0.001, 0, 0, 1.0, 2.0)


def test_dedupe_prefers_dr1_and_sorts_by_time():
    items = [product('b', 1, 'QR3', 61000), product('a', 2, 'DR1', 60000), product('a', 2, 'QR3', 60000)]
    out = dedupe(items)
    assert [p.id for p in out] == ['a-D2', 'b-D1']
    assert out[0].release == 'DR1'


def test_visit_grouping_by_gap():
    items = [product('a', 1, 'DR1', 60000), product('b', 1, 'DR1', 60010), product('c', 1, 'DR1', 60100)]
    visits = group_visits(items)
    assert [len(v) for v in visits] == [2, 1]


# ---------------------------------------------------------------- evidence model

def test_evidence_document_is_json_serialisable_and_uses_null_for_missing():
    from pipeline.analysis import build_investigation
    rows = [{'product_id': f'p{i}-D1', 'mjd': 61000.0 + i, 'status': 'measured', 'detector': 1, 'release': 'DR1',
             'wavelength_um': 1.0, 'bandwidth_um': 0.03, 'flags': ['OVERFLOW', 'SOURCE'],
             'centroid': {'ok': False, 'reason': 'core_saturated'}, 'follow': {'ok': False, 'reason': 'core_saturated'}}
            for i in range(8)]
    doc = build_investigation(rows, inv_id='t', kind='user', title='t', field_id='f', source={'ra': 1.0, 'dec': 2.0, 'label': 'x'},
                              visits=[])
    text = json.dumps(doc, allow_nan=False)
    assert 'saturated' in [v['code'] for v in doc['summary']['verdicts']]
    assert doc['detections'][0]['ra'] is None and doc['detections'][0]['flux_ujy'] is None
    assert '"H6"' in text
