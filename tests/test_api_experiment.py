"""API contract and held-out isolation tests (uses the committed curated data; no network)."""

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def client():
    from api.app import app
    return TestClient(app)


def test_health_and_targets(client):
    assert client.get('/api/health').json()['ok'] is True
    targets = client.get('/api/targets').json()
    assert [t['slug'] for t in targets] == ['epsilon-indi-b', 'barnards-star', 'wise-0855', 'rw-aurigae', 'r-draconis']


def test_invalid_coordinates_rejected(client):
    r = client.post('/api/fields', json={'ra': 'abc', 'dec': 10})
    assert r.status_code == 400
    r = client.post('/api/fields', json={'ra': 10, 'dec': 95})
    assert r.status_code == 400
    r = client.post('/api/fields', json={'ra': 10, 'dec': 10, 'fov_arcmin': 90})
    assert r.status_code == 400


def test_resolve_coordinates_and_known_alias(client):
    r = client.get('/api/resolve', params={'q': '08h55m10.831s -07d14m42.53s'}).json()
    assert r['ra'] == pytest.approx(133.7951292, abs=1e-6)
    r = client.get('/api/resolve', params={'q': 'WISE 0855'}).json()
    assert r['target'] == 'wise-0855'
    # propagated far from the historical 2010-era coordinate (about 8 arcsec/yr)
    assert abs(r['ra'] - 133.7951292) * 3600 * 0.992 > 60


@pytest.mark.skipif(not (ROOT / 'data/targets/epsilon-indi-b/investigation.json').exists(), reason='curated data not built')
def test_curated_field_and_investigation_contract(client):
    f = client.get('/api/fields/epsilon-indi-b').json()
    assert f['grid']['row0'] == 'north' and f['frames']
    fr = f['frames'][0]
    for key in ('id', 'mjd', 'time_utc', 'detector', 'release', 'wavelength_um', 'data_url', 'sha256', 'archive_url'):
        assert key in fr
    blob = client.get(fr['data_url']).content
    assert len(blob) == f['grid']['nx'] * f['grid']['ny'] * 2
    inv = client.get('/api/investigations/epsilon-indi-b').json()
    assert {h['id'] for h in inv['hypotheses']} == {'H0', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6'}
    csv = client.get('/api/investigations/epsilon-indi-b/export', params={'format': 'csv'})
    assert csv.status_code == 200 and 'product_id' in csv.text and '10.26131/IRSA678' in csv.text


def test_unknown_ids_404(client):
    assert client.get('/api/investigations/inothere00000').status_code == 404
    assert client.get('/api/fields/fnot.there').status_code == 404
    assert client.get('/api/no-such-endpoint').status_code == 404
    r = client.get('/files/targets/epsilon-indi-b/..%2F..%2F..%2FREADME.md')
    assert r.status_code == 404


# ------------------------------------------------------------- held-out isolation

EXP = ROOT / 'validation/experiments/epsilon-indi-b'


@pytest.mark.skipif(not (EXP / 'prediction.json').exists(), reason='experiment not run')
def test_prediction_hash_matches_and_heldout_not_in_training():
    blob = (EXP / 'prediction.json').read_bytes()
    assert hashlib.sha256(blob).hexdigest() == (EXP / 'prediction.sha256').read_text().split()[0]
    pred = json.loads(blob)
    held = set(pred['held_out']['product_ids'])
    train = json.loads((EXP / 'training_measurements.json').read_text())
    assert held and not held & {r.get('product_id') for r in train}
    assert max(r['mjd'] for r in train if r.get('mjd')) < pred['held_out']['visit']['mjd_start']
    assert pred['held_out']['pixels_inspected_before_lock'] is False


def test_lock_refuses_when_heldout_pixels_exist(tmp_path, monkeypatch):
    from validation import experiment
    monkeypatch.setattr(experiment, 'CACHE', tmp_path)
    monkeypatch.setattr(experiment, 'EXP', tmp_path / 'exp')
    (tmp_path / 'targets/epsilon-indi-b/raw').mkdir(parents=True)
    man = json.loads((ROOT / 'data/targets/epsilon-indi-b/archive_manifest.json').read_text())
    sealed = [p for p in man['products'] if p.get('sealed')]
    if not sealed:
        pytest.skip('no sealed products in manifest')
    (tmp_path / 'targets/epsilon-indi-b/raw' / f"{sealed[0]['id']}.fits").write_bytes(b'x')
    monkeypatch.setattr(experiment, 'field_setup', lambda slug: (None, man, []))
    with pytest.raises(SystemExit, match='Refusing to lock'):
        experiment.lock('epsilon-indi-b')


def test_reveal_refuses_tampered_prediction(tmp_path, monkeypatch):
    from validation import experiment
    d = tmp_path / 'exp/x'
    d.mkdir(parents=True)
    (d / 'prediction.json').write_text('{"a": 1}\n')
    (d / 'prediction.sha256').write_text('0' * 64 + '  prediction.json\n')
    monkeypatch.setattr(experiment, 'EXP', tmp_path / 'exp')
    with pytest.raises(SystemExit, match='does not match'):
        experiment.reveal('x')
