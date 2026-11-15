from datetime import date

from pipeline.discovery_tasks import RESULT_QUESTION, TaskScope, interpret_task, result_reply


def test_description_selects_chunks_dates_and_archive_followup():
    scope, question = interpret_task('Search h-2 and H-03 from October 20 to Nov 13, 2026, then look for follow-up images.')
    assert question is None
    assert scope.chunks == ['H-02', 'H-03']
    assert (scope.start, scope.end) == (date(2026, 10, 20), date(2026, 11, 13))
    assert scope.task == 'search_followup'


def test_clarification_completes_the_original_task():
    draft, question = interpret_task('Look for moving objects in H-02.')
    assert draft.chunks == ['H-02'] and 'dates' in question
    scope, question = interpret_task('2026-10-20 to 2026-11-13', draft=draft)
    assert question is None and scope.chunks == ['H-02']
    assert scope.end == date(2026, 11, 13)


def test_followup_refers_to_the_previous_job():
    previous = TaskScope(chunks=['H-02'], start=date(2026, 10, 20), end=date(2026, 11, 13))
    scope, question = interpret_task('Find images for that search.', previous=previous)
    assert question is None and scope.task == 'search_followup'
    assert scope.chunks == previous.chunks and scope.start == previous.start


def test_replay_and_unsupported_requests():
    scope, question = interpret_task('Replay NW034 and check SPHEREx.')
    assert question is None and scope.benchmark and scope.task == 'search_followup'
    assert interpret_task('What color is Mars?')[1]
    assert interpret_task('Search H-02 and H-03 and H-04 from 2026-10-20 to 2026-11-13')[1]


def test_map_chunk_applies_only_when_named_by_reference():
    dates = 'from 2026-10-20 to 2026-11-13'
    scope, question = interpret_task(f'Search this chunk {dates} without follow-up images.', map_chunk='H-02')
    assert question is None and scope.chunks == ['H-02'] and scope.task == 'search'
    assert interpret_task(f'Search {dates}', map_chunk='H-02')[1]


def test_result_question_summarizes_completed_evidence():
    assert RESULT_QUESTION.fullmatch('What did the last run find?')
    result = result_reply({'candidates': [{}], 'followup': {'status': 'incomplete'}})
    assert '1 ranked asteroid linkage.' in result
    assert 'could not be completed' in result
