from dataclasses import replace
from io import BytesIO

import numpy as np
from astropy.io import fits
from fastapi.testclient import TestClient
from PIL import Image

from api import lookup
from api.lookup import create_app
from pipeline.archive import (
    ArchiveUnavailable,
    Exposure,
    SkyPosition,
    build_sequence,
    choose_frames,
    decode_fits,
    group_visits,
    is_reserved,
    render_frames,
)


CENTER = SkyPosition(269.45, 4.7)
EXPOSURE = Exposure('first', 'D5', 'DR1', 'https://irsa.ipac.caltech.edu/early.fits',
                    61000., 61000.001, CENTER.ra, CENTER.dec)


def test_group_deduplicates_and_preserves_reserve_boundary():
    later = replace(EXPOSURE, obs_id='second', t_min=61100, t_max=61100.001)
    reserve = replace(EXPOSURE, obs_id='reserve', release='QR3', t_min=61200, t_max=61200.001)
    duplicate = replace(EXPOSURE, release='QR3')
    visits = group_visits([reserve, duplicate, later, EXPOSURE])
    assert [[item.id for item in v] for v in visits] == [['first-D5'], ['second-D5'], ['reserve-D5']]
    assert visits[0][0].release == 'DR1'
    assert [x.id for x, _ in choose_frames(visits[:2], CENTER, limit=4)] == ['first-D5', 'second-D5']


def test_reserved_obs_id_guard_includes_other_detectors_and_nearby_geometry():
    reservation = {'obs_ids': ['sealed'], 't_min': 61199, 't_max': 61210}
    assert is_reserved(replace(EXPOSURE, obs_id='sealed', detector='D4'), SkyPosition(42, 10), reservation)
    overlapping = replace(EXPOSURE, obs_id='undiscovered', t_min=61200, t_max=61200.001)
    assert is_reserved(overlapping, SkyPosition(269.46, 4.7), reservation)
    assert not is_reserved(overlapping, SkyPosition(42, 10), reservation)


def example_cutout(value, *, center=CENTER):
    shape = (40, 40)
    image = fits.ImageHDU(np.full(shape, value, dtype='float32'), name='IMAGE')
    image.header.update(
        CTYPE1='RA---TAN', CTYPE2='DEC--TAN', CRVAL1=center.ra, CRVAL2=center.dec,
        CRPIX1=20.5, CRPIX2=20.5, CDELT1=-6.15 / 3600, CDELT2=6.15 / 3600,
    )
    image.header['MJD-AVG'] = 61000
    flags = fits.ImageHDU(np.zeros(shape, dtype='int32'), name='FLAGS')
    stream = BytesIO()
    fits.HDUList([fits.PrimaryHDU(), image, flags]).writeto(stream)
    return stream.getvalue()


def test_common_stretch_preserves_difference_between_images():
    images = [decode_fits(example_cutout(value), CENTER, 2 / 60) for value in (1, 9)]
    pngs = render_frames(images)
    decoded = [Image.open(BytesIO(png)) for png in pngs]
    assert decoded[0].size == decoded[1].size
    assert decoded[0].getpixel((8, 8)) < decoded[1].getpixel((8, 8))


def test_sequence_never_requests_the_reserved_frame(tmp_path):
    calls = []
    later = replace(EXPOSURE, obs_id='second', t_min=61100, t_max=61100.001)
    reserve = replace(EXPOSURE, obs_id='reserve', t_min=61200, t_max=61200.001)

    class Archive:
        def search(self, position):
            return [EXPOSURE, later, reserve]

        def cutout(self, item, position, size):
            calls.append(item.id)
            return example_cutout(1 if item.id == 'first-D5' else 9)

    result = build_sequence(
        Archive(), CENTER, tmp_path,
        reservation={'obs_ids': ['reserve'], 't_min': 61199, 't_max': 61210},
    )
    assert sorted(calls) == ['first-D5', 'second-D5']
    assert result['status'] == 'ready'
    assert result['comparison_status'] == 'unverified'
    assert len(result['frames']) == 2
    assert all(x['wavelength_um'] is None for x in result['frames'])


def test_http_validates_coordinates_and_normalizes_ra_wrap(tmp_path):
    calls = []

    class Archive:
        def search(self, position):
            calls.append(position)
            return []

    with TestClient(create_app(cache=tmp_path, archive=Archive())) as client:
        for path in ('?ra=NaN&dec=0', '?ra=1&dec=91', '?ra=-1&dec=0', '?dec=0'):
            assert client.get('/api/sequence' + path).status_code == 400
        response = client.get('/api/sequence?ra=360&dec=0')
        assert response.status_code == 200
        assert response.json()['status'] == 'no_coverage'
        assert calls == [SkyPosition(0, 0)]


def test_http_fails_closed_at_barnard_without_local_reservation(tmp_path, monkeypatch):
    monkeypatch.setattr(lookup, 'RESERVATION', tmp_path / 'missing.json')

    class Archive:
        def search(self, position):
            raise AssertionError('The sealed field must be checked before calling IRSA.')

    stale = tmp_path / 'v1-269.48500000_4.78000000'
    stale.mkdir()
    (stale / 'old.png').write_bytes(b'unservable')
    with TestClient(create_app(cache=tmp_path, archive=Archive())) as client:
        result = client.get('/api/sequence?ra=269.485&dec=4.78')
        assert result.json()['status'] == 'archive_unavailable'
        assert client.get('/frames/v1-269.48500000_4.78000000/old.png').status_code == 404


def test_live_lookup_returns_warm_cache_when_irsa_is_unavailable(tmp_path):
    failing = False

    class Archive:
        def search(self, position):
            if failing:
                raise ArchiveUnavailable('simulated upstream outage')
            return [EXPOSURE]

        def cutout(self, item, position, size):
            return example_cutout(1)

    archive = Archive()
    first = build_sequence(archive, CENTER, tmp_path, reservation={})
    assert first['status'] == 'one_visit'
    assert first['source'] == 'archive'
    failing = True
    second = build_sequence(archive, CENTER, tmp_path, reservation={})
    assert second['source'] == 'cache'
    assert second['frames'] == first['frames']
