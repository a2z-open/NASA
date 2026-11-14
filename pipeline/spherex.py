"""SPHEREx archive access (IRSA SIA2 + cutouts), FITS loading and quality flags.

Release-aware: collections are configured in RELEASES, so a future release can
be added without code changes elsewhere.  Every downloaded cutout is stored
with its SHA-256, retrieval URL and retrieval time (see `Provenance`).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import threading
import time
import warnings

import numpy as np
import requests
from astropy.io import fits
from astropy.io.votable import parse_single_table
from astropy.wcs import WCS, FITSFixedWarning
from astropy import log as _astropy_log

# SPHEREx headers carry SIP coefficients without a '-SIP' CTYPE suffix; astropy applies them (as intended) and
# logs an INFO message for every WCS it builds.  Silence that one known, expected message.
_astropy_log.setLevel('WARNING')

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.parallax-cache'
SIA_URL = 'https://irsa.ipac.caltech.edu/SIA'
IRSA_HOST = 'irsa.ipac.caltech.edu'

# Release configuration.  QR2 is no longer searchable through SIA2 and is not used.
RELEASES = {
    'spherex_dr1': {
        'release': 'DR1', 'doi': '10.26131/IRSA678',
        'citation': 'SPHEREx Science Team (2026). SPHEREx Data Release 1 Spectral Images. NASA/IPAC Infrared Science Archive. https://doi.org/10.26131/IRSA678',
    },
    'spherex_qr3': {
        'release': 'QR3', 'doi': None,
        'citation': 'SPHEREx Quick Release 3 Spectral Images, NASA/IPAC Infrared Science Archive (IRSA), retrieved via the spherex_qr3 SIA2 collection. Cite per IRSA SPHEREx data-release guidance.',
    },
}
COLLECTIONS = tuple(RELEASES)
VISIT_GAP_DAYS = 30.0
PIXEL_ARCSEC = 6.15
SR_PER_ARCSEC2 = (math.pi / 180 / 3600) ** 2
USER_AGENT = 'PARALLAX-SpaceApps-2026/0.2 (research prototype; python-requests)'

# Detector wavelength ranges (micrometres) from the SPHEREx instrument description.
DETECTOR_RANGES = {1: (0.75, 1.09), 2: (1.10, 1.62), 3: (1.63, 2.41), 4: (2.42, 3.82), 5: (3.83, 4.41), 6: (4.42, 5.00)}

# ---------------------------------------------------------------------------
# Quality flags.  Bit names are always read from the MSKN* cards of each file.
# ---------------------------------------------------------------------------
HARD_FLAGS = {'OVERFLOW', 'SUR_ERROR', 'NONFUNC', 'MISSING_DATA', 'HOT', 'COLD', 'NONLINEAR', 'PERSIST'}
# OUTLIER is *not* hard-masked in the flagged-candidate path: SPHEREx can set it
# on genuine moving sources.  The strict path does exclude it.
STRICT_EXTRA = {'OUTLIER', 'TRANSIENT'}
WARNING_FLAGS = {'DICHROIC', 'PHANMISS', 'CROSSTALK', 'GHOST', 'GHOST_FPA', 'GHOST_EXT', 'STREAK', 'BLOOM', 'SNOWBALL', 'HALO'}
INFORMATIONAL_FLAGS = {'SOURCE', 'FULLSAMPLE'}


def flag_names(header) -> dict[int, str]:
    out = {}
    for key, value in header.items():
        m = re.fullmatch(r'MSKN(\d+)', key)
        if m:
            out[int(m.group(1))] = str(value).strip()
    return out


def flag_mask(names: dict[int, str], wanted: set[str]) -> int:
    return sum(1 << bit for bit, name in names.items() if name in wanted)


def decode_flags(value: int, names: dict[int, str]) -> list[str]:
    return [name for bit, name in sorted(names.items()) if value & (1 << bit)]


# ---------------------------------------------------------------------------
# Archive discovery
# ---------------------------------------------------------------------------

class ArchiveUnavailable(RuntimeError):
    pass


@dataclass
class Product:
    """One SPHEREx Level-2 spectral image (one exposure on one detector)."""
    obs_id: str
    detector: int
    collection: str
    release: str
    access_url: str
    t_min: float
    t_max: float
    s_ra: float
    s_dec: float
    em_min_um: float | None
    em_max_um: float | None
    publisher_did: str | None = None
    cloud_access: str | None = None

    @property
    def id(self) -> str:
        return f'{self.obs_id}-D{self.detector}'

    @property
    def processing_version(self) -> str | None:
        return next((p for p in self.access_url.split('/') if p.startswith('l2b-')), None)

    @property
    def t_mid(self) -> float:
        return 0.5 * (self.t_min + self.t_max)

    def to_dict(self):
        d = asdict(self)
        d['id'] = self.id
        d['processing_version'] = self.processing_version
        return d


_session_lock = threading.Lock()
_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    with _session_lock:
        if _session is None:
            s = requests.Session()
            s.headers['User-Agent'] = USER_AGENT
            adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=8)
            s.mount('https://', adapter)
            _session = s
        return _session


def _get(url, params=None, *, timeout=60, retries=3, stream=False):
    last = None
    for attempt in range(retries):
        try:
            r = session().get(url, params=params, timeout=timeout, stream=stream)
            if r.status_code in (429, 500, 502, 503, 504):
                last = ArchiveUnavailable(f'HTTP {r.status_code} from {url}')
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as error:
            last = error
            time.sleep(1.5 * (attempt + 1))
    raise ArchiveUnavailable(f'Archive request failed: {url} ({last})')


def parse_sia(raw: bytes, collection: str) -> list[Product]:
    table = parse_single_table(io.BytesIO(raw)).to_table(use_names_over_ids=True)
    release = RELEASES.get(collection, {}).get('release', collection.removeprefix('spherex_').upper())
    out = []
    for row in table:
        try:
            url = str(row['access_url'])
            band = str(row['energy_bandpassname'])
            m = re.search(r'D([1-6])$', band)
            if not m or IRSA_HOST not in url or not url.endswith('.fits'):
                continue
            em_min = float(row['em_min']) * 1e6 if 'em_min' in table.colnames and not np.ma.is_masked(row['em_min']) else None
            em_max = float(row['em_max']) * 1e6 if 'em_max' in table.colnames and not np.ma.is_masked(row['em_max']) else None
            vals = [float(row[k]) for k in ('t_min', 't_max', 's_ra', 's_dec')]
            if not all(math.isfinite(v) for v in vals):
                continue
            out.append(Product(
                obs_id=str(row['obs_id']), detector=int(m.group(1)), collection=collection, release=release,
                access_url=url, t_min=vals[0], t_max=vals[1], s_ra=vals[2], s_dec=vals[3],
                em_min_um=em_min, em_max_um=em_max,
                publisher_did=str(row['obs_publisher_did']) if 'obs_publisher_did' in table.colnames else None,
                cloud_access=str(row['cloud_access']) if 'cloud_access' in table.colnames else None,
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def search(ra: float, dec: float, *, radius_deg: float = 0.0003, collections=COLLECTIONS) -> list[Product]:
    """Query each configured SIA2 collection for images containing (ra, dec)."""
    def one(collection):
        r = _get(SIA_URL, params={'COLLECTION': collection, 'POS': f'CIRCLE {ra:.7f} {dec:.7f} {radius_deg}',
                                  'RESPONSEFORMAT': 'VOTABLE'}, timeout=45)
        return parse_sia(r.content, collection)
    with ThreadPoolExecutor(max_workers=len(collections)) as ex:
        results = list(ex.map(one, collections))
    return dedupe([p for rs in results for p in rs])


def dedupe(products: list[Product]) -> list[Product]:
    """Keep one product per (obs_id, detector): prefer DR1 over QR3, then newest processing."""
    rank = {'DR1': 0, 'QR3': 1}
    best: dict[str, Product] = {}
    for p in products:
        key = p.id
        cur = best.get(key)
        if cur is None or (rank.get(p.release, 9), -_version_num(p)) < (rank.get(cur.release, 9), -_version_num(cur)):
            best[key] = p
    return sorted(best.values(), key=lambda p: (p.t_min, p.id))


def _version_num(p: Product) -> int:
    v = p.processing_version or ''
    m = re.search(r'(\d{4})-(\d{3})$', v)
    return int(m.group(1) + m.group(2)) if m else 0


def group_visits(products: list[Product], gap_days: float = VISIT_GAP_DAYS) -> list[list[Product]]:
    visits: list[list[Product]] = []
    for p in sorted(products, key=lambda p: (p.t_min, p.id)):
        if not visits or p.t_min - visits[-1][-1].t_min > gap_days:
            visits.append([])
        visits[-1].append(p)
    return visits


# ---------------------------------------------------------------------------
# Cutouts and provenance
# ---------------------------------------------------------------------------

@dataclass
class Provenance:
    product_id: str
    obs_id: str
    detector: int
    release: str
    collection: str
    doi: str | None
    archive_url: str
    cutout_url: str
    center_ra: float
    center_dec: float
    size_arcmin: float
    sha256: str
    bytes: int
    retrieved_utc: str
    processing_version: str | None
    path: str


def cutout_url(p: Product, ra: float, dec: float, size_arcmin: float) -> str:
    return f'{p.access_url}?center={ra:.7f},{dec:.7f}&size={size_arcmin:.4f}arcmin'


def field_key(ra: float, dec: float, size_arcmin: float) -> str:
    return f'f{ra:09.5f}_{dec:+09.5f}_{size_arcmin:04.1f}'.replace('+', 'p').replace('-', 'm')


def validate_fits(raw: bytes) -> None:
    with fits.open(io.BytesIO(raw), memmap=False) as h:
        names = [x.name for x in h]
        for need in ('IMAGE', 'FLAGS', 'VARIANCE'):
            if need not in names:
                raise ValueError(f'cutout lacks {need} extension')
        im = h['IMAGE']
        if im.data is None or im.data.ndim != 2 or min(im.data.shape) < 5:
            raise ValueError('cutout image is empty or too small')
        if h['FLAGS'].data.shape != im.data.shape or h['VARIANCE'].data.shape != im.data.shape:
            raise ValueError('cutout extensions have mismatched shapes')
        if not math.isfinite(float(im.header['MJD-AVG'])):
            raise ValueError('cutout lacks a valid MJD-AVG')


def fetch_cutout(p: Product, ra: float, dec: float, size_arcmin: float, folder: Path) -> Provenance:
    """Download (or reuse) one cutout. Returns its provenance record."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{p.id}.fits'
    meta_path = folder / f'{p.id}.prov.json'
    if path.is_file() and meta_path.is_file():
        return Provenance(**json.loads(meta_path.read_text()))
    url = cutout_url(p, ra, dec, size_arcmin)
    r = _get(url, timeout=90, retries=3)
    raw = r.content
    if len(raw) > 40 * 1024 * 1024:
        raise ValueError('cutout response unexpectedly large')
    validate_fits(raw)
    tmp = path.with_suffix('.part')
    tmp.write_bytes(raw)
    tmp.replace(path)
    prov = Provenance(
        product_id=p.id, obs_id=p.obs_id, detector=p.detector, release=p.release, collection=p.collection,
        doi=RELEASES.get(p.collection, {}).get('doi'), archive_url=p.access_url, cutout_url=url,
        center_ra=ra, center_dec=dec, size_arcmin=size_arcmin, sha256=hashlib.sha256(raw).hexdigest(),
        bytes=len(raw), retrieved_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        processing_version=p.processing_version, path=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
    )
    meta_path.write_text(json.dumps(asdict(prov), indent=1))
    return prov


