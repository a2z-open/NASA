"""Asteroid hunt: find things that move from night to night in SPHEREx images, then ask which ones are known.

    python -m validation.asteroids plan      # 1. choose patches near the ecliptic that SPHEREx imaged on 3+ nights
    python -m validation.asteroids fetch     # 2. download the image cutouts, and the Gaia and WISE stars of each patch
    python -m validation.asteroids detect    # 3. every point of light that is not a catalogued star (pipeline/distant.py)
    python -m validation.asteroids link      # 4. join them into straight-line tracks over 3+ nights; LOCK the tracks
    python -m validation.asteroids known     # 5. only now: ask IMCCE SkyBoT which known asteroids were there
    python -m validation.asteroids report    # 6. recovery of known asteroids, and any track that matches nothing

Near the ecliptic, at SPHEREx's 90-degree viewing angle, a main-belt asteroid moves about 10 to 40 arcseconds per hour:
too little to see inside one 6-minute sequence, several arcminutes from one night to the next.  So a detection must be
seen in at least two images of the same night (which removes cosmic rays and noise), and a track must join three or
more nights in a straight line.  Nothing about known asteroids is used before step 5.
"""
from __future__ import annotations

import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation' / 'asteroids'
CACHE = ROOT / '.parallax-cache' / 'asteroids60v3'      # version 2 (calibration) images are in asteroids60/
SKYBOT = 'https://ssp.imcce.fr/webservices/skybot/api/conesearch.php'

SIZE_ARCMIN = 60.0              # cutout width (v2; v1 used 24 arcmin)
DETECTORS = (1, 2)              # 0.75 to 1.6 microns: where asteroids are brightest in reflected sunlight, and deepest
PER_NIGHT_PER_DET = 2           # images per detector per night
N_FIELDS = 6
MIN_NIGHTS = 3                  # nights a patch must have been imaged on
TRACK_NIGHTS = 4                # nights a track must join: 3-night lines happen by chance (see the control)
FLUX_RATIO_MAX = 3.0            # brightest / faintest night along a track
NIGHT_GAP_D = 0.25
EPOCH_GAP_D = 30 / 1440          # images closer than 30 minutes form one epoch (SPHEREx takes them about 2 minutes apart)
STATIC_ARCSEC = 4.0             # a dot seen within this distance on 2+ other epochs is a fixed source, not a mover
PEAK_SNR = 4.5
SAME_NIGHT_ARCSEC = 4.0         # two detections in one night within this distance are the same thing
RATE_MIN, RATE_MAX = 1.0, 90.0  # arcsec per hour
TRACK_TOL_ARCSEC = 4.0
TRACK_RMS_MAX = 2.0
MATCH_ARCSEC = 20.0             # a track and a known asteroid are the same if they agree this well on each night


def _tangent(ra, dec, ra0, dec0):
    ra, dec, ra0, dec0 = map(np.radians, (np.asarray(ra, float), np.asarray(dec, float), ra0, dec0))
    c = np.sin(dec0) * np.sin(dec) + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0)
    return (np.degrees(np.cos(dec) * np.sin(ra - ra0) / c) * 3600, np.degrees((np.cos(dec0) * np.sin(dec) - np.sin(dec0) * np.cos(dec) * np.cos(ra - ra0)) / c) * 3600)


def _nights(mjds: list[float]) -> list[list[int]]:
    order = np.argsort(mjds)
    groups = []
    for i in order:
        if not groups or mjds[i] - mjds[groups[-1][-1]] > NIGHT_GAP_D:
            groups.append([])
        groups[-1].append(int(i))
    return groups


# ---------------------------------------------------------------------------
# 1. plan
# ---------------------------------------------------------------------------

