"""Distant-world search: orbit geometry, linking, the lock ledger, the Planet Nine arithmetic, and the audit fixes."""
import json
import math

import numpy as np
import pytest

from pipeline import distant, hunt
from pipeline.astrometry import JULIAN_YEAR_DAYS, earth_barycentric_au
from validation import ledger, planet_nine
from tests.test_hunt import EPOCH, GAIA_HEAD, MOVER, WISE_HEAD, _Http


def _body(r_au, mjd, ra0=200.0, dec0=20.0, v=(0.0, 0.0, 0.0), noise=0.0, seed=0):
    """Apparent positions of a body from an INDEPENDENT calculation: plain vectors, no call to distant.predict."""
    rng = np.random.default_rng(seed)
    a, d = math.radians(ra0), math.radians(dec0)
    b0 = r_au * np.array([math.cos(d) * math.cos(a), math.cos(d) * math.sin(a), math.sin(d)])
    t0 = float(np.mean(mjd))
    out = []
    for t, e in zip(mjd, earth_barycentric_au(mjd)):
        tau = (t - t0) / JULIAN_YEAR_DAYS
        b = b0 + np.array(v) * tau - 0.5 * distant.MU * b0 / r_au ** 3 * tau ** 2
        u = (b - e) / np.linalg.norm(b - e)
        ra, dec = math.degrees(math.atan2(u[1], u[0])) % 360, math.degrees(math.asin(u[2]))
        out.append({'mjd': float(t), 'ra': ra + rng.normal(0, noise) / 3600 / math.cos(math.radians(dec)), 'dec': dec + rng.normal(0, noise) / 3600,
                    'sigma_arcsec': max(noise, 0.6), 'obs_id': f'e{t:.3f}', 'product_id': f'e{t:.3f}', 'flux_ujy': 500.0})
    return out


VISITS = np.concatenate([60850 + np.arange(0, 8, 1.3), 61035 + np.arange(0, 8, 1.3), 61215 + np.arange(0, 8, 1.3)])


@pytest.mark.parametrize('r', [40.0, 95.0, 600.0])
def test_orbit_fit_returns_the_distance_of_an_independently_computed_body(r):
    dets = _body(r, VISITS, v=(0.3 / math.sqrt(r / 40), 0.1, 0.0), noise=0.5, seed=3)
    # beyond a few hundred AU the speed towards or away from the Sun cannot be measured in two years,
    # so the Planet Nine mode holds it at zero (five numbers instead of six)
    orb = distant.fit_orbit(dets, fix_radial=r > 300)
    assert orb is not None and orb['bound']
    assert abs(orb['r_au'] - r) / r < 0.02
    assert orb['chi2r'] < 2.5


def test_mirrored_earth_cannot_fit_a_real_parallax():
    dets = _body(60.0, VISITS, v=(0.5, 0.1, 0.0), noise=0.5, seed=4)
    good, mirrored = distant.fit_orbit(dets), distant.fit_orbit(dets, mirror=True)
    assert mirrored['chi2r'] > distant.MIRROR_RATIO_MIN * good['chi2r']


def test_tracklets_pick_the_moving_body_out_of_noise():
    rng = np.random.default_rng(5)
    t = 61000 + np.sort(rng.uniform(0, 6, 10))
    track = [{'mjd': float(x), 'ra': 150.0 + 30.0 * (x - 61000) / 3600, 'dec': 10.0 + 5.0 * (x - 61000) / 3600, 'sigma_arcsec': 0.6,
              'obs_id': f't{i}', 'product_id': f't{i}'} for i, x in enumerate(t)]
    noise = [{'mjd': float(61000 + rng.uniform(0, 6)), 'ra': 150.0 + rng.uniform(-0.1, 0.1), 'dec': 10.0 + rng.uniform(-0.1, 0.1),
              'sigma_arcsec': 0.6, 'obs_id': f'n{i}', 'product_id': f'n{i}'} for i in range(40)]
    dets = sorted(track + noise, key=lambda d: d['mjd'])
    tr = distant.tracklets(dets)
    assert tr and tr[0]['n'] >= 9
    assert all(dets[k]['obs_id'].startswith('t') for k in tr[0]['members'])
    assert abs(tr[0]['rate_arcsec_day'] - math.hypot(30.0 * math.cos(math.radians(10.0)), 5.0)) < 1.0


