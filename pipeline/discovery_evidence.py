"""Attach bounded historical evidence by exact MPC observation identity."""

from hashlib import file_digest, sha256
from io import BytesIO
import json
from math import hypot
import os
from pathlib import Path
import subprocess
import sys
import warnings

import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.io.fits.verify import VerifyWarning
from astropy.wcs import FITSFixedWarning, WCS
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import map_coordinates

from .archive import atomic_write


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_PACKET = WORKSPACE / 'discovery-runs/2026-11-14/expansion'
PACKET_ENV = 'PARALLAX_DISCOVERY_EVIDENCE_DIR'
WEST = 'asteroids-west'
G96_ARCHIVE = 'https://sbnarchive.psi.edu/pds4/surveys/gbo.ast.catalina.survey/data_calibrated/G96/2026/'
MPC_WAMO = 'https://data.minorplanetcenter.net/api/wamo'
PINS = {
    f'{WEST}/NW004/candidate-orbit.json': '921ec45a757f1daeea4f8ba02bc98afc4d2e1940853bf6c647986bb750506c06',
    f'{WEST}/NW004/decision.json': '36876f115709e0e808ed61e4c523e0ffb92da9c141011dc12419da69fab1eb2b',
    f'{WEST}/NW004/comet-88P-check.json': '4091460b6380a97a6ad8e37826e41900dc8a25f404c4b16a23f4fe3c8a29e79b',
    f'{WEST}/NW034/candidate-orbit.json': '47285b648b6061ebf21d1d5f7c2c7b733c54813f234715ba9e5c7cf4c2ee81d1',
    f'{WEST}/NW034/candidate-extended-orbit.json': 'a06fa7b62630ce60908a42956891184df40b72c69fa916c33729ee31737ec7f3',
    f'{WEST}/NW034/catalog-crossmatch.json': '5bc7d9370447f8d884bf3fba004022fc7323aa90ff78255c279404e096b0317c',
    f'{WEST}/NW034/extended-wamo.json': '5324e97dfc14c1a6539ef4682c9bb3e2cba9afbfd48d63e8840085246818cb2a',
    f'{WEST}/NW034/pixels/pixel-remeasurement-results.json': '87bb46e9a964503d6c49bee9402e87d17fcd185a1c11621b51e2cbc90d795245',
    f'{WEST}/NW034/pixels/G96-Nov13-calibrated-index.html': '80c3fe2ae1062abf56456f52518bd670f9ec3917b7f85e152b347ac6b6faf880',
    'independent-review/review.json': 'c9d504939325a10603f9e8627595239a251abe98f150e4638c8d9a17e39e3a9d',
}


def _pinned(path, digest, expected_bytes=None):
    try:
        with path.open('rb') as stream:
            if expected_bytes is not None and os.fstat(stream.fileno()).st_size != expected_bytes:
                return False
            return file_digest(stream, 'sha256').hexdigest() == digest
    except OSError:
        return False


def _receipt(root, name):
    try:
        body = (root / name).read_bytes()
    except OSError:
        return None
    return json.loads(body) if sha256(body).hexdigest() == PINS[name] else None


def _observations(packet):
    return {row['line_sha256']: row for row in (packet or {}).get('observations', [])
            if sha256(row['obs80'].encode('ascii')).hexdigest() == row['line_sha256']}


def _matched(rows, trusted):
    matched = {}
    for row in rows:
        digest = row.get('line_sha256')
        reference = trusted.get(digest)
        if (reference and row.get('station') == reference['station'] and row.get('night') == reference['night']
                and abs(row['mjd_utc'] - reference['mjd_utc']) <= 2e-7
                and abs(row['ra_deg'] - reference['ra_deg']) <= 1e-6
                and abs(row['dec_deg'] - reference['dec_deg']) <= 1e-6):
            matched[digest] = row
    return matched


def _comet(root, trusted):
    decision = _receipt(root, f'{WEST}/NW004/decision.json')
    check = _receipt(root, f'{WEST}/NW004/comet-88P-check.json')
    if not decision or not check or check['compared'] != decision['count'] or check['command'] != 'DES=88P;CAP;':
        return {}
    matches = {}
    for entry in check['by_station']:
        station, receipt = entry['station'], entry['receipt']
        raw = root / WEST / 'NW004' / 'catalog-raw' / f'horizons-DES_88P_CAP_-{station}.txt'
        if receipt['http_status'] != 200 or not _pinned(raw, receipt['response_sha256']):
            continue
        for residual in entry['errors']:
            digest = residual['line_sha256']
            row = trusted.get(digest)
            if (row and row['station'] == station and abs(row['mjd_utc'] - residual['mjd_utc']) <= 2e-7
                    and residual['time_error_s'] < .01 and residual['separation_arcsec'] <= 2):
                matches[digest] = {'line_sha256': digest, 'night': row['night'], 'station': station,
                                   'separation_arcsec': residual['separation_arcsec'],
                                   'source_url': receipt['url'], 'receipt_sha256': receipt['response_sha256']}
    return matches if len(matches) <= decision['within_2arcsec'] else {}


