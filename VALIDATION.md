# Validation report

Every number below comes from real SPHEREx DR1/QR3 data processed by the code in this repository. The one exception is
the synthetic injection section, which is labelled as such. Machine-readable results are in `validation/validation_results.json`
(served at `/api/validation`) and `validation/experiments/`.

## Decision thresholds (fixed before validation)

Defined in `pipeline/analysis.py` and `pipeline/investigate.py`. They were not tuned per target or after seeing results.

| Quantity | Threshold |
|---|---|
| Usable position | ePSF centroid converged, S/N ≥ 5, no OVERFLOW/NONLINEAR within 1.5 px |
| Significant motion | likelihood-ratio equivalent ≥ 5σ **and** total proper motion ≥ 5× its error |
| Minimum data | ≥ 6 usable positions for any motion fit; ≥ 3 visits before parallax is fitted |
| Variability | wavelength-matched visit-to-visit change ≥ 5σ **and** ≥ 5 % in flux |
| Template match | SPIFF capped 10 %-floor reduced χ² ≤ 3 over ≥ 15 bins, with the best type in the ultracool range |
| Saturation-dominated | ≥ 50 % of exposures saturated at the source |
| Wing photometry (experimental) | accepted only if the fit's reduced χ² < 50 |

Uncertainties: fit covariances are multiplied by max(1, χ²ᵣ). Per-exposure position errors combine three terms:
the formal centroid error, the registration error, and an empirical floor taken from the reference-star scatter.

## 1. Held-out prediction experiment (Lock → Predict → Reveal)

**Target:** Epsilon Indi B (Gaia DR3 6412596012146801152).

**Data split.** Visits were grouped by gaps of more than 30 days in IRSA metadata. The rule (written in
`validation/experiment.py` before the lock) holds out the chronologically last visit.

| | Visits | Dates (UTC) | Products |
|---|---|---|---|
| Training | 1–3 (DR1) | 2025-04-24 → 2026-05-04 | 337 downloaded, 324 usable |
| Held-out | 4 (QR3) | 2026-09-22 → 2026-10-02 | 120 listed; only metadata was read before the lock |

**Lock.** The code was committed first (`1039625`). The prediction was then written and committed (`ef75c76`,
2026-11-14 00:37:57 −08:00). Its SHA-256 is `c902006d2cb11e96db29bace24b4a2f8111ae4d0cc84ccd744563203c95798d5`.
`lock` refuses to run if any held-out pixel file exists locally. `reveal` refuses if the hash does not match or the file is not committed.

**Primary model.** SPHEREx-only position, proper motion and parallax, fitted to training data:
μα* = 3927 ± 26, μδ = −2383 ± 26 mas/yr, ϖ = 295 ± 10 mas, χ²ᵣ = 0.95.
Predicted position at the held-out mean epoch: RA 331.098144°, Dec −56.801354°, σ ≈ 0.028″ per axis.

**Pre-registered criterion.** Take the inverse-variance mean residual over the usable held-out exposures. PASS if its
Mahalanobis d² < 11.83 (the 2-dof "3σ" region), using Σ = Σ_prediction + Σ_measurement. INCONCLUSIVE if fewer than 10 usable exposures.

**Reveal** (`51d8ea1`, 00:39:49): 112 of 120 held-out cutouts downloaded (8 failed with IRSA HTTP 503), 111 usable.

| Model | Type | Residual | σ_pred | d² | Verdict |
|---|---|---|---|---|---|
| **Primary: SPHEREx pm + parallax** | independent | **0.072″** | 0.028″ | **4.85** | **PASS** |
| SPHEREx pm + catalogue parallax | catalogue-assisted parallax | 0.084″ | 0.027″ | 6.74 | PASS |
| Gaia DR3 propagation (pm + parallax) | catalogue only | 0.561″ | 0.001″ (formal) | 1067 | FAIL |
| Stationary null ("stays here") | — | 1.954″ | 0.019″ | 5670 | FAIL |

