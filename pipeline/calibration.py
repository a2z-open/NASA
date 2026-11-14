"""Native detector calibration for DR1 and QR3 SPHEREx cutouts."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy.io import fits


DETECTOR_PIXELS = 2040
CALIBRATION_BUCKET = "https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com"
SPECTRAL_PRODUCT_VERSION = "cal-swcs-v5-2026-191"


@dataclass(frozen=True)
class SpectralCalibration:
    detector: int
    source: str
    cwave: np.ndarray
    cband: np.ndarray


@dataclass(frozen=True)
class Epsf:
    data: np.ndarray
    oversampling: tuple[int, int]
    zone: tuple[int, int]


def spectral_calibration_url(release: str, detector: int) -> str:
    """Return the indexed public product. Verify its FITS identity before use."""
    if release not in {"dr1", "qr3"} or detector not in range(1, 7):
        raise ValueError("Expected a DR1 or QR3 detector numbered 1 through 6.")
    version = SPECTRAL_PRODUCT_VERSION
    return (
        f"{CALIBRATION_BUCKET}/{release}/spectral_wcs/{version}/{detector}/"
        f"spectral_wcs_D{detector}_spx_{version}.fits"
    )


def _calibration_source(header: fits.Header) -> str | None:
    prefix = "Calibration source file:"
    sources = {
        str(card.value)[len(prefix):].strip()
        for card in header.cards
        if card.keyword == "HISTORY" and str(card.value).startswith(prefix)
    }
    return next(iter(sources)) if len(sources) == 1 else None


def load_spectral_calibration(
    path: str | Path, *, wcs_wave_header: fits.Header
) -> SpectralCalibration:
    """Require the exposure and detector map to identify the same source calibration."""
    expected_source = _calibration_source(wcs_wave_header)
    with fits.open(path, memmap=False) as hdul:
        cwave, cband = hdul["CWAVE"], hdul["CBAND"]
        detector = int(wcs_wave_header.get("DETECTOR", 0))
        if detector not in range(1, 7) or any(
            int(hdu.header.get("DETECTOR", 0)) != detector for hdu in (cwave, cband)
        ):
            raise ValueError("Spectral calibration detector does not match the exposure.")
        if not expected_source or any(
            _calibration_source(hdu.header) != expected_source for hdu in (cwave, cband)
        ):
            raise ValueError("Spectral calibration source does not match the exposure.")
        if any(
            hdu.shape != (DETECTOR_PIXELS, DETECTOR_PIXELS)
            or hdu.header.get("BUNIT") != "um"
            for hdu in (cwave, cband)
        ):
            raise ValueError("Expected full detector calibration maps in micrometers.")
        return SpectralCalibration(detector, expected_source, cwave.data, cband.data)


def _parent_pixel(image_header: fits.Header, x: float, y: float) -> tuple[float, float]:
    # Cutout WCS returns zero-based pixels, but CRPIXnA follows FITS indexing.
    parent_x = 1 + x - image_header["CRPIX1A"]
    parent_y = 1 + y - image_header["CRPIX2A"]
    if not all(-0.5 <= value < DETECTOR_PIXELS - 0.5 for value in (parent_x, parent_y)):
        raise ValueError("Position is outside the original detector.")
    return parent_x, parent_y


def wavelength_at(
    calibration: SpectralCalibration, image_header: fits.Header, x: float, y: float
) -> tuple[float, float]:
    """Return wavelength and bandwidth in µm at the nearest original detector pixel."""
    parent_x, parent_y = _parent_pixel(image_header, x, y)
    index = (int(np.floor(parent_y + 0.5)), int(np.floor(parent_x + 0.5)))
    wavelength = float(calibration.cwave[index])
    bandwidth = float(calibration.cband[index])
    if not all(np.isfinite(value) and value > 0 for value in (wavelength, bandwidth)):
        raise ValueError("Expected positive finite wavelength and bandwidth.")
    return wavelength, bandwidth


def epsf_at(hdul: fits.HDUList, x: float, y: float) -> Epsf:
    """Select the nearest release-provided ePSF at zero-based cutout position (x, y)."""
    parent_x, parent_y = _parent_pixel(hdul["IMAGE"].header, x, y)
    extension = hdul["EPSF"]
    zones = extension.data
    distances = np.hypot(zones["XCENTER"] - parent_x, zones["YCENTER"] - parent_y)
    if not distances.size or not np.isfinite(distances).all():
        raise ValueError("Invalid ePSF zone coordinates.")
    nearest = zones[np.argmin(distances)]
    data = np.asarray(nearest["EPSF"], dtype=float)
    oversampling = (int(extension.header["OVSMPY"]), int(extension.header["OVSMPX"]))
    if data.ndim != 2 or not np.isfinite(data).all() or min(oversampling) < 1:
        raise ValueError("Invalid ePSF data or oversampling.")
    zone = (int(nearest["BINX"]), int(nearest["BINY"]))
    return Epsf(data, oversampling, zone)