def _catalog(root, candidates, parent_rows, extended_rows):
    comet_rows = _observations(_receipt(root, f'{WEST}/NW004/candidate-orbit.json'))
    comet = _comet(root, comet_rows)
    catalog = _receipt(root, f'{WEST}/NW034/catalog-crossmatch.json')
    wamo = _receipt(root, f'{WEST}/NW034/extended-wamo.json')
    review = _receipt(root, 'independent-review/review.json')
    extended_rows = extended_rows if wamo and review and catalog else {}
    parent_rows = parent_rows if catalog else {}

    for candidate in candidates:
        rows = candidate['observations']
        total = len(rows)
        overlap = _matched(rows, comet_rows)
        precise = [comet[key] for key in overlap if key in comet]
        nights = {row['night'] for row in precise}
        if precise:
            strong = len(precise) >= 3 and len(nights) >= 2
            known = strong and len(precise) == total
            blend = strong and len(precise) * 2 > total and len(overlap) == total and len(comet) == 19
            status = 'known_object' if known else ('known_contamination' if blend else 'partial_match')
            candidate['catalog'] = {
                'status': status, 'name': '88P/Howell', 'source': 'Archived JPL Horizons topocentric ephemerides',
                'source_url': precise[0]['source_url'], 'checked_on': '2026-11-14',
                'match_radius_arcsec': 2, 'matches': precise, 'matched_observations': len(precise),
                'matched_nights': len(nights), 'total_observations': total,
                'unmatched_observations': total - len(precise), 'exclude_from_novel_review': known or blend,
                'message': ('All candidate observations match within 2 arcsec.' if known else
                            'Only the listed observations match; unmatched rows remain unresolved.'),
            }
            if known or blend:
                candidate.update(display_label='88P/Howell' if known else '88P/Howell with unmatched observations',
                                 benchmark_label='NW004')
        elif total and (len(_matched(rows, extended_rows)) == total == len(extended_rows)
                        or len(_matched(rows, parent_rows)) == total == len(parent_rows)):
            candidate.update(display_label='NW034', benchmark_label='NW034')
            candidate['catalog'] = {
                'status': 'no_match_in_checked_catalogs', 'source': 'Archived MPC WAMO, IMCCE SkyBoT and JPL Horizons',
                'source_url': MPC_WAMO, 'checked_on': '2026-11-14', 'total_observations': total,
                'exclude_from_novel_review': False,
                'scope': 'Bounded sky searches and nominated known orbits; unpublished links and catalog gaps remain possible.',
                'message': 'No tested catalog alternative matched these observations in the archived checks.',
            }
        else:
            candidate['catalog'] = {'status': 'unverified', 'exclude_from_novel_review': False,
                                    'message': 'No observation-matched catalog check is available for this linkage.'}


_REDUCER = '''
import json
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from pipeline.itf_catalina_pixels import measure
root = Path(sys.argv[2])
results = {}
for frame in json.load(sys.stdin):
    try:
        results[frame['id']] = measure(root / (frame['id'] + '.arch.fz'), frame, controls=True)
    except (OSError, ValueError, KeyError, IndexError):
        pass
print(json.dumps(results, allow_nan=False))
'''


def _remeasure(folder, records):
    # Isolate the earlier checkout; both repositories have a top-level pipeline package.
    legacy = WORKSPACE / 'parallax-event'
    if not (legacy / 'pipeline/itf_catalina_pixels.py').is_file():
        return {row['id']: row['measure'] for row in records}, 'archived_measurement'
    try:
        process = subprocess.run([sys.executable, '-IB', '-c', _REDUCER, str(legacy), str(folder)],
                                 input=json.dumps(records), capture_output=True, text=True, timeout=30, check=True)
        return json.loads(process.stdout), 'remeasured_original_fits'
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}, 'unavailable'


