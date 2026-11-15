"""PARALLAX web API (see docs/API.md).

Run:  .venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from base64 import b64encode
import csv
from datetime import datetime, timezone
import hashlib
from hmac import compare_digest
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import traceback
import uuid
import xml.etree.ElementTree as ET

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import requests

from api.chunks import router as chunks_router
from api.discovery import router as discovery_router
from pipeline import ephem
from pipeline.archive import SkyPosition, is_reserved, load_reservation, near_barnard, reserved_observation, write_json
from pipeline.astrometry import CoordinateError, mjd_to_iso, parse_dec, parse_position, parse_ra, propagate, to_tangent
from pipeline.spherex import CACHE, RELEASES, ROOT, ArchiveUnavailable, fetch_cutout, field_key, group_visits, search
from pipeline.targets import ORDER, TARGETS

VERSION = '1.0.0'
DATA = ROOT / 'data' / 'targets'
FIELDS = CACHE / 'fields'
INVESTIGATIONS = CACHE / 'investigations'
EXPERIMENTS = ROOT / 'validation' / 'experiments'
RESERVATION = ROOT / 'validation' / 'barnards-star-archive.json'
FIELDS.mkdir(parents=True, exist_ok=True)
INVESTIGATIONS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title='PARALLAX', version=VERSION)
app.add_middleware(GZipMiddleware, minimum_size=2000)
app.include_router(chunks_router)
app.include_router(discovery_router)


@app.middleware('http')
async def team_access(request: Request, call_next):
    password = os.getenv('PARALLAX_TEAM_PASSWORD')
    if not password:
        return await call_next(request)
    expected = b'Basic ' + b64encode(f'team:{password}'.encode())
    if not compare_digest(request.headers.get('Authorization', '').encode(), expected):
        return Response(status_code=401, headers={'WWW-Authenticate': 'Basic realm="PARALLAX team"', 'Cache-Control': 'no-store'})
    response = await call_next(request)
    response.headers.setdefault('Cache-Control', 'private')
    return response

_jobs: dict[str, dict] = {}
_jobs_lock = threading.RLock()
_pool = ThreadPoolExecutor(max_workers=3)
_catalog_pool = ThreadPoolExecutor(max_workers=3)
_json_cache: dict[str, tuple[float, object]] = {}


def read_json(path: Path):
    key = str(path)
    mtime = path.stat().st_mtime
    hit = _json_cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    obj = json.loads(path.read_text())
    _json_cache[key] = (mtime, obj)
    return obj


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def job_update(job_id, **kw):
    with _jobs_lock:
        _jobs[job_id].update(kw)


def new_job(kind, result_id):
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {'job_id': job_id, 'kind': kind, 'status': 'queued', 'progress': {'stage': 'queued', 'done': 0, 'total': 0},
                         'result_id': result_id, 'message': None, 'created_utc': now()}
    return job_id


# ---------------------------------------------------------------------------
# Health, targets, resolve
# ---------------------------------------------------------------------------

@app.get('/api/health')
def health():
    n_targets = sum(1 for s in ORDER if (DATA / s / 'field.json').exists())
    return {'ok': True, 'version': VERSION, 'cache': {'targets': n_targets, 'fields': sum(1 for _ in FIELDS.glob('*/field.json'))},
            'services': {'irsa': 'unknown', 'gaia': 'unknown'}, 'time_utc': now()}


@app.get('/api/targets')
def targets():
    out = []
    for slug in ORDER:
        t = TARGETS[slug]
        fpath, ipath = DATA / slug / 'field.json', DATA / slug / 'investigation.json'
        field = read_json(fpath) if fpath.exists() else None
        inv = read_json(ipath) if ipath.exists() else None
        out.append({
            'slug': slug, 'title': t.title, 'kind': t.kind, 'purpose': t.purpose, 'notes': list(t.notes),
            'astrometry': t.astrometry.__dict__,
            'field': {'field_id': slug, 'ra': field['ra'], 'dec': field['dec'], 'fov_arcmin': field['fov_arcmin']} if field else None,
            'status': 'cached' if field else 'missing',
            'n_observations': len(field['frames']) if field else 0,
            'n_visits': len(field['archive']['visits']) if field else 0,
            'date_range': [field['frames'][0]['time_utc'], field['frames'][-1]['time_utc']] if field and field['frames'] else None,
            'headline': ({'verdict': (inv['summary']['verdicts'][0]['code'] if inv['summary']['verdicts'] else 'none'),
                          'label': inv['summary']['headline'], 'detail': inv['summary']['one_liner']} if inv else None),
            'investigation_id': slug if inv else None,
        })
    return out


ALIASES = {
    'barnard': 'barnards-star', "barnard's star": 'barnards-star', 'barnards star': 'barnards-star', 'gj 699': 'barnards-star',
    'epsilon indi b': 'epsilon-indi-b', 'eps ind b': 'epsilon-indi-b', 'epsilon indi ba': 'epsilon-indi-b', 'eps indi b': 'epsilon-indi-b',
    'wise 0855': 'wise-0855', 'wise 0855-0714': 'wise-0855', 'wise j085510.83-071442.5': 'wise-0855', 'wise0855': 'wise-0855',
    'rw aur': 'rw-aurigae', 'rw aurigae': 'rw-aurigae', 'r dra': 'r-draconis', 'r draconis': 'r-draconis',
}


@app.get('/api/resolve')
def resolve(q: str):
    q = (q or '').strip()
    if not q or len(q) > 120:
        raise HTTPException(400, 'Enter a name or coordinates.')
    try:
        ra, dec = parse_position(q)
        return {'name': None, 'ra': ra, 'dec': dec, 'source': 'coordinates', 'epoch_note': 'as entered (ICRS)'}
    except CoordinateError as error:
        if re.match(r'^[+−-]?\d', q) and re.fullmatch(r'''[\d\s.,:+−hdms°'"′″-]+''', q, re.IGNORECASE) and re.search(r'[\s,]', q):
            raise HTTPException(400, str(error)) from error
    key = re.sub(r'\s+', ' ', q.lower().replace('’', "'"))
    if key in ('earth', 'the earth'):
        raise HTTPException(400, 'This sky map looks outward from Earth, so Earth itself has no position on it.')
    epoch = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    epoch_mjd = epoch.timestamp() / 86400 + 40587
    catalogue_epoch = f'Catalogue position propagated to {epoch:%Y-%m-%d} UTC (proper motion and parallax)'
    if key in ALIASES:
        t = TARGETS[ALIASES[key]]
        p = propagate(t.astrometry.ra_deg, t.astrometry.dec_deg,
                      t.astrometry.epoch_mjd or (51544.5 + (t.astrometry.epoch_jyear - 2000.0) * 365.25),
                      t.astrometry.pmra_masyr, t.astrometry.pmdec_masyr, t.astrometry.parallax_mas, [epoch_mjd])
        return {'name': t.title, 'ra': float(p.ra[0]), 'dec': float(p.dec[0]), 'source': t.astrometry.source,
                'epoch_note': catalogue_epoch, 'target': t.slug,
                'pmra_masyr': t.astrometry.pmra_masyr, 'pmdec_masyr': t.astrometry.pmdec_masyr, 'parallax_mas': t.astrometry.parallax_mas}
    # Planets, the Sun, the Moon, dwarf planets and asteroids move, so star catalogues do not list them: ask JPL Horizons.
    if key in ephem.SOLAR:
        command, title, kind = ephem.SOLAR[key]
        try:
            w = ephem.where_now(command)
        except Exception as error:  # noqa: BLE001
            raise HTTPException(503, f'Could not reach NASA JPL Horizons to find {title} ({type(error).__name__}). Try again.')
        return {'name': title, 'ra': w['ra'], 'dec': w['dec'], 'source': 'JPL Horizons', 'kind': kind, 'moves': True,
                'distance_au': w['delta_au'], 'body_id': command, 'position_utc': w['position_utc'],
                'epoch_note': 'Earth-centered astrometric position (ICRF)'}
    try:
        r = requests.get('https://vizier.cfa.harvard.edu/viz-bin/nph-sesame/-oxp/SNV?' + requests.utils.quote(q), timeout=15,
                         headers={'User-Agent': 'PARALLAX/1.0 (research prototype)'})
        root = ET.fromstring(r.content)
        res = root.find('.//Resolver')
        if res is None or res.find('jradeg') is None:
            # Not a star or galaxy: it may be a numbered or named asteroid or comet-free small body.
            if re.fullmatch(r"[A-Za-z0-9' \-]{2,40}", q):
                try:
                    w = ephem.where_now(f'{q};')
                    return {'name': w['target'], 'ra': w['ra'], 'dec': w['dec'], 'source': 'JPL Horizons', 'kind': 'small body',
                            'moves': True, 'distance_au': w['delta_au'], 'position_utc': w['position_utc'],
                            'epoch_note': 'Earth-centered astrometric position (ICRF)'}
                except Exception:  # noqa: BLE001
                    pass
            raise HTTPException(404, f'Couldn\'t find "{q}". Try a star like Vega, a planet like Mars, or coordinates.')
        ra, dec = parse_ra(float(res.findtext('jradeg'))), parse_dec(float(res.findtext('jdedeg')))
        pmra = res.findtext('pm/pmRA')
        pmdec = res.findtext('pm/pmDE')
        plx = res.findtext('plx/v')
        resolver = res.get('name', 'Sesame')
        source = 'SIMBAD (CDS)' if 'simbad' in resolver.lower() else resolver
        out = {'name': q, 'ra': ra, 'dec': dec, 'source': source, 'epoch_note': 'Catalogue position at J2000',
               'otype': res.findtext('otype')}
        if pmra and pmdec:
            pmra, pmdec = float(pmra), float(pmdec)
            p = propagate(ra, dec, 51544.5, pmra, pmdec, float(plx) if plx else 0.0, [epoch_mjd])
            out.update({'ra': float(p.ra[0]), 'dec': float(p.dec[0]), 'pmra_masyr': pmra, 'pmdec_masyr': pmdec,
                        'parallax_mas': float(plx) if plx else None,
                        'epoch_note': catalogue_epoch})
        return out
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001
        raise HTTPException(503, f'Name resolver unavailable ({type(error).__name__}). Enter coordinates instead.')


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------

def field_path(field_id: str) -> Path:
    if field_id in TARGETS:
        return DATA / field_id / 'field.json'
    if not re.fullmatch(r'f[\w.]+', field_id):
        raise HTTPException(404, 'Unknown field.')
    return FIELDS / field_id / 'field.json'


def raw_dir(field_id: str) -> Path:
    return CACHE / 'targets' / field_id / 'raw' if field_id in TARGETS else FIELDS / field_id / 'raw'


def _unsafe_live_cache(field):
    if not field.get('frames'):
        return False
    pos = SkyPosition(field['ra'], field['dec'])
    reservation = load_reservation(RESERVATION)
    if reservation is None:
        return near_barnard(pos)
    return any(reserved_observation(f['obs_id'], f['mjd'], pos, reservation) for f in field['frames'])


async def _json_body(request: Request) -> dict:
    """The request body as a JSON object, or a 400 (never a 500) when it is missing or malformed."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(400, 'The request body must be JSON.')
    if not isinstance(body, dict):
        raise HTTPException(400, 'The request body must be a JSON object.')
    return body


