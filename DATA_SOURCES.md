# Data sources, citations and provenance

PARALLAX's core functionality runs on NASA SPHEREx spectral images. Every image you see and every number PARALLAX
reports comes from the products below. Machine-readable provenance for each target is in
`data/targets/<slug>/provenance.json`, which gives the archive URL, cutout URL, SHA-256, epoch, detector, wavelength and flags.
The prediction experiment's manifests are in `validation/experiments/`.

## NASA data (primary)

| Dataset | Release | Provider | Citation / DOI | How PARALLAX uses it |
|---|---|---|---|---|
| SPHEREx Spectral Images (Level 2) | DR1 (`spherex_dr1` SIA2 collection) | NASA/IPAC Infrared Science Archive (IRSA) | **doi:10.26131/IRSA678** | Search, cutouts, playback frames, and all astrometry, photometry and spectra |
| SPHEREx Spectral Images (Level 2) | QR3 (`spherex_qr3` SIA2 collection) | NASA/IPAC IRSA | Cite according to IRSA's current SPHEREx release guidance. **TEAM TODO:** confirm the QR DOI on the IRSA SPHEREx page before submission. | Same as DR1. The Epsilon Indi B held-out visit (Sep–Oct 2026) is QR3. |

The DR1 Spectral All-Sky Cube (doi:10.26131/IRSA679) is **not** used, so it is not cited as a data source.

**Required acknowledgement (from the IRSA SPHEREx DR1 overview):**

> This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of
> Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California
> Institute of Technology, and is funded by the National Aeronautics and Space Administration.

Access points (all public, no credentials):
- SIA2 discovery: `https://irsa.ipac.caltech.edu/SIA?COLLECTION=spherex_dr1|spherex_qr3&POS=CIRCLE ra dec r` (VOTable).
- Cutouts: `<access_url>?center=<ra>,<dec>&size=<N>arcmin`, using IRSA's documented cutout service. Every cutout is a
  multi-extension FITS file with IMAGE (MJy/sr, zodiacal light not subtracted), FLAGS, VARIANCE, ZODI, EPSF (a table of
  oversampled effective PSFs) and WCS-WAVE (the spectral WCS lookup table).
- Documentation: https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_dr1.html ·
  https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/ ·
  https://irsa.ipac.caltech.edu/data/SPHEREx/docs/cutout_tool.html

Release handling:
- QR2 is not searchable through SIA2 and is not used.
- DR1 and QR3 are queried together and deduplicated by `(obs_id, detector)`, preferring DR1.
- New collections are added in `pipeline/spherex.py:RELEASES`.

### Units, calibration and quality conventions

- **Time.** `MJD-AVG` (the exposure midpoint) from the IMAGE header. `DATE` is a processing date and is never used.
- **Wavelength.** Read per pixel from the spectral WCS: `WCS(header, fobj=hdul, key='W')`, with SIP disabled for that
  WCS. The per-PSF-zone `CWAVE`/`CBAND` table values are not used for science.
- **Flux.** µJy = Σ(MJy/sr) × `OMEGA_MEDIAN` (arcsec² → sr) × 10¹². The median pixel solid angle is a stated approximation.
- **Flags.** Bit names are read from each file's `MSKN*` cards.
  - Hard-masked: OVERFLOW, SUR_ERROR, NONFUNC, MISSING_DATA, HOT, COLD, NONLINEAR, PERSIST.
  - The strict path also masks OUTLIER and TRANSIENT. OUTLIER is not masked in general, because SPHEREx can set it on genuine movers.
  - SOURCE and FULLSAMPLE are informational.
  - Saturation (OVERFLOW/NONLINEAR within 1.5 px of a source) excludes that exposure from position and core-flux measurements.

## Other catalogues and references

| Resource | Used for | Citation | Access |
|---|---|---|---|
| Gaia DR3 | Reference astrometry for Epsilon Indi B, Barnard's Star, RW Aur and R Dra. Field stars for registration, deblending and negative controls. Catalogue overlay. | Gaia Collaboration, Vallenari et al. 2023, A&A 674, A1 (doi:10.1051/0004-6361/202243940) | ESA Gaia TAP, https://gea.esac.esa.int/tap-server/tap |
| Kirkpatrick et al. 2021, "A full-sky census of brown dwarfs within 20 pc" | WISE 0855−0714 astrometry: position at MJD 57633.39, μα* = −8123.7 ± 1.3 mas/yr, μδ = 673.2 ± 1.3 mas/yr, ϖ = 439.0 ± 2.4 mas | ApJS 253, 7 (2021); VizieR J/ApJS/253/7 (doi:10.26093/cds/vizier/bb-7x-7) | VizieR CfA mirror, retrieved 2026-11-14 (the CDS primary was unavailable) |
| SIMBAD via Sesame | Name resolution for arbitrary objects in the search box | Wenger et al. 2000, A&AS 143, 9 | https://vizier.cfa.harvard.edu/viz-bin/nph-sesame (CfA mirror) |
| SPIFF spectral templates and 102-bin SPHEREx table | Template comparison of motion-corrected spectra | Gagné et al. 2026, "A SPHEREx Pipeline and Spectral Library for Ultracool Dwarfs", arXiv:2604.22012; code at https://github.com/jgagneastro/SPIFF, commit 5252fc4 (MIT licence) | Installed locally from the pinned commit |
| NASA Space Apps 2026 challenge "Planet X and SPHEREx" | Target list and the historical WISE 0855 coordinate (08h55m10.831s −07°14′42.53″, used only as context) | https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/ | — |

Not used, despite being mentioned in planning: WISE/NEOWISE images, CatWISE2020 (queried once and found to split
WISE 0855 into several entries), the MOCA database and the all-sky cube. They are not cited as data sources.

## Provenance records

- `data/targets/<slug>/archive_manifest.json`:
  - every SPHEREx product the archive lists for the field (ID, release, collection, access URL, times, wavelength range, cloud key)
  - the visit grouping
  - which products were sealed
- `data/targets/<slug>/provenance.json`: one entry per measured exposure, with archive URL, cutout URL, SHA-256 of the downloaded FITS, MJD, detector, release, wavelength at the source and flags near the source. It also lists the processing steps.
- `data/targets/<slug>/field.json`: per-frame URLs, SHA-256 and processing versions for every display frame.
- `validation/experiments/epsilon-indi-b/`:
  - `prediction.json` and its SHA-256: the locked prediction, training-set summary and protocol
  - `training_measurements.json` and `heldout_measurements.json`: per-exposure measurements
  - `result.json`: the evaluation
- Raw FITS cutouts are cached in `.parallax-cache/` (not committed; about 4 MB each). Each one can be re-downloaded from its recorded cutout URL and checked against its SHA-256.

Retrieval date for all cached data: 2026-11-14 (UTC). Usage conditions: SPHEREx data are public NASA data distributed
by IRSA; Gaia data are public under ESA's terms; both require the citations above.

PARALLAX is an independent hackathon project. It is not affiliated with or endorsed by NASA, JPL, Caltech, IPAC or ESA.