def plan(log=print) -> dict:
    from astropy.coordinates import BarycentricTrueEcliptic, SkyCoord
    import astropy.units as u
    from pipeline import spherex
    cands = []
    for lam in np.arange(5, 360, 10.0):
        for beta in (-3.0, 3.0):
            c = SkyCoord(lam * u.deg, beta * u.deg, frame=BarycentricTrueEcliptic(equinox='J2000')).icrs
            if abs(c.galactic.b.deg) < 25:
                continue
            cands.append((float(c.ra.deg), float(c.dec.deg), float(lam), beta))
    fields = []

    def one(c):
        ra, dec, lam, beta = c
        try:
            prods = [p for p in spherex.dedupe(spherex.search(ra, dec, radius_deg=0.001)) if p.detector in DETECTORS]
        except Exception as error:  # noqa: BLE001
            return None, f'{type(error).__name__}'
        best = None
        for visit in spherex.group_visits(prods, gap_days=3.0):
            idx = _nights([p.t_min for p in visit])
            if len(idx) < MIN_NIGHTS or visit[idx[-1][0]].t_min - visit[idx[0][0]].t_min > 7:
                continue
            chosen = []
            for g in idx:
                night = [visit[i] for i in g]
                for det in DETECTORS:
                    chosen += [p for p in night if p.detector == det][:PER_NIGHT_PER_DET]
            score = (len(idx), len(chosen))
            if best is None or score > best[0]:
                best = (score, chosen, len(idx))
        if best is None:
            return None, 'no visit with 3 nights'
        return {'ra': ra, 'dec': dec, 'ecl_lon': lam, 'ecl_lat': beta, 'n_nights': best[2],
                'products': [{'id': p.id, 'obs_id': p.obs_id, 'detector': p.detector, 'mjd': p.t_min, 'access_url': p.access_url, 'release': p.release,
                              'collection': p.collection} for p in best[1]]}, None

    with ThreadPoolExecutor(max_workers=6) as ex:
        for f, why in ex.map(one, cands):
            if f:
                fields.append(f)
    fields.sort(key=lambda f: (-f['n_nights'], f['ecl_lon']))
    # version 3 searches fresh patches only: the version-2 patches were used to tune the linker on known asteroids
    calib = OUT / 'v2_calibration' / 'plan.json'
    if calib.is_file():
        used = json.loads(calib.read_text())['fields']
        fields = [f for f in fields if all(abs((f['ecl_lon'] - g['ecl_lon'] + 180) % 360 - 180) >= 8 for g in used)]
    # spread along the ecliptic: no two chosen fields within 15 degrees of longitude
    chosen = []
    for f in fields:
        if all(abs((f['ecl_lon'] - g['ecl_lon'] + 180) % 360 - 180) >= 15 for g in chosen):
            chosen.append(f)
        if len(chosen) >= N_FIELDS:
            break
    for k, f in enumerate(chosen):
        f['id'] = f'ast{k:02d}'
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'n_candidate_points': len(cands), 'n_with_3_nights': len(fields),
           'settings': {'size_arcmin': SIZE_ARCMIN, 'detectors': DETECTORS, 'per_night_per_detector': PER_NIGHT_PER_DET, 'min_nights': MIN_NIGHTS},
           'fields': chosen}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'plan.json').write_text(json.dumps(doc, indent=1))
    log(f"{len(cands)} points near the ecliptic and away from the Milky Way; {len(fields)} have a SPHEREx visit with 3+ nights; chose {len(chosen)}: "
        + ', '.join(f"{f['id']} (lon {f['ecl_lon']:.0f}, {f['n_nights']} nights, {len(f['products'])} images)" for f in chosen))
    return doc


# ---------------------------------------------------------------------------
# 2. fetch
# ---------------------------------------------------------------------------

def _allwise_vizier(ra: float, dec: float, radius_deg: float, cache: Path) -> list[dict]:
    """WISE stars in a cone from AllWISE (Cutri et al. 2013) on the CfA VizieR mirror, in the format pipeline.distant
    uses for CatWISE.  Used because the CatWISE services at IRSA and NOIRLab did not answer on the day."""
    if cache.is_file():
        return json.loads(cache.read_text())
    params = [('-source', 'II/328/allwise'), ('-c', f'{ra:.6f} {dec:+.6f}'), ('-c.rd', f'{radius_deg:.4f}'), ('-out.max', '99999'),
              ('-out', 'RAJ2000'), ('-out', 'DEJ2000'), ('-out', 'W1mag'), ('-out', 'W2mag')]
    for k in range(4):
        try:
            r = requests.get('https://vizier.cfa.harvard.edu/viz-bin/asu-tsv', params=params, timeout=180)
            if r.status_code == 200 and '#RESOURCE' in r.text:
                break
        except requests.RequestException:
            pass
        time.sleep(3 * (k + 1))
    else:
        raise RuntimeError('AllWISE (VizieR) did not answer')
    lines = [ln for ln in r.text.splitlines() if ln and not ln.startswith('#')]
    rows = []
    for ln in lines[3:]:
        v = ln.split('\t')
        try:
            ra2, dec2 = float(v[0]), float(v[1])
        except (ValueError, IndexError):
            continue
        f = lambda x: float(x) if x.strip() else None          # noqa: E731
        rows.append({'ra': ra2, 'dec': dec2, 'w1': f(v[2]), 'w2': f(v[3]), 'cat': 'AllWISE (VizieR, CfA mirror)'})
    cache.write_text(json.dumps(rows))
    return rows


