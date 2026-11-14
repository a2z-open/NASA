"""Build the cached field (display frames) and investigation for a curated target.

    python -m pipeline.build_curated epsilon-indi-b
    python -m pipeline.build_curated --all
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import glob
import json
import math
from pathlib import Path
import platform

import numpy as np

from .analysis import build_investigation, DETECTION_SNR
from .astrometry import mjd_to_iso, propagate, target_epoch_mjd
from .frames import grid_doc, make_frames, display_wcs, frame_stats
from .investigate import measure_epochs, track_from_catalog, track_from_fit, track_position
from .measure import gaia_field, reference_candidates
from .motion import fit_motion
from .investigate import usable_positions
from .spherex import CACHE, RELEASES, ROOT, load_observation
from .targets import ORDER, TARGETS

DATA = ROOT / 'data' / 'targets'
GAIA_IDS = {'epsilon-indi-b': '6412596012146801152', 'barnards-star': '4472832130942575872',
            'rw-aurigae': '156430817820015232', 'r-draconis': '1648328016354496384'}
# Real, unsaturated comparison stars in the same SPHEREx images, used to demonstrate the naive (mixed-wavelength)
# versus wavelength-matched comparison when the named target itself saturates.  Created with POST /api/investigations.
DEMOS = {'rw-aurigae': 'i3d564e91b603', 'r-draconis': 'ib1edeba1aaeb'}
KNOWN_BLENDS = {'rw-aurigae': 'RW Aur A and RW Aur B (Gaia DR3 156430822114424576) are 1.4 arcsec apart, far below one SPHEREx pixel: always blended.',
                'epsilon-indi-b': 'Epsilon Indi Ba (T1) and Bb (T6) are separated by well under one SPHEREx pixel; the measurement is their combined light.'}


def jdump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=None, separators=(',', ':'), allow_nan=False, default=_default))


def _default(o):
    if isinstance(o, (np.floating,)):
        return float(o) if math.isfinite(float(o)) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def sanitize(o):
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [sanitize(v) for v in o]
    if isinstance(o, np.generic):
        return sanitize(o.item())
    return o


def merged_manifest(slug):
    m = json.loads((DATA / slug / 'archive_manifest.json').read_text())
    exp = ROOT / 'validation' / 'experiments' / slug / 'result.json'
    if exp.exists():   # held-out visit has been revealed: it may join the public investigation
        for v in m['visits']:
            v['sealed'] = False
            v['revealed_after_experiment'] = True
    return m


def software_versions():
    import astropy, scipy
    try:
        import spiff
        spiff_v = getattr(spiff, '__version__', '0.1.1') + ' @ 5252fc4'
    except Exception:  # noqa: BLE001
        spiff_v = None
    return [{'name': 'astropy', 'version': astropy.__version__}, {'name': 'numpy', 'version': np.__version__},
            {'name': 'scipy', 'version': scipy.__version__}, {'name': 'SPIFF (templates, binning)', 'version': spiff_v},
            {'name': 'python', 'version': platform.python_version()}]


def comoving_stack(paths, track, size_arcmin=3.0, pixel_arcsec=3.075):
    """Shift-and-stack in the source's rest frame: each exposure is reprojected onto a grid centred on the
    track position at that exposure's epoch, median-subtracted, and inverse-variance averaged."""
    from scipy.ndimage import map_coordinates
    acc = None
    wsum = None
    n = 0
    for p in paths:
        o = load_observation(p, keep_epsf_zones=0)
        ra, dec = track_position(track, o.mjd)
        w, size = display_wcs(ra, dec, size_arcmin, pixel_arcsec)
        yy, xx = np.indices((size, size), dtype=float)
        gra, gdec = w.pixel_to_world_values(xx, yy)
        x, y = o.wcs.world_to_pixel_values(gra, gdec)
        img = o.image.copy()
        bad = o.hard_mask()
        img[bad] = np.nan
        med = np.nanmedian(img)
        arr = map_coordinates(img - med, [y, x], order=1, mode='constant', cval=np.nan)
        var = map_coordinates(np.where(bad, np.nan, o.variance), [y, x], order=1, mode='constant', cval=np.nan)
        ok = np.isfinite(arr) & np.isfinite(var) & (var > 0)
        if ok.mean() < 0.5:
            continue
        if acc is None:
            acc = np.zeros_like(arr)
            wsum = np.zeros_like(arr)
        acc[ok] += arr[ok] / var[ok]
        wsum[ok] += 1 / var[ok]
        n += 1
    if acc is None:
        return None, 0
    out = np.where(wsum > 0, acc / np.where(wsum > 0, wsum, 1), np.nan)
    return np.flipud(out), n


