"""PARALLAX web API (see docs/API.md).

Run:  .venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
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

from pipeline.astrometry import CoordinateError, mjd_to_iso, parse_dec, parse_position, parse_ra, propagate, to_tangent
from pipeline.spherex import CACHE, ROOT, ArchiveUnavailable, field_key, group_visits, search, fetch_many
from pipeline.targets import ORDER, TARGETS

VERSION = '1.0.0'
DATA = ROOT / 'data' / 'targets'
FIELDS = CACHE / 'fields'
INVESTIGATIONS = CACHE / 'investigations'
EXPERIMENTS = ROOT / 'validation' / 'experiments'
FIELDS.mkdir(parents=True, exist_ok=True)
INVESTIGATIONS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title='PARALLAX', version=VERSION)
app.add_middleware(GZipMiddleware, minimum_size=2000)

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=3)
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
    except CoordinateError:
        pass
    key = re.sub(r'\s+', ' ', q.lower().replace('’', "'"))
    if key in ALIASES:
        t = TARGETS[ALIASES[key]]
        p = propagate(t.astrometry.ra_deg, t.astrometry.dec_deg,
                      t.astrometry.epoch_mjd or (51544.5 + (t.astrometry.epoch_jyear - 2000.0) * 365.25),
                      t.astrometry.pmra_masyr, t.astrometry.pmdec_masyr, t.astrometry.parallax_mas, [61040.0])
        return {'name': t.title, 'ra': float(p.ra[0]), 'dec': float(p.dec[0]), 'source': t.astrometry.source,
                'epoch_note': 'catalogue astrometry propagated to 2026.0 (proper motion + parallax)', 'target': t.slug,
                'pmra_masyr': t.astrometry.pmra_masyr, 'pmdec_masyr': t.astrometry.pmdec_masyr, 'parallax_mas': t.astrometry.parallax_mas}
    try:
        r = requests.get('https://vizier.cfa.harvard.edu/viz-bin/nph-sesame/-oxp/SNV?' + requests.utils.quote(q), timeout=15,
                         headers={'User-Agent': 'PARALLAX/1.0 (research prototype)'})
        root = ET.fromstring(r.content)
        res = root.find('.//Resolver')
        if res is None or res.find('jradeg') is None:
            raise HTTPException(404, f'Name "{q}" was not resolved (Sesame/SIMBAD via the CfA mirror).')
        ra, dec = float(res.findtext('jradeg')), float(res.findtext('jdedeg'))
        pmra = res.findtext('pm/pmRA')
        pmdec = res.findtext('pm/pmDE')
        plx = res.findtext('plx/v')
        out = {'name': q, 'ra': ra, 'dec': dec, 'source': res.get('name', 'Sesame'), 'epoch_note': 'J2000 position from SIMBAD',
               'otype': res.findtext('otype')}
        if pmra and pmdec:
            pmra, pmdec = float(pmra), float(pmdec)
            p = propagate(ra, dec, 51544.5, pmra, pmdec, float(plx) if plx else 0.0, [61040.0])
            out.update({'ra': float(p.ra[0]), 'dec': float(p.dec[0]), 'pmra_masyr': pmra, 'pmdec_masyr': pmdec,
                        'parallax_mas': float(plx) if plx else None,
                        'epoch_note': 'SIMBAD J2000 position propagated to 2026.0 with its proper motion and parallax'})
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


@app.post('/api/fields')
async def create_field(request: Request):
    body = await request.json()
    try:
        ra, dec = parse_ra(body.get('ra')), parse_dec(body.get('dec'))
    except CoordinateError as error:
        raise HTTPException(400, str(error))
    fov = float(body.get('fov_arcmin') or 6.0)
    if not 2.0 <= fov <= 30.0:
        raise HTTPException(400, 'Field of view must be between 2 and 30 arcmin.')
    max_frames = int(min(max(int(body.get('max_frames') or 24), 4), 48))
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
        # A 'processing' document with no live job was interrupted (e.g. a server restart): run it again.
        if doc['data_state'] not in ('archive_unavailable', 'failed', 'processing'):
            return {'field_id': fid, 'status': 'ready', 'job_id': None}
    job = new_job('field', fid)
    from pipeline.frames import grid_doc
    job_update(job, field_meta={'ra': ra, 'dec': dec, 'fov_arcmin': fov, 'grid': grid_doc(ra, dec, fov), 'catalog': [],
                                'catalog_epoch_mjd': 57388.5, 'archive': None, 'stacks': [], 'title': None})
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
    from pipeline.frames import grid_doc, make_frames
    from pipeline.measure import gaia_field
    folder = FIELDS / fid
    folder.mkdir(parents=True, exist_ok=True)
    base = {'field_id': fid, 'kind': 'live', 'title': None, 'ra': ra, 'dec': dec, 'fov_arcmin': fov, 'progress': None,
            'grid': grid_doc(ra, dec, fov), 'archive': None, 'frames': [], 'catalog': [], 'catalog_epoch_mjd': 57388.5,
            'stacks': [], 'investigation_id': None}

    def save(doc):
        (folder / 'field.json').write_text(json.dumps(doc, allow_nan=False, default=lambda o: None))

    try:
        job_update(job_id, status='running', progress={'stage': 'Querying IRSA SIA2 (spherex_dr1, spherex_qr3)', 'done': 0, 'total': 0})
        try:
            products = search(ra, dec)
        except ArchiveUnavailable as error:
            save(base | {'data_state': 'archive_unavailable', 'message': f'IRSA did not respond: {error}'})
            job_update(job_id, status='done', message='archive_unavailable')
            return
        if not products:
            save(base | {'data_state': 'no_coverage', 'message': 'IRSA returned no SPHEREx DR1/QR3 spectral images covering this position.'})
            job_update(job_id, status='done', message='no_coverage')
            return
        chosen, visits = choose_products(products, max_frames, wmin, wmax)
        vis_doc = [{'id': f'visit-{i + 1}', 'start_utc': mjd_to_iso(v[0].t_min), 'end_utc': mjd_to_iso(v[-1].t_max),
                    'mjd_start': v[0].t_min, 'mjd_end': v[-1].t_max, 'n_products': len(v),
                    'releases': sorted({p.release for p in v}), 'per_detector': {f'D{d}': sum(1 for p in v if p.detector == d) for d in range(1, 7)},
                    'sealed': False} for i, v in enumerate(visits)]
        vmap = {p.id: f'visit-{i + 1}' for i, v in enumerate(visits) for p in v}
        archive = {'n_products': len(products), 'collections': sorted({p.collection for p in products}), 'queried_utc': now(), 'visits': vis_doc}
        total = len(chosen)

        def prog(n, tot):
            job_update(job_id, progress={'stage': 'Downloading SPHEREx cutouts from IRSA', 'done': n, 'total': tot})
        save(base | {'data_state': 'processing', 'message': None, 'archive': archive, 'progress': {'stage': 'download', 'done': 0, 'total': total}})
        done, failures = fetch_many(chosen, ra, dec, fov, folder / 'raw', workers=6, progress=prog)
        if not done:
            save(base | {'data_state': 'archive_unavailable', 'archive': archive,
                         'message': f'All {total} cutout downloads failed; IRSA may be busy. Try again shortly.'})
            job_update(job_id, status='done', message='archive_unavailable')
            return
        job_update(job_id, progress={'stage': 'Reprojecting frames onto a common sky grid', 'done': 0, 'total': len(done)})
        paths = [folder / 'raw' / f'{p.product_id}.fits' for p in done]
        frames, errors = make_frames(paths, ra, dec, fov, folder / 'frames', visits=vmap, workers=4)
        for fr in frames:
            fr['data_url'] = f"/files/fields/{fid}/frames/{fr.pop('file')}"
        job_update(job_id, progress={'stage': 'Fetching Gaia DR3 catalogue overlay', 'done': 0, 'total': 1})
        try:
            cat = gaia_field(ra, dec, fov / 60 * 0.75, gmax=19.0, cache=folder / 'gaia_field.json')
        except Exception:  # noqa: BLE001
            cat = []
        n_vis = len({f['visit'] for f in frames})
        state = 'live' if n_vis >= 2 else 'insufficient'
        msg = None if n_vis >= 2 else 'Only one SPHEREx visit covers this position so far; a time comparison needs at least two.'
        if failures:
            msg = (msg + ' ' if msg else '') + f'{len(failures)} of {total} cutouts failed to download and are omitted.'
        save(base | {'data_state': state, 'message': msg, 'archive': archive, 'frames': frames, 'frame_errors': len(errors),
                     'catalog': [s for s in cat if s.get('ra') is not None]})
        job_update(job_id, status='done', progress={'stage': 'done', 'done': len(frames), 'total': len(frames)})
    except Exception as error:  # noqa: BLE001
        traceback.print_exc()
        save(base | {'data_state': 'failed', 'message': f'Processing failed: {type(error).__name__}: {error}'})
        job_update(job_id, status='failed', message=str(error)[:300])


@app.get('/api/fields/{field_id}')
def get_field(field_id: str):
    p = field_path(field_id)
    if not p.exists():
        with _jobs_lock:
            j = next((j for j in _jobs.values() if j['result_id'] == field_id), None)
        if j:
            return {'field_id': field_id, 'kind': 'live', 'data_state': 'processing', 'progress': j['progress'], 'frames': [],
                    'message': None, **j.get('field_meta', {})}
        raise HTTPException(404, 'Unknown field.')
    doc = dict(read_json(p))
    if doc.get('data_state') == 'processing':
        with _jobs_lock:
            j = next((j for j in _jobs.values() if j['result_id'] == field_id and j['status'] in ('queued', 'running')), None)
        if j:
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
    body = await request.json()
    fid = str(body.get('field_id', ''))
    try:
        ra, dec = parse_ra(body.get('ra')), parse_dec(body.get('dec'))
    except CoordinateError as error:
        raise HTTPException(400, str(error))
    fp = field_path(fid)
    if not fp.exists():
        raise HTTPException(404, 'Field not found or still processing.')
    field = read_json(fp)
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
        gcache = (DATA / fid / 'gaia_field.json') if fid in TARGETS else (FIELDS / fid / 'gaia_field.json')
        try:
            stars = gaia_field(field['ra'], field['dec'], field['fov_arcmin'] / 60 * 0.75, gmax=19.0, cache=gcache)
        except Exception:  # noqa: BLE001
            stars = []
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
    for p in sorted((ROOT / 'validation' / 'forecasts').glob('*.json')):
        d = read_json(p)
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
                                          'criterion', 'stays_here_null', 'predictions', 'how_to_check')}
                   | {'sha256': sha_p.read_text().split()[0] if sha_p.is_file() else None, 'commit': commit})
    return {'forecasts': out}


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
    if slug not in TARGETS or '..' in path:
        raise HTTPException(404)
    p = DATA / slug / path
    if not p.is_file():
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