def fetch_many(products, ra, dec, size_arcmin, folder, *, workers=5, progress=None):
    """Bounded-concurrency download. Returns (provenances, failures)."""
    done, failures = [], []
    lock = threading.Lock()

    def one(p):
        try:
            prov = fetch_cutout(p, ra, dec, size_arcmin, folder)
            with lock:
                done.append(prov)
        except Exception as error:  # noqa: BLE001 - record and continue
            with lock:
                failures.append({'product_id': p.id, 'error': str(error)[:300]})
        if progress:
            progress(len(done) + len(failures), len(products))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, products))
    return done, failures


# ---------------------------------------------------------------------------
# FITS loading
# ---------------------------------------------------------------------------

@dataclass
class EpsfZone:
    xcenter: float      # parent-detector pixel coordinates (zero-based)
    ycenter: float
    data: np.ndarray    # oversampled ePSF
    oversample: int


@dataclass
class Observation:
    product_id: str
    obs_id: str
    detector: int
    release: str
    mjd: float
    mjd_beg: float
    mjd_end: float
    image: np.ndarray        # MJy/sr, zodi NOT subtracted
    variance: np.ndarray     # (MJy/sr)^2
    flags: np.ndarray
    flag_names: dict[int, str]
    wcs: WCS                 # celestial (with SIP)
    wave: np.ndarray         # per-pixel central wavelength (um) from the spectral WCS (key W)
    band: np.ndarray         # per-pixel bandwidth (um)
    omega_arcsec2: float     # OMEGA_MEDIAN pixel solid angle
    psf_fwhm_arcsec: float | None
    crpix_parent: tuple[float, float]   # CRPIX1A, CRPIX2A
    epsf: list[EpsfZone] = field(default_factory=list)
    path: str = ''
    meta: dict = field(default_factory=dict)

    @property
    def shape(self):
        return self.image.shape

    def hard_mask(self, strict=False) -> np.ndarray:
        wanted = HARD_FLAGS | (STRICT_EXTRA if strict else set())
        m = flag_mask(self.flag_names, wanted)
        bad = (self.flags & m) != 0
        return bad | ~np.isfinite(self.image) | ~np.isfinite(self.variance) | (self.variance <= 0)

    def flags_near(self, x: float, y: float, radius: float = 1.5) -> list[str]:
        yy, xx = np.indices(self.shape)
        sel = (xx - x) ** 2 + (yy - y) ** 2 <= radius ** 2
        if not sel.any():
            return ['OFF_IMAGE']
        value = int(np.bitwise_or.reduce(self.flags[sel].astype(np.int64)))
        return decode_flags(value, self.flag_names)

    def wavelength_at(self, x: float, y: float) -> tuple[float, float]:
        xi = int(np.clip(round(x), 0, self.shape[1] - 1))
        yi = int(np.clip(round(y), 0, self.shape[0] - 1))
        return float(self.wave[yi, xi]), float(self.band[yi, xi])

    def epsf_at(self, x: float, y: float) -> EpsfZone | None:
        if not self.epsf:
            return None
        px = x + 1 - self.crpix_parent[0]
        py = y + 1 - self.crpix_parent[1]
        return min(self.epsf, key=lambda z: (z.xcenter - px) ** 2 + (z.ycenter - py) ** 2)

    @property
    def ujy_per_unit(self) -> float:
        """Multiply a pixel sum in MJy/sr by this to obtain microjansky."""
        return self.omega_arcsec2 * SR_PER_ARCSEC2 * 1e12


