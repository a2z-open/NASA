import json
import os
from pathlib import Path

import pytest

from pipeline.discovery_engine import run_search, source_ready, wrapped_delta


BENCHMARK = {
    'regions': [{'ra_min': 24, 'ra_max': 38, 'dec_min': -6, 'dec_max': 24}],
    'start': '2026-10-04', 'fit_start': '2026-10-20', 'fit_end': '2026-11-09',
    'test_end': '2026-11-13', 'end': '2026-11-13', 'benchmark': True,
}


def test_invalid_inputs_fail_before_accessing_archive(tmp_path):
    with pytest.raises(ValueError, match='windows'):
        run_search({**BENCHMARK, 'fit_end': '2026-11-14'}, tmp_path)
    assert not list(tmp_path.iterdir())


def test_angular_difference_across_zero_meridian():
    assert wrapped_delta(.001, 359.999) == pytest.approx(.002)
    assert wrapped_delta(359.999, .001) == pytest.approx(-.002)


@pytest.mark.skipif(os.getenv('PARALLAX_RUN_ARCHIVE_REPLAY') != '1', reason='opt-in pinned archive replay')
def test_nw034_replay_reads_original_rows_and_keeps_tests_disjoint(tmp_path):
    assert source_ready()
    result = run_search(BENCHMARK, tmp_path)
    candidate = next(row for row in result['candidates'] if row['id'] == 'NW034')
    by_stage = {stage: [row for row in candidate['observations'] if row['stage'] == stage]
                for stage in ('training', 'later_holdout', 'earlier_extension')}
    assert [len(rows) for rows in by_stage.values()] == [15, 4, 3]
    assert {r['night'] for r in by_stage['later_holdout']} == {'2026-11-13'}
    assert {r['night'] for r in by_stage['earlier_extension']} == {'2026-10-04'}
    assert len({r['line_sha256'] for r in candidate['observations']}) == 22
    assert candidate['orbit']['rms_arcsec'] == pytest.approx(.280187, abs=.001)
    assert candidate['arc_days'] == pytest.approx(39.855838, abs=.00001)
    assert candidate['tests']['earlier_extension']['groups'][0]['positions'][0]['residual_arcsec'] == pytest.approx(15.70, abs=.15)
    assert candidate['tests']['later_holdout']['training_sha256'] == result['artifacts']['training-fits.json']
    json.dumps(result, allow_nan=False)
