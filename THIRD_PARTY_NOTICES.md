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

The design direction was dealt with the `design-taste-frontend` skill; no code, fonts or images from the reference
sites the team supplied were copied.

## External services called at runtime

| Service | Purpose | Terms |
|---|---|---|
| NASA/IPAC IRSA SIA2 and cutout service | SPHEREx observations | Public NASA archive; cite per DATA_SOURCES.md |
| ESA Gaia archive TAP | Gaia DR3 field stars | ESA Gaia data terms; cite Gaia Collaboration 2023 |
| CDS Sesame / SIMBAD (CfA mirror) | Object-name resolution | CDS terms; cite Wenger et al. 2000 |
| NASA/IPAC IRSA TAP (CatWISE2020) | Decade-baseline check of movers | Public NASA archive; cite Marocco et al. 2021 |
| IMCCE SkyBoT | Known solar-system objects near a source | IMCCE terms; cite Berthier et al. 2006 |
