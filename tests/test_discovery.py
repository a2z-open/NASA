from datetime import date
import json

import httpx
import pytest
from pydantic import ValidationError

from pipeline.discovery import SearchRequest, chunk_region, evidence_order, plan_evidence


def test_chunk_edges_match_the_map_grid():
    cell = chunk_region('G-24')
    assert (cell.ra_min, cell.ra_max) == (345, 360)
    assert cell.dec_min == 0
    assert cell.dec_max == pytest.approx(9.5940682269)


def test_duplicate_chunks_and_reversed_dates_are_rejected():
    with pytest.raises(ValidationError):
        SearchRequest(chunks=['G-01', 'G-01'], start=date(2026, 10, 10), end=date(2026, 11, 11))
    with pytest.raises(ValidationError):
        SearchRequest(chunks=['G-01'], start=date(2026, 11, 11), end=date(2026, 10, 10))


def test_planner_can_prioritize_pixels_but_both_checks_run():
    assert evidence_order('pixels') == ('pixels', 'catalog')
    assert evidence_order('catalog') == ('catalog', 'pixels')
    with pytest.raises(ValueError):
        evidence_order('change the fitted orbit')


def test_benchmark_pins_train_and_holdout_to_separate_dates():
    spec = SearchRequest(benchmark=True).engine_spec()
    assert spec['regions'] == [{'ra_min': 24, 'ra_max': 38, 'dec_min': -6, 'dec_max': 24}]
    assert spec['fit_start'] == '2026-10-20'
    assert spec['fit_end'] == '2026-11-09'
    assert spec['test_end'] == '2026-11-13'


@pytest.mark.parametrize(('selected', 'expected'), [(None, 'gpt-6.1-terra'), ('gpt-6.1-sol', 'gpt-6.1-sol')])
def test_openai_planner_sends_selected_model_and_only_a_fitted_summary(monkeypatch, selected, expected):
    monkeypatch.setenv('OPENAI_API_KEY', 'fake-test-key')
    monkeypatch.delenv('PARALLAX_OPENAI_MODEL', raising=False)
    request = SearchRequest(benchmark=True, planner_model=selected)

    def response(url, **options):
        assert url == 'https://api.openai.com/v1/responses'
        body = options['json']
        assert body['model'] == expected
        assert not body['store']
        assert json.loads(body['input']) == [
            {'fit_observations': 1, 'test_observations': 0, 'catalina_observations': 1, 'fit_rms_arcsec': 0.28}]
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'status': 'completed', 'id': 'response-fixture', 'model': expected, 'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': '{"first":"pixels","reason":"Check the Catalina exposures."}'}]}]})

    monkeypatch.setattr(httpx, 'post', response)
    plan = plan_evidence([{'orbit': {'rms_arcsec': .28},
                          'observations': [{'phase': 'fit', 'station': 'G96', 'obs80': 'raw source record'}]}],
                         True, request.planner_model)
    assert plan['status'] == 'used'
    assert plan['requested_model'] == expected == plan['model']
    assert plan['order'] == ['pixels', 'catalog']


def test_unavailable_model_falls_back_without_using_a_different_model(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'fake-test-key')
    calls = []

    def response(url, **options):
        calls.append(options['json']['model'])
        return httpx.Response(404, request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx, 'post', response)
    plan = plan_evidence([{'orbit': {}, 'observations': []}], True, 'gpt-6.1-sol')
    assert calls == ['gpt-6.1-sol']
    assert plan == {'status': 'fallback', 'order': ['catalog', 'pixels'],
                    'requested_model': 'gpt-6.1-sol', 'failure': 'model_access'}


def test_followup_checks_the_selected_saved_prediction_then_tries_the_other(monkeypatch):
    from pipeline import discovery_followup as work

    rows = [
        {'night': '2026-11-13', 'mjd_utc': 61357.25, 'phase': 'test', 'station': 'G96',
         'predicted_ra_deg': 25.1, 'predicted_dec_deg': 8.2, 'sigma_major_arcsec': 1.1},
        {'night': '2026-10-04', 'mjd_utc': 61317.25, 'phase': 'test', 'station': 'F52',
         'predicted_ra_deg': 26.1, 'predicted_dec_deg': 9.2, 'sigma_major_arcsec': 9.1},
    ]
    prompts = work.predicted_fields([{'id': 'NW034', 'observations': rows}])
    calls = []

    def check(field):
        calls.append(field['night'])
        if field['night'] == '2026-10-04':
            return {'status': 'no_results', 'products': []}
        return {'status': 'found', 'products': [{'id': 'real-product'}]}

    monkeypatch.setattr(work, 'query_field', check)
    task = work.run_followup(prompts, 1)
    assert calls == ['2026-10-04', '2026-11-13']
    assert task['status'] == 'found'
    assert task['checks'][1]['field']['ra'] == 25.1


def test_followup_never_reports_unanswered_archive_as_empty(monkeypatch):
    from pipeline import discovery_followup as work

    monkeypatch.setattr(work, 'query_field', lambda _: {'status': 'incomplete', 'products': []})
    task = work.run_followup([{'night': '2026-11-13'}], 0)
    assert task['status'] == 'incomplete'


def test_planner_can_select_only_a_saved_prediction(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'fake-test-key')
    selected = 1

    def reply(url, **options):
        body = options['json']
        assert body['text']['format']['schema']['properties']['followup_first']['enum'] == [0, 1]
        assert [x['night'] for x in json.loads(body['input'])['followup_predictions']] == ['2026-11-13', '2026-10-04']
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(
                {'first': 'catalog', 'reason': 'Look near the earlier prediction.', 'followup_first': selected})}]}]})

    monkeypatch.setattr(httpx, 'post', reply)
    fields = [{'night': '2026-11-13'}, {'night': '2026-10-04'}]
    candidates = [{'orbit': {}, 'observations': []}]
    assert plan_evidence(candidates, True, followups=fields)['followup_first'] == 1
    selected = 42
    plan = plan_evidence(candidates, True, followups=fields)
    assert (plan['status'], plan['followup_first']) == ('fallback', 0)
