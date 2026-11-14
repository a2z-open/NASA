# PARALLAX

**A scientific discovery engine for the infrared universe.**
*Motion tells you something moved. Spectroscopy helps tell you what it is.*

PARALLAX is the team's entry for the NASA Space Apps Challenge 2026, Seattle, in the challenge
[Planet X and SPHEREx](https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/).

You can type any sky coordinates or object name. PARALLAX then:
1. retrieves real NASA SPHEREx observations (DR1 + QR3) from IRSA;
2. plays them back in time order on one aligned sky grid;
3. lets you click a source;
4. measures that source on native pixels: its motion (proper motion and parallax), its brightness at matched
   wavelengths, and a motion-corrected 0.75–5 µm spectrum;
5. weighs seven competing explanations (H0–H6);
6. writes a reproducible evidence dossier that you can export and share.

> Status: built for team review. **Not deployed and not submitted.** The demo URL is TBD and needs team approval. Everything
> below runs locally.

## What PARALLAX found with real SPHEREx data

All of these come from this repository's code and data. See [VALIDATION.md](VALIDATION.md) and [RESULTS_LOG.md](RESULTS_LOG.md).

| Target | Result |
|---|---|
| **Epsilon Indi B** (brown-dwarf binary) | **Held-out prediction passed.** A motion model fitted only to SPHEREx visits 1–3 (337 exposures) was locked (SHA-256 `c902006d…`) and committed *before* the sealed visit 4 was downloaded. Visit 4 (111 usable exposures) landed **0.072″** from the prediction (d² = 4.85 against a pre-registered pass threshold of 11.83). A "stays here" null missed by 1.95″. All four visits give proper motion 4635 ± 16 mas/yr and parallax 298 ± 9 mas (Gaia DR3: 4685 mas/yr total, 270.7 mas; the differences are 2–3σ and plausibly due to the unresolved binary's photocentre). The motion-corrected spectrum fills all 102 SPHEREx bins and best matches a **T3** template (SPIFF library, reduced χ² 1.5), consistent with the unresolved T1 + T6 pair. Measured at one fixed sky position instead, the source keeps only **55 %** of its flux, which shows why following the motion matters. |
| **WISE 0855−0714** (coldest known brown dwarf) | **Invisible at 0.75–3.8 µm, detected at 3.8–5.0 µm.** The source was deblended from an 8″ Gaia neighbour and measured with forced photometry along the Kirkpatrick et al. (2021) track. Results: −10 ± 6 µJy at 0.75–2.4 µm; 298 ± 28 µJy at 3.8–4.4 µm; 460 ± 32 µJy at 4.4–5.0 µm (17.24 AB, S/N 14), consistent with its WISE W2 brightness. The spectrum best matches **Y1**, the coldest template in the library, so read it as "at least as cold as Y1". Twelve high-S/N exposures show motion of 10.1 ± 1.1″/yr, consistent within 2σ with the published 8.15″/yr. |
| **Barnard's Star** | **Inconclusive, saturated.** All 63 cached exposures are flagged OVERFLOW at the core, so PARALLAX refuses to fit it rather than forcing a result. Visit 3 (Aug–Sep 2026) remains sealed and was never downloaded. |
| **RW Aurigae** and **R Draconis** | **Variability not measurable: saturated** (RW Aur in 131 of 142 exposures; R Dra in 103 of 103). An experimental fit to the unsaturated PSF wings was attempted and rejected (median reduced χ² ≈ 400). The naive-versus-wavelength-matched lesson is shown instead on real, unsaturated comparison stars in the same images. Their apparent 9–11× "changes" in a time-ordered light curve shrink to 0.98–1.02 once the comparison is matched in wavelength. |

Validation numbers (negative controls, false positives, synthetic injections) are in [VALIDATION.md](VALIDATION.md).

## What is new, and what is not

Blinking images, mover detection, catalogue overlays, spectra and path-following photometry already exist in tools such as
SPHEREx Blink 3.0, SpectraShift, WiseView, IRSA's SPHEREx tools, Driftnet and SkyShift. PARALLAX does not claim them.
What PARALLAX adds is one accessible workflow that combines:
1. **Wavelength-aware** time exploration. Every frame shows its true per-pixel wavelength, and difference images warn
   when the two frames are not wavelength-matched.
2. **Motion-corrected spectral extraction** with forced ePSF photometry on native pixels.
3. **Evidence-based comparison of competing explanations** (H0–H6), with thresholds you can inspect.
4. **Independent prediction and held-out validation** (Lock → Predict → Reveal).
5. **Reproducible, shareable dossiers** with per-file SHA-256 provenance.

PARALLAX builds on SPIFF (Gagné et al. 2026, arXiv:2604.22012) for template comparison and its 102-bin wavelength table.

## Run it locally

Requirements: Python 3.12+ and Node 20+ (tested with Python 3.13 and Node 22).

```sh
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt pytest
npm --prefix web ci
npm --prefix web run build
.venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. For frontend development, run `npm --prefix web run dev`, open http://127.0.0.1:5173,
and keep the API on port 8000.

The five curated targets work offline from `data/targets/`, which holds real SPHEREx display frames, investigations and
provenance. Any other coordinates query IRSA live. Clicking a source in a curated field re-fetches its native cutouts from
IRSA and checks each one against its recorded SHA-256.

**Docker:** run `docker build -t parallax . && docker run -p 8000:8000 parallax`.

## Reproduce the science

```sh
# 1. Fetch cutouts. The held-out visit is sealed: only its metadata is recorded.
.venv/bin/python -m pipeline.fetch_target epsilon-indi-b --seal-last-visit --workers 6
.venv/bin/python -m pipeline.fetch_target wise-0855 --per-detector-visit 6 --detectors 5,6
.venv/bin/python -m pipeline.fetch_target barnards-star --seal-last-visit --per-detector-visit 6
.venv/bin/python -m pipeline.fetch_target rw-aurigae --per-detector-visit 8
.venv/bin/python -m pipeline.fetch_target r-draconis --per-detector-visit 6
# 2. Lock -> commit -> reveal (a new target needs its own sealed visit)
.venv/bin/python -m validation.experiment lock <slug>  &&  git add validation/experiments/<slug> && git commit -m "lock"
.venv/bin/python -m validation.experiment reveal <slug>
# 3. Build the curated fields and investigations, then validate
.venv/bin/python -m pipeline.build_curated --all
.venv/bin/python -m validation.run
.venv/bin/python -m validation.inject
# Tests
.venv/bin/python -m pytest -q
npm --prefix web test
```

## Architecture

```
web/            Vite + React + TypeScript. Canvas sky viewer (float16 frames, client-side stretch, blink,
                difference, stack, spectral sort) and custom SVG charts.
api/app.py      FastAPI service (docs/API.md). Background jobs for live fields and investigations; static frames.
pipeline/
  spherex.py      IRSA SIA2 (DR1+QR3) discovery, dedupe, visits, checksummed cutouts, FITS loading, flags, spectral WCS
  astrometry.py   coordinate parsing, tangent plane, proper motion, parallax factors (sign checked against astropy)
  measure.py      native-pixel ePSF fits (release EPSF), Gaia DR3 registration, neighbour deblending
  motion.py       weighted tangent-plane fits: stationary / linear / linear + parallax; model comparison
  investigate.py  per-exposure measurement along a track (centroid, follow and fixed forced photometry)
  analysis.py     spectrum (102 bins), SPIFF templates, wavelength-matched variability, H0–H6 evidence, verdicts
  frames.py       display-only reprojection onto a north-up TAN grid
  build_curated.py  curated fields, investigations and provenance
validation/     experiment.py (lock/reveal), run.py (benchmark + negative controls), inject.py (synthetic), results
data/targets/   committed curated products: frames, investigations, provenance, archive manifests, Gaia fields
```

### Scientific method (short version)

- **Time and wavelength.** Time is `MJD-AVG`. Wavelength comes per pixel from the spectral WCS (`key='W'`), so a
  detector name alone is never treated as a wavelength.
- **Registration.** Each exposure is shifted onto Gaia DR3 stars propagated to that epoch with proper motion and parallax.
  Typical registration RMS is about 0.25″. An empirical error floor comes from the scatter of the reference stars.
- **Centroids and fluxes.** The release ePSF is fitted to native pixels. Hard-flagged pixels are masked; saturated cores
  are refused; known Gaia neighbours are fitted at the same time.
- **Motion.** Weighted least squares in the tangent plane. Covariances are scaled by max(1, χ²ᵣ). Models are compared
  with Δχ² and BIC. Parallax is fitted only with three or more visits.
- **Thresholds** (fixed before validation): motion needs ≥ 5σ and |μ|/σ ≥ 5; variability needs ≥ 5σ and ≥ 5 %;
  a template match needs reduced χ² ≤ 3 over ≥ 15 bins.

## Known limitations

- Three of the five NASA targets saturate SPHEREx. PARALLAX reports this rather than forcing a measurement.
- Pixels are 6.15″, so close pairs (Epsilon Indi Ba/Bb, RW Aur A/B) are measured as one blend.
- Display frames are bilinearly reprojected for viewing only; science uses native pixels.
- Fluxes use the median pixel solid angle and the release ePSF. Absolute-calibration systematics of a few percent are not propagated.
- No solar-system ephemeris check yet, so H5 is "not testable" unless the motion is clearly stellar.
- Live queries download at most 48 cutouts (about 4 MB each) to respect IRSA and keep response times reasonable.
- The validation set is small. It does not establish full-sky completeness or false-positive rates.

## Documents

[DATA_SOURCES.md](DATA_SOURCES.md) · [VALIDATION.md](VALIDATION.md) · [RESULTS_LOG.md](RESULTS_LOG.md) ·
[AI_USAGE.md](AI_USAGE.md) · [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) ·
[DEVELOPMENT_HISTORY.md](DEVELOPMENT_HISTORY.md) · [SUBMISSION.md](SUBMISSION.md) (draft) ·
[DEMO_SCRIPT.md](DEMO_SCRIPT.md) · [docs/API.md](docs/API.md)

Data: NASA SPHEREx DR1 Spectral Images (doi:10.26131/IRSA678) and QR3 via NASA/IPAC IRSA; Gaia DR3 (ESA). *This
publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization
and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California Institute of
Technology, and is funded by the National Aeronautics and Space Administration.* PARALLAX is not affiliated with or
endorsed by NASA.