def fetch(log=print) -> dict:
    from pipeline import spherex
    from pipeline.measure import gaia_field
    doc = json.loads((OUT / 'plan.json').read_text())
    total = 0
    for f in doc['fields']:
        folder = CACHE / f['id']
        folder.mkdir(parents=True, exist_ok=True)
        prods = [spherex.Product(obs_id=p['obs_id'], detector=p['detector'], collection=p['collection'], release=p['release'], access_url=p['access_url'],
                                 t_min=p['mjd'], t_max=p['mjd'], s_ra=f['ra'], s_dec=f['dec'], em_min_um=None, em_max_um=None) for p in f['products']]
        t = time.time()
        ok, failed = spherex.fetch_many(prods, f['ra'], f['dec'], SIZE_ARCMIN, folder, workers=5)
        # v2 needs Gaia only to register each image (stars brighter than G 18.5); nothing is removed by catalogue
        gaia_field(f['ra'], f['dec'], SIZE_ARCMIN / 60 * 0.75, gmax=18.5, cache=folder / 'gaia_all.json')
        total += len(ok)
        log(f"{f['id']}: {len(ok)} of {len(prods)} cutouts in {time.time() - t:.0f} s" + (f"; failed: {failed[0]['error'][:80]}" if failed else ''))
    return {'n_files': total}


# ---------------------------------------------------------------------------
# 3. detect
# ---------------------------------------------------------------------------

def _sources(path: str) -> dict:
    """Every point source in one image (matched-filter S/N >= PEAK_SNR), with sky positions from a 3 x 3 centroid after
    registering the image on Gaia stars.  No catalogue is used to remove anything: fixed sources are removed later by
    comparing epochs with each other."""
    from pipeline.distant import _snr_map
    from pipeline.hunt import find_peaks
    from pipeline.measure import reference_candidates, register
    from pipeline.spherex import load_observation
    try:
        obs = load_observation(path)
        gaia = json.loads((Path(path).parent / 'gaia_all.json').read_text())
        reg, _ = register(obs, reference_candidates([g for g in gaia if g.get('g') is not None and g['g'] < 18.5]))
        if not reg.ok:
            return {'ok': False, 'path': path, 'reason': 'registration failed'}
        snr, _ = _snr_map(obs)
        if snr is None:
            return {'ok': False, 'path': path, 'reason': 'no valid pixels'}
        out = []
        ny, nx = snr.shape
        for x, y, v in find_peaks(snr, PEAK_SNR, edge=4):
            xi, yi = int(round(x)), int(round(y))
            win = np.nan_to_num(snr[yi - 1:yi + 2, xi - 1:xi + 2]).clip(0)
            if win.shape != (3, 3) or win.sum() <= 0:
                continue
            gy, gx = np.mgrid[-1:2, -1:2]
            cx, cy = xi + (win * gx).sum() / win.sum(), yi + (win * gy).sum() / win.sum()
            ra, dec = obs.wcs.pixel_to_world_values(cx - reg.dx, cy - reg.dy)
            out.append({'ra': float(ra), 'dec': float(dec), 'snr': float(v)})
        return {'ok': True, 'path': str(Path(path).resolve().relative_to(ROOT)), 'mjd': obs.mjd, 'detector': obs.detector, 'product_id': obs.product_id, 'sources': out,
                'reg_rms_arcsec': None if not math.isfinite(reg.rms_arcsec) else round(reg.rms_arcsec, 2)}
    except Exception as error:  # noqa: BLE001
        return {'ok': False, 'path': path, 'reason': f'{type(error).__name__}: {error}'[:120]}


def detect(log=print) -> dict:
    doc = json.loads((OUT / 'plan.json').read_text())
    summary = {}
    for f in doc['fields']:
        files = sorted(str(p) for p in (CACHE / f['id']).glob('*.fits'))
        with ProcessPoolExecutor(max_workers=8) as ex:
            res = list(ex.map(_sources, files, chunksize=1))
        ok = [r for r in res if r['ok']]
        (OUT / f"{f['id']}_sources.json").write_text(json.dumps({'field': f['id'], 'images': ok, 'failed': [r for r in res if not r['ok']]}))
        summary[f['id']] = {'images': len(files), 'ok': len(ok), 'sources': sum(len(r['sources']) for r in ok)}
        log(f"{f['id']}: {len(ok)}/{len(files)} images, {summary[f['id']]['sources']} point sources")
    return summary


