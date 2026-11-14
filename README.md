# PARALLAX

**Find what moves in the infrared sky. Then prove it.**

PARALLAX is the team's entry for the NASA Space Apps Challenge 2026, Seattle, in the challenge
[Planet X and SPHEREx](https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/).

Type any sky coordinates or object name. PARALLAX fetches real NASA SPHEREx images of that patch, lines them up and
plays them like a short video, so anything that moves stands out. Click a source and it measures the motion, the
distance and the spectrum. A blind search does the same for every source in a field at once.

> Status: built for team review. **Not deployed and not submitted.** Everything below runs locally.

## What the challenge asks, and where it is

| The challenge asks for | In PARALLAX |
|---|---|
| A public web tool: enter RA and Dec, see the images play as a video | Home and **Explore**: a name or coordinates, then Play, Blink, Subtract, Add |
| Tested on Barnard's Star, Epsilon Indi B, WISE 0855, RW Aurigae, R Draconis | All five are built in and work offline; results below |
| Easy to update with new data releases | One `RELEASES` table in `pipeline/spherex.py`; DR1 and QR3 are both searched |
| Show the 102 bands; add detectors together; spectra on the fly | Every frame shows its wavelength; filter by detector or wavelength; **Add** mode; click a source for its 0.75–5 µm spectrum; the Sky map slides through all 102 all-sky colours |
| Add or subtract images taken at different times | **Add** and **Subtract** modes, with a warning when two frames are not the same wavelength |
| Let the user choose the field of view | The **Width** box (2′ to 30′) |
| Overlays from other telescopes (Gaia, WISE) | Gaia DR3 stars moved to each frame's date; **What WISE saw around 2015** (CatWISE2020); the **Sky map** shows the whole sky in SPHEREx's 102 colours and in WISE, 2MASS, photographic plates and IRAS |
| Coordinates in the URL, embeddable | `/explore?ra=..&dec=..&fov=..`; add `&embed=1` for a viewer-only page |
| Show metadata such as contamination flags | Flags, release, wavelength and SHA-256 for every frame; saturated sources are refused, not forced |
| Use Astropy | Yes, throughout the pipeline |

## What PARALLAX found with real SPHEREx data

Everything here comes from this repository's code and data. Details: [VALIDATION.md](VALIDATION.md),
[docs/HUNT_REPORT.md](docs/HUNT_REPORT.md), [RESULTS_LOG.md](RESULTS_LOG.md).

