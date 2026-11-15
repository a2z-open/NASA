"""Asteroid hunt: fixed sources are removed by comparing epochs, a straight-line mover is linked, chance lines are not."""

import numpy as np

from validation import asteroids as A


def _image(mjd, sources, det=1):
    return {'mjd': mjd, 'detector': det, 'product_id': f'{mjd:.5f}-{det}', 'sources': sources}


def _sky(x, y, ra0=150.0, dec0=10.0):
    """Arcsec offsets east/north to RA, Dec (small field)."""
    return ra0 + x / 3600 / np.cos(np.radians(dec0)), dec0 + y / 3600


def test_fixed_sources_are_removed_and_a_mover_survives():
    rng = np.random.default_rng(0)
    stars = [(rng.uniform(-1500, 1500), rng.uniform(-1500, 1500)) for _ in range(300)]
    images = []
    for e in range(5):
        t = 61000 + e * 0.6
        hours = e * 0.6 * 24
        mover = (-800 + 20 * hours, 300 - 6 * hours)
        for k in range(2):                                         # two images about 2 minutes apart
            src = [dict(zip(('ra', 'dec'), _sky(x + rng.normal(0, 0.5), y + rng.normal(0, 0.5))), snr=8.0) for x, y in stars]
            src.append(dict(zip(('ra', 'dec'), _sky(mover[0] + rng.normal(0, 0.5), mover[1] + rng.normal(0, 0.5))), snr=9.0))
            images.append(_image(t + k * 0.0015, src))
    dets, info = A._night_detections(images, 150.0, 10.0)
    assert info['epochs'] == 5 and info['fixed_sources_removed'] >= 290 * 5
    assert len(dets) == 5                                           # only the mover is left, once per epoch
    tracks = A._link_field(dets)
    assert len(tracks) == 1 and len(tracks[0]['points']) == 5
    assert abs(tracks[0]['rate_arcsec_h'] - np.hypot(20, 6)) < 1.0


def test_random_dots_do_not_make_tracks():
    rng = np.random.default_rng(1)
    dets = [{'night': n, 'mjd': 61000 + n * 0.7, 'x': rng.uniform(-1700, 1700), 'y': rng.uniform(-1700, 1700), 'sigma': 1.5, 'snr': 6,
             'n_images': 2, 'detectors': [1], 'flux_ujy': rng.uniform(5, 15)} for n in range(8) for _ in range(40)]
    assert A._link_field(dets) == []
    assert A._control(dets, 3) == []
