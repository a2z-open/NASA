"""IRSA Level 2 discovery and display-only SPHEREx frame preparation."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
import json
from math import isfinite
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from time import monotonic
from urllib.parse import urlsplit
import warnings
from xml.etree import ElementTree as ET

from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import FITSFixedWarning, NoConvergence, WCS
import httpx
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates


IRSA_HOST = 'irsa.ipac.caltech.edu'
SIA_URL = f'https://{IRSA_HOST}/SIA'
COLLECTIONS = ('spherex_dr1', 'spherex_qr3')
LIVE_FOV_DEG = 2 / 60
PIXEL_DEG = 6.15 / 3600
VISIT_GAP_DAYS = 30
BARNARD_CENTER = (269.4463, 4.7685)
# Also refuse a reserve-date cutout near Barnard when a product did not appear
# in the exact-center SIA2 response. Exposures show several degrees of sky.
RESERVE_GUARD_RADIUS_DEG = 0.25
MAX_CUTOUT_BYTES = 12 * 1024 * 1024
DISPLAY_INVALID_FLAGS = {'MISSING_DATA', 'NONFUNC', 'PHANMISS'}


@dataclass(frozen=True)
class SkyPosition:
    ra: float
    dec: float

    @classmethod
    def parse(cls, ra, dec):
        try:
            ra, dec = float(ra), float(dec)
        except (TypeError, ValueError):
            raise ValueError('Enter RA and Dec in decimal degrees.') from None
        if not (isfinite(ra) and isfinite(dec) and 0 <= ra <= 360 and -90 <= dec <= 90):
            raise ValueError('RA must be 0–360° and Dec −90–90°.')
        return cls(round(ra % 360, 8) % 360, round(dec, 8))

    def skycoord(self):
        return SkyCoord(self.ra, self.dec, unit='deg', frame='icrs')


@dataclass(frozen=True)
class Exposure:
    obs_id: str
    detector: str
    release: str
    url: str
    t_min: float
    t_max: float
    ra: float
    dec: float

    @property
    def id(self):
        return f'{self.obs_id}-{self.detector}'

    @property
    def processing_version(self):
        return next((part for part in urlsplit(self.url).path.split('/') if part.startswith('l2b-')), None)


@dataclass(frozen=True)
class DisplayImage:
    pixels: np.ndarray
    mjd_avg: float
    image_shape: tuple[int, int]


class ArchiveUnavailable(Exception):
    """The upstream service failed or returned incomplete metadata."""


class InvalidCutout(ValueError):
    """A cutout could not support display at the query position."""


def decode_discovery(raw, collection):
    """Parse table data from IRSA's default SIA2 VOTable response."""
    try:
        root = ET.fromstring(raw)
        statuses = [node.get('value') for node in root.findall('.//{*}INFO')
                    if node.get('name') == 'QUERY_STATUS']
        if not statuses or any(status != 'OK' for status in statuses):
            raise ArchiveUnavailable(f'IRSA returned an incomplete response for {collection}.')
        table = root.find('.//{*}TABLE')
        if table is None:
            raise ArchiveUnavailable(f'IRSA returned no response table for {collection}.')
        fields = [f.get('name') for f in table.findall('{*}FIELD')]
        rows = [dict(zip(fields, (cell.text for cell in row)))
                for row in table.findall('.//{*}TABLEDATA/{*}TR')]
        result = []
        for row in rows:
            obs_id = row['obs_id']
            url = row['access_url']
            detector = row['energy_bandpassname'].split('-')[-1]
            release = collection.removeprefix('spherex_').upper()
            parsed = urlsplit(url)
            if (parsed.scheme != 'https' or parsed.netloc != IRSA_HOST
                    or not parsed.path.startswith(f'/ibe/data/spherex/{release.lower()}/level2/')
                    or not parsed.path.endswith('.fits') or parsed.query or parsed.fragment
                    or not re.fullmatch(r'[\w-]+', obs_id, flags=re.ASCII)
                    or not re.fullmatch(r'D[1-6]', detector)):
                continue
            times_and_center = [float(row[key]) for key in ('t_min', 't_max', 's_ra', 's_dec')]
            if not all(map(isfinite, times_and_center)):
                continue
            result.append(Exposure(obs_id, detector, release, url, *times_and_center))
        return result
    except (ET.ParseError, KeyError, ValueError, TypeError, AttributeError) as error:
        raise ArchiveUnavailable(f'IRSA returned unreadable metadata for {collection}.') from error


