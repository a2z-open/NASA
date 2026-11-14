# Project submission: DRAFT for team review

> **Do not submit until the team has reviewed and approved this draft.** Fill in every item marked TEAM TODO.
> Check the current official Project Submission Guide in the event portal before submitting.

**Project title:** PARALLAX
**Team name:** TEAM TODO. The team may be registered as "Aiges"; confirm the current registered name.
**Challenge:** Planet X and SPHEREx (NASA Space Apps Challenge 2026)
**Local event:** Seattle
**Public demo:** TEAM TODO (deploy only after approval; see "Deployment" in the review checklist)
**Repository:** TEAM TODO. `github.com/a2z-open/NASA` is public; branch `parallax-build` is local only until approved.
**Demo video / slides:** TEAM TODO (≤ 30 s video or ≤ 7 slides; see DEMO_SCRIPT.md)

## Short description (about 50 words)

PARALLAX turns NASA SPHEREx observations into testable evidence. Enter any coordinates and watch real infrared exposures
change over time. Click a source and PARALLAX measures its motion, parallax and a motion-corrected 0.75–5 µm spectrum. It then
weighs competing explanations, so anyone can move from "that dot moved" to "here is why", with reproducible, shareable evidence.

## Problem

SPHEREx images the whole sky in 102 infrared channels at many epochs. Spotting a changing dot is easy; understanding it is
hard. Was it real motion, a variable star, two blended sources or a detector artifact? And if it moved, what is it? SPHEREx
adds a trap of its own. Each exposure sees a different wavelength, so a "brightness change" between two frames is usually the
source's spectrum, not time variability. Today, answering these questions takes several professional tools and expert judgment.

## Solution

One public web workflow: **Explore → Detect → Investigate → Identify → Validate → Share.**
- **Explore:** coordinate or name search, then real DR1 + QR3 cutouts from IRSA on one aligned grid, with true timestamps
  and per-pixel wavelengths. Playback, blink, difference (with a wavelength-match warning), stacking, a spectral sort and a Gaia overlay.
- **Investigate:**
  - native-pixel ePSF astrometry registered to Gaia
  - weighted fits of proper motion and parallax
  - forced photometry along the motion track, giving a motion-corrected spectrum
  - SPIFF template comparison
  - wavelength-matched variability
- **Evidence:** seven competing hypotheses (stationary, moving, variable, blended, artifact, solar-system, insufficient).
  Each is marked supported, disfavoured, possible or not testable, with the measured reason.
- **Validate:** a Lock → Predict → Reveal experiment, negative controls and injection tests.
- **Share:** URL state, plus JSON and CSV dossiers with SHA-256 provenance for every exposure.

## How NASA data is used

PARALLAX runs on **SPHEREx Spectral Images**:
- DR1 (doi:10.26131/IRSA678) and QR3, from NASA/IPAC IRSA through the SIA2 and cutout services
- 913 exposures cached across the five targets
- live queries for any other position

It reads every extension it needs: IMAGE (MJy/sr), VARIANCE, FLAGS (bit names from MSKN cards), the EPSF table (for fitting)
and the WCS-WAVE spectral WCS (per-pixel wavelength). `MJD-AVG` gives each exposure's time. Gaia DR3 provides registration
stars and catalogue context. WISE 0855's astrometry comes from Kirkpatrick et al. (2021). Full citations are in DATA_SOURCES.md.

## Scientific validation (actual results)

1. **Held-out prediction: PASS.**
   - We fitted Epsilon Indi B's motion and parallax using only SPHEREx visits 1–3.
   - We hashed and committed the prediction (SHA-256 `c902006d…`), then downloaded the sealed visit 4.
   - Visit 4 landed **0.072″** from the prediction (d² = 4.85 against a pre-registered 11.83).
   - The "stays here" null failed by 1.95″. Gaia DR3 propagation failed by 0.56″, which we attribute to the binary's photocentre.
2. **Epsilon Indi B:**
   - μ = 4635 ± 16 mas/yr and ϖ = 298 ± 9 mas from SPHEREx alone (434 exposures)
   - a 102-bin motion-corrected spectrum that best matches a T3 template (unresolved T1 + T6)
   - fixed-position photometry would have lost 45 % of the light
3. **WISE 0855:** not detected at 0.75–3.8 µm (3σ < 9 µJy at 0.75–2.4 µm), detected at 4.4–5.0 µm (460 ± 32 µJy, S/N 14),
   with the spectrum at the cold end of the template library (Y1).
4. **Honest failures:** Barnard's Star, RW Aur and R Dra saturate SPHEREx. PARALLAX reports this rather than forcing
   numbers, and shows the naive-versus-wavelength-matched lesson on real comparison stars: an apparent 9–11× change
   becomes 0.98–1.02 at matched wavelengths.
5. **Controls:**
   - 33 stationary stars measured with leave-one-out registration gave **0 false positives**, and the proper-motion pulls have σ = 0.93, so the error bars are honest.
   - 16 synthetic injection scenarios gave 0 false positives, with recovery thresholds mapped.
   - The automated test suite passes: 45 Python tests and 12 web tests.

## Impact

Citizen scientists, students and educators can investigate real NASA data without learning a professional software stack.
They come away with evidence a researcher can check: every number links back to archive files and SHA-256 checksums. The same
engine extends to new SPHEREx releases (collections are configurable) and to targeted searches for cold, fast-moving neighbours of the Sun.

## Innovation

Blinking, mover detection, catalogue overlays, spectra and path-following photometry already exist in other tools. PARALLAX
integrates five things into one public workflow:
1. wavelength-aware time exploration
2. motion-corrected spectra
3. a competing-hypotheses evidence model
4. pre-registered held-out prediction
5. reproducible dossiers

## AI disclosure ("Super Intelligence" section)

AI coding assistants (Claude Code; ChatGPT for planning and research) helped write the code and documents. No AI runs at
runtime: all measurements and verdicts come from deterministic, inspectable code with fixed thresholds. No AI-generated
images or NASA branding are used. See AI_USAGE.md. TEAM TODO: complete it with your own tools and verification.

## Limitations

- 6.15″ pixels blend close pairs.
- Bright stars (K ≲ 8–9) saturate.
- The validation set is small.
- The WISE 0855 detection is forced photometry on a catalogue track.
- There is no solar-system ephemeris check yet.

## Future work

- WISE/NEOWISE epochs for decade baselines.
- Solar-system ephemeris checks (JPL Horizons).
- A pre-registered cold-object candidate search.
- More held-out experiments on other known movers.
- A compact analysis worker for onboard data triage. This is exploratory only; no satellite integration is claimed.

## References

- SPHEREx DR1 Spectral Images, doi:10.26131/IRSA678. QR3 per IRSA guidance.
- Gaia Collaboration 2023, A&A 674, A1.
- Kirkpatrick et al. 2021, ApJS 253, 7.
- Gagné et al. 2026, arXiv:2604.22012 (SPIFF).
- Wenger et al. 2000 (SIMBAD).
- Astropy Collaboration 2022.
- Virtanen et al. 2020 (SciPy).
- Harris et al. 2020 (NumPy).

*This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of
Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California
Institute of Technology, and is funded by the National Aeronautics and Space Administration.* PARALLAX is not affiliated
with or endorsed by NASA.