Measurement σ of the held-out mean was 0.017″. The held-out scatter about the prediction had χ²ᵣ = 0.74.

**Interpretation.**
- SPHEREx alone predicted where Epsilon Indi B would be in a visit it had never seen, to 0.07″, about 1/85 of a pixel.
- The Gaia DR3 propagation misses by 0.56″. Epsilon Indi B is an unresolved binary with Gaia RUWE 4.3, so its photocentre
  in Gaia's optical band, and over Gaia's 2014–2017 orbital phase, need not match the near-infrared photocentre in 2025–26.
  That failure is not a SPHEREx error. It is a measured difference that the catalogue's formal errors cannot explain.

**Classification.** Independent held-out recovery. The motion model uses SPHEREx positions only. Gaia was used to identify
the source in training images (the centroid search seed) and to register frames on field stars.

**Disclosures** (verbatim in `prediction.json`):
- The experimenter, an AI coding agent, had seen published Gaia values before the experiment.
- No held-out pixel was viewed before the lock.
- Git timestamps are self-reported. The commits have not been pushed: that waits for team approval.

### 1b. Second held-out experiment: 2MASS J0415−0935 (T8 brown dwarf; not one of the NASA five)

This experiment was added after the first one, using the **identical, unmodified protocol and code**. The catalogue seed
comes from SIMBAD via Sesame: a 2MASS position whose epoch was approximated as J2000.0, proper motion from Faherty et al. 2009,
and parallax from Faherty et al. 2012. The seed was used only to find the source in the images.

| | Visits | Products |
|---|---|---|
| Training | 1–2 (DR1, 2025-08 and 2026-02) | 258 downloaded, 164 usable |
| Held-out | 3 (QR3, 2026-08-12 → 09-20) | 122 listed, 121 downloaded, 74 usable |

The lock is commit `4a5d715` (01:21:13 −08:00), with prediction SHA-256 `c9beae2e2bb8d75321b9d96b1d18ea20831fc0000e121ce6073483acff6b3b8c`.
The reveal is commit `ce84964` (01:29:42).

| Model | Residual | σ_pred | d² | Verdict |
|---|---|---|---|---|
| Primary: SPHEREx pm + parallax | 0.206″ | 0.93″ | 0.48 | PASS (**weak test**, see below) |
| SPHEREx pm + catalogue parallax | **0.130″** | 0.099″ | **1.46** | **PASS** |
| Catalogue propagation | 3.28″ | — | 6386 | FAIL. Not meaningful: the seed's position epoch is approximate (about 1 year × 2.3″/yr). |
| Stationary null | 1.54″ | 0.044″ | 651 | FAIL |

**Honest reading.** The two training visits are about six months apart, so a SPHEREx-only fit cannot separate proper motion
from parallax (ϖ = 153 ± 323 mas in training). The pre-registered primary prediction therefore had a large uncertainty
and passes trivially. We report it as pre-registered rather than swapping the model afterwards. The informative test is
the catalogue-parallax variant (σ_pred 0.10″), which landed 0.13″ from the measured position. With all three visits,
SPHEREx alone gives μα* = 2180 ± 56 and μδ = 512 ± 56 mas/yr, against the literature 2193 and 527 (−0.2σ, −0.3σ), and
ϖ = 195 ± 27 mas against 174 ± 3 (+0.8σ). The motion-corrected spectrum fills 102 of 102 bins. Its best template is
**T8** (χ²ᵣ 1.08; T7 4.95; T9 5.83), which matches the published spectral type, T8.0.

## 2. The five NASA targets

