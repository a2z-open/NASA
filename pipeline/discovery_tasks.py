"""Turn messages about the sky map into the existing validated archive jobs."""

import calendar
from datetime import date
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .discovery import CHUNK_ID, PlannerModel, SearchRequest, SearchTask

CHUNKS = re.compile(r'\b([a-l])\s*[-–‑]\s*(\d{1,2})\b', re.I)
MONTHS = {name.lower(): i for i in range(1, 13) for name in (calendar.month_name[i], calendar.month_abbr[i])}
MONTH_PATTERN = '|'.join(sorted(MONTHS, key=len, reverse=True))
DATES = re.compile(rf'\b(?:(?P<iso>\d{{4}}-\d{{2}}-\d{{2}})|'
                   rf'(?P<month>{MONTH_PATTERN})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?'
                   rf'(?:,?\s+(?P<year>\d{{4}}))?)\b', re.I)
FOLLOWUP = re.compile(r'\b(follow[ -]?up|spherex|images?|exposures?)\b', re.I)
SKIP_FOLLOWUP = re.compile(r"\b(?:no|skip|without|don['’]t|do not)\b[^.;!?]{0,42}\b(?:follow[ -]?up|spherex|images?|exposures?)\b", re.I)
REFERENCE = re.compile(r'\b(same|those|again|rerun|that (?:search|run|job)|(?:previous|last) (?:search|run|job))\b', re.I)
CURRENT_CHUNK = re.compile(r'\b(?:this|current|selected) (?:sky )?chunk\b', re.I)
SEARCH = re.compile(r'\b(search|scan|look|find|check|run|replay|moving objects?|asteroids?)\b', re.I)
RESULT_QUESTION = re.compile(
    r'(?:what did (?:you|(?:the )?(?:last|previous) (?:run|search)) find|'
    r'(?:show(?: me)?|what are) (?:the )?results(?: from (?:that|the last) (?:run|search))?)[.?]?', re.I)
SECRET = re.compile(r'\bsk-(?:proj-|svcacct-)?[\w-]{20,}')


class TaskScope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    chunks: list[str] = Field(default_factory=list, max_length=2)
    start: date | None = None
    end: date | None = None
    benchmark: bool = False
    task: SearchTask = 'search'

    def search_request(self, model: PlannerModel | None) -> SearchRequest:
        return SearchRequest(**self.model_dump(), planner_model=model)


class TaskMessage(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=800)
    draft: TaskScope | None = None
    previous_run: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    map_chunk: str | None = Field(default=None, pattern=r'^[A-L]-(?:0[1-9]|1[0-9]|2[0-4])$')
    planner_model: PlannerModel | None = None

def message_dates(message: str, fallback_year: int | None) -> list[date]:
    matches = list(DATES.finditer(message))
    years = {int(match['iso'][:4] if match['iso'] else match['year'])
             for match in matches if match['iso'] or match['year']}
    default_year = next(iter(years)) if len(years) == 1 else fallback_year if not years else None
    parsed = []
    for match in matches:
        if match['iso']:
            parsed.append(date.fromisoformat(match['iso']))
        else:
            year = int(match['year']) if match['year'] else default_year
            if year is None:
                raise ValueError('Include the year in the dates.')
            parsed.append(date(year, MONTHS[match['month'].lower()], int(match['day'])))
    return parsed


def interpret_task(message: str, *, draft: TaskScope | None = None,
                   previous: TaskScope | None = None, map_chunk: str | None = None) -> tuple[TaskScope, str | None]:
    chunks = list(dict.fromkeys(f'{row.upper()}-{int(column):02d}' for row, column in CHUNKS.findall(message)))
    followup = bool(FOLLOWUP.search(message))
    replay = bool(re.search(r'\bNW034\b', message, re.I))
    referring = bool(REFERENCE.search(message) or (followup and not chunks and not DATES.search(message)))
    scope = (draft or (previous if referring else None) or TaskScope()).model_copy(deep=True)
    if followup:
        scope.task = 'search' if SKIP_FOLLOWUP.search(message) else 'search_followup'

    if not (chunks or replay or followup or referring or SEARCH.search(message) or DATES.search(message) or CURRENT_CHUNK.search(message)):
        return scope, 'I can search for moving objects, find follow-up images, or replay NW034. What should I run?'
    if len(chunks) > 2 or any(not CHUNK_ID.fullmatch(chunk) for chunk in chunks):
        return scope, 'Give me one or two chunk IDs from A-01 through L-24.'
    if replay:
        if chunks or DATES.search(message):
            return scope, 'NW034 uses its historical region and dates. Ask for the replay by name, or give a chunk and date range for a separate search.'
        return TaskScope(benchmark=True, task=scope.task), None
    if CURRENT_CHUNK.search(message) and not chunks:
        if map_chunk is None:
            return scope, 'Zoom in to a chunk or include a chunk ID in the message, such as H-02.'
        chunks = [map_chunk]
    if chunks:
        scope.chunks = chunks
        scope.benchmark = False
    try:
        dates = message_dates(message, scope.start.year if scope.start else None)
    except ValueError:
        return scope, 'Give me valid start and end dates with a year, such as 2026-10-20 to 2026-11-13.'
    if len(dates) > 2:
        return scope, 'Which two dates should I use for the search?'
    if dates:
        scope.benchmark = False
        if len(dates) == 2:
            scope.start, scope.end = dates
        elif scope.start and not scope.end:
            scope.end = dates[0]
        else:
            scope.start, scope.end = dates[0], None
    if scope.benchmark:
        return scope, None
    if not scope.chunks:
        return scope, 'Which one or two chunks should I search? For example, H-02 and H-03.'
    if not scope.start or not scope.end:
        return scope, 'What dates should I search? Give me the UTC start and end, for example 2026-10-20 to 2026-11-13.'
    try:
        scope.search_request(None)
    except ValidationError as error:
        return scope, error.errors()[0]['msg'].removeprefix('Value error, ')
    return scope, None


def assigned_reply(scope: TaskScope, reused: bool) -> str:
    area = 'the NW034 replay' if scope.benchmark else (
        f"{' and '.join(scope.chunks)} from {scope.start.isoformat()} to {scope.end.isoformat()} UTC")
    if reused:
        return f'Checking SPHEREx for the saved predictions from {area}.'
    if scope.task == 'search_followup':
        return f'Started {area} with a search for moving objects and SPHEREx follow-up.'
    return f'Started a search for moving objects in {area}.'


def result_reply(packet: dict | None) -> str:
    if packet is None:
        return 'Send a search task first. I’ll show the result here when it finishes.'
    count = len(packet['candidates'])
    reply = f'The last job returned {count} ranked asteroid {"linkage" if count == 1 else "linkages"}.'
    result = packet.get('followup')
    if result:
        if result['status'] == 'found':
            reply += ' SPHEREx returned possible exposures for pixel review.'
        elif result['status'] == 'no_results':
            reply += ' The checked SPHEREx releases returned no matching exposure metadata.'
        elif result['status'] == 'incomplete':
            reply += ' Some SPHEREx archive queries could not be completed.'
        else:
            reply += ' The search produced no saved prediction to check in SPHEREx.'
    return reply + ' The work log and evidence packet are below.'