class IrsaArchive:
    def __init__(self, *, transport=None):
        self.client = httpx.Client(timeout=httpx.Timeout(8.0, connect=4.0), transport=transport)

    def close(self):
        self.client.close()

    def search_collection(self, collection, position):
        params = {
            'COLLECTION': collection,
            'POS': f'CIRCLE {position.ra:.8f} {position.dec:.8f} 0.0001',
            'RESPONSEFORMAT': 'VOTABLE',
        }
        try:
            response = self.client.get(SIA_URL, params=params)
            response.raise_for_status()
            return decode_discovery(response.content, collection)
        except httpx.HTTPError as error:
            raise ArchiveUnavailable(f'IRSA discovery failed for {collection}.') from error

    def search(self, position):
        with ThreadPoolExecutor(max_workers=len(COLLECTIONS)) as executor:
            results = executor.map(lambda name: self.search_collection(name, position), COLLECTIONS)
            return [item for collection in results for item in collection]

    def cutout(self, item, position, size):
        params = {'center': f'{position.ra:.7f},{position.dec:.7f}', 'size': f'{size:.7f}'}
        deadline = monotonic() + 12
        for attempt in range(2):
            try:
                timeout = httpx.Timeout(max(0.1, deadline - monotonic()), connect=4.0)
                with self.client.stream('GET', item.url, params=params, timeout=timeout) as response:
                    if attempt == 0 and response.status_code == 503 and monotonic() < deadline:
                        continue
                    response.raise_for_status()
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        if monotonic() > deadline:
                            raise ArchiveUnavailable(f'IRSA cutout deadline exceeded for {item.id}.')
                        data.extend(chunk)
                        if len(data) > MAX_CUTOUT_BYTES:
                            raise InvalidCutout('IRSA response exceeded the cutout size limit.')
                    return bytes(data)
            except httpx.HTTPError as error:
                raise ArchiveUnavailable(f'IRSA cutout unavailable for {item.id}.') from error


def group_visits(exposures):
    """Deduplicate releases and group candidate observations by a 30-day gap."""
    products = {}
    for item in sorted(exposures, key=lambda x: (x.release != 'DR1', x.url), reverse=True):
        products[item.id] = item
    visits = []
    for item in sorted(products.values(), key=lambda x: (x.t_min, x.id)):
        if not visits or item.t_min - visits[-1][-1].t_min > VISIT_GAP_DAYS:
            visits.append([])
        visits[-1].append(item)
    return visits


def choose_frames(visits, position, *, limit, detector=None):
    """Sample across visits first, using exposures whose footprint center is nearer."""
    target = position.skycoord()
    ranked = []
    for index, visit in enumerate(visits, start=1):
        pool = [item for item in visit if detector is None or item.detector == detector]
        if pool:
            sky = SkyCoord([item.ra for item in pool], [item.dec for item in pool], unit='deg')
            order = np.argsort(target.separation(sky).deg, kind='stable')
            ranked.append([(pool[i], f'visit-{index}') for i in order])
    picked = []
    for depth in range(max((len(visit) for visit in ranked), default=0)):
        for visit in ranked:
            if depth < len(visit):
                picked.append(visit[depth])
            if len(picked) == limit:
                return picked
    return picked


def is_reserved(item, position, reservation):
    return reserved_observation(item.obs_id, item.t_min, position, reservation)


def reserved_observation(obs_id, mjd, position, reservation):
    if obs_id in reservation.get('obs_ids', []):
        return True
    if not reservation.get('t_min', float('inf')) <= mjd <= reservation.get('t_max', -1):
        return False
    return near_barnard(position)


def load_reservation(path):
    try:
        reserve = json.loads(path.read_text())['reserve']
        if reserve['obs_ids'] and reserve['t_min'] < reserve['t_max']:
            return reserve
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def near_barnard(position):
    center = SkyPosition(*BARNARD_CENTER).skycoord()
    return position.skycoord().separation(center).deg <= RESERVE_GUARD_RADIUS_DEG


def sky_grid(position, fov_deg):
    """A north-up TAN grid with a fixed crosshair at the input coordinate."""
    width = max(1, int(round(fov_deg / PIXEL_DEG)))
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    wcs.wcs.crval = [position.ra, position.dec]
    wcs.wcs.crpix = [(width + 1) / 2] * 2
    wcs.wcs.cdelt = [-PIXEL_DEG, PIXEL_DEG]
    y, x = np.indices((width, width), dtype=float)
    return wcs.pixel_to_world(x, y)


