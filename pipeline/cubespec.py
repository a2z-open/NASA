"""A 102-colour spectrum of any point on the sky, from the SPHEREx DR1 all-sky data cube at IRSA.

The cube is published as HEALPix tiles (order 5, 512 x 512 pixels of 12.9", 102 wavelength planes, MJy/sr, zodiacal
light already removed).  One tile is 321 MB, so nothing is downloaded whole: a single HTTP request with 102 byte
ranges fetches a small window around the target from every plane (about 1.7 MB).

    from pipeline.cubespec import spectrum
    s = spectrum(ra_deg, dec_deg)        # {'wave_um', 'flux_ujy', 'err_ujy', ...}

Photometry is deliberately simple and the same for every object: a weighted fit of a fixed Gaussian profile over
the 3 x 3 pixels around the brightest pixel near the expected position, minus the median of a surrounding ring, with
the ring's scatter as the error.  The absolute flux scale is not calibrated here (at 1.28 um it reads about 1.4 times
the 2MASS J-band flux for M dwarfs); only the shape of the spectrum is used.  Source: https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube (SPHEREx Science Data Center).
"""
from __future__ import annotations

import re
import time

import astropy.units as u
import numpy as np
import requests
from astropy.io import fits
from astropy.wcs import WCS
from astropy_healpix import HEALPix

from .spherex import CACHE, USER_AGENT

BASE = 'https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube'
ORDER, TILE, NPLANE = 5, 512, 102
HALF = 5                         # window half-width in cube pixels (11 x 11 pixels, 142" across)
PIX_SR = (4 * np.pi / (12 * (2 ** ORDER * TILE) ** 2))           # solid angle of one cube pixel, steradian
UJY_PER_MJYSR_PIX = PIX_SR * 1e12                                 # 1 MJy/sr over one pixel, in microjansky
WAVES = np.array([0.753, 0.771, 0.790, 0.809, 0.828, 0.848, 0.868, 0.889, 0.910, 0.932, 0.955, 0.978, 1.001, 1.025, 1.050, 1.075, 1.102,
                  1.113, 1.139, 1.167, 1.195, 1.224, 1.254, 1.284, 1.315, 1.346, 1.378, 1.412, 1.446, 1.481, 1.517, 1.554, 1.592, 1.631,
                  1.656, 1.695, 1.735, 1.775, 1.818, 1.861, 1.905, 1.949, 1.995, 2.041, 2.089, 2.139, 2.189, 2.240, 2.292, 2.345, 2.399,
                  2.445, 2.506, 2.575, 2.646, 2.719, 2.794, 2.871, 2.951, 3.033, 3.118, 3.204, 3.293, 3.383, 3.476, 3.570, 3.667, 3.768,
                  3.833, 3.867, 3.901, 3.935, 3.970, 4.005, 4.040, 4.076, 4.112, 4.148, 4.184, 4.220, 4.257, 4.294, 4.331, 4.368, 4.405,
                  4.435, 4.467, 4.500, 4.533, 4.566, 4.600, 4.635, 4.669, 4.704, 4.739, 4.773, 4.808, 4.843, 4.879, 4.915, 4.951, 4.988])
MID_EPOCH_MJD = 60980.0          # middle of the exposures in the DR1 cube (2025-07-26 to 2026-02-07)

_hp = HEALPix(nside=2 ** ORDER, order='nested')
_session = None
_tiles: dict[int, dict] = {}


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers['User-Agent'] = USER_AGENT
        _session.mount('https://', requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=2))
    return _session


def _get(url: str, rng: str, tries: int = 5) -> requests.Response:
    last = None
    for k in range(tries):
        try:
            r = session().get(url, headers={'Range': 'bytes=' + rng}, timeout=120)
            if r.status_code in (200, 206):
                return r
            if r.status_code == 404:
                raise FileNotFoundError(url)
            last = RuntimeError(f'HTTP {r.status_code}')
        except (requests.ConnectionError, requests.Timeout) as error:
            last = error
        time.sleep(1.5 * (k + 1))
    raise last


def tile_url(npix: int) -> str:
    return f'{BASE}/Norder{ORDER}/Dir{(npix // 10000) * 10000}/Npix{npix}/Npix{npix}_cube.fits'


