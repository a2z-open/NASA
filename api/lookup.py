"""Web service for the local PARALLAX viewer and coordinate lookup."""

from contextlib import asynccontextmanager
import json
from pathlib import Path
import re

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pipeline.archive import IrsaArchive, SkyPosition, build_sequence, near_barnard, sequence_payload


ROOT = Path(__file__).resolve().parents[1]
RESERVATION = ROOT / 'validation/barnards-star-archive.json'


def active_reservation():
    try:
        reserve = json.loads(RESERVATION.read_text())['reserve']
        if not reserve['obs_ids'] or not reserve['t_min'] < reserve['t_max']:
            return None
        return reserve
    except (OSError, ValueError, KeyError, TypeError):
        return None


def create_app(*, cache=None, archive=None):
    cache = cache if cache is not None else ROOT / '.parallax-cache/sequences'
    cache.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app):
        app.state.archive = archive if archive is not None else IrsaArchive()
        try:
            yield
        finally:
            if archive is None:
                app.state.archive.close()

    app = FastAPI(title='PARALLAX', lifespan=lifespan)

    @app.get('/api/sequence')
    def sequence(request: Request, ra: str | None = None, dec: str | None = None):
        try:
            position = SkyPosition.parse(ra, dec)
        except ValueError as error:
            return JSONResponse(status_code=400, content={'message': str(error)})
        reservation = active_reservation()
        if reservation is None and near_barnard(position):
            return sequence_payload(position, [], 'archive_unavailable') | {
                'message': 'Barnard’s reserve protection is pending. Open the saved case to view early visits.',
            }
        return build_sequence(request.app.state.archive, position, cache, reservation=reservation or {})

    # Serve only the current sequence cache layout.
    @app.get('/frames/{sequence_id}/{frame_name}')
    def frame(sequence_id: str, frame_name: str):
        if re.fullmatch(r'v2-\d{1,3}\.\d{8}_-?\d{1,2}\.\d{8}', sequence_id) and re.fullmatch(
            r'[\w-]+\.png', frame_name, flags=re.ASCII
        ):
            path = cache / sequence_id / frame_name
            if path.is_file():
                return FileResponse(path, media_type='image/png')
        return JSONResponse(status_code=404, content={'message': 'Display frame was not found.'})
    dist = ROOT / 'web/dist'
    if dist.is_dir():
        app.mount('/', StaticFiles(directory=dist, html=True), name='viewer')
    else:
        app.mount('/data', StaticFiles(directory=ROOT / 'web/public/data'), name='cases')
    return app


app = create_app()
