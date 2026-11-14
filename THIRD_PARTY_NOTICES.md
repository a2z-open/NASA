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
- Web fonts are loaded from Google Fonts under the SIL Open Font License. **TEAM TODO:** confirm the font families the frontend actually loads.

## External services called at runtime

| Service | Purpose | Terms |
|---|---|---|
| NASA/IPAC IRSA SIA2 and cutout service | SPHEREx observations | Public NASA archive; cite per DATA_SOURCES.md |
| ESA Gaia archive TAP | Gaia DR3 field stars | ESA Gaia data terms; cite Gaia Collaboration 2023 |
| CDS Sesame / SIMBAD (CfA mirror) | Object-name resolution | CDS terms; cite Wenger et al. 2000 |
