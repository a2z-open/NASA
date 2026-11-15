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
| **WISE 0855−0714** | 258 / 155 / 12 (3 visits; D5/D6 fully, others subsampled) | **Detected only at 3.8–5.0 µm** (forced ePSF photometry on the Kirkpatrick et al. 2021 track, G = 16.3 neighbour 7–8″ away deblended) | 0.75–2.42 µm: −10 ± 6 µJy (3σ < 19 µJy; an earlier version said 9, which let a negative mean lower the limit). 2.42–3.83 µm: 6 ± 8 µJy. 3.83–4.42 µm: 298 ± 28 µJy (S/N 11). 4.42–5.00 µm: **460 ± 32 µJy = 17.24 AB** (S/N 14). Spectrum best fits **Y1**, the coldest template, so "at least as cold as Y1". 12 exposures at S/N ≥ 5: μ = 10.1 ± 1.1″/yr. The published motion plus parallax predicts 6.6″/yr between these two visits, so the measurement is about 3σ high (in RA) and unexplained; the positions sit about 1″ off the published track. Parallax not fitted (only two visits have usable positions). |
| **RW Aurigae** | 335 / 142 / 3 | **Inconclusive: saturated** in 131 of 142 exposures. A/B are 1.4″ apart, always blended. | Wing photometry was attempted on saturated frames: 48 converged with χ²ᵣ 250–770. All but 2 were **rejected**, and those 2 are not used for any claim. |
| **R Draconis** | 539 / 104 / 0 | **Inconclusive: saturated** in 103 of 103 measured exposures. | Almost no unflagged pixels inside the ePSF footprint (±3.3 px): 3 of 103 wing fits converged, too few for photometry. |

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

## 6. Blind search: the Planet X hunt

Full tables: [docs/HUNT_REPORT.md](docs/HUNT_REPORT.md), generated from the result files by `validation/hunt_report.py`.

The search (`pipeline/hunt.py`) receives a field and its exposures and nothing else. It stacks each visit in three
bands, detects every source, links detections across visits, measures every linked source in every exposure on native
pixels, and applies the motion rule above (≥ 5σ and |μ|/σ_μ ≥ 5). A mover must then (a) move the same way below and
above 2.42 µm, (b) keep its motion when the positions are refitted with a colour term, (c) survive dropping any one
visit (after removing the fitted parallax), (d) not sit within 4 native pixels of a persistently saturated star, (e) not
need a parallax above 800 mas, and (f) not have a motionless counterpart at its present position in Gaia DR3 (2016.0) or
CatWISE2020 (about 2015). A visit counts for a source only if it was measured in at least 4 exposures. All of these were
fixed in code before the final run; several were added after earlier runs exposed false alarms (RESULTS_LOG.md).

| | |
|---|---|
| Fields | 25 (2.3 square degrees): the 5 NASA target fields and J0415−0935, 15 recovery fields around known cold brown dwarfs, and 4 blank control fields |
| SPHEREx exposures | 2,891 |
| Sources found / motion-tested | 8,718 / 5,195 |
| Known fast movers in the fields | 19 |
| Detected | 17 |
| **Found as movers, blind** | **13** |
| Movers no catalogue explains | **0** |
| False alarms caught by the vetting | 8 |
| Median single-visit 5σ depth at 3.8–5.0 µm | 141 µJy |

For the recovery fields the catalogue position was used only to choose the field (offset by a pseudo-random amount of
up to 4′) and, after the search, to score it.

Three false alarms found during development, all now caught, are recorded in RESULTS_LOG.md: a faint Gaia star at
0.95″/yr, a G = 19.6 star at 1.37″/yr that passed every test until the decade check was added, and two halo artifacts
beside the saturated RW Aurigae.

### 6b. Blind injection test (SYNTHETIC: not real sources)

Sixteen cold point sources (no flux below 3.8 µm) were added to the real exposures of the blank field `control-cosmos`
(69 exposures, 3 visits) from each exposure's own ePSF. The blind search was run without being told where they are.

| Injected speed | 150 µJy | 300 µJy | 600 µJy | 1200 µJy |
|---|---|---|---|---|
| not moving | too faint | still (correct) | still (correct) | still (correct) |
| 1″/yr | too faint | seen, motion not proven | seen, motion not proven | found (1.14″/yr) |
| 3″/yr | too faint | seen, motion not proven | found (2.55″/yr) | found (3.31″/yr) |
| 8″/yr | seen, motion not proven | seen, motion not proven | found (8.46″/yr) | found (8.05″/yr) |

5 of 12 moving injections were found, 0 of 4 stationary injections were called movers, and the search reported no
other mover in that field. This field's first visit has only 5 long-wavelength exposures, so it is a hard case: with
the rule that a visit needs at least 4 positions per source, a 300 µJy source is seen but its motion is not proven.
WISE 0855 (about 350 µJy in this band, 8.15″/yr) was found in its own field, which has 36–44 long-wavelength exposures
in two of its visits. Cold sources fainter than a few hundred µJy are seen but not confirmed as movers.

## 7. The saturated variable stars, from their halo (experimental)

`pipeline/halo.py` measures the median surface brightness in an unsaturated ring around the star in every exposure and
solves ln H = S(wavelength bin) + V(visit). Only wavelength bins observed in at least two visits constrain V. The same
5σ and 5 % rule as section 0 applies.