def test_two_tracklets_of_one_body_are_joined_and_unrelated_ones_are_not():
    a = _body(52.0, VISITS, v=(0.6, 0.2, 0.0), noise=0.5, seed=6)
    vid = distant.split_visits([d['mjd'] for d in a])
    tracks = [{'members': [i for i in range(len(a)) if vid[i] == v]} for v in sorted(set(vid))]
    objs = distant.link_orbits(a, tracks, [0, 1, 2])
    assert len(objs) == 1 and objs[0]['n_visits'] == 3 and objs[0]['passes_mirror_test']
    assert abs(objs[0]['orbit']['r_au'] - 52.0) < 1.0
    # visit 0 of one body with visit 1 of a body somewhere else: no bound orbit should join them
    b = _body(52.0, VISITS, ra0=200.4, dec0=20.9, v=(-0.5, 0.4, 0.0), noise=0.5, seed=7)
    mixed = [d for d, v in zip(a, vid) if v == 0] + [d for d, v in zip(b, vid) if v == 1]
    n0 = sum(1 for v in vid if v == 0)
    objs = distant.link_orbits(mixed, [{'members': list(range(n0))}, {'members': list(range(n0, len(mixed)))}], [0, 1])
    assert not [o for o in objs if o['passes_mirror_test'] and o['orbit']['chi2r'] < distant.ORBIT_CHI2R_MAX and abs(o['orbit']['r_au'] - 52.0) < 2.0]


def test_ledger_detects_an_edited_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, 'ROOT', tmp_path)
    monkeypatch.setattr(ledger, 'LEDGER', tmp_path / 'ledger.jsonl')
    f = tmp_path / 'blind.json'
    f.write_text('{"r": 52.7}')
    e = ledger.append('test', [f], note='first')
    assert ledger.verify() == (True, [])
    assert ledger.locked('test', f)['hash'] == e['hash']
    f.write_text('{"r": 52.8}')
    ok, problems = ledger.verify()
    assert not ok and 'differs' in problems[0]
    with pytest.raises(RuntimeError):
        ledger.locked('test', f)


def test_ledger_detects_an_edited_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, 'ROOT', tmp_path)
    monkeypatch.setattr(ledger, 'LEDGER', tmp_path / 'ledger.jsonl')
    f = tmp_path / 'a.json'
    f.write_text('1')
    ledger.append('one', [f])
    ledger.append('two', [f])
    lines = (tmp_path / 'ledger.jsonl').read_text().splitlines()
    first = json.loads(lines[0])
    first['time_utc'] = '2020-01-01T00:00:00+00:00'
    (tmp_path / 'ledger.jsonl').write_text(json.dumps(first, sort_keys=True) + '\n' + lines[1] + '\n')
    ok, problems = ledger.verify()
    assert not ok and any('edited' in p for p in problems)


def test_planet_nine_arithmetic():
    assert abs(planet_nine.v_to_ujy(22.0) - 7.24) < 0.05                # V 22 is about 7 microjansky near 1 um
    rows = {r['world']: r['max_distance_au'] for r in planet_nine.reach(300.0)}
    assert rows['A twin of Jupiter'] > rows['A twin of Neptune'] > rows['Planet Nine, as predicted']
    assert 190 < rows['Planet Nine, as predicted'] < 240
    assert planet_nine.mu_max_arcsec_yr(500) > planet_nine.mu_max_arcsec_yr(2000)


def test_planet_nine_linker_finds_a_synthetic_planet_and_rejects_a_static_triple():
    mjd = np.array([60880.0, 61055.0, 61242.0])
    planet = _body(700.0, mjd, ra0=34.4, dec0=-5.2, v=(0.2, 0.05, 0.0))
    pts = [dict(p, id=f'p{i}', visit=i, snr=20.0, band='short', sigma_arcsec=2.0) for i, p in enumerate(planet)]
    rng = np.random.default_rng(8)
    for i in range(3):
        for k in range(12):
            pts.append({'id': f'n{i}.{k}', 'visit': i, 'mjd': float(mjd[i]), 'ra': 34.4 + rng.uniform(-0.15, 0.15), 'dec': -5.2 + rng.uniform(-0.15, 0.15),
                        'snr': 8.0, 'band': 'short', 'flux_ujy': float(rng.uniform(200, 5000)), 'sigma_arcsec': 2.4})
    res = planet_nine.search_points(pts, 34.4, -5.2)
    hit = [t for t in res['triples'] if set(t['members']) == {'p0', 'p1', 'p2'}]
    assert hit and abs(hit[0]['r_au'] - 700.0) / 700.0 < 0.1 and hit[0]['passes_mirror_test']
    assert not hit[0]['too_bright_for_a_planet'] or hit[0]['flux_ujy'] > 10 * hit[0]['jupiter_twin_ujy']