# ---------------------------------------------------------------------------
# 4. link (blind) and lock
# ---------------------------------------------------------------------------

def _night_detections(images: list[dict], ra0: float, dec0: float) -> tuple[list[dict], dict]:
    """Epoch detections that are (1) seen in two images of the same epoch, about 2 minutes apart, within SAME_NIGHT_ARCSEC,
    and (2) NOT seen within STATIC_ARCSEC on two or more other epochs: whatever is still there on other days is fixed."""
    images = sorted(images, key=lambda im: im['mjd'])
    epochs = []
    for im in images:
        if not epochs or im['mjd'] - epochs[-1][-1]['mjd'] > EPOCH_GAP_D:
            epochs.append([])
        epochs[-1].append(im)
    xy = []
    for ep in epochs:
        pts = [(s['ra'], s['dec'], s['snr'], k) for k, im in enumerate(ep) for s in im['sources']]
        if not pts:
            xy.append(np.zeros((0, 4)))
            continue
        x, y = _tangent([p[0] for p in pts], [p[1] for p in pts], ra0, dec0)
        xy.append(np.column_stack([x, y, [p[2] for p in pts], [p[3] for p in pts]]))
    out, n_pairs, n_static = [], 0, 0
    for e, ep in enumerate(epochs):
        if len(ep) < 2 or not len(xy[e]):
            continue
        A = xy[e]
        first, rest = A[A[:, 3] == 0], A[A[:, 3] > 0]
        if not len(rest):
            continue
        d = np.hypot(first[:, None, 0] - rest[None, :, 0], first[:, None, 1] - rest[None, :, 1])
        j = np.argmin(d, axis=1)
        for i in np.where(d[np.arange(len(j)), j] <= SAME_NIGHT_ARCSEC)[0]:
            n_pairs += 1
            px, py = (first[i, 0] + rest[j[i], 0]) / 2, (first[i, 1] + rest[j[i], 1]) / 2
            seen = 0
            for f, other in enumerate(xy):
                if f == e or not len(other):
                    continue
                if np.min(np.hypot(other[:, 0] - px, other[:, 1] - py)) <= STATIC_ARCSEC:
                    seen += 1
                    if seen >= 2:
                        break
            if seen >= 2:
                n_static += 1
                continue
            mj = float(np.mean([im['mjd'] for im in ep]))
            out.append({'night': e, 'mjd': mj, 'x': float(px), 'y': float(py), 'sigma': 1.5, 'n_images': 2, 'detectors': sorted({im['detector'] for im in ep}),
                        'snr': float(max(first[i, 2], rest[j[i], 2])), 'flux_ujy': float((first[i, 2] + rest[j[i], 2]) / 2)})
    return out, {'epochs': len(epochs), 'epochs_with_pairs': sum(1 for ep in epochs if len(ep) >= 2), 'paired_detections': n_pairs, 'fixed_sources_removed': n_static}


def _fit(pts: list[dict], quad: bool = False):
    t = np.array([p['mjd'] for p in pts]) * 24.0
    t0 = t.mean()
    A = np.vstack([np.ones_like(t), t - t0] + ([(t - t0) ** 2] if quad else [])).T
    w = np.array([1 / p['sigma'] for p in pts])
    cx, *_ = np.linalg.lstsq(A * w[:, None], np.array([p['x'] for p in pts]) * w, rcond=None)
    cy, *_ = np.linalg.lstsq(A * w[:, None], np.array([p['y'] for p in pts]) * w, rcond=None)
    r = np.hypot(A @ cx - [p['x'] for p in pts], A @ cy - [p['y'] for p in pts])
    return cx, cy, t0, float(np.sqrt(np.mean(r ** 2)))


PAIR_MAX_H = 36.0               # a seed pair spans at most this many hours
ACCEL_MAX = 0.15                # arcsec per hour per hour: how much an asteroid's path may bend (allowed before a curved fit)
MIN_SPAN_H = 6.0


