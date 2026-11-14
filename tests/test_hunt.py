"""Tests for the blind search (pipeline/hunt.py), the halo photometry and the solar-system lookup.

All inputs here are synthetic and exist only to test the code paths; no result in the app comes from them.
"""

import math

import numpy as np
import pytest

from pipeline import halo, hunt, solarsystem
from pipeline.astrometry import JULIAN_YEAR_DAYS


# ---------------------------------------------------------------------------
# Stage 1: detection
# ---------------------------------------------------------------------------

def _stack(n=81, sources=(), noise=1.0, seed=1, band='cold'):
    rng = np.random.default_rng(seed)
    img = rng.normal(0, noise, (n, n))
    K, s = hunt._kernel(hunt.KERNEL_FWHM_ARCSEC[band] / hunt.GRID_ARCSEC)
    yy, xx = np.mgrid[0:n, 0:n]
    for x, y, amp in sources:
        img += amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * s * s))
    return img.astype('f4'), np.full((n, n), noise, 'f4'), np.full((n, n), 10)


def test_matched_filter_finds_a_source_and_its_position():
    mean, noise, ncov = _stack(sources=[(40.3, 37.6, 6.0)])
    snr, amp, err, to_ujy, scale = hunt.snr_map(mean, noise, ncov, 'cold')
    peaks = hunt.find_peaks(snr, hunt.SEED_SNR)
    assert len(peaks) == 1
    x, y, s = peaks[0]
    assert abs(x - 40.3) < 0.4 and abs(y - 37.6) < 0.4
    assert s > 10


def test_pure_noise_gives_no_seed_detections():
    hits = 0
    for seed in range(6):
        mean, noise, ncov = _stack(seed=seed)
        snr, *_ = hunt.snr_map(mean, noise, ncov, 'cold')
        hits += len(hunt.find_peaks(snr, hunt.SEED_SNR))
    assert hits == 0


def test_uncovered_pixels_are_never_detected():
    mean, noise, ncov = _stack(sources=[(40, 40, 8.0)])
    ncov[:] = 1                                   # fewer exposures than MIN_COVER everywhere
    snr, *_ = hunt.snr_map(mean, noise, ncov, 'cold')
    assert not np.isfinite(snr).any()


def test_combine_rejects_a_single_exposure_outlier():
    rng = np.random.default_rng(3)
    items = [{'img': rng.normal(0, 1, (20, 20)).astype('f4'), 'var': np.ones((20, 20), 'f4')} for _ in range(8)]
    items[2]['img'][10, 10] = 500.0               # a cosmic ray in one exposure
    mean, noise, ncov = hunt.combine(items)
    assert abs(mean[10, 10]) < 3
    assert ncov[10, 10] == 7


# ---------------------------------------------------------------------------
# Stage 2: linking
# ---------------------------------------------------------------------------

def _visits_with(sources_per_visit, t=(60800.0, 60980.0, 61160.0)):
    """Build visit dicts with real S/N maps from synthetic stacks."""
    visits, per_visit = [], []
    for k, src in enumerate(sources_per_visit):
        mean, noise, ncov = _stack(sources=src, seed=10 + k)
        snr, amp, err, to_ujy, scale = hunt.snr_map(mean, noise, ncov, 'cold')
        v = {'id': f'visit-{k + 1}', 'mjd_mid': t[k], 'mjd_start': t[k] - 5, 'mjd_end': t[k] + 5,
             'bands': {'cold': {'mean': mean, 'snr': snr, 'amp': amp, 'err': err, 'to_ujy': to_ujy, 'n': 10, 'ncov': ncov}}}
        visits.append(v)
        per_visit.append(hunt.detect_visit(v, k))
    return visits, per_visit


def test_static_sources_link_into_one_object_each():
    stars = [(20, 20, 8.0), (60, 55, 9.0)]
    visits, per_visit = _visits_with([stars, stars, stars])
    objs = hunt.link(visits, per_visit)
    assert len(objs) == 2
    assert not any(o['linked_orphans'] for o in objs)
    assert all(len(o['visits_detected']) == 3 for o in objs)


def test_fast_mover_is_chained_and_its_speed_is_right():
    star = (20, 20, 8.0)
    # 8 arcsec/yr eastward: 2.6 grid pixels per ~0.49 yr step
    step = 8.0 * (180.0 / JULIAN_YEAR_DAYS) / hunt.GRID_ARCSEC
    mover = [(50 - i * step, 50, 9.0) for i in range(3)]
    visits, per_visit = _visits_with([[star, mover[0]], [star, mover[1]], [star, mover[2]]])
    objs = hunt.link(visits, per_visit)
    chains = [o for o in objs if o['linked_orphans']]
    assert len(chains) == 1
    o = chains[0]
    assert len(o['visits_detected']) == 3
    speed = math.hypot(o['vx'], o['vy']) * hunt.GRID_ARCSEC
    assert abs(speed - 8.0) < 2.0          # stack positions are only seeds; native pixels give the precise motion
    sm = hunt.stack_motion(dict(o))
    assert sm['n_visits'] == 3 and abs(sm['pm_arcsec_yr'] - 8.0) < 3 * sm['pm_err_arcsec_yr'] + 0.5


