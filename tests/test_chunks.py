from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from api.app import app


@pytest.fixture
def clients(monkeypatch, tmp_path):
    monkeypatch.setenv('PARALLAX_CHUNKS_DB', str(tmp_path / 'chunks.sqlite3'))
    return TestClient(app), TestClient(app)


def update(client, action, chunk='I-14', **data):
    return client.post(f'/api/chunks/{chunk}', json={'action': action, **data})


def test_named_claim_is_shared_and_only_owner_can_advance(clients):
    owner, teammate = clients
    assert owner.get('/api/chunks').json() == {}
    teammate.get('/api/chunks')
    assert update(owner, 'claim', name='  Lavi  ').json() == {'status': 'claimed', 'name': 'Lavi', 'mine': True, 'teammates': []}
    assert teammate.get('/api/chunks').json()['I-14'] == {'status': 'claimed', 'name': 'Lavi', 'mine': False, 'teammates': []}
    assert update(teammate, 'claim', name='Lavi').status_code == 409
    assert update(teammate, 'start').status_code == 403
    assert update(owner, 'review').status_code == 409
    assert update(owner, 'start').json()['status'] == 'in_progress'
    assert update(owner, 'review').json()['status'] == 'reviewed'
    assert teammate.get('/api/chunks').json()['I-14']['name'] == 'Lavi'
    assert update(owner, 'reopen').json()['status'] == 'in_progress'
    assert update(owner, 'release').json() is None
    assert 'I-14' not in teammate.get('/api/chunks').json()


def test_one_claim_wins_when_two_people_claim_together(clients):
    gate = Barrier(2)
    for client in clients:
        client.get('/api/chunks')

    def claim(client, name):
        gate.wait(timeout=5)
        return update(client, 'claim', name=name).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(claim, clients, ('Pat', 'Sam')))
    assert sorted(codes) == [200, 409]


def test_rejects_unknown_chunk_and_blank_name(clients):
    client, _ = clients
    assert client.get('/api/chunks').status_code == 200
    assert update(client, 'claim', chunk='I-25', name='Lavi').status_code == 404
    assert update(client, 'claim', name='   ').status_code == 422


def test_teammates_join_share_status_and_leave(clients):
    lead, teammate = clients
    assert update(lead, 'claim', name='Lavi').status_code == 200
    assert update(teammate, 'join', name='Sam').json()['teammates'] == [{'name': 'Sam', 'mine': True}]
    assert update(teammate, 'join', name='Sam').json()['teammates'] == [{'name': 'Sam', 'mine': True}]
    assert lead.get('/api/chunks').json()['I-14']['teammates'] == [{'name': 'Sam', 'mine': False}]
    assert update(teammate, 'start').json()['status'] == 'in_progress'
    assert update(lead, 'release').status_code == 409
    assert update(teammate, 'review').json()['status'] == 'reviewed'
    assert lead.get('/api/chunks').json()['I-14']['status'] == 'reviewed'
    assert update(teammate, 'leave').json()['teammates'] == []


def test_team_server_requires_access_password(clients, monkeypatch):
    monkeypatch.setenv('PARALLAX_TEAM_PASSWORD', 'test-only-password')
    client, _ = clients
    for url in ['/api/health', '/api/chunks']:
        assert client.get(url).status_code == 401
        assert client.get(url, auth=('team', 'test-only-password')).status_code == 200