def _fit_xy(pts, quad):
    t = np.array([p['mjd'] for p in pts]) * 24.0
    t0 = t.mean()
    A = np.vstack([np.ones_like(t), t - t0] + ([(t - t0) ** 2] if quad else [])).T
    cx, *_ = np.linalg.lstsq(A, np.array([p['x'] for p in pts]), rcond=None)
    cy, *_ = np.linalg.lstsq(A, np.array([p['y'] for p in pts]), rcond=None)
    pred = lambda tt: (np.polyval(cx[::-1], tt - t0), np.polyval(cy[::-1], tt - t0))       # noqa: E731
    r = np.hypot(A @ cx - [p['x'] for p in pts], A @ cy - [p['y'] for p in pts])
    return pred, float(np.sqrt(np.mean(r ** 2))), cx, cy, t0


def _link_field(dets: list[dict]) -> list[dict]:
    """Grow tracks step by step.  A seed is a pair of detections on two epochs at most PAIR_MAX_H apart with a speed in
    range.  The track then takes the nearest epoch in time, predicts where the object should be there (a straight line
    while the track has fewer than 4 points, a curved path after), and adds the closest detection within
    TRACK_TOL_ARCSEC plus the bending allowed over the extrapolated time.  It repeats until no epoch adds anything."""
    if not dets:
        return []
    nights = sorted({d['night'] for d in dets})
    X = {n: np.array([[d['x'], d['y'], d['mjd'] * 24] for d in dets if d['night'] == n]) for n in nights}
    D = {n: [d for d in dets if d['night'] == n] for n in nights}
    T = {n: float(np.mean(X[n][:, 2])) for n in nights}
    tracks = []
    for ia, na in enumerate(nights):
        for nb in nights[ia + 1:]:
            if T[nb] - T[na] > PAIR_MAX_H:
                break
            A_, B_ = X[na], X[nb]
            dt = B_[None, :, 2] - A_[:, None, 2]
            vx = (B_[None, :, 0] - A_[:, None, 0]) / dt
            vy = (B_[None, :, 1] - A_[:, None, 1]) / dt
            rate = np.hypot(vx, vy)
            for i, j in zip(*np.where((rate >= RATE_MIN) & (rate <= RATE_MAX))):
                pts = [D[na][i], D[nb][j]]
                used = {na, nb}
                while True:
                    lo, hi = min(p['mjd'] for p in pts) * 24, max(p['mjd'] for p in pts) * 24
                    rest = [n for n in nights if n not in used]
                    if not rest:
                        break
                    quad = len(pts) >= 4
                    pred, _, *_ = _fit_xy(pts, quad)
                    added = False
                    for n in sorted(rest, key=lambda n: min(abs(T[n] - lo), abs(T[n] - hi))):
                        ext = max(lo - T[n], T[n] - hi, 0.0)
                        tol = TRACK_TOL_ARCSEC + (0.01 if quad else 0.5 * ACCEL_MAX) * ext ** 2
                        if tol > 600:
                            break                                   # too far to extrapolate: stop growing in this direction
                        C = X[n]
                        px, py = pred(C[:, 2])
                        d = np.hypot(C[:, 0] - px, C[:, 1] - py)
                        k = int(np.argmin(d))
                        if d[k] <= tol:
                            pts.append(D[n][k])
                            used.add(n)
                            added = True
                            break
                        used.add(n)                                 # nothing there: this epoch is skipped for good
                    if not added:
                        break
                if len(pts) < TRACK_NIGHTS:
                    continue
                pts.sort(key=lambda p: p['mjd'])
                if (pts[-1]['mjd'] - pts[0]['mjd']) * 24 < MIN_SPAN_H:
                    continue
                fl = [abs(p.get('flux_ujy', 1.0)) or 1e-9 for p in pts]
                if max(fl) / max(min(fl), 1e-9) > FLUX_RATIO_MAX:
                    continue
                # 4 points: a straight line must fit (a curve would fit almost anything); 5 or more: a curve with physical bending
                _, rms, cx, cy, t0 = _fit_xy(pts, len(pts) >= 5)
                if rms > (1.5 * TRACK_RMS_MAX if len(pts) == 4 else TRACK_RMS_MAX):
                    continue
                if len(pts) >= 5 and math.hypot(cx[2], cy[2]) * 2 > ACCEL_MAX:
                    continue
                tracks.append({'points': pts, 'rms_arcsec': rms, 'rate_arcsec_h': float(math.hypot(cx[1], cy[1])), 'cx': cx.tolist(), 'cy': cy.tolist(), 't0_h': t0})
    tracks.sort(key=lambda t: (-len(t['points']), t['rms_arcsec']))
    used, kept = set(), []
    for t in tracks:
        keys = {(p['night'], round(p['x'], 2), round(p['y'], 2)) for p in t['points']}
        if keys & used:
            continue
        used |= keys
        kept.append(t)
    return kept


