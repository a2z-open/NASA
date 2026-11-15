# Third-party notices

PARALLAX's own code is released under the MIT licence (see LICENSE). It depends on, or bundles, the software and data
listed below. Data citations are in DATA_SOURCES.md.

## Reused scientific code and data

| Component | Version | Licence | How it is used |
|---|---|---|---|
| SPIFF: Gagné et al. 2026, arXiv:2604.22012, https://github.com/jgagneastro/SPIFF | commit 5252fc4 (package 0.1.1) | MIT, © 2026 Jonathan Gagné | Installed as a dependency, not vendored into this repo. PARALLAX calls `spiff.autotype` (template comparison: chi-square with a 10 % uncertainty floor, worst-5 rejection, non-field-grid penalties) and uses SPIFF's bundled SPHEREx templates and 102-bin wavelength table. PARALLAX does not use SPIFF's Level-2 extraction (`spiff-lv2`/`spiff-fit`); it does its own motion-corrected extraction, because those tools expect the QR2 PSF cube layout. |

PARALLAX does not copy code from other Space Apps projects (SPHEREx Blink 3.0, SpectraShift, Driftnet, SkyShift and
others). Ideas they share with PARALLAX, such as blinking, path-following photometry and dossiers, are acknowledged in the README.

## Python runtime dependencies

| Package | Version tested | Licence |
|---|---|---|
| astropy (+ pyerfa, astropy-iers-data) | 8.0.2 | BSD-3-Clause |
| numpy | 2.5.4 | BSD-3-Clause (plus bundled permissive licences) |
| scipy | 1.18.1 | BSD-3-Clause |
| requests | 2.34.2 | Apache-2.0 |
| fastapi / starlette | 0.162.7 / 1.10.0 | MIT / BSD-3-Clause |
| uvicorn | 0.54.0 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause (used by the original `api/lookup.py`) |
| pillow | 13.0.0 | MIT-CMU (used by the original `pipeline/archive.py`) |
| pandas, joblib, matplotlib | 3.1.1, 1.6.0, 3.11.2 | BSD-3-Clause, BSD-3-Clause, PSF-based (all pulled in by SPIFF) |
| pytest (development only) | — | MIT |

## Frontend dependencies

See `web/package.json` for exact versions.

- React and React DOM: MIT
- Vite and @vitejs/plugin-react: MIT
- TypeScript: Apache-2.0
- Web font from Google Fonts, under the SIL Open Font License 1.1: Hanken Grotesk (all text).

## Photographs used in the interface

