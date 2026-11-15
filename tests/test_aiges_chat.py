from datetime import date
from threading import RLock
from zipfile import ZipFile

from fastapi.testclient import TestClient
import httpx
import pytest

from api import discovery as routes
from api.app import app
from pipeline import aiges_chat
from pipeline.discovery_tasks import TaskScope, archive_intent, requested_workflow
from pipeline.research_archive import OpticalSurvey, query_chunk, survey


def test_questions_do_not_run_jobs(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setattr(routes, 'queue_search', lambda *args: pytest.fail('question queued a job'))
    with TestClient(app) as client:
        response = client.post('/api/discovery/tasks', json={'message': 'What do we know about Planet Nine?'})
        assert response.status_code == 200
        doc = response.json()
        assert 'not confirmed' in doc['reply']
        assert doc['sources'][0]['href'].startswith('https://authors.library.caltech.edu/')
        assert 'run' not in doc
        next_reply = client.post('/api/discovery/tasks', json={
            'message': 'How far away is it?', 'space_topic': doc['space_topic'],
        }).json()
        assert '380 AU' in next_reply['reply']
        assert 'run' not in next_reply


def test_task_scope_survives_a_conversation_and_returns_real_run_id(monkeypatch, tmp_path):
    monkeypatch.setattr(routes, 'RUNS', tmp_path)
    monkeypatch.setattr(routes, 'active', None)
    packet = {'kind': 'optical', 'receipts': [{'chunk': 'G-05', 'status': 'complete'}],
              'eligible_exposures': 2, 'repeat_groups': 1, 'groups': [], 'limits': []}

    def checked(scope, report):
        assert scope.chunks == ['G-05']
        assert isinstance(scope, OpticalSurvey)
        report('Checked two dates')
        return packet | {'request': scope.model_dump(mode='json')}

    monkeypatch.setattr(routes, 'survey', checked)
    monkeypatch.setattr(routes.pool, 'submit', lambda fn, *args: fn(*args))
    # Run on a background-style lock so the inline test callback can finish.
    monkeypatch.setattr(routes, 'lock', RLock())
    with TestClient(app) as client:
        start = client.post('/api/discovery/tasks', json={'message': 'Find deep optical images for a dwarf planet search.'})
        assert start.status_code == 200 and 'run' not in start.json()
        assert start.json()['draft']['workflow'] == 'optical'
        area = client.post('/api/discovery/tasks', json={'message': 'G-05', 'draft': start.json()['draft']})
        assert area.status_code == 200 and 'run' not in area.json()
        dates = client.post('/api/discovery/tasks', json={
            'message': '2024-10-01 to 2025-02-01', 'draft': area.json()['draft'],
        })
        assert dates.status_code == 202
        run_id = dates.json()['run']['id']
        state = client.get(f'/api/discovery/runs/{run_id}').json()
        assert state['state'] == 'complete'
        assert state['evidence']['eligible_exposures'] == 2
        assert state['evidence']['kind'] == 'optical'
        assert 'Checked two dates' in state['activity']
        assert client.get(f'/api/discovery/runs/{run_id}/files/evidence.zip').status_code == 200
        with ZipFile(tmp_path / run_id / 'evidence.zip') as archive:
            assert archive.namelist() == ['evidence.json']
        summary = client.post('/api/discovery/tasks', json={
            'message': 'What did you find?', 'previous_run': run_id,
        }).json()
        assert '2 eligible DECam exposures' in summary['reply']


def test_paper_search_takes_priority_over_sky_jobs():
    draft = TaskScope(chunks=['G-05'], start=date(2024, 1, 1), end=date(2024, 2, 1))
    assert not archive_intent('Find papers about Planet Nine', draft, None)
    assert not archive_intent('What is an asteroid in G-05?', draft, None)
    assert archive_intent('Look for unknown planets in G-05', None, None)
    assert requested_workflow('Search this chunk', None, None) == 'optical'
    assert requested_workflow('Search for asteroids in G-05', None, None) == 'linkage'


@pytest.mark.parametrize(('deep', 'model'), [(False, 'gpt-6.1-sol'), (True, 'gpt-6.1-terra')])
def test_model_is_chosen_on_server_and_outputs_grounded_sources(monkeypatch, deep, model):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only')
    monkeypatch.delenv('PARALLAX_OPENAI_MODEL', raising=False)
    monkeypatch.delenv('PARALLAX_OPENAI_CHAT_MODEL', raising=False)

    def request(url, **kwargs):
        assert kwargs['json']['model'] == model
        assert kwargs['json']['store'] is False
        result = {'status': 'completed', 'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': '{"reply":"An observation.","sources":[1]}'},
        ]}]}
        return httpx.Response(200, json=result, request=httpx.Request('POST', url))

    monkeypatch.setattr(aiges_chat.httpx, 'post', request)
    refs = [{'label': 'Primary evidence', 'href': 'https://example.org/observation'}]
    assert aiges_chat.model_reply('What was observed?', [], refs, deep) == {'reply': 'An observation.', 'sources': refs}


def test_optical_archive_filters_products_and_counts_utc_nights(monkeypatch):
    import pipeline.research_archive as research
    scope = OpticalSurvey(chunks=['G-05'], start='2024-01-01', end='2024-02-01')
    template = {'archive_filename': 'image.fits.fz', 'md5sum': 'a' * 32, 'release_date': '2024-01-20',
                'ra_center': 65.0, 'dec_center': 7.7, 'exposure': 100, 'ifilter': 'i band', 'proposal': 'example',
                'seeing': .9, 'PHOTDPTH': 23.8}
    rows = [{}, template | {'EXPNUM': 1, 'dateobs_min': '2024-01-10T01:01:00Z'},
            template | {'EXPNUM': 2, 'dateobs_min': '2024-01-10T03:01:00Z'},
            template | {'EXPNUM': 3, 'dateobs_min': '2024-01-15T03:01:00Z'},
            template | {'EXPNUM': 4, 'dateobs_min': '2024-01-15T03:01:00Z', 'PHOTDPTH': 20.5},
            template | {'EXPNUM': 5, 'dateobs_min': '2024-01-15T03:01:00Z', 'ra_center': 80.0}]

    def archive(url, **kwargs):
        assert ['instrument', 'decam'] in kwargs['json']['search']
        return httpx.Response(200, json=rows, request=httpx.Request('POST', url))

    monkeypatch.setattr(research.httpx, 'post', archive)
    receipt, exposures = query_chunk(scope, 'G-05')
    assert receipt['status'] == 'complete' and receipt['response_sha256']
    assert len(exposures) == 3
    result = survey(scope, lambda _: None)
    assert result['eligible_exposures'] == 3
    assert result['groups'][0]['nights'] == 2
    assert result['repeat_groups'] == 1
