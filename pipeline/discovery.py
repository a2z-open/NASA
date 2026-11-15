"""Run a bounded asteroid linkage search and save a reviewable evidence packet."""

from __future__ import annotations

import argparse
from datetime import date
import json
from math import asin, degrees
import os
from pathlib import Path
import re
from shutil import copyfile
from typing import Callable, Literal
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

CHUNK_ID = re.compile(r'[A-L]-(?:0[1-9]|1[0-9]|2[0-4])')
BENCHMARK_START = date(2026, 10, 4)
BENCHMARK_END = date(2026, 11, 13)
BENCHMARK_REGION = {'ra_min': 24, 'ra_max': 38, 'dec_min': -6, 'dec_max': 24}
MAX_SEARCH_DAYS = 90
PlannerModel = Literal['gpt-6.1-terra', 'gpt-6.1-sol']
SearchTask = Literal['search', 'search_followup']
PLANNER_MODELS = {'gpt-6.1-terra': 'GPT-6.1 Terra', 'gpt-6.1-sol': 'GPT-6.1 Sol'}
MODEL_FAILURES = {401: 'authentication', 403: 'model_access', 404: 'model_access', 429: 'rate_limit'}


def default_planner_model() -> str:
    return os.getenv('PARALLAX_OPENAI_MODEL', '').strip() or 'gpt-6.1-terra'


