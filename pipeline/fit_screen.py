"""Screen earlier Barnard visits. The reserve has no pixel input to this tool."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates
from scipy.optimize import least_squares

from pipeline.calibration import epsf_at

BARNARD_ID = "4472832130942575872"
GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
# SOURCE and FULLSAMPLE remain eligible. This exploratory screen rejects known
# hard failures and artifact flags, including saturated pixels.
EXCLUSIONS = {
    "TRANSIENT", "OVERFLOW", "SUR_ERROR", "NONFUNC", "DICHROIC", "MISSING_DATA",
    "HOT", "COLD", "PHANMISS", "NONLINEAR", "PERSIST", "OUTLIER", "CROSSTALK",
    "GHOST", "GHOST_FPA", "GHOST_EXT", "STREAK", "BLOOM", "SNOWBALL", "HALO",
}


def fit_manifest_rows(manifest):
    rows = manifest["fit_frames"]
    reserve = manifest["reserve"]
    if not reserve or not rows:
        raise ValueError("Fit frames and reserved metadata are both required")
    reserved_ids = set(reserve["obs_ids"])
    reserved_visits = set(reserve["visit_ids"])
    for row in rows:
        if (row["visit_id"] in reserved_visits or row["id"].rsplit("-", 1)[0] in reserved_ids
                or row["mjd_avg"] >= reserve["t_min"]):
            raise ValueError(f"The fit manifest contains a reserved frame: {row['id']}")
    if len({row["visit_id"] for row in rows}) != 2:
        raise ValueError("Expected exactly two earlier fit visits")
    return rows


def reference_offsets(offsets):
    # Stable split based on Gaia source IDs, before any residuals are inspected.
    registration = [offset for key, offset in offsets.items() if int(key) % 5 != 0]
    validation = {key: offset for key, offset in offsets.items() if int(key) % 5 == 0}
    if len(registration) < 3 or not validation:
        raise ValueError("Insufficient accepted registration or held-back reference stars")
    shift = np.median(registration, axis=0)
    return shift, {key: value - shift for key, value in validation.items()}


def gaia_sources(ra, dec):
    query = f"""SELECT TOP 80 source_id,ra,dec,ref_epoch,pmra,pmdec,parallax,phot_g_mean_mag
    FROM gaiadr3.gaia_source
    WHERE 1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{ra:.9f},{dec:.9f},0.13))
    AND pmra IS NOT NULL AND pmdec IS NOT NULL AND phot_g_mean_mag < 17
    ORDER BY phot_g_mean_mag"""
    params = urlencode({"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": query})
    with urlopen(f"{GAIA_TAP}?{params}", timeout=20) as response:
        return list(csv.DictReader(io.StringIO(response.read().decode("utf-8"))))


def propagated_position(source, when):
    origin = SkyCoord(float(source["ra"]), float(source["dec"]), unit="deg")
    elapsed_years = when.jyear - float(source["ref_epoch"])
    return origin.spherical_offsets_by(
        float(source["pmra"]) * elapsed_years * u.mas,
        float(source["pmdec"]) * elapsed_years * u.mas,
    )


def centroid(hdul, x, y, mask_bits, *, omit_core=False):
    image = hdul["IMAGE"].data
    variance = hdul["VARIANCE"].data
    flags = hdul["FLAGS"].data
    radius = 5
    if not (np.isfinite(x) and np.isfinite(y)):
        return None
    ix, iy = round(float(x)), round(float(y))
    if not (radius <= ix < image.shape[1] - radius and radius <= iy < image.shape[0] - radius):
        return None
    cutout = np.s_[iy - radius:iy + radius + 1, ix - radius:ix + radius + 1]
    yy, xx = np.mgrid[iy - radius:iy + radius + 1, ix - radius:ix + radius + 1]
    pixels, var, pixel_flags = image[cutout], variance[cutout], flags[cutout]
    valid = np.isfinite(pixels) & np.isfinite(var) & (var > 0) & ((pixel_flags & mask_bits) == 0)
    distance2 = (xx - x) ** 2 + (yy - y) ** 2
    if omit_core:
        valid &= distance2 >= 1.5 ** 2
    if valid.sum() < 60 or np.count_nonzero(valid & (distance2 < 3 ** 2)) < 7:
        return None
    if not omit_core and not valid[radius, radius]:
        return None
    noise = np.sqrt(var[valid])
    background = np.median(pixels[valid])
    if omit_core and np.max((pixels[valid] - background) / noise) < 5:
        return None
    psf = epsf_at(hdul, x, y)
    cy, cx = (np.array(psf.data.shape) - 1) / 2
    sy, sx = psf.oversampling
    py, px = yy[valid], xx[valid]

    def residual(parameters):
        fit_x, fit_y, amplitude, local_bg = parameters
        sampled = map_coordinates(psf.data, [cy + (py - fit_y) * sy, cx + (px - fit_x) * sx], order=3)
        return (amplitude * sampled + local_bg - pixels[valid]) / noise

    amplitude_guess = max(1.0, float((pixels[valid].max() - background) / psf.data.max()))
    fit = least_squares(
        residual, [x, y, amplitude_guess, background],
        bounds=([x - 2, y - 2, 0, -np.inf], [x + 2, y + 2, np.inf, np.inf]),
    )
    fx, fy = fit.x[:2]
    if not fit.success or max(abs(fx - x), abs(fy - y)) >= 1.9:
        return None
    null_cost = np.sum(((pixels[valid] - np.average(pixels[valid], weights=1 / var[valid])) / noise)**2)
    chi2 = float(fit.fun @ fit.fun)
    if null_cost - chi2 < 25:
        return None
    return fx, fy, chi2 / (valid.sum() - 4)


def screen_frame(row, sources, target, expected_center):
    native_path = Path(row["path"])
    if not native_path.is_file() or hashlib.sha256(native_path.read_bytes()).hexdigest() != row["sha256"]:
        raise ValueError(f"Missing or changed fit input: {row['id']}")
    with fits.open(native_path, memmap=False) as hdul:
        header = hdul["IMAGE"].header
        when = Time(header["MJD-AVG"], format="mjd", scale="utc")
        wcs = WCS(header, naxis=2).celestial
        bits = hdul["FLAGS"].header
        found = {str(bits[key]): int(key[4:]) for key in bits if key.startswith("MSKN") and key[4:].isdigit()}
        if not {"OVERFLOW", "NONLINEAR"}.issubset(found):
            raise ValueError("Unrecognized SPHEREx quality flags")
        mask_bits = sum(1 << found[name] for name in EXCLUSIONS & found.keys())
        offsets = {}
        wing_checks = {}
        target_fit = None
        target_wings = None
        for source in [target, *sources]:
            key = source["source_id"]
            position = propagated_position(source, when)
            seed = wcs.world_to_pixel(position)
            fit = centroid(hdul, *seed, mask_bits)
            if key == BARNARD_ID:
                wings = centroid(hdul, *seed, mask_bits, omit_core=True)
                if wings is not None:
                    target_wings = (wcs.pixel_to_world(*wings[:2]), wings[2])
            if fit is None:
                continue
            measured = wcs.pixel_to_world(fit[0], fit[1])
            if key == BARNARD_ID:
                target_fit = (measured, fit[2])
            elif fit[2] <= 5:
                east, north = position.spherical_offsets_to(measured)
                offsets[key] = np.array([east.arcsec, north.arcsec])
                if int(key) % 5 == 0:
                    wings = centroid(hdul, *seed, mask_bits, omit_core=True)
                    if wings is not None and wings[2] <= 5:
                        wing_checks[key] = float(measured.separation(wcs.pixel_to_world(*wings[:2])).arcsec)
        row_result = {"id": row["id"], "visit_id": row["visit_id"], "detector": row["detector"], "mjd_avg": float(when.mjd)}
        try:
            shift, held_out = reference_offsets(offsets)
        except ValueError as error:
            return {**row_result, "status": str(error), "accepted_references": len(offsets)}
        row_result.update({
            "accepted_references": len(offsets),
            "registration_shift_arcsec": shift.tolist(),
            "held_back_reference_residuals_arcsec": {key: val.tolist() for key, val in held_out.items()},
            "held_back_wing_vs_core_arcsec": wing_checks,
        })
        if target_wings is not None:
            east, north = expected_center.spherical_offsets_to(target_wings[0])
            row_result["exploratory_wing_fit"] = {
                "registered_target_tangent_arcsec": (np.array([east.arcsec, north.arcsec]) - shift).tolist(),
                "reduced_chi_square": target_wings[1],
            }
        if target_fit is None:
            return {**row_result, "status": "No eligible target core fitted"}
        east, north = expected_center.spherical_offsets_to(target_fit[0])
        return {
            **row_result, "status": "exploratory centroid",
            "registered_target_tangent_arcsec": (np.array([east.arcsec, north.arcsec]) - shift).tolist(),
            "target_reduced_chi_square": target_fit[1],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    rows = fit_manifest_rows(manifest)
    center = manifest["center"]
    sources = gaia_sources(float(center["ra"]), float(center["dec"]))
    target = next((source for source in sources if source["source_id"] == BARNARD_ID), None)
    if target is None:
        raise ValueError("Gaia response did not include the Barnard’s Star source")
    references = [source for source in sources if source["source_id"] != BARNARD_ID
                  and np.hypot(float(source["pmra"]), float(source["pmdec"])) < 30]
    sky_center = SkyCoord(center["ra"], center["dec"], unit="deg")
    results = [screen_frame(row, references, target, sky_center) for row in rows]
    visits = {}
    for visit_id in dict.fromkeys(row["visit_id"] for row in rows):
        group = [frame for frame in results if frame["visit_id"] == visit_id]
        positions = [frame["registered_target_tangent_arcsec"] for frame in group
                     if "registered_target_tangent_arcsec" in frame]
        residuals = [np.linalg.norm(residual) for frame in group
                     for residual in frame.get("held_back_reference_residuals_arcsec", {}).values()]
        visits[visit_id] = {
            "frames_screened": len(group), "target_centroids": len(positions),
            "reference_checks": len(residuals),
            "median_reference_residual_arcsec": float(np.median(residuals)) if residuals else None,
            "target_repeat_scatter_arcsec": np.std(positions, axis=0, ddof=1).tolist() if len(positions) > 1 else None,
        }
    report = {
        "scope": "Exploratory early-visit screen, catalog-assisted position seeds, no reserved frames",
        "limitations": ["No observer parallax correction", "No wavelength-match claim", "No validated motion verdict",
                        "Repeat scatter is descriptive across available exposures, including possible different bandpasses"],
        "tangent_origin_degrees": center, "reference_catalog": "Gaia DR3",
        "reference_catalog_endpoint": GAIA_TAP, "target_seed": target, "reference_seeds": references,
        "frame_inputs": [{key: row[key] for key in ("id", "sha256", "archive_url")} for row in rows],
        "visits": visits, "frames": results,
    }
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
