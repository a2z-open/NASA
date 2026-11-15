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

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from pipeline.discovery import PLANNER_MODELS, SearchRequest, default_planner_model, run, write_json
from pipeline.spherex import CACHE

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


def perform(run_id: str, folder: Path, request: SearchRequest) -> None:
    global active
    activity = []

    def status(state: str, message: str) -> None:
        activity.append(message)
        write_json(folder / 'status.json', {'id': run_id, 'state': state, 'message': message, 'activity': activity})

    try:
        run(request, folder, lambda message: status('running', message))
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


@router.post('/runs', status_code=202)
def start_search(request: SearchRequest):
    global active
    if not source_ready():
        raise HTTPException(503, 'This server needs an MPC snapshot and the HelioLinC3D tools.')
    with lock:
        if active:
            raise HTTPException(409, 'A search is already running on this server. Try again when it finishes.')
        run_id = uuid4().hex
        folder = RUNS / run_id
        folder.mkdir(parents=True)
        status = {'id': run_id, 'state': 'running', 'message': 'Opening the archive'}
        write_json(folder / 'status.json', status)
        active = run_id
        pool.submit(perform, run_id, folder, request)
    return JSONResponse(status, status_code=202, headers=no_cache)


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
