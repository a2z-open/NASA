"""Cache real playback sequences and record metadata for the sealed Barnard visit."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from io import BytesIO
import warnings

from astropy.io import fits
from astropy.wcs import WCS, FITSFixedWarning

from .archive import (
    BARNARD_CENTER, COLLECTIONS, ArchiveUnavailable, InvalidCutout, IrsaArchive, SkyPosition,
    atomic_write, choose_frames, decode_fits, frame_payload, group_visits, render_frames,
    sequence_payload, utc_time, write_json,
)
from .calibration import load_spectral_calibration, wavelength_at


ROOT = Path(__file__).resolve().parents[1]
CURATED_FOV = 10 / 60
FITS_CACHE = ROOT / '.parallax-cache/fits'
PUBLIC = ROOT / 'web/public/data'
VALIDATION = ROOT / 'validation'
CALIBRATION_PATH = ROOT / '.parallax-cache/calibration/spectral_wcs_D5_spx_cal-swcs-v5-2026-191.fits'
# Selected using only earlier fit visits. Angular samples use the Gaia DR3
# tangent-plane motion at each FITS midpoint (no parallax applied).
DISPLAY_PAIR = {
    '2025W35_1A_0146_4-D5': (269.44634673622016, 4.767193528302913),
    '2026W11_2A_0550_2-D5': (269.4462234188485, 4.768782183737392),
}


@dataclass(frozen=True)
class Target:
    slug: str
    title: str
    center: tuple[float, float]
    coordinate_source: str


BARNARD = Target(
    'barnards-star', 'Barnard’s Star', BARNARD_CENTER,
    'Fixed field near Gaia DR3 source 4472832130942575872 propagated to the SPHEREx era.',
)
TARGETS = (
    BARNARD,
    Target('epsilon-indi-b', 'Epsilon Indi B', (331.0441466, -56.7828442),
           'https://simbad.u-strasbg.fr/simbad/sim-id?Ident=Epsilon+Indi+B (ICRS/J2000; coverage only)'),
    Target('wise-0855', 'WISE 0855', (133.7951292, -7.2451472),
           'NASA Space Apps Planet X and SPHEREx brief (reference coordinate; coverage only)'),
    Target('rw-aurigae', 'RW Aurigae', (76.95654, 30.40144),
           'https://vsx.aavso.org/index.php?oid=3777&view=detail.top (J2000; coverage only)'),
    Target('r-draconis', 'R Draconis', (248.1676108, 66.7549794),
           'https://simbad.u-strasbg.fr/simbad/sim-id?Ident=R+Dra (ICRS/J2000; coverage only)'),
)


def metadata(archive, position):
    with ThreadPoolExecutor(max_workers=2) as pool:
        released = list(pool.map(lambda name: archive.search_collection(name, position), COLLECTIONS))
    counts = dict(zip(COLLECTIONS, map(len, released)))
    return group_visits([item for batch in released for item in batch]), counts


def visit_summary(visits):
    return [
        {'id': f'visit-{index}', 'detector_products': len(visit),
         'start_utc': utc_time(visit[0].t_min), 'end_utc': utc_time(max(x.t_max for x in visit))}
        for index, visit in enumerate(visits, start=1)
    ]


def curated_payload(target, position, frames, status, message=None):
    result = sequence_payload(position, frames, status, 'cache')
    result['title'] = target.title
    result['field_of_view_arcmin'] = 10
    if message:
        result['message'] = message
    return result


def write_coverage(archive, target):
    position = SkyPosition(*target.center)
    try:
        visits, counts = metadata(archive, position)
    except ArchiveUnavailable as error:
        result = curated_payload(target, position, [], 'archive_unavailable', str(error))
        result['coverage'] = None
    else:
        total = sum(counts.values())
        message = (f'IRSA lists {total} detector products in {len(visits)} candidate visits. '
                   'Candidate coverage only for this field.')
        result = curated_payload(target, position, [], 'no_usable_frames' if total else 'no_coverage', message)
        result['coverage'] = {'rows': counts, 'visits': visit_summary(visits), 'target_resolution': 'coverage_only'}
    result['coordinate_source'] = target.coordinate_source
    write_json(PUBLIC / f'{target.slug}.json', result)
    return result


def pair_calibration(item, raw):
    if item.id not in DISPLAY_PAIR or item.release != 'DR1' or not CALIBRATION_PATH.is_file():
        return {}
    sample = SkyPosition(*DISPLAY_PAIR[item.id])
    with fits.open(BytesIO(raw), memmap=False) as hdul, warnings.catch_warnings():
        warnings.simplefilter('ignore', FITSFixedWarning)
        header = hdul['IMAGE'].header
        native = WCS(header).celestial
        x, y = native.world_to_pixel(sample.skycoord())
        calibration = load_spectral_calibration(CALIBRATION_PATH, wcs_wave_header=hdul['WCS-WAVE'].header)
        wavelength, bandwidth = wavelength_at(calibration, header, float(x), float(y))
    return {
        'wavelength_um': wavelength, 'bandwidth_um': bandwidth, 'sample_center': asdict(sample),
        'calibration_id': calibration.source, 'calibration_file': CALIBRATION_PATH.name,
    }


def write_barnard(archive):
    position = SkyPosition(*BARNARD.center)
    visits, counts = metadata(archive, position)
    if len(visits) < 3:
        raise ArchiveUnavailable('Barnard SIA2 metadata did not include at least three separable visits.')
    fit_visits = visits[:2]
    reserved = [item for visit in visits[2:] for item in visit]
    reservation = {
        'visit_ids': [f'visit-{index}' for index in range(3, len(visits) + 1)],
        't_min': min(item.t_min for item in reserved),
        't_max': max(item.t_max for item in reserved),
        'obs_ids': sorted({item.obs_id for item in reserved}),
        'pixels_downloaded': False,
        'products': [asdict(item) | {'id': item.id} for item in reserved],
    }
    evidence = {
        'center': asdict(position),
        'coordinate_source': BARNARD.coordinate_source,
        'collection_counts': counts,
        'visits': visit_summary(visits),
        'field_of_view_arcmin': 10,
        'fit_frames': [],
        'reserve': reservation,
    }
    # Install the public API exclusion before any curated frames become public.
    evidence_path = VALIDATION / 'barnards-star-archive.json'
    write_json(evidence_path, evidence)

    cached_folder = FITS_CACHE / BARNARD.slug
    candidates = choose_frames(fit_visits, position, limit=12, detector='D5')
    known = {item.id for item, _ in candidates}
    for index, visit in enumerate(fit_visits, start=1):
        candidates.extend(
            (item, f'visit-{index}') for item in visit if item.id not in known and (
                item.id in DISPLAY_PAIR or (cached_folder / f'{item.id}.fits').is_file()
            )
        )

    def fit_frame(pick):
        item, visit_id = pick
        path = cached_folder / f'{item.id}.fits'
        try:
            raw = path.read_bytes() if path.is_file() else archive.cutout(item, position, CURATED_FOV)
            image = decode_fits(raw, position, CURATED_FOV)
        except (ArchiveUnavailable, InvalidCutout):
            return None
        if not path.is_file():
            atomic_write(path, raw)
        cutout_url = f'{item.url}?center={position.ra:.7f},{position.dec:.7f}&size={CURATED_FOV:.7f}'
        details = {
            'id': item.id, 'visit_id': visit_id, 'path': str(path.relative_to(ROOT)),
            'sha256': sha256(raw).hexdigest(), 'archive_url': item.url, 'cutout_url': cutout_url,
            'time_utc': utc_time(image.mjd_avg), 'mjd_avg': image.mjd_avg,
            'detector': item.detector, 'release': item.release, 'native_shape': image.image_shape,
        }
        details.update(pair_calibration(item, raw))
        return item, visit_id, image, details

    with ThreadPoolExecutor(max_workers=6) as pool:
        fit_frames = sorted((entry for entry in pool.map(fit_frame, candidates) if entry is not None),
                            key=lambda entry: entry[2].mjd_avg)
    if not fit_frames:
        raise ArchiveUnavailable('Barnard candidate cutouts were unavailable or clipped.')
    evidence['fit_frames'] = [details for _, _, _, details in fit_frames]
    write_json(evidence_path, evidence)

    preview = [entry for entry in fit_frames if entry[0].id in DISPLAY_PAIR]
    if len(preview) != len(DISPLAY_PAIR):
        preview = fit_frames[:1] + [
            entry for entry in fit_frames if entry[1] != fit_frames[0][1]
        ][:1]
    frames = []
    pngs = render_frames([image for _, _, image, _ in preview])
    for (item, visit_id, image, details), png in zip(preview, pngs):
        file = f'barnards-star/{item.id}.png'
        atomic_write(PUBLIC / file, png)
        frame = frame_payload(item, visit_id, image, f'/data/{file}')
        for key in ('wavelength_um', 'bandwidth_um', 'calibration_id', 'sample_center'):
            if key in details:
                frame[key] = details[key]
        frame['wavelength_verified'] = 'calibration_id' in frame
        frames.append(frame)
    keep = {Path(frame['display_url']).name for frame in frames}
    for old in (PUBLIC / BARNARD.slug).glob('*.png'):
        if old.name not in keep:
            old.unlink()
    status = 'ready' if len({x['visit_id'] for x in frames}) > 1 else 'one_visit'
    message = 'The reserved visit stays sealed.'
    if all(frame['id'] in DISPLAY_PAIR and frame['wavelength_verified'] for frame in frames) and len(frames) == 2:
        message = 'Barnard’s core failed quality checks in the saved frames. ' + message
    case = curated_payload(BARNARD, position, frames, status, message)
    case.update({
        'coordinate_source': BARNARD.coordinate_source,
        'coverage': {'rows': counts, 'visits': visit_summary(visits)},
        'reserved_visit_count': len(reservation['visit_ids']),
        'comparison_status': 'unverified',
    })
    if len(frames) == 2 and all(frame['bandwidth_um'] is not None for frame in frames):
        lo = max(frame['wavelength_um'] - frame['bandwidth_um'] / 2 for frame in frames)
        hi = min(frame['wavelength_um'] + frame['bandwidth_um'] / 2 for frame in frames)
        case['approximate_top_hat_overlap'] = max(0, hi - lo) / max(
            frame['bandwidth_um'] for frame in frames
        )
    write_json(PUBLIC / f'{BARNARD.slug}.json', case)
    return case


def main():
    archive = IrsaArchive()
    try:
        barnard = write_barnard(archive)
        print(f'{BARNARD.title}: {len(barnard["frames"])} real fit frames ({barnard["status"]})', flush=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            for case in pool.map(lambda target: write_coverage(archive, target), TARGETS[1:]):
                counts = case['coverage']['rows'] if case['coverage'] is not None else {}
                print(f'{case["title"]}: {sum(counts.values())} detector products', flush=True)
    finally:
        archive.close()


if __name__ == '__main__':
    main()