| | Result |
|---|---|
| **A prediction locked before the data was downloaded** | A motion model fitted only to SPHEREx visits 1–3 of **Epsilon Indi B** was hashed and committed, and only then was visit 4 downloaded. Visit 4 landed **0.072″** from the prediction (pass limit set in advance). "It stays put" missed by 1.95″. A second experiment on 2MASS J0415−0935 also passed. |
| **Predictions for images that do not exist yet** | Positions of Epsilon Indi B and 2MASS J0415−0935 for every month of 2027 were locked in commit `bbfd25f` on 14 Nov 2026. The archive's newest image of each field at that moment is recorded. Anyone can check them when NASA releases the next visit. |
| **A blind search that finds known movers by itself** | Across 25 fields (2.3 square degrees, 2,891 exposures) the search tested **5,195 sources** for motion without being told which ones move (Gaia is used only to line the images up). It found **13 of 19 known fast movers** on its own, including the free-floating planetary-mass object SIMP 0136, flagged **0 movers that no catalogue explains**, and rejected 8 false alarms with its vetting tests. Hidden synthetic cold sources were recovered down to 600 µJy at 3–8″/yr, with no stationary one called a mover. |
| **The coldest known brown dwarf** | **WISE 0855** is invisible at 0.75–3.8 µm and detected at 3.8–5.0 µm (460 ± 32 µJy at 4.4–5.0 µm, S/N 14). The blind search flags it as a cold-only mover, and the WISE catalogue confirms it was where its motion says, ten years ago. |
| **The two variable stars** | RW Aurigae and R Draconis saturate SPHEREx, so normal photometry fails. Measured from the unsaturated ring of light around each star, at matched wavelength: **R Draconis faded by 42 %** (9.6σ) and **RW Aurigae by 36 %** (5.3σ) between visits. Barnard's Star, the control, stayed flat (4 %, 0.8σ). Of 6 other bright stars measured the same way (11 visit comparisons), 0 were flagged variable; their median change was 3 % and the largest 8 %. Significances are calibrated against simulated constant stars with the same sampling, which lowered them by a factor of 1.2 to 1.3. Experimental. |
<!-- DISTANT_ROWS:start -->
| **Distant worlds, found by their parallax** | **2 of 4 known distant worlds found blind and placed at the right distance**: Makemake (52.72 ± 0.01 AU; JPL 52.72), Eris (95.53 ± 0.07 AU; JPL 95.52). 0 false objects were linked. Missed: Pluto (only one visit holds enough detections of the body, and the rule needs two); Haumea (only one visit holds enough detections of the body, and the rule needs two). The largest distance error among those found is under 0.1 %. Each blind result was hashed into a local lock record before JPL's positions were opened. Makemake's spectrum along the fitted orbit shows the dips of methane ice, which is what its surface is known to be. |
| **Planet Nine** | The same search for a body at 200 to 20,000 AU in the 23 fields with three or more visits (2.1 square degrees): **no detection**. 2 geometric candidates were raised and both were rejected as thousands of times too bright to be planets; one is a reflection of a saturated star that imitates parallax. Synthetic planets are recovered down to 300 µJy (10 of 16); the predicted Planet Nine is about 7 µJy, so these images could not have found it. |
| **Barnard's Star** | Its core is saturated, so we tracked the centre of its halo. In a visit that had been sealed, the halo had moved **10.56″ in 0.98 years; Gaia says 10.23″** (they differ by 0.37″; limit set in advance 1.5″). PASS. |
| **What disappeared since WISE** | Of 945 bright sources WISE saw around 2015 in our fields, the ones SPHEREx no longer sees at those spots are 4 known brown dwarfs (2MASS J0415-0935, Epsilon Indi B, SIMP J013656.5+093347.3, WISEP J150649.97+702736.0): each one's SPHEREx motion, run back to the WISE years, passes through the empty spot. 0 faded or vanished without an explanation. |
| **Waiting for the next images** | A watcher checks NASA's archive for new SPHEREx images of every locked prediction (python -m pipeline.watch). Makemake's next position is locked from the blind orbit alone; SPHEREx should next see it between 2026-12-22 and 2027-01-17, and JPL's ephemeris, checked after locking, agrees to 3″. |
| **Machine learning, tested honestly** | A machine-learning real/artefact model, trained on synthetic stars in real SPHEREx images and tested on the real detections of four dwarf planets it never saw, ranks them with AUC 0.87; signal-to-noise alone gives 0.88. It does not beat the simple rule yet, so it is not used in any result. |
<!-- DISTANT_ROWS:end -->
| **No false alarms** | 33 stars that Gaia says are still: 0 flagged as moving, and the error bars behave as quoted (pull spread 0.93). |

No new object is claimed. Sources the search cannot explain are called candidates, and movers that an older catalogue
already lists are labelled as known.

## What is new, and what is not

Blinking images, mover searches, catalogue overlays and spectra already exist in tools such as SPHEREx Blink 3.0,
WiseView, Driftnet and others ([docs/COMPETITORS.md](docs/COMPETITORS.md)). PARALLAX does not claim them. What it adds:

1. **It tests itself in public.** Predictions are locked before the test images are downloaded, and the pass rule is fixed first. The 2027 forecasts are locked before those images exist at all.
2. **Its blind search is scored.** Known movers are hidden in the fields, and the search is graded on finding them
   and on not inventing others.
3. **Every claimed mover faces older catalogues.** If Gaia (2016) or WISE (2015) saw a source at the same spot, the
   motion is rejected. If they saw it where the motion says it was, it is confirmed over ten years.
4. **Wavelength is never ignored.** Each frame carries its true per-pixel wavelength, and brightness is compared only
   at matched wavelength, including for the saturated variable stars.
5. **Everything is reproducible.** Each file's SHA-256 and archive URL are recorded, and every page has a shareable link.
6. **Distance from parallax, for solar-system worlds.** SPHEREx sees every patch from opposite sides of the Earth's orbit, six months apart. PARALLAX links a
   world across those visits with one orbit and reads its distance from the jump. We found no other SPHEREx tool that does this.
7. **A saturated star is still measured.** Brightness and motion come from the unsaturated halo, each with a control or a locked test.

PARALLAX builds on SPIFF (Gagné et al. 2026, arXiv:2604.22012) for brown-dwarf templates.

The interface uses real NASA photographs of Pluto, Neptune, the WISE sky and SPHEREx as decoration. Each is credited in
the page footer and in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The sky images you measure are always SPHEREx data.

## Run it locally

Requirements: Python 3.12+ and Node 20+ (tested with Python 3.13 and Node 22).

