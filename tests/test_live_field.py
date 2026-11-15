from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import numpy as np
from astropy.io import fits
from fastapi.testclient import TestClient

from api import app as viewer
from pipeline import measure, spherex
from pipeline.spherex import Product


def test_retry_shows_queued_state_while_worker_is_busy(tmp_path, monkeypatch):
    monkeypatch.setattr(viewer, 'FIELDS', tmp_path)
    monkeypatch.setattr(viewer, '_jobs', {})
    monkeypatch.setattr(viewer, '_pool', SimpleNamespace(submit=lambda *args: None))
    coords = {'ra': 10., 'dec': 40., 'fov_arcmin': 3}

    with TestClient(viewer.app) as client:
        first = client.post('/api/fields', json=coords)
        assert first.status_code == 200
        job, fid = first.json()['job_id'], first.json()['field_id']
        path = tmp_path / fid / 'field.json'
        pending = viewer.read_json(path)
        viewer.write_json(path, pending | {'data_state': 'archive_unavailable'})
        viewer.job_update(job, status='done')

        retry = client.post('/api/fields', json=coords)
        assert retry.status_code == 200
        assert retry.json()['job_id'] != job
        field = client.get(f'/api/fields/{fid}').json()
        assert field['data_state'] == 'processing'
        assert field['progress']['stage'] == 'queued'


def test_usable_frame_is_served_while_another_cutout_and_gaia_are_pending(tmp_path, monkeypatch):
    center = (10., 40.)
    products = [
        Product(f'fixture-{idx}', 3, 'spherex_dr1', 'DR1', f'https://example.com/{idx}.fits',
                mjd, mjd + .001, *center, None, None)
        for idx, mjd in enumerate((61000., 61100.))
    ]
    first_image = Event()
    last_image = Event()
    catalog_waiting = Event()
    catalog_release = Event()
    catalog_done = Event()
    later_downloaded = Event()

    def search(ra, dec, *, on_unavailable):
        on_unavailable('spherex_qr3')
        return products

    def get(url, **kwargs):
        product = next(p for p in products if p.access_url in url)
        if product is products[0]:
            assert first_image.wait(3)
        else:
            later_downloaded.set()
        image = fits.ImageHDU(np.ones((40, 40), dtype=np.float32), name='IMAGE')
        image.header.update(CTYPE1='RA---TAN', CTYPE2='DEC--TAN', CRVAL1=center[0], CRVAL2=center[1],
                            CRPIX1=20.5, CRPIX2=20.5, CDELT1=-6.15 / 3600, CDELT2=6.15 / 3600,
                            OBSID=product.obs_id, DETECTOR=product.detector)
        image.header['MJD-AVG'] = product.t_mid
        from io import BytesIO
        stream = BytesIO()
        fits.HDUList([fits.PrimaryHDU(), image, fits.ImageHDU(np.ones((40, 40)), name='VARIANCE'),
                      fits.ImageHDU(np.zeros((40, 40), dtype=np.int32), name='FLAGS')]).writeto(stream)
        return SimpleNamespace(content=stream.getvalue())

    def gaia(*args, **kwargs):
        catalog_waiting.set()
        assert catalog_release.wait(3)
        return [{'ra': 10., 'dec': 40., 'source_id': 'catalogue-fixture'}]

    monkeypatch.setattr(viewer, 'FIELDS', tmp_path)
    monkeypatch.setattr(viewer, 'search', search)
    monkeypatch.setattr(spherex, '_get', get)
    monkeypatch.setattr(measure, 'gaia_field', gaia)

    fid = 'fprogressive'
    job = viewer.new_job('field', fid)
    original = viewer.job_update

    def job_update(job_id, **kwargs):
        original(job_id, **kwargs)
        progress = kwargs.get('progress', {})
        if progress.get('stage') == 'Loading Gaia DR3 overlay':
            last_image.set()
        if kwargs.get('status') == 'done':
            catalog_done.set()

    monkeypatch.setattr(viewer, 'job_update', job_update)
    from time import monotonic, sleep
    with ThreadPoolExecutor(max_workers=1) as pool:
        work = pool.submit(viewer._field_job, job, fid, *center, 3, 4, None, None)
        try:
            assert later_downloaded.wait(2)
            deadline = monotonic() + 2
            doc = viewer.get_field(fid)
            while not doc['frames'] and monotonic() < deadline:
                sleep(.01)
                doc = viewer.get_field(fid)
            assert doc['data_state'] == 'processing'
            assert [frame['id'] for frame in doc['frames']] == [products[1].id]
            assert not doc['catalog']
            with TestClient(viewer.app) as client:
                frame = client.get(doc['frames'][0]['data_url'])
                assert frame.status_code == 200
                assert len(frame.content) == 2 * doc['grid']['nx'] * doc['grid']['ny']
            assert catalog_waiting.is_set()
            first_image.set()
            assert last_image.wait(2)
            doc = viewer.get_field(fid)
            assert [frame['id'] for frame in doc['frames']] == [p.id for p in products]
            assert doc['data_state'] == 'live'
            assert doc['catalog_status'] == 'loading'
            work.result(timeout=2)
        finally:
            first_image.set()
            catalog_release.set()
        assert catalog_done.wait(3)
    result = viewer.get_field(fid)
    assert result['data_state'] == 'live'
    assert [frame['visit'] for frame in result['frames']] == ['visit-1', 'visit-2']
    assert result['catalog'][0]['source_id'] == 'catalogue-fixture'
    assert result['catalog_status'] == 'ready'
    assert result['archive']['unavailable_collections'] == ['spherex_qr3']
    assert not list(Path(tmp_path).rglob('*.part'))
