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

### Added for the blind search, the decade check and the variable stars (14 Nov 2026)

| Source | What it is used for | Citation / access |
|---|---|---|
| **CatWISE2020** | After a source passes the SPHEREx motion test: was it at the same place around 2015 (rejects the motion), or does WISE list a source with the same motion (confirms it over a ~10-year baseline)? Never used to decide where to look. | Marocco et al. 2021, ApJS 253, 8; IRSA table `catwise_2020` through the IRSA TAP service (`https://irsa.ipac.caltech.edu/TAP/sync`); doi:10.26131/IRSA551. Based on WISE and NEOWISE data (Wright et al. 2010; Mainzer et al. 2014). |
| **Gaia DR3, all magnitudes** | Same decade check against Gaia's 2016.0 positions, for sources fainter than the G < 18.5 list used for registration. | Gaia Collaboration, Vallenari et al. 2023, A&A 674, A1; ESA Gaia archive TAP. |
| **SIMBAD through CDS Sesame** | Coordinates, proper motions and spectral types of the known brown dwarfs used as *recovery fields* in the hunt. Used to choose the fields and, after the search, to score it. | Wenger et al. 2000, A&AS 143, 9; Sesame name resolver (CfA mirror). Each resolved record is saved in `validation/hunt_fields.json` with its retrieval time. |
| **IMCCE SkyBoT** | Known asteroids and comets within 60″ of a source at the times it was observed (hypothesis H5). | Berthier et al. 2006, ASP Conf. Ser. 351, 367; `https://ssp.imcce.fr/webservices/skybot/`. Queried from the geocentre. |

The 16 recovery fields and 4 control fields of the hunt are listed in `validation/hunt_fields.py`. For every field,
`data/hunt/<field>/manifest.json` records the archive query, and `data/hunt/<field>/hunt.json` lists every exposure used
with its SHA-256 and archive URL.

### Added for the distant-world search and the Barnard's Star halo test (14 Nov 2026, third session)

| Source | Used for | How it is reached |
|---|---|---|
| JPL Horizons (Giorgini et al. 1996), https://ssd.jpl.nasa.gov/horizons/ | Positions of Pluto, Makemake, Haumea and Eris: to choose which patches to download, and to score the blind result afterwards. Never passed to the search. | `pipeline/ephem.py`, cached in `.parallax-cache/horizons/` |
| CatWISE2020 (Marocco et al. 2021) at NOIRLab Astro Data Lab, https://datalab.noirlab.edu/ | The same catalogue as IRSA's, used when IRSA's catalogue service is down (it returned HTTP 502 for most of 14 Nov). | `pipeline/distant.py: catwise_field`, `pipeline/hunt.py: external_checks` |
| AllWISE (Cutri et al. 2013) at the ESA Gaia archive | Last fallback if both CatWISE services fail. Each cached catalogue file records which service answered. | `pipeline/distant.py: catwise_field` |
| Gaia DR3, all magnitudes to G = 21.5 | Removing known stars from the per-exposure detections; the expected displacement of Barnard's Star. | `pipeline/measure.py: gaia_field` |

The distant-world fields (16 arcminutes, detectors 1 to 3) are in `.parallax-cache/distant/<body>/`, with a provenance record and SHA-256 beside
every cutout. The 36 exposures of Barnard's Star's third visit, sealed until 14 Nov, are in `.parallax-cache/targets/barnards-star/unsealed-visit-3/`.

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

## Added in the fourth session (cold-world spectra)

| Source | Used for | How it is reached |
|---|---|---|
| **SPHEREx DR1 all-sky data cube** (SPHEREx Science Data Center; IRSA HiPS, order 5, 102 planes, MJy/sr) | A 102-colour spectrum at any position: an 11 × 11 pixel window per object, read with HTTP byte ranges (`pipeline/cubespec.py`). Also the SPHEREx layer of the sky map. | https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube |
| **SIMBAD** (Wenger et al. 2000), TAP service at the CfA mirror | Lists of known M, L, T and Y dwarfs with spectral types (training), and of brown-dwarf candidates and fast red objects with no spectral type; bibliography of flagged objects. | https://simbad.cfa.harvard.edu/simbad/sim-tap |
| **2MASS Point Source Catalog** (Skrutskie et al. 2006; VizieR II/246) and **AllWISE** (Cutri et al. 2013; VizieR II/328), CfA VizieR mirror | Where each object was around 2000 and in 2010.56, hence its motion and where to look in the cube. 2MASS J and K and WISE W1 and W2 also check the SPHEREx colours. Never model inputs. | https://vizier.cfa.harvard.edu |
| **Best et al. 2020**, AJ 159, 257, table 1 (VizieR J/AJ/159/257) | Published spectral types, consulted only after the model's scores were locked, to vet what it flagged. | https://vizier.cfa.harvard.edu |
| **JPL Horizons** (Giorgini et al. 1996) | Today's position of the Sun, Moon, planets, dwarf planets and asteroids for the search box (`pipeline/ephem.py`, `where_now`). | https://ssd.jpl.nasa.gov/api/horizons.api |
| **HiPS previews of AllWISE, 2MASS, DSS2 and IRAS** (made by CDS, served by IRSA) | Thumbnails on the sky map's Layers tile. | https://irsa.ipac.caltech.edu/data/hips/CDS/ |