def _number(value, default: float, what: str) -> float:
    if value is None or value == '':
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f'{what} must be a number.')
    if not math.isfinite(v):
        raise HTTPException(400, f'{what} must be a number.')
    return v


@app.post('/api/fields')
async def create_field(request: Request):
    body = await _json_body(request)
    try:
        ra, dec = parse_ra(body.get('ra')), parse_dec(body.get('dec'))
    except CoordinateError as error:
        raise HTTPException(400, str(error))
    fov = _number(body.get('fov_arcmin'), 6.0, 'Field of view')
    if not 2.0 <= fov <= 30.0:
        raise HTTPException(400, 'Field of view must be between 2 and 30 arcmin.')
    max_frames = int(min(max(int(_number(body.get('max_frames'), 24, 'max_frames')), 4), 48))
    wmin = body.get('wavelength_min_um')
    wmax = body.get('wavelength_max_um')
    # Curated target nearby? Re-use its cache.
    for slug in ORDER:
        p = DATA / slug / 'field.json'
        if p.exists():
            f = read_json(p)
            xi, eta = to_tangent(ra, dec, f['ra'], f['dec'])
            if math.hypot(float(xi), float(eta)) < 30 and abs(fov - f['fov_arcmin']) < 0.5:
                return {'field_id': slug, 'status': 'ready', 'job_id': None}
    fid = field_key(ra, dec, fov) + (f'_w{float(wmin):.2f}-{float(wmax):.2f}' if wmin and wmax else '') + f'_n{max_frames}'
    fp = FIELDS / fid / 'field.json'
    with _jobs_lock:
        running = next((j for j in _jobs.values() if j['result_id'] == fid and j['status'] in ('queued', 'running')), None)
        if running:
            return {'field_id': fid, 'status': 'processing', 'job_id': running['job_id']}
        if fp.exists():
            doc = read_json(fp)
            # Interrupted, unavailable, or partial-release documents may be retried.
            if (doc['data_state'] not in ('archive_unavailable', 'failed', 'processing')
                    and not (doc.get('archive') or {}).get('unavailable_collections') and not _unsafe_live_cache(doc)):
                return {'field_id': fid, 'status': 'ready', 'job_id': None}
        from pipeline.frames import grid_doc
        # Publish the pending document before returning the job, including retries of cached failures.
        write_json(fp, {'field_id': fid, 'kind': 'live', 'data_state': 'processing', 'frames': [], 'message': None,
                        'ra': ra, 'dec': dec, 'fov_arcmin': fov, 'grid': grid_doc(ra, dec, fov), 'catalog': [],
                        'catalog_epoch_mjd': 57388.5, 'archive': None, 'stacks': [], 'title': None})
        job = new_job('field', fid)
    _pool.submit(_field_job, job, fid, ra, dec, fov, max_frames, wmin, wmax)
    return {'field_id': fid, 'status': 'processing', 'job_id': job}