def _blink_frame(path, output, record, measure, origin, extent=18, width=241):
    # Map the same north-up, east-left sky grid onto each detector, independent of centroids.
    east, north = np.meshgrid(np.linspace(extent, -extent, width), np.linspace(extent, -extent, width))
    sky = origin.spherical_offsets_by(east * u.arcsec, north * u.arcsec)
    with warnings.catch_warnings(), fits.open(path) as hdus:
        warnings.simplefilter('ignore', FITSFixedWarning)
        warnings.simplefilter('ignore', VerifyWarning)
        hdu = hdus[1]
        x, y = WCS(hdu.header).world_to_pixel_values(sky.ra.deg, sky.dec.deg)
        x0, y0 = int(np.floor(x.min())) - 1, int(np.floor(y.min())) - 1
        x1, y1 = int(np.ceil(x.max())) + 2, int(np.ceil(y.max())) + 2
        if not (0 <= x0 < x1 <= hdu.shape[1] and 0 <= y0 < y1 <= hdu.shape[0]):
            raise ValueError('Display grid outside calibrated detector.')
        pixels = hdu.section[y0:y1, x0:x1].astype(float)
        pixels[(pixels <= 0) | (pixels >= hdu.header['SATURATE'] * .98)] = np.nan
    sky_level = np.nanmedian(pixels)
    sigma = 1.4826 * np.nanmedian(abs(pixels - sky_level))
    if not np.isfinite(sigma) or sigma <= 0:
        raise ValueError('Display grid has no measurable background.')
    display = map_coordinates((pixels - sky_level) / sigma, [y - y0, x - x0], order=1)
    display = np.clip((np.nan_to_num(display, nan=-1.7) + 1.7) / 6.2, 0, 1)
    image = Image.fromarray(np.uint8(display * 255)).convert('RGB')
    offsets = origin.spherical_offsets_to(SkyCoord(*measure['fitted_deg'], unit='deg'))
    scale = (width - 1) / (2 * extent)
    cx, cy = ((extent - angle.arcsec) * scale for angle in offsets)
    radius = 2.5 * scale
    ImageDraw.Draw(image).ellipse((cx-radius, cy-radius, cx+radius, cy+radius), outline='#51d7ec', width=2)
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    body = buffer.getvalue()
    file = f'nw034-{record["id"]}.png'
    atomic_write(output / file, body)
    measured = SkyCoord(*measure['fitted_deg'], unit='deg')
    mpc_point = SkyCoord(*record['mpc_point_deg'], unit='deg')
    return {
        'file': file, 'epoch': record['utc_midpoint'] + 'Z', 'station': record['station'],
        'source_url': record['pds_pixel_url'], 'label_url': record['original_label_url'],
        'line_sha256': record['mpc_observation_sha256'], 'source_sha256': record['sha256'],
        'display_sha256': sha256(body).hexdigest(),
        'forced_snr': measure['forced_snr'], 'centroid_snr': measure['fitted_snr'],
        'centroid_minus_mpc_arcsec': measured.separation(mpc_point).arcsec,
        'viewport_center_deg': [origin.ra.deg, origin.dec.deg], 'viewport_arcsec': extent * 2,
        'centroid_pixel_xy': [round(cx, 2), round(cy, 2)],
    }


def _image_summary(records, measures):
    first, last = records[0], records[-1]
    fits = [SkyCoord(*measures[row['id']]['fitted_deg'], unit='deg') for row in records]
    catalogue = [SkyCoord(*row['mpc_point_deg'], unit='deg') for row in (first, last)]
    motion = fits[0].spherical_offsets_to(fits[-1])
    expected = catalogue[0].spherical_offsets_to(catalogue[-1])
    displacement = fits[0].separation(fits[-1]).arcsec
    mismatch = hypot(*(a.arcsec - b.arcsec for a, b in zip(motion, expected, strict=True)))
    values = [measures[row['id']] for row in records]
    weights = 1 / np.array([row['error_relative_to_zero_mag'] for row in values])
    weights /= np.linalg.norm(weights)
    combined = float(weights @ [row['forced_snr'] for row in values])
    controls = [row['off_track_snr'] for row in values]
    shared = set.intersection(*(set(control) for control in controls))
    best = max((float(weights @ [row[key] for row in controls]) for key in shared), default=None)
    confirmed = (len(records) == 4 and all(row['forced_snr'] >= 3 for row in values)
                 and len(shared) >= 8 and combined >= 5 and combined > best
                 and displacement >= 3 and mismatch <= 2)
    return confirmed, {'combined_snr': combined, 'strongest_positive_control_snr': best,
                       'control_count': len(shared), 'motion_arcsec': displacement,
                       'motion_disagreement_arcsec': mismatch}


