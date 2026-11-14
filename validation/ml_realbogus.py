"""A machine-learning "real or artefact" scorer for single-exposure detections, honestly tested.

    python -m validation.ml_realbogus

Survey pipelines (ZTF's real/bogus classifiers, for example) train a model to tell a real point of light from an
artefact, then use it to look deeper.  The same here, at small scale:

  positives  SYNTHETIC point sources, built from each exposure's own ePSF, added to real SPHEREx exposures of the
             distant-world fields at S/N 3 to 20, then detected by the normal pipeline
  negatives  every other detection in those exposures that no Gaia or WISE catalogue explains (cosmic rays, artefacts,
             noise), minus anything within 12" of the known dwarf planet's track
  test 1     train on three bodies' fields, test on the fourth (leave-one-field-set-out): ROC AUC on synthetic vs artefacts
  test 2     the REAL detections of the dwarf planets (never used in training): how are they ranked among artefacts?

The model only ranks.  No detection is accepted or rejected by it in any locked result.
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation' / 'distant'
CACHE = ROOT / '.parallax-cache' / 'distant'
BODIES = ['makemake', 'haumea', 'eris', 'pluto']
PER_BODY = 60           # exposures sampled per body's fields
N_INJECT = 6            # synthetic sources per exposure
FEATURES = ['snr', 'peak_snr', 'chi2r', 'log_flux', 'wavelength_um', 'detector', 'n_flags', 'peak_fit_offset_px', 'nearest_catalogue_px',
            'catalogue_within_3px', 'flux_snr_ratio']


def _one(args):
    path, gaia, wise, seed, body_track = args
    from pipeline import distant, hunt
    from pipeline.measure import gaia_positions, measure_position, reference_candidates, register
    from pipeline.spherex import load_observation
    rng = np.random.default_rng(seed)
    try:
        obs = load_observation(path)
    except Exception:  # noqa: BLE001
        return []
    refs = reference_candidates([s for s in gaia if s.get('g') is not None and s['g'] < 18.5])
    reg, _ = register(obs, refs)
    if not reg.ok:
        return []
    ny, nx = obs.shape
    cx, cy = [], []
    if gaia:
        gra, gdec = gaia_positions(gaia, obs.mjd)
        gx, gy = obs.wcs.world_to_pixel_values(gra, gdec)
        cx += list(gx + reg.dx)
        cy += list(gy + reg.dy)
    if wise:
        wx, wy = obs.wcs.world_to_pixel_values([s['ra'] for s in wise], [s['dec'] for s in wise])
        cx += list(wx + reg.dx)
        cy += list(wy + reg.dy)
    cx, cy = np.asarray(cx, float), np.asarray(cy, float)
    # inject synthetic sources away from catalogued stars, at S/N 3-20 (flux from the local noise)
    noise = float(np.sqrt(np.nanmedian(obs.variance)))
    inj = []
    for _ in range(N_INJECT * 6):
        if len(inj) >= N_INJECT:
            break
        x, y = rng.uniform(12, nx - 12), rng.uniform(12, ny - 12)
        if cx.size and np.min(np.hypot(cx - x, cy - y)) < 4:
            continue
        snr = rng.uniform(3, 20)
        ra, dec = obs.wcs.pixel_to_world_values(x - reg.dx, y - reg.dy)
        flux = snr * noise * 2.8 * obs.ujy_per_unit       # ~ S/N for a point source spread over ~8 pixels
        inj.append({'ra': float(ra), 'dec': float(dec), 't0': obs.mjd, 'pmra': 0.0, 'pmdec': 0.0, 'flux_ujy': float(flux), 'x': x, 'y': y})
    hunt.inject_sources(obs, inj)
    snr_map, _ = distant._snr_map(obs)
    if snr_map is None:
        return []
    rows = []
    for x, y, s in hunt.find_peaks(snr_map, 3.0, edge=4):
        d_cat = float(np.min(np.hypot(cx - x, cy - y))) if cx.size else 99.0
        if d_cat <= distant.STAR_RADIUS_PX:
            continue                                               # explained by a catalogue: not part of this problem
        f, pos = measure_position(obs, reg, x, y)
        if pos is None or not f.ok:
            continue
        lam, _ = obs.wavelength_at(f.x, f.y)
        label = 1 if any(math.hypot(i['x'] - x, i['y'] - y) < 1.5 for i in inj) else 0
        on_track = False
        if body_track is not None:
            bra, bdec = np.interp(obs.mjd, body_track['mjd'], body_track['ra']), np.interp(obs.mjd, body_track['mjd'], body_track['dec'])
            on_track = math.hypot((pos['ra'] - bra) * math.cos(math.radians(bdec)), pos['dec'] - bdec) * 3600 < 12
        rows.append({'label': label, 'real_body': bool(on_track and label == 0), 'snr': float(f.snr), 'peak_snr': float(s),
                     'chi2r': float(f.chi2r) if math.isfinite(f.chi2r) else 50.0,
                     'log_flux': math.log10(max(abs(f.flux * obs.ujy_per_unit), 1e-3)), 'wavelength_um': float(lam) if math.isfinite(lam) else 1.5,
                     'detector': obs.detector, 'n_flags': len(f.flags), 'peak_fit_offset_px': math.hypot(f.x - x, f.y - y),
                     'nearest_catalogue_px': min(d_cat, 30.0), 'catalogue_within_3px': int(np.sum(np.hypot(cx - x, cy - y) < 3)) if cx.size else 0,
                     'flux_snr_ratio': float(f.flux / f.flux_err / max(f.snr, 1e-3)) if f.flux_err and math.isfinite(f.flux_err) and f.flux_err > 0 else 1.0})
    return rows


def collect(log=print) -> dict:
    from pipeline import ephem
    data = {}
    rng = np.random.default_rng(7)
    for body in BODIES:
        plan = json.loads((OUT / body / 'plan.json').read_text())
        eph = ephem.horizons(ephem.BODIES[body]['command'], '2025-04-20', '2026-11-05', '6 h')
        track = {'mjd': eph['mjd'].tolist(), 'ra': eph['ra'].tolist(), 'dec': eph['dec'].tolist()}
        jobs = []
        for b in plan['bins']:
            folder = CACHE / body / b['id']
            gaia = json.loads((folder / 'gaia_all.json').read_text()) if (folder / 'gaia_all.json').is_file() else []
            wise = json.loads((folder / 'catwise.json').read_text()) if (folder / 'catwise.json').is_file() else []
            for f in sorted(folder.glob('*.fits')):
                jobs.append((str(f), gaia, wise, int(rng.integers(1e9)), track))
        pick = rng.choice(len(jobs), size=min(PER_BODY, len(jobs)), replace=False)
        with ProcessPoolExecutor(max_workers=8) as ex:
            rows = [r for rr in ex.map(_one, [jobs[i] for i in pick], chunksize=2) for r in rr]
        data[body] = rows
        log(f"{body}: {len(pick)} exposures, {sum(r['label'] for r in rows)} synthetic detected, "
            f"{sum(1 for r in rows if not r['label'] and not r['real_body'])} artefact detections, {sum(r['real_body'] for r in rows)} real body detections")
    return data


def evaluate(data, log=print) -> dict:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score

    def xy(rows, real_as_positive=False):
        rows = [r for r in rows if not r['real_body'] or real_as_positive]
        X = np.array([[r[k] for k in FEATURES] for r in rows], float)
        y = np.array([1 if (r['label'] or (real_as_positive and r['real_body'])) else 0 for r in rows])
        return X, y, rows
    folds = []
    for held in BODIES:
        train = [r for b in BODIES if b != held for r in data[b]]
        X, y, _ = xy(train)
        model = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, max_leaf_nodes=15, random_state=0).fit(X, y)
        Xt, yt, _ = xy(data[held])
        auc = roc_auc_score(yt, model.predict_proba(Xt)[:, 1]) if len(set(yt)) == 2 else None
        # the real dwarf-planet detections against the artefacts of the same fields (never trained on)
        real = [r for r in data[held] if r['real_body']]
        art = [r for r in data[held] if not r['label'] and not r['real_body']]
        real_auc = real_base = None
        if real and art:
            Xr = np.array([[r[k] for k in FEATURES] for r in real + art], float)
            yr = np.array([1] * len(real) + [0] * len(art))
            real_auc = roc_auc_score(yr, model.predict_proba(Xr)[:, 1])
            real_base = roc_auc_score(yr, Xr[:, FEATURES.index('snr')])
        # baseline: the plain signal-to-noise, which the pipeline already uses
        base = roc_auc_score(yt, Xt[:, FEATURES.index('snr')]) if len(set(yt)) == 2 else None
        folds.append({'held_out': held, 'n_train': int(len(y)), 'n_test': int(len(yt)), 'auc_synthetic': auc, 'auc_snr_only': base,
                      'n_real_body': len(real), 'n_artefacts': len(art), 'auc_real_body_vs_artefacts': real_auc, 'auc_real_body_snr_only': real_base})
        log(f"held out {held:9s}: AUC model {auc and round(auc, 3)}  (S/N alone {base and round(base, 3)})   real {held} detections vs artefacts: "
            f"AUC {real_auc and round(real_auc, 3)} (S/N alone {real_base and round(real_base, 3)}) over {len(real)} real and {len(art)} artefacts")
    return {'folds': folds}


def main(log=print) -> dict:
    cache = ROOT / '.parallax-cache' / 'ml_realbogus_rows.json'
    data = json.loads(cache.read_text()) if cache.is_file() else collect(log)
    cache.write_text(json.dumps(data))
    ev = evaluate(data, log)
    aucs = [f['auc_synthetic'] for f in ev['folds'] if f['auc_synthetic'] is not None]
    reals = [f['auc_real_body_vs_artefacts'] for f in ev['folds'] if f['auc_real_body_vs_artefacts'] is not None]
    base = [f['auc_snr_only'] for f in ev['folds'] if f['auc_snr_only'] is not None]
    rbase = [f['auc_real_body_snr_only'] for f in ev['folds'] if f.get('auc_real_body_snr_only') is not None]
    doc = {'synthetic': True, 'model': 'gradient-boosted decision trees (scikit-learn HistGradientBoostingClassifier)', 'features': FEATURES,
           'n_examples': {b: len(r) for b, r in data.items()}, 'folds': ev['folds'],
           'mean_auc_synthetic': float(np.mean(aucs)) if aucs else None, 'mean_auc_snr_only': float(np.mean(base)) if base else None,
           'mean_auc_real_body': float(np.mean(reals)) if reals else None,
           'mean_auc_real_body_snr_only': float(np.mean(rbase)) if rbase else None,
           'role': 'Ranks detections only. It is not used to accept or reject anything in a locked result.',
           'note': 'Positives are SYNTHETIC point sources added to real exposures. AUC 0.5 is guessing, 1.0 is perfect.'}
    (ROOT / 'validation' / 'ml_realbogus.json').write_text(json.dumps(doc, indent=1))
    log(f"mean AUC on held-out fields: model {doc['mean_auc_synthetic']:.3f}, S/N alone {doc['mean_auc_snr_only']:.3f}; "
        f"real dwarf-planet detections vs artefacts: {doc['mean_auc_real_body'] and round(doc['mean_auc_real_body'], 3)}")
    return doc


if __name__ == '__main__':
    main()
