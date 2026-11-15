"""Other telescopes: what is counted, which previews may be fetched, and the candidate check (no network: archives are faked)."""

import pytest
from astropy.table import Table

from pipeline import archives as A
from validation import coldspec_others as C


def test_only_mast_jwst_and_hubble_previews_pass():
    assert A.PREVIEW_URI.match('mast:JWST/product/jw01230-o003_t001_nircam_clear-f444w_i2d.jpg')
    assert A.PREVIEW_URI.match('mast:HST/product/if8s05020_drz.jpg')
    for bad in ('https://evil.example/x.jpg', 'mast:HLA/product/x.jpg', 'mast:JWST/product/../../secret.jpg', 'mast:JWST/product/x.fits', ''):
        assert not A.PREVIEW_URI.match(bad)
    with pytest.raises(ValueError):
        A.preview('https://evil.example/x.jpg')


def test_mjd_to_year_and_bad_input():
    assert A._mjd_year(51544.5) == 2000.0
    assert A._mjd_year(None) is None and A._mjd_year('x') is None
    with pytest.raises(ValueError):
        A.look(10.0, 95.0)


def test_mast_counts_real_telescopes_and_skips_test_entries(monkeypatch):
    def fake_tap(url, query, timeout):
        if 'GROUP BY' in query:
            return Table(rows=[('JWST', 37, 59900.0, 60250.0), ('HST', 103, 57000.0, 61000.0), ('HLA', 28, 0, 0), ('ROMAN', 158, 61321.0, 61321.0)],
                         names=('obs_collection', 'n', 't0', 't1'))
        coll = 'JWST' if "'JWST'" in query else 'HST'
        return Table(rows=[('NIRCAM/IMAGE' if coll == 'JWST' else 'WFC3/IR', 'WISE0855', 60000.0, f'mast:{coll}/product/a_i2d.jpg'),
                           ('X', 'Y', 60000.0, 'https://elsewhere.example/b.jpg')],
                     names=('instrument_name', 'target_name', 't_min', 'jpegurl'))
    monkeypatch.setattr(A, '_tap', fake_tap)
    got = A.mast(133.787, -7.2445, 0.05)
    assert {r['key'] for r in got['rows']} == {'JWST', 'HST'}
    assert {s['collection'] for s in got['skipped']} == {'HLA', 'ROMAN'}
    assert len(got['previews']) == 2 and all(p['url'].startswith('/api/telescopes/preview?uri=mast%3A') for p in got['previews'])


def test_lookup_distinguishes_empty_failed_and_partial_archives(monkeypatch, tmp_path):
    monkeypatch.setattr(A, 'CACHE', tmp_path)
    attempts = []
    row = {'key': 'chanmaster', 'name': 'Chandra X-ray Observatory', 'archive': 'NASA HEASARC', 'n': 2}

    def mast_unavailable(*args):
        attempts.append('mast')
        raise TimeoutError

    monkeypatch.setattr(A, 'mast', mast_unavailable)
    monkeypatch.setattr(A, 'heasarc', lambda *args: {'rows': [row], 'errors': ['NICER: TimeoutError']})
    monkeypatch.setattr(A, 'neossat', lambda *args: {'rows': []})
    result = A.look(246.05986, 0.48773)
    assert result['n_observations'] == 2
    assert result['coverage'] == {'mast': 'unavailable', 'heasarc': 'partial', 'cadc': 'complete'}

    A.look(246.05986, 0.48773)
    assert len(attempts) == 2  # A failed lookup does not suppress a fresh attempt.


def test_candidate_check_reads_motion_in_the_right_order(monkeypatch):
    def fake_vizier(source, ra, dec, r, cols):
        if source.startswith('II/365'):   # CatWISE2020 row of DES 1055175672, as VizieR gives it (arcsec/yr)
            return [{'_r': '0.318', 'pmRA': '0.03421', 'e_pmRA': '0.0249', 'pmDE': '-0.24146', 'e_pmDE': '0.0242',
                     'W1mproPM': '16.482', 'e_W1mproPM': '0.032', 'W2mproPM': '15.051', 'e_W2mproPM': '0.025'}]
        if source.startswith('II/367'):
            return [{'_r': '0.985', 'J-Kspnt': '-0.1087', 'e_J-Kspnt': '0.0473'}]
        return []
    monkeypatch.setattr(C, '_vizier', fake_vizier)
    monkeypatch.setattr('pipeline.archives.look', lambda ra, dec, r: {'telescopes': []})
    out = C.check({'name': 'DES 1055175672', 'ra': 4.553804, 'dec': -47.503267, 'grade': 'strong', 'pred_type': 'T4.8'})
    assert abs(out['tests']['moves']['value'] - 244) <= 1 and abs(out['tests']['moves']['error'] - 24) <= 1
    assert out['tests']['j_ks']['pass'] and out['tests']['w1_w2']['pass'] and out['agrees']