def decode_fits(raw, position, fov_deg):
    """Project native cutout data onto the common grid, for display only."""
    try:
        with fits.open(BytesIO(raw), memmap=False) as hdul:
            image = hdul['IMAGE']
            pixels = np.asarray(image.data, dtype=float)
            flags = hdul['FLAGS']
            if flags.shape != pixels.shape:
                raise InvalidCutout('Native flag image does not match image dimensions.')
            flag_mask = sum(
                1 << int(key.removeprefix('MSKN'))
                for key, name in flags.header.items()
                if re.fullmatch(r'MSKN\d+', key) and name in DISPLAY_INVALID_FLAGS
            )
            if flag_mask:
                pixels[(flags.data & flag_mask) != 0] = np.nan
            midpoint = float(image.header['MJD-AVG'])
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', FITSFixedWarning)
                native = WCS(image.header).celestial
    except (OSError, KeyError, ValueError, TypeError, IndexError) as error:
        raise InvalidCutout('Missing or invalid native FITS image/WCS.') from error
    if pixels.ndim != 2 or not isfinite(midpoint) or not native.has_celestial:
        raise InvalidCutout('Invalid native image geometry or observation time.')
    try:
        grid = sky_grid(position, fov_deg)
        x, y = native.world_to_pixel(grid)
        registered = map_coordinates(pixels, [y, x], order=1, mode='constant', cval=np.nan)
    except (ValueError, RuntimeError, NoConvergence) as error:
        raise InvalidCutout('Native WCS could not be mapped to the display grid.') from error
    # Require the central pixel and substantial coverage of the common grid.
    center = tuple(side // 2 for side in registered.shape)
    if not np.isfinite(registered[center]) or np.isfinite(registered).mean() < 0.7:
        raise InvalidCutout('The requested field is clipped or blank.')
    return DisplayImage(registered, midpoint, pixels.shape)


def render_frames(images):
    """Apply identical limits and asinh stretch to a sequence of frames."""
    samples = np.concatenate([item.pixels[np.isfinite(item.pixels)] for item in images])
    low, high = np.percentile(samples, [5, 99.7])
    width = max(float(high - low), 1e-10)
    pngs = []
    for item in images:
        normalized = np.clip((item.pixels - low) / width, 0, 1)
        stretched = np.arcsinh(10 * normalized) / np.arcsinh(10)
        gray = np.nan_to_num(stretched, nan=0) * 255
        stream = BytesIO()
        Image.fromarray(np.flipud(gray.astype(np.uint8))).save(stream, format='PNG', optimize=True)
        pngs.append(stream.getvalue())
    return pngs


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as file:
        file.write(data)
    Path(file.name).replace(path)


def write_json(path, data):
    atomic_write(path, (json.dumps(data, indent=2, allow_nan=False) + '\n').encode())


def utc_time(mjd):
    return Time(mjd, format='mjd', scale='utc').isot + 'Z'


def frame_payload(item, visit_id, image, display_url):
    return {
        'id': item.id, 'visit_id': visit_id, 'time_utc': utc_time(image.mjd_avg),
        'detector': item.detector, 'release': item.release,
        'processing_version': item.processing_version,
        'archive_url': item.url, 'display_url': display_url,
        'wavelength_um': None, 'bandwidth_um': None,
    }


MESSAGES = {
    'no_coverage': 'IRSA returned no Level 2 observations at this position.',
    'no_usable_frames': 'IRSA listed observations, but no eligible display cutouts loaded.',
    'archive_unavailable': 'IRSA is currently unavailable. Try a saved target or retry.',
    'one_visit': 'One usable visit. More visits are needed for a time comparison.',
}


def sequence_payload(position, frames, status, source=None):
    return {
        'ra': position.ra,
        'dec': position.dec,
        'status': status,
        'source': source,
        'comparison_status': 'unverified',
        'message': MESSAGES.get(status),
        'frames': frames,
    }


def fetch_display(archive, item, position, size):
    raw = archive.cutout(item, position, size)
    return raw, decode_fits(raw, position, size)


def build_sequence(archive, position, cache, *, reservation):
    key = f'v2-{position.ra:.8f}_{position.dec:.8f}'
    folder = cache / key
    saved = folder / 'sequence.json'
    if saved.is_file():
        result = json.loads(saved.read_text())
        if all((folder / Path(frame['display_url']).name).is_file() for frame in result['frames']):
            # Changing the reserved visit invalidates earlier previews.
            if not any(
                is_reserved(
                    Exposure(
                        frame['id'].rsplit('-', 1)[0], frame['detector'],
                        frame['release'], frame['archive_url'],
                        float(Time(frame['time_utc']).mjd), 0, position.ra, position.dec,
                    ),
                    position,
                    reservation,
                ) for frame in result['frames']
            ):
                result['source'] = 'cache'
                return result
    try:
        exposures = archive.search(position)
    except ArchiveUnavailable:
        return sequence_payload(position, [], 'archive_unavailable')
    if not exposures:
        return sequence_payload(position, [], 'no_coverage')
    visits = group_visits(exposures)
    allowed_visits = [[item for item in v if not is_reserved(item, position, reservation)] for v in visits]
    picked = choose_frames(allowed_visits, position, limit=8)

    def result_for(pair):
        item, visit_id = pair
        try:
            _, image = fetch_display(archive, item, position, LIVE_FOV_DEG)
        except (ArchiveUnavailable, InvalidCutout) as error:
            return error
        return item, visit_id, image

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(result_for, picked))
    accepted = sorted((x for x in results if not isinstance(x, Exception)), key=lambda x: x[2].mjd_avg)
    if not accepted:
        status = ('archive_unavailable' if results and all(isinstance(x, ArchiveUnavailable) for x in results)
                  else 'no_usable_frames')
        return sequence_payload(position, [], status)
    frames = []
    pngs = render_frames([image for _, _, image in accepted])
    for (item, visit, image), png in zip(accepted, pngs):
        file = f'{item.id}.png'
        atomic_write(folder / file, png)
        frames.append(frame_payload(item, visit, image, f'/frames/{key}/{file}'))
    status = 'ready' if len({x['visit_id'] for x in frames}) > 1 else 'one_visit'
    result = sequence_payload(position, frames, status, 'archive')
    write_json(saved, result)
    return result