N_CONTROL = 8


def _control(dets: list[dict], seed: int) -> list[int]:
    """Chance tracks: rotate each night's detections by its own random angle about the patch centre (and mirror half the
    nights).  Real movers no longer line up; the density of dots stays the same.  Returns the night count of each track."""
    rng = np.random.default_rng(seed)
    out = []
    for k in range(N_CONTROL):
        scr = []
        for n in sorted({d['night'] for d in dets}):
            a, flip = rng.uniform(0, 2 * math.pi), rng.random() < 0.5
            c, s_ = math.cos(a), math.sin(a)
            for d in dets:
                if d['night'] == n:
                    x = -d['x'] if flip else d['x']
                    scr.append(dict(d, x=c * x - s_ * d['y'], y=s_ * x + c * d['y']))
        out += [len(t['points']) for t in _link_field(scr)]
    return out


def link(log=print) -> dict:
    from validation import ledger
    doc = json.loads((OUT / 'plan.json').read_text())
    all_tracks, summary = [], {}
    for f in doc['fields']:
        src = json.loads((OUT / f"{f['id']}_sources.json").read_text())
        nd, ndinfo = _night_detections(src['images'], f['ra'], f['dec'])
        tr = _link_field(nd)
        for k, t in enumerate(tr):
            t['id'] = f"{f['id']}-t{k:02d}"
            t['field'] = f['id']
            t['n_nights'] = len(t['points'])
            t['detectors'] = sorted({d for p in t['points'] for d in p['detectors']})
        all_tracks += tr
        ctl = _control(nd, seed=1000 + int(f['id'][3:]))
        summary[f['id']] = {**ndinfo, 'night_detections': len(nd), 'nights': len({d['night'] for d in nd}), 'tracks': len(tr),
                            'tracks_4plus': sum(1 for t in tr if t['n_nights'] >= 4),
                            'chance_tracks_per_run': round(len(ctl) / N_CONTROL, 2), 'chance_tracks_4plus_per_run': round(sum(1 for n in ctl if n >= 4) / N_CONTROL, 2)}
        log(f"{f['id']}: {ndinfo['epochs']} epochs, {ndinfo['paired_detections']} dots seen in both images of an epoch, {ndinfo['fixed_sources_removed']} fixed; "
            f"{len(nd)} left, over {summary[f['id']]['nights']} epochs -> {len(tr)} tracks "
            f"({summary[f['id']]['tracks_4plus']} on 4+ nights); chance alone gives {summary[f['id']]['chance_tracks_per_run']} "
            f"({summary[f['id']]['chance_tracks_4plus_per_run']} on 4+ nights)")
    out = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
           'settings': {'same_night_arcsec': SAME_NIGHT_ARCSEC, 'rate_arcsec_h': [RATE_MIN, RATE_MAX], 'track_tol_arcsec': TRACK_TOL_ARCSEC,
                        'track_rms_max': TRACK_RMS_MAX, 'track_nights': TRACK_NIGHTS, 'flux_ratio_max': FLUX_RATIO_MAX, 'pair_max_h': PAIR_MAX_H,
                        'accel_max': ACCEL_MAX, 'min_span_h': MIN_SPAN_H, 'linker': 'grow step by step, curved fit from 4 points (version 3)'},
           'statement': 'Tracks found from SPHEREx detections alone. No asteroid catalogue was consulted before this file was locked.',
           'version': 3,
           'history': ('Version 1 (24-arcminute patches) removed every dot near a Gaia or WISE star. In these fields the ~10,000 catalogue stars per patch '
                       'covered almost the whole image, so nothing was left (validation/asteroids/v1/, ledger entry 24). '
                       'Version 2 removes fixed sources by comparing epochs with each other, as moving-object surveys do, and uses 60-arcminute patches; '
                       'on six patches it recovered 1 of 3 known asteroids brighter than V 17 and none fainter (validation/asteroids/v2_calibration/, ledger entry 25). '
                       'Those six patches were then used to tune the linker on known asteroids (version 3: tracks grow step by step and may curve). '
                       'Version 3 is run blind on six different patches; the tuning patches are not counted in its result.'),
           'control': (f'Each field was also linked {N_CONTROL} times after rotating each night\'s detections by a random angle about the field centre '
                       '(and mirroring half the nights): the number of tracks that appear by chance.'),
           'summary': summary, 'tracks': all_tracks}
    (OUT / 'tracks.json').write_text(json.dumps(out, indent=1))
    e = ledger.append('asteroids:tracks', [OUT / 'tracks.json', OUT / 'plan.json', ROOT / 'validation' / 'asteroids.py'],
                      note='Moving-object tracks from SPHEREx alone, locked before any asteroid catalogue was consulted.')
    log(f"{len(all_tracks)} tracks in {len(doc['fields'])} fields; locked as ledger entry {e['seq']}")
    return out