def build(slug, *, workers=8, reuse=False):
    t = TARGETS[slug]
    man = merged_manifest(slug)
    c = man['field_center']
    raw = CACHE / 'targets' / slug / 'raw'
    out = DATA / slug
    files = sorted(glob.glob(str(raw / '*.fits')))
    sealed = {p['id'] for p in man['products'] if p.get('sealed')} if any(v.get('sealed') for v in man['visits']) else set()
    files = [f for f in files if Path(f).stem not in sealed]
    print(f'{slug}: {len(files)} cutouts', flush=True)
    stars = gaia_field(c['ra'], c['dec'], 0.13, cache=out / 'gaia_field.json')
    # exclude the target and anything within 20" of its track from the reference set
    refs = reference_candidates(stars, exclude_ids=[GAIA_IDS.get(slug, '')])
    visits = [{'id': v['id'], 'mjd_start': v['mjd_start'], 'mjd_end': v['mjd_end'], 'start_utc': v['start_utc'],
               'end_utc': v['end_utc'], 'n_products': v['n_products'], 'releases': v['releases'],
               'per_detector': v['per_detector'], 'sealed': v.get('sealed', False)} for v in man['visits']]
    cat_track = track_from_catalog(t.astrometry)
    stars_all = stars
    stars = [s_ for s_ in stars_all if s_['source_id'] != GAIA_IDS.get(slug)]   # never deblend the target from itself
    first_mjd = min(p['t_min'] for p in man['products'])
    fixed = track_position(cat_track, first_mjd)   # one fixed sky position: where the source was at the first visit

    rows_cache = CACHE / 'targets' / slug / 'rows.json'
    if reuse and rows_cache.exists():
        saved = json.loads(rows_cache.read_text())
        rows, track_note = saved['rows'], saved['track_note']
        used = []
    else:
        rows = measure_epochs(files, cat_track, refs, fixed=fixed, workers=workers, stars=stars)
        used = usable_positions(rows)
        track_note = f'catalogue track ({t.astrometry.source})'
    if len(used) >= 10:
        mjd = [r['mjd'] for r in used]
        f = fit_motion(mjd, [r['position']['ra'] for r in used], [r['position']['dec'] for r in used],
                       [r['position']['sigma_arcsec'] for r in used], model='linear_parallax' if len({round(m / 60) for m in mjd}) >= 3 else 'linear')
        pm = math.hypot(f.params.get('pmra', 0), f.params.get('pmdec', 0)) * 1000
        if pm > 50:   # follow the SPHEREx-measured track for photometry (independent of the catalogue)
            sp_track = track_from_fit(f)
            rows = measure_epochs(files, sp_track, refs, fixed=fixed, workers=workers, stars=stars)
            track_note = f'SPHEREx-fitted track ({f.model})'
    rows_cache.write_text(json.dumps(sanitize({'rows': rows, 'track_note': track_note})))
    catalog = {'source': t.astrometry.source, 'pmra_masyr': t.astrometry.pmra_masyr, 'pmdec_masyr': t.astrometry.pmdec_masyr,
               'parallax_mas': t.astrometry.parallax_mas, 'pmra_err': t.astrometry.pmra_err, 'pmdec_err': t.astrometry.pmdec_err,
               'parallax_err': t.astrometry.parallax_err}
    src_pos = track_position(cat_track, 61040.0)
    provenance = {
        'datasets': [{'name': 'SPHEREx DR1 Spectral Images', 'doi': RELEASES['spherex_dr1']['doi'], 'citation': RELEASES['spherex_dr1']['citation']},
                     {'name': 'SPHEREx QR3 Spectral Images', 'doi': None, 'citation': RELEASES['spherex_qr3']['citation']}],
        'catalogs': [{'name': t.astrometry.source, 'url': t.astrometry.source_url},
                     {'name': 'Gaia DR3 (registration and context)', 'url': 'https://doi.org/10.1051/0004-6361/202243940'}],
        'software': software_versions(), 'n_files': len(rows), 'manifest_url': f'/files/targets/{slug}/provenance.json',
        'photometry_track': track_note, 'fixed_position': {'ra': fixed[0], 'dec': fixed[1], 'epoch_utc': mjd_to_iso(first_mjd)},
    }
    inv = build_investigation(
        rows, inv_id=slug, kind='curated', title=t.title, field_id=slug,
        source={'ra': src_pos[0], 'dec': src_pos[1], 'label': t.title, 'epoch_note': 'catalogue position propagated to 2026.0',
                'catalog': t.astrometry.__dict__},
        visits=visits, identification=t.astrometry.source.split(' (')[0], catalog=catalog, catalog_stars=stars,
        known_blend=KNOWN_BLENDS.get(slug), extra_limitations=list(t.notes), provenance=provenance)
    stars = stars_all
    # Frames
    vmap = {}
    for p in man['products']:
        vmap[p['id']] = p['visit']
    old_field = out / 'field.json'
    if reuse and old_field.exists():
        prev = json.loads(old_field.read_text())
        frames, errors = prev['frames'], [None] * prev.get('frame_errors', 0)
        for fr in frames:
            fr['file'] = fr['data_url'].rsplit('/', 1)[1]
    else:
        frames, errors = make_frames(files, c['ra'], c['dec'], man['field_size_arcmin'], out / 'frames', visits=vmap, workers=workers)
    for fr in frames:
        fr['data_url'] = f"/files/targets/{slug}/frames/{fr.pop('file')}"
    field = {
        'field_id': slug, 'kind': 'curated', 'title': t.title, 'ra': c['ra'], 'dec': c['dec'], 'fov_arcmin': man['field_size_arcmin'],
        'data_state': 'cached', 'message': None, 'progress': None,
        'grid': grid_doc(c['ra'], c['dec'], man['field_size_arcmin']),
        'archive': {'n_products': len(man['products']), 'collections': man['collections'], 'queried_utc': man['queried_utc'], 'visits': visits},
        'frames': frames, 'frame_errors': len(errors),
        'catalog': [s for s in stars if s.get('ra') is not None],
        'catalog_epoch_mjd': 57388.5,
        'investigation_id': slug,
    }
    # Co-moving stacks for the cold/faint target demonstration
    stacks = []
    if reuse and old_field.exists():
        stacks = prev.get('stacks', [])
    elif slug in ('wise-0855', 'epsilon-indi-b'):
        trk = cat_track if slug == 'wise-0855' else track_from_catalog(t.astrometry)
        groups = [('short', 'D1–D3 (0.75–2.4 µm)', {1, 2, 3}), ('long', 'D6 (4.4–5.0 µm)', {6}), ('mid', 'D5 (3.8–4.4 µm)', {5})]
        det_of = {r['product_id']: r['detector'] for r in rows if r.get('product_id')}
        for key, label, dets in groups:
            ps = [f for f in files if det_of.get(Path(f).stem) in dets]
            arr, n = comoving_stack(ps, trk)
            if arr is None:
                continue
            fn = f'stack-{key}.bin'
            arr.astype('<f4').tofile(out / 'frames' / fn)
            stacks.append({'id': f'stack-{key}', 'label': label, 'n_frames': n, 'data_url': f'/files/targets/{slug}/frames/{fn}',
                           'nx': arr.shape[1], 'ny': arr.shape[0], 'pixel_arcsec': 3.075, 'dtype': 'float32', 'row0': 'north',
                           'stats': frame_stats(arr), 'centered_on': 'the source track at each exposure epoch (co-moving)',
                           'note': 'Shift-and-stack in the source rest frame; background stars smear, a co-moving source sharpens.'})
    if slug == 'wise-0855':
        for st in stacks:
            if st['id'] == 'stack-short':
                st['note'] = ("Shift-and-stack in WISE 0855's rest frame. Light just east of the centre is the G = 16.3 Gaia star about 8\u2033 "
                              "away, fixed on the sky and therefore smeared here; joint PSF fitting attributes the short-wavelength flux to it, "
                              "not to WISE 0855 (see the cold-object table).")
    field['stacks'] = stacks
    if slug == 'wise-0855':
        inv['cold_search'] = wise0855_summary(inv)
    demo_path = ROOT / 'data' / 'investigations' / f'{DEMOS.get(slug, "none")}.json'
    if demo_path.exists():
        demo = json.loads(demo_path.read_text())
        v = demo.get('variability') or {}
        inv['demonstration'] = {
            'investigation_id': demo['id'], 'title': demo['title'],
            'why': (f"{t.title} saturates SPHEREx, so its own variability cannot be measured here. The same comparison is shown on a "
                    f"real, unsaturated star in the same images: a naive time-ordered light curve mixes wavelengths, while a "
                    f"wavelength-matched comparison isolates genuine change."),
            'naive_max_ratio': (v.get('naive') or {}).get('max_ratio'),
            'matched_visit_pairs': (v.get('matched') or {}).get('visit_pairs'), 'variability_status': v.get('status'),
        }
    jdump(out / 'field.json', sanitize(field))
    jdump(out / 'investigation.json', sanitize(inv))
    prov = {'target': slug, 'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'datasets': provenance['datasets'],
            'files': [{'product_id': r.get('product_id'), 'archive_url': r.get('archive_url'), 'sha256': r.get('sha256'),
                       'mjd': r.get('mjd'), 'detector': r.get('detector'), 'release': r.get('release'),
                       'wavelength_um': r.get('wavelength_um'), 'flags_near_source': r.get('flags'),
                       'cutout_url': next((fr['cutout_url'] for fr in frames if fr['id'] == r.get('product_id')), None)}
                      for r in rows],
            'processing': ['IRSA SIA2 discovery (spherex_dr1, spherex_qr3)', 'IRSA cutout service, 10 arcmin',
                           'native-pixel ePSF fits (release EPSF extension)', 'Gaia DR3 shift registration',
                           'spectral WCS (WAVE-TAB, key W) per-pixel wavelength', 'MJy/sr x OMEGA_MEDIAN -> microjansky']}
    jdump(out / 'provenance.json', sanitize(prov))
    print(f"{slug}: {inv['summary']['headline']} | frames {len(frames)} (errors {len(errors)}) | stacks {len(stacks)}", flush=True)
    return inv


