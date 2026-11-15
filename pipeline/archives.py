"""Which other telescopes have looked at a patch of sky.

Three public archives are asked at once, each with its own time limit:

* NASA's MAST (Hubble, JWST, TESS, GALEX, Pan-STARRS, Swift UV/optical, IUE, Kepler/K2, FUSE, SDSS spectra), through its
  TAP service on the CAOM tables (one count per telescope, plus a few JWST and Hubble preview images);
* NASA's HEASARC (Chandra, XMM-Newton, Swift X-ray, NuSTAR, NICER), through its TAP service on each mission's master table;
* the Canadian Astronomy Data Centre (NEOSSat, the Canadian Space Agency's asteroid-hunting satellite), through its CAOM TAP.

Only counts, dates and preview links are returned: no data is downloaded.  An archive that does not answer in time is
reported as such, never as "no observations".  Results are cached for a week per position.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.parallax-cache' / 'archives'
CACHE_DAYS = 7.0

MAST_TAP = 'https://mast.stsci.edu/vo-tap/api/v0.1/caom/sync'
HEASARC_TAP = 'https://heasarc.gsfc.nasa.gov/xamin/vo/tap/sync'
CADC_TAP = 'https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/argus/sync'

# MAST collection -> (name people know, who runs it, kind of light).  Collections not listed (processed products such as
# HLA and HLSP, and test entries such as ROMAN) are not counted, so nothing is counted twice or counted before it is real.
MAST = {
    'JWST': ('James Webb Space Telescope', 'NASA, ESA, CSA', 'infrared'),
    'HST': ('Hubble Space Telescope', 'NASA, ESA', 'visible and ultraviolet'),
    'TESS': ('TESS', 'NASA', 'visible'),
    'GALEX': ('GALEX', 'NASA', 'ultraviolet'),
    'PS1': ('Pan-STARRS', 'University of Hawaii', 'visible'),
    'SWIFT': ('Swift (ultraviolet camera)', 'NASA', 'ultraviolet'),
    'IUE': ('International Ultraviolet Explorer', 'NASA, ESA, UK', 'ultraviolet'),
    'Kepler': ('Kepler', 'NASA', 'visible'),
    'K2': ('Kepler (K2)', 'NASA', 'visible'),
    'FUSE': ('FUSE', 'NASA', 'far ultraviolet'),
    'SDSS': ('Sloan Digital Sky Survey (spectra)', 'SDSS', 'visible'),
    'SPITZER_SHA': ('Spitzer', 'NASA', 'infrared'),
    'EUVE': ('EUVE', 'NASA', 'extreme ultraviolet'),
    'HUT': ('Hopkins Ultraviolet Telescope', 'NASA', 'ultraviolet'),
    'WUPPE': ('WUPPE', 'NASA', 'ultraviolet'),
    'BEFS': ('BEFS', 'NASA', 'ultraviolet'),
}
NOT_COUNTED = {'HLA': 'processed Hubble images (already counted as Hubble)', 'HLSP': 'processed products contributed by science teams',
               'ROMAN': 'entries marked as tests in the archive', 'OPO': 'outreach images'}
# HEASARC master table -> (name, who runs it, light, time column)
HEASARC = {
    'chanmaster': ('Chandra X-ray Observatory', 'NASA', 'X-ray', 'time'),
    'xmmmaster': ('XMM-Newton', 'ESA', 'X-ray', 'time'),
    'swiftmastr': ('Swift (X-ray telescope)', 'NASA', 'X-ray', 'start_time'),
    'numaster': ('NuSTAR', 'NASA', 'hard X-ray', 'time'),
    'nicermastr': ('NICER', 'NASA', 'X-ray', 'time'),
}
# Only MAST's own JWST and Hubble preview images may be fetched through this app (no open proxy).
PREVIEW_URI = re.compile(r'^mast:(JWST|HST)/product/[A-Za-z0-9_.\-]+\.(jpg|jpeg|png)$')
LINKS = {
    'mast': 'https://mast.stsci.edu/portal/Mashup/Clients/Mast/Portal.html?searchQuery={ra:.5f}%20{dec:.5f}',
    'heasarc': 'https://heasarc.gsfc.nasa.gov/xamin/',
    'cadc': 'https://www.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/en/search/',
}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers['User-Agent'] = 'PARALLAX (NASA Space Apps 2026 project; https://github.com/a2z-open/NASA)'
    return s


def _tap(url: str, query: str, timeout: float):
    """One synchronous ADQL query; returns an astropy Table."""
    from astropy.io.votable import parse_single_table
    r = _session().post(url, data={'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': 'votable', 'RESPONSEFORMAT': 'votable', 'QUERY': query},
                        timeout=timeout)
    r.raise_for_status()
    return parse_single_table(io.BytesIO(r.content)).to_table()


def _mjd_year(m) -> float | None:
    try:
        m = float(m)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(m) or m <= 0:
        return None
    return round(2000.0 + (m - 51544.5) / 365.25, 2)


def _circle(ra_col: str, dec_col: str, ra: float, dec: float, r_deg: float) -> str:
    return f"CONTAINS(POINT('ICRS', {ra_col}, {dec_col}), CIRCLE('ICRS', {ra:.6f}, {dec:.6f}, {r_deg:.6f}))=1"


def mast(ra: float, dec: float, r_deg: float, timeout: float = 15.0) -> dict:
    where = _circle('s_ra', 's_dec', ra, dec, r_deg)
    tb = _tap(MAST_TAP, f"SELECT obs_collection, COUNT(*) AS n, MIN(t_min) AS t0, MAX(t_min) AS t1 FROM dbo.ObsPointing WHERE {where} "
                        f"GROUP BY obs_collection", timeout)
    rows, skipped = [], []
    for r in tb:
        c = str(r['obs_collection']).strip()
        n = int(r['n'])
        if c in MAST:
            name, agency, light = MAST[c]
            rows.append({'key': c, 'name': name, 'agency': agency, 'light': light, 'archive': 'NASA MAST', 'n': n,
                         'first_year': _mjd_year(r['t0']), 'last_year': _mjd_year(r['t1'])})
        else:
            skipped.append({'collection': c, 'n': n, 'why': NOT_COUNTED.get(c, 'not a telescope we list')})
    def sample(coll: str, label: str) -> list:
        previews = []
        try:
            pv = _tap(MAST_TAP, f"SELECT TOP 4 instrument_name, target_name, t_min, jpegURL FROM dbo.ObsPointing WHERE {where} "
                                f"AND obs_collection='{coll}' AND jpegURL IS NOT NULL AND dataproduct_type='image' ORDER BY t_min DESC",
                      min(timeout, 7.0))
            col = {c.lower(): c for c in pv.colnames}
            for r in pv:
                uri = str(r[col['jpegurl']]).strip()
                if PREVIEW_URI.fullmatch(uri):
                    previews.append({'telescope': label, 'instrument': str(r[col['instrument_name']]).strip(),
                                     'target': str(r[col['target_name']]).strip(), 'year': _mjd_year(r[col['t_min']]),
                                     'url': '/api/telescopes/preview?uri=' + quote(uri, safe='')})
        except Exception:  # Optional previews must not suppress the returned counts.
            pass
        return previews

    previews = []
    collections = {row['key'] for row in rows}
    with ThreadPoolExecutor(max_workers=2) as ex:
        tasks = [ex.submit(sample, coll, label) for coll, label in (('JWST', 'JWST'), ('HST', 'Hubble')) if coll in collections]
        for task in tasks:
            previews.extend(task.result())
    return {'rows': rows, 'skipped': skipped, 'previews': previews}


def heasarc(ra: float, dec: float, r_deg: float, timeout: float = 15.0) -> dict:
    rows = []

    def one(item):
        table, (name, agency, light, tcol) = item
        tb = _tap(HEASARC_TAP, f"SELECT COUNT(*) AS n, MIN({tcol}) AS t0, MAX({tcol}) AS t1 FROM {table} WHERE {_circle('ra', 'dec', ra, dec, r_deg)}",
                  timeout)
        n = int(tb[0]['n']) if len(tb) else 0
        return {'key': table, 'name': name, 'agency': agency, 'light': light, 'archive': 'NASA HEASARC', 'n': n,
                'first_year': _mjd_year(tb[0]['t0']) if n else None, 'last_year': _mjd_year(tb[0]['t1']) if n else None}

    errors = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(one, it): it[0] for it in HEASARC.items()}
        for f, table in futs.items():
            try:
                row = f.result()
                if row['n']:
                    rows.append(row)
            except Exception as error:  # noqa: BLE001
                errors.append(f"{HEASARC[table][0]}: {type(error).__name__}")
    return {'rows': rows, 'errors': errors, 'available': len(errors) < len(HEASARC)}


def neossat(ra: float, dec: float, r_deg: float, timeout: float = 15.0) -> dict:
    q = (f"SELECT COUNT(*) AS n, MIN(p.time_bounds_lower) AS t0, MAX(p.time_bounds_lower) AS t1 FROM caom2.Observation AS o "
         f"JOIN caom2.Plane AS p ON p.obsID = o.obsID WHERE o.collection = 'NEOSSAT' "
         f"AND INTERSECTS(CIRCLE('ICRS', {ra:.6f}, {dec:.6f}, {r_deg:.6f}), p.position_bounds)=1")
    tb = _tap(CADC_TAP, q, timeout)
    n = int(tb[0]['n']) if len(tb) else 0
    rows = [{'key': 'NEOSSAT', 'name': 'NEOSSat', 'agency': 'Canadian Space Agency', 'light': 'visible', 'archive': 'CADC (Canada)', 'n': n,
             'first_year': _mjd_year(tb[0]['t0']), 'last_year': _mjd_year(tb[0]['t1'])}] if n else []
    return {'rows': rows}


def look(ra: float, dec: float, radius_arcmin: float = 3.0, *, refresh: bool = False) -> dict:
    """Every archive at once.  Returns telescopes with counts (largest first), previews, and which archives did not answer."""
    ra, dec, radius_arcmin = float(ra), float(dec), float(radius_arcmin)
    if not all(map(math.isfinite, (ra, dec, radius_arcmin))):
        raise ValueError('coordinates and radius must be finite')
    ra %= 360.0
    if not -90 <= dec <= 90:
        raise ValueError('declination must be between -90 and +90 degrees')
    radius_arcmin = min(max(radius_arcmin, 0.1), 30.0)
    r_deg = radius_arcmin / 60.0
    key = hashlib.sha1(f'{ra:.6f},{dec:.6f},{r_deg:.6f}'.encode()).hexdigest()[:16]
    path = CACHE / f'{key}.json'
    if path.is_file() and not refresh:
        doc = json.loads(path.read_text())
        if (time.time() - doc.get('asked_unix', 0) < CACHE_DAYS * 86400
                and doc.get('coverage') and not doc.get('unanswered')):
            return doc | {'from_cache': True}
    jobs = {'mast': ('NASA MAST', mast), 'heasarc': ('NASA HEASARC', heasarc), 'cadc': ('CADC (NEOSSat)', neossat)}
    rows, previews, skipped, unanswered = [], [], [], []
    coverage = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {key: ex.submit(fn, ra, dec, r_deg) for key, (_, fn) in jobs.items()}
        for key, f in futs.items():
            try:
                got = f.result()
                rows += got['rows']
                previews += got.get('previews', [])
                skipped += got.get('skipped', [])
                errors = got.get('errors', [])
                unanswered += errors
                coverage[key] = 'unavailable' if not got.get('available', True) else 'partial' if errors else 'complete'
            except Exception as error:  # noqa: BLE001
                unanswered.append(f'{jobs[key][0]}: {type(error).__name__}')
                coverage[key] = 'unavailable'
    rows.sort(key=lambda r: -r['n'])
    doc = {'ra': ra, 'dec': dec, 'radius_arcmin': radius_arcmin, 'asked_unix': time.time(), 'seconds': round(time.time() - t0, 1),
           'telescopes': rows, 'n_telescopes': len(rows), 'n_observations': sum(r['n'] for r in rows), 'previews': previews,
           'not_counted': skipped, 'unanswered': unanswered, 'coverage': coverage,
           'links': {k: v.format(ra=ra, dec=dec) for k, v in LINKS.items()},
           'note': ('MAST and HEASARC match pointing centers; CADC matches NEOSSat image footprints. '
                    'The search covers selected collections. Images centered farther away can still cover this spot.')}
    if not unanswered:
        CACHE.mkdir(parents=True, exist_ok=True)
        # If another search writes the same key, readers still see a complete document.
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(mode='w', dir=CACHE, delete=False) as tmp:
            json.dump(doc, tmp)
        Path(tmp.name).replace(path)
    return doc


def preview(uri: str) -> bytes:
    """A JWST or Hubble preview image from MAST, cached on disk.  MAST serves these as downloads that browsers will not show
    inline, so the app passes them on as images."""
    if not PREVIEW_URI.match(uri or ''):
        raise ValueError('not a MAST JWST or Hubble preview image')
    path = CACHE / 'previews' / (hashlib.sha1(uri.encode()).hexdigest()[:20] + '.' + uri.rsplit('.', 1)[-1])
    if path.is_file():
        return path.read_bytes()
    r = _session().get('https://mast.stsci.edu/api/v0.1/Download/file', params={'uri': uri}, timeout=60)
    r.raise_for_status()
    if not (r.content.startswith(b'\xff\xd8\xff') or r.content.startswith(b'\x89PNG')):
        raise ValueError('MAST did not return an image')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return r.content