```sh
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt pytest
npm --prefix web ci
npm --prefix web run build
.venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. The five NASA targets, the hunt results and the proofs work offline. Any other
coordinates query the NASA archive live.

**Docker:** `docker build -t parallax . && docker run -p 8000:8000 parallax`.

## Reproduce the science

```sh
# 1. Fetch cutouts for the test targets. A held-out visit is sealed: only its metadata is recorded.
.venv/bin/python -m pipeline.fetch_target epsilon-indi-b --seal-last-visit --workers 6
# 2. Lock -> commit -> reveal
.venv/bin/python -m validation.experiment lock <slug> && git add validation/experiments/<slug> && git commit -m lock
.venv/bin/python -m validation.experiment reveal <slug>
# 3. Build the target pages, then validate
.venv/bin/python -m pipeline.build_curated --all
.venv/bin/python -m validation.run && .venv/bin/python -m validation.inject
# 4. The Planet X hunt: resolve the fields, download, search, summarise
.venv/bin/python -m validation.hunt_fields resolve
.venv/bin/python -m validation.hunt_fields fetch
.venv/bin/python -m validation.hunt_fields run all && .venv/bin/python -m validation.hunt_fields index
# 5. Variable stars from their halo, with controls; forward predictions; the hunt report
.venv/bin/python -m validation.halo_controls
.venv/bin/python -m validation.forecast
.venv/bin/python -m validation.hunt_report
# 6. Distant worlds: choose and download the fields, search blind, lock, then score against JPL
.venv/bin/python -m validation.distant_fields plan makemake pluto haumea eris && .venv/bin/python -m validation.distant_fields fetch makemake pluto haumea eris
for b in makemake pluto haumea eris; do .venv/bin/python -m validation.distant_run detect $b && .venv/bin/python -m validation.distant_run link $b && .venv/bin/python -m validation.distant_run score $b; done
.venv/bin/python -m validation.distant_spectrum makemake && .venv/bin/python -m validation.distant_report && .venv/bin/python -m validation.distant_md
# 7. Planet Nine mode, and Barnard's Star from its halo
.venv/bin/python -m validation.planet_nine search && .venv/bin/python -m validation.planet_nine inject && .venv/bin/python -m validation.planet_nine report
.venv/bin/python -m validation.barnard_halo lock && .venv/bin/python -m validation.barnard_halo open
.venv/bin/python -m validation.shiftstack_run search eris && .venv/bin/python -m validation.shiftstack_run score eris
.venv/bin/python -m validation.forecast_distant makemake    # forecast for images that do not exist yet
.venv/bin/python -m pipeline.watch                         # check NASA's archive for new images
.venv/bin/python -m validation.vanished && .venv/bin/python -m validation.ml_realbogus
.venv/bin/python -m validation.ledger verify      # the local lock record
# Tests
.venv/bin/python -m pytest -q
npm --prefix web test
```

## Architecture

```
web/            Vite + React + TypeScript. Canvas sky viewer, SVG charts, Aladin Lite sky map, pages: Sky map, Explore, Planet X hunt, Proof, About.
api/app.py      FastAPI service (docs/API.md). Live fields and measurements run as background jobs.
pipeline/
  spherex.py      IRSA SIA2 (DR1 + QR3) search, de-duplication, visits, checksummed cutouts, FITS loading, flags, wavelengths
  astrometry.py   coordinates, tangent plane, proper motion, parallax factors
  measure.py      native-pixel ePSF fits, Gaia DR3 registration, neighbour deblending
  motion.py       weighted fits: stationary, linear, linear + parallax; model comparison
  investigate.py  one source measured in every exposure along a track
  analysis.py     spectrum (102 bins), SPIFF templates, matched-wavelength variability, seven competing explanations
  hunt.py         the blind search: stacks, linking, motion test on every source, vetting, Gaia and WISE decade checks
  halo.py         brightness of saturated stars from their unsaturated halo
  solarsystem.py  known asteroids and comets near a source (IMCCE SkyBoT)
  distant.py      distant worlds: per-exposure detection, tracklets, one orbit across visits, mirrored-Earth test
  ephem.py        JPL Horizons positions (to choose fields and to score; never given to the search)
  shiftstack.py   shift-and-stack: adds exposures along trial paths to find worlds too faint for one image
  watch.py        checks NASA's archive for new SPHEREx images of every locked prediction
  frames.py       display-only reprojection onto a north-up grid
validation/     experiment.py (lock and reveal), forecast.py, run.py (targets and controls), inject.py (synthetic),
                hunt_fields.py (the hunt), halo_controls.py, hunt_report.py, distant_run.py (blind test on known worlds),
                planet_nine.py, barnard_halo.py, ledger.py (local lock record), shiftstack_run.py, forecast_distant.py,
                vanished.py (what disappeared since WISE), ml_realbogus.py (the machine-learning test)