def tile_info(npix: int) -> dict:
    """Sky-to-pixel transform and the byte offset of the IMAGE data in one tile (one small request, cached)."""
    if npix in _tiles:
        return _tiles[npix]
    path = CACHE / 'cubespec' / 'tiles' / f'{npix}.hdr'
    if path.is_file():
        raw = path.read_bytes()
    else:
        raw = _get(tile_url(npix), '0-14399').content
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    # two headers: the empty primary, then IMAGE
    pos, headers = 0, []
    while len(headers) < 2:
        end = pos
        while True:
            block = raw[end:end + 2880]
            end += 2880
            if any(block[i:i + 8] == b'END     ' for i in range(0, 2880, 80)):
                break
            if end >= len(raw):
                raise ValueError('header longer than expected')
        headers.append(fits.Header.fromstring(raw[pos:end].decode('ascii', 'replace')))
        pos = end
    hdr = headers[1]
    if hdr.get('EXTNAME') != 'IMAGE' or (hdr['NAXIS1'], hdr['NAXIS2'], hdr['NAXIS3']) != (TILE, TILE, NPLANE) or hdr['BITPIX'] != -32:
        raise ValueError('unexpected tile layout')
    # keep only the two sky axes: the third (wavelength) uses a lookup table that is not needed here
    sky = fits.Header()
    sky['NAXIS'], sky['NAXIS1'], sky['NAXIS2'], sky['WCSAXES'] = 2, TILE, TILE, 2
    for k in ('CRPIX1', 'CRPIX2', 'PC1_1', 'PC1_2', 'PC2_1', 'PC2_2', 'CDELT1', 'CDELT2', 'CUNIT1', 'CUNIT2', 'CTYPE1', 'CTYPE2',
              'CRVAL1', 'CRVAL2', 'PV2_1', 'PV2_2', 'LONPOLE', 'LATPOLE', 'RADESYS'):
        if k in hdr:
            sky[k] = hdr[k]
    info = {'npix': npix, 'offset': pos, 'wcs': WCS(sky), 'unit': hdr.get('BUNIT', '').strip()}
    _tiles[npix] = info
    return info


def _multipart(r: requests.Response) -> list[bytes]:
    ctype = r.headers.get('Content-Type', '')
    if 'multipart/byteranges' not in ctype:
        return [r.content]
    boundary = re.search(r'boundary=([^;]+)', ctype).group(1).strip('"').encode()
    parts = []
    for chunk in r.content.split(b'--' + boundary)[1:]:
        if chunk.startswith(b'--'):
            break
        head, _, body = chunk.lstrip(b'\r\n').partition(b'\r\n\r\n')
        m = re.search(rb'bytes (\d+)-(\d+)/', head)
        parts.append((int(m.group(1)), body[:int(m.group(2)) - int(m.group(1)) + 1]))
    return [b for _, b in sorted(parts)]


def window(ra: float, dec: float) -> dict:
    """The (102, 11, 11) window of the cube around a position, MJy/sr.  Returns {'cube', 'x', 'y', 'npix'}."""
    npix = int(_hp.lonlat_to_healpix(ra * u.deg, dec * u.deg))
    info = tile_info(npix)
    x, y = (float(v) for v in info['wcs'].all_world2pix(ra, dec, 0))
    xi, yi = int(round(x)), int(round(y))
    if not (HALF <= xi < TILE - HALF and HALF <= yi < TILE - HALF):
        raise ValueError('too close to a tile edge')
    x0, x1, y0, y1 = xi - HALF, xi + HALF, yi - HALF, yi + HALF
    n = 2 * HALF + 1
    ranges = []
    for p in range(NPLANE):
        a = info['offset'] + ((p * TILE + y0) * TILE + x0) * 4
        b = info['offset'] + ((p * TILE + y1) * TILE + x1) * 4 + 3
        ranges.append(f'{a}-{b}')
    parts = _multipart(_get(tile_url(npix), ','.join(ranges)))
    if len(parts) != NPLANE:
        raise RuntimeError(f'expected {NPLANE} byte ranges, got {len(parts)}')
    cube = np.empty((NPLANE, n, n), np.float32)
    span = (n - 1) * TILE + n
    for p, raw in enumerate(parts):
        row = np.frombuffer(raw, dtype='>f4', count=span)
        cube[p] = np.stack([row[j * TILE:j * TILE + n] for j in range(n)])
    return {'cube': cube, 'x': x - x0, 'y': y - y0, 'npix': npix}


PSF_SIGMA_PIX = 0.40             # Gaussian width that best fits bright point sources in the cube (pixels of 12.9")


def _pix_gauss(n: int, c: float, s: float) -> np.ndarray:
    """A Gaussian of width s centred at c, integrated over each of n pixels."""
    from scipy.special import erf
    e = np.arange(n + 1) - 0.5
    return 0.5 * np.diff(erf((e - c) / (s * np.sqrt(2))))