| Star | Ring (px) | Exposures used | Visit 2 / visit 1 | Visit 3 / visit 1 | Verdict |
|---|---|---|---|---|---|
| R Draconis (Mira variable) | 8–12 | 99 | 0.81 ± 0.04 (3.6σ) | **0.58 ± 0.03 (9.6σ)** | variable |
| RW Aurigae (T Tauri) | 3–5 | 107 | 0.83 ± 0.05 (2.6σ) | **0.64 ± 0.04 (5.3σ)** | variable |
| Barnard's Star (control: saturated, not a large-amplitude variable) | 5–8 | 61 | 1.04 ± 0.03 (0.8σ) | not measured | not variable |

Significances in this table are calibrated. The solver fits one level per wavelength bin and per visit from few points, so its formal errors are too
small: for simulated constant stars with each star's own sampling, the same statistic has a spread of 1.30 (R Draconis), 1.21 (RW Aurigae) and 1.98
(Barnard's Star) instead of 1. Every significance is divided by that factor (`pipeline/halo.py`, `null_scale`). Before calibration they read 12.4σ, 6.4σ
and 1.5σ. RW Aurigae now clears the 5σ rule by a small margin.

Of 6 other bright stars measured the same way (11 visit comparisons), 0 were flagged variable; their median change was 3 % and the largest 8 %.

Caveats: the ring differs between stars; the method assumes the wing profile at a fixed wavelength does not change
between visits; R Draconis's visits each span two to three months, during which a Mira changes, so "visit 1" is an
average. The result is a brightness ratio, not a calibrated flux.

## 8. Known solar-system objects

For each of the five targets, IMCCE SkyBoT was queried at 8 observation times spread over the data (geocentric, 60″
radius). No known asteroid or comet was within 60″ at any of them. Hypothesis H5 is "disfavoured" on that evidence.
Asteroids are not something the hunt can find: they cross a stack in hours and are rejected as outliers by design.

## 9. Forward predictions (open)

`validation/forecast.py` fitted all current data and wrote monthly positions for Dec 2026 to Dec 2027, locked in commit
`bbfd25f` (14 Nov 2026, 04:11:33 PT).

| Target | Positions used | Newest archive exposure at lock | Predicted for 1 Apr 2027 (deg) | 1σ | SHA-256 |
|---|---|---|---|---|---|
| Epsilon Indi B | 434 | 2 Oct 2026 | 331.099349, −56.801591 | 0.02″, 0.03″ | `61320ba9…` |
| 2MASS J0415−0935 | 240 | 20 Sep 2026 | 63.849105, −9.580958 | 0.07″, 0.07″ | `b35e4458…` |

The pass rule is the held-out criterion of section 1. The Epsilon Indi B forecast ignores the binary's orbital motion,
which is its main risk. WISE 0855 was not forecast because its SPHEREx motion is already 2–3σ from the catalogue value.
Git times are self-reported until the commit is pushed.

## 10. Test suite

- `pytest`: 85 tests, all passing (14 added in the third session: orbit fit against an independent calculation, the mirrored-Earth
  test, tracklets, linking, the lock ledger, the Planet Nine arithmetic and linker, the halo centre, the WISE motion rule, the file-route
  containment and request validation). The 45 earlier tests cover coordinates, motion fits, ePSF centroids, deblending,
  saturation refusal, flags, de-duplication, evidence serialisation, the API contract and held-out isolation. The 26 new
  tests cover the matched filter, outlier rejection in stacks, static and fast-mover linking, the colour-term and
  leave-one-visit-out vetting, the Gaia and CatWISE decade checks (HTTP mocked), halo photometry on synthetic series,
  the SkyBoT parser, the hunt API, and the rules for thin visits, parallax, saturated neighbours and stack-only candidates.
- `npm test`: 12 frontend unit tests, all passing.

## Limitations

- The validation set is small: five named targets plus one extra target, two held-out experiments, 33 measured controls, 16 targeted and
  16 blind synthetic scenarios, and 25 hunt fields. It does not establish full-sky completeness or false-positive rates.
- The hunt's recovery fields were chosen because a known mover is there; they measure completeness, not a discovery rate.
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
.venv/bin/python -m validation.hunt_fields run all && .venv/bin/python -m validation.hunt_fields index   # the hunt (~1 h)
.venv/bin/python -m validation.hunt_inject  # blind injections (~3 min)
.venv/bin/python -m validation.halo_controls && .venv/bin/python -m validation.hunt_report
.venv/bin/python -m pytest -q && npm --prefix web test
```

<!-- DISTANT_SECTION:start -->
## 11. Distant worlds, Planet Nine mode and Barnard's Star (third session)

Full tables: [docs/DISTANT_WORLDS.md](docs/DISTANT_WORLDS.md). Protocols: `validation/distant/PROTOCOL.md`, `validation/distant/PROTOCOL_P9.md`, `validation/experiments/barnards-star-halo/protocol.json`. Lock record: `validation/ledger.jsonl` (`python -m validation.ledger verify`).

- **Blind recovery of known distant worlds.** **2 of 4 known distant worlds found blind and placed at the right distance**: Makemake (52.72 ± 0.01 AU; JPL 52.72), Eris (95.53 ± 0.07 AU; JPL 95.52). 0 false objects were linked. Missed: Pluto (only one visit holds enough detections of the body, and the rule needs two); Haumea (only one visit holds enough detections of the body, and the rule needs two). The largest distance error among those found is under 0.1 %. The pass rule (within 12″ of JPL's track, distance within 5 %, no second object) was written first. These fields were never used to tune the search, so unlike the hunt in section 6 this score is out of sample.
- **Planet Nine mode.** The same search for a body at 200 to 20,000 AU in the 23 fields with three or more visits (2.1 square degrees): **no detection**. 2 geometric candidates were raised and both were rejected as thousands of times too bright to be planets; one is a reflection of a saturated star that imitates parallax. Synthetic planets are recovered down to 300 µJy (10 of 16); the predicted Planet Nine is about 7 µJy, so these images could not have found it. The thresholds went through four locked versions in one day; versions 2 and 3 were driven by synthetic planets, and version 4 added a brightness rule after the two real candidates had been seen. That last rule is therefore not blind.
- **Barnard's Star.** Its core is saturated, so we tracked the centre of its halo. In a visit that had been sealed, the halo had moved **10.56″ in 0.98 years; Gaia says 10.23″** (they differ by 0.37″; limit set in advance 1.5″). PASS. Gaia supplies the expected motion, so this tests the halo method. A visit in the opposite season is 1.7″ off in RA and was left out.
- **Shift-and-stack.** Eris was found only by adding exposures along trial paths. The way visits are joined went through three locked versions before it worked (`validation/distant/PROTOCOL_SHIFTSTACK.md`); none used JPL's positions, but the last was written after seeing which candidates fit.
- **What disappeared since WISE.** Of 945 bright sources WISE saw around 2015 in our fields, the ones SPHEREx no longer sees at those spots are 4 known brown dwarfs (2MASS J0415-0935, Epsilon Indi B, SIMP J013656.5+093347.3, WISEP J150649.97+702736.0): each one's SPHEREx motion, run back to the WISE years, passes through the empty spot. 0 faded or vanished without an explanation. The rules that skip WISE artefacts and the glare of saturated stars were added after the first run (`validation/vanished.py`).
- **Live forecasts.** A watcher checks NASA's archive for new SPHEREx images of every locked prediction (python -m pipeline.watch). Makemake's next position is locked from the blind orbit alone; SPHEREx should next see it between 2026-12-22 and 2027-01-17, and JPL's ephemeris, checked after locking, agrees to 3″.
- **Machine learning.** A machine-learning real/artefact model, trained on synthetic stars in real SPHEREx images and tested on the real detections of four dwarf planets it never saw, ranks them with AUC 0.87; signal-to-noise alone gives 0.88. It does not beat the simple rule yet, so it is not used in any result. Results in `validation/ml_realbogus.json`.
- **What this does not show.** It does not show that SPHEREx can find Planet Nine: the predicted planet is about 40 times fainter than the faintest synthetic planet recovered. It does not show discovery power for unknown worlds either: every field was chosen because a known body is in it.
<!-- DISTANT_SECTION:end -->

<!-- COLDSPEC -->
## 12. Cold-world spectra: reading spectral types from 102 colours (fourth session)

**Question.** SPHEREx measures every source in 102 infrared colours. Can a model read a spectral type from that alone, and does it flag anything among objects that have no spectral type?

**Data.** Spectra come from the SPHEREx DR1 all-sky data cube at IRSA (HEALPix tiles, 12.9″ pixels, 102 planes), read with HTTP byte ranges so that only an 11 × 11 pixel window per object is downloaded (`pipeline/cubespec.py`). Object lists and spectral types come from SIMBAD (2026-11-14). Positions in 2MASS and AllWISE (VizieR, CfA mirror) say where to look.

| Set | From SIMBAD | Kept |
|---|---:|---:|
| Known T and Y dwarfs, J < 17.2 | 298 | 254 |
| Known L dwarfs, J < 16.5 (36 per subtype) | 1,234 | 320 |
| Known M6 to M9 dwarfs, moving over 0.1″/yr (60 per subtype) | 2,295 | 240 |
| Known M3 to M5 dwarfs, moving over 0.2″/yr (30 per subtype) | 539 | 90 |
| Brown-dwarf candidates with no spectral type | 751 | 720 |
| Fast-moving red objects with no spectral type (over 0.2″/yr, J − K > 1) | 624 | 534 |

Kept means: brighter limit J > 11 (SPHEREx saturates), more than 10° from the Galactic plane, and a usable spectral type for the known sets. 904 known objects, 1,254 unclassified. A spectrum was extracted for 2,056 of 2,158.

**Is the photometry right?** Checked on known objects only, against catalogues the model never sees. SPHEREx's K/J flux ratio agrees with 2MASS's to 0.049 dex (about 12 %) for the 468 objects that pass the quality cuts, and 0.067 dex before the cuts. Its 4.6/3.4 µm ratio agrees with AllWISE's W2/W1 to 0.046 dex (median offset -0.049 dex, 466 objects). The cuts were placed where that agreement breaks down: source found within 0.5 pixel of where it was expected, no pixel brighter than 2 × the source within 3.2 pixels, profile misfit under 0.12, J-band signal-to-noise of at least 5. The absolute flux scale is not calibrated (at 1.28 µm it reads about 1.4 times the 2MASS J flux for M dwarfs); only the shape of each spectrum is used.

**Model.** Gradient-boosted trees on 30 features that describe the shape of the spectrum only (22 normalised bands and 8 band differences); brightness is left out, and every training spectrum is also degraded to fainter levels, so that "faint" cannot stand in for "cold". Five-fold cross-validation, split by object, on 480 known dwarfs (257 M, 157 L, 66 T).

| Held-out test | Type error (RMS, subtypes) | M | L | T | T dwarfs recognised | Warmer dwarfs called T |
|---|---:|---:|---:|---:|---:|---:|
| As observed | 1.49 | 0.84 | 1.84 | 2.33 | 59 of 66 | 0 of 414 |
| Degraded to S/N 6 to 10 | 1.83 | 1.29 | 2.02 | 2.88 | 58 of 66 | 0 of 414 |

A plain rule that uses only the depth of the 1.7 µm methane band separates T dwarfs with an AUC of 0.978; the model reaches 0.999. So most of the signal is the methane band itself; the model adds a little and gives a type.

**Lock.** Model, cuts, feature list and decision rule were written to `validation/coldspec/protocol.json` and hashed into the ledger on 2026-11-14T23:00:14Z, before any unclassified object was scored. Rule: An unclassified object is a T-dwarf candidate if its SPHEREx spectrum passes the quality cuts, the classifier gives P(T/Y) >= 0.9, the regressor gives a type of T0 or later, and its features are not outliers (nearest known object closer than the 99th percentile of that distance among known objects).

**Result.** Of 1,202 unclassified objects with a spectrum, 448 pass the quality cuts. 4 look unlike anything in the training set and get no answer. The model reads 314 as M, 125 as L and 5 as T. **5 meet the locked rule for a T-dwarf candidate.** The scores were hashed into the ledger before any vetting.

| Object (SIMBAD name) | Model type | P(T) | J-band S/N | W1 − W2 | Published type | Verdict |
|---|---|---:|---:|---:|---|---|
| 2MASS J05541699-0008334 | T4.3 | 1.00 | 20 | 1.31 | T4.5 (PSO J088.5709-00.1430) | already typed in the literature |
| 2MASS J08301554-1111101 | T2.8 | 1.00 | 18 | 1.2 | T3 (PSO J127.5648-11.1861) | already typed in the literature |
| 2MASS J01374485+0908117 | T2.6 | 1.00 | 20 | 1.11 | T3.5 (PSO J024.4369+09.1360) | already typed in the literature |
| PSO J005.6302-06.8669 | T0.6 | 1.00 | 26 | 0.78 | T3 (PSO J005.6302-06.8669) | already typed in the literature |
| PSO J011.1793-03.7847 | T2.7 | 1.00 | 38 | 1.02 | T2 (PSO J011.1793-03.7847) | already typed in the literature |

**Vetting against the literature (after the lock).** "No spectral type in SIMBAD" does not mean nobody has typed an object. Best et al. 2020, AJ 159, 257, table 1 (VizieR J/AJ/159/257), consulted after the scores were locked. 7 of the scored unclassified objects have a published type there. Of the 6 published T dwarfs among them, the model flagged 5; of the 1 published warmer dwarf(s), it flagged 0. Model type against published type: median error 0.72 subtypes, RMS 4.47 (the RMS is dominated by the one miss).

| Object | Published | Model | Flagged |
|---|---|---|---|
| 2MASS J05541699-0008334 | T4.5 | T4.3 | yes |
| 2MASS J01374485+0908117 | T3.5 | T2.6 | yes |
| 2MASS J08301554-1111101 | T3 | T2.8 | yes |
| PSO J005.6302-06.8669 | T3 | T0.6 | yes |
| PSO J011.1793-03.7847 | T2 | T2.7 | yes |
| 2MASS J04385515+0423001 | T2 | L0.5 | no |
| ULAS J120357.45+001547.7 | L5.0 | L4.8 | no |

The miss, 2MASS J04385515+0423001, was read as L0.5. Its SPHEREx signal is far stronger than its catalogue J magnitude allows, so the light is probably blended with a neighbour at 12.9″ per pixel. We count it as a miss.

**Conclusion: 0 new candidates.** Every object the model flagged is a T dwarf that astronomers had already typed; SIMBAD simply does not carry the type. So this search found no new cold world. What it gives instead is a blind test: the model had never been told what these objects are, and the truth was looked up only after its answers were locked. No claim of discovery is made, and nothing has been sent to anyone.

### 12b. The wider search

The first search only covered objects that SIMBAD lists. The wider search takes objects that other surveys picked out from their colours alone (photometric candidates, most never observed with a spectrograph) and fainter SIMBAD candidates. **The model, the cuts and the decision rule are the locked ones**: `wide_apply` refuses to run unless `protocol.json` and `model.joblib` still match ledger entry `coldspec:protocol`. Nothing was refitted or retuned.

| Pool | Objects kept |
|---|---:|
| DES Y6 ultracool candidates (Dal Ponte et al. 2023), photometric type L6 or later | 256 |
| DES Y3 L and T candidates (Carnero Rosell et al. 2019), L6 or later, not already above | 74 |
| UKIDSS photometric T dwarfs (Skrzypek et al. 2016) | 43 |
| UKIDSS photometric L dwarfs, L6 or later (Skrzypek et al. 2016) | 32 |
| SIMBAD brown-dwarf candidates with no spectral type, J 17.2 to 18.3 | 440 |

Kept means: J between 11 and 18.3, more than 10° from the Galactic plane, and not already scored in the first search. 845 objects; a spectrum was extracted for 809; 158 pass the quality cuts; 10 are outliers and get no answer. **The model flagged 20.** The scores were hashed into the ledger (`coldspec:wide-results`) before vetting.

**Vetting.** Each scored object was compared with published spectral types: Best et al. 2018, ApJS 234, 1; Best et al. 2020, AJ 159, 257; Best et al. 2021, AJ 161, 42; Kirkpatrick et al. 2021, ApJS 253, 7; spectroscopic types quoted in the candidate tables; SIMBAD main and measurement tables within 12 arcsec (flagged objects). 29 scored objects have a published type. Blind test on those: the model flagged 7 of 9 published T dwarfs and 0 of 20 published warmer dwarfs; median type error 0.77 subtypes.

Of the 20 flagged: **7 already have a published type, 1 are doubtful (WISE colour), and 12 have no published spectrum that we could find.**

| Object | Pool | J | Survey's photometric type | Model type | P(T) | J-band S/N | W1 − W2 | Published type | Verdict |
|---|---|---:|---|---|---:|---:|---:|---|---|
| DES 1055175672 | des_y6 | 16.71 | T5.0 | T4.8 | 1.00 | 14 | 1.39 | none found | no published spectrum found; WISE colour agrees |
| DES 1075884089 | des_y6 | 17.40 | T5.0 | T5.6 | 1.00 | 16 | 1.68 | none found | no published spectrum found; WISE colour agrees |
| DES 1082529367 | des_y6 | 17.34 | T3.0 | T2.8 | 1.00 | 13 | 1.08 | none found | no published spectrum found; WISE colour agrees |
| DES 1316158591 | des_y6 | 17.98 | T3.0 | T4.7 | 1.00 | 9 | 1.31 | none found | no published spectrum found; WISE colour agrees |
| DES 1409842617 | des_y6 | 16.61 | T6.0 | T5.2 | 1.00 | 22 | 1.84 | none found | no published spectrum found; WISE colour agrees |
| DES 1418166094 | des_y6 | 17.11 | T3.0 | T4.0 | 1.00 | 10 | 1.12 | none found | no published spectrum found; WISE colour agrees |
| DES 1441279267 | des_y6 | 17.20 | T5.0 | T4.8 | 1.00 | 11 | 1.49 | none found | no published spectrum found; WISE colour agrees |
| DES 1498379950 | des_y6 | 17.47 | T6.0 | T6.7 | 1.00 | 13 | 2.7 | none found | no published spectrum found; WISE colour agrees |
| DES 1034152240 | des_y6 | 17.30 | T2.0 | T2.3 | 1.00 | 8 | 0.95 | none found | no published spectrum found; WISE colour agrees |
| DES 261972837 | des_y3 | 17.18 | T3.0 | T3.0 | 1.00 | 8 | 1.05 | none found | no published spectrum found; WISE colour agrees |
| DES 1511657102 | des_y6 | 17.60 | T3.0 | T1.1 | 1.00 | 8 | 0.95 | none found | no published spectrum found; WISE colour agrees |
| DES 1462875234 | des_y6 | 17.29 | T2.0 | T1.5 | 1.00 | 11 | 0.78 | none found | no published spectrum found; WISE colour agrees |
| DES 1159918707 | des_y6 | 17.12 | T7.0 | T6.3 | 1.00 | 18 | 2.3 | T8 (Kirkpatrick et al. 2021, ApJS 253, 7) | already typed in the literature |
| DES 1358847797 | des_y6 | 17.38 | T6.0 | T6.0 | 1.00 | 8 | 1.57 | T6 (Best et al. 2018, ApJS 234, 1) | already typed in the literature |
| DES 920214585 | des_y6 | 15.86 | T5.0 | T5.7 | 1.00 | 33 | 1.51 | T5 (Best et al. 2020, AJ 159, 257) | already typed in the literature |
| DES 101455938 | des_y3 | 17.65 | T4.0 | T5.4 | 1.00 | 12 | 0.39 | none found | doubtful: WISE colour is not that of a T dwarf |
| ULAS J131307.47+123540.7 | ukidss_T | 17.43 | T2.0 | T2.3 | 1.00 | 6 | 0.78 | T2.5 (Best et al. 2018, ApJS 234, 1) | already typed in the literature |
| ULAS J152103.14+013143.2 | ukidss_T | 16.10 | T2.5 | T2.6 | 1.00 | 23 | 0.97 | T2 (spectroscopic type quoted in its source table) | already typed in the literature |
| DES 1355223843 | des_y6 | 17.66 | T2.0 | T2.1 | 1.00 | 6 | 1.03 | T2.5 (Best et al. 2018, ApJS 234, 1) | already typed in the literature |
| DES 1359412367 | des_y6 | 16.59 | T1.0 | T1.1 | 1.00 | 25 | 0.79 | T1 (Best et al. 2020, AJ 159, 257) | already typed in the literature |

**Grading by methane depth (after vetting).** strong: both methane indices deeper than 99 % of known M and L dwarfs; likely: flagged by the locked model but not past both limits. Indices are band differences of the normalised spectrum (pipeline: validation.coldspec.features). Limits from known dwarfs: 1.7 µm index below -0.31, 3.3/4.5 µm index below 0.01. **10 of 12 are strong.** None of the 12 has any entry in SIMBAD within 15″.

| Object | Grade | Model type | 1.7 µm index | 3.3/4.5 µm index | J-band S/N | W1 − W2 |
|---|---|---|---:|---:|---:|---:|
| DES 1055175672 (RA 4.55380, Dec -47.50327) | strong | T4.8 | -2.82 | -1.02 | 14 | 1.39 |
| DES 1441279267 (RA 61.24970, Dec -64.54753) | strong | T4.8 | -1.81 | -1.49 | 11 | 1.49 |
| DES 1498379950 (RA 69.89003, Dec -45.80226) | strong | T6.7 | -1.8 | -1.95 | 13 | 2.7 |
| DES 1409842617 (RA 55.38634, Dec -19.42995) | strong | T5.2 | -1.78 | -0.6 | 22 | 1.84 |
| DES 1075884089 (RA 8.40716, Dec -22.33739) | strong | T5.6 | -1.3 | -1.03 | 16 | 1.68 |
| DES 1418166094 (RA 56.97830, Dec -19.50366) | strong | T4.0 | -1.24 | -0.46 | 10 | 1.12 |
| DES 1316158591 (RA 39.68498, Dec -19.11612) | strong | T4.7 | -1.1 | -0.81 | 9 | 1.31 |
| DES 1082529367 (RA 8.78375, Dec -45.42984) | strong | T2.8 | -1.02 | -0.31 | 13 | 1.08 |
| DES 1511657102 (RA 72.93045, Dec -31.39194) | strong | T1.1 | -0.55 | -0.07 | 8 | 0.95 |
| DES 261972837 (RA 29.37018, Dec -2.85308) | strong | T3.0 | -0.52 | -0.2 | 8 | 1.05 |
| DES 1462875234 (RA 63.13043, Dec -58.53592) | likely | T1.5 | -0.54 | 0.15 | 11 | 0.78 |
| DES 1034152240 (RA 359.50761, Dec -51.71081) | likely | T2.3 | -0.25 | -0.35 | 8 | 0.95 |

**What this is.** Objects that the Dark Energy Survey listed as T-dwarf candidates from colours alone (Dal Ponte et al. 2023; Carnero Rosell et al. 2019). We found no published spectrum of them in four compilations, in their source tables or in SIMBAD (where they have no entry at all). Their SPHEREx spectra show methane absorption. This is a first spectroscopic confirmation of their nature at SPHEREx resolution, not the discovery of new objects, and it should be checked with a proper spectrum before it is published.

**What the wider search does and does not show.** "No published spectrum found" means: none in the four compilations listed, none quoted by the candidate's own source table, and none in SIMBAD within 12 arcsec. It does not prove that no spectrum exists. These objects were already picked out by other surveys from their colours; what SPHEREx adds is a spectrum that shows methane. They are candidates for a first spectroscopic type, not new discoveries of objects. No claim has been sent to anyone.

**Reproduce.** `python -m validation.coldspec lists | positions | extract | quality | train | lock | apply`, then `python -m validation.coldspec_after vet | wide_lists | wide_positions | wide_extract | wide_apply | wide_vet | wide_grade | check`, then `python -m validation.coldspec_md`. Files: `validation/coldspec/` (`objects.json`, `positions.json`, `spectra.npz`, `quality.json`, `cv.json`, `protocol.json`, `model.joblib`, `results.json`, `vetting.json`, `check_queue.json`).
<!-- /COLDSPEC -->

<!-- ASTEROIDS -->
## 13. Asteroid hunt: things that move from night to night (fourth session)

**Method.** Patches of sky near the ecliptic (the path of the planets), away from the Milky Way, that SPHEREx imaged on several epochs within one week. In each epoch SPHEREx takes two images about 2 minutes apart. A dot counts only if it is in both images of an epoch (within 4.0″), which removes cosmic rays and noise. A dot that is also present at the same place on two or more other epochs is a fixed star or galaxy and is removed, so no catalogue is used to remove anything. What is left is joined into straight lines over 4 or more epochs (speed 1 to 90″ per hour, within 4.0″, fit scatter under 2.0″, brightness steady within a factor 3).

**Blind, then checked.** The tracks were written to `validation/asteroids/tracks.json` and hashed into the ledger before any asteroid catalogue was consulted. Only then was IMCCE SkyBoT (Berthier et al. 2006) asked which known asteroids were in each patch at each epoch.

**Chance control.** Each patch was also linked 8 times after rotating each epoch's dots by a random angle about the patch centre. Real movers no longer line up; the density of dots stays the same.

| Patch | Ecliptic longitude | Epochs | Dots in both images | Fixed, removed | Left | Tracks | Chance tracks per run |
|---|---:|---:|---:|---:|---:|---:|---:|
| ast00 | 355° | 11 | 8262 | 8148 | 114 | 0 | 0.0 |
| ast01 | 145° | 9 | 7075 | 6908 | 167 | 0 | 0.0 |
| ast02 | 15° | 8 | 6546 | 6406 | 140 | 0 | 0.0 |
| ast03 | 55° | 8 | 9343 | 9126 | 217 | 0 | 0.0 |
| ast04 | 215° | 9 | 7613 | 7410 | 203 | 0 | 0.0 |
| ast05 | 335° | 9 | 7239 | 7115 | 124 | 0 | 0.0 |

**Result.** 0 tracks. **0 are known asteroids**, recovered blind. 0 match no known asteroid (0 on 4+ epochs); chance alone is expected to give 0.0 tracks in total.

| Known asteroids in view on 4+ epochs, by V | In view | Found blind |
|---|---:|---:|
| V 0-17 | 3 | 0 |
| V 18-19 | 7 | 0 |
| V 19-20 | 32 | 0 |
| V 20+ | 1178 | 0 |

**What this is and is not.** A track that matches no known asteroid is a candidate, not a discovery. It needs follow-up images and a report to the Minor Planet Center, which this project has not made. Nothing has been sent to the Minor Planet Center or anyone else.

**Calibration patches (version 2, not counted above).** 1 track(s), all known asteroids: Mertona (V 16.9). Recovery by V: V 0-17: 1/3, V 17-18: 0/3, V 18-19: 0/10, V 19-20: 0/42, V 20+: 0/1409. The linker was then tuned on these patches (version 3) and, on them, recovered 2 of the 3 known asteroids brighter than V 17.

**Conclusion.** Single SPHEREx images, linked this way, catch only asteroids brighter than about magnitude 17, and only some of those. Every asteroid that bright was catalogued long ago, so this channel cannot find a new asteroid. It is reported as a measured limit, not a discovery.

**Adding photos along known paths (fifth session).** 715 known asteroids (V up to 21.5) were measured at their exact predicted positions in every photo, with no search, after subtracting the same sky spot in photos taken more than 6 hours away. Adding the photos along each path was compared with the single-photo search of section 13, and with 4 control paths per asteroid 60″ away (2792 in all). Threshold: the stacked S/N that 1% of control paths reach (2.47).

| V | Known asteroids | Seen in single photos (S/N 5 in two photos) | Added up, S/N 5 | Added up, 1% false-alarm threshold |
|---|---:|---:|---:|---:|
| 0-17 | 7 | 5 | 6 | 6 |
| 17-18 | 9 | 9 | 9 | 9 |
| 18-19 | 25 | 12 | 23 | 25 |
| 19-20 | 115 | 1 | 12 | 73 |
| 20-21.5 | 559 | 0 | 3 | 37 |

At S/N 5, where only 5 of 2792 control paths land (about 1.3 false ones expected), 53 are seen when photos are added, against 27 in single photos. At the 1% threshold, 150, of which about 7 would be expected by chance. The faintest gains are at V 19-20. The pictures on the /how page are of asteroids that never pass S/N 4 in any single photo (re-picked after the lock: the first pick showed one-photo artefacts).

In total 27 were seen in single photos and 150 when the photos were added. This measures what stacking adds for objects whose path is known; it discovers nothing. `python -m validation.asteroids_stack` (ledger label asteroids:stack).

**History.** Version 1 (24-arcminute patches) removed every dot near a Gaia or WISE star. In these fields the ~10,000 catalogue stars per patch covered almost the whole image, so nothing was left (validation/asteroids/v1/, ledger entry 24). Version 2 removes fixed sources by comparing epochs with each other, as moving-object surveys do, and uses 60-arcminute patches; on six patches it recovered 1 of 3 known asteroids brighter than V 17 and none fainter (validation/asteroids/v2_calibration/, ledger entry 25). Those six patches were then used to tune the linker on known asteroids (version 3: tracks grow step by step and may curve). Version 3 is run blind on six different patches; the tuning patches are not counted in its result. A one-line fix to the report step (brightness values given as text) is recorded as its own ledger entry.

**Reproduce.** `python -m validation.asteroids plan | fetch | detect | link | known | report`, then `python -m validation.asteroids_md`.
<!-- /ASTEROIDS -->

<!-- P9DEEP -->
## 14. Planet Nine: adding up one visit along its parallax (fifth session)

**Why.** One SPHEREx photo reaches about 179 µJy (5 sigma, 0.75–1.6 µm, in these patches). Planet Nine is predicted at 7.2 µJy (V 22.0 at 550 AU; Brown, Holman & Batygin 2024), and at most 26 µJy. Adding N photos lowers the noise by the square root of N, but only if each photo is shifted so that the planet lands on the same spot. Over one SPHEREx visit (one to four weeks) a body 150–1500 AU away moves almost only because the Earth moves, so its path is set by its distance; its own orbital motion is allowed for along the predicted track.

| Patch | RA, Dec | Galactic latitude | Photos (0.75–1.6 µm) | Visits |
|---|---|---:|---:|---:|
| p9-033-02 | 33.0°, -2.0° | -58° | 114 | 4 |
| p9-074+16 | 74.0°, 16.0° | -17° | 134 | 3 |

Both patches sit on the predicted Planet Nine track. p9-074+16 had the most photos in one visit of the track points checked, but lies near the Milky Way, where stars are crowded; p9-033-02 is far from it.

**Method.** (1) Each photo is registered to Gaia and filtered with its own point-spread function at 3 × 3 sub-pixel offsets (the SPHEREx PSF is sharp and undersampled), then resampled to a common 4″ sky grid. (2) The fixed sky (stars, galaxies) is fitted at every grid pixel as a quadratic in wavelength from the OTHER visits only, months away, when a distant planet is somewhere else, so it cannot subtract itself. Each photo's flux scale and noise are measured against that template. (3) Masked: SPHEREx's own artifact flags (CROSSTALK and GHOST widened by one pixel), sky brighter than 400 µJy (with a 12″ border), dark holes in the template (3 sigma below the ring around them and 15 µJy below the field), and a disc around every 4-sigma outlier in each photo. (4) The photos are added along the path of every trial distance from 150 to 1500 AU, spaced so that no photo's predicted position moves by more than half a pixel between trials. (5) The same is done twice more with motions no distant body can have: the parallax reversed, and the parallax turned by 90°. A peak is planet-like only if it beats both at the same spot by 1.5 in S/N; a still source scores the same in all three. The threshold is the highest planet-like peak of the two controls.

**How the method was set (before the locked runs).** It was developed on patch p9-074+16 looking only at the controls and at synthetic planets, never at the real search map. A Gaussian filter recovered about half the flux of synthetic planets; the sub-pixel PSF filter about 70%. Most false control peaks were dark crosstalk echoes in the August visits (flagged by SPHEREx as CROSSTALK): subtracting a dark spot leaves a bright one. Masking the flags, the dark holes and the outlier discs brought the control peaks above S/N 5 from 33 to a few. Patch p9-033-02 was then run with the method frozen.

| Patch | Visit | Photos searched | Area (deg²) | One photo, 5σ (µJy) | Threshold S/N | Planet-like candidates | Still changes |
|---|---:|---:|---:|---:|---:|---:|---:|
| p9-033-02 | 1 | 36 | 0.158 | 186 | 5.1 | 0 | 0 |
| p9-033-02 | 3 | 36 | 0.165 | 179 | 5.8 | 1 | 0 |
| p9-033-02 | 4 | 40 | 0.160 | 186 | 5.1 | 1 | 0 |
| p9-074+16 | 1 | 38 | 0.100 | 220 | 5.0 | 0 | 1 |
| p9-074+16 | 2 | 57 | 0.075 | 203 | 5.0 | 0 | 1 |
| p9-074+16 | 3 | 39 | 0.109 | 217 | 6.3 | 0 | 2 |

Every candidate list was written and hashed into the ledger before any check (p9-033-02: entry 34, p9-074+16: entry 32).

**Depth: synthetic planets (SYNTHETIC, never real).** Planets built from each photo's own PSF were added to every real photo, at the place their distance puts them, and the largest visit of each patch was searched again with exactly the same steps.

| Patch | Distance (AU) | Brightness (µJy) | Found / tried |
|---|---:|---:|---:|
| p9-033-02 | 550 | 80 | 10 / 20 |
| p9-033-02 | 550 | 60 | 4 / 20 |
| p9-033-02 | 550 | 40 | 0 / 20 |
| p9-033-02 | 550 | 26 | 0 / 20 |
| p9-033-02 | 550 | 15 | 0 / 20 |
| p9-033-02 | 300 | 40 | 2 / 20 |
| p9-033-02 | 1000 | 40 | 0 / 20 |
| p9-074+16 | 550 | 80 | 16 / 16 |
| p9-074+16 | 550 | 60 | 13 / 16 |
| p9-074+16 | 550 | 40 | 7 / 17 |
| p9-074+16 | 550 | 26 | 3 / 17 |
| p9-074+16 | 550 | 15 | 0 / 16 |
| p9-074+16 | 300 | 40 | 13 / 15 |
| p9-074+16 | 1000 | 40 | 2 / 17 |

Half of the synthetic planets at 550 AU are found down to 60 µJy in the better patch: about 3.4 times fainter than one photo reaches, and 8 times brighter than the predicted Planet Nine.

**The candidates.** 2 planet-like peak(s) passed the locked rule. With no planet at all, the real search and its two controls are alike, so the real map's top peak beats both controls' top peaks one time in three: the rule expects about 2.0 chance candidates in these 6 visits. After the lock, each candidate was checked: a real source shows in both halves of its visit and in both detectors, and does not rest on one photo.

| Patch | Visit | S/N | Margin | Best distance (AU) | First / second half | Detector 1 / 2 | Largest one-photo drop | Passes |
|---|---:|---:|---:|---:|---|---|---:|---|
| p9-033-02 | 3 | 5.9 | 2.21 | 151 | 6.31 / 2.3 | 2.89 / 6.36 | 0.41 | no |
| p9-033-02 | 4 | 6.11 | 1.84 | 150 | 5.53 / 4.6 | 4.98 / 5.36 | 0.46 | yes |

The p9-033-02 visit-4 candidate, looked for in visit 1 where its distance and speed put it: highest S/N there 3.13 (87% of those places searchable); the same shape at 125 random places gives as much 44% of the time. Verdict: not seen where it must be: not a planet.

Visit 1 and visit 4 of p9-033-02 are one year apart, so the Earth was in nearly the same place and parallax cancels; only the body's own motion along its orbit moves it, which keeps it inside the patch. The other visits put a body this close tens of arcminutes away, outside these patches.

**Disclosed approximation.** The direction of a body's own orbital motion was taken from the predicted track between RA 60° and 90° in both patches. Projected onto p9-033-02 (RA 33°), it differs from the local track direction by 0.5°, which changes nothing measurable; it was noticed after the lock and is left as it was.

**Still changes.** 4 still sources were brighter in one visit than in the others (S/N 7 or more). They are not planet candidates: a still source scores the same in all three searches. All of them sit next to masked bright stars.

**What this is and is not.** A method that reaches several times deeper than one photo, with its depth measured, its false alarms counted by controls, and its candidates locked before checking. It covered about 0.13 deg² per visit in 2 patches, a tiny part of the region where Planet Nine is predicted, and its depth is still above the predicted brightness. It is not a search that could have found the predicted Planet Nine, and nothing found here is reported as a planet. Nothing has been sent to anyone.

**Reproduce.** `python -m validation.p9_deepstack fetch|stack|inject|vet|cross <patch>`, then `python -m validation.p9_deepstack_md`.
<!-- /P9DEEP -->