| Target | Archive / cached / usable | Result | Key measurements |
|---|---|---|---|
| **Epsilon Indi B** | 458 / 449 / 434 (4 visits, 2025-04 → 2026-10) | Recovered: motion, parallax and spectral type measured; held-out prediction passed | μ = 4635 ± 16 mas/yr (μα* 3952 ± 17, μδ −2421 ± 16), ϖ = 298 ± 9 mas, χ²ᵣ 0.89. Gaia DR3 differs by −1.8σ, +2.8σ and +2.9σ (binary photocentre; see above). Spectrum: 102/102 bins filled, 99 detected; best template **T3** (χ²ᵣ 1.55; T2 2.64; T4 3.74). Fixed-position extraction recovers 55 % of the flux. No variability: matched ratios 0.971 ± 0.009, 1.012 ± 0.009, 1.008 ± 0.015. |
| **Barnard's Star** | 358 / 63 / 0 (visits 1–2; visit 3 sealed, never downloaded) | **Inconclusive: saturated.** OVERFLOW within 1.5 px of the core in 63 of 63 exposures; BLOOM in 62. | None. PARALLAX refuses to fit saturated cores. |
| **WISE 0855−0714** | 258 / 155 / 12 (3 visits; D5/D6 fully, others subsampled) | **Detected only at 3.8–5.0 µm** (forced ePSF photometry on the Kirkpatrick et al. 2021 track, G = 16.3 neighbour 7–8″ away deblended) | 0.75–2.42 µm: −10 ± 6 µJy (3σ < 9 µJy). 2.42–3.83 µm: 6 ± 8 µJy. 3.83–4.42 µm: 298 ± 28 µJy (S/N 11). 4.42–5.00 µm: **460 ± 32 µJy = 17.24 AB** (S/N 14). Spectrum best fits **Y1**, the coldest template, so "at least as cold as Y1". 12 exposures at S/N ≥ 5: μ = 10.1 ± 1.1″/yr (published 8.15″/yr: −1.8σ in RA, +0.4σ in Dec). Parallax not fitted (only two visits have usable positions). |
| **RW Aurigae** | 335 / 142 / 3 | **Inconclusive: saturated** in 131 of 142 exposures. A/B are 1.4″ apart, always blended. | Wing photometry was attempted on saturated frames: 48 converged with χ²ᵣ 250–770 and all were **rejected**. |
| **R Draconis** | 539 / 104 / 0 | **Inconclusive: saturated** in 103 of 103 measured exposures. | No unflagged pixels inside the ePSF footprint (±3.3 px), so no wing photometry is possible. |

**Naive vs wavelength-matched comparison** (the RW Aur / R Dra lesson, shown on real unsaturated stars in the same images):

| Star | Naive time-ordered max/min | Wavelength-matched visit ratios | Verdict |
|---|---|---|---|
| Gaia DR3 1648326843826192768 (R Dra field, G = 12.5) | 9.1× | 0.984 ± 0.013, 1.017 ± 0.017 | not variable |
| Gaia DR3 156431234433162368 (RW Aur field, G = 12.6) | 10.7× | 0.986 ± 0.007, 1.022 ± 0.012 | not variable |
| Epsilon Indi B (S/N ≥ 10 points) | 83× | 0.971 ± 0.009, 1.012 ± 0.009, 1.008 ± 0.015 | not variable |

A change in brightness between two SPHEREx frames is mostly the source spectrum seen at a different wavelength. Only
a same-wavelength comparison can show real variability.

## 3. Negative controls (stationary stars)

The controls are Gaia DR3 stars with |μ| < 20 mas/yr, G = 11.5–16.5 and RUWE < 1.4, isolated (no comparable neighbour within 20″)
and within 4′ of four field centres. Each control was measured with the production pipeline and thresholds. **Each star was
removed from the registration reference set while it was measured**, so registration cannot absorb its motion.

| Controls | Measured | Insufficient | **False positives** | Highest motion significance | Pull σ (μ_SPHEREx − μ_Gaia)/σ |
|---|---|---|---|---|---|
| 34 | 33 | 1 (3 usable exposures) | **0** | 4.3σ (below 5σ) | **0.93**, mean −0.07, max |pull| 2.5 |