def _pixels(root, output, candidates, trusted, allow):
    for candidate in candidates:
        candidate['images'] = {
            'status': 'unverified' if allow else 'disabled', 'frames': [], 'coverage': [], 'expected_frames': 0,
            'message': 'No observation-matched images were checked.' if allow else 'Image check was disabled for this run.',
        }
    if not allow or not trusted:
        return
    pixel_dir = f'{WEST}/NW034/pixels'
    folder = root / pixel_dir
    records = _receipt(root, f'{pixel_dir}/pixel-remeasurement-results.json') or []
    overlaps = [_matched(candidate['observations'], trusted) for candidate in candidates]
    needed = set().union(*overlaps)
    coverage_receipt = f'{pixel_dir}/G96-Nov13-calibrated-index.html'
    archived_404 = _pinned(root / coverage_receipt, PINS[coverage_receipt])
    archived = [row for row in records if row['mpc_observation_sha256'] in needed]
    good = []
    for row in archived:
        image_path = folder / (row['id'] + '.arch.fz')
        label_path = folder / (row['id'] + '.fits.xml')
        if (row['bytes'] == int(row['head_headers']['content-length'])
                and _pinned(label_path, row['label_sha256'])
                and _pinned(image_path, row['sha256'], row['bytes'])):
            good.append(row)

    frames, measures, measurement_origin = {}, {}, None
    if good:
        measures, measurement_origin = _remeasure(folder, good)
        origin = SkyCoord(*np.mean([row['forecast_deg'] for row in records], axis=0), unit='deg')
        for row in good:
            measure = measures.get(row['id'])
            if not measure or 'fitted_deg' not in measure:
                continue
            try:
                digest = row['mpc_observation_sha256']
                frames[digest] = _blink_frame(folder / (row['id'] + '.arch.fz'), output, row, measure, origin)
            except (OSError, ValueError, KeyError, IndexError):
                continue

    for candidate, overlap in zip(candidates, overlaps, strict=True):
        images = candidate['images']
        if archived_404 and any(row['night'] == '2026-11-13' and row['station'] == 'G96' for row in overlap.values()):
            images['coverage'].append({
                'night': '2026-11-13', 'station': 'G96', 'status': 'archive_not_available',
                'http_status': 404, 'source_url': G96_ARCHIVE + '26Nov13/',
                'message': 'The archived Catalina listing was unavailable for this night; no pixel nondetection was measured.',
            })
        applicable = [row for row in archived if row['mpc_observation_sha256'] in overlap]
        images['expected_frames'] = len(applicable)
        scored = [row for row in applicable if row['mpc_observation_sha256'] in frames]
        if applicable and not scored:
            images['message'] = 'Matching exposures exist in the historical receipt, but the calibrated files could not be verified and displayed.'
        if not scored:
            continue
        confirmed, metrics = _image_summary(scored, measures) if len(scored) >= 2 else (False, {})
        status = 'verified_same_exposure' if confirmed and measurement_origin == 'remeasured_original_fits' else (
            'archived_same_exposure' if confirmed else 'partial')
        images.update(status=status, measurement_origin=measurement_origin,
                      source='Catalina Sky Survey · NASA PDS', source_url=G96_ARCHIVE + '26Nov04/',
                      frames=[frames[row['mpc_observation_sha256']] for row in scored],
                      message='Original Catalina exposures verify existing November 4 astrometry only; they do not add an independent night.'
                      if confirmed else 'Matching Catalina cutouts are available, but this result does not establish the full four-exposure motion check.',
                      scope='same_exposures_only', **metrics)


def attach_evidence(result: dict, output: Path, *, allow_pixels: bool = True,
                    order: tuple[str, str] = ('catalog', 'pixels')) -> None:
    """Run both evidence checks, in the requested order, using the pinned offline packet."""
    if tuple(order) not in (('catalog', 'pixels'), ('pixels', 'catalog')):
        raise ValueError('Evidence order must contain catalog and pixels exactly once.')
    root = Path(os.environ.get(PACKET_ENV) or DEFAULT_PACKET)
    candidates = result['candidates']
    parent = _observations(_receipt(root, f'{WEST}/NW034/candidate-orbit.json'))
    extended = _observations(_receipt(root, f'{WEST}/NW034/candidate-extended-orbit.json'))
    for step in order:
        if step == 'catalog':
            _catalog(root, candidates, parent, extended)
        else:
            _pixels(root, output, candidates, parent | extended, allow_pixels)
