"""The five NASA challenge targets, with authoritative reference astrometry.

Every number here was retrieved from a named catalogue on 2026-11-14 (see
DATA_SOURCES.md). Nothing is guessed: if a catalogue lacks a value, the field is
None and the pipeline treats the corresponding model term as unavailable.
"""

from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class Astrometry:
    ra_deg: float
    dec_deg: float
    epoch_jyear: float | None          # Julian-year epoch of ra/dec, or None
    epoch_mjd: float | None            # MJD epoch, used when the catalogue gives MJD
    pmra_masyr: float | None           # mu_alpha * cos(delta)
    pmdec_masyr: float | None
    parallax_mas: float | None
    pmra_err: float | None = None
    pmdec_err: float | None = None
    parallax_err: float | None = None
    source: str = ''
    source_url: str = ''


@dataclass(frozen=True)
class Target:
    slug: str
    title: str
    kind: str
    purpose: str
    astrometry: Astrometry
    field_arcmin: float = 10.0
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self):
        return asdict(self)


GAIA_URL = 'https://gea.esac.esa.int/archive/'

TARGETS: dict[str, Target] = {
    'epsilon-indi-b': Target(
        'epsilon-indi-b', 'Epsilon Indi B', 'Brown-dwarf binary (unresolved)',
        'Motion recovery, held-out prediction and substellar spectroscopy',
        Astrometry(331.07645259656397, -56.79381206688221, 2016.0, None,
                   3981.97666296105, -2466.8318147663504, 270.6580324694526,
                   0.6016568, 0.6256827, 0.6895573,
                   'Gaia DR3 6412596012146801152 (RUWE 4.30: astrometric binary, treat errors as optimistic)',
                   GAIA_URL),
        notes=(
            'Ba (T1) and Bb (T6) are separated by well under one 6.15" SPHEREx pixel; PARALLAX measures the combined light.',
            'Epsilon Indi A (Gaia DR3 6412595290592307840, G = 4.3) lies about 7 arcmin away and is outside the default 10 arcmin field.',
        ),
    ),
    'barnards-star': Target(
        'barnards-star', "Barnard's Star", 'Nearby M4 dwarf',
        'Large stellar proper motion (about 10.4 arcsec per year)',
        Astrometry(269.44850252543836, 4.739420051112412, 2016.0, None,
                   -801.5509783684709, 10362.394206546573, 546.975939730948,
                   0.031820867, 0.036070455, 0.040116355,
                   'Gaia DR3 4472832130942575872', GAIA_URL),
        notes=('Very bright in the near-infrared (K about 4.5); SPHEREx cores are expected to saturate.',),
    ),
    'wise-0855': Target(
        'wise-0855', 'WISE 0855-0714', 'Coldest known brown dwarf (Y dwarf, about 250 K)',
        'Can SPHEREx see an extremely cold, fast-moving substellar object at 4-5 micrometres?',
        Astrometry(133.780984, -7.243932, None, 57633.39,
                   -8123.7, 673.2, 439.0, 1.3, 1.3, 2.4,
                   'Kirkpatrick et al. 2021, ApJS 253, 7 (J/ApJS/253/7, parallax and motion fit)',
                   'https://vizier.cfa.harvard.edu/viz-bin/VizieR?-source=J/ApJS/253/7'),
        notes=(
            'Not in Gaia DR3 (too faint in the optical).',
            'NASA brief coordinate 08h55m10.831s -07d14m42.53s is a historical (WISE discovery era) position; '
            'PARALLAX propagates the Spitzer-based solution to each SPHEREx epoch instead of searching that spot.',
            'Mass and formation interpretation are model-dependent; PARALLAX does not call it a rogue planet.',
        ),
    ),
    'rw-aurigae': Target(
        'rw-aurigae', 'RW Aurigae', 'Young T Tauri binary with disk',
        'Brightness variability, wavelength-aware light curves',
        Astrometry(76.9565443110343, 30.401316149887936, 2016.0, None,
                   4.90603392110511, -24.577534567492915, 5.454096456582266,
                   0.32915834, 0.25464907, 0.33244956,
                   'Gaia DR3 156430817820015232 (RW Aur A, RUWE 16.4)', GAIA_URL),
        notes=('RW Aur B (Gaia DR3 156430822114424576) is about 1.4 arcsec away: always blended in SPHEREx.',),
    ),
    'r-draconis': Target(
        'r-draconis', 'R Draconis', 'Mira variable (asymptotic giant branch)',
        'Large-amplitude variability; naive vs wavelength-matched comparison',
        Astrometry(248.1673783672889, 66.75500674547219, 2016.0, None,
                   -20.642811719160797, 6.148818852711324, 1.2509180143740992,
                   0.08512829, 0.091321476, 0.0647879,
                   'Gaia DR3 1648328016354496384', GAIA_URL),
        notes=('Extremely bright in the infrared; saturation is expected in many channels.',),
    ),
}

ORDER = ['epsilon-indi-b', 'barnards-star', 'wise-0855', 'rw-aurigae', 'r-draconis']
