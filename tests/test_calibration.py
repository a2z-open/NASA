import numpy as np
import pytest
from astropy.io import fits

from pipeline.calibration import (
    epsf_at,
    load_spectral_calibration,
    wavelength_at,
)


def test_spectral_values_come_from_parent_pixel_and_matching_version(tmp_path):
    wavelengths = np.zeros((2040, 2040), dtype=np.float32)
    widths = np.zeros_like(wavelengths)
    # At cutout pixel (2, 1), the original pixel is (202, 301).
    wavelengths[301, 202] = 1.346
    widths[301, 202] = 0.034
    source = "spectral_wcs_2_v2.2.fits"
    maps = [fits.ImageHDU(wavelengths, name="CWAVE"), fits.ImageHDU(widths, name="CBAND")]
    for hdu in maps:
        hdu.header["DETECTOR"] = 2
        hdu.header["BUNIT"] = "um"
        hdu.header["HISTORY"] = f"Calibration source file: {source}"
    calibration_path = tmp_path / "spectral.fits"
    fits.HDUList([fits.PrimaryHDU(), *maps]).writeto(calibration_path)
    wave_header = fits.Header({"DETECTOR": 2})
    wave_header["HISTORY"] = f"Calibration source file: {source}"
    image_header = fits.Header({"CRPIX1A": -199, "CRPIX2A": -299})

    calibration = load_spectral_calibration(calibration_path, wcs_wave_header=wave_header)
    assert wavelength_at(calibration, image_header, 2.2, 1.1) == pytest.approx((1.346, 0.034))
    with pytest.raises(ValueError, match="outside the original detector"):
        wavelength_at(calibration, image_header, -201, 1)
    with pytest.raises(ValueError, match="positive finite"):
        wavelength_at(calibration, image_header, 1, 1)

    wave_header["DETECTOR"] = 3
    with pytest.raises(ValueError, match="detector"):
        load_spectral_calibration(calibration_path, wcs_wave_header=wave_header)
    wave_header["DETECTOR"] = 2
    del wave_header["HISTORY"]
    wave_header["HISTORY"] = "Calibration source file: spectral_wcs_2_v9.fits"
    with pytest.raises(ValueError, match="source"):
        load_spectral_calibration(calibration_path, wcs_wave_header=wave_header)

    del wave_header["HISTORY"]
    wave_header["HISTORY"] = f"Calibration source file: {source}"
    del maps[1].header["HISTORY"]
    fits.HDUList([fits.PrimaryHDU(), *maps]).writeto(calibration_path, overwrite=True)
    with pytest.raises(ValueError, match="source"):
        load_spectral_calibration(calibration_path, wcs_wave_header=wave_header)


def test_epsf_selection_uses_original_detector_coordinates():
    table = fits.BinTableHDU.from_columns(
        [
            fits.Column(name="BINX", format="J", array=[0, 1]),
            fits.Column(name="BINY", format="J", array=[0, 1]),
            fits.Column(name="XCENTER", format="E", array=[1, 205]),
            fits.Column(name="YCENTER", format="E", array=[1, 301]),
            fits.Column(
                name="EPSF", format="9D", dim="(3,3)",
                array=np.stack([np.ones((3, 3)), np.eye(3)]),
            ),
        ],
        name="EPSF",
    )
    table.header["OVSMPX"] = 5
    table.header["OVSMPY"] = 4
    image = fits.ImageHDU(name="IMAGE")
    image.header["CRPIX1A"] = -199
    image.header["CRPIX2A"] = -299
    cutout = fits.HDUList([fits.PrimaryHDU(), image, table])

    model = epsf_at(cutout, 2, 1)

    assert model.zone == (1, 1)
    assert model.oversampling == (4, 5)
    np.testing.assert_array_equal(model.data, np.eye(3))
