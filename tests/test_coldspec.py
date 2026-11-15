"""Cold-world spectra: type parsing, features, the solar-system name lookup table, and the "check a candidate" API.

No network.  The API tests use the committed queue (validation/coldspec/check_queue.json) and write votes to a
temporary file, never to the real one.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / 'validation' / 'coldspec' / 'check_queue.json'


def test_numeric_type():
    from validation.coldspec import numeric_type
    assert numeric_type('M8V') == 8
    assert numeric_type('L3.5') == 13.5
    assert numeric_type('T6.5') == 26.5
    assert numeric_type('Y0') == 30
    assert numeric_type('T0p') == 20
    for bad in ('', 'sdL7', 'L3+T1', 'M9III', 'K5V', 'M'):
        assert numeric_type(bad) is None, bad


def test_features_see_methane_and_ignore_brightness():
    """A spectrum with the 1.7 micron band removed has a strongly negative methane index, at any brightness."""
    from pipeline.cubespec import WAVES
    from validation.coldspec import FEATURES, features
    flat = np.where(np.isin(np.arange(len(WAVES)), [50, 51]), np.nan, 1000.0)
    err = np.full(len(WAVES), 20.0)
    dip = flat.copy()
    dip[(WAVES >= 1.66) & (WAVES < 1.78)] = 50.0
    i = FEATURES.index('ch4_H')
    x_flat, meta = features(WAVES, flat, err)
    x_dip, _ = features(WAVES, dip, err)
    x_faint, _ = features(WAVES, dip / 10, err / 10)
    assert abs(x_flat[i]) < 0.02 and x_dip[i] < -0.8
    assert np.allclose(x_dip, x_faint)                      # shape only: scaling the spectrum changes nothing
    assert meta['snr_J'] > 50 and np.isfinite(x_flat).all()


def test_solar_system_names_are_known():
    from pipeline import ephem
    for name in ('sun', 'moon', 'mars', 'pluto', 'makemake', 'eris', 'sedna'):
        assert name in ephem.SOLAR, name


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import api.app as appmod
    monkeypatch.setattr(appmod, 'CHECK_VOTES', tmp_path / 'votes.jsonl')
    return TestClient(appmod.app)


@pytest.mark.skipif(not QUEUE.is_file(), reason='check queue not built')
def test_check_queue_hides_answers_and_counts_votes(client):
    q = client.get('/api/check').json()
    full = json.loads(QUEUE.read_text())
    assert len(q['items']) == len(full['items']) > 10 and q['total_votes'] == 0
    for it in q['items']:                                    # nothing that gives the answer away before a vote
        assert not {'truth', 'truth_label', 'name', 'model'} & set(it)
        assert it['spectrum'] and it['votes'] == 0
    known = next(it for it in full['items'] if it['truth'] == 'dips')
    r = client.post('/api/check', json={'id': known['id'], 'answer': 'dips', 'name': '<b>Ada</b> Lovelace, the first programmer'}).json()
    assert r['agrees_with_known'] is True and r['tally'] == {'dips': 1, 'smooth': 0, 'unsure': 0, 'n': 1} and r['name'] == known['name']
    r = client.post('/api/check', json={'id': known['id'], 'answer': 'smooth'}).json()
    assert r['agrees_with_known'] is False and r['tally']['n'] == 2
    unknown = next(it for it in full['items'] if it['kind'] == 'unknown')
    r = client.post('/api/check', json={'id': unknown['id'], 'answer': 'unsure'}).json()
    assert r['agrees_with_known'] is None and r['truth'] is None and r['total_votes'] == 3
    assert client.get('/api/check').json()['total_votes'] == 3
    import api.app as appmod
    saved = [json.loads(line) for line in appmod.CHECK_VOTES.read_text().splitlines()]
    assert saved[0]['name'] == 'bAdab Lovelace the first' and '<' not in saved[0]['name']      # tags stripped, 24 characters at most


@pytest.mark.skipif(not QUEUE.is_file(), reason='check queue not built')
def test_check_rejects_bad_votes(client):
    assert client.post('/api/check', json={'id': 'nope', 'answer': 'dips'}).status_code == 400
    first = json.loads(QUEUE.read_text())['items'][0]['id']
    assert client.post('/api/check', json={'id': first, 'answer': 'maybe'}).status_code == 400
    assert client.post('/api/check', content=b'not json').status_code == 400


def test_coldspec_endpoint_reports_the_vetting(client):
    r = client.get('/api/coldspec')
    if r.status_code == 404:
        pytest.skip('search not run')
    d = r.json()
    assert d['cv']['held_out']['false_T'] <= 2 and d['cv']['threshold_p_T'] >= 0.9
    if d['results'] and d['vetting']:
        assert 'typed' not in d['results']
        flagged = {c['name'] for c in d['results']['candidates']}
        assert flagged == {c['name'] for c in d['vetting']['candidates']}