These are real NASA photographs (and two artist's impressions, labelled as such), downloaded from the NASA Image and
Video Library (images.nasa.gov) on 14 Nov 2026, then cropped and compressed. They decorate the pages; none of them is
PARALLAX data and none is presented as a PARALLAX result. NASA imagery is generally not copyrighted; each is credited
as NASA asks, and its use here does not imply NASA's endorsement. Files are in `web/public/img/`.

| File | NASA ID | What it is | Credit |
|---|---|---|---|
| `pluto.webp` | PIA19952 | Pluto in enhanced colour, New Horizons, 14 July 2015 | NASA/Johns Hopkins University Applied Physics Laboratory/Southwest Research Institute |
| `pluto-horizon.webp` | PIA19948 | Pluto's mountains and haze, backlit, New Horizons | NASA/Johns Hopkins University Applied Physics Laboratory/Southwest Research Institute |
| `neptune.webp` | PIA01492 | Neptune, Voyager 2, 1989 | NASA/JPL |
| `wise-sky.webp`, `wise-sky-centre.webp` | PIA15481 | The whole infrared sky from WISE | NASA/JPL-Caltech/UCLA |
| `cold-dwarf.webp` | PIA18001 | WISE J0855−0714, artist's impression | NASA/JPL-Caltech/Penn State University |
| `spherex-dust.webp` | PIA26352 | Dust in the Large Magellanic Cloud, SPHEREx, 3.29 µm | NASA/JPL-Caltech |
| `spherex-vela.webp`, `spherex-vela-wide.webp` | PIA26354 | The Vela Molecular Ridge, SPHEREx | NASA/JPL-Caltech |
| `spherex-orbit.webp` | PIA26531 | SPHEREx in orbit, artist's concept (not currently shown) | NASA/JPL-Caltech |
| `spherex-assembly.webp` | PIA26543 | SPHEREx in final assembly, March 2024 | NASA/JPL-Caltech/BAE Systems |
| `spherex-glow.webp`, `spherex-glow-soft.webp` | (unknown) | SPHEREx as a silhouette above the glowing edge of Earth, illustration; opening picture of the home page; the soft file is a blurred copy used as a tint | Supplied by the team on 14 Nov 2026 as "SPHEREx Silhouette Above Earth's Glow". **TEAM TODO: confirm who made it and its licence, then fix this credit and the home-page footer.** It was not found among NASA/JPL-Caltech releases. |

The design direction was dealt with the `design-taste-frontend` skill. The home page follows the section order of
eclipse.space (a reference the team supplied); no code, fonts, text or images from the reference sites were copied.

## External services called at runtime

| Service | Purpose | Terms |
|---|---|---|
| NASA/IPAC IRSA SIA2 and cutout service | SPHEREx observations | Public NASA archive; cite per DATA_SOURCES.md |
| ESA Gaia archive TAP | Gaia DR3 field stars | ESA Gaia data terms; cite Gaia Collaboration 2023 |
| CDS Sesame / SIMBAD (CfA mirror) | Object-name resolution | CDS terms; cite Wenger et al. 2000 |
| NASA/IPAC IRSA TAP (CatWISE2020) | Decade-baseline check of movers | Public NASA archive; cite Marocco et al. 2021 |
| IMCCE SkyBoT | Known solar-system objects near a source | IMCCE terms; cite Berthier et al. 2006 |

## Added on 14 Nov 2026 (fourth session)

- **Aladin Lite 3.8.2** (CDS, Strasbourg; https://github.com/cds-astro/aladin-lite), the sky-map library on the Sky map page. The npm
  package metadata says "GPL-3"; the LICENSE file shipped in the package is the GNU LGPL v3 (with COPYING and COPYING.LESSER). It is used
  unmodified and loaded as its own separate file (`web/dist/assets/aladin-*.js`) only on the Sky map page. TEAM TODO: confirm this use
  is acceptable under its licence before publishing.
- **All-sky map layers (HiPS)** served by NASA/IPAC IRSA: the SPHEREx DR1 all-sky data cube (SPHEREx Science Data Center, NASA/SPHEREx,
  Caltech/IPAC), and AllWISE, 2MASS, DSS2 and IRAS (IRIS) layers made by CDS. Loaded from IRSA at viewing time; nothing is copied.
- **scikit-learn 1.9.1** (BSD-3-Clause), used only by `validation/ml_realbogus.py`.
- **JPL Horizons** (NASA/JPL) and **CatWISE2020** via NOIRLab Astro Data Lab, as listed in DATA_SOURCES.md.

- **astropy-healpix 2.0.1** (BSD-3-Clause), used by `pipeline/cubespec.py` to find the HEALPix tile of a sky position.
- **joblib** (BSD-3-Clause, installed with scikit-learn), used to store the locked model `validation/coldspec/model.joblib`.
- Fonts: **Inter** and **Barlow** (SIL Open Font License 1.1), loaded from Google Fonts. On Apple devices the system font is used instead.
- Home page photograph: SPHEREx in orbit, illustration by NASA/JPL-Caltech. Footer: Pluto's horizon, NASA/JHUAPL/SwRI.

## Sky-map picture layers from other telescopes (fifth session)

The sky map can show pictures from other telescopes, loaded by the viewer's browser directly from the archives that publish
them as HiPS tiles. None are copied into this repository. Credits, as each publisher asks: JWST (NASA/ESA/CSA; tiles from
ESA's eJWST archive via ESASky), Hubble (NASA/ESA; eHST via ESASky), Spitzer (NASA/JPL-Caltech; ESASky), AKARI (JAXA), Herschel
(ESA), Gaia DR3 (ESA/Gaia/DPAC), Fermi (NASA; HEALPixed by CDS), INTEGRAL (ESA), WISE, 2MASS, IRAS/IRIS, DSS2, SDSS and Planck
(tiles from NASA/IPAC IRSA, many HEALPixed by CDS), Pan-STARRS DR1 (PS1 Science Consortium; tiles from STScI/MAST), GALEX
(NASA; STScI/MAST), VISTA VHS (ESO) and UKIDSS (UKIRT/WFAU; both hosted by Paris Observatory PADC), Swift UVOT (NASA; HEASARC
SkyView), Chandra (NASA/CXC), XMM-Newton (ESA), eROSITA DR1 (MPE/IKI). The map's status line names the source of the layer
being shown.