def choose_products(products, max_frames, wmin=None, wmax=None):
    if wmin is not None and wmax is not None:
        products = [p for p in products if p.em_max_um is None or (p.em_max_um >= float(wmin) and p.em_min_um <= float(wmax))]
    visits = group_visits(products)
    if not visits:
        return [], visits
    per_visit = max(1, max_frames // len(visits))
    chosen = []
    for v in visits:
        by_det = {}
        for p in v:
            by_det.setdefault(p.detector, []).append(p)
        dets = sorted(by_det)
        i = 0
        picked = []
        while len(picked) < per_visit and any(by_det.values()):
            d = dets[i % len(dets)]
            if by_det[d]:
                lst = by_det[d]
                picked.append(lst.pop(len(lst) // 2))
            i += 1
            if i > 10000:
                break
        chosen += picked
    return sorted(chosen, key=lambda p: p.t_min)[:max_frames], visits


def _field_job(job_id, fid, ra, dec, fov, max_frames, wmin, wmax):
    from pipeline.frames import grid_doc, make_frame
    from pipeline.measure import gaia_field
    folder = FIELDS / fid
    folder.mkdir(parents=True, exist_ok=True)
    base = {'field_id': fid, 'kind': 'live', 'title': None, 'ra': ra, 'dec': dec, 'fov_arcmin': fov, 'progress': None,
            'grid': grid_doc(ra, dec, fov), 'archive': None, 'frames': [], 'catalog': [], 'catalog_epoch_mjd': 57388.5,
            'stacks': [], 'investigation_id': None}

    def save(doc):
        write_json(folder / 'field.json', doc)

    try:
        job_update(job_id, status='running', progress={'stage': 'Searching NASA/IPAC IRSA for DR1 and QR3 observations', 'done': 0, 'total': 0})
        save(base | {'data_state': 'processing', 'message': None})
        pos = SkyPosition(ra, dec)
        reservation = load_reservation(RESERVATION)
        if reservation is None and near_barnard(pos):
            save(base | {'data_state': 'archive_unavailable', 'message': 'The reserved Barnard’s Star visit could not be checked. Open the saved case to view earlier observations.'})
            job_update(job_id, status='done', message='archive_unavailable')
            return
        unavailable = []
        try:
            products = search(ra, dec, on_unavailable=unavailable.append)
        except ArchiveUnavailable as error:
            save(base | {'data_state': 'archive_unavailable', 'message': f'IRSA did not respond: {error}'})
            job_update(job_id, status='done', message='archive_unavailable')
            return
        if not products:
            state = 'archive_unavailable' if unavailable else 'no_coverage'
            message = ('IRSA returned no images from the release that responded. Coverage is unknown for the unavailable release.'
                       if unavailable else 'IRSA returned no SPHEREx DR1/QR3 spectral images covering this position.')
            save(base | {'data_state': state, 'message': message})
            job_update(job_id, status='done', message=state)
            return
        eligible = [p for p in products if not is_reserved(p, pos, reservation or {})]
        chosen, visits = choose_products(eligible, max_frames, wmin, wmax)
        vis_doc = [{'id': f'visit-{i + 1}', 'start_utc': mjd_to_iso(v[0].t_min), 'end_utc': mjd_to_iso(v[-1].t_max),
                    'mjd_start': v[0].t_min, 'mjd_end': v[-1].t_max, 'n_products': len(v),
                    'releases': sorted({p.release for p in v}), 'per_detector': {f'D{d}': sum(1 for p in v if p.detector == d) for d in range(1, 7)},
                    'sealed': False} for i, v in enumerate(visits)]
        vmap = {p.id: f'visit-{i + 1}' for i, v in enumerate(visits) for p in v}
        archive = {'n_products': len(products), 'collections': sorted({p.collection for p in products}),
                   'unavailable_collections': unavailable, 'queried_utc': now(), 'visits': vis_doc}
        if not chosen:
            save(base | {'data_state': 'no_coverage', 'archive': archive, 'message': 'The responding releases have no eligible SPHEREx exposures for this field and wavelength range.'})
            job_update(job_id, status='done', message='no_coverage')
            return

        total = len(chosen)
        processing = base | {'data_state': 'processing', 'message': None, 'archive': archive}
        save(processing)
        job_update(job_id, progress={'stage': 'Downloading and aligning SPHEREx cutouts', 'done': 0, 'total': total})

        def extract(product):
            try:
                prov = fetch_cutout(product, ra, dec, fov, folder / 'raw')
            except Exception:  # A failed cutout leaves other products eligible.
                return None, None
            path = folder / 'raw' / f'{prov.product_id}.fits'
            try:
                frame = make_frame((str(path), ra, dec, fov, folder / 'frames', base['grid']['dtype'], vmap[product.id]),
                                   versioned=True)
            except Exception as error:  # Astrometry and FITS failures are reported per exposure.
                frame = {'error': str(error)[:200]}
            return prov.product_id, frame

        catalogue = _catalog_pool.submit(gaia_field, ra, dec, fov / 60 * 0.75, gmax=19.0, cache=folder / 'gaia_field.json')
        frames, native_ids = [], []
        failures, errors = 0, 0
        with ThreadPoolExecutor(max_workers=6) as executor:
            work = [executor.submit(extract, p) for p in chosen]
            for completed, future in enumerate(as_completed(work), start=1):
                product_id, frame = future.result()
                if product_id is None:
                    failures += 1
                else:
                    native_ids.append(product_id)
                    if 'error' in frame:
                        errors += 1
                    else:
                        frame['data_url'] = f"/files/fields/{fid}/frames/{frame.pop('file')}"
                        frames.append(frame)
                        frames.sort(key=lambda f: (f['mjd'], f['id']))
                        save(processing | {'frames': frames})
                job_update(job_id, progress={'stage': 'Downloading and aligning SPHEREx cutouts', 'done': completed, 'total': total})

        if not native_ids:
            catalogue.cancel()
            save(base | {'data_state': 'archive_unavailable', 'archive': archive,
                         'message': f'All {total} cutout downloads failed; IRSA may be busy. Try again shortly.'})
            job_update(job_id, status='done', message='archive_unavailable')
            return
        if not frames:
            catalogue.cancel()
            save(base | {'data_state': 'insufficient', 'archive': archive, 'frame_errors': errors,
                         'message': 'The archive returned cutouts, but none could be aligned with enough coverage of this field.'})
            job_update(job_id, status='done', message='insufficient')
            return

        n_vis = len({f['visit'] for f in frames})
        state = 'live' if n_vis >= 2 else 'insufficient'
        msg = None if n_vis >= 2 else 'Only one SPHEREx visit covers this position so far; a time comparison needs at least two.'
        if unavailable:
            releases = ', '.join(RELEASES[c]['release'] for c in unavailable)
            msg = (msg + ' ' if msg else '') + f'IRSA {releases} did not respond. Showing observations from the available release.'
        if failures or errors:
            msg = (msg + ' ' if msg else '') + f'{failures + errors} of {total} cutouts could not be downloaded or aligned.'
        ready = base | {'data_state': state, 'message': msg, 'archive': archive, 'frames': frames,
                        'frame_errors': errors, 'native_product_ids': native_ids}

        def finish_catalog(result):
            try:
                stars = [s for s in result.result() if s.get('ra') is not None]
            except Exception:
                save(ready | {'catalog_status': 'unavailable'})
            else:
                save(ready | {'catalog': stars, 'catalog_status': 'ready'})
            finally:
                job_update(job_id, status='done', progress={'stage': 'done', 'done': len(frames), 'total': len(frames)})

        save(ready | {'catalog_status': 'loading'})
        job_update(job_id, progress={'stage': 'Loading Gaia DR3 overlay', 'done': 0, 'total': 0})
        catalogue.add_done_callback(finish_catalog)
    except Exception as error:  # noqa: BLE001
        traceback.print_exc()
        save(base | {'data_state': 'failed', 'message': f'Processing failed: {type(error).__name__}: {error}'})
        job_update(job_id, status='failed', message=str(error)[:300])


@app.get('/api/fields/{field_id}')
def get_field(field_id: str):
    p = field_path(field_id)
    if not p.exists():
        raise HTTPException(404, 'Unknown field.')
    doc = dict(read_json(p))
    if field_id not in TARGETS and _unsafe_live_cache(doc):
        return doc | {'data_state': 'failed', 'frames': [], 'archive': None, 'progress': None,
                      'message': 'This cached field predates the reserve check. Search these coordinates again to refresh it.'}
    if doc.get('data_state') == 'processing' or doc.get('catalog_status') == 'loading':
        with _jobs_lock:
            j = next((j for j in _jobs.values() if j['result_id'] == field_id and j['status'] in ('queued', 'running')), None)
        if doc['data_state'] != 'processing':
            if not j:
                doc = read_json(p).copy()
                if doc.get('catalog_status') == 'loading':
                    doc['catalog_status'] = 'unavailable'
        elif j:
            doc['progress'] = j['progress']
        else:
            doc['data_state'] = 'failed'
            doc['message'] = 'Processing was interrupted (the server restarted). Search this position again to retry.'
    return doc


@app.get('/api/fields/{field_id}/wise')
def field_wise(field_id: str):
    """CatWISE2020 sources in a field (WISE + NEOWISE, positions near 2015), for the viewer overlay."""
    p = field_path(field_id)
    if not p.exists():
        raise HTTPException(404, 'Unknown field.')
    cache = CACHE / 'wise' / f'{field_id}.json'
    if cache.is_file():
        return read_json(cache)
    f = read_json(p)
    rad = min(max(float(f.get('fov_arcmin') or 6.0), 2.0) / 60 * 0.75, 0.25)
    q = ('SELECT TOP 800 source_name, ra, dec, w1mpro, w2mpro, pmra, pmdec, sigpmra, sigpmdec FROM catwise_2020 '
         f"WHERE CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{float(f['ra']):.6f},{float(f['dec']):.6f},{rad:.5f}))=1 AND w2mpro < 16.5")
    try:
        r = requests.get('https://irsa.ipac.caltech.edu/TAP/sync', params={'FORMAT': 'csv', 'QUERY': q}, timeout=60)
        r.raise_for_status()
    except requests.RequestException:
        raise HTTPException(503, 'The WISE catalogue (IRSA) could not be reached. Try again in a moment.')
    out = []
    for row in csv.DictReader(io.StringIO(r.text)):
        def num(k):
            try:
                v = float(row[k])
                return v if math.isfinite(v) else None
            except (TypeError, ValueError):
                return None
        pa, pd_, sa, sd = num('pmra') or 0.0, num('pmdec') or 0.0, num('sigpmra') or 9.0, num('sigpmdec') or 9.0
        pmv = math.hypot(pa, pd_)
        sig = math.hypot(pa * sa, pd_ * sd) / pmv if pmv > 0 else 9.0
        out.append({'name': row['source_name'], 'ra': num('ra'), 'dec': num('dec'), 'w1': num('w1mpro'), 'w2': num('w2mpro'),
                    'pm_arcsec_yr': round(pmv, 3), 'mover': bool(pmv >= 0.3 and pmv / sig >= 5)})
    doc = {'catalogue': 'CatWISE2020 (Marocco et al. 2021), via NASA/IPAC IRSA', 'epoch': 'about 2015', 'n': len(out), 'sources': out}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(doc))
    return doc


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str):
    with _jobs_lock:
        j = _jobs.get(job_id)
    if not j:
        raise HTTPException(404, 'Unknown job.')
    return j


# ---------------------------------------------------------------------------
# Investigations
# ---------------------------------------------------------------------------

def inv_path(inv_id: str) -> Path:
    if inv_id in TARGETS:
        return DATA / inv_id / 'investigation.json'
    if not re.fullmatch(r'i[0-9a-f]{12}', inv_id):
        raise HTTPException(404, 'Unknown investigation.')
    curated = ROOT / 'data' / 'investigations' / f'{inv_id}.json'   # committed demonstration investigations
    return curated if curated.exists() else INVESTIGATIONS / f'{inv_id}.json'


@app.post('/api/investigations')
async def create_investigation(request: Request):
    body = await _json_body(request)
    fid = str(body.get('field_id', ''))
    try:
        ra, dec = parse_ra(body.get('ra')), parse_dec(body.get('dec'))
    except CoordinateError as error:
        raise HTTPException(400, str(error))
    fp = field_path(fid)
    if not fp.exists():
        raise HTTPException(404, 'Field not found or still processing.')
    field = read_json(fp)
    if fid not in TARGETS and (field['data_state'] in ('processing', 'failed') or _unsafe_live_cache(field)):
        raise HTTPException(409, 'Wait for the field to finish processing, or search this position again before measuring it.')
    # Clicking on a curated target opens its precomputed investigation.
    if fid in TARGETS:
        inv = read_json(DATA / fid / 'investigation.json')
        xi, eta = to_tangent(ra, dec, inv['source']['ra'], inv['source']['dec'])
        if math.hypot(float(xi), float(eta)) < 12:
            return {'investigation_id': fid, 'status': 'ready', 'job_id': None}
    inv_id = 'i' + hashlib.sha256(f'{fid}|{ra:.5f}|{dec:.5f}|v1'.encode()).hexdigest()[:12]
    ip = INVESTIGATIONS / f'{inv_id}.json'
    if ip.exists():
        return {'investigation_id': inv_id, 'status': 'ready', 'job_id': None}
    with _jobs_lock:
        running = next((j for j in _jobs.values() if j['result_id'] == inv_id and j['status'] in ('queued', 'running')), None)
    if running:
        return {'investigation_id': inv_id, 'status': 'processing', 'job_id': running['job_id']}
    job = new_job('investigation', inv_id)
    _pool.submit(_investigation_job, job, inv_id, fid, field, ra, dec, body.get('label'))
    return {'investigation_id': inv_id, 'status': 'processing', 'job_id': job}


def ensure_raw(fid, field, job_id=None, max_n=80):
    """Re-download native cutouts for a field from their recorded cutout URLs (e.g. on a fresh deployment),
    verifying each against the SHA-256 recorded at curation time."""
    import hashlib as _h
    d = raw_dir(fid)
    if any(d.glob('*.fits')):
        return
    d.mkdir(parents=True, exist_ok=True)
    frames = [fr for fr in field.get('frames', []) if fr.get('cutout_url')]
    if len(frames) > max_n:
        step = len(frames) / max_n
        frames = [frames[int(i * step)] for i in range(max_n)]
    from pipeline.spherex import _get
    for i, fr in enumerate(frames):
        if job_id:
            job_update(job_id, progress={'stage': 'Re-fetching native cutouts from IRSA (verified by SHA-256)', 'done': i, 'total': len(frames)})
        try:
            raw = _get(fr['cutout_url'], timeout=90, retries=4).content
        except Exception:  # noqa: BLE001
            continue
        if fr.get('sha256') and _h.sha256(raw).hexdigest() != fr['sha256']:
            continue   # archive content changed since curation; do not mix versions silently
        (d / f"{fr['id']}.fits").write_bytes(raw)
        prov = {'product_id': fr['id'], 'obs_id': fr.get('obs_id'), 'detector': fr.get('detector'), 'release': fr.get('release'),
                'collection': None, 'doi': None, 'archive_url': fr.get('archive_url'), 'cutout_url': fr['cutout_url'],
                'center_ra': field['ra'], 'center_dec': field['dec'], 'size_arcmin': field['fov_arcmin'], 'sha256': fr.get('sha256'),
                'bytes': len(raw), 'retrieved_utc': now(), 'processing_version': fr.get('processing_version'), 'path': ''}
        (d / f"{fr['id']}.prov.json").write_text(json.dumps(prov))


def _investigation_job(job_id, inv_id, fid, field, ra, dec, label):
    from pipeline.analysis import build_investigation, neighbours
    from pipeline.build_curated import sanitize, software_versions
    from pipeline.investigate import measure_epochs, track_from_fit, usable_positions
    from pipeline.measure import gaia_field, reference_candidates
    from pipeline.motion import fit_motion
    from pipeline.spherex import RELEASES
    try:
        job_update(job_id, status='running', progress={'stage': 'Preparing reference stars', 'done': 0, 'total': 0})
        ensure_raw(fid, field, job_id)
        files = sorted(str(p) for p in raw_dir(fid).glob('*.fits'))
        if not files:
            raise RuntimeError('No native cutouts are available for this field (IRSA unreachable?).')
        if fid in TARGETS:
            man = json.loads((DATA / fid / 'archive_manifest.json').read_text())
            sealed = {p['id'] for p in man['products'] if p.get('sealed')}
            if not (EXPERIMENTS / fid / 'result.json').exists():
                files = [f for f in files if Path(f).stem not in sealed]
        else:
            eligible = set(field.get('native_product_ids', [frame['id'] for frame in field['frames']]))
            files = [f for f in files if Path(f).stem in eligible]
        gcache = (DATA / fid / 'gaia_field.json') if fid in TARGETS else (FIELDS / fid / 'gaia_field.json')
        try:
            stars = gaia_field(field['ra'], field['dec'], field['fov_arcmin'] / 60 * 0.75, gmax=19.0, cache=gcache)
        except Exception as error:  # noqa: BLE001
            # Without Gaia the exposures cannot be lined up and "no Gaia counterpart" would be an empty claim: stop here.
            raise RuntimeError('The Gaia catalogue could not be reached, so this source was not measured. Try again in a minute.') from error
        nb = neighbours(stars, ra, dec, 61040.0, 3.0)
        ident = None
        exclude = []
        if nb:
            ident = f"Gaia DR3 {nb[0]['source_id']}"
            exclude = [nb[0]['source_id']]
        refs = reference_candidates(stars, exclude_ids=exclude)
        deblend = [s for s in stars if s['source_id'] not in set(exclude)]   # never deblend the source from itself
        track = {'ra': ra, 'dec': dec, 't0_mjd': 61040.0, 'pmra': 0.0, 'pmdec': 0.0, 'parallax': 0.0, 'source': 'user click (stationary seed)'}
        if nb and nb[0].get('pmra') is not None:
            g = next(s for s in stars if s['source_id'] == nb[0]['source_id'])
            track = {'ra': g['ra'], 'dec': g['dec'], 't0_mjd': 57388.5, 'pmra': g['pmra'], 'pmdec': g['pmdec'],
                     'parallax': g.get('parallax') or 0.0, 'source': f'{ident} track (catalogue-assisted centroid seed)'}
        job_update(job_id, progress={'stage': f'Measuring the source in {len(files)} native SPHEREx exposures', 'done': 0, 'total': len(files)})
        def prog(n, tot, stage=f'Measuring the source in {len(files)} native SPHEREx exposures'):
            job_update(job_id, progress={'stage': stage, 'done': n, 'total': tot})
        rows = measure_epochs(files, track, refs, fixed=(ra, dec), workers=6, stars=deblend, progress=prog)
        used = usable_positions(rows)
        note = track['source']
        if len(used) >= 8:
            mjd = [r['mjd'] for r in used]
            f = fit_motion(mjd, [r['position']['ra'] for r in used], [r['position']['dec'] for r in used],
                           [r['position']['sigma_arcsec'] for r in used], model='linear')
            pm = math.hypot(f.params['pmra'], f.params['pmdec']) * 1000
            e = f.errors()
            pm_err = math.hypot(e['pmra'], e['pmdec']) * 1000 / math.sqrt(2)
            if pm > 5 * pm_err and pm > 50:
                job_update(job_id, progress={'stage': 'Re-measuring along the fitted motion track', 'done': 0, 'total': len(files)})
                rows = measure_epochs(files, track_from_fit(f), refs, fixed=(ra, dec), workers=6, stars=deblend,
                                      progress=lambda n, t: job_update(job_id, progress={'stage': 'Re-measuring along the fitted motion track', 'done': n, 'total': t}))
                note = 'SPHEREx-fitted linear track (second pass)'
        visits = field['archive']['visits'] if field.get('archive') else []
        if visits and 'mjd_start' not in visits[0]:
            visits = []
        job_update(job_id, progress={'stage': 'Evaluating hypotheses', 'done': 1, 'total': 1})
        catalog = None
        if nb and nb[0].get('pmra') is not None:
            catalog = {'source': ident, 'pmra_masyr': nb[0]['pmra'], 'pmdec_masyr': nb[0]['pmdec'], 'parallax_mas': nb[0].get('parallax'),
                       'pmra_err': None, 'pmdec_err': None, 'parallax_err': None}
        prov = {'datasets': [{'name': 'SPHEREx DR1 Spectral Images', 'doi': RELEASES['spherex_dr1']['doi'], 'citation': RELEASES['spherex_dr1']['citation']},
                             {'name': 'SPHEREx QR3 Spectral Images', 'doi': None, 'citation': RELEASES['spherex_qr3']['citation']}],
                'catalogs': [{'name': 'Gaia DR3', 'url': 'https://doi.org/10.1051/0004-6361/202243940'}],
                'software': software_versions(), 'n_files': len(rows), 'manifest_url': f'/api/investigations/{inv_id}/export?format=json',
                'photometry_track': note}
        try:
            from pipeline import solarsystem
            ss_doc = solarsystem.check(ra, dec, [r['mjd'] for r in rows if r.get('mjd')], max_epochs=6)
        except Exception:  # noqa: BLE001 - the check is optional; a failure must not sink the investigation
            ss_doc = None
        doc = build_investigation(rows, inv_id=inv_id, kind='user', title=label or f'Source at {ra:.5f}, {dec:+.5f}', field_id=fid,
                                  solar_system=ss_doc,
                                  source={'ra': ra, 'dec': dec, 'label': label or 'User-selected source', 'catalog': nb[0] if nb else None},
                                  visits=visits, identification=ident, catalog=catalog, catalog_stars=stars, provenance=prov)
        (INVESTIGATIONS / f'{inv_id}.json').write_text(json.dumps(sanitize(doc), allow_nan=False))
        job_update(job_id, status='done', progress={'stage': 'done', 'done': 1, 'total': 1})
    except Exception as error:  # noqa: BLE001
        traceback.print_exc()
        job_update(job_id, status='failed', message=f'{type(error).__name__}: {str(error)[:300]}')


@app.get('/api/investigations/{inv_id}')
def get_investigation(inv_id: str):
    p = inv_path(inv_id)
    if not p.exists():
        with _jobs_lock:
            j = next((j for j in _jobs.values() if j['result_id'] == inv_id), None)
        if j:
            return {'id': inv_id, 'status': 'processing' if j['status'] != 'failed' else 'failed', 'progress': j['progress'], 'message': j['message']}
        raise HTTPException(404, 'Unknown investigation.')
    return read_json(p)


@app.get('/api/investigations/{inv_id}/export')
def export_investigation(inv_id: str, format: str = 'json'):
    p = inv_path(inv_id)
    if not p.exists():
        raise HTTPException(404, 'Unknown investigation.')
    doc = read_json(p)
    if format == 'json':
        return Response(json.dumps(doc, indent=1), media_type='application/json',
                        headers={'Content-Disposition': f'attachment; filename="parallax-{inv_id}.json"'})
    if format == 'csv':
        buf = io.StringIO()
        cols = ['product_id', 'time_utc', 'mjd', 'visit', 'detector', 'release', 'wavelength_um', 'bandwidth_um', 'ra', 'dec',
                'sigma_arcsec', 'snr', 'flux_ujy', 'flux_err_ujy', 'fixed_flux_ujy', 'fixed_flux_err_ujy', 'flags', 'used_for_motion',
                'outcome', 'archive_url', 'sha256']
        w = csv.writer(buf)
        w.writerow(['# PARALLAX evidence export', doc['id'], doc['title'], 'generated', doc['created_utc']])
        w.writerow(['# Data: NASA SPHEREx DR1 (doi:10.26131/IRSA678) and QR3 spectral images via NASA/IPAC IRSA'])
        w.writerow(cols)
        for d in doc['detections']:
            w.writerow([('|'.join(d[c]) if isinstance(d.get(c), list) else ('' if d.get(c) is None else d.get(c))) for c in cols])
        return Response(buf.getvalue(), media_type='text/csv',
                        headers={'Content-Disposition': f'attachment; filename="parallax-{inv_id}.csv"'})
    raise HTTPException(400, 'format must be json or csv')


# ---------------------------------------------------------------------------
# Validation and Discovery Lab
# ---------------------------------------------------------------------------

def git_commit_for(path: Path):
    rec = path.parent / 'commits.json'
    if rec.exists():
        hist = json.loads(rec.read_text()).get(path.name) or []
        if hist:
            return hist[-1]   # oldest = the commit that first froze this file (git log lists newest first)
    try:
        out = subprocess.run(['git', 'log', '-1', '--format=%H %cI', '--', str(path.relative_to(ROOT))], cwd=ROOT,
                             capture_output=True, text=True, timeout=5).stdout.strip()
        if out:
            h, t = out.split(' ', 1)
            return {'hash': h, 'time': t}
    except Exception:  # noqa: BLE001
        pass
    return None


@app.get('/api/validation')
def validation():
    p = ROOT / 'validation' / 'validation_results.json'
    if p.exists():
        return read_json(p)
    raise HTTPException(404, 'Validation results have not been generated yet (run python -m validation.run).')


@app.get('/api/lab')
def lab():
    from pipeline.astrometry import to_tangent as tt
    from pipeline.motion import MotionFit
    import numpy as np
    out = []
    for d in sorted(EXPERIMENTS.glob('*/prediction.json')):
        slug = d.parent.name
        pred = read_json(d)
        res_p = d.parent / 'result.json'
        res = read_json(res_p) if res_p.exists() else None
        P = pred['predictions']['primary']
        f = MotionFit(P['model'], P['ra_ref'], P['dec_ref'], P['t0_mjd'], P['params'], np.array(P['param_cov']), 0, 1, 0, 0,
                      P.get('fixed_parallax_arcsec'))
        pts = []
        train = read_json(d.parent / 'training_measurements.json')
        held = read_json(d.parent / 'heldout_measurements.json') if (d.parent / 'heldout_measurements.json').exists() else []
        from pipeline.investigate import usable_positions
        for label, rows in (('training', train), ('heldout', held if res else [])):
            for r in usable_positions(rows):
                xi, eta = tt(r['position']['ra'], r['position']['dec'], f.ra_ref, f.dec_ref)
                pts.append({'mjd': r['mjd'], 'xi': float(xi), 'eta': float(eta), 'sigma': r['position']['sigma_arcsec'], 'set': label,
                            'product_id': r['product_id'], 'wavelength_um': r.get('wavelength_um')})
        t_all = [p['mjd'] for p in pts] + [pred['held_out']['mean_epoch_mjd']]
        tgrid = np.linspace(min(t_all) - 20, max(pred['held_out']['visit']['mjd_end'], max(t_all)) + 20, 300)
        pr = f.predict(tgrid)
        track = [{'mjd': float(t), 'xi': float(a), 'eta': float(b)} for t, a, b in zip(tgrid, pr['xi'], pr['eta'])]
        pm = f.predict([pred['held_out']['mean_epoch_mjd']])
        sha = (d.parent / 'prediction.sha256').read_text().split()[0]
        field = read_json(DATA / slug / 'field.json') if (DATA / slug / 'field.json').exists() else None
        held_ids = set(pred['held_out']['product_ids'])
        tr_ids, ho_ids = [], []
        if field:
            for fr in field['frames']:
                (ho_ids if fr['id'] in held_ids else tr_ids).append(fr['id'])
        out.append({
            'id': pred['experiment'], 'target': slug, 'title': pred['target']['title'], 'prediction': pred,
            'prediction_sha256': sha, 'prediction_commit': git_commit_for(d), 'result': res,
            'result_commit': git_commit_for(res_p) if res else None, 'field_id': slug,
            'training_frame_ids': tr_ids, 'heldout_frame_ids': ho_ids if res else [],
            'points': pts, 'predicted_track': track,
            'predicted_at_mean_epoch': {'xi': float(pm['xi'][0]), 'eta': float(pm['eta'][0]), 'cov_arcsec2': pm['cov'][0].tolist(),
                                        'ra_deg': P['ra_deg'], 'dec_deg': P['dec_deg']},
            'tangent_reference': {'ra_deg': f.ra_ref, 'dec_deg': f.dec_ref},
        })
    return {'experiments': out}


# ---------------------------------------------------------------------------
# Planet X hunt (blind search results; see pipeline/hunt.py and validation/hunt_fields.py)
# ---------------------------------------------------------------------------

HUNT = ROOT / 'data' / 'hunt'


@app.get('/api/forecasts')
def forecasts():
    """Forward predictions for SPHEREx data that did not exist when they were locked (validation/forecast.py)."""
    out = []
    from validation import ledger
    for p in sorted((ROOT / 'validation' / 'forecasts').glob('*.json')):
        if p.name.endswith('-vs-jpl.json'):
            continue
        d = read_json(p)
        lk = ledger.find(f"forecast:{d.get('target')}")
        sha_p = p.with_suffix('.sha256')
        commit = None
        try:
            log = subprocess.run(['git', 'log', '--diff-filter=A', '--format=%H %cI', '--', str(p.relative_to(ROOT))], cwd=ROOT,
                                 capture_output=True, text=True, timeout=5).stdout.strip().splitlines()
            if log:
                h, t = log[-1].split(' ', 1)
                commit = {'hash': h, 'time': t}
        except Exception:  # noqa: BLE001
            pass
        out.append({k: d.get(k) for k in ('target', 'title', 'locked_utc', 'model', 'model_note', 'data_used', 'archive_at_lock', 'fit',
                                          'criterion', 'stays_here_null', 'predictions', 'how_to_check', 'kind', 'spherex_windows')}
                   | {'sha256': sha_p.read_text().split()[0] if sha_p.is_file() else None, 'commit': commit,
                      'ledger': {'seq': lk['seq'], 'time_utc': lk['time_utc'], 'hash': lk['hash']} if lk else None,
                      'jpl_check': read_json(p.with_name(p.stem + '-vs-jpl.json')) if p.with_name(p.stem + '-vs-jpl.json').is_file() else None})
    return {'forecasts': out}


@app.get('/api/distant')
def distant_results():
    """Blind recovery of known distant bodies by parallax (validation/distant_report.py)."""
    p = ROOT / 'validation' / 'distant_results.json'
    if not p.exists():
        raise HTTPException(404, 'Distant-world results have not been generated yet (python -m validation.distant_report).')
    return read_json(p)


@app.get('/api/planet-nine')
def planet_nine_results():
    """The Planet Nine mode: search of the hunt fields, synthetic test and reach (validation/planet_nine.py)."""
    p = ROOT / 'validation' / 'planet_nine.json'
    if not p.exists():
        raise HTTPException(404, 'Planet Nine results have not been generated yet (python -m validation.planet_nine report).')
    return read_json(p)


@app.get('/api/barnard-halo')
def barnard_halo():
    """Barnard's Star: motion measured from its unsaturated halo, tested on the sealed visit (validation/barnard_halo.py)."""
    folder = ROOT / 'validation' / 'experiments' / 'barnards-star-halo'
    if not (folder / 'result.json').exists():
        raise HTTPException(404, "The Barnard's Star halo test has not been run yet (python -m validation.barnard_halo open).")
    proto = read_json(folder / 'protocol.json')
    return {'result': read_json(folder / 'result.json'), 'pass_rule': proto['pass_rule'], 'method': proto['method'],
            'disclosures': proto['disclosures'], 'n_reference': proto['reference_visit']['n_exposures']}


@app.get('/api/vanished')
def vanished_results():
    """Bright WISE sources (about 2015) that SPHEREx no longer sees where WISE saw them (validation/vanished.py)."""
    p = ROOT / 'validation' / 'vanished.json'
    if not p.exists():
        raise HTTPException(404, 'The disappearance check has not been run yet (python -m validation.vanished).')
    d = read_json(p)
    return {k: d[k] for k in ('method', 'thresholds', 'n_fields', 'n_tested', 'counts', 'flagged')} | {
        'fields_without_catalogue': [f['field_id'] for f in d['fields'] if f['n_wise'] == 0]}


@app.get('/api/coldspec')
def coldspec_results():
    """Cold-world spectra: a model that reads spectral types from SPHEREx's 102 colours (validation/coldspec.py)."""
    base = ROOT / 'validation' / 'coldspec'
    if not (base / 'cv.json').exists():
        raise HTTPException(404, 'The cold-world spectral search has not been run yet (python -m validation.coldspec).')
    out = {'cv': read_json(base / 'cv.json'), 'protocol': None, 'results': None, 'lists': None, 'vetting': None, 'quality': None}
    if (base / 'vetting.json').exists():
        out['vetting'] = read_json(base / 'vetting.json')
    if (base / 'quality.json').exists():
        q = read_json(base / 'quality.json')
        out['quality'] = {k: q.get(k) for k in ('scatter_passing_cuts_dex', 'n_passing', 'wise_check')}
    if (base / 'protocol.json').exists():
        out['protocol'] = read_json(base / 'protocol.json')
    if (base / 'results.json').exists():
        r = dict(read_json(base / 'results.json'))
        r.pop('typed', None)                      # the full list is in the file; the page needs the summary and the candidates
        out['results'] = r
    if (base / 'objects.json').exists():
        o = read_json(base / 'objects.json')
        out['lists'] = {'counts': o['counts'], 'generated_utc': o['generated_utc'], 'source': o['source']}
    wide = base / 'wide'
    out['wide'] = None
    if (wide / 'vetting.json').exists() and (wide / 'results.json').exists():
        r, lists = read_json(wide / 'results.json'), read_json(wide / 'objects.json')
        out['wide'] = {'n_objects': len(lists['objects']), 'counts': lists['counts'], 'sources': lists['sources'], 'n_spectra': r['n_objects'],
                       'n_pass_quality': r['n_pass_quality'], 'n_outliers': r['n_outliers'], 'n_flagged': r['n_flagged'], 'vetting': read_json(wide / 'vetting.json'),
                       'candidates': read_json(wide / 'candidates.json') if (wide / 'candidates.json').exists() else None,
                       'other_telescopes': read_json(wide / 'other_telescopes.json') if (wide / 'other_telescopes.json').exists() else None}
    return out


# ---------------------------------------------------------------------------
# "Check a candidate": people look at a real SPHEREx spectrum and say whether the methane bands are dark.
# Votes are kept on this server only (.parallax-cache/check/votes.jsonl): an answer, an optional first name, a time.
# ---------------------------------------------------------------------------

CHECK_QUEUE = ROOT / 'validation' / 'coldspec' / 'check_queue.json'
CHECK_VOTES = CACHE / 'check' / 'votes.jsonl'
CHECK_ANSWERS = ('dips', 'smooth', 'unsure')
_votes_lock = threading.Lock()


def _check_tallies() -> dict:
    out: dict[str, dict] = {}
    if CHECK_VOTES.is_file():
        for line in CHECK_VOTES.read_text().splitlines():
            try:
                v = json.loads(line)
            except ValueError:
                continue
            t = out.setdefault(v.get('id', ''), {'dips': 0, 'smooth': 0, 'unsure': 0, 'n': 0})
            if v.get('answer') in CHECK_ANSWERS:
                t[v['answer']] += 1
                t['n'] += 1
    return out


@app.get('/api/check')
def check_queue():
    """The objects to check, with how people have voted so far.  Known answers are sent only after a vote."""
    if not CHECK_QUEUE.exists():
        raise HTTPException(404, 'The check queue has not been built yet (python -m validation.coldspec check).')
    q = read_json(CHECK_QUEUE)
    tallies = _check_tallies()
    items = [{k: v for k, v in it.items() if k not in ('truth', 'truth_label', 'name', 'model')} | {'votes': tallies.get(it['id'], {'dips': 0, 'smooth': 0, 'unsure': 0, 'n': 0})['n']}
             for it in q['items']]
    return {'question': q['question'], 'reference': q['reference'], 'bands_um': q['bands_um'], 'note': q['note'], 'items': items,
            'total_votes': sum(t['n'] for t in tallies.values())}


@app.post('/api/check')
async def check_vote(request: Request):
    body = await _json_body(request)
    if not CHECK_QUEUE.exists():
        raise HTTPException(404, 'The check queue has not been built yet.')
    item = next((it for it in read_json(CHECK_QUEUE)['items'] if it['id'] == str(body.get('id', ''))), None)
    answer = body.get('answer')
    if item is None or answer not in CHECK_ANSWERS:
        raise HTTPException(400, 'Send {"id": an object in the queue, "answer": "dips" | "smooth" | "unsure"}.')
    name = re.sub(r'[^\w .\-]', '', str(body.get('name') or ''))[:24].strip() or None
    with _votes_lock:
        CHECK_VOTES.parent.mkdir(parents=True, exist_ok=True)
        with CHECK_VOTES.open('a') as f:
            f.write(json.dumps({'id': item['id'], 'answer': answer, 'name': name, 'utc': now()}) + '\n')
        tallies = _check_tallies()
        tally = tallies[item['id']]
    return {'id': item['id'], 'tally': tally, 'kind': item['kind'], 'name': item['name'], 'truth': item['truth'], 'truth_label': item['truth_label'],
            'model': item['model'], 'flagged': bool(item.get('flagged')), 'first_spectrum': bool(item.get('first_spectrum')),
            'agrees_with_known': (answer == item['truth']) if item['truth'] and answer != 'unsure' else None,
            'total_votes': sum(t['n'] for t in tallies.values())}


@app.get('/api/asteroids')
def asteroid_results():
    """Asteroid hunt: tracks found in SPHEREx images alone, then matched to known asteroids (validation/asteroids.py)."""
    p = ROOT / 'validation' / 'asteroids' / 'results.json'
    if not p.exists():
        raise HTTPException(404, 'The asteroid hunt has not been run yet (python -m validation.asteroids).')
    d = dict(read_json(p))
    d['tracks'] = [{k: v for k, v in t.items() if k != 'points'} | {'n_points': len(t['points'])} for t in d['tracks']]
    d.pop('recovery', None)
    tr = ROOT / 'validation' / 'asteroids' / 'tracks.json'
    if tr.exists():
        t = read_json(tr)
        d['history'], d['version'] = t.get('history'), t.get('version')
    plan = ROOT / 'validation' / 'asteroids' / 'plan.json'
    if plan.exists():
        d['fields'] = [{k: f[k] for k in ('id', 'ra', 'dec', 'ecl_lon', 'n_nights')} | {'n_images': len(f['products'])} for f in read_json(plan)['fields']]
    return d


def _p9_survivors(vet: dict, cross_path: Path) -> int:
    """Deep-stack candidates still standing: they passed the split checks and were not missing from another visit where they must be."""
    passed = [c for c in vet['candidates'] if c['checks']['passes_split_tests'] and not c['checks']['rests_on_one_image']]
    if cross_path.exists():
        gone = {(r['visit'], r['ra'], r['dec']) for r in read_json(cross_path)['candidates'] if r['verdict'].startswith('not seen')}
        passed = [c for c in passed if (c['visit'], c['ra'], c['dec']) not in gone]
    return len(passed)


@app.get('/api/how')
def how_we_find_them():
    """Real numbers and pictures for the step-by-step page that explains the method (web: /how). Every part is optional."""
    base = ROOT / 'validation'
    out: dict = {}
    tr = base / 'asteroids' / 'tracks.json'
    if tr.exists():
        s = read_json(tr)['summary']
        out['still'] = {'patches': len(s), 'dots': sum(v.get('paired_detections', 0) for v in s.values()),
                        'still': sum(v.get('fixed_sources_removed', 0) for v in s.values()),
                        'left': sum(v.get('night_detections', 0) for v in s.values()),
                        'example': next(({'id': k, **v} for k, v in s.items()), None)}
    cal = base / 'asteroids' / 'v2_calibration' / 'results.json'
    if cal.exists():
        c = read_json(cal)
        t = next((t for t in c['tracks'] if t.get('known')), None)
        if t:
            out['track'] = {'name': t['known']['name'], 'V': t['known']['V'], 'rate_arcsec_h': t['rate_arcsec_h'], 'rms_arcsec': t['rms_arcsec'],
                            'points': [{'mjd': p['mjd'], 'x': p['x'], 'y': p['y']} for p in t['points']],
                            'chance_tracks_expected': c.get('chance_tracks_expected')}
    st = base / 'asteroids' / 'stack.json'
    if st.exists():
        d = read_json(st)
        out['stack'] = {k: d[k] for k in ('by_V', 'n_asteroids', 'n_seen_single', 'n_seen_stack', 'threshold_stack_snr', 'examples', 'n_control_paths')}
        out['stack']['n_seen_stack_snr5'] = sum(1 for r in d['asteroids'] if r['stack_snr'] >= 5)
        out['stack']['n_control_snr5'] = sum(1 for r in d['asteroids'] for c in r['controls'] if c >= 5)
    deep = []
    for f in sorted((base / 'p9_deepstack').glob('*/search.json')):
        d = read_json(f)
        inj = read_json(f.with_name('injection.json')) if f.with_name('injection.json').exists() else None
        fe = read_json(f.with_name('fetch.json')) if f.with_name('fetch.json').exists() else {'visits': []}
        vet = read_json(f.with_name('vet.json')) if f.with_name('vet.json').exists() else None
        deep.append({'field': f.parent.name, 'ra': d['field']['ra'], 'dec': d['field']['dec'], 'visits': fe['visits'], 'n_photos': fe.get('n_downloaded'), 'n_visits_all': len(fe['visits']),
                     'n_images': sum(v['images']['n_target'] for v in d['visits']), 'n_visits': len(d['visits']),
                     'area_deg2': round(sum(v['area_deg2'] for v in d['visits']) / max(len(d['visits']), 1), 3),
                     'single_5sigma_ujy': min(v['noise']['single_5sigma_ujy'] for v in d['visits']),
                     'n_candidates': d['n_candidates'], 'n_still_changes': len(d.get('still_changes', [])),
                     'n_passed_checks': None if vet is None else _p9_survivors(vet, f.with_name('cross.json')),
                     'chance_expected': round(len(d['visits']) / 3, 2),
                     'injection': inj['results'] if inj else None, 'injection_visit_images': None if not inj else
                     next((v['images']['n_target'] for v in d['visits'] if v['visit'] == inj['visit']), None)})
    out['deep'] = deep
    p9 = base / 'planet_nine.json'
    if p9.exists():
        out['planet_nine'] = read_json(p9)['nominal']
    from validation import ledger
    ok, _ = ledger.verify()
    es = ledger.entries()
    out['ledger'] = {'ok': ok, 'n': len(es), 'last': [{'seq': e['seq'], 'label': e['label'], 'hash': e['hash'][:12], 'time_utc': e['time_utc']} for e in es[-4:]]}
    return out


@app.get('/api/telescopes')
def other_telescopes(ra: float, dec: float, radius_arcmin: float = 3.0):
    """Which other telescopes have looked at this spot: NASA MAST (Hubble, JWST, TESS, ...), NASA HEASARC (Chandra, XMM-Newton,
    Swift, ...) and CADC (NEOSSat). Counts, years and a few preview images; nothing is downloaded (pipeline/archives.py)."""
    from pipeline import archives
    try:
        return archives.look(ra, dec, radius_arcmin)
    except ValueError as error:
        raise HTTPException(400, str(error))


@app.get('/api/telescopes/preview')
def other_telescope_preview(uri: str):
    """A JWST or Hubble preview image from MAST, passed on as an image (only MAST preview addresses are accepted)."""
    from fastapi.responses import Response
    from pipeline import archives
    try:
        data = archives.preview(uri)
    except ValueError as error:
        raise HTTPException(400, str(error))
    except Exception:  # noqa: BLE001
        raise HTTPException(502, 'MAST did not send the preview image.')
    kind = 'image/png' if data.startswith(b'\x89PNG') else 'image/jpeg'
    return Response(content=data, media_type=kind, headers={'Cache-Control': 'public, max-age=604800'})


@app.get('/api/ml')
def ml_results():
    """The machine-learning real/artefact test (validation/ml_realbogus.py)."""
    p = ROOT / 'validation' / 'ml_realbogus.json'
    if not p.exists():
        raise HTTPException(404, 'The machine-learning test has not been run yet (python -m validation.ml_realbogus).')
    return read_json(p)


@app.get('/api/watch')
def watch_status():
    """The latest check of NASA's archive for new SPHEREx images of everything PARALLAX has predicted (pipeline/watch.py)."""
    p = ROOT / 'data' / 'watch' / 'status.json'
    if not p.exists():
        raise HTTPException(404, 'The archive has not been checked yet (python -m pipeline.watch).')
    return read_json(p)


@app.get('/api/ledger')
def lock_ledger():
    """The local lock record: what was hashed, when, and whether the chain and the files still match."""
    from validation import ledger
    ok, problems = ledger.verify()
    return {'ok': ok, 'problems': problems, 'entries': ledger.entries()}


@app.get('/api/halo')
def halo_results():
    p = ROOT / 'validation' / 'halo_results.json'
    if not p.exists():
        raise HTTPException(404, 'Halo results have not been generated yet (python -m validation.halo_controls).')
    return read_json(p)


@app.get('/api/hunt')
def hunt_index():
    p = HUNT / 'index.json'
    if not p.exists():
        raise HTTPException(404, 'The hunt has not been run yet (python -m validation.hunt_fields run all).')
    return read_json(p)


@app.get('/api/hunt-injection')
def hunt_injection():
    p = ROOT / 'validation' / 'hunt_injection.json'
    if not p.exists():
        raise HTTPException(404, 'The blind injection test has not been run yet (python -m validation.hunt_inject).')
    return read_json(p)


@app.get('/api/hunt/{field_id}')
def hunt_field(field_id: str):
    p = HUNT / field_id / 'hunt.json'
    if not re.fullmatch(r'[\w.-]+', field_id) or not p.is_file():
        raise HTTPException(404, 'No hunt result for this field.')
    return read_json(p)


@app.get('/files/hunt/{field_id}/frames/{name}')
def hunt_frame(field_id: str, name: str):
    if not re.fullmatch(r'[\w.-]+', field_id) or not re.fullmatch(r'[\w.-]+\.bin', name):
        raise HTTPException(404)
    p = HUNT / field_id / 'frames' / name
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, media_type='application/octet-stream', headers={'Cache-Control': 'public, max-age=3600'})


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

