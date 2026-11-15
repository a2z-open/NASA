"""Background archive searches and evidence on the sky map."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
from pathlib import Path
import re
from threading import Lock
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from pipeline.discovery import PLANNER_MODELS, SearchRequest, default_planner_model, run, write_json
from pipeline.aiges_chat import answer
from pipeline.discovery_tasks import (
    RESULT_QUESTION, SECRET, TaskMessage, TaskScope, archive_intent, assigned_reply, interpret_task,
    requested_workflow, result_reply,
)
from pipeline.research_archive import OpticalSurvey, optical_reply, survey
from pipeline.spherex import CACHE, ROOT

router = APIRouter(prefix='/api/discovery')
RUNS = CACHE / 'discovery' / 'runs'
RUN_ID = re.compile(r'[a-f0-9]{32}')
pool = ThreadPoolExecutor(max_workers=1)
lock = Lock()
active: str | None = None
no_cache = {'Cache-Control': 'private, no-store'}
logger = logging.getLogger(__name__)


def source_ready() -> bool:
    from pipeline.discovery_engine import source_ready as available

    return available()


@router.get('/settings')
def settings():
    return JSONResponse({'archive_ready': source_ready(),
                         'planner_ready': bool(os.getenv('OPENAI_API_KEY', '').strip()),
                         'planner_default_model': default_planner_model(),
                         'planner_models': PLANNER_MODELS}, headers=no_cache)


def perform(run_id: str, folder: Path, request: SearchRequest | OpticalSurvey, reuse: Path | None = None) -> None:
    global active
    activity = []

    def status(state: str, message: str) -> None:
        activity.append(message)
        write_json(folder / 'status.json', {'id': run_id, 'state': state, 'message': message, 'activity': activity})

    try:
        def progress(message: str) -> None:
            status('running', message)

        if isinstance(request, OpticalSurvey):
            packet = survey(request, progress)
            write_json(folder / 'evidence.json', packet)
            with ZipFile(folder / 'evidence.zip', 'w', compression=ZIP_DEFLATED) as archive:
                archive.write(folder / 'evidence.json', 'evidence.json')
        else:
            run(request, folder, progress, reuse=reuse)
        status('complete', 'Evidence ready')
    except Exception as error:
        logger.exception('Discovery run %s failed', run_id)
        message = 'Search failed. Retry the run or ask the server operator to check the archive tools.'
        if isinstance(error, ValueError) and str(error).startswith('No archive dates'):
            message = str(error)
        status('error', message)
    finally:
        with lock:
            active = None


def queue_search(request: SearchRequest | OpticalSurvey, reuse: Path | None = None) -> dict:
    global active
    if isinstance(request, SearchRequest) and reuse is None and not source_ready():
        raise HTTPException(503, 'This server needs an MPC snapshot and the HelioLinC3D tools.')
    with lock:
        if active:
            raise HTTPException(409, 'A search is already running on this server. Try again when it finishes.')
        run_id = uuid4().hex
        folder = RUNS / run_id
        folder.mkdir(parents=True)
        status = {'id': run_id, 'state': 'running', 'message': (
            'Connecting to NSF NOIRLab' if isinstance(request, OpticalSurvey)
            else 'Loading saved predictions' if reuse else 'Opening the MPC archive')}
        write_json(folder / 'status.json', status)
        active = run_id
        pool.submit(perform, run_id, folder, request, reuse)
    return status


@router.post('/runs', status_code=202)
def start_search(request: SearchRequest):
    return JSONResponse(queue_search(request), status_code=202, headers=no_cache)


@router.post('/tasks')
def assign_task(task: TaskMessage):
    if any(SECRET.search(text) for text in (task.message, task.space_topic or '', *(turn.text for turn in task.history))):
        raise HTTPException(400, 'Remove the API key from your message. Configure it on the server.')
    previous = None
    packet = None
    prior = RUNS / task.previous_run if task.previous_run else None
    if prior and (prior / 'evidence.json').is_file():
        packet = json.loads((prior / 'evidence.json').read_text())
        previous_request = packet['request']
        values = {key: previous_request[key] for key in TaskScope.model_fields if key in previous_request}
        if packet.get('kind') == 'optical':
            values['workflow'] = 'optical'
        if values.get('benchmark'):
            values.pop('start', None)
            values.pop('end', None)
        previous = TaskScope.model_validate(values)
    draft = task.draft.model_dump(mode='json') if task.draft else None
    if RESULT_QUESTION.fullmatch(task.message):
        reply = optical_reply(packet) if packet and packet.get('kind') == 'optical' else result_reply(packet)
        if packet is None and prior and (prior / 'status.json').is_file():
            status = json.loads((prior / 'status.json').read_text())
            if active == task.previous_run and status.get('state') == 'running':
                reply = f"The search is still running. {status['message']}."
            elif status.get('state') == 'error':
                reply = status['message']
            else:
                reply = 'There is no completed evidence packet for that run. Open its work log for details.'
        return JSONResponse({'reply': reply, 'draft': draft}, headers=no_cache)
    if not archive_intent(task.message, task.draft, previous):
        p9_report = None
        try:
            p9_report = json.loads((ROOT / 'validation' / 'planet_nine.json').read_text())
        except (OSError, ValueError):
            pass
        return JSONResponse({'draft': draft, **answer(task.message, task.space_topic,
                                                      [turn.model_dump() for turn in task.history], p9_report)},
                            headers=no_cache)
    workflow = requested_workflow(task.message, task.draft, previous)
    scope, question = interpret_task(task.message, draft=task.draft, previous=previous,
                                     map_chunk=task.map_chunk, workflow=workflow)
    if question:
        draft = scope.model_dump(mode='json') if scope != TaskScope() else None
        return JSONResponse({'reply': question, 'draft': draft}, headers=no_cache)
    try:
        if scope.workflow == 'optical':
            if previous == scope.model_copy(update={'task': 'search'}) and scope.task == 'search_followup':
                return JSONResponse({'reply': 'That DECam survey found image records. A measured orbit is needed before I can look for exposures at its predicted position.'}, headers=no_cache)
            status = queue_search(scope.optical_request())
            reply = (f"I’m checking NSF NOIRLab for deep DECam exposures in {' and '.join(scope.chunks)} "
                     f"from {scope.start} to {scope.end} UTC. I’ll rank fields by repeat nights and reported depth.")
        else:
            same_scope = previous and scope.model_dump(exclude={'task'}) == previous.model_dump(exclude={'task'})
            reuse = prior if same_scope and scope.task == 'search_followup' else None
            status = queue_search(scope.search_request(task.planner_model), reuse)
            reply = assigned_reply(scope, reuse is not None)
    except HTTPException as error:
        if error.status_code not in {409, 503}:
            raise
        reply = (str(error.detail) if error.status_code == 409
                 else 'This preview can check DECam coverage, but the MPC linkage worker needs its archive and orbit tools configured before it can run. I can still explain the NW034 evidence.')
        return JSONResponse({'reply': reply, 'draft': scope.model_dump(mode='json')}, headers=no_cache)
    return JSONResponse({'reply': reply, 'run': status}, status_code=202, headers=no_cache)


def run_folder(run_id: str) -> Path:
    if not RUN_ID.fullmatch(run_id) or not (RUNS / run_id / 'status.json').is_file():
        raise HTTPException(404, 'Search run not found.')
    return RUNS / run_id


@router.get('/runs/{run_id}')
def search_status(run_id: str):
    folder = run_folder(run_id)
    with lock:
        status = json.loads((folder / 'status.json').read_text())
        if status['state'] == 'running' and active != run_id:
            status.update({'state': 'error', 'message': 'The server restarted during this search. Start a new run.'})
    if status['state'] == 'complete':
        status['evidence'] = json.loads((folder / 'evidence.json').read_text())
    return JSONResponse(status, headers=no_cache)


@router.get('/runs/{run_id}/files/{name:path}')
def search_file(run_id: str, name: str):
    folder = run_folder(run_id)
    path = (folder / name).resolve()
    if folder.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, 'Evidence file not found.')
    if name in {'evidence.json', 'evidence.zip'}:
        return FileResponse(path, filename=f'parallax-{name}', headers=no_cache)
    if path.suffix not in {'.gif', '.png', '.webp'}:
        raise HTTPException(404, 'Evidence file not found.')
    return FileResponse(path, headers=no_cache)
