"""Coordinates, epochs, proper motion, parallax and tangent-plane geometry.

Conventions
-----------
* Frame: ICRS. Angles in degrees unless a name says otherwise.
* Proper motion in RA is always mu_alpha* = mu_alpha cos(delta) (mas/yr).
* Local motion fits work in a gnomonic tangent plane (xi, eta) in arcsec,
  never in raw RA/Dec differences.
* Parallax displacement uses the barycentric position of the Earth.  SPHEREx
  orbits the Earth at about 700 km, which changes a 1000 mas parallax by
  less than 0.02 mas, so the Earth's position is adequate here.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re

import numpy as np
from astropy import units as u
from astropy.coordinates import Angle, SkyCoord, get_body_barycentric
from astropy.time import Time

MAS = 1.0 / 3.6e6          # degrees per milliarcsecond
ARCSEC = 1.0 / 3600.0
JULIAN_YEAR_DAYS = 365.25


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

class CoordinateError(ValueError):
    pass


_SEXA = re.compile(r'[hdms:°\'"′″\s]+', re.IGNORECASE)


def _looks_sexagesimal(text: str) -> bool:
    return bool(re.search(r'[hdms:°\'"′″]|\d\s+\d', text.strip(), re.IGNORECASE))


def parse_ra(text) -> float:
    """Parse RA as decimal degrees or sexagesimal hours (e.g. 08h55m10.8s, 08:55:10.8)."""
    if isinstance(text, (int, float)):
        value = float(text)
    else:
        s = str(text).strip()
        if not s:
            raise CoordinateError('Right Ascension is empty.')
        try:
            if _looks_sexagesimal(s):
                value = Angle(s.replace('′', 'm').replace('″', 's'), unit=u.hourangle).degree
            else:
                value = float(s)
        except (ValueError, u.UnitsError) as error:
            raise CoordinateError(f'Could not read Right Ascension "{s}".') from error
    if not math.isfinite(value) or not 0 <= value <= 360:
        raise CoordinateError('Right Ascension must be between 0 and 360 degrees (0h to 24h).')
    return value % 360.0


def parse_dec(text) -> float:
    """Parse Dec as decimal degrees or sexagesimal degrees (e.g. -07d14m42.5s, -07:14:42.5)."""
    if isinstance(text, (int, float)):
        value = float(text)
    else:
        s = str(text).strip().replace('−', '-')
        if not s:
            raise CoordinateError('Declination is empty.')
        try:
            if _looks_sexagesimal(s):
                value = Angle(s.replace('°', 'd').replace('′', 'm').replace('″', 's'), unit=u.deg).degree
            else:
                value = float(s)
        except (ValueError, u.UnitsError) as error:
            raise CoordinateError(f'Could not read Declination "{s}".') from error
    if not math.isfinite(value) or not -90 <= value <= 90:
        raise CoordinateError('Declination must be between -90 and +90 degrees.')
    return value


def parse_position(text: str) -> tuple[float, float]:
    """Parse a single 'RA Dec' string in decimal or sexagesimal form."""
    s = text.strip().replace(',', ' ').replace('−', '-')
    parts = s.split()
    if len(parts) == 2:
        return parse_ra(parts[0]), parse_dec(parts[1])
    if len(parts) == 6:
        return parse_ra(' '.join(parts[:3])), parse_dec(' '.join(parts[3:]))
    m = re.match(r'^(.*?[\d.]+s?)\s*([+-].*)$', s)
    if m:
        return parse_ra(m.group(1)), parse_dec(m.group(2))
    raise CoordinateError('Enter coordinates as "RA Dec", e.g. "331.0957 -56.8003" or "22h04m23s -56d48m01s".')


def format_sexagesimal(ra: float, dec: float) -> tuple[str, str]:
    c = SkyCoord(ra * u.deg, dec * u.deg, frame='icrs')
    return (c.ra.to_string(unit=u.hourangle, sep='hms', precision=2, pad=True),
            c.dec.to_string(unit=u.deg, sep='dms', precision=1, alwayssign=True, pad=True))


# --------------------------------------------------------------------------
# Time
# --------------------------------------------------------------------------

def jyear_to_mjd(jyear: float) -> float:
    return float(Time(jyear, format='jyear', scale='tcb').mjd)


def mjd_to_iso(mjd: float) -> str:
    return Time(mjd, format='mjd', scale='utc').isot + 'Z'


def mjd_to_jyear(mjd: float) -> float:
    return float(Time(mjd, format='mjd', scale='utc').jyear)


# --------------------------------------------------------------------------
# Tangent plane
# --------------------------------------------------------------------------

def to_tangent(ra, dec, ra0, dec0):
    """Gnomonic projection: (ra, dec) -> (xi, eta) in arcsec around (ra0, dec0)."""
    ra, dec = np.radians(ra), np.radians(dec)
    a0, d0 = math.radians(ra0), math.radians(dec0)
    cosc = np.sin(d0) * np.sin(dec) + np.cos(d0) * np.cos(dec) * np.cos(ra - a0)
    xi = np.cos(dec) * np.sin(ra - a0) / cosc
    eta = (np.cos(d0) * np.sin(dec) - np.sin(d0) * np.cos(dec) * np.cos(ra - a0)) / cosc
    return np.degrees(xi) * 3600.0, np.degrees(eta) * 3600.0


def from_tangent(xi, eta, ra0, dec0):
    """Inverse gnomonic projection: (xi, eta) arcsec -> (ra, dec) degrees."""
    x = np.radians(np.asarray(xi, dtype=float) / 3600.0)
    y = np.radians(np.asarray(eta, dtype=float) / 3600.0)
    a0, d0 = math.radians(ra0), math.radians(dec0)
    rho = np.hypot(x, y)
    c = np.arctan(rho)
    with np.errstate(invalid='ignore', divide='ignore'):
        dec = np.where(rho == 0, d0, np.arcsin(np.cos(c) * np.sin(d0) + y * np.sin(c) * np.cos(d0) / np.where(rho == 0, 1, rho)))
        ra = a0 + np.arctan2(x * np.sin(c), rho * np.cos(d0) * np.cos(c) - y * np.sin(d0) * np.sin(c))
    return np.degrees(ra) % 360.0, np.degrees(dec)


def separation_arcsec(ra1, dec1, ra2, dec2):
    a = SkyCoord(ra1 * u.deg, dec1 * u.deg)
    b = SkyCoord(ra2 * u.deg, dec2 * u.deg)
    return a.separation(b).arcsec


# --------------------------------------------------------------------------
# Parallax and proper motion
# --------------------------------------------------------------------------

def earth_barycentric_au(mjd) -> np.ndarray:
    """Barycentric (x, y, z) of the Earth in AU (ICRS axes), shape (N, 3)."""
    t = Time(np.atleast_1d(np.asarray(mjd, dtype=float)), format='mjd', scale='utc')
    pos = get_body_barycentric('earth', t)
    return np.vstack([pos.x.to_value(u.au), pos.y.to_value(u.au), pos.z.to_value(u.au)]).T


def parallax_factors(ra_deg: float, dec_deg: float, mjd) -> tuple[np.ndarray, np.ndarray]:
    """Return (P_alpha*, P_delta): displacement per unit parallax (same units as parallax).

    Delta alpha* = plx * (X sin a - Y cos a)
    Delta delta  = plx * (X cos a sin d + Y sin a sin d - Z cos d)
    where (X, Y, Z) is the barycentric Earth position in AU.  The sign is
    verified against astropy's full ICRS->GCRS transform in the tests.
    """
    xyz = earth_barycentric_au(mjd)
    a, d = math.radians(ra_deg), math.radians(dec_deg)
    X, Y, Z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    pa = X * math.sin(a) - Y * math.cos(a)
    pd = X * math.cos(a) * math.sin(d) + Y * math.sin(a) * math.sin(d) - Z * math.cos(d)
    return pa, pd


@dataclass(frozen=True)
class Propagated:
    ra: np.ndarray
    dec: np.ndarray
    xi: np.ndarray          # arcsec, tangent plane at the reference position
    eta: np.ndarray


def propagate(ra0, dec0, epoch_mjd, pmra, pmdec, parallax, mjd, *, include_parallax=True) -> Propagated:
    """Propagate catalogue astrometry to observation epochs (linear motion + parallax).

    Linear tangent-plane propagation is accurate to << 1 mas over the ~10 yr
    baselines used here for every target in this project (|mu| < 11"/yr).
    """
    mjd = np.atleast_1d(np.asarray(mjd, dtype=float))
    dt = (mjd - epoch_mjd) / JULIAN_YEAR_DAYS
    xi = (pmra or 0.0) * dt / 1000.0
    eta = (pmdec or 0.0) * dt / 1000.0
    if include_parallax and parallax:
        pa, pd = parallax_factors(ra0, dec0, mjd)
        xi = xi + parallax * pa / 1000.0
        eta = eta + parallax * pd / 1000.0
    ra, dec = from_tangent(xi, eta, ra0, dec0)
    return Propagated(np.atleast_1d(ra), np.atleast_1d(dec), xi, eta)


def target_epoch_mjd(astrometry) -> float:
    if astrometry.epoch_mjd is not None:
        return float(astrometry.epoch_mjd)
    return jyear_to_mjd(astrometry.epoch_jyear)


def propagate_target(astrometry, mjd, *, include_parallax=True) -> Propagated:
    return propagate(astrometry.ra_deg, astrometry.dec_deg, target_epoch_mjd(astrometry),
                     astrometry.pmra_masyr, astrometry.pmdec_masyr, astrometry.parallax_mas, mjd,
                     include_parallax=include_parallax)