def photometry(cube: np.ndarray, x: float, y: float, search: float = 1.0) -> dict:
    """Weighted (matched-filter) photometry in every plane, the same way for every object.

    The source is located once, on the median of all planes: the brightest pixel within `search` pixels of (x, y),
    refined to a sub-pixel centre.  In each plane the flux is the best-fitting amplitude of a fixed Gaussian profile
    over the 3 x 3 pixels around that centre, after subtracting the median of a surrounding ring (3 to 5.5 pixels);
    the ring's scatter gives the error.  A weighted fit, unlike a plain box sum, is barely touched by neighbours."""
    n = cube.shape[1]
    yy, xx = np.mgrid[0:n, 0:n]
    good = np.isfinite(cube).all(axis=(1, 2))
    if good.sum() < 40:
        raise ValueError('too few valid planes')
    # the detection image: the mean of the planes where every cool dwarf is bright (the Y, J and H peaks), so that a
    # methane dwarf, dark in most other planes, is located as well as a star is
    peaks = good & (((WAVES >= 1.00) & (WAVES <= 1.34)) | ((WAVES >= 1.50) & (WAVES <= 1.64)))
    white = np.mean(cube[peaks], axis=0) if peaks.sum() >= 8 else np.nanmedian(cube[good], axis=0)
    r0 = np.hypot(xx - x, yy - y)
    far = r0 >= 3.0
    white = white - np.median(white[far])
    noise = 1.4826 * np.median(np.abs(white[far] - np.median(white[far])))
    near = r0 <= search
    cy, cx = np.unravel_index(np.argmax(np.where(near, white, -np.inf)), white.shape)
    if not (2 <= cx < n - 2 and 2 <= cy < n - 2):
        raise ValueError('peak at the window edge')
    box = (np.abs(xx - cx) <= 1) & (np.abs(yy - cy) <= 1)
    w = np.clip(white, 0, None) * box
    if w.sum() <= 0:
        raise ValueError('nothing there')
    fx, fy = float((w * xx).sum() / w.sum()), float((w * yy).sum() / w.sum())
    prof = np.outer(_pix_gauss(n, fy, PSF_SIGMA_PIX), _pix_gauss(n, fx, PSF_SIGMA_PIX))[box]
    den = float((prof ** 2).sum())
    r = np.hypot(xx - cx, yy - cy)
    ring = (r >= 3.0) & (r <= HALF + 0.5)
    flux, err = np.full(cube.shape[0], np.nan), np.full(cube.shape[0], np.nan)
    for p in np.where(good)[0]:
        bg = cube[p][ring]
        med = np.median(bg)
        sig = 1.4826 * np.median(np.abs(bg - med))
        if sig <= 0:
            continue
        flux[p] = float((prof * (cube[p][box] - med)).sum()) / den * UJY_PER_MJYSR_PIX
        err[p] = sig / np.sqrt(den) * UJY_PER_MJYSR_PIX
    # the brightest pixel between 1.6 and 3.2 pixels away, relative to the target's peak: a bright close neighbour
    near_rival = float(np.max(np.where((r > 1.6) & (r <= 3.2), white, -np.inf)) / max(white[cy, cx], 1e-9))
    amp = float((prof * white[box]).sum()) / den
    peak = max(amp * prof.max(), 1e-9)
    # how point-like it is: the misfit of the profile in the detection image, beyond what noise alone would give
    rms = float(np.sqrt(np.mean((white[box] - amp * prof) ** 2)))
    resid = float(np.sqrt(max(rms ** 2 - noise ** 2, 0.0)) / peak)
    return {'flux_ujy': flux, 'err_ujy': err, 'offset_pix': float(np.hypot(fx - x, fy - y)), 'near_rival': near_rival, 'resid': resid,
            'snr_det': float(amp / (noise / np.sqrt(den))) if noise > 0 else 0.0}


def spectrum(ra: float, dec: float, *, key: str | None = None, cache: bool = True, alternatives: list[tuple[float, float]] | None = None) -> dict:
    """Spectrum at (ra, dec), degrees ICRS, at the cube's epoch.  Cached under .parallax-cache/cubespec/.

    `alternatives` are other places the same object could be (for example, if its catalogue position has a different
    epoch than assumed).  The window is fetched once, around (ra, dec); the source is then looked for at each place
    and the one found closest to where it was expected is kept."""
    name = key or f'{ra:.5f}_{dec:+.5f}'
    path = CACHE / 'cubespec' / 'win' / (re.sub(r'[^A-Za-z0-9_.+-]+', '_', name) + '.npz')
    if cache and path.is_file():
        d = np.load(path)
        win = {'cube': d['cube'], 'x': float(d['x']), 'y': float(d['y']), 'npix': int(d['npix'])}
    else:
        win = window(ra, dec)
        if cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(path, cube=win['cube'], x=win['x'], y=win['y'], npix=win['npix'])
    tries = [(win['x'], win['y'], 0)]
    if alternatives:
        wcs = tile_info(win['npix'])['wcs']
        x0, y0 = (float(v) for v in wcs.all_world2pix(ra, dec, 0))
        for k, (ra2, dec2) in enumerate(alternatives, start=1):
            x2, y2 = (float(v) for v in wcs.all_world2pix(ra2, dec2, 0))
            tries.append((win['x'] + x2 - x0, win['y'] + y2 - y0, k))
    best, error = None, None
    n = win['cube'].shape[1]
    for x, y, k in tries:
        if not (1.5 <= x <= n - 2.5 and 1.5 <= y <= n - 2.5):
            continue
        try:
            ph = photometry(win['cube'], x, y)
        except ValueError as e:
            error = e
            continue
        ph['hypothesis'] = k
        if best is None or ph['offset_pix'] < best['offset_pix']:
            best = ph
    if best is None:
        raise error or ValueError('no usable position')
    best.update({'wave_um': WAVES, 'npix': win['npix'], 'ra': ra, 'dec': dec})
    return best