def test_two_unrelated_faint_sources_are_not_chained_when_brightness_differs():
    a = (30, 30, 9.0)
    b = (33, 30, 40.0)       # 9 arcsec away, four times brighter: not the same object
    visits, per_visit = _visits_with([[a], [b], []])
    objs = hunt.link(visits, per_visit)
    assert not any(o['linked_orphans'] for o in objs)


# ---------------------------------------------------------------------------
# Stage 4: vetting
# ---------------------------------------------------------------------------

def _rows(pm_arcsec_yr=(0.0, 0.0), chroma=0.0, n=120, sigma=0.3, seed=5):
    rng = np.random.default_rng(seed)
    t = np.concatenate([rng.uniform(60800, 60815, n // 3), rng.uniform(60980, 60995, n // 3), rng.uniform(61160, 61175, n // 3)])
    lam = rng.uniform(0.8, 4.9, t.size)
    # give the middle visit a redder wavelength mix, as real coverage can
    lam[n // 3: 2 * n // 3] = rng.uniform(2.8, 4.9, n // 3)
    yr = (t - t.mean()) / JULIAN_YEAR_DAYS
    dec0 = -20.0
    ra = 150.0 + (pm_arcsec_yr[0] * yr + chroma * (lam - 2.5) + rng.normal(0, sigma, t.size)) / 3600 / math.cos(math.radians(dec0))
    dec = dec0 + (pm_arcsec_yr[1] * yr + rng.normal(0, sigma, t.size)) / 3600
    visits = [{'id': f'visit-{k + 1}', 'mjd_start': a, 'mjd_end': b} for k, (a, b) in enumerate([(60800, 60815), (60980, 60995), (61160, 61175)])]
    rows = [{'status': 'measured', 'product_id': f'p{i}', 'mjd': float(t[i]), 'centroid': {'ok': True, 'snr': 20.0},
             'position': {'ra': float(ra[i]), 'dec': float(dec[i]), 'sigma_arcsec': sigma}, 'wavelength_um': float(lam[i]), 'flags': []}
            for i in range(t.size)]
    return rows, visits


def test_real_motion_survives_the_colour_term_and_the_jackknife():
    rows, visits = _rows(pm_arcsec_yr=(2.0, -1.0))
    rb = hunt.robust_motion(rows, visits)
    assert rb['tested'] and rb['pm_over_error'] > 10
    assert abs(rb['pm_arcsec_yr'] - math.hypot(2.0, 1.0)) < 0.2
    assert rb['jackknife_stable'] is True
    assert hunt.chromatic_check(rows)['consistent']


def test_colour_dependent_shift_is_not_mistaken_for_motion():
    # No motion at all, but the position depends on wavelength (a blend), and the visits have different colour mixes.
    rows, visits = _rows(pm_arcsec_yr=(0.0, 0.0), chroma=0.6)
    rb = hunt.robust_motion(rows, visits)
    assert rb['tested']
    assert rb['pm_over_error'] < hunt.MOTION_PM_SNR


def test_stationary_noise_is_not_significant():
    rows, visits = _rows()
    motion, usable = hunt.analyse_motion(rows, visits)
    assert motion['status'] != 'significant'


# ---------------------------------------------------------------------------
# Stage 5: decade-baseline catalogue checks (HTTP mocked)
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError('http error')

    def json(self):
        import json
        return json.loads(self.text)


class _Http:
    def __init__(self, gaia_csv, wise_csv):
        self.gaia_csv, self.wise_csv = gaia_csv, wise_csv

    def post(self, url, data=None, timeout=None):
        return _Resp(self.gaia_csv)

    def get(self, url, params=None, timeout=None):
        return _Resp(self.wise_csv)


GAIA_HEAD = 'source_id,ra,dec,pmra,pmdec,parallax,phot_g_mean_mag\n'
WISE_HEAD = 'source_name,ra,dec,w1mpro,w2mpro,pmra,pmdec,sigpmra,sigpmdec,meanobsmjd\n'
EPOCH = 61100.0
MOVER = {'ra': 150.0, 'dec': 10.0, 'pm_arcsec_yr': 2.0, 'pmra_masyr': 2000.0, 'pmdec_masyr': 0.0, 'pmra_err_masyr': 60.0,
         'pmdec_err_masyr': 60.0, 'flags': [], 'class': 'candidate'}


def test_a_star_already_at_this_spot_in_2016_vetoes_the_motion():
    gaia = GAIA_HEAD + '111,150.0002,10.0001,3.0,-2.0,0.5,19.4\n'       # a static Gaia star at the current position
    ext = hunt.external_checks(dict(MOVER), EPOCH, session=_Http(gaia, WISE_HEAD))
    assert ext['gaia']['verdict'] == 'static_counterpart'
    doc = dict(MOVER, flags=[])
    hunt.apply_external(doc, ext)
    assert doc['class'] == 'suspect' and 'gaia_2016_shows_it_here' in doc['flags']


def test_a_wise_source_with_the_same_motion_confirms_it():
    dt = (EPOCH - 57170.0) / JULIAN_YEAR_DAYS
    ra_2015 = 150.0 - 2.0 * dt / 3600 / math.cos(math.radians(10.0))
    wise = WISE_HEAD + f'J100000.00+100000.0,{ra_2015:.7f},10.0,16.0,13.5,2.0,0.0,0.02,0.02,57170.0\n'
    ext = hunt.external_checks(dict(MOVER), EPOCH, session=_Http(GAIA_HEAD, wise))
    assert ext['wise']['verdict'] == 'same_motion'
    assert ext['gaia']['verdict'] == 'no_counterpart'
    doc = dict(MOVER, flags=[])
    hunt.apply_external(doc, ext)
    assert doc['class'] == 'candidate' and doc['decade_confirmed'] and doc['catalogued_as'].startswith('CatWISE2020')


def test_nothing_in_either_catalogue_leaves_the_candidate_unexplained():
    ext = hunt.external_checks(dict(MOVER), EPOCH, session=_Http(GAIA_HEAD, WISE_HEAD))
    doc = dict(MOVER, flags=[])
    hunt.apply_external(doc, ext)
    assert doc['class'] == 'candidate' and not doc.get('decade_confirmed')


# ---------------------------------------------------------------------------
# Halo photometry of saturated stars
# ---------------------------------------------------------------------------

def _halo_rows(visit_factor=(1.0, 1.0, 1.0), n_per=30, scatter=0.05, seed=2):
    rng = np.random.default_rng(seed)
    rows = []
    for v, f in enumerate(visit_factor):
        for i in range(n_per):
            lam = 0.8 * (1.06 ** (i % 28))              # the same wavelengths recur in every visit
            spectrum = 5.0 * lam ** -1.5                # strong dependence on wavelength
            h = spectrum * f * math.exp(rng.normal(0, scatter))
            rows.append({'status': 'measured', 'product_id': f'v{v}e{i}', 'mjd': 60800.0 + 180 * v + 0.3 * i, 'detector': 1,
                         'wavelength_um': lam, 'rings': {'r5-8': {'h': h, 'err': 0.02 * h, 'snr': 50.0, 'valid_fraction': 1.0}}})
    return rows


def test_halo_recovers_a_fade_despite_a_steep_spectrum():
    doc = halo.analyse(_halo_rows(visit_factor=(1.0, 0.8, 0.55)))
    assert doc['status'] == 'variable'
    r = {v['visit']: v['ratio'] for v in doc['visits']}
    assert abs(r['visit-2'] - 0.8) < 0.05 and abs(r['visit-3'] - 0.55) < 0.04


def test_halo_does_not_flag_a_steady_star():
    doc = halo.analyse(_halo_rows())
    assert doc['status'] == 'not_detected'
    assert all(abs(v['ratio'] - 1) < 0.05 for v in doc['visits'])


def test_halo_needs_enough_exposures():
    assert halo.analyse(_halo_rows(n_per=2))['status'] == 'insufficient'


# ---------------------------------------------------------------------------
# Solar-system lookup (HTTP mocked)
# ---------------------------------------------------------------------------

class _Sky:
    def __init__(self, responses):
        self.responses = list(responses)

    def get(self, url, params=None, timeout=None):
        return self.responses.pop(0)


def test_skybot_no_content_means_no_bodies():
    assert solarsystem.known_bodies(10.0, 20.0, 60800.0, session=_Sky([_Resp('', 204)])) == []


def test_skybot_rows_are_parsed():
    body = '[{"Num":28257,"Name":"1999 BT24","Class":"MB>Middle","VMag (mag)":17.8,"d (arcsec)":18.2,"dRA (arcsec/h)":30.0,"dDEC (arcsec/h)":-40.0}]'
    out = solarsystem.known_bodies(10.0, 20.0, 60800.0, session=_Sky([_Resp(body)]))
    assert out[0]['name'] == '1999 BT24' and out[0]['sep_arcsec'] == 18.2
    assert abs(out[0]['rate_arcsec_per_hour'] - 50.0) < 1e-6


def test_check_reports_unavailable_when_every_query_fails(monkeypatch):
    def boom(*a, **k):
        raise solarsystem.requests.ConnectionError('down')
    monkeypatch.setattr(solarsystem, 'known_bodies', boom)
    doc = solarsystem.check(10.0, 20.0, [60800.0, 60900.0])
    assert doc['status'] == 'unavailable' and doc['n_epochs_checked'] == 0


def test_check_with_no_times_is_not_checked():
    assert solarsystem.check(10.0, 20.0, [])['status'] == 'not_checked'


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def test_hunt_api_rejects_unknown_fields():
    from fastapi.testclient import TestClient
    from api.app import app
    c = TestClient(app)
    assert c.get('/api/hunt/does-not-exist').status_code == 404
    assert c.get('/files/hunt/does-not-exist/frames/x.bin').status_code == 404
    assert c.get('/files/hunt/..%2F..%2Fetc/frames/passwd.bin').status_code == 404