# ---------------------------------------------------------------------------
# 5. known asteroids (SkyBoT), only after the lock
# ---------------------------------------------------------------------------

def _skybot(ra, dec, mjd, radius_deg):
    from pipeline.astrometry import mjd_to_iso
    params = {'-ep': mjd_to_iso(mjd).rstrip('Z'), '-ra': f'{ra:.6f}', '-dec': f'{dec:.6f}', '-rd': f'{radius_deg:.4f}', '-mime': 'json',
              '-output': 'basic', '-loc': '500', '-from': 'spherex-viewer'}
    for k in range(4):
        try:
            r = requests.get(SKYBOT, params=params, timeout=90)
            if r.status_code == 204 or not r.text.strip():
                return []
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(3 * (k + 1))
    raise RuntimeError('SkyBoT did not answer')


def _hms(s, hours):
    p = [float(v) for v in s.split()]
    sign = -1 if s.strip().startswith('-') else 1
    v = abs(p[0]) + p[1] / 60 + p[2] / 3600
    return sign * v * (15 if hours else 1)


def known(log=print) -> dict:
    from validation import ledger
    ledger.locked('asteroids:tracks', OUT / 'tracks.json')
    plan_doc = json.loads((OUT / 'plan.json').read_text())
    out = {}
    for f in plan_doc['fields']:
        src = json.loads((OUT / f"{f['id']}_sources.json").read_text())
        mj = sorted(im['mjd'] for im in src['images'])
        nights = []
        for m in mj:
            if not nights or m - nights[-1][-1] > EPOCH_GAP_D:
                nights.append([])
            nights[-1].append(m)
        nights = [float(np.mean(g)) for g in nights]
        epochs = []
        for m in nights:
            rows = _skybot(f['ra'], f['dec'], m, SIZE_ARCMIN / 60 / math.sqrt(2) + 0.02)
            bodies = []
            for r in rows:
                ra, dec = _hms(r['RA (hms)'], True), _hms(r['DEC (dms)'], False)
                x, y = _tangent(ra, dec, f['ra'], f['dec'])
                bodies.append({'name': r['Name'], 'class': r.get('Class'), 'V': r.get('VMag (mag)'), 'x': float(x), 'y': float(y),
                               'rate_ra': r.get('dRA (arcsec/h)'), 'rate_dec': r.get('dDEC (arcsec/h)'), 'delta_au': r.get('dg (ua)')})
            epochs.append({'mjd': m, 'bodies': bodies})
        out[f['id']] = epochs
        log(f"{f['id']}: {len(nights)} nights, known bodies per night {[len(e['bodies']) for e in epochs]}")
    (OUT / 'known.json').write_text(json.dumps(out))
    return out


# ---------------------------------------------------------------------------
# 6. report
# ---------------------------------------------------------------------------

