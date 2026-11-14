"""Barnard's Star saturates SPHEREx, so its core cannot be centroided.  Its halo can.

A locked test on the visit that was sealed in the first session and never downloaded:

    python -m validation.barnard_halo lock     # reference positions from visit 1, the rule, the list of sealed exposures
    python -m validation.barnard_halo open     # refuses unless the lock is intact; then downloads and scores

Method: for each exposure, the centre of light of the unsaturated ring 3 to 9 pixels from the star.  A pixel is
used only if its mirror image through the trial centre is usable too, so masked pixels cannot pull the centre.
Visits 1 and 3 are one year apart, at the same season, so parallax cancels and the spacecraft has the same
orientation; visit 2 (opposite orientation) showed a 1.7 arcsecond sideways offset and is not used.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

from pipeline import spherex
from pipeline.measure import gaia_field, gaia_positions, reference_candidates, register
from pipeline.spherex import flag_mask, load_observation
from validation import ledger

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation' / 'experiments' / 'barnards-star-halo'
RAW = ROOT / '.parallax-cache' / 'targets' / 'barnards-star' / 'raw'
UNSEALED = ROOT / '.parallax-cache' / 'targets' / 'barnards-star' / 'unsealed-visit-3'
RA0, DEC0, SIZE_ARCMIN = 269.448, 4.74, 10.0
RING_PX, BG_PX, MIN_PIXELS = (3.0, 9.0), (13.0, 17.0), 60
PER_DETECTOR = 6
PASS_ARCSEC = 1.5            # a quarter of a pixel


def _gaia():
    gaia = gaia_field(RA0, DEC0, 0.12, gmax=18.5, cache=OUT / 'gaia_field.json')
    star = max((s for s in gaia if s['pmra'] is not None), key=lambda s: math.hypot(s['pmra'], s['pmdec']))
    return star, reference_candidates([s for s in gaia if s['source_id'] != star['source_id']])


def halo_centre(obs, x0: float, y0: float):
    bad = obs.hard_mask() | ((obs.flags & flag_mask(obs.flag_names, {'BLOOM', 'OVERFLOW', 'NONLINEAR', 'SUR_ERROR', 'PERSIST', 'GHOST'})) != 0)
    ny, nx = obs.shape
    yy, xx = np.indices(obs.shape)
    cx, cy, n = x0, y0, 0
    for _ in range(4):
        r = np.hypot(xx - cx, yy - cy)
        sky = (r > BG_PX[0]) & (r < BG_PX[1]) & ~bad
        if sky.sum() < 30:
            return None
        bg = np.nanmedian(obs.image[sky])
        ring = (r >= RING_PX[0]) & (r <= RING_PX[1]) & ~bad
        mx, my = np.rint(2 * cx - xx).astype(int), np.rint(2 * cy - yy).astype(int)
        inside = (mx >= 0) & (mx < nx) & (my >= 0) & (my < ny)
        sym = np.zeros_like(ring)
        sym[inside] = ring[my[inside], mx[inside]]
        use = ring & sym
        n = int(use.sum())
        w = np.clip(obs.image[use] - bg, 0, None)
        if n < MIN_PIXELS or w.sum() <= 0:
            return None
        cx, cy = float(np.sum(w * xx[use]) / w.sum()), float(np.sum(w * yy[use]) / w.sum())
    return cx, cy, n


def measure(files, star, refs) -> list[dict]:
    rows = []
    for f in sorted(files):
        obs = load_observation(f)
        reg, _ = register(obs, refs)
        if not reg.ok:
            continue
        pra, pdec = gaia_positions([star], obs.mjd)
        x0, y0 = (float(v) for v in obs.wcs.world_to_pixel_values(pra[0], pdec[0]))
        ny, nx = obs.shape
        if not (18 < x0 < nx - 18 and 18 < y0 < ny - 18):
            continue
        c = halo_centre(obs, x0 + reg.dx, y0 + reg.dy)
        if c is None:
            continue
        ra, dec = obs.wcs.pixel_to_world_values(c[0] - reg.dx, c[1] - reg.dy)
        rows.append({'product_id': obs.product_id, 'mjd': obs.mjd, 'detector': obs.detector, 'ra': float(ra), 'dec': float(dec), 'n_pixels': c[2]})
    return rows


def _per_detector(rows):
    out = {}
    for det in sorted({r['detector'] for r in rows}):
        sel = [r for r in rows if r['detector'] == det]
        out[str(det)] = {'n': len(sel), 'ra': float(np.median([r['ra'] for r in sel])), 'dec': float(np.median([r['dec'] for r in sel])),
                         'mjd': float(np.median([r['mjd'] for r in sel]))}
    return out


def lock(log=print) -> None:
    star, refs = _gaia()
    rows = [r for r in measure(RAW.glob('*.fits'), star, refs) if r['mjd'] < 61000]            # visit 1 only (Aug-Oct 2025)
    prods = [p for p in spherex.search(RA0, DEC0) if p.t_min > 61250]                           # the sealed visit (Aug-Sep 2026)
    chosen = []
    for det in range(1, 7):
        chosen += sorted((p for p in prods if p.detector == det), key=lambda p: p.t_min)[:PER_DETECTOR]
    doc = {'target': "Barnard's Star", 'gaia_source_id': star['source_id'],
           'method': 'centre of light of the unsaturated halo (ring 3-9 px, mirror-symmetric pixels only, sky from 13-17 px), registered to Gaia DR3',
           'reference_visit': {'n_exposures': len(rows), 'per_detector': _per_detector(rows)},
           'sealed_products': [p.to_dict() for p in chosen], 'selection_rule': f'the {PER_DETECTOR} earliest exposures of each detector after MJD 61250',
           'prediction': 'For each detector, the halo centre in the sealed visit minus the halo centre in visit 1 equals the displacement Gaia DR3 '
                         '(proper motion and parallax) gives between the two median dates. The result is the median over detectors.',
           'pass_rule': {'max_difference_arcsec': PASS_ARCSEC, 'statement': 'PASS if the measured displacement differs from the Gaia displacement by at most 1.5 arcseconds (a quarter of a pixel).'},
           'disclosures': ['No pixel of the sealed visit has been downloaded or viewed.',
                           'Visit 2 was examined: its halo centre is 1.7 arcseconds from the Gaia track in RA, in the opposite spacecraft orientation. It is not used.',
                           'Gaia DR3 supplies the expected displacement. This tests the halo method, not Gaia.']}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'protocol.json').write_text(json.dumps(doc, indent=1))
    e = ledger.append('barnard-halo-protocol', [OUT / 'protocol.json', Path(__file__)], note='Locked before any sealed exposure of Barnard\'s Star was downloaded.')
    log(f'reference: {len(rows)} exposures in visit 1; {len(chosen)} sealed exposures chosen; locked as ledger entry {e["seq"]} ({e["hash"][:12]})')


def open_(log=print) -> None:
    lockrec = ledger.locked('barnard-halo-protocol', OUT / 'protocol.json')
    ledger.locked('barnard-halo-protocol', Path(__file__))
    proto = json.loads((OUT / 'protocol.json').read_text())
    star, refs = _gaia()
    prods = [spherex.Product(**{k: v for k, v in p.items() if k not in ('id', 'processing_version')}) for p in proto['sealed_products']]
    done, failures = spherex.fetch_many(prods, RA0, DEC0, SIZE_ARCMIN, UNSEALED, workers=6)
    rows = measure(UNSEALED.glob('*.fits'), star, refs)
    new, ref = _per_detector(rows), proto['reference_visit']['per_detector']
    cosd = math.cos(math.radians(DEC0))
    per = []
    for det in sorted(set(new) & set(ref)):
        a, b = ref[det], new[det]
        meas = ((b['ra'] - a['ra']) * cosd * 3600, (b['dec'] - a['dec']) * 3600)
        (ra1, de1), (ra2, de2) = gaia_positions([star], a['mjd']), gaia_positions([star], b['mjd'])
        pred = ((ra2[0] - ra1[0]) * cosd * 3600, (de2[0] - de1[0]) * 3600)
        per.append({'detector': int(det), 'n_ref': a['n'], 'n_new': b['n'], 'years': (b['mjd'] - a['mjd']) / 365.25,
                    'measured': meas, 'predicted': pred, 'difference_arcsec': math.hypot(meas[0] - pred[0], meas[1] - pred[1])})
    mx, my = float(np.median([p['measured'][0] for p in per])), float(np.median([p['measured'][1] for p in per]))
    px, py = float(np.median([p['predicted'][0] for p in per])), float(np.median([p['predicted'][1] for p in per]))
    yrs = float(np.median([p['years'] for p in per]))
    spread = 1.4826 * float(np.median(np.abs(np.array([p['difference_arcsec'] for p in per]) - np.median([p['difference_arcsec'] for p in per])))) if len(per) > 1 else None
    diff = math.hypot(mx - px, my - py)
    res = {'locked_entry': lockrec['seq'], 'locked_hash': lockrec['hash'], 'locked_time_utc': lockrec['time_utc'], 'n_downloaded': len(done),
           'n_failed': len(failures), 'n_measured': len(rows), 'per_detector': per, 'years_between': yrs,
           'measured_shift_arcsec': [mx, my], 'predicted_shift_arcsec': [px, py], 'measured_total_arcsec': math.hypot(mx, my),
           'predicted_total_arcsec': math.hypot(px, py), 'difference_arcsec': diff, 'detector_scatter_arcsec': spread,
           'motion_arcsec_per_year': math.hypot(mx, my) / yrs, 'gaia_motion_arcsec_per_year': math.hypot(px, py) / yrs,
           'passed': bool(diff <= proto['pass_rule']['max_difference_arcsec'])}
    (OUT / 'result.json').write_text(json.dumps(res, indent=1))
    log(f"{len(done)} downloaded ({len(failures)} failed), {len(rows)} measured, {len(per)} detectors")
    for p in per:
        log(f"   D{p['detector']}: measured ({p['measured'][0]:+.2f}, {p['measured'][1]:+.2f})  Gaia ({p['predicted'][0]:+.2f}, {p['predicted'][1]:+.2f})  differ by {p['difference_arcsec']:.2f}\"")
    log(f"measured {res['measured_total_arcsec']:.2f}\" in {yrs:.2f} yr; Gaia {res['predicted_total_arcsec']:.2f}\"; difference {diff:.2f}\"; PASS={res['passed']}")


if __name__ == '__main__':
    {'lock': lock, 'open': open_}[sys.argv[1]]()
