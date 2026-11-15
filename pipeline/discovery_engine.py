"""Replay and extend links from a pinned MPC Isolated Tracklet File snapshot.

The OBS80 parser, native encoder and two-body astrometry routines are adapted
from this project's prior parallax-event ITF research and the near-west search.
Candidate identifiers are assigned after linkage, tests and the complete fit.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
import os
import subprocess
from collections import Counter, defaultdict
from datetime import date, timedelta
from hashlib import file_digest, sha256
from importlib.metadata import version
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.coordinates import EarthLocation, get_body_barycentric
from astropy.time import Time
from astropy.utils import iers
from scipy.integrate import solve_ivp
from scipy.interpolate import CubicSpline
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_NAME = 'multi-family-holdout-1727-20261114.gz'
ARCHIVE_SHA = 'eeffc38d092a5ed67c88808414533bae3b2572c545b1721f53332db90f40fe10'
STATION_SHA = '95bdb7b9324a8a047c7dc758fb73963f65b984f5a733abb67ec194b7915bedc3'
EARTH_SHA = 'b79b39b08ea79c5643427710f12fe807c7fc5a169f38a57ebe67a61049a3a8f8'
NATIVE_SOURCE_REV = '086064983bc7b6e7878fe78dd9e30e0465e7722f'
NW034_TRAINING_HASH = '7e0cafc1873926bb342e3c5c033149711f7d40d2713498a681199306907b8357'
NW034_COMBINED_HASH = '2b22d5a1052b04680bc077435b931ac82a48c40a223a73b0274625a59b5742e0'
OPTICAL_MODES = {b'C', b'c', b'B', b'D'}
OFFSETS = np.array([0, -480, -360, -240, 240, 360, 480])
FLOOR_SIGMA = .45  # arcsec per coordinate
MAX_SEPARATION = 120.  # arcsec
MAX_MAHALANOBIS = 3.
MIN_TEST_SPAN = 5.  # minutes
MAX_MOTION_ERROR = 2.5  # arcsec
INTERPOLATION_MINUTES = 15
DAY = timedelta(days=1)
MJD_ZERO_ORDINAL = date(1858, 11, 17).toordinal()

MU = .0002959122082855911  # AU^3/day^2
C = 173.144632674240  # AU/day
ARCSEC_PER_RADIAN = (1 * u.rad).to_value(u.arcsec)
OBLIQUITY = (84381.448 * u.arcsec).to_value(u.rad)
OBSERVER_RADIUS_KM = 6378.137
MIN_ERROR_ARCSEC = .25
FIT_MAX_ARCSEC = .35



def angle(field, major_limit):
    major_text, minute_text, second_text = field.split()
    major, minute, second = int(major_text.lstrip(b'+-')), int(minute_text), float(second_text)
    if (major > major_limit or not 0 <= minute < 60 or not 0 <= second < 60
            or (major == major_limit and (major_limit == 24 or minute or second))):
        raise ValueError('Invalid sexagesimal position.')
    if major_limit == 90 and not major_text.startswith((b'+', b'-')):
        raise ValueError('Declination must specify its sign.')
    if major_limit == 24 and not major_text.isdigit():
        raise ValueError('Right ascension must be unsigned.')
    decimal = major + minute / 60. + second / 3600.
    return -decimal if major_text.startswith(b'-') else decimal


def plural_nights(rows):
    group = defaultdict(set)
    for row in rows:
        group[row['night']].add(row['mjd_utc'])
    return sum(len(times) >= 2 for times in group.values())


def linked_rows(mapping, detections):
    groups = defaultdict(list)
    for item in mapping:
        groups[int(item['clusternum'])].append(detections[int(item['detnum'])])
    return dict(groups)


def read_csv(path):
    with path.open() as handle:
        return list(csv.DictReader([handle.readline().removeprefix('#'), *handle]))


def tracklet_endpoints(rows):
    """Fit joint unwrapped RA and Dec tangent-plane endpoint proxies within one tracklet."""
    delta = np.array([row['mjd_utc'] - rows[0]['mjd_utc'] for row in rows])
    ra = np.degrees(np.unwrap(np.radians([r['ra_deg'] for r in rows])))
    dec = [r['dec_deg'] for r in rows]
    design = np.column_stack((np.ones(delta.size), delta))
    coeffs = np.linalg.lstsq(design, np.column_stack((ra, dec)), rcond=None)[0]
    model = design @ coeffs
    return ((model[0, 0] % 360, model[0, 1]), (model[-1, 0] % 360, model[-1, 1]))


def propagate(state, times):
    def derivative(_, y):
        return np.r_[y[3:], -MU * y[:3] / np.linalg.norm(y[:3]) ** 3]

    positions = np.empty((len(times), 3))
    for indices, boundary in ((times < 0, min(-.1, *times)), (times >= 0, max(.1, *times))):
        if indices.any():
            solution = solve_ivp(derivative, (0, boundary), state, method='DOP853',
                                 rtol=2e-11, atol=1e-13, dense_output=True)
            if not solution.success:
                raise ValueError('Two-body propagation failed.')
            positions[indices] = solution.sol(times[indices])[:3].T
    return positions


def sites_from(path, selected):
    sites = {}
    for line in path.read_text().splitlines():
        key = line[:3]
        if key not in selected:
            continue
        longitude, radius_cos, radius_sin = (float(line[a:b]) for a, b in ((4, 13), (13, 21), (21, 30)))
        lon = np.radians(longitude)
        sites[key] = EarthLocation.from_geocentric(radius_cos * np.cos(lon) * OBSERVER_RADIUS_KM,
                                                   radius_cos * np.sin(lon) * OBSERVER_RADIUS_KM,
                                                   radius_sin * OBSERVER_RADIUS_KM, unit=u.km)
    if set(sites) != selected:
        raise ValueError('Some positions lack exact ground-site metadata.')
    return sites


def observation_basis(rows, ref, observatories):
    when = Time([r['mjd_utc'] for r in rows], format='mjd', scale='utc')
    earth = (get_body_barycentric('earth', when, ephemeris='builtin')
             - get_body_barycentric('sun', when, ephemeris='builtin')).xyz.to_value(u.au).T
    for station, location in sites_from(observatories, {r['station'] for r in rows}).items():
        indices = [i for i, row in enumerate(rows) if row['station'] == station]
        earth[indices] += location.get_gcrs_posvel(when[indices])[0].xyz.to_value(u.au).T
    times = (when.tdb - Time(ref, format='mjd', scale='utc').tdb).to_value(u.day)
    ra, dec = np.radians([[r['ra_deg'] for r in rows], [r['dec_deg'] for r in rows]])
    direction = np.array([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)]).T
    east = np.array([-np.sin(ra), np.cos(ra), np.zeros(len(ra))]).T
    north = np.array([-np.sin(dec) * np.cos(ra), -np.sin(dec) * np.sin(ra), np.cos(dec)]).T
    return earth, times, direction, east, north


def orbit_elements(state):
    position, velocity = state[:3], state[3:]
    radius = np.linalg.norm(position)
    momentum = np.cross(position, velocity)
    a = 1 / (2 / radius - np.dot(velocity, velocity) / MU)
    eccentricity = np.linalg.norm(np.cross(velocity, momentum) / MU - position / radius)
    return np.array([a, a * (1 - eccentricity), eccentricity])


def fit(rows, initial, observatories):
    earth, time, direction, east, north = observation_basis(rows, float(initial['reference_MJD']), observatories)
    cos, sin = np.cos(OBLIQUITY), np.sin(OBLIQUITY)
    ecliptic_to_equatorial = np.array([[1, 0, 0], [0, cos, -sin], [0, sin, cos]])
    xyz, velocity = (ecliptic_to_equatorial @ np.array([float(initial[prefix + axis]) for axis in 'XYZ'])
                     for prefix in ('pos', 'vel'))
    x0 = np.r_[xyz * u.km.to(u.au), velocity * (u.km/u.s).to(u.au/u.day)]

    def residual(state):
        emission = time
        for _ in range(3):
            line_of_sight = propagate(state, emission) - earth
            emission = time - np.linalg.norm(line_of_sight, axis=1) / C
        forward = np.einsum('ij,ij->i', line_of_sight, direction)
        return (np.column_stack([np.arctan2(np.einsum('ij,ij->i', line_of_sight, axis), forward)
                                 for axis in (east, north)]) * ARCSEC_PER_RADIAN).ravel()

    result = least_squares(residual, x0, diff_step=1e-5, x_scale='jac', max_nfev=80,
                           ftol=1e-8, gtol=1e-8, xtol=1e-10)
    deviations = result.fun.reshape(-1, 2)
    rms = float(np.sqrt(np.mean(np.square(deviations).sum(axis=1))))
    a, q, e = orbit_elements(result.x)
    _, sv, right = np.linalg.svd(result.jac, full_matrices=False)
    covariance = None
    if (sv > sv[0] * 1e-10).sum() == 6:
        scatter = max(MIN_ERROR_ARCSEC, np.linalg.norm(result.fun) / np.sqrt(len(result.fun) - 6))
        covariance = (right.T / sv**2) @ right * scatter**2
    usable = result.success and covariance is not None and rms <= FIT_MAX_ARCSEC and 2 <= a <= 4 and 0 <= e < .5
    return {'optimizer_converged': bool(result.success), 'rms_arcsec': rms, 'residuals_east_north_arcsec': deviations.tolist(),
            'evaluations': result.nfev, 'semimajor_axis_au': float(a), 'perihelion_au': float(q), 'eccentricity': float(e),
            'state_equatorial_au_au_per_day': result.x.tolist(), 'state_epoch_utc_mjd': float(initial['reference_MJD']),
            'full_rank_training_covariance': covariance is not None, 'condition_number': float(sv[0]/sv[-1]) if sv[-1] else None,
            'training_linearized_covariance': covariance.tolist() if covariance is not None else None, 'training_rule_pass': bool(usable)}


def encode(groups, wd, source, aux):
    rows = sorted([r for group in groups for r in group], key=lambda r: (r['mjd_utc'], r['station'], r['line_sha256']))
    earth = aux / 'Earth1day2020s_02a.csv'
    sites = aux / 'ObsCodesNew.txt'
    with (wd / 'detections.csv').open('w', newline='') as handle:
        csvout = csv.writer(handle)
        csvout.writerow(('id', 'mjd', 'ra', 'dec', 'mag', 'band', 'station'))
        for index, row in enumerate(rows):
            raw = row['obs80']
            csvout.writerow((index + 1, format(row['mjd_utc'], '.9f'), row['ra_deg'], row['dec_deg'],
                             raw[65:70].strip() or '99.999', raw[70].strip() or 'V', row['station']))
    (wd / 'columns.txt').write_text('IDCOL 1\nMJDCOL 2\nRACOL 3\nDECCOL 4\nMAGCOL 5\nBANDCOL 6\nOBSCODECOL 7\n')
    _run_native(source, wd, 'positions', 'make_tracklets', '-dets', 'detections.csv', '-colformat', 'columns.txt',
        '-earth', str(earth), '-obscode', str(sites), '-maxvel', '0.001', '-minvel', '0.0001')
    image_file = wd / 'outimfile01.txt'
    lookup = {}
    original = image_file.read_text().splitlines()
    for i, line in enumerate(original):
        fields = line.split()
        lookup[(round(float(fields[0]), 7), fields[3])] = i
    images = [lookup.get((round(row['mjd_utc'], 7), row['station'])) for row in rows]
    by_station = defaultdict(list)
    for (epoch, station), index in lookup.items():
        by_station[station].append((epoch, index))
    alias = []
    for j, (image, row) in enumerate(zip(images, rows, strict=True)):
        if image is not None:
            continue
        choices = sorted((abs(epoch - row['mjd_utc']) * 86400, index)
                         for epoch, index in by_station.get(row['station'], ()))
        if choices and choices[0][0] <= .20:
            images[j] = choices[0][1]
            alias.append({'station':row['station'], 'mjd_utc':row['mjd_utc'], 'line_sha256':row['line_sha256'],
                          'native_index':choices[0][1], 'time_disagreement_s':choices[0][0]})
    _write(wd / 'native-aliases.json', alias)
    if any(img is None for img in images):
        raise ValueError('Native observatory state mapping cannot account for every original UTC exposure.')
    by_image = defaultdict(list)
    for i, idx in enumerate(images):
        by_image[idx].append(i)
    for i, entry in enumerate(original):
        fields = entry.split()
        ids = by_image[i]
        if ids and ids[-1] - ids[0] + 1 != len(ids):
            raise ValueError('Exposure rows are not contiguous.')
        fields[10:12] = [str(ids[0]), str(ids[-1] + 1)] if ids else ['0', '0']
        original[i] = ' '.join(fields)
    image_file.write_text('\n'.join(original) + '\n')
    line_index = {row['line_sha256']: i for i, row in enumerate(rows)}
    with ((wd / 'known_pairs.csv').open('w', newline='') as detections,
          (wd / 'known_tracklets.csv').open('w', newline='') as t,
          (wd / 'known_tracklet_map.csv').open('w', newline='') as m):
        pdata, tracklets, mapping = csv.writer(detections), csv.writer(t), csv.writer(m)
        pdata.writerow(('#MJD','RA','Dec','mag','trail_len','trail_PA','sigmag','sig_across','sig_along','sig_RA','sig_Dec',
                        'radec_covar','image','idstring','band','obscode','known_obj','det_qual','origindex'))
        tracklets.writerow(('#Image1','RA1','Dec1','Image2','RA2','Dec2','npts','trk_ID'))
        mapping.writerow(('#trk_ID','Det_ID'))
        for i, row in enumerate(rows):
            raw = row['obs80']
            pdata.writerow((format(row['mjd_utc'], '.9f'), row['ra_deg'], row['dec_deg'], raw[65:70].strip() or 99.99,
                             0, 90, 9.999, .25, .25, .25, .25, 0, images[i], f'D{i}', raw[70].strip() or 'V',
                             row['station'], -1, -1, i))
        for i, group in enumerate(groups):
            start, stop = tracklet_endpoints(group)
            ids = [line_index[r['line_sha256']] for r in group]
            tracklets.writerow((images[ids[0]], *start, images[ids[-1]], *stop, len(ids), i))
            mapping.writerows((i, idx) for idx in ids)
    return rows


def _source_paths():
    cache = ROOT / '.parallax-cache' / 'itf'
    research = ROOT.parent / 'parallax-event'
    pinned_stations = ROOT.parent / 'discovery-runs/2026-11-14/independent-validation/mpc-stations-pinned.txt'
    source = Path(os.getenv('PARALLAX_HELIOLINC_SOURCE', str(cache / 'heliolinc'))).expanduser().resolve()
    aux = Path(os.getenv('PARALLAX_HELIOLINC_AUX', str(cache / 'aux'))).expanduser().resolve()
    archive = Path(os.getenv('PARALLAX_ITF_ARCHIVE', str(
        cache / ARCHIVE_NAME if (cache / ARCHIVE_NAME).is_file() else research / '.parallax-cache/itf' / ARCHIVE_NAME
    ))).expanduser().resolve()
    stations = Path(os.getenv('PARALLAX_ITF_STATIONS', str(
        pinned_stations if pinned_stations.is_file() else aux / 'ObsCodesNew.txt'))).expanduser().resolve()
    return archive, stations, source, aux


def source_ready() -> bool:
    archive, stations, source, aux = _source_paths()
    reads = (archive, stations, aux / 'ObsCodesNew.txt', aux / 'Earth1day2020s_02a.csv')
    programs = (source / 'src' / name for name in ('make_tracklets', 'heliolinc'))
    return (all(path.is_file() and os.access(path, os.R_OK) for path in reads)
            and all(path.is_file() and os.access(path, os.R_OK | os.X_OK) for path in programs))


def digest(path):
    with path.open('rb') as blob:
        return file_digest(blob, 'sha256').hexdigest()


def _write(path, value):
    # Stable bytes make every fixed-model forecast traceable to its input artifact.
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return digest(path)


def _run_native(source, work, label, program, *arguments):
    with (work / f'{label}.log').open('w') as output:
        subprocess.run([str(source / 'src' / program), *arguments], cwd=work,
                       stdout=output, stderr=subprocess.STDOUT, check=True, timeout=120)


def _windows(spec):
    start, end = (date.fromisoformat(spec[k]) for k in ('start', 'end'))
    fit_start = date.fromisoformat(spec['fit_start']) if spec.get('fit_start') else start
    fit_end = (date.fromisoformat(spec['fit_end']) if spec.get('fit_end')
               else end - timedelta(days=max(1, min(4, (end - fit_start).days // 4))))
    test_end = date.fromisoformat(spec['test_end']) if spec.get('test_end') else end
    if not (start <= fit_start <= fit_end < test_end <= end):
        raise ValueError('The UTC windows must include a later test window after the training window.')
    if (end - start).days >= 92 or start.year < 2020 or end.year > 2029:
        raise ValueError('Use at most 92 calendar days within the native Earth ephemeris coverage, 2020–2029.')
    return start, fit_start, fit_end, test_end, end


def _regions(spec):
    boxes = []
    for region in spec['regions']:
        ra_lo, ra_hi, dec_lo, dec_hi = (float(region[k]) for k in ('ra_min', 'ra_max', 'dec_min', 'dec_max'))
        if not (0 <= ra_lo < ra_hi <= 360 and -90 <= dec_lo < dec_hi <= 90):
            raise ValueError('Regions must be half-open equatorial rectangles; split any RA seam crossing at 0°.')
        boxes.append((ra_lo, ra_hi, dec_lo, dec_hi))
    if not 1 <= len(boxes) <= 2:
        raise ValueError('Select one or two sky regions.')
    return boxes


def _ground_stations(path):
    sites = set()
    for line in path.read_bytes().splitlines():
        try:
            lon, rc, rs = (float(line[a:b]) for a, b in ((4, 13), (13, 21), (21, 30)))
        except ValueError:
            continue
        if 0 <= lon < 360 and .95 < math.hypot(rc, rs) < 1.03:
            sites.add(line[:3])
    return sites


def _archive_rows(archive, first, last, stations, counts, regions=None):
    nights = {d.isoformat().replace('-', ' ').encode(): (d.isoformat(), d.toordinal() - MJD_ZERO_ORDINAL)
              for d in (first + i * DAY for i in range((last - first).days + 1))}
    with gzip.open(archive, 'rb') as file:
        for raw in file:
            counts['snapshot_lines'] += 1
            if raw[15:25] not in nights:
                continue
            counts['records_in_window'] += 1
            if raw[:5] != b'     ' or raw[14:15] not in OPTICAL_MODES:
                continue
            counts['optical_unassigned_in_window'] += 1
            line = raw.rstrip(b'\r\n')
            if len(line) != 80 or not line.isascii() or line[77:80] not in stations:
                counts['unsupported_station_or_format'] += 1
                continue
            try:
                ra, dec = 15 * angle(line[32:44], 24), angle(line[44:56], 90)
                if regions and not any(a <= ra < b and c <= dec < d for a, b, c, d in regions):
                    continue
                night, midnight = nights[line[15:25]]
                fraction = float(line[25:32])
                if not 0 <= fraction < 1 or not line[5:12].strip():
                    raise ValueError('A dated observation needs fractional UTC and temporary identifier.')
                mjd = midnight + fraction
            except (ValueError, UnicodeError):
                counts['invalid'] += 1
                continue
            counts['scored_rows'] += 1
            yield line, ra, dec, mjd, night


def _observation(line, ra, dec, mjd, night, stage):
    return {'ra_deg': ra, 'dec_deg': dec, 'mjd_utc': mjd, 'night': night, 'station': line[77:80].decode(),
            'temporary_id': line[5:12].decode().strip(), 'obs80': line.decode(),
            'line_sha256': sha256(line).hexdigest(), 'phase': 'fit' if stage == 'training' else 'test', 'stage': stage}


def _training(archive, first, last, stations, regions, work, native, aux, obs_codes, report):
    groups = defaultdict(list)
    counts = Counter()
    for raw in _archive_rows(archive, first, last, stations, counts, regions):
        row = _observation(*raw, 'training')
        groups[row['station'], row['night'], row['temporary_id']].append(row)
    if not counts['records_in_window']:
        raise ValueError('No archive dates overlap the training window in the loaded MPC snapshot.')
    tracklets = []
    for rows in groups.values():
        rows = sorted({r['mjd_utc']: r for r in rows}.values(), key=lambda r: r['mjd_utc'])
        if len(rows) >= 2 and (rows[-1]['mjd_utc'] - rows[0]['mjd_utc']) * 1440 >= 4:
            tracklets.append(rows)
    result = {'archive_scan': dict(counts), 'tracklets': len(tracklets), 'n_rows': sum(map(len, tracklets)),
              'all_raw_proposals': 0, 'training_passes': 0, 'fits': []}
    report(f"Training scan read {counts['snapshot_lines']:,} snapshot rows and selected {len(tracklets):,} within-night tracklets.")
    if len({group[0]['night'] for group in tracklets}) < 3:
        return result
    if result['n_rows'] > 40_000:
        raise ValueError('The selection exceeds the 40,000 native detection limit; narrow the region or time window.')
    work.mkdir()
    detections = encode(tracklets, work, native, aux)
    with (work / 'hyp.txt').open('w') as grid:
        grid.write('#r(AU) rdot(AU/day) mean_accel\n')
        for distance in np.arange(1.85, 4.4, .12):
            for radial_velocity in np.arange(-.006, .0061, .002):
                grid.write(f'{distance:.4f} {radial_velocity:.5f} 0.0\n')
    _run_native(native, work, 'link', 'heliolinc',
                '-imgs', 'outimfile01.txt', '-pairdets', 'known_pairs.csv', '-tracklets', 'known_tracklets.csv',
                '-trk2det', 'known_tracklet_map.csv', '-earth', str(aux / 'Earth1day2020s_02a.csv'),
                '-heliodist', 'hyp.txt', '-clustrad', '220000', '-minobsnights', '3', '-mintimespan', '2',
                '-outsum', 'summary.csv', '-clust2det', 'map.csv')
    proposals = read_csv(work / 'summary.csv')
    mapped = linked_rows(read_csv(work / 'map.csv'), detections)
    result['linkage_input_sha256'] = {name: digest(work / name) for name in (
        'outimfile01.txt', 'known_pairs.csv', 'known_tracklets.csv', 'known_tracklet_map.csv',
        'hyp.txt', 'native-aliases.json', 'summary.csv', 'map.csv',
    )}
    unique = {}
    for row in proposals:
        positions = mapped[int(row['clusternum'])]
        if len(positions) < 6 or plural_nights(positions) < 3:
            continue
        key = tuple(sorted(r['line_sha256'] for r in positions))
        if key not in unique or float(row['totRMS']) < float(unique[key][0]['totRMS']):
            unique[key] = row, positions
    if len(unique) > 350:
        raise ValueError('More than 350 eligible orbit fits; narrow the region or time window.')
    report(f"HelioLinC3D produced {len(proposals):,} proposals; fitting {len(unique):,} distinct linkages.")
    for initial, rows in unique.values():
        try:
            solution = _with_inclination(fit(rows, initial, obs_codes))
        except (ArithmeticError, ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
            solution = {'training_rule_pass': False, 'error': str(exc)}
        result['fits'].append({'proposal': int(initial['clusternum']), 'observations': rows, 'orbit': solution})
    result['all_raw_proposals'] = len(proposals)
    result['training_passes'] = sum(f['orbit']['training_rule_pass'] for f in result['fits'])
    return result


def wrapped_delta(observed, predicted):
    """Smallest signed angular displacement, in degrees."""
    return (observed - predicted + 180) % 360 - 180


def _with_inclination(orbit):
    state = np.array(orbit['state_equatorial_au_au_per_day']).reshape(2, 3)
    eq_to_ecl = _equatorial_to_ecliptic()
    h = np.cross(*(state @ eq_to_ecl.T))
    orbit['inclination_deg'] = float(np.degrees(np.arctan2(np.linalg.norm(h[:2]), h[2])))
    if not np.isfinite(state).all() or not all(
        math.isfinite(orbit[k]) for k in ('rms_arcsec', 'semimajor_axis_au', 'perihelion_au', 'eccentricity', 'inclination_deg')
    ):
        raise ValueError('Fit did not produce a finite orbit.')
    return orbit


def _equatorial_to_ecliptic():
    c, s = np.cos(OBLIQUITY), np.sin(OBLIQUITY)
    return np.array([[1, 0, 0], [0, c, s], [0, -s, c]])


def _refit(rows, orbit, stations):
    eq_to_ecl = _equatorial_to_ecliptic()
    pos, vel = np.array(orbit['state_equatorial_au_au_per_day']).reshape(2, 3)
    initial = {'reference_MJD': orbit['state_epoch_utc_mjd']}
    for prefix, vector, scale in (('pos', pos, u.au.to(u.km)), ('vel', vel, (u.au / u.day).to(u.km / u.s))):
        initial.update({prefix + a: float(x * scale) for a, x in zip('XYZ', eq_to_ecl @ vector)})
    try:
        result = _with_inclination(fit(rows, initial, stations))
    except (ArithmeticError, ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
        return {'training_rule_pass': False, 'error': str(exc)}
    return result


def _forecast(orbit, epochs, station, stations, *, uncertainty):
    """Forecast tangent plane position and propagated covariance at the real station."""
    state = np.array(orbit['state_equatorial_au_au_per_day'])
    observer = (get_body_barycentric('earth', epochs, ephemeris='builtin')
                - get_body_barycentric('sun', epochs, ephemeris='builtin')).xyz.to_value(u.au).T
    site = sites_from(stations, {station})[station]
    observer += site.get_gcrs_posvel(epochs)[0].xyz.to_value(u.au).T
    t = (epochs.tdb - Time(orbit['state_epoch_utc_mjd'], format='mjd', scale='utc').tdb).to_value(u.day)

    def project(params):
        emission = t
        for _ in range(3):
            direction = propagate(params, emission) - observer
            emission = t - np.linalg.norm(direction, axis=1) / C
        return direction / np.linalg.norm(direction, axis=1)[:, None]

    vx, vy, vz = project(state).T
    ra, dec = np.arctan2(vy, vx), np.arcsin(vz)
    sky = np.column_stack((np.degrees(np.unwrap(ra)), np.degrees(dec)))
    if not uncertainty:
        return sky
    east = np.array([-np.sin(ra), np.cos(ra), np.zeros(len(ra))]).T
    north = np.array([-np.sin(dec) * np.cos(ra), -np.sin(dec) * np.sin(ra), np.cos(dec)]).T
    derivatives = []
    for axis, delta in enumerate(np.diag([1e-8] * 3 + [1e-9] * 3)):
        change = ((project(state + delta) - project(state - delta)) * ARCSEC_PER_RADIAN
                  / (2 * delta[axis]))
        derivatives.append(np.column_stack(((change * east).sum(axis=1), (change * north).sum(axis=1))))
    jacobian = np.array(derivatives).transpose((1, 2, 0))
    covariance = np.einsum('nas,st,nbt->nab', jacobian, orbit['training_linearized_covariance'], jacobian)
    return np.column_stack((sky, covariance[:, 0, 0], covariance[:, 0, 1], covariance[:, 1, 1]))


def _scan_fixed(archive, first, last, ground, stations, orbits, excluded, stage):
    counts = Counter()
    summary = {'start': first.isoformat(), 'end': last.isoformat(), 'groups': [], 'forecast_errors': {}}
    if not orbits:
        return {**summary, 'status': 'no_eligible_orbits', 'archive_scan': {}}
    reference = {}
    groups = defaultdict(list)
    day0 = first.toordinal() - MJD_ZERO_ORDINAL
    day1 = last.toordinal() - MJD_ZERO_ORDINAL + 1
    knots = Time(np.linspace(day0, day1, (day1 - day0) * (1440 // INTERPOLATION_MINUTES) + 1),
                 format='mjd', scale='utc')
    reference_site = 'G96' if b'G96' in ground else min(ground).decode()
    for key, orbit in orbits.items():
        try:
            reference[key] = CubicSpline(knots.mjd, _forecast(orbit, knots, reference_site, stations, uncertainty=False))
        except (ArithmeticError, ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
            summary['forecast_errors'][key] = str(exc)
    if reference:
        # Vectorize the broad spatial gate; date slices alone can still contain >100,000 MPC rows.
        rows = list(_archive_rows(archive, first, last, ground, counts))
        if rows:
            xyz = np.array([(ra, dec, mjd) for _, ra, dec, mjd, _ in rows])
        else:
            xyz = np.empty((0, 3))
        for key, interpolator in reference.items():
            ra, dec, epochs = xyz.T
            ref_ra, ref_dec = interpolator(epochs).T
            tangent_ra = np.abs(wrapped_delta(ra, ref_ra) * np.cos(np.deg2rad(ref_dec)))
            nearby = np.flatnonzero((tangent_ra <= .20) & (np.abs(dec - ref_dec) <= .22))
            matching_rows = defaultdict(list)
            for i in nearby:
                line, *_ = rows[i]
                station = line[77:80].decode()
                matching_rows[station].append(i)
            for station, indices in matching_rows.items():
                try:
                    predictor = CubicSpline(knots.mjd, _forecast(orbits[key], knots, station, stations, uncertainty=True))
                    estimates = predictor(epochs[indices])
                except (ArithmeticError, ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                    summary['forecast_errors'][f'{key}/{station}'] = str(exc)
                    continue
                for i, (pra, pdec, c11, c12, c22) in zip(indices, estimates, strict=True):
                    line, rra, rdec, mjd, night = rows[i]
                    row = _observation(line, rra, rdec, mjd, night, stage)
                    if row['line_sha256'] in excluded:
                        counts['excluded_previously_fitted_rows'] += 1
                        continue
                    east = wrapped_delta(rra, pra) * math.cos(math.radians(pdec)) * 3600
                    north = (rdec - pdec) * 3600
                    residuals = np.column_stack((np.full(len(OFFSETS), east), north - OFFSETS))
                    covariance = np.array([[c11 + FLOOR_SIGMA ** 2, c12], [c12, c22 + FLOOR_SIGMA ** 2]])
                    axes = np.linalg.eigvalsh(covariance)
                    if not np.isfinite(axes).all() or axes[0] <= 0:
                        counts['invalid_predictive_covariance'] += 1
                        continue
                    sep = np.linalg.norm(residuals, axis=1)
                    if np.min(sep) > MAX_SEPARATION:
                        continue
                    sq_maha = np.sum(residuals.T * np.linalg.solve(covariance, residuals.T), axis=0)
                    for off, residual, dist, chi2 in zip(OFFSETS, residuals, sep, sq_maha, strict=True):
                        if dist > MAX_SEPARATION or chi2 > MAX_MAHALANOBIS ** 2:
                            continue
                        groups[key, int(off), station, night, row['temporary_id']].append({
                            **row, 'predicted_ra_deg': float(pra % 360), 'predicted_dec_deg': float(pdec),
                            'east_north_arcsec': residual.tolist(), 'residual_arcsec': float(dist),
                            'mahalanobis': float(np.sqrt(max(0., chi2))),
                            'sigma_major_arcsec': float(np.sqrt(axes[1])), 'sigma_minor_arcsec': float(np.sqrt(axes[0])),
                            'prediction_covariance_arcsec2': covariance.tolist(),
                        })
    for (key, offset, station, night, tracklet), match in sorted(groups.items()):
        positions = sorted({row['mjd_utc']: row for row in match}.values(), key=lambda row: row['mjd_utc'])
        duration = (positions[-1]['mjd_utc'] - positions[0]['mjd_utc']) * 1440
        motion = float(np.linalg.norm(np.subtract(positions[-1]['east_north_arcsec'], positions[0]['east_north_arcsec'])))
        summary['groups'].append({'proposal': key, 'shift_arcsec': offset, 'station': station,
                                  'date_utc': night, 'tracklet': tracklet, 'positions': positions,
                                  'duration_minutes': duration, 'displacement_vector_error_arcsec': motion,
                                  'passed': len(positions) >= 2 and duration >= MIN_TEST_SPAN and motion <= MAX_MOTION_ERROR})
    status = ('partial' if summary['forecast_errors'] else
              'scanned' if counts['records_in_window'] else 'no_archive_dates')
    return {**summary, 'status': status, 'archive_scan': dict(counts)}


def _test_for(scan, key, **parent):
    groups = [g for g in scan['groups'] if g['proposal'] == key]
    zero = [g for g in groups if g['passed'] and not g['shift_arcsec']]
    offset = [g for g in groups if g['passed'] and g['shift_arcsec']]
    errors = {k: v for k, v in scan['forecast_errors'].items() if k.split('/')[0] == str(key)}
    return {'status': ('ambiguous' if offset else 'partial' if errors else 'passed' if zero
                       else 'no_match' if scan['status'] in ('scanned', 'partial') else scan['status']),
            'start': scan.get('start'), 'end': scan.get('end'), 'groups': groups,
            'passing_tracklets': len(zero), 'passing_offset_tracklets': len(offset), 'forecast_errors': errors, **parent}


def _rows_for(test):
    if test['status'] != 'passed':
        return []
    unique = {r['line_sha256']: r for g in test['groups'] if g['passed'] and not g['shift_arcsec'] for r in g['positions']}
    return sorted(unique.values(), key=_observation_order)


def _observation_order(row):
    return row['mjd_utc'], row['station'], row['line_sha256']


def _rows_hash(rows):
    return sha256('\n'.join(sorted(r['line_sha256'] for r in rows)).encode()).hexdigest()


def _rank(candidate):
    return (candidate['tests']['earlier_extension']['status'] != 'passed',
            candidate['tests']['later_holdout']['status'] != 'passed', -len(candidate['observations']),
            candidate['orbit']['rms_arcsec'], candidate['proposal'])


def _unique_candidates(candidates):
    ranked = []
    for item in sorted(candidates, key=_rank):
        fitted = {r['line_sha256'] for r in item['observations'] if r['phase'] == 'fit'}
        tests = {r['line_sha256'] for r in item['observations'] if r['stage'] == 'later_holdout'}
        for earlier, earlier_fit, earlier_tests in ranked:
            overlap = len(fitted & earlier_fit)
            if overlap == min(len(fitted), len(earlier_fit)) or (tests & earlier_tests and overlap >= 6):
                earlier['related_proposals'].append(item['proposal'])
                break
        else:
            ranked.append((item, fitted, tests))
    return [item for item, _, _ in ranked]


def _artifact_source(archive, stations, native, aux):
    earth = aux / 'Earth1day2020s_02a.csv'
    native_obs = aux / 'ObsCodesNew.txt'
    hashes = {'archive_sha256': digest(archive), 'stations_sha256': digest(stations),
              'native_stations_sha256': digest(native_obs), 'earth_ephemeris_sha256': digest(earth)}
    if (hashes['archive_sha256'] != os.getenv('PARALLAX_ITF_ARCHIVE_SHA256', ARCHIVE_SHA)
            or hashes['stations_sha256'] != STATION_SHA or hashes['native_stations_sha256'] != STATION_SHA
            or hashes['earth_ephemeris_sha256'] != EARTH_SHA):
        raise ValueError('A required ITF source hash disagrees with the server pin.')
    return {'archive': 'MPC Isolated Tracklet File', 'snapshot_file': archive.name,
            'snapshot_url': 'https://minorplanetcenter.net/iau/ITF/itf.txt.gz',
            'original_linker_source_revision': NATIVE_SOURCE_REV,
            'engine_sha256': digest(Path(__file__)),
            'native_binary_sha256': {name: digest(native / 'src' / name) for name in ('make_tracklets', 'heliolinc')},
            'python_dependencies': {package: version(package) for package in ('astropy', 'astropy-iers-data', 'numpy', 'scipy')},
            **hashes}


def _protocol(spec, boxes, start, fit_start, fit_end, test_end, end):
    return {
        'regions_ra_dec_half_open': boxes,
        'utc_inclusive': {'requested': [start.isoformat(), end.isoformat()],
                          'training': [fit_start.isoformat(), fit_end.isoformat()],
                          'later_holdout': [(fit_end + DAY).isoformat(), test_end.isoformat()],
                          'earlier_extension': [start.isoformat(), (fit_start - DAY).isoformat()] if start < fit_start else None},
        'benchmark': bool(spec.get('benchmark')),
        'linkage': {'minimum_observing_nights': 3, 'minimum_span_days': 2, 'minimum_tracklet_minutes': 4,
                    'clustering_radius_km': 220000, 'distance_grid_au': [1.85, 4.4, .12],
                    'radial_velocity_grid_au_per_day': [-.006, .006, .002]},
        'fit': {'model': 'heliocentric two-body with station parallax, TDB dynamics and iterative light time',
                'earth_ephemeris': 'Astropy builtin', 'maximum_rms_arcsec': FIT_MAX_ARCSEC,
                'base_positional_sigma_arcsec': MIN_ERROR_ARCSEC, 'semimajor_axis_au': [2, 4], 'eccentricity': [0, .5]},
        'holdout': {'measurement_floor_sigma_arcsec': FLOOR_SIGMA,
                    'station_interpolation_minutes': INTERPOLATION_MINUTES, 'offset_controls_arcsec': OFFSETS[1:].tolist(),
                    'maximum_separation_arcsec': MAX_SEPARATION, 'maximum_mahalanobis': MAX_MAHALANOBIS,
                    'minimum_tracklet_positions': 2, 'minimum_tracklet_minutes': MIN_TEST_SPAN,
                    'maximum_motion_vector_error_arcsec': MAX_MOTION_ERROR,
                    'search_scope': 'all usable ground stations near the predicted track, including beyond the discovery regions'},
    }


def run_search(spec: dict, output: Path, report=lambda message: None) -> dict:
    """Run a constrained local archive search; preserve immutable phase inputs and results."""
    with iers.conf.set_temp('auto_download', False):
        return _run_search(spec, output, report)


def _run_search(spec, output, report):
    start, fit_start, fit_end, test_end, end = _windows(spec)
    boxes = _regions(spec)
    if not source_ready():
        raise FileNotFoundError('The pinned MPC snapshot, station table or native HelioLinC3D installation is unavailable.')
    archive, stations, native, aux = _source_paths()
    source = _artifact_source(archive, stations, native, aux)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'protocol.json').exists():
        raise FileExistsError('Use a new output directory for each archival search run.')
    protocol = _protocol(spec, boxes, start, fit_start, fit_end, test_end, end)
    artifacts = {'protocol.json': _write(output / 'protocol.json', {'source': source, **protocol})}
    ground = _ground_stations(stations)
    if not ground:
        raise ValueError('No supported physical ground stations in the pinned table.')
    training = _training(archive, fit_start, fit_end, ground, boxes, output / 'native', native, aux, stations, report)
    training_sha = artifacts['training-fits.json'] = _write(output / 'training-fits.json', {
        'protocol_sha256': artifacts['protocol.json'], **training,
    })
    usable = {str(row['proposal']): row for row in training['fits'] if row['orbit']['training_rule_pass']}
    training_ids = {r['line_sha256'] for fit_row in training['fits'] for r in fit_row['observations']}
    report(f'Froze {len(usable):,} training orbits before opening the later test window.')
    late = _scan_fixed(archive, fit_end + DAY, test_end, ground, stations,
                       {key: row['orbit'] for key, row in usable.items()}, training_ids, 'later_holdout')
    late_sha = artifacts['later-holdout.json'] = _write(output / 'later-holdout.json', {'training_sha256': training_sha, **late})
    candidates = []
    fixed_combined = {}
    for key, record in usable.items():
        test = _test_for(late, key, training_sha256=training_sha, report_sha256=late_sha)
        combined = sorted(record['observations'] + _rows_for(test), key=_observation_order)
        orbit = record['orbit']
        combined_fit = None
        if len(combined) > len(record['observations']):
            combined_fit = _refit(combined, orbit, stations)
            if combined_fit['training_rule_pass']:
                orbit = combined_fit
                fixed_combined[key] = {'orbit': orbit, 'observations': combined}
            else:
                test['status'] = 'combined_refit_failed'
                combined = record['observations']
        candidates.append({'proposal': record['proposal'], 'related_proposals': [],
                           'observations': combined, 'orbit': orbit, 'training_orbit': record['orbit'],
                           'combined_fit': combined_fit, 'tests': {'later_holdout': test}})
    combined_sha = artifacts['fixed-combined-fits.json'] = _write(output / 'fixed-combined-fits.json', {
        'training_sha256': training_sha, 'later_holdout_sha256': late_sha, 'fits': fixed_combined,
    })
    report(f'{len(fixed_combined):,} linkages matched the later test and passed refitting; their orbits are frozen.')
    early = {'status': 'not_requested', 'groups': [], 'forecast_errors': {}}
    if start < fit_start:
        combined_ids = {r['line_sha256'] for rows in fixed_combined.values() for r in rows['observations']} | training_ids
        early = _scan_fixed(archive, start, fit_start - DAY, ground, stations,
                            {key: row['orbit'] for key, row in fixed_combined.items()}, combined_ids, 'earlier_extension')
    early_sha = artifacts['earlier-extension.json'] = _write(output / 'earlier-extension.json', {
        'fixed_combined_fits_sha256': combined_sha, **early,
    })
    for item in candidates:
        key = str(item['proposal'])
        extension = _test_for(early, key, fixed_combined_fits_sha256=combined_sha, report_sha256=early_sha)
        if start < fit_start and key not in fixed_combined:
            extension['status'] = 'no_passing_later_fit'
        rows = _rows_for(extension)
        if rows:
            expanded = sorted(rows + item['observations'], key=_observation_order)
            extended_fit = _refit(expanded, item['orbit'], stations)
            item['extended_fit'] = extended_fit
            if extended_fit['training_rule_pass']:
                item.update(observations=expanded, orbit=extended_fit)
            else:
                extension['status'] = 'combined_refit_failed'
        item['tests']['earlier_extension'] = extension
        item['arc_days'] = item['observations'][-1]['mjd_utc'] - item['observations'][0]['mjd_utc']
        item['training_observations_sha256'] = _rows_hash(r for r in item['observations'] if r['phase'] == 'fit')
        item['observations_sha256'] = _rows_hash(item['observations'])
        item['id'] = f"ITF-{item['training_observations_sha256'][:12]}"
        if (source['archive_sha256'] == ARCHIVE_SHA and item['training_observations_sha256'] == NW034_TRAINING_HASH
                and item['observations_sha256'] == NW034_COMBINED_HASH):
            item['id'] = 'NW034'
            item['replayed_benchmark'] = 'NW034 archived observation sets matched by SHA-256 after search and scoring'
        item['status'] = ('temporal_match' if item['tests']['later_holdout']['status'] == 'passed' else 'training_only')
        item['novelty'] = 'unverified'
    candidates = _unique_candidates(candidates)
    for rank, item in enumerate(candidates, 1):
        item['rank'] = rank
    result = {'source': source, 'protocol': protocol, 'artifacts': artifacts, 'candidates': candidates,
              'counts': {k: training[k] for k in ('n_rows', 'all_raw_proposals', 'tracklets', 'training_passes')},
              'limits': [
                  'MPC isolated tracklet records are not a complete survey footprint or injection/recovery study.',
                  'The heliocentric grid and fit gates only admit the configured main-belt class.',
                  'Later observations are held out of orbit fitting; the earlier stage is exploratory archival precovery.',
                  'Position and motion tests support a linkage. They do not establish a unique or novel catalog designation.',
                  'Neither local covariance nor a finite set of fixed offsets is a calibrated false discovery rate.',
              ]}
    _write(output / 'archive-result.json', result)
    report(f'Ranked {len(candidates):,} candidates; {sum(r["status"] == "temporal_match" for r in candidates):,} have later temporal matches.')
    return result
