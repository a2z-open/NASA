"""Make the "spot what moves" game images from two real SPHEREx exposures.

    .venv/bin/python -m tools.make_blink

For each level: two exposures of the same patch of sky, taken days apart, are resampled onto one shared
north-up grid (so every star lands on the same pixel in both) after registering each exposure on Gaia stars.
The moving body's position in each image comes from PARALLAX's own blind detection (validation/distant/<body>/blind.json),
not from an ephemeris.  Output: web/public/blink/<level>-a.png, -b.png and levels.json.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates

from pipeline.measure import reference_candidates, register
from pipeline.spherex import load_observation

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.parallax-cache' / 'distant'
OUT = ROOT / 'web' / 'public' / 'blink'
PIX = 6.15            # arcsec per output pixel (SPHEREx native)

LEVELS = [
    # (level id, body, exposure A, exposure B, width, height, where the body should sit as a fraction of width and height)
    ('makemake', 'makemake', '2025W52_2A_0525_1', '2026W01_1A_0533_1', 300, 200, (0.62, 0.42)),
    
]
FACTS = {
    'makemake': {'title': 'Makemake', 'what': 'a dwarf planet', 'note': 'Found in 2005. Twice as far as Pluto at this point in its orbit.'},
    'eris': {'title': 'Eris', 'what': 'a dwarf planet', 'note': 'The most massive dwarf planet. Its discovery in 2005 is why Pluto was reclassified.'},
}


def _find(body: str, obs_id: str) -> Path:
    hits = sorted((CACHE / body).glob(f'*/{obs_id}-D*.fits'))
    if not hits:
        raise FileNotFoundError(f'{obs_id} not cached for {body}')
    return hits[0]


def _wide(small: Path, ra: float, dec: float, size_arcmin: float = 40.0) -> Path:
    """A wider cutout of the same exposure from IRSA (same file the search used, bigger window), cached once."""
    from pipeline.spherex import USER_AGENT, validate_fits
    import requests
    out = ROOT / '.parallax-cache' / 'blink' / f'{small.stem}-{size_arcmin:.0f}arcmin.fits'
    if out.is_file():
        return out
    prov = json.loads(small.with_suffix('.prov.json').read_text())
    url = f"{prov['archive_url']}?center={ra:.7f},{dec:.7f}&size={size_arcmin:.4f}arcmin"
    import time
    for attempt in range(6):
        r = requests.get(url, timeout=300, headers={'User-Agent': USER_AGENT})
        if r.status_code < 500:
            break
        time.sleep(5 * (attempt + 1))
    r.raise_for_status()
    validate_fits(r.content)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    out.with_suffix('.prov.json').write_text(json.dumps({**prov, 'cutout_url': url, 'size_arcmin': size_arcmin,
                                                          'path': str(out.relative_to(ROOT)), 'bytes': len(r.content)}, indent=1))
    return out


def _pick_pair(dets: list[dict]) -> tuple[dict, dict]:
    """Two strong detections in the same visit, as far apart in time as possible (up to 6 days), similar wavelength."""
    best, score = None, -1.0
    for a in dets:
        for b in dets:
            dt = b['mjd'] - a['mjd']
            if not (0.5 < dt < 6) or a['snr'] < 8 or b['snr'] < 8:
                continue
            s = dt - 4 * abs(a['wavelength_um'] - b['wavelength_um'])
            if s > score:
                best, score = (a, b), s
    if best is None:
        raise RuntimeError('no usable pair')
    return best


def _tangent(ra, dec, ra0, dec0):
    """Gnomonic projection, arcsec: xi east, eta north."""
    ra, dec, ra0, dec0 = map(np.radians, (ra, dec, ra0, dec0))
    c = np.sin(dec0) * np.sin(dec) + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0)
    xi = np.cos(dec) * np.sin(ra - ra0) / c
    eta = (np.cos(dec0) * np.sin(dec) - np.sin(dec0) * np.cos(dec) * np.cos(ra - ra0)) / c
    return np.degrees(xi) * 3600, np.degrees(eta) * 3600


def _untangent(xi, eta, ra0, dec0):
    xi, eta = np.radians(np.asarray(xi) / 3600), np.radians(np.asarray(eta) / 3600)
    ra0, dec0 = math.radians(ra0), math.radians(dec0)
    rho = np.hypot(xi, eta)
    c = np.arctan(rho)
    with np.errstate(invalid='ignore', divide='ignore'):
        dec = np.arcsin(np.cos(c) * math.sin(dec0) + np.where(rho > 0, eta * np.sin(c) * math.cos(dec0) / rho, 0))
        ra = ra0 + np.arctan2(xi * np.sin(c), rho * math.cos(dec0) * np.cos(c) - eta * math.sin(dec0) * np.sin(c))
    return np.degrees(ra) % 360, np.degrees(dec)


def _render(path: Path, ra0, dec0, w, h, cx, cy, folder: Path | None = None):
    obs = load_observation(path)
    folder = folder or path.parent
    gaia = json.loads((folder / 'gaia_all.json').read_text()) if (folder / 'gaia_all.json').is_file() else []
    reg, _ = register(obs, reference_candidates([s for s in gaia if s.get('g') is not None and s['g'] < 18.5]))
    dx, dy = (reg.dx, reg.dy) if reg.ok else (0.0, 0.0)
    jj, ii = np.mgrid[0:h, 0:w]
    xi = (cx - ii) * PIX                    # east to the left
    eta = (cy - jj) * PIX                   # north up
    ra, dec = _untangent(xi, eta, ra0, dec0)
    x, y = obs.wcs.world_to_pixel_values(ra.ravel(), dec.ravel())
    img = obs.image.copy()
    bad = obs.hard_mask()
    med = float(np.nanmedian(img[~bad]))
    img = np.where(bad, med, img) - med
    noise = 1.4826 * float(np.nanmedian(np.abs(img[~bad])))
    out = map_coordinates(img, [np.asarray(y) + dy, np.asarray(x) + dx], order=1, mode='constant', cval=np.nan).reshape(h, w)
    return out / noise, obs, reg.ok


def _to_png(snr: np.ndarray, path: Path, up: int = 3):
    """Stretch at native resolution (light smoothing keeps SPHEREx's undersampled faint points), then resample 3x
    with Lanczos so stars stay round. Near-black sky with a little natural grain.
    Brightness is monotonic in signal-to-noise, so nothing is added or removed; only the display changes."""
    from scipy.ndimage import gaussian_filter
    snr = gaussian_filter(np.nan_to_num(snr), 0.55)
    v = np.arcsinh(np.clip(snr + 0.3, 0, None) / 2.2) / np.arcsinh(60 / 2.2)
    v = np.clip((v - 0.10) / 0.90, 0, 1) ** 1.05
    h, w = v.shape
    big = Image.fromarray((v * 255).astype(np.uint8), mode='L').resize((w * up, h * up), Image.LANCZOS)
    big.save(path, optimize=True)


def build(level, body, a_id, b_id, w, h, target):
    blind = json.loads((ROOT / 'validation' / 'distant' / body / 'blind.json').read_text())
    obj = next(o for o in blind['objects'] if o['accepted'])
    dets = obj['detections']
    if a_id and b_id:
        a = next(d for d in dets if d['obs_id'] == a_id)
        b = next(d for d in dets if d['obs_id'] == b_id)
    else:
        a, b = _pick_pair(dets)
    ra0, dec0 = (a['ra'] + b['ra']) / 2, (a['dec'] + b['dec']) / 2
    big = 460
    c0 = (big - 1) / 2
    renders = []
    for d in (a, b):
        small = _find(body, d['obs_id'])
        renders.append(_render(_wide(small, ra0, dec0), ra0, dec0, big, big, c0, c0, folder=small.parent))
    valid = np.isfinite(renders[0][0]) & np.isfinite(renders[1][0])
    pos = []
    for d in (a, b):
        xi, eta = _tangent(d['ra'], d['dec'], ra0, dec0)
        pos.append((c0 - xi / PIX, c0 - eta / PIX))
    # every window fully covered by both exposures that keeps both positions 24 px from its edges;
    # take the one that puts the body nearest the target spot (so it is a search, and clear of the headline)
    ii = np.cumsum(np.cumsum(~valid, 0), 1)
    def holes(x0, y0):
        x1, y1 = x0 + w - 1, y0 + h - 1
        t = ii[y1, x1] - (ii[y0 - 1, x1] if y0 else 0) - (ii[y1, x0 - 1] if x0 else 0) + (ii[y0 - 1, x0 - 1] if x0 and y0 else 0)
        return t
    mx, my = (pos[0][0] + pos[1][0]) / 2, (pos[0][1] + pos[1][1]) / 2
    best, bd = None, 1e9
    for y0 in range(0, big - h, 2):
        for x0 in range(0, big - w, 2):
            if any(not (x0 + 24 < px < x0 + w - 24 and y0 + 24 < py < y0 + h - 24) for px, py in pos):
                continue
            if holes(x0, y0):
                continue
            dd = math.hypot(mx - x0 - target[0] * w, my - y0 - target[1] * h)
            if dd < bd:
                best, bd = (x0, y0), dd
    if best is None:
        raise RuntimeError('no window covered by both exposures')
    x0, y0 = best
    frames = []
    crops = [np.nan_to_num(r[0][y0:y0 + h, x0:x0 + w]) for r in renders]
    streaks = _streaks_from(crops[0], crops[1], w, h)
    for tag, d, (snr, obs, ok), (px, py) in zip('ab', (a, b), renders, pos):
        _to_png(snr[y0:y0 + h, x0:x0 + w], OUT / f'{level}-{tag}.png')
        frames.append({'src': f'/blink/{level}-{tag}.png', 'x': float(px - x0 + 0.5) / w, 'y': float(py - y0 + 0.5) / h,
                       'date': datetime.fromtimestamp((d['mjd'] - 40587) * 86400, timezone.utc).strftime('%-d %b %Y, %H:%M UTC'),
                       'wavelength_um': round(d['wavelength_um'], 3), 'obs_id': d['obs_id'], 'registered': ok})
    xi, eta = _tangent(b['ra'], b['dec'], a['ra'], a['dec'])
    moved = float(math.hypot(xi, eta))
    orbit = obj.get('orbit') or {}
    return {'id': level, **FACTS[body], 'w': w, 'h': h, 'frames': frames, 'moved_arcsec': round(moved, 1),
            'hours': round((b['mjd'] - a['mjd']) * 24, 1), 'distance_au': round(orbit['r_au'], 1) if orbit.get('r_au') else None,
            'arcsec_per_px': PIX, 'streaks': streaks, 'source': 'NASA SPHEREx Level 2 images (IRSA); positions from the PARALLAX blind search'}


def _streaks_from(sa: np.ndarray, sb: np.ndarray, w: int, h: int) -> list[dict]:
    """Long straight trails that appear in only one image (satellites, most likely), as end points in fractions."""
    out = []
    for tag, d in (('b', sb - sa), ('a', sa - sb)):
        ys, xs = np.where(d > 3.0)
        if len(xs) < 40:
            continue
        rng = np.random.default_rng(1)
        best = (0, None)
        for _ in range(4000):
            i, j = rng.integers(len(xs), size=2)
            if abs(ys[i] - ys[j]) < h / 5:
                continue
            m = (xs[i] - xs[j]) / (ys[i] - ys[j])
            c = xs[i] - m * ys[i]
            n = int(np.sum(np.abs(xs - (m * ys + c)) < 1.2))
            if n > best[0]:
                best = (n, (m, c))
        n, mc = best
        if mc and n > 0.3 * h:          # a line covering a good part of the image height
            m, c = mc
            out.append({'in': tag, 'x1': float(c / w), 'y1': 0.0, 'x2': float((m * (h - 1) + c) / w), 'y2': 1.0})
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    levels = []
    for spec in LEVELS:
        try:
            levels.append(build(*spec))
            print('built', spec[0], levels[-1]['moved_arcsec'], 'arcsec in', levels[-1]['hours'], 'h; distance', levels[-1]['distance_au'])
        except Exception as error:  # noqa: BLE001
            print('skipped', spec[0], type(error).__name__, error)
    (OUT / 'levels.json').write_text(json.dumps(levels, indent=1))


if __name__ == '__main__':
    main()