class Region(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ra_min: float = Field(ge=0, lt=360)
    ra_max: float = Field(gt=0, le=360)
    dec_min: float = Field(ge=-90, lt=90)
    dec_max: float = Field(gt=-90, le=90)

    @model_validator(mode='after')
    def edges(self):
        if self.ra_min >= self.ra_max or self.dec_min >= self.dec_max:
            raise ValueError('Region bounds must increase. Split a region across 0° RA into two regions.')
        return self


def chunk_region(chunk: str) -> Region:
    if not CHUNK_ID.fullmatch(chunk):
        raise ValueError(f'Unknown sky chunk {chunk}. Use A-01 through L-24.')
    row = ord(chunk[0]) - ord('A')
    column = int(chunk[2:]) - 1
    return Region(ra_min=15 * column, ra_max=15 * (column + 1),
                  dec_min=degrees(asin((row - 6) / 6)), dec_max=degrees(asin((row - 5) / 6)))


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    chunks: list[str] = Field(default_factory=list, max_length=2)
    regions: list[Region] = Field(default_factory=list, max_length=2)
    start: date | None = None
    end: date | None = None
    fit_start: date | None = None
    fit_end: date | None = None
    test_end: date | None = None
    benchmark: bool = False
    use_ai: bool = True
    planner_model: PlannerModel | None = None
    task: SearchTask = 'search'

    @model_validator(mode='after')
    def scope(self):
        if self.benchmark:
            if self.chunks or self.regions or any((self.start, self.end, self.fit_start, self.fit_end, self.test_end)):
                raise ValueError('The NW034 replay sets its own region and dates.')
            return self
        if bool(self.chunks) == bool(self.regions):
            raise ValueError('Choose one or two chunks or provide explicit sky bounds.')
        if len(set(self.chunks)) != len(self.chunks):
            raise ValueError('Choose distinct chunks.')
        for chunk in self.chunks:
            chunk_region(chunk)
        if not self.start or not self.end or not 4 <= (self.end - self.start).days < MAX_SEARCH_DAYS:
            raise ValueError(f'Choose a date range of 5 to {MAX_SEARCH_DAYS} UTC days.')
        if self.fit_start and not self.start <= self.fit_start < self.end:
            raise ValueError('The fit start must fall within the search dates.')
        if self.fit_end and not (self.fit_start or self.start) < self.fit_end < self.end:
            raise ValueError('The fit must end before the final observation date.')
        if self.test_end and (not self.fit_end or not self.fit_end < self.test_end <= self.end):
            raise ValueError('The holdout must end after the fit and within the search dates.')
        return self

    def engine_spec(self) -> dict:
        if self.benchmark:
            return {'regions': [BENCHMARK_REGION.copy()], 'start': BENCHMARK_START.isoformat(),
                    'end': BENCHMARK_END.isoformat(), 'fit_start': '2026-10-20', 'fit_end': '2026-11-09',
                    'test_end': '2026-11-13', 'benchmark': True}
        areas = self.regions or [chunk_region(chunk) for chunk in self.chunks]
        spec = {name: getattr(self, name).isoformat() for name in ('start', 'end', 'fit_start', 'fit_end', 'test_end')
                if getattr(self, name) is not None}
        return {**spec, 'regions': [region.model_dump() for region in areas], 'chunks': self.chunks, 'benchmark': False}


def evidence_order(first: Literal['catalog', 'pixels']) -> tuple[str, str]:
    if first == 'catalog':
        return 'catalog', 'pixels'
    if first == 'pixels':
        return 'pixels', 'catalog'
    raise ValueError('Unexpected planner action.')


def plan_evidence(candidates: list[dict], enabled: bool, selected_model: PlannerModel | None = None,
                  followups: list[dict] | None = None, *, archive_only: bool = False) -> dict:
    default = {'order': [] if archive_only else list(evidence_order('catalog'))}
    if followups:
        default['followup_first'] = 0
    if not enabled:
        return default | {'status': 'disabled'}
    model = selected_model or default_planner_model()
    default['requested_model'] = model
    if not candidates:
        return default | {'status': 'no_candidates'}
    if archive_only and not followups:
        return default | {'status': 'no_predictions'}
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        return default | {'status': 'unconfigured'}

    summary = []
    for candidate in candidates[:12]:
        rows = candidate['observations']
        summary.append({'fit_observations': sum(row['phase'] == 'fit' for row in rows),
                        'test_observations': sum(row['phase'] == 'test' for row in rows),
                        'catalina_observations': sum(row['station'] == 'G96' for row in rows),
                        'fit_rms_arcsec': candidate['orbit'].get('rms_arcsec')})
    instructions = (
        'Prioritize evidence checks for asteroid linkages. Choose catalog to resolve identity first, '
        'or pixels to inspect original Catalina images for motion or artifacts. Both checks will run. '
        'Give one short reason. You cannot change measurements, fits, scores, or identification verdicts.'
    )
    properties = {'first': {'type': 'string', 'enum': ['catalog', 'pixels']}, 'reason': {'type': 'string'}}
    if archive_only:
        instructions = 'Choose the first public image archive query for this asteroid candidate. Give one short reason.'
        properties.pop('first')
    model_input = summary
    if followups:
        instructions += (
            ' Also choose which saved prediction should drive the first real SPHEREx archive query. '
            'Prefer the date with better positional certainty when the available records support that choice. '
            'Pick an index from followup_predictions. The runner will try another night if it finds no images.'
        )
        properties['followup_first'] = {'type': 'integer', 'enum': list(range(len(followups)))}
        model_input = {'linkages': summary, 'followup_predictions': [
            {'index': index, **{key: field.get(key) for key in ('night', 'station', 'sigma_major_arcsec')}}
            for index, field in enumerate(followups)]}
    fallback = default | {'status': 'fallback'}
    try:
        reply = httpx.post(
            'https://api.openai.com/v1/responses',
            headers={'Authorization': f'Bearer {key}'},
            timeout=25,
            json={
                'model': model, 'store': False, 'max_output_tokens': 700,
                'instructions': instructions,
                'input': json.dumps(model_input, allow_nan=False),
                'text': {'format': {'type': 'json_schema', 'name': 'evidence_priority', 'strict': True, 'schema': {
                    'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False,
                }}},
            },
        )
        reply.raise_for_status()
        doc = reply.json()
        if doc['status'] != 'completed':
            return fallback | {'failure': 'incomplete_response'}
        raw = next(part['text'] for item in doc['output'] if item['type'] == 'message'
                   for part in item['content'] if part['type'] == 'output_text')
        decision = json.loads(raw)
        plan = {'status': 'used', 'requested_model': model, 'model': doc.get('model') or model,
                'order': [] if archive_only else list(evidence_order(decision['first'])),
                'reason': decision['reason'].strip()[:280],
                'response_id': doc.get('id')}
        if followups:
            index = decision['followup_first']
            if type(index) is not int or not 0 <= index < len(followups):
                return fallback | {'failure': 'invalid_response'}
            plan['followup_first'] = index
        return plan
    except httpx.HTTPStatusError as error:
        return fallback | {'failure': MODEL_FAILURES.get(error.response.status_code, 'request')}
    except httpx.HTTPError:
        return fallback | {'failure': 'request'}
    except (ValueError, KeyError, TypeError, AttributeError, StopIteration):
        return fallback | {'failure': 'invalid_response'}


def write_json(path: Path, payload: dict) -> None:
    pending = path.with_suffix(path.suffix + '.tmp')
    pending.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n')
    pending.replace(path)


def evidence_assets(result: dict) -> set[str]:
    files = set(result['artifacts'])
    for candidate in result['candidates']:
        files.update(frame['file'] for frame in candidate['images']['frames'])
    return files


def bundle_evidence(output: Path, result: dict) -> Path:
    target = output / 'evidence.zip'
    pending = target.with_suffix('.zip.tmp')
    with ZipFile(pending, 'w', compression=ZIP_DEFLATED) as packet:
        for name in sorted({'evidence.json', *evidence_assets(result)}):
            packet.write(output / name, arcname=name)
    pending.replace(target)
    return target


def run(request: SearchRequest, output: Path, report: Callable[[str], None] = lambda _: None,
        *, reuse: Path | None = None) -> dict:
    from .discovery_engine import run_search
    from .discovery_evidence import attach_evidence
    from .discovery_followup import predicted_fields, run_followup

    output.mkdir(parents=True, exist_ok=True)
    spec = request.engine_spec()
    activity = []

    def step(message):
        activity.append(message)
        report(message)

    if reuse is None:
        step('Opening the pinned MPC archive')
        result = run_search(spec, output, step)
    else:
        step('Loading the saved linkages and frozen predictions')
        result = json.loads((reuse / 'evidence.json').read_text())
        for name in evidence_assets(result):
            source, target = (reuse / name).resolve(), (output / name).resolve()
            if reuse.resolve() not in source.parents or output.resolve() not in target.parents:
                raise ValueError('Invalid saved evidence path.')
            target.parent.mkdir(parents=True, exist_ok=True)
            copyfile(source, target)
        spec = result['request']
        result['reused_from'] = reuse.name
    fields = predicted_fields(result['candidates']) if request.task == 'search_followup' else []
    step('Choosing the next evidence check')
    planner = plan_evidence(result['candidates'], request.use_ai, request.planner_model, fields,
                            archive_only=reuse is not None)
    if reuse is None:
        labels = {'catalog': 'catalog comparisons', 'pixels': 'original images'}
        step('Checking ' + ' and '.join(labels[action] for action in planner['order']))
        attach_evidence(result, output, order=tuple(planner['order']))
    if request.task == 'search_followup':
        result['followup'] = run_followup(fields, planner.get('followup_first', 0), step)
    step('Saving the evidence packet')
    result.update({'request': spec | {'task': request.task}, 'planner': planner, 'activity': activity})
    # Put catalog matches after review candidates while preserving the scientific ordering in each group.
    result['candidates'].sort(key=lambda candidate: bool(candidate['catalog'].get('exclude_from_novel_review')))
    for index, candidate in enumerate(result['candidates'], 1):
        candidate['rank'] = index
    write_json(output / 'evidence.json', result)
    bundle_evidence(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chunk', action='append', default=[], help='One of up to two sky chunk IDs')
    parser.add_argument('--region', action='append', nargs=4, type=float, default=[],
                        metavar=('RA_MIN', 'RA_MAX', 'DEC_MIN', 'DEC_MAX'))
    parser.add_argument('--start', help='First date in UTC, inclusive')
    parser.add_argument('--end', help='Last date in UTC, inclusive')
    parser.add_argument('--fit-start')
    parser.add_argument('--fit-end')
    parser.add_argument('--test-end')
    parser.add_argument('--benchmark', action='store_true', help='Replay the near-west NW034 search')
    parser.add_argument('--no-ai', action='store_true', help='Use fixed evidence order without an OpenAI request')
    parser.add_argument('--planner-model', choices=PLANNER_MODELS, help='OpenAI model for evidence planning')
    parser.add_argument('--find-exposures', action='store_true', help='Look up SPHEREx images near held-out predictions')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        request = SearchRequest(chunks=args.chunk, regions=[dict(zip(Region.model_fields, edges)) for edges in args.region],
                                start=args.start, end=args.end, fit_start=args.fit_start, fit_end=args.fit_end,
                                test_end=args.test_end, benchmark=args.benchmark, use_ai=not args.no_ai,
                                planner_model=args.planner_model, task='search_followup' if args.find_exposures else 'search')
        output = args.output.resolve()
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            parser.error('Choose a new or empty output directory to preserve previous evidence.')
        result = run(request, output, lambda message: print(message, flush=True))
    except (ValidationError, ValueError, FileNotFoundError, RuntimeError) as error:
        parser.exit(1, f'{error}\n')
    print(f"{len(result['candidates'])} ranked linkages · {output / 'evidence.zip'}")


if __name__ == '__main__':
    main()