data/           targets/ (the five NASA targets), hunt/ (every searched field), investigations/
```

### Method, briefly

- **Time and wavelength.** Time is `MJD-AVG`. Wavelength comes per pixel from the spectral WCS, so a detector name is
  never treated as a wavelength.
- **Registration.** Each exposure is shifted on to Gaia DR3 stars moved to that date. Typical scatter is 0.25″. Where
  too few stars are bright enough (most 4.4–5.0 µm exposures), the image's own coordinates are used with a larger error.
- **Positions and fluxes.** The release ePSF is fitted to the original pixels. Flagged pixels are masked, saturated
  cores are refused, and known neighbours are fitted at the same time.
- **Motion.** Weighted least squares in the tangent plane; errors grow when the fit is worse than they claim.
- **Rules fixed in advance.** Motion needs ≥ 5σ and |μ|/σ ≥ 5. A brightness change needs ≥ 5σ and ≥ 5 %. A template
  match needs reduced χ² ≤ 3 over ≥ 15 bins.
- **The blind search** adds: the motion must look the same at short and long wavelengths, must survive dropping any
  one visit, must not sit next to a saturated star, and must agree with Gaia and WISE positions from ten years ago.

## Known limits

- Three of the five NASA targets saturate SPHEREx. Their cores cannot be measured; the halo method is experimental.
- Pixels are 6.15″, so close pairs (Epsilon Indi Ba/Bb, RW Aur A/B) are measured as one blend.
- WISE 0855 comes out too fast: 10.0 ± 0.4″/yr measured, where the published motion and parallax predict 8.3″/yr at
  the same dates. That is about 3σ and we cannot explain it; a star 8″ away may be pulling the centroid.
- The hunt's vetting rules were added as false alarms turned up on these same 25 fields, so "13 of 19" and "0
  unexplained" are in-sample scores. The distant-world test below was scored out of sample.
- Gaia is not optional: it lines up every exposure, and for 5 of the 8 rejected false alarms the Gaia check was the
  only test that caught them. In the 4.4–5.0 µm detector most exposures have too few stars to line up, so those use
  the image's own coordinates with a larger error.
- The hunt's recovery fields were chosen because a known mover is there. They measure completeness, not discovery.
- The Planet Nine mode is a method and a limit, not a real chance of discovery: about 2 square degrees searched out of
  thousands, and the predicted planet is about 40 times fainter than the faintest synthetic planet we can link.
- The distant-world fields were chosen from JPL's positions. That tests whether the search works; it cannot find an unknown world.
- The distant-world search found 1 of 4 known worlds. It needs at least four single-exposure detections in each of two visits, so it
  misses worlds fainter than about magnitude 18, worlds in crowded star fields, and worlds imaged in one visit only.
- Locks made in the third session are in a local file, not in Git, so their times are this computer's own.
- Live queries download at most 48 cutouts to stay polite to the archive, and about one in five can fail when it is busy.

## Documents

[VALIDATION.md](VALIDATION.md) · [docs/HUNT_REPORT.md](docs/HUNT_REPORT.md) · [docs/DISTANT_WORLDS.md](docs/DISTANT_WORLDS.md) ·
[docs/PLANET_NINE_RESEARCH.md](docs/PLANET_NINE_RESEARCH.md) · [docs/JUDGING_NOTES.md](docs/JUDGING_NOTES.md) · [RESULTS_LOG.md](RESULTS_LOG.md) ·
[DATA_SOURCES.md](DATA_SOURCES.md) · [AI_USAGE.md](AI_USAGE.md) · [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) ·
[DEVELOPMENT_HISTORY.md](DEVELOPMENT_HISTORY.md) · [SUBMISSION.md](SUBMISSION.md) (draft) ·
[DEMO_SCRIPT.md](DEMO_SCRIPT.md) · [docs/API.md](docs/API.md) · [docs/COMPETITORS.md](docs/COMPETITORS.md) ·
[docs/REVIEW_CHECKLIST.md](docs/REVIEW_CHECKLIST.md)

Data: NASA SPHEREx DR1 Spectral Images (doi:10.26131/IRSA678) and QR3 from NASA/IPAC IRSA; Gaia DR3 (ESA);
CatWISE2020. *This publication makes use of data products from the Spectro-Photometer for the History of the Universe,
Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the
California Institute of Technology, and is funded by the National Aeronautics and Space Administration.* PARALLAX is
not affiliated with or endorsed by NASA.

## Cold-world spectra (fourth session)

<!-- COLDSPEC_LINE -->
- Cold-world spectra: the model reads types to ±1.5 subtypes and recognises 59 of 66 known T dwarfs with 0 false alarms; applied under a locked rule to 448 unclassified objects, it flagged 5: 5 are T dwarfs already typed in the literature (a blind test passed), 0 doubtful, 0 new candidates. It missed 1 of 6 published T dwarfs hidden in the list. See VALIDATION.md, section 12.
<!-- /COLDSPEC_LINE -->
