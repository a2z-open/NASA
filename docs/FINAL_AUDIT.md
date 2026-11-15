# PARALLAX — final audit and competition readiness

Written 14 Nov 2026, about 23:30 Seattle time, for team review only. Nothing here was submitted, published or sent anywhere.
Repository state audited: `b777479` (GitHub `main`) plus today's uncommitted Explore redesign. Auditor: Claude Code (Opus 5.5).

How to read this: section 1 is the summary. Section 15 is the to-do list, ordered P0 → P1 → P2. Section 16 answers the
20 questions in one or two lines each. Everything else is evidence.

Evidence types used below:

- **[auto]** an automated test or script I ran.
- **[browser]** I did it in the running app and looked at the result.
- **[docs]** taken from the project's own records (`VALIDATION.md`, `RESULTS_LOG.md`, the ledger). I re-checked a sample against the live API.

Scores use the official 1–5 scale from the Space Apps judging guide. They are **our own estimate**, not a prediction of results.

---

## 1. Executive summary

PARALLAX does what NASA asked:

- You type a position (a name, RA/Dec in decimal, or RA/Dec in NASA's sexagesimal format).
- It fetches the real SPHEREx images of that patch from NASA's IRSA archive.
- It plays them like a little video, blinks two dates, subtracts and adds them, and orders them by colour.
- The five NASA test targets load from the repository in about one second, with no archive call.

It goes well beyond the brief, and the science is unusually honest:

- Predictions are locked before the data is opened.
- Failures are reported as failures.
- Nothing is called a discovery.

**What is holding it back is not the science. It is reach and reliability:**

1. **Nobody outside this laptop can use it yet.** The GitHub repository is private and the app is not deployed. The
   submission guide requires a public "Link to Final Project", and NASA judges review online. This is the biggest eligibility risk.
2. **The submission demo must be 30 seconds or less (or at most 7 slides).** Projects over the limit "will not be eligible for
   Global Judging" (Project Submission Guide). The 4-minute video is for the Seattle stage only. A separate short demo is needed.
3. **Live queries depend on one European server.** ESA's Gaia archive (`gea.esac.esa.int`) is unreachable from this network
   tonight. Because of that, every new position waits up to 90 s before its photos appear, and every "tap to measure" on a
   new position fails. NASA's MAST archive serves the same Gaia DR3 table in 0.37 s.
4. **The AI disclosure is now wrong.** `AI_USAGE.md` and `SUBMISSION.md` say no AI runs inside the app. Since the teammates'
   commit `b777479`, an optional OpenAI planner can run inside the discovery agent.
5. **The NASA-required tool is hard to find.** Explore is not in the top navigation. The home page buttons go to the sky
   map, and the map's button for it is labelled "Archive field".

All five problems are small to fix. Items 1, 2 and 6 in section 15 need team decisions. The rest are less than an hour of
work each.

Today's change: the Explore page was redesigned to match the home page and to be simple for a child, with every function
kept (screenshots in `docs/audit/screens/`). See section 8.

### Fixed since the audit (15 Nov 2026, approved by the team)

The rest of this report describes the state before these fixes; the rows below replace what it says about them.

| Item | What changed | How it was checked |
|---|---|---|
| P0-1 Gaia | `gaia_query()` in `pipeline/measure.py` asks ESA first with an 8 s connection limit, then NASA's MAST copy of the same Gaia DR3 table. After an ESA failure it goes straight to MAST for 10 minutes. MAST's cone search is slightly inexact near the edge, so it is asked for a 10% wider circle and the stars are then cut to the exact radius. The hunt's Gaia check uses the same function. | [auto] For Epsilon Indi B, Barnard's Star and WISE 0855, the MAST result has the same stars (110, 1052, 171) and the same values as the saved ESA files. 4 new tests in `tests/test_gaia_fallback.py`; all 125 Python tests pass. [browser/API] A brand-new 6′ position (RA 150.1, Dec 2.2) finished in 75 s with 24 photos and 34 Gaia stars (the Gaia step took 9 s, then about 1 s on later calls). Tap-to-measure on a star in it measured all 24 photos, each aligned on 5–9 Gaia stars, and returned "stationary". |
| P0-5 Explore hard to find | "Explore" added to both top bars (inner pages and home), after "Sky map". The footer's duplicate "Images" link was removed. The map button "Archive field" is now "SPHEREx photos". On phones the six links fit without scrolling at 375 px. | [browser] Desktop and 375 px phone. |
| P1-4 Map opens a slow live query for saved targets | On the map, the five NASA targets now open their saved page (`/explore?target=…`, all photos, blink starts). Other places still open a live query at the map's zoom. | [browser] Epsilon Indi B card → saved 446-photo page. |

Still open: the team decisions (repository visibility and a public link, the 30-second demo, the AI disclosure, the
picture provenance, registration). Saving the photos before the Gaia step (part of P0-1) was not needed once the
Gaia step became fast.

---

## 2. Mandatory NASA requirements, line by line

| # | NASA requirement | Status | Evidence | Where in the UI | Works end to end? | What remains |
|---|---|---|---|---|---|---|
| 1 | Public-facing web tool | **Partial** | [auto] Runs on `127.0.0.1:8000`. A fresh clone installs, builds and serves all five targets. [docs] `docs/DEPLOYMENT.md` is ready, not executed. GitHub: `visibility: private`. | Whole app | Locally, yes. Publicly, **no**. | Deploy, or make the repo public with run instructions (team decision, P0-4). |
| 2 | Genuine SPHEREx imagery | **Complete** | [browser] Every frame comes from IRSA (DR1 and QR3) with a product ID, FITS link and sha256. Footer cites DOI 10.26131/IRSA678. | Explore → More tools → "About this photo" | Yes | — |
| 3 | Right ascension entry | **Complete** | [browser] Typed `08h55m10.831s -7d14m42.53s` → RA 133.795129°. Decimal also works. | Explore search pill (helper text gives examples) | Yes | — |
| 4 | Declination entry | **Complete** | Same test → Dec −7.245147°. Signs, `d m s` and `°′″` accepted. Out-of-range values give a plain error. | Same | Yes | — |
| 5 | Retrieve the requested patch | **Complete, with a reliability gap** | [browser] A live 6′ query of WISE 0855 returned 24 cutouts, reprojected and dated. It took about 2 minutes: about 1 minute of IRSA download, then a 90 s wait on the unreachable ESA Gaia server. | Explore, after Go | Yes, but slow tonight | P0-1: use MAST for Gaia. Show photos before the catalogue step. |
| 6 | Multiple epochs of one region | **Complete** | [auto] Curated fields: 2–4 SPHEREx visits each (for example Epsilon Indi B: 4 visits, 2025-04-24 → 2026-10-02). Live field: May 2025 → May 2026. | Timeline under the image; date chip on the image | Yes | — |
| 7 | Video-like playback | **Complete** | [browser] Play at 1–30 photos a second, step ←/→, Blink between two dates, timeline scrubbing. | Explore panel tabs; playback row | Yes | — |
| 8 | Easy to spot moving objects | **Complete (visual)** | [browser] Blink starts by itself on curated targets. A ring labels the target. Subtract shows a dark/bright pair. The fitted path is dashed. Tapping measures motion. | Explore | Visual: yes. Measuring a **new** spot fails while ESA Gaia is down. | P0-1 |
| 9 | Ease of use for non-astronomers | **Partial** | [browser] The new Explore is plain-language and works on phones. But Explore is hard to reach from the home page, the map button says "Archive field", and the measurement card is written for astronomers. | Navigation, map card, measurement | — | P0-5, P1-2 |

The brief's extra checks:

- **Alignment.** Frames are registered to Gaia and resampled to one sky grid, while measurements use the original pixels (stated in the UI). [docs] The held-out prediction landed 0.072″ (1/85 pixel) from the truth.
- **Coordinate accuracy.** The ICRS position is shown on every page. Names are propagated to today's date. NASA's WISE 0855 coordinates are about 2.2′ from where the object is now, because it has moved since that position was measured. Typing the name centres it.
- **Timestamps.** UTC to the second on every frame.
- **Brightness variation.** Halo photometry for saturated stars, plus a "Different colours: brightness can't be compared" warning.
- **Public discovery.** The Check page collects human votes on real candidates (stored locally only).

---

## 3. NASA's five test targets

All five open in one click from Explore's start page and from the Proof page. They work offline: a fresh clone served
every target with no archive call [auto].

| Target | Result | Identity and data | What a user sees | Measurement | Limits |
|---|---|---|---|---|---|
| **Epsilon Indi B** | **PASS** | Gaia DR3 6412596012146801152. 446 frames, 4 visits, all 6 detectors, 0.75–5.01 µm, Apr 2025 → Oct 2026. | Blink starts by itself; the ring jumps. Tap → measurement. | [auto+docs] μ = 4,635 ± 16 mas/yr (Gaia total 4,684), ϖ = 298 ± 9 mas (Gaia 270.7). Gaia differs by −1.8σ, +2.8σ, +2.9σ, explained as the photocentre of an unresolved binary. **Held-out prediction PASS: 0.072″, d² = 4.85 < 11.83, locked before download.** Spectrum best fits T3 (χ²ᵣ 1.55). | 6.15″ pixels blend the pair. The parallax tension is disclosed in VALIDATION.md, but not on screen. |
| **Barnard's Star** | **PARTIAL** | Gaia DR3 4472832130942575872. 62 frames (2 visits) in the viewer; the archive has 358. | Visible, but saturated. Explore's measurement says motion is "insufficient". | [docs] The core overflows in 63/63 exposures. **Halo-centre test on a sealed visit: 10.56″ in 0.98 yr vs Gaia 10.23″, gap 0.37″ (limit 1.5″), PASS (ledger record 7).** | The pass is shown only on the Proof page (Test 5). The Proof scorecard row still says "Inconclusive for motion", and Explore does not link to the result (P1-1, P1-2). |
| **WISE 0855−0714** | **PARTIAL** | Kirkpatrick et al. 2021 track. 155 frames (3 visits). Seen only at 3.8–5.0 µm. | Opens on detector 6 (long wavelength). The dot is visible and moves. | [docs] Detected 460 ± 32 µJy at 4.42–5.00 µm (S/N 14). Spectrum ≥ Y1. Motion 10.1 ± 1.1″/yr from 12 exposures. **About 3σ faster than the published track predicts (6.6″/yr between these visits), and unexplained; positions sit about 1″ off the track.** | Faint, so only 12 positions. Parallax not fitted. The offset is disclosed in VALIDATION.md, not on screen. |
| **RW Aurigae** | **PARTIAL** | Gaia DR3 match. 142 frames (3 visits). | Saturated core; the halo is visible. | [docs] Faded to 0.64 ± 0.04 of the first visit (5.3σ after the audit correction), from halo photometry at matched wavelength. Controls: 0 of 7 steady bright stars wrongly flagged. | Experimental method. The core is saturated in 131/142 frames. It only just passes the 5σ rule. |
| **R Draconis** | **PARTIAL** | Gaia DR3 match. 101 frames in the viewer (3 visits). | Saturated core (a black hole in the image); the halo is visible. | [docs] Faded to 0.58 ± 0.03 (9.6σ), halo method, same controls. | Experimental method. The core is saturated in 103/104. The wing-photometry fallback fails (0 accepted). |

Honest bottom line: one clean PASS (Epsilon Indi B), plus a strong locked pass for Barnard's Star that the main tool does
not yet surface. The other three are real detections with clearly stated caveats. SPHEREx saturates on three of NASA's
five targets. That is a property of the telescope, and PARALLAX says so.

---

## 4. NASA's optional considerations

| Item | Status | How it works | Visible in the UI? | Value |
|---|---|---|---|---|
| A. Latest data | **Complete for live queries, manual for saved targets** | Live queries ask IRSA's SIA2 service for DR1 and QR3 at request time. `python -m pipeline.watch` checks for new images of every locked prediction. The five targets are saved snapshots and need a re-run to refresh. | Proof → "Waiting for the next images" (last check 5 h ago) | High |
| B. 102 bands, 6 detectors, spectra | **Complete (spectra on demand need Gaia)** | Detector buttons with real ranges (0.75–1.09 … 4.42–5.00 µm), a wavelength range, a "Colours" mode ordering photos by wavelength, and "Add" over the chosen detectors (NASA's S/N suggestion). The measurement builds a 102-bin spectrum at the moving position, with SPIFF templates and errors in µJy. | Explore → More tools → Infrared colours; measurement card | High. On-demand spectra for **new** spots fail while ESA Gaia is down (P0-1). |
| C. Add and subtract | **Complete** | Add: median-subtracted stack of up to 240 frames. Subtract: later minus earlier, with a warning when colours differ. Shift-and-stack along the predicted path (short/mid/long). | Explore tabs; More tools → "Photos added along its path" | High |
| D. Field of view | **Complete** | Width chips 6′/10′/20′/30′ (any 2–30′ by URL). With a field open, a chip reopens the same spot at that width. The UI says "Wider shows more sky but loads slower." | Explore head | Medium |
| E. Gaia and WISE overlays | **Complete for saved targets; Gaia empty on new spots tonight** | Gaia DR3 stars propagated to each frame's date (proper motion), WISE movers from IRSA, epochs stated. | More tools → Show on the photo | High once P0-1 is fixed |
| F. Coordinates in the URL | **Complete** | `ra`, `dec`, `fov`, mode, detectors, wavelength range, frame, A/B, stretch, selected source and measurement all live in the URL. `?embed=1` gives an embeddable viewer. | "Share this view" button | High. Verified that a shared link restores the view. |
| G. Metadata and flags | **Complete** | Date (UTC), wavelength and bandwidth, detector, visit, release and version, flags at the centre (OVERFLOW, SUR_ERROR, …), product ID, FITS link, sha256. Flag counts appear in the Proof scorecard. | More tools → About this photo | High |
| H. Astropy / Aladin | **Complete** | Astropy (WCS, coordinates), astropy-healpix, Aladin Lite 3.8.2 for the sky map, and SPIFF for spectral templates. | Sky map | Medium. Note the licence TODO (P1-8). |

---

## 5. NASA and partner data: use and credit

| Resource | Used? | What for | Working tonight? | Credited? | More worth it? |
|---|---|---|---|---|---|
| IRSA SPHEREx (DR1 + QR3) | **Yes, core** | Every image, archive manifests, the all-sky map layer | Yes (SIA2 1.7 s) | Footer, DATA_SOURCES, DOI | — |
| SPHEREx tutorial notebooks | Not directly | (Same SIA2 + cutout method) | — | Not mentioned | Cite as a reference in the submission |
| WiseView | No (inspiration) | WISE data comes from IRSA instead | — | README mentions it | Cite as the inspiration for blinking |
| Gaia DR3 | **Yes** | Registration, overlays, known-object checks | **ESA server down here; MAST copy works** | Yes (7 mentions) | Switch to MAST (P0-1) |
| NEOSSat / CADC (CSA partner) | **Yes, small** | "What other telescopes saw here" asks CADC for NEOSSat frames | Not re-tested tonight | DATA_SOURCES | Mention CSA in the submission's partner field |
| data.nasa.gov | No | — | — | — | Not needed |
| Also used | | JPL Horizons (planets, Makemake), MAST (JWST/HST observation lists, previews), HEASARC (Chandra, XMM, Swift, NuSTAR, NICER), CatWISE/AllWISE, VHS, UKIDSS, MPC, Sesame/SIMBAD, 23 HiPS map layers | ESA-hosted HiPS (JWST/HST imagery on the map) are **unreachable tonight** | DATA_SOURCES, THIRD_PARTY_NOTICES | List all of them in the "References" field: the submission checkbox requires it |

Eligibility: "use at least one NASA dataset" is clearly met. SPHEREx is the core of the product, not an add-on.

---

## 6. Scientific validity and technical reliability

**Strong:**

- **Lock → predict → reveal.** 47 hash-chained ledger entries. `verify()` passes [auto].
- **Out-of-sample checks.**
  - Held-out SPHEREx visit of Epsilon Indi B: 0.072″.
  - Makemake 52.72 ± 0.01 AU vs JPL 52.72; Eris 95.53 vs 95.52 (found blind, 0 false links).
  - Blind hunt: 13 of 19 known fast movers found, 0 unexplained movers, 8 false alarms rejected.
- **Honest negatives.**
  - Planet Nine deep stack: 60 µJy reached against 7.2 µJy predicted. 2 flagged, 0 survive.
  - Machine learning "does not beat the simple rule, so it is not used".
  - Halo significances were reduced after an internal audit.
- **No discovery is claimed anywhere.** Candidates are called candidates.

**Weak or unverified:**

1. **Single point of failure on ESA Gaia** for every new-spot measurement and catalogue overlay (P0-1).
2. **WISE 0855 speed** is about 3σ high and unexplained. **The Epsilon Indi B parallax** is 2.9σ from Gaia. Both are disclosed in VALIDATION.md but not on screen (P1-12).
3. **The halo method** is experimental. RW Aurigae only just passes 5σ.
4. **The teammates' discovery agent** (MPC Isolated Tracklet File + HelioLinC3D + Catalina evidence) could not be run here: `/api/discovery/settings` reports `archive_ready: false`. Its claims are **unverified by this audit**.
5. **Machine learning** runs only offline in validation scripts. The optional OpenAI planner only orders evidence checks; per its own prompt it "cannot change measurements, fits, scores, or identification verdicts". All measurements are deterministic code.

Reproducibility:

- A fresh clone installed, built and served all five targets [auto].
- 121 Python tests pass (4 skipped), the 16 web tests pass, and the production build and type check pass [auto].
- I did **not** test with Wi-Fi switched off. Do this 2-minute check before the tech check.

---

## 7. Judging criteria (official 1–5 scale, our estimate)

| Criterion | Score | Why | What stops a 5 | Quickest raise |
|---|---|---|---|---|
| Impact | **3** | A public SPHEREx blink tool plus citizen checking could reach many people. But nothing is public yet, and impact is claimed, not shown (no users, no outside reviewers). | Not usable by anyone else tonight | Public link (P0-4). One sentence on who uses it (classrooms, Backyard Worlds volunteers). |
| Creativity | **4** | Locked predictions as a product feature, halo astrometry of saturated stars, motion-following 102-colour spectra, and blind dwarf-planet recovery. No other SPHEREx tool found does these (docs/COMPETITORS.md). | Blinking itself is not new (WiseView) | Lead with "every claim is tested before we look" |
| Validity | **4** | Out-of-sample passes, honest failures, disclosed offsets. | Live measurement breaks without ESA; three targets saturated; two ~3σ tensions | P0-1. Show caveats on screen. |
| Relevance | **4** | Every mandatory item works; all eight optional items are present; SPHEREx is the core. | The required flow is hard to find from the home page | P0-5 |
| Presentation | **3** | A beautiful home page and a clear new Explore. But the 30-second demo, the 4-minute video and the public link do not exist yet, and the measurement card is technical. | Missing demo assets | 30-second cut + `/deck` PDF + rehearsed live path on cached targets |

A skeptical judge would say: "Impressive science and honest, but can I open it? And what happens if I type my own
coordinates?" Tonight the honest answers are "not yet" and "it waits 90 seconds". Both are fixable before 1 PM.

---

## 8. UI/UX audit: where a judge sees each requirement

**Explore redesign (done today, uncommitted).** Light page and black data cards, as on the home page.

- **Search:** a home-style pill with examples and sky-width chips.
- **View modes:** five pill tabs (Play, Blink, Subtract, Add, Colours). Each has a one-line, child-level explanation ("Spot the jump. … The dot that jumps is moving.").
- **First instruction:** "Tap the ring to measure Epsilon Indi B."
- **More tools (closed by default):** all expert controls, under "More tools".
- **Removed:** the status pill (now shown only on errors), the "Hide controls" button, the brown hint bar, and the monospace stats line.
- **Measurement colours:** status labels are black and white (solid = supported, dashed = tentative, dotted = not supported).
- **Scrolling:** the mouse wheel scrolls the page; zoom is a pinch, Ctrl + scroll, or the +/− buttons.
- **Phone:** the layout works at 390 px.
- **Unchanged:** all logic, URLs and keyboard keys.

Screenshots are in `docs/audit/screens/`. Verification: type check, build, the 16 web tests, every mode, the measurement
open and close, typed NASA coordinates, phone, embed, and no console errors [auto + browser].

**Requirement → feature → location → evidence → benefit**

| NASA requirement | PARALLAX feature | Where | Evidence | Judging benefit |
|---|---|---|---|---|
| Enter RA/Dec | Search pill: decimal, sexagesimal or name | /explore | NASA's WISE 0855 string parsed exactly | Relevance |
| Real SPHEREx images | IRSA cutouts, IDs, FITS, sha256 | More tools → About this photo | 446 frames for Epsilon Indi B | Relevance, Validity |
| Little video | Play / Blink / timeline | Panel tabs, playback row | Blink auto-starts on targets | Relevance, Presentation |
| Spot movers | Ring hint, Subtract, dashed path, tap to measure | Image, measurement card | 4.63″/yr; prediction to 0.072″ | Validity |
| Five targets | One-click cards | /explore start page; /proof | All load offline | Relevance |
| 102 bands / detectors / spectra | Detector buttons, Colours mode, spectrum | More tools; measurement | T3 and Y1 template fits | Creativity |
| Add / subtract | Add, Subtract, path stacks | Tabs; More tools | Live in the viewer | Relevance |
| Field of view | Width chips 6–30′ | Explore head | 6′ and 20′ fields fetched | Relevance |
| Gaia / WISE overlays | Checkboxes | More tools → Show on the photo | Epoch-propagated | Validity |
| URL / embed | Share, `?embed=1` | Head; any page | Link restores the view | Impact |
| Metadata / flags | Flags at centre, release, visit | About this photo; Proof scorecard | Flag counts per target | Validity |

**Hidden or confusing (fix list):**

- Explore is missing from the top navigation, and the home page buttons lead to the sky map (P0-5).
- The map's button to open the photos says "Archive field" and opens a slow 20′ live query (P0-5, P1-4).
- Barnard's Star's passing motion test is only on the Proof page; its scorecard row contradicts it (P1-1).
- The measurement card opens with technical text ("reduced chi-square") (P1-2).
- The Investigation and Hunt pages still use green, amber and red labels (P1-7).

**One-minute test (first-time, non-astronomer):**

- Starting at `/explore`: **pass**. One tap on a target card shows a real moving object blinking within about 5 s.
- Starting at the home page: **at risk**. There is no visible route to Explore above the fold. A first-timer lands on the sky map and must find "Archive field".

**Personas:**

- **First-time user:** follows the home page story; may never reach the image tool.
- **NASA judge:** wants the requirements in order; needs the public link and Explore in the navigation.
- **Citizen scientist:** Check page and sky chunks, but votes stay on this server only.
- **Astronomer:** will open VALIDATION.md and find honest numbers, and will ask about the Gaia parallax tension and the WISE 0855 speed.

Accessibility:

- Visible focus, labelled controls, keyboard keys, reduced motion respected.
- The view tabs use radio roles without arrow-key movement (P2).

Performance:

- Saved targets: field JSON 489 kB in 0.04 s.
- Live queries: about 1–2 min; IRSA is the main cost, plus the Gaia timeout tonight.

---

## 9. Everything built beyond NASA's requirements

| Capability | Works? | Validated? | Unique? | Criterion | Visible? | In the demo? |
|---|---|---|---|---|---|---|
| Lock-before-reveal predictions + hash ledger | Yes | Yes (47 entries verify) | Yes, for SPHEREx tools | Validity, Creativity | Proof Tests 1, 5, 7 | **Yes** |
| Motion + parallax from SPHEREx alone | Yes | Held-out PASS | Rare | Validity | Measurement card | Yes |
| Motion-following 102-bin spectra | Yes (needs Gaia on new spots) | Template fits; 59 of 66 methane dwarfs, 0 of 414 false | Yes | Creativity | Measurement card | Yes (one shot) |
| Halo photometry / astrometry of saturated stars | Yes | Controls, locked Barnard test | Yes | Creativity, Validity | Proof Tests 4–5 | Yes |
| Blind mover hunt (25 fields) | Yes | 13 of 19 known movers, 0 unexplained | Partly | Validity | /hunt | Short |
| Blind dwarf-planet recovery | Yes | Makemake and Eris to < 0.1 % | Yes | Validity, Creativity | /hunt | **Hero shot** |
| Planet Nine deep stack (null) | Yes | Controls and injections | Yes | Validity (honesty) | /hunt, /how | One line |
| Asteroid stacking along known paths | Yes | 27 → 53 seen at S/N 5 | Partly | Creativity | /how | Optional |
| Sky map: SPHEREx all-sky + 23 layers + "what other telescopes saw" | Yes (ESA layers down tonight) | Previews are real archive products | Partly | Relevance (data) | /map | Yes |
| Check a candidate (citizen review) + shared sky chunks | Yes (local votes) | — | Partly | Impact | /check, /map | Short |
| Forecasts for future SPHEREx dates + archive watcher | Yes | Waiting for data | Yes | Validity | Proof → Test 7 | One line |
| Discovery agent (MPC ITF + HelioLinC3D + Catalina, optional LLM ordering) | **Not runnable here** | **Unverified** | Possibly | Creativity | Map → "Search agent" | **Only if a teammate's machine runs it** |
| Embed mode, full URL state | Yes | Tested | No | Impact | Share | Mention |
| Kid-level explainers (home game, How page) | Yes | — | Partly | Presentation | /, /how | Yes |

---

## 10. Comparison with existing tools

| Tool | What it does better | What PARALLAX does better | Where PARALLAX is weaker |
|---|---|---|---|
| WiseView (byw.tools) | A proven blink of WISE epochs at any position. Behind hundreds of public discoveries. A decade-long baseline. | SPHEREx's 102 colours; measurement, spectra and proof in the same tool | A short SPHEREx baseline (about 1.5 years); no community yet |
| Backyard Worlds (Zooniverse) | A large volunteer community, a classification workflow, a route to publication | Every result is measured and tested, not only voted on | The Check page is tiny and stores votes locally |
| Aladin / Aladin Lite (CDS) | A professional multi-survey viewer with catalogues and cross-match | Time-series blink of SPHEREx epochs plus measurement (PARALLAX embeds Aladin for its map) | Aladin's catalogue depth |
| IRSA's own viewers | Official, complete access to SPHEREx products | Public-friendly blinking and a plain-language story | No bulk data or professional tools |

**Strongest three differentiators:**

1. Claims tested before looking (locked, hash-chained predictions that passed on unseen data).
2. SPHEREx-native science from one tool: motion, parallax and a 102-colour spectrum, even for saturated stars.
3. A child-simple public blink viewer with NASA's five targets ready offline.

---

## 11. Seattle local awards

A project can win one. The local judges are aerospace engineers (Juno Propulsion, Blue Origin autonomy/GNC, The Exploration
Company), not astronomers. Pitch trust and verification, not jargon.

- **Best Use of Data: strongest fit.** SPHEREx is the core, plus 23 telescopes, all real archive data.
- **Best Use of Technology: second.**
- **Best Storytelling: possible**, with the Pluto/Neptune "say first, look after" story.
- Most Inspirational, Art & Technology, Local Impact and Best Mission Concept are weaker fits.

---

## 12. Global Nomination and Global Awards

Competitive for nomination **if** the eligibility items are fixed:

- a public link;
- a demo of 30 seconds or less (or at most 7 slides);
- complete fields, including References;
- a correct AI disclosure;
- all members on the Members tab.

Best global fits: **Best Use of Science** (the lock-then-reveal method is the scientific method, applied in public) and
**Best Use of Data**.

Remote NASA judges will review the project page and links without us. The README, `/proof` and the public link must
explain everything on their own.

Dates: nominees 3 Dec 2026, finalists 17 Dec 2026, winners 26 Jan 2027.

What separates PARALLAX from a winner today: no public users and no deployment, the live path depends on one European
server, and three of five targets saturate (not our fault, but it makes the headline result narrower).

---

## 13. Eligibility checklist

| Item | Status | Note |
|---|---|---|
| Responds to an official challenge | Yes (team to confirm the selected challenge on the site) | |
| Team registered, same Local Event, ≤ 6 members, all on the Members tab | **Team to confirm** | Do not change registration without team agreement |
| At least one member in person on Sunday | **Team to confirm** | Organiser email |
| NASA data used | **Yes** | SPHEREx core; list everything in "NASA Data" |
| Open-source licence | Yes, MIT | Aladin Lite licence note to confirm (P1-8) |
| Publicly available "for anyone to use" | **No: repository private, not deployed** | P0-4 |
| Secrets | Clean | No keys in the tree or the history [auto]. The OpenAI key is read from the environment only. |
| Reproducible | Yes | A fresh clone installs, builds and serves the five targets [auto] |
| AI ("Super Intelligence") disclosure | **Needs fixing** | P0-2. Also add this session (Explore redesign, this audit). |
| SI-generated images or video watermarked | **Unknown** | The home illustration's source is unknown (P0-6) |
| No NASA logos or branding | Yes | |
| Demo of 30 s or less, or at most 7 slides | **Missing** | P0-3. `/deck` already has 7 slides. |
| References field lists every external resource | **To do** | Use DATA_SOURCES + THIRD_PARTY_NOTICES |
| No people under 18 in media | Yes | |
| Project name | **Team decision** | At least 4 other entries use "PARALLAX" |

---

## 14. Four-minute presentation (240 s, organisers' split)

The live parts use **saved targets only**. No new coordinates on stage unless P0-1 is done and the venue network has been
tested. The backup is a screen recording of this exact sequence.

| Time | Section | On screen | Say (short) |
|---|---|---|---|
| 0:00–0:35 | Person + Problem | Home page hero; then 446 real SPHEREx photos of one patch | "In 1930 Pluto was found because one dot moved between two photos. NASA's SPHEREx now photographs the whole sky in 102 colours, every six months. Nobody can blink it all by hand." |
| 0:35–1:20 | Solution | Explore: type `08h55m10.8s -07d14m42s` **or** tap a saved target; Play → Blink → Subtract | "Type any position. Real NASA images, lined up and dated, play like a video. The dot that jumps is moving." |
| 1:20–1:50 | Measure | Tap Epsilon Indi B → measurement card | "4.6 arcseconds a year and a brown-dwarf spectrum, from SPHEREx alone." |
| 1:50–2:30 | Proof 1 | Proof → Test 1 → "Open them" | "We locked a prediction before downloading the newest images. It landed 0.07 arcseconds away." |
| 2:30–3:05 | Proof 2 | /hunt: Makemake | "Found blind: 52.72 AU. NASA JPL says 52.72." Mention honestly: "We looked for Planet Nine and did not find it; here is how deep we looked." |
| 3:05–3:45 | Possibility | Sky map + Check page + Test 7 forecasts | "Anyone can check a candidate. Our 2027 predictions are already locked. New SPHEREx data arrives every week." |
| 3:45–4:00 | Close | Wordmark | "Find what moves. Then prove it." |

Likely Q&A answers (one line each):

- *Did you discover anything?* No. We recovered known objects blind and published our nulls.
- *Why trust it?* Predictions are locked before the data is opened; the ledger is public.
- *Three targets saturate?* Yes. We measure the ring of light around them, and checked it on 7 steady stars.
- *Does AI do the science?* No. The measurements are fixed, deterministic code. An optional AI planner only orders evidence checks.
- *What if the archive is down?* The five targets and all the proofs work offline.

---

## 15. Remaining tasks, prioritised

Effort is wall-clock for one person. "1 PM?" means it must be done before Sunday's 1 PM tech check.

### P0 — critical

| ID | Issue (feature) | Requirement / criterion | Fix | Benefit | Effort | Verify | 1 PM? |
|---|---|---|---|---|---|---|---|
| P0-1 | ESA Gaia unreachable → new spots wait 90 s and every new-spot measurement fails (`pipeline/measure.py` `GAIA_TAP`, `api/app.py`) | Req 5, 8; opt. B, E; Validity | Query MAST Gaia DR3 (`mast.stsci.edu/vo-tap/api/v0.1/gaiadr3`, 0.37 s, same source and values) first, or after a 10 s ESA timeout. Save the photos before the catalogue step. | Live demo safe; NASA-recommended Gaia source | 45 min + tests | Block ESA; a new spot shows photos in under 70 s and tap-to-measure succeeds | **Yes** if live coordinates are shown |
| P0-2 | AI disclosure says "no AI at runtime"; the OpenAI planner exists (`AI_USAGE.md`, `SUBMISSION.md`) | Submission rules; honesty | Describe the optional planner: off without a key, orders checks only. Add the 14–15 Nov sessions. Fill the TEAM TODOs. | Eligibility, trust | 20 min | Text matches the code; no "No AI runs" line remains | Before Q&A ideally; must be in by 11:59 PM |
| P0-3 | No submission demo; the limit is 30 s video or 7 slides | Global eligibility | Print `/deck` to PDF (7 slides) and/or cut a 30-s video from the 4-min recordings | Eligibility, Presentation | 20 min (deck) / 1–2 h (video) | Length ≤ 30 s or ≤ 7 slides; public link opens in a private window | No (11:59 PM) |
| P0-4 | Not public: private repo, no deployment; SUBMISSION.md wrongly says "public" | Open source; "Link to Final Project" | **Team decision:** make `a2z-open/NASA` public and/or deploy per `docs/DEPLOYMENT.md`. Fix the SUBMISSION.md line. | Eligibility; remote judging | 15 min (visibility) / 1–2 h (deploy) | Open the link logged out | Ideally; must be before 11:59 PM |
| P0-5 | Explore hard to find: not in the navigation; map button says "Archive field" | Ease of use; Relevance | Add "Explore" to `NAV` in `Shell.tsx`; rename the button "See photos over time"; add a home-page link "Type coordinates" | One-minute test passes | 15 min | From the home page, reach a blinking target in < 3 clicks | **Yes** |
| P0-6 | Home illustration `spherex-glow.webp`: source unknown (THIRD_PARTY_NOTICES TODO) | SI watermark rule; copyright checkbox | Team confirms the source. If AI-generated, watermark it; if unknown, replace with a NASA/JPL SPHEREx image (credited) | Avoids an eligibility problem on the first screen | 15–30 min | Credit line present | **Yes** (it opens the talk) |
| P0-7 | Team items: team name, members on the Members tab, challenge selected, project page fields, in-person attendance | Eligibility | Team only. I do not touch the Space Apps site. | Eligibility | Team | Team check | Yes |

### P1 — high impact

| ID | Issue | Criterion | Fix | Effort | Verify | 1 PM? |
|---|---|---|---|---|---|---|
| P1-1 | Proof scorecard Barnard row says "Inconclusive", "63 cached · 3 visits"; Test 5 says PASS; the API serves 62 frames from 2 visits | Validity, Presentation | Update the row and the "Three of the five…" sentence | 20 min | Page text consistent with Test 5 and the API | Yes |
| P1-2 | Measurement card opens with astronomer text; for saturated targets it shows "insufficient" without a link to the halo results | Ease of use | One plain line on top ("It moves 4.6″ a year: proof it is close") and a link to Proof Tests 4–5 for saturated targets | 30 min | Barnard and R Dra cards link to proof | Yes |
| P1-3 | DEMO_SCRIPT A/B describe the old UI ("round window", "press Search") | Presentation | Update to the new Explore | 20 min | Script matches the app | Yes |
| P1-4 | Map "Archive field" opens a 20′ live query even for saved targets | Reliability | Route known targets to `?target=`; default 10′ | 20 min | Card for Epsilon Indi B opens the saved field in 1 s | Yes |
| P1-5 | ESA-hosted map layers (JWST/HST imagery via `skies.esac.esa.int`) unreachable tonight | Reliability | Re-test at the venue. Don't demo those layers live, or add a "layer unavailable" message. | 15–45 min | Layers load or show a message | Yes (demo plan) |
| P1-6 | Wi-Fi-off test not done | Reliability | Turn Wi-Fi off and walk the 4-min path | 5 min | Every step works | **Yes** |
| P1-7 | Green/amber/red labels on the Investigation and Hunt pages (only Explore was fixed) | Presentation (house style) | Move the `.xp-dark` label rules into the shared CSS | 20 min | No coloured labels site-wide | Optional |
| P1-8 | Aladin Lite licence note (GPL-3 metadata vs LGPL-3 file) | Open source | Confirm and state it in THIRD_PARTY_NOTICES | 10 min | Note updated | No |
| P1-9 | Discovery agent not runnable here (`archive_ready: false`) | Validity of claims | Teammate demonstrates on their machine or labels it "needs setup"; don't present unverified results | 15 min | Run once end to end | Yes (decide) |
| P1-10 | NASA Data / Partner / References fields not drafted | Eligibility | Draft from DATA_SOURCES + this report (SPHEREx, Gaia via ESA/MAST, WISE, JPL, MAST, HEASARC, CSA NEOSSat via CADC) | 30 min | Every external resource listed | No (11:59 PM) |
| P1-11 | Two ~3σ tensions not on screen (Epsilon Indi B parallax, WISE 0855 speed) | Validity | Add a "Known caveats" line to the Proof scorecard | 20 min | Visible on /proof | Optional |
| P1-12 | Video work (4-min stage video + 30-s cut) | Presentation | Resume per `video/SPEC.md`; re-record the two Explore clips with the new UI | 3–5 h | Plays with sound on this Mac; USB copy | **Yes** (backup) |

### P2 — polish

| ID | Issue | Fix | Effort |
|---|---|---|---|
| P2-1 | Date formats differ ("Sep 28, 2026" vs "28 Sept 2025") | One formatter | 10 min |
| P2-2 | "1 of 93" vs "446 photos": the detector filter is not explained | Add "detector 3 only — change in More tools" | 10 min |
| P2-3 | View tabs lack arrow-key movement | Roving tabindex | 20 min |
| P2-4 | JS bundle > 500 kB warning | Code-split the map | 30 min |
| P2-5 | Saved targets are snapshots | Schedule `pipeline.watch` and refresh after each release | 30 min |
| P2-6 | Cite the SPHEREx tutorial notebooks and WiseView as references | Add to DATA_SOURCES | 5 min |
| P2-7 | No automated UI tests for Explore | A Playwright smoke test of the five targets | 45 min |

---

## 16. The 20 questions

1. **Every mandatory requirement met?** Functionally yes. All nine work in the app. "Public-facing" is not met until it is deployed or the repo is public, and ease of use needs P0-5.
2. **All five objects genuinely tested?** Yes, with real SPHEREx data: 1 PASS (Epsilon Indi B), 4 PARTIAL (Barnard's Star, WISE 0855, RW Aurigae, R Draconis), with stated reasons.
3. **Optional items completed?** All eight (A–H) are implemented. A and E are partial in practice: snapshots for saved targets, and the Gaia outage for new spots.
4. **Optional items incomplete?** On-demand spectra and Gaia overlays for new spots while ESA is down; automatic refresh of saved targets.
5. **Built beyond requirements?** Locked predictions and a hash ledger, SPHEREx-only motion and parallax, 102-colour spectra, halo methods for saturated stars, the blind hunt, blind dwarf-planet recovery, the Planet Nine null, asteroid stacking, a 23-layer sky map with archive lookups, citizen checking, forecasts, and the discovery agent (unverified).
6. **Genuinely unique?** Lock-then-reveal as a public feature, saturated-star halo astrometry, and motion-following SPHEREx spectra. Blinking itself is not unique.
7. **Credible to NASA experts?** Yes, because it reports its failures and tensions. Expect questions on the Epsilon Indi B parallax (+2.9σ) and the WISE 0855 speed (~3σ).
8. **Does the UI communicate every capability?** Mostly, after today's Explore redesign. Not yet: the route from the home page, Barnard's pass, and the technical measurement text.
9. **Understandable without explanation?** Explore and Proof, yes. The overall route through the site, not yet (P0-5).
10. **Scores (our estimate, 1–5):** Impact 3 · Creativity 4 · Validity 4 · Relevance 4 · Presentation 3.
11. **Strongest advantage?** Every claim is tested before looking, with a 0.072″ held-out pass and Makemake to 4 digits.
12. **Biggest weakness?** Nobody outside this laptop can use it, and live queries depend on one European server.
13. **Strongest Seattle awards?** Best Use of Data, then Best Use of Technology, then Best Storytelling.
14. **Competitive for Global Nomination?** Yes, if P0-2, P0-3, P0-4 and P0-7 are done by 11:59 PM.
15. **What separates us from a global winner?** Real public use (a deployed link), a reliable live path, and a sharper 30-second story.
16. **Compliant on open source, NASA data and AI?** NASA data: yes. Open source: licence yes, availability no (P0-4). AI disclosure: not until P0-2. Image provenance: P0-6.
17. **Is the four-minute demo ready and reliable?** Not yet. The script needs updating (P1-3), the video and backup are unfinished (P1-12), and the live path must use saved targets.
18. **What remains before Sunday's presentation?** P0-1, P0-5, P0-6, P0-7, P1-1 to P1-4, P1-6, P1-9, P1-12, then rehearse with Wi-Fi off.
19. **What remains before final submission?** P0-2, P0-3, P0-4, P1-10, the TEAM TODOs in SUBMISSION.md and AI_USAGE.md, and the team pressing "Submit for Judging" themselves.
20. **Only three more improvements?** (1) Public link plus a 30-s demo (eligibility). (2) Gaia via MAST (live reliability). (3) Explore in the navigation, with the Barnard pass shown (judges find the core feature and the proof).

---

### Audit method and limits

- **Automated:** pytest (121 passed, 4 skipped), web tests (16), type check, production build, ledger `verify()`, secret scan of the tree and history, fresh-clone install, build and serve test.
- **Browser:** Explore at 1440 and 390 px; all five modes; typed NASA coordinates (live IRSA query); measurement open and close; embed; console; Investigation page; sky map card; Proof page text.
- **API checks:** five-target data and measurements; ESA, IRSA and MAST Gaia reachability; name lookup; on-demand measurement (failed because of ESA).
- **Read only:** the official Project Submission Guide and Judging & Awards Guide (13 Nov 2026), spaceappsseattle.org (judges, sponsors: F5 and Parsimoni), and public pages on Parsimoni.
- **Sponsors:** the site lists only F5 and Parsimoni. The other names in the brief could not be verified. Parsimoni's documented product is **SpaceOS** (an onboard app platform). No product called "SpaceRun" was found. A credible future idea is running PARALLAX's deterministic mover check onboard to prioritise which cutouts to send down. That is a concept only, not an integration.
- **Not done:** a Wi-Fi-off run; running the discovery agent; checking the teammates' claims about it; NEOSSat lookups tonight.