@app.get('/files/targets/{slug}/{path:path}')
def target_file(slug: str, path: str):
    if slug not in TARGETS:
        raise HTTPException(404)
    base = (DATA / slug).resolve()
    p = (base / path.lstrip('/')).resolve()      # a leading slash or '..' must never escape the target's folder
    if base not in p.parents or not p.is_file():
        raise HTTPException(404)
    mt = 'application/octet-stream' if p.suffix == '.bin' else 'application/json'
    return FileResponse(p, media_type=mt, headers={'Cache-Control': 'public, max-age=86400'})


@app.get('/files/fields/{fid}/frames/{name}')
def field_frame(fid: str, name: str):
    if not re.fullmatch(r'f[\w.]+', fid) or not re.fullmatch(r'[\w.-]+\.bin', name):
        raise HTTPException(404)
    p = FIELDS / fid / 'frames' / name
    if not p.is_file():
        raise HTTPException(404)
    field = get_field(fid)
    if not any(f['data_url'] == f'/files/fields/{fid}/frames/{name}' for f in field['frames']):
        raise HTTPException(404)
    return FileResponse(p, media_type='application/octet-stream', headers={'Cache-Control': 'public, max-age=86400'})


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse(status_code=exc.status_code, content={'message': exc.detail})


_dist = ROOT / 'web' / 'dist'
if _dist.is_dir():
    @app.get('/{full_path:path}')
    def spa(full_path: str):
        if full_path.startswith(('api/', 'files/')) or full_path in ('api', 'files'):
            raise HTTPException(404, 'Not found.')
        p = _dist / full_path
        if full_path and p.is_file() and _dist in p.resolve().parents:
            return FileResponse(p)
        return FileResponse(_dist / 'index.html')
