import numpy as np
import pytest

from pipeline.fit_screen import centroid, fit_manifest_rows, reference_offsets


def test_fit_manifest_rejects_reserved_frame_before_access():
    manifest = {
        "fit_frames": [{"id": "one-D5", "visit_id": "later", "path": "reserve.fits", "mjd_avg": 20}],
        "reserve": {"visit_ids": ["later"], "obs_ids": ["one"], "t_min": 19.9},
    }
    with pytest.raises(ValueError, match="reserved"):
        fit_manifest_rows(manifest)


def test_reference_offset_uses_only_registration_stars():
    offsets = {str(i): np.array([2.0, -1.0]) for i in range(1, 11)}
    offsets["5"] = np.array([5.0, 5.0])
    offsets["10"] = np.array([5.0, 5.0])
    shift, held_out = reference_offsets(offsets)
    np.testing.assert_equal(shift, [2.0, -1.0])
    assert set(held_out) == {"5", "10"}
    np.testing.assert_equal(held_out["5"], [3.0, 6.0])


def test_wing_fit_rejects_a_core_only_even_when_wings_are_enabled():
    from types import SimpleNamespace

    yy, xx = np.mgrid[:21, :21]
    pixels = 20 * np.exp(-0.5 * ((xx - 10) ** 2 + (yy - 10) ** 2) / 0.36)
    hdu = {
        "IMAGE": SimpleNamespace(data=pixels),
        "VARIANCE": SimpleNamespace(data=np.ones_like(pixels)),
        "FLAGS": SimpleNamespace(data=np.zeros(pixels.shape, dtype=int)),
    }
    assert centroid(hdu, 10, 10, 0, omit_core=True) is None