def _quiet_wcs(*args, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return WCS(*args, **kwargs)


def load_observation(path: str | Path, *, keep_epsf_zones: int = 4) -> Observation:
    path = Path(path)
    with fits.open(path, memmap=False) as h:
        im = h['IMAGE']
        hd = im.header
        image = np.asarray(im.data, dtype=np.float64)
        variance = np.asarray(h['VARIANCE'].data, dtype=np.float64)
        flags = np.asarray(h['FLAGS'].data, dtype=np.int64)
        names = flag_names(h['FLAGS'].header)
        cel = _quiet_wcs(hd).celestial
        ny, nx = image.shape
        # Per-pixel wavelength from the spectral WCS lookup table (WAVE-TAB, key W).
        try:
            sw = _quiet_wcs(hd, fobj=h, key='W')
            sw.sip = None
            yy, xx = np.indices((ny, nx), dtype=float)
            lam, bw = sw.pixel_to_world_values(xx.ravel(), yy.ravel())
            wave = np.asarray(lam, dtype=float).reshape(ny, nx)
            band = np.asarray(bw, dtype=float).reshape(ny, nx)
        except Exception:  # noqa: BLE001
            wave = np.full((ny, nx), np.nan)
            band = np.full((ny, nx), np.nan)
        crpix = (float(hd.get('CRPIX1A', 1.0)), float(hd.get('CRPIX2A', 1.0)))
        zones = []
        if 'EPSF' in h and keep_epsf_zones:
            t = h['EPSF'].data
            ov = int(h['EPSF'].header.get('OVSMPX', 5))
            cx = 0.5 * (nx - 1) + 1 - crpix[0]
            cy = 0.5 * (ny - 1) + 1 - crpix[1]
            d = np.hypot(t['XCENTER'] - cx, t['YCENTER'] - cy)
            for i in np.argsort(d)[:keep_epsf_zones]:
                arr = np.asarray(t['EPSF'][i], dtype=float).reshape(33, 33)
                zones.append(EpsfZone(float(t['XCENTER'][i]), float(t['YCENTER'][i]), arr, ov))
        obs = Observation(
            product_id=f"{hd.get('OBSID', path.stem.rsplit('-', 1)[0])}-D{int(hd.get('DETECTOR', 0))}",
            obs_id=str(hd.get('OBSID', '')), detector=int(hd.get('DETECTOR', 0)),
            release='', mjd=float(hd['MJD-AVG']), mjd_beg=float(hd.get('MJD-BEG', hd['MJD-AVG'])),
            mjd_end=float(hd.get('MJD-END', hd['MJD-AVG'])),
            image=image, variance=variance, flags=flags, flag_names=names, wcs=cel, wave=wave, band=band,
            omega_arcsec2=float(hd.get('OMEGA_MEDIAN', PIXEL_ARCSEC ** 2)),
            psf_fwhm_arcsec=float(hd['PSF_FWHM']) if 'PSF_FWHM' in hd else None,
            crpix_parent=crpix, epsf=zones, path=str(path),
            meta={'BUNIT': hd.get('BUNIT'), 'DATE-OBS': hd.get('DATE-OBS')},
        )
    prov_path = path.with_suffix('.prov.json')
    if prov_path.is_file():
        prov = json.loads(prov_path.read_text())
        obs.release = prov.get('release', '')
        obs.meta['provenance'] = prov
    return obs