def report(log=print) -> dict:
    from validation import ledger
    ledger.locked('asteroids:tracks', OUT / 'tracks.json')
    tracks = json.loads((OUT / 'tracks.json').read_text())['tracks']
    kn = json.loads((OUT / 'known.json').read_text())

    def _v(x):                                            # SkyBoT gives V as a number, but now and then as text
        try:
            return float(x)
        except (TypeError, ValueError):
            return None
    for epochs in kn.values():
        for e in epochs:
            for b in e['bodies']:
                b['V'] = _v(b['V'])
    plan_doc = json.loads((OUT / 'plan.json').read_text())
    half = SIZE_ARCMIN * 60 / 2 - 40                      # inside the cutout, with a 40" margin
    # each known body, at each night: the body's position, interpolated from the epoch list by name
    matched_bodies, results = {}, []
    for t in tracks:
        hits = {}
        for p in t['points']:
            ep = min(kn[t['field']], key=lambda e: abs(e['mjd'] - p['mjd']))
            dh = (p['mjd'] - ep['mjd']) * 24
            for b in ep['bodies']:
                bx = b['x'] + (b['rate_ra'] or 0) * dh
                by = b['y'] + (b['rate_dec'] or 0) * dh
                if math.hypot(p['x'] - bx, p['y'] - by) <= MATCH_ARCSEC:
                    hits[b['name']] = hits.get(b['name'], 0) + 1
        name = max(hits, key=hits.get) if hits else None
        ok = bool(name and hits[name] >= 2)
        if ok:
            matched_bodies.setdefault(t['field'], set()).add(name)
        info = None
        if ok:
            b = next(b for e in kn[t['field']] for b in e['bodies'] if b['name'] == name)
            info = {'name': name, 'class': b['class'], 'V': b['V'], 'delta_au': b['delta_au']}
        results.append({'id': t['id'], 'field': t['field'], 'n_nights': t['n_nights'], 'rate_arcsec_h': round(t['rate_arcsec_h'], 1), 'rms_arcsec': round(t['rms_arcsec'], 2),
                        'detectors': t['detectors'], 'snr_max': round(max(p['snr'] for p in t['points']), 1),
                        'known': info, 'first_mjd': t['points'][0]['mjd'], 'points': [{k: p[k] for k in ('mjd', 'x', 'y', 'snr', 'n_images', 'flux_ujy')} for p in t['points']]})
    # recovery: known bodies that were inside the cutout on 3+ of the imaged nights
    rec = []
    for f in plan_doc['fields']:
        epochs = kn[f['id']]
        names = {b['name'] for e in epochs for b in e['bodies']}
        for nme in names:
            seen = [b for e in epochs for b in e['bodies'] if b['name'] == nme and abs(b['x']) < half and abs(b['y']) < half]
            if len(seen) < TRACK_NIGHTS:
                continue
            rec.append({'field': f['id'], 'name': nme, 'V': seen[0]['V'], 'class': seen[0]['class'], 'found': nme in matched_bodies.get(f['id'], set())})
    bins = [(0, 17), (17, 18), (18, 19), (19, 20), (20, 30)]
    table = [{'V': f'{a}-{b}' if b < 30 else f'{a}+', 'n': sum(1 for r in rec if r['V'] is not None and a <= r['V'] < b),
              'found': sum(1 for r in rec if r['V'] is not None and a <= r['V'] < b and r['found'])} for a, b in bins]
    unknown = [r for r in results if not r['known']]
    summ = json.loads((OUT / 'tracks.json').read_text()).get('summary', {})
    chance = round(sum(v.get('chance_tracks_per_run', 0) for v in summ.values()), 1)
    chance4 = round(sum(v.get('chance_tracks_4plus_per_run', 0) for v in summ.values()), 1)
    doc = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'n_fields': len(plan_doc['fields']), 'n_tracks': len(results),
           'n_tracks_known': sum(1 for r in results if r['known']), 'n_tracks_unmatched': len(unknown), 'recovery_by_V': table,
           'n_known_in_view': len(rec), 'n_known_found': sum(r['found'] for r in rec), 'tracks': results, 'recovery': rec,
           'chance_tracks_expected': chance, 'chance_tracks_4plus_expected': chance4,
           'n_unmatched_4plus': sum(1 for r in unknown if r['n_nights'] >= 4),
           'note': ('A track that matches no known asteroid is a candidate, not a discovery. It needs follow-up images and a report to the Minor Planet Center, '
                    'which this project has not made.')}
    (OUT / 'results.json').write_text(json.dumps(doc, indent=1))
    ledger.append('asteroids:results', [OUT / 'results.json', OUT / 'known.json'], note='Tracks matched to known asteroids after the lock.')
    log(f"{len(results)} tracks: {doc['n_tracks_known']} are known asteroids, {len(unknown)} match nothing known "
        f"({doc['n_unmatched_4plus']} on 4+ nights); chance alone is expected to give {chance} tracks ({chance4} on 4+ nights)")
    log('recovery of known asteroids in view on 3+ nights, by V: ' + ', '.join(f"V {r['V']}: {r['found']}/{r['n']}" for r in table))
    for r in unknown:
        log(f"  UNMATCHED {r['id']}: {r['n_nights']} nights, {r['rate_arcsec_h']}\"/h, rms {r['rms_arcsec']}\", S/N up to {r['snr_max']}, detectors {r['detectors']}")
    return doc


if __name__ == '__main__':
    {'plan': plan, 'fetch': fetch, 'detect': detect, 'link': link, 'known': known, 'report': report}[sys.argv[1] if len(sys.argv) > 1 else 'plan']()
