from hashlib import sha256
from importlib.util import find_spec
import json
from pathlib import Path

import pytest
from PIL import Image


PACKET = (Path(__file__).resolve().parents[2] / 'discovery-runs/2026-11-14/expansion')
pytestmark = pytest.mark.skipif(not PACKET.is_dir(), reason='original evidence packet is a local workspace artifact')


def _attach(candidates, tmp_path, **kwargs):
    assert find_spec('pipeline.discovery_evidence') is not None, 'discovery evidence helper is missing'
    from pipeline.discovery_evidence import attach_evidence

    attach_evidence({'candidates': candidates}, tmp_path, **kwargs)


def _observations(label, packet='candidate-orbit.json'):
    return json.loads((PACKET / 'asteroids-west' / label / packet).read_bytes())['observations']


def test_precise_comet_matches_and_blend_are_distinguished(tmp_path):
    rows = _observations('NW004')
    precise = [row for row in rows if row['station'] != 'D29']
    blend = {'id': 'unrelated-run-hash', 'observations': rows}
    known = {'id': 'plain-run-hash', 'observations': precise}
    mixed = {'id': 'NW004', 'observations': precise + _observations('NW034')[:4]}
    spoofed = {'id': 'NW004', 'observations': [row | {'ra_deg': row['ra_deg'] + .1} for row in precise]}
    _attach([blend, known, mixed, spoofed], tmp_path, allow_pixels=False)
    assert blend['catalog']['status'] == 'known_contamination'
    assert blend['catalog']['matched_observations'] == 19
    assert blend['catalog']['total_observations'] == 22
    assert blend['catalog']['exclude_from_novel_review']
    assert known['catalog']['status'] == 'known_object'
    assert known['catalog']['exclude_from_novel_review']
    assert known['catalog']['name'] == '88P/Howell'
    assert mixed['catalog']['status'] == 'partial_match'
    assert not mixed['catalog']['exclude_from_novel_review']
    assert spoofed['catalog']['status'] == 'unverified'
    assert known['images']['status'] == 'disabled'


def test_nw034_remeasures_original_exposures_on_one_blink_grid(tmp_path):
    rows = _observations('NW034', 'candidate-extended-orbit.json')
    candidate = {'id': 'unrelated-run-hash', 'observations': rows}
    unrelated = {'id': 'NW034', 'observations': _observations('NW004')[:3]}
    _attach([candidate, unrelated], tmp_path, order=('pixels', 'catalog'))
    assert candidate['catalog']['status'] == 'no_match_in_checked_catalogs'
    assert unrelated['catalog']['status'] == 'unverified'
    assert unrelated['images']['status'] == 'unverified'
    images = candidate['images']
    assert images['status'] == 'verified_same_exposure'
    assert images['measurement_origin'] == 'remeasured_original_fits'
    assert images['combined_snr'] == pytest.approx(12.47172, abs=.001)
    assert images['strongest_positive_control_snr'] == pytest.approx(1.61734, abs=.001)
    assert images['motion_arcsec'] == pytest.approx(14.54, abs=.01)
    assert images['coverage'][0]['status'] == 'archive_not_available'
    assert len(images['frames']) == 4
    assert len({tuple(f['viewport_center_deg']) for f in images['frames']}) == 1
    assert len({tuple(f['centroid_pixel_xy']) for f in images['frames']}) == 4
    assert [frame['epoch'] for frame in images['frames']] == sorted(frame['epoch'] for frame in images['frames'])
    for frame in images['frames']:
        assert frame['source_url'].startswith('https://sbnarchive.psi.edu/')
        path = tmp_path / frame['file']
        assert sha256(path.read_bytes()).hexdigest() == frame['display_sha256']
        with Image.open(path) as png:
            assert png.width == png.height and png.width >= 160
            assert len(png.getcolors(maxcolors=512)) > 32


def test_calibrated_pixels_must_match_the_archive_receipt(tmp_path, monkeypatch):
    base = 'asteroids-west/NW034'
    mirror = tmp_path / 'evidence'
    (mirror / base / 'pixels').mkdir(parents=True)
    needed = [
        'candidate-orbit.json', 'pixels/pixel-remeasurement-results.json',
        'pixels/G96-Nov13-calibrated-index.html',
    ]
    for name in needed:
        (mirror / base / name).symlink_to(PACKET / base / name)
    pixels = mirror / base / 'pixels'
    receipt = json.loads((pixels / 'pixel-remeasurement-results.json').read_bytes())[0]
    (pixels / (receipt['id'] + '.fits.xml')).symlink_to(PACKET / base / 'pixels' / (receipt['id'] + '.fits.xml'))
    (pixels / (receipt['id'] + '.arch.fz')).write_bytes(b'wrong bytes')
    monkeypatch.setenv('PARALLAX_DISCOVERY_EVIDENCE_DIR', str(mirror))
    out = tmp_path / 'output'
    candidate = {'id': 'NW034', 'observations': _observations('NW034')}
    _attach([candidate], out)
    assert not out.exists()
    assert candidate['catalog']['status'] == 'unverified'
    assert candidate['images']['frames'] == []
    assert candidate['images']['status'] == 'unverified'
    assert candidate['images']['expected_frames'] == 4
    assert candidate['images']['coverage'][0]['status'] == 'archive_not_available'