def test_a_wise_mover_with_a_different_motion_is_not_a_confirmation():
    dt = (EPOCH - 57170.0) / JULIAN_YEAR_DAYS
    # a catalogued mover that ends up at the same place today but travels north, not east
    dec_2015 = 10.0 - 1.0 * dt / 3600
    wise = WISE_HEAD + f'J100000.00+100000.0,150.0,{dec_2015:.7f},16.0,16.1,0.07,1.0,0.02,0.02,57170.0\n'
    ext = hunt.external_checks(dict(MOVER), EPOCH, session=_Http(GAIA_HEAD, wise))
    assert ext['wise']['verdict'] == 'different_motion'
    doc = dict(MOVER, flags=[])
    hunt.apply_external(doc, ext)
    assert not doc.get('decade_confirmed')


def test_file_route_cannot_leave_the_target_folder():
    from fastapi.testclient import TestClient
    from api.app import app
    c = TestClient(app)
    for path in ('/files/targets/wise-0855//etc/hosts', '/files/targets/wise-0855/%2Fetc%2Fhosts', '/files/targets/wise-0855/..%2F..%2FREADME.md'):
        assert c.get(path).status_code == 404


def test_bad_request_bodies_are_400_not_500():
    from fastapi.testclient import TestClient
    from api.app import app
    c = TestClient(app)
    assert c.post('/api/fields', content='{bad', headers={'content-type': 'application/json'}).status_code == 400
    assert c.post('/api/fields', json={'ra': 10, 'dec': 10, 'fov_arcmin': 'abc'}).status_code == 400
    assert c.post('/api/investigations', json=[1, 2]).status_code == 400


class _FakeObs:
    """Just enough of an Observation for the halo-centre code."""
    def __init__(self, image, saturated):
        self.image, self._bad = image, saturated
        self.flags = np.zeros(image.shape, np.int64)
        self.flag_names = {}
        self.shape = image.shape

    def hard_mask(self, strict=False):
        return self._bad


def test_halo_centre_follows_a_saturated_star_and_ignores_masked_pixels():
    from validation.barnard_halo import halo_centre
    yy, xx = np.indices((61, 61))
    x_true, y_true = 30.37, 29.62
    r = np.hypot(xx - x_true, yy - y_true)
    image = 5.0 + 4000.0 / (1.0 + (r / 1.5) ** 2.6)                 # a bright star with broad wings on a flat sky
    saturated = r < 2.6                                              # the core is unusable
    saturated[20:42, 31] = True                                      # and a bleed column off-centre
    c = halo_centre(_FakeObs(image, saturated), 30.0, 30.0)          # start half a pixel away
    assert c is not None
    assert math.hypot(c[0] - x_true, c[1] - y_true) < 0.12


def test_shift_and_stack_finds_a_mover_too_faint_for_any_single_image():
    """A synthetic point source at S/N ~2 per exposure, moving 1.2 px/day: invisible alone, found by stacking."""
    from pipeline import shiftstack
    rng = np.random.default_rng(11)
    n, size = 30, 70
    t = 61000 + np.sort(rng.uniform(0, 12, n))
    t0 = float(np.median(t))
    vx, vy, x0, y0 = 1.2, -0.7, 34.0, 36.0
    yy, xx = np.mgrid[0:size, 0:size]
    sig = 8.0 / shiftstack.PIX / 2.3548
    items = []
    for tk in t:
        cx, cy = x0 + vx * (tk - t0), y0 + vy * (tk - t0)
        star = 3.0 * np.exp(-((xx - 20) ** 2 + (yy - 50) ** 2) / (2 * sig * sig))          # a static star
        mover = 0.55 * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sig * sig))
        items.append({'mjd': float(tk), 'img': star + mover + rng.normal(0, 0.2, (size, size)), 'var': np.full((size, size), 0.04), 'sat': None})
    single = 0.55 / 0.2 * np.sqrt(np.sum(np.exp(-((xx - 35) ** 2 + (yy - 35) ** 2) / (2 * sig * sig)) ** 2))
    assert single < 4.5                                                                   # not detectable in one exposure
    res = shiftstack.search_visit(items, vmax=12.0, thresh=7.0)
    assert res['peaks'], 'no candidate found'
    p = res['peaks'][0]
    assert math.hypot(p['x'] - x0, p['y'] - y0) < 1.5
    assert abs(p['vx_px_day'] - vx) < 0.25 and abs(p['vy_px_day'] - vy) < 0.25
    assert p['snr'] > 10