Pulls close to N(0, 1) mean the quoted proper-motion uncertainties are realistic, neither inflated nor optimistic. The
median proper-motion error for these stars is 49 mas/yr, from 50–450 exposures each.

## 4. Synthetic injection–recovery (SYNTHETIC: not real sources)

Point sources were built from each exposure's own release ePSF and added to 150 real cutouts of the Epsilon Indi B field
(every third exposure, 4 visits) at an empty position. They moved at position angle 135°. Each was measured blind from a
stationary seed with production code and thresholds. Source photon noise is not simulated; the real background and read noise are present.

| Injected μ \ flux | 30 µJy | 100 µJy | 300 µJy (S/N ≈ 8) | 1000 µJy (S/N ≈ 22) |
|---|---|---|---|---|
| 0 mas/yr | not detected | stationary ✓ | stationary ✓ (51 ± 118) | stationary ✓ (27 ± 46) |
| 300 mas/yr | not detected | missed | missed (232 ± 115) | **recovered** (270 ± 46) |
| 1000 mas/yr | not detected | missed | **recovered** (978 ± 119) | **recovered** (966 ± 46) |
| 4000 mas/yr | not detected | missed | **recovered** (3972 ± 112) | **recovered** (3956 ± 45) |

There were no false positives. Every recovered motion lies within 1σ of the injected value. Over this 4-visit, 1.4-year
baseline, a source is detected reliably above about 200–300 µJy per exposure (about 17.5 AB). Motions of about ≥ 5× the
achieved error are recovered: about 600 mas/yr at 300 µJy and about 250 mas/yr at 1000 µJy.

## 5. Live arbitrary-coordinate test

Teegarden's Star was resolved by name through Sesame and propagated to 2026.0. IRSA listed 332 products in 3 visits.
24 cutouts were requested and 19 retrieved (5 IRSA 503 failures, reported in the UI). Frames were reprojected with a Gaia
overlay, all in about 80 s. The star itself is saturated in 14 of 19 exposures. PARALLAX reports "saturated" instead of a
motion. A second live query (RA 270.0, Dec −23.5, 3′) rendered 16 frames in the browser test.

## 6. Test suite

- `pytest`: 45 tests, all passing. They cover coordinate parsing and sexagesimal input, RA wrap, tangent-plane round trips
  across RA = 0, the parallax sign against astropy, the cos δ convention, motion fits on synthetic tracks, covariance inflation,
  ePSF centroids and flux, neighbour deblending, saturated-core refusal, flag decoding, release dedupe, visit grouping,
  evidence serialisation (null, not 0, for missing values), API contracts, invalid inputs, held-out isolation, and tamper refusal.
- `npm test`: 12 frontend unit tests, all passing (coordinates, TAN grid orientation, float16 decoding, stretch, propagation,
  wavelength matching, difference and stack).

## Limitations

- The validation set is small: five named targets plus one extra target, two held-out experiments, 33 measured controls and 16 synthetic scenarios.
  It does not establish full-sky completeness or false-positive rates.
- The controls are moderately bright, isolated stars. Crowded fields, nebulosity and faint sources near the detection limit are under-represented.
- Three of the five NASA targets saturate SPHEREx; the release ePSF cannot model their wings.
- The Epsilon Indi B photocentre is a binary blend. Agreement with Gaia at the few-σ level is all that should be expected.
- WISE 0855 photometry is forced on a catalogue track (the source is identified by the catalogue). Its 12-exposure motion
  is seeded by that track, and the track itself was not independently tested with a held-out visit.
- Registration fits a pure shift per exposure; residual distortion goes into an empirical floor.

## Reproduce

```sh
.venv/bin/python -m validation.run          # benchmark + negative controls (~15 min on 8 cores)
.venv/bin/python -m validation.inject       # synthetic injections (~5 min)
.venv/bin/python -m pytest -q && npm --prefix web test
```