def wise0855_summary(inv):
    """Forced-photometry stacking at the propagated track: is the coldest brown dwarf detected?"""
    pts = (inv.get('spectrum') or {}).get('points') or []
    groups = [('0.75–2.42 µm (D1–D3)', 0.7, 2.42), ('2.42–3.83 µm (D4)', 2.42, 3.83), ('3.83–4.42 µm (D5)', 3.83, 4.42),
              ('4.42–5.00 µm (D6)', 4.42, 5.01), ('4.6–5.0 µm (peak of a Y dwarf)', 4.6, 5.01)]
    out = []
    for label, lo, hi in groups:
        sel = [p for p in pts if lo <= p['wavelength_um'] < hi]
        if not sel:
            out.append({'band': label, 'n': 0, 'flux_ujy': None, 'flux_err_ujy': None, 'snr': None, 'detected': False})
            continue
        w = np.array([1 / p['flux_err_ujy'] ** 2 for p in sel])
        f = np.array([p['flux_ujy'] for p in sel])
        mean = float(np.sum(w * f) / w.sum())
        err = float(1 / math.sqrt(w.sum()))
        chi2r = float(np.sum(w * (f - mean) ** 2) / max(len(f) - 1, 1))
        err *= math.sqrt(max(chi2r, 1))
        snr = mean / err
        out.append({'band': label, 'n': len(sel), 'flux_ujy': mean, 'flux_err_ujy': err, 'snr': snr,
                    'detected': snr >= DETECTION_SNR, 'upper_limit_3sigma_ujy': (mean + 3 * err) if snr < DETECTION_SNR else None,
                    'ab_mag': (23.9 - 2.5 * math.log10(mean)) if mean > 0 and snr >= DETECTION_SNR else None})
    return {'method': 'Inverse-variance mean of forced ePSF photometry at the Kirkpatrick et al. (2021) track (proper motion + parallax) '
                      'in each exposure, grouped by wavelength. Detection threshold S/N >= 5 (pre-declared).', 'bands': out}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('slug', nargs='?')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--reuse', action='store_true', help='re-run the analysis on saved measurements and frames')
    a = ap.parse_args()
    for s in (ORDER if a.all else [a.slug]):
        build(s, reuse=a.reuse)
