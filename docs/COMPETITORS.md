# Competitor and requirements research: "Planet X and SPHEREx"

**Retrieved: 14 Nov 2026.** Based on public pages only (the challenge site, public GitHub
repositories and READMEs, and public demo sites). Nothing was posted, starred, forked,
signed into or submitted.

How to read this file:

- Every feature entry is **what the project's own README or live page states**, not
  something I tested, unless it says "seen" (first screen of the live site viewed) or
  "HTTP 200" (the demo URL answered on 14 Nov 2026).
- **yes** = stated in the README or seen on the page. **no** = the README itself says it is
  absent or limited. **unclear** = the README is silent or ambiguous. I did not guess.
- Wording from other sites is paraphrased. To respect quoting limits there is exactly one
  short verbatim quote in this file (section 1); everything else is a close paraphrase.
  Feature names such as *Find movers* are the projects' own labels.
- "PARALLAX" below means this project as described in the brief I was given. Where the
  brief did not mention a feature I say "not in the brief", which is not the same as
  "missing". Check each against the current build.
- Method: the challenge and guide pages were downloaded directly; GitHub was searched
  through the public unauthenticated API (15 queries, 413 repositories returned, 374
  READMEs downloaded, 368 mention SPHEREx); about 60 READMEs were read or keyword-digested;
  30 demo URLs were pinged; 9 live sites were opened for a first-screen look.

---

## 1. What the challenge literally asks

Source: <https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/>
(page last published 13 Nov 2026 per its metadata; difficulty tag: Advanced; skills tags:
Astrophysics, Planets & Moons, Software).

### The ask

The one verbatim phrase: participants must "create a public-facing web tool to display
images of the sky" (NASA Space Apps challenge page) from SPHEREx, so that anyone can
quickly see how those images change over time.

Objectives, paraphrased closely:

1. The tool is public-facing and web-based.
2. The user **enters the coordinates of a patch of sky (Right Ascension and declination)**.
3. The tool shows **a time-ordered series of images of that patch that plays like a short
   video**, so moving objects are easy to spot.
4. **Test it on five named targets**:
   - Barnard's Star
   - Epsilon Indi B (described as a pair of brown dwarfs orbiting a star)
   - WISE 0855 (described as a fast-moving brown dwarf; coordinates given as
     RA 08h55m10.831s, Dec -7d14m42.53s)
   - the variable stars RW Aurigae and R Draconis

Note that two of the five test targets are **variable stars, not movers**. The summary
also lists what should show up by shifting position: comets, asteroids, stars, brown
dwarfs and, in the page's framing, possibly new planets. The background section names Pluto's
discovery by blinking and the Backyard Worlds volunteer projects as the model, and says
the goal is to help as many people as possible make discoveries.

### Potential Considerations (optional, eight items)

| # | Consideration (paraphrased) |
|---|---|
| 1 | New data arrives fast: design the tool so it is easy to update with the latest data releases. |
| 2 | Display the 102 infrared bands creatively; for example, add together the data of each of the six detector arrays to improve signal-to-noise. The page gives extra credit to tools that generate spectra on the fly. |
| 3 | Give users the option to add together or subtract images taken at different times. |
| 4 | Let users choose the field of view (larger fields track faster movers but cost transfer time). |
| 5 | Offer overlays of data from other telescopes, such as Gaia or WISE. |
| 6 | Make the tool queryable by coordinates in the URL so it can be embedded in other sites. |
| 7 | Display metadata such as contamination flags. |
| 8 | Consider existing public tools: Astropy for handling data and Aladin (CDS, Strasbourg) for display. |

### Data and resources the page points to

| Resource | URL | What the page says it is |
|---|---|---|
| NASA/IPAC Infrared Science Archive | <https://irsa.ipac.caltech.edu/Missions/spherex.html> | SPHEREx resources |
| SPHEREx Tutorial Notebooks | <https://caltech-ipac.github.io/irsa-tutorials/spherex/> | Example Jupyter notebooks for Python access |
| WiseView | <http://byw.tools/wiseview> | A similar tool for WISE data, offered as a model or inspiration |
| Gaia Mission Data | <https://archive.stsci.edu/missions-and-data/gaia> | Use the latest release (DR3) |
| Backyard Worlds (in the background text) | <http://backyardworlds.org/> | The volunteer project cited as precedent |
| CSA: NEOSSat overview | <https://www.asc-csa.gc.ca/eng/satellites/neossat/> | Space Agency Partner resource |
| CSA: Canadian Astronomy Data Centre | <https://www.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/en/> | Space Agency Partner resource |
| CSA: NEOSSat data tutorial | <https://github.com/asc-csa/NEOSSAT_Tutorial> | Space Agency Partner resource |
| CSA: NEOSSat dataset | <https://data.asc-csa.gc.ca/dataset/neossat> | Space Agency Partner resource |

The IRSA page itself (same date) lists the releases: Quick Release products from July 2025,
QR2 from October 2025, QR3 from September 2026 and **Data Release 1 (DR1) in November 2026**,
plus cloud (AWS S3) access and a cutout tool.

---

## 2. Judging criteria and Global Awards (official, 2026)

Source: Judging & Awards Guide,
<https://www.spaceappschallenge.org/resources/judging-awards-guide/>
(the awards overview at <https://www.spaceappschallenge.org/awards/> confirms ten Global
Awards chosen by an executive committee of NASA and partner-agency experts).
Submission rules: <https://www.spaceappschallenge.org/resources/project-submission-guide/>.

### Criteria

At every level (Local/Universal, Global, Executive) each project is scored **1 to 5 on
each of five criteria**:

| Criterion | What the guide asks (paraphrased) | What a 5 looks like (paraphrased) |
|---|---|---|
| **Impact** | Size of the problem addressed, quality and quantity of the effect, how many people it inspires or helps. | Significant problem, extensive reach, benefits a large audience, far exceeds expectations. |
| **Creativity** | Originality and innovation: a novel concept or a meaningful improvement on existing ideas. | An approach not attempted before that challenges conventional methods. |
| **Validity** | Grounded in scientific principles; technically feasible; achieves its purpose; completeness; usability and user-friendliness. | Scientifically sound, fully developed, ready for real-world use, highly usable. |
| **Relevance** | Fully and directly addresses the chosen challenge and uses NASA data as a core component, not a superficial addition. | Thoroughly engages the challenge; NASA data is integral and well executed. |
| **Presentation** | How clearly the team communicates the challenge, solution and significance. Judges use both the demo and the full project for this score. | Well-structured, engaging, polished storytelling. |

The guide explicitly tells teams to give Presentation as much attention as the other four.

### Process and hard rules that affect ranking

- Phase 1: Local (or Universal Event) judges pick Global Nominees, announced 3 Dec 2026.
- Phase 2: Global judges pick Global Finalists and Honorable Mentions, announced 17 Dec 2026.
- Phase 3: an executive committee picks Global Winners, announced 26 Jan 2027.
- Demo: **a slide deck of at most 7 slides (title and intro included) or a video of at most
  30 seconds**; over-limit projects are not eligible for Global Judging. The demo link and
  final-project link must open without login. English required (video may be in another
  language with English subtitles).
- Deadline: Sunday 15 Nov 2026, 11:59 p.m. local time of the Local Event.
- At least one NASA data source or resource must be used to be eligible for a Global Award.
- All external code, text and images must be listed in the References field.
- AI is called *Super Intelligence (SI)* in the form. The SI answer is collected for data
  purposes and not shown to judges, but judges can see SI-generated indicators in the
  project and assess originality, intent and execution.
- The submission guide says most of the evaluation rests on the project submission page;
  the demo is considered and mainly helps the Presentation score.

### The ten Global Awards

| Award | One-line definition (paraphrased from the guide) |
|---|---|
| Best Use of Science | Best and most valid use of the scientific method. |
| Best Use of Data | Best at making space data accessible or applying it in a unique way. |
| Best Use of Technology | Most innovative use of technology. |
| Galactic Impact | Most potential to improve life on Earth or in the universe. |
| Best Mission Concept | Most plausible concept and design. |
| Most Inspirational | The project that captures the judges' hearts. |
| Best Storytelling Award | Most creatively communicates the potential of open data through storytelling. |
| Global Connection Award | Best connects people around the world through technology. |
| Art & Technology Award | Most effectively combines technical and creative skills. |
| Local Impact Award | Greatest potential to make a difference in the team's local community. |

For PARALLAX the natural targets are **Best Use of Science** (pre-registration, controls)
and **Best Use of Data** (spectra and astrometry from Level-2 frames).

---

## 3. The field

### 3.1 Size

- The challenge page's Teams tab reported **860 teams** on this challenge when opened
  (14 Nov 2026). I did not enumerate them.
- GitHub search returned 413 repositories for SPHEREx-related queries; most recent ones are
  entries for this challenge (a few are unrelated, for example a learning-management system
  and a desktop tool that share the name). Many have empty or one-line READMEs.
- Name collision: besides PARALLAX, at least four other entries use the name:
  ZENITH LABS **ParallaX**, **Parallax - Planet X / SPHEREx Observatory**
  (`hs-isadev/planet-x`), `bbaadd309/parallax-spherex-observatory`, and
  `wfrghh-code/ParallaxStack-`.

### 3.2 PARALLAX's own public repository (not a competitor)

`https://github.com/a2z-open/NASA` is titled PARALLAX and this project's local
`SUBMISSION.md` names it as the team repository, so I treat it as this project. What
a judge would see there at retrieval time:

- The public README describes an **earlier state** than the brief: one held-out Epsilon
  Indi B test (0.50 arcsec residual against a 3.15 arcsec frozen tolerance), five scorable
  stationary red controls, a WISE-to-SPHEREx benchmark called inconclusive, and Barnard's
  Star described as not supporting a centroid. It does not mention 33 controls, two passed
  predictions, template matching or the seven-explanation comparison.
- It credits ZENITH LABS: the browser build reuses their public sky index and two FITS/WCS
  modules under Apache-2.0. That is a competitor's code and must be in References.
- Demos: `https://a2z-open.github.io/NASA/` and `https://parallax-live.onrender.com/` (the
  README says the hosted viewer can take about a minute to wake).

### 3.3 Top tier: detailed feature records

#### A. ParallaX, team ZENITH LABS (Beirut)

- Repo: <https://github.com/abed-r-j/parallax-spherex> (created and last pushed 14 Nov 2026,
  Apache-2.0). Demo: <https://abed-r-j.github.io/parallax-spherex/> (HTTP 200, seen).
- One line: a static site that blinks SPHEREx frames for any position and replaces naive
  differencing with a per-pixel *chromatic template* that predicts each frame at its own
  wavelength.

| Feature | Status | Evidence |
|---|---|---|
| Blink / animation viewer | yes | README feature table: blink player with play, step, speed, loop, by survey pass or by frame; seen on the Barnard page. |
| Wavelength shown per frame | yes | Per-pixel wavelength read-out, wavelength window filter, time-against-wavelength map of all frames (README; map visible on the live page). |
| Automatic mover search | yes | `pipeline/src/parallax/detect.py`, `movers.py`; README says the classifier and linker recover asteroid (52) Europa's track without the ephemeris (28.3 arcsec/h against 28.5 predicted). Precomputed fields only. |
| Catalogue cross-match | yes | Gaia DR3 moved to frame date, CatWISE2020, IMCCE SkyBoT, JPL Horizons as seen from SPHEREx (`catalogs.py`, `sso.py`). |
| Spectra extraction | yes | Click any pixel for a spectrum from every frame, light curve in a wavelength window, CSV download. |
| Proper motion / parallax with uncertainties | PM yes, parallax no | README table: Barnard's Star 10.2 +- 0.5 arcsec/yr, Epsilon Indi B 4.64 +- 0.09, WISE 0855 7.81 +- 1.57 with catalogue parallax assumed. README states parallax is not measured reliably. |
| Validation | yes | Three-way *ledger* (naive, wavelength-gated, template) with injection-recovery at a matched false-alarm rate; known-object recovery of Europa and Pluto against Horizons; 185 offline tests; README says an independent review re-ran the code. Variables: RW Aurigae magnitude change with a control star, R Draconis period fit. |
| Planet X / discovery mode | no | README Limits: Planet X is the motivation, not a claim; no dedicated mode. |
| Live archive for arbitrary coordinates | yes | A 45.6 MB index of 1,628,230 Level-2 images ships with the site; the browser range-reads the public bucket (`?ra=&dec=&live=1`). README: live fields are simpler (no template, ledger, candidates or catalogue overlays). |
| Public demo | yes | GitHub Pages; URL parameters, `embed=1`, iframe snippet, Share button. |
| UI polish | high | Dark research console, tabs for seven view modes, light theme toggle (seen). |

Also ships: a 7-slide deck (PDF and PPTX), an IEEE-style paper PDF, a project report PDF,
a speaker script, user guide, judges' Q&A, a challenge checklist mapping every objective
and consideration to a feature, licences and citation file. SI disclosure: built with Claude.

#### B. Driftnet

- Repo: <https://github.com/epsretriever/spherex-planet-x> (created 29 Oct 2026, pushed
  14 Nov 2026, MIT). Demo: <https://driftnet-sky.vercel.app> (HTTP 200, seen).
- One line: a survey-style search for solar-system movers in SPHEREx with a catalogue of
  objects, per-object evidence reports, orbits and measured detection limits.

| Feature | Status | Evidence |
|---|---|---|
| Blink / animation viewer | yes | README: Explorer mode blinks real observations of a patch; *Patches of sky* tab. |
| Wavelength shown per frame | unclear | README mentions the changing filter position only for building spectra. |
| Automatic mover search | yes | Pipeline: find sources, reject stars, link tracks, score; weekly survey of ecliptic tiles in GitHub Actions. Live Objects page showed 571 objects: 69 unexplained, 462 known, 29 unconfirmed pairs, 11 likely artefacts (seen). |
| Catalogue cross-match | yes (solar system) | Live JPL SBIdent and Horizons checks through a Cloudflare Worker; IRSA TAP. Gaia/SIMBAD/WISE not mentioned. |
| Spectra extraction | yes | `science/composition.py`: distance- and phase-corrected reflectance compared with Bus-DeMeo asteroid classes; 2.7-3.1 micron hydration band. |
| Proper motion / parallax with uncertainties | orbits instead | `science/orbit.py`: statistical ranging, least-squares refinement, 100 orbit clones; distance given as median and 5-95% range. No stellar PM or parallax fit. |
| Validation | yes | Live Limits page: 23,400 simulated objects planted in real images; 92% recovery for AB <= 17 at 10-30 arcsec/h; half-recovery depth AB 17.0-17.7; **2 false candidates in 175.5 deg2** of control fields (1,950 runs); 0% recovery at 0.3-1 arcsec/h because linking spans about 1.5 days. Orbit and composition validation endpoints. |
| Planet X / discovery mode | yes (framing) | *Unexplained leads* tab, Planet Nine search region on the sky map, and a table on whether a planet could have been seen. README states it does not claim to find Planet X. |
| Live archive for arbitrary coordinates | no | README: pixel processing is done ahead of time; only catalogue checks are live. |
| Public demo | yes | Vercel site plus API health endpoint. |
| UI polish | high | Dark navy product-style site, natural-language search box, object cards with scores (seen). CI runs Playwright screenshots and Lighthouse >= 90 per README. |

Also: AI write-ups and natural-language search (Workers AI) with number checking, Isolation
Forest *most unusual* ranking, ADES-format draft export, a footprint map that records tiles
searched and found empty.

#### C. Muninn, team Yggdrasil

- Repo: <https://github.com/root3315/muninn> (created 11 Nov 2026, pushed 14 Nov 2026).
  Demo: <https://muninn.mydevbox.xyz> (HTTP 200, seen). Talk: `/talk.html` on the same host.
- One line: a live viewer reading SPHEREx frames by HTTP range request, with catalogue
  identification of marked sources and a slow-mover mode called *Hunter X*.

| Feature | Status | Evidence |
|---|---|---|
| Blink / animation viewer | yes | Blink every visit in sequence; wipe two visits against each other. |
| Wavelength shown per frame | yes | Each exposure is used at the wavelength the file gives for its detector pixel (README). |
| Automatic mover search | yes | README: finds and names asteroid (152) Atala (SNR 374 in one visit); *Hunter X* takes the twelve strongest flagged places, measures each in every visit, keeps what moves and sorts by slowness. |
| Catalogue cross-match | yes | Gaia (moved to visit date), WISE/CatWISE2020 via IRSA TAP, SkyBoT, JPL small-body identification. |
| Spectra extraction | yes | Spectrum on demand for a marked source from up to sixty exposures, plus a light curve at the most-sampled wavelength. |
| Proper motion / parallax with uncertainties | partly | Converts apparent rate to a distance (rate-to-distance formula in `public/js/hunt.js`); CatWISE proper motions are reported only at five times their error. A fitted PM with uncertainty for a new source is not stated. |
| Validation | partly | 79 offline tests on synthetic FITS; documents a rejected false flash (flagged cosmic-ray pixel); measures a 5-sigma depth of 17.61 AB per visit from delivered pixels. No injection completeness or false-alarm rate seen. |
| Planet X / discovery mode | yes | *Hunter X* plus an explicit sensitivity statement: 5.0-6.7 mag short of a Planet Nine prediction per visit, 2.1-3.8 mag short with 200 visits coadded. |
| Live archive for arbitrary coordinates | yes | Search box accepts names or coordinates; frames read from the AWS mirror by range request. |
| Public demo | yes | Custom domain; ten-slide talk; English and Russian. |
| UI polish | high | Full-screen star-field landing with target chips and an object card (seen). |

#### D. SPHEREx Blink 3.0 (and 2.0)

- Repo: <https://github.com/mateibut/SPHEREx-Blink-3.0> (created 7 Nov 2026, pushed
  12 Nov 2026, 4 stars, MIT). Demo: <https://mateibut.github.io/SPHEREx-Blink-3.0/>
  (HTTP 200, seen). Sister repos with the same lineage:
  <https://github.com/mateibut/SPHEREx-Blink-2.0>, <https://github.com/Andrei25Ciuta/SPHEREx>.
- Status caveats from its own README: it calls itself a personal practice project started
  5 Nov 2026 and not a competition submission; **the public demo runs on synthetic data**
  and real SPHEREx images are used only on the author's machine. An empty repository
  `mateibut/SPHEREx-Blink-4.0` was created on 14 Nov 2026 (no files, no README).
- One line: the most feature-complete blink workspace found, with mover search, a full
  source census with dossiers, and an Earth-parallax *Planet X mode*.

| Feature | Status | Evidence |
|---|---|---|
| Blink / animation viewer | yes | Blink, trail, compare A-B / A+B, per-detector thumbnails, timeline. |
| Wavelength shown per frame | yes | Timeline plots time against wavelength with one button per image and a wavelength window. |
| Automatic mover search | yes | *Find movers* links detections across survey passes and keeps a candidate only if the expected number of chance alignments is below 1; *Find everything* lists and classifies every source. |
| Catalogue cross-match | yes | SIMBAD, Gaia DR3, 2MASS, AllWISE at each catalogue's own epoch, SkyBoT asteroids at each image date, Aladin Lite context map. |
| Spectra extraction | yes | *Spectrum along its path* measures a mover where it is on each date; colour hint (4-5 micron against 1-2 micron). README: uncalibrated aperture sums. |
| Proper motion / parallax with uncertainties | partly | Candidate rows give speed in arcsec/yr, direction and significance; Planet X mode fits an Earth-parallax distance with a range (Makemake 52.65 AU against 52.62 AU from Horizons when told where to look). |
| Validation | yes | README and `docs/VALIDATION.md`: blind recovery of Barnard's Star and Epsilon Indi B on real cutouts (motion within 0.2-0.8 arcsec/yr of catalogue); chance-alignment estimate; *needs checking* threshold lets through about 1 false lead per 21 empty fields; failures published on a results page. |
| Planet X / discovery mode | yes | *Look for a distant body*: tests triples of detections from three passes for the displacement Earth's motion predicts. README's own status: the blind search with default options found nothing on real Makemake images; loosened options found it among about 33 chance candidates per field. |
| Live archive for arbitrary coordinates | only with local backend | FastAPI backend with `/api/cutouts?ra=&dec=&fov=&det=`; the public page is synthetic. |
| Public demo | yes (synthetic) | GitHub Pages with Overview, Workspace, Sky Explorer, Simulator, Planet X Lab, Results pages. |
| UI polish | high | Dark editorial landing with an amber accent and clear synthetic-data labels (seen). |

Also: CSV/JSON export and Markdown dossiers with a provenance record (thresholds,
algorithm version, run time) in every row.

#### E. EpochLoom

- Repo: <https://github.com/paradoxshh/epoch-loom> (created and pushed 14 Nov 2026, MIT).
  Demo: <https://epochloom.space> (HTTP 200, seen).
- One line: a live any-position viewer that aligns every exposure, blinks stacked visits,
  finds movers and names them from catalogues, with a local AI explainer.

| Feature | Status | Evidence |
|---|---|---|
| Blink / animation viewer | yes | Play, blink visit against visit with each visit stacked, difference, ratio. |
| Wavelength shown per frame | unclear | Stacks by wavelength and one-band blinking are stated; a per-frame label is not. |
| Automatic mover search | yes | Measure, Movers, *Find movers*; README example: Epsilon Indi B row reads 4.7 arcsec/yr. |
| Catalogue cross-match | yes | Gaia, CatWISE, SIMBAD, NEOWISE history, SkyBoT. |
| Spectra extraction | yes | README: photometry follows the archive recipe and agrees with IRSA's tool to 1-3% for isolated stars. |
| Proper motion / parallax with uncertainties | PM yes | README quotes WISE 0855 at 8.15 +- 2.0 arcsec/yr and Epsilon Indi B at 4.68 +- 0.10 against catalogue values. Parallax not stated. |
| Validation | partly | Catalogue agreement above; spectral-feature analysis checked on synthetic truth and three real stars. No false-alarm rate seen. |
| Planet X / discovery mode | unclear | Not named in the README. |
| Live archive for arbitrary coordinates | yes | Any position or name; every view is a URL with `ra`, `dec`, `fov`, `det`, `pm`, `mode`. |
| Public demo | yes | Custom domain, no login. |
| UI polish | high | Clean landing with one search field, a one-minute tour and a full tour, plain-language target table, light/dark toggle (seen). |

#### F. spherex-lens

- Repo: <https://github.com/Evan-Lim/spherex-lens> (created 5 Nov 2026, pushed 14 Nov 2026,
  MIT). The README's deploy target `https://spherex-lens.fly.dev` **did not answer**
  (no connection) when tried; no other public URL found in the README.
- One line: a *discovery portal* pipeline (co-add, ZOGY subtraction, catalogue triage,
  spectral-index classifier, ML real/bogus) with a measured accuracy page.

| Feature | Status | Evidence |
|---|---|---|
| Blink / animation viewer | unclear | README describes maps, vetting cards and an auto-cycling demo; it links to WiseView for flip-books. No SPHEREx blink player described. |
| Wavelength shown per frame | yes (metadata) | Wavelength from the `WCS-WAVE` table listed among per-exposure fields. |
| Automatic mover search | yes | ZOGY differencing with dipole/monopole detections and triage. |
| Catalogue cross-match | yes | Gaia DR3 (IRSA, MAST fallback), AllWISE and NEOWISE, AAVSO VSX, JPL SB Identification and SBDB, CADC SSOIS, NEOSSat. |
| Spectra extraction | yes | `step5_spectrum.py`: aperture photometry and a three-index classifier (CH4, H2O, NIR slope). |
| Proper motion / parallax with uncertainties | unclear | Uses catalogue motions for agreement scoring; no fitted PM stated. |
| Validation | yes (strongest found) | Null test (two halves of one epoch) sets the threshold; 12,240 strict injections on 18 DR1 fields: 69.3% found overall, movers 56.0%; 1.66 false candidates per field after triage (0 in six star fields); ML real/bogus scored on four held-out fields; a CI gate fails changes that lower precision or recall. |
| Planet X / discovery mode | unclear | *Discovery portal* framing; no Planet X mode named. |
| Live archive for arbitrary coordinates | with backend | *Open any field* and *Live from IRSA* need the Python backend; disabled and labelled on the static build. |
| Public demo | not reachable | See above. |
| UI polish | not seen | README describes a two-column light console, public/expert switch, WCAG 2.1 AA notes. |

Also: public voting that feeds labels back, CSV/VOTable and IVOA cone-search export, deep
ecliptic-pole light curves.

#### G. Nakshatra CHRONOS

- Repo: <https://github.com/PRITIDIPADAS/nakshatra-chronus> (created 12 Nov 2026, pushed
  14 Nov 2026, Apache-2.0). Demo: <https://pritidipadas.github.io/nakshatra-chronus/>
  (HTTP 200, seen), with a 30-second video and a 7-slide deck linked from the README.
- One line: an *observatory for change* that compares only same-colour pairs, runs three
  detection methods, **ranks five explanations** and tries to falsify its own answer. This
  is the closest in concept to PARALLAX's rule-based comparison of explanations.

| Feature | Status | Evidence |
|---|---|---|
| Blink / animation viewer | yes | Chapter I: time slider and blink. |
| Wavelength shown per frame | yes | *Fair pairs* plane of colour against time; pixel colour from `WCS-WAVE`. |
| Automatic mover search | yes | Methods P (catalogue), D (difference), A (anomaly ensemble); agreement pattern kept as a measurement. |
| Catalogue cross-match | yes | Gaia anchors, AllWISE overlay; Rubin alerts and known small bodies in live mode. |
| Spectra extraction | yes | *Spectral fingerprint* per candidate dossier. |
| Proper motion / parallax with uncertainties | partly | Motion map with error ellipses; no PM/parallax numbers seen. |
| Validation | yes, mostly simulated | 109 unseen simulated fields: 98.8% accuracy when it decides, 0 of 840 static stars called moving, 0.375 false candidates per empty field. On real QR3: 29 of 120 planted sources found (24%); the README says real data is much harder and that QR3 holds one visit at three of the five targets. |
| Planet X / discovery mode | yes (sandbox) | Chapter IX *Planet X lab* for a hypothetical planet. |
| Live archive for arbitrary coordinates | local only | The hosted page shows seven simulated fields; the full app (any coordinate, live data) runs locally. |
| Public demo | yes (simulated) | GitHub Pages; bilingual story (English and Bangla). |
| UI polish | distinctive | Light, serif, editorial layout with chapter navigation (seen). |

Also: SHA-256 *black box* seal of inputs and outputs with a reproduce button, a citizen
lab with blind repeats, plain-language queries mapped to measurements.

#### H. Radians

- Repo: <https://github.com/merttmtnn-sudo/Radians> (created and pushed 14 Nov 2026, MIT).
  Demo: <https://radians.onrender.com> (HTTP 200, seen).

| Feature | Status | Evidence |
|---|---|---|
| Blink / animation viewer | yes | Blink movie per epoch (co-added) or per exposure; GIF download. |
| Wavelength shown per frame | yes | Wavelength matching across visits is on by default; per-exposure wavelength at one pixel. |
| Automatic mover search | yes | Candidate finder; candidates panel on the live page (seen). |
| Catalogue cross-match | yes | Gaia DR3 at each frame date, SkyBoT, Aladin Lite with AllWISE, 2MASS, CatWISE2020; NEOSSat archive. |
| Spectra extraction | yes | 0.75-5 micron spectrum of any pixel on request; light curves. |
| Proper motion / parallax with uncertainties | unclear | Not stated. |
| Validation | yes | Injection test (40 injections per cell); with nothing injected the finder reports no candidate besides the target in the five challenge fields. |
| Planet X / discovery mode | unclear | Not named. |
| Live archive for arbitrary coordinates | yes | Archive queried live; README says new releases are picked up automatically. |
| Public demo | yes | Render free instance (README warns of about a minute to wake). |
| UI polish | medium-high | Dark tool layout with a control sidebar; English and Turkish (seen). |

#### I. SPHEREx Time-Lapse

- Repo: <https://github.com/ShivenKhurana1/spherex-timelapse> (created 25 Sep 2026, pushed
  14 Nov 2026, 1 star). Demo: <https://spherex-timelapse.vercel.app> (HTTP 200, seen).

| Feature | Status | Evidence |
|---|---|---|
| Blink / animation viewer | yes | Five views: time-lapse, blink, difference against the median sky, motion trail, deep stack. |
| Wavelength shown per frame | yes | Wavelengths from each file's `WCS-WAVE` table; detector band picker. |
| Automatic mover search | yes | *Scan for changes* rejects single-exposure glitches and links detections into tracklets; README: finds and names Pluto from 4 visits at 8.7 arcsec/day against JPL's 9.0. |
| Catalogue cross-match | yes (solar system) | SkyBoT labels, JPL Horizons as seen from SPHEREx, IMCCE Miriade. |
| Spectra extraction | yes | Click any star for light curve and spectrum. |
| Proper motion / parallax with uncertainties | unclear | Not stated. |
| Validation | partly | Pluto recovery above; no rates seen. |
| Planet X / discovery mode | unclear | Not named. |
| Live archive for arbitrary coordinates | yes | No backend; an image index rebuilt weekly from IRSA TAP (the landing page reported about 1.29 million images indexed). Can also follow a named comet or asteroid. |
| Public demo | yes | Vercel. |
| UI polish | high | Dark landing with curated example cards (seen). |

### 3.4 Second tier: compact matrix

Codes: Y = yes, N = no (stated by the README), ? = unclear. Columns: Blink, per-frame
wavelength, automatic mover search, catalogue cross-match, spectra, PM/parallax fit with
uncertainties, validation, Planet X mode, live any-coordinate queries, demo.

| Project (repo under github.com/) | Blink | Wl | Auto | X-match | Spec | PM fit | Valid. | PX mode | Live | Demo (14 Nov) | Notes and evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **SpectraShift** `rafincs3023-cyber/SpectraShift` | Y | Y | Y | Y | Y | N | synthetic tests | N | N | <https://spectrashift.rafincs3023.workers.dev> 200, seen | 102-channel spectral view plus two fixed dates (19 Jun and 17 Dec 2025) of one region; two-epoch candidate pipeline with Gaia, SIMBAD and known-object checks; README states no discovery labels. Clean dark landing. Last push 5 Oct. |
| **GhostShift** `ahmedatta3322/ghostshift` | Y | N | Y | Y (MPChecker) | ? | N | ? | N | CLI only | none in README | Two-sweep difference and track scripts, detector D2; README says SkyBoT blocked its requests and that SPHEREx cannot see Planet Nine. Last push 27 Oct. |
| **SkyShift** `anirudh12032008/skyshift` | Y | Y | Y | Y | Y | Y | synthetic truth | ? | local only | <https://anirudh12032008.github.io/skyshift/> 200 | Gaia DR3 and CatWISE2020 propagated to each date; weighted linear PM fits with errors calibrated on static stars; hosted page uses precomputed real targets. |
| **SkyShift** `cucuradu/skyshift` | Y | ? | ? | Y | Y | ? | ? | N | Y | README link `skyshift.web.app` returned 404 | Measures displacement under each blink and compares with Gaia; SkyBoT; spectrum coloured by visit. |
| **SkyShift** `samuelakosaonyejekwe/skyshift-spherex` | Y | Y | ? | Y | Y | ? | ? | ? | Y | <https://samuelakosaonyejekwe.github.io/skyshift-spherex/> 200 | Movie, blink, wavelength-matched difference, stack, false colour, user image equations; Gaia/WISE overlays; NEOSSat listings; presentation page. |
| **SkyShift** `Mahadi5577/skyshift` | Y | Y | ? | Y (SkyBoT) | ? | ? | ? | Y (game) | Y | <https://mahadi5577.github.io/skyshift/> 200 | *Hunt Planet X* game that trains players on planted fake movers with a skill score; Zenodo DOI and CI badge. Last push 6 Oct. |
| **SkyShift X** `Nour-saber57/-SkyShift-X` | Y | ? | ? | Y | Y | ? | ? | N | Y with backend | <https://skyshift-x.vercel.app> 200 | Simple mode plus Research Mode; Gaia DR3, CatWISE2020, 2MASS; explicit no-planet disclaimer. |
| **SkyShift** `happinessisreal/skyshift` | Y | Y | Y | Y | Y (approximate) | ? | ? | ? | partly | none in README | Rust/WebAssembly alignment in a worker; *Find movers*; SIMBAD, Gaia DR3, SkyBoT; README says under development. |
| **SPHEREx Time Machine** `ahmedm12j/spherex-time-machine` | Y | Y | Y | Y | Y | ? | functional checklist | Y (*Discovery Mode*) | Y | Streamlit link redirected my client to a login gate | Top-5 ranked candidate movers with CSV export; Gaia DR3/AllWISE overlays; 20-second tour. |
| **Slowsky** `Clupai8o0/slowsky` | Y | Y | N | Y | ? | N | ? | N | Y | <https://slowsky.vercel.app> 200 | Viewer only; README says it is not a planet finder; per-frame wavelength and flag summary. |
| **Fazari** `adembtr/fazari` | Y | Y | ? | Y (Gaia) | ? | Y | catalogue comparison | ? | ? | <https://adembtr.github.io/fazari/> 200 | README reports a Barnard's Star fit of -788.5 +- 53.1, 10264.5 +- 53.1 mas/yr from 354 exposures against the Gaia values. |
| **Cosmic Lens** `MSH2006/Cosmic-Lens` | Y | Y | Y | Y | Y | Y | ? | ? | Y | none in README | Linker classes mover/variable; Gaia DR3, AllWISE, 2MASS, JPL small bodies, NEOSSat; README table lists a mover at 8.97 +- 0.43 arcsec/yr. |
| **Star Platinum** `NazarKozak1/blink-comparator` | Y | ? | N in app | Y | Y | ? | ? | ? | Y | none in README | Frames/stacks/blink/diff; SIMBAD and Gaia DR3 at frame date; README says automated detection exists only as offline scripts. |
| **SPHEREx Explorer** `minhaz-42/spherex-explorer` | Y | Y | ? | Y | ? | ? | ? | ? | Y | <https://spherex-explorer.vercel.app> 200 | Each frame shows the wavelength at the target; GIF/video export; SIMBAD summary. |
| **AetherX** `asshifasultana/AetherX` | Y | ? | N | Y (Gaia) | Y | ? | ? | N | Y | <https://aether-x-alpha.vercel.app> 200 | AI agent with 24 viewer tools and a guard that blocks discovery claims; sky-culture content; spectrum hints. |
| **Team Prometheus** `diwakarsingh07/Team.Prometheus-NASA-SPACE-APP-CHALLENGE` | Y | ? | ? | Y | Y | ? | ? | Y (framing) | ? | <https://teamprometheus.diwkr7789.workers.dev/> 200 | Six comparison modes, Aladin Lite, Gaia PM vectors, AllWISE contours, scrollytelling landing. README lists bundled frame images and a simulated Kuiper Belt field; whether cutouts are fetched live is unclear. |
| **AURAx** `Thawshi-Srikanth/01-AuraX-2026` | ? | Y | N | Y (SIMBAD) | Y | N | ? | N | Y | none in README | Backend-first; wavelength-screened comparisons; spectral samples with variance-derived uncertainties; README says no PM estimate or discovery claim is produced. |
| **NoSleepClub Sky Lab** `dakiemdarktharr/nosleepclub_nasa_spherex` | ? | Y | ? | Y | ? | partly | simulations | N | ? | <https://nosleepclub-nasa-spherex.vercel.app> 200 | README mostly Vietnamese: WISE 0855 astrometry diagnostics with Gaia covariance, a reported shift of 3.29 +- 0.52 arcsec over 163.5 days, and a statement that the real-sky false-alarm rate is not yet confirmed. |
| **NOVAX** `englszz/novax-space-data-lab` | ? | Y | Y | Y (SkyBoT) | N | N | ? | N | N | <https://novax-space-data-lab.vercel.app> 200 | Spanish README: two-epoch detector-1 residual screen at 8 sigma with ePSF fitting; states no Planet X claim. Last push 1 Nov. |
| **BlinkSky** `skibidimama106-lang/BlinkSky` | Y | ? | N | Y | ? | N | ? | N | partly | <https://skibidimama106-lang.github.io/BlinkSky/> 200 | Game: tap what moved; taps checked against JPL sb_ident; real rounds plus generated practice rounds. |
| **SPHEREx Blink Comparator** `Unavailable4u/spherex-blink` | Y | Y | ? | Y | ? | ? | ? | Y (lab) | N | <https://spherex-blink-web.vercel.app> 200 | Each frame labelled with wavelength and a colour-mismatch warning; *Planet X lab* shows expected motion for a chosen distance; 20 prebuilt real fields. |
| **Sferavis** `Radit-Raian/Sferavis` | N | ? | Y | Y | ? | ? | ? | ? | ? | none | ML detection and classification pipeline with tracklet linking; no viewer described. |
| `shantanu-research/spherex-planet-x` | Y | Y | ? | Y | Y | Y (claimed) | ? | Y (title) | ? | none | Seven viewing modes with filter-colour tinting; centroiding plus linear PM regression; no numbers seen. |
| **Parallax observatory** `hs-isadev/planet-x` | ? | Y | ? | Y | Y | ? | ? | ? | Y | none in README | Science viewer with quick-look spectrum at native per-pixel wavelengths; Gaia and AllWISE context. Shares the name. |
| `Julian1006/spherex-time-machine` | Y | Y | ? | Y (Horizons) | Y | ? | ? | ? | Y | none | Blink and difference against a pinned reference; click-for-spectrum; follows a moving body. Last push 10 Nov. |
| `shree-aru/spherex-motion-explorer` | Y | Y | partly | Y | Y | ? | ? | ? | Y | none | Per-pair wavelength-match verdict; Gaia overlay auto-flags a high-PM star; 40-point spectrum. Last push 2 Nov. |
| `Veer-004/spherex-explorer-handoff` | ? | ? | Y (models) | Y | ? | ? | ? | ? | ? | none | README describes a zip with stacking-classifier mover models and five real fields; nothing else verifiable. |

### 3.5 Status of the names I was asked to look for

| Name | Found? | Where |
|---|---|---|
| SPHEREx Blink 3.0 | yes | `mateibut/SPHEREx-Blink-3.0` (section 3.3 D). Also Blink 2.0; Blink 4.0 repo exists but is empty. |
| SpectraShift | yes | `rafincs3023-cyber/SpectraShift` (section 3.4). Three other repositories with that name have no README and look unrelated. |
| Driftnet | yes | `epsretriever/spherex-planet-x`, live at driftnet-sky.vercel.app (section 3.3 B). |
| SkyShift | yes, at least ten repos | Six with real READMEs in section 3.4; `teoaguiilar/skyshift` and `nirmalapawar03-ops/skyshift` have one-line READMEs; `sreenath1212/skyshift-spherex` (demo 200; README lists a blink mode, a wavelength slider and a hypothetical Planet X, no archive or catalogue named); `kamikaze1120/skyshift` (curated asteroid blink). |
| GhostShift | yes | `ahmedatta3322/ghostshift` (section 3.4). |
| ZENITH LABS ParallaX | yes | `abed-r-j/parallax-spherex` (section 3.3 A). |
| WiseView | yes (prior art) | Section 3.6. |
| Backyard Worlds: Planet 9 | yes (prior art) | Section 3.6. |

### 3.6 Prior art they build on

| Item | URL | What it is (from the page itself) |
|---|---|---|
| WiseView | <http://byw.tools/wiseview>, code <https://github.com/backyardworlds/wiseview> (last push Sep 2021) | Browser blink tool for WISE/NEOWISE. Its control panel shows: RA/Dec and field of view, W1/W2 bands, blink interval, sliding time window, difference imaging, shift-and-add with a proper motion, a Gaia DR3 overlay, and a synthetic-object injector. Several entries copy this control set. |
| Backyard Worlds: Planet 9 | <http://backyardworlds.org/>, <https://www.zooniverse.org/projects/marckuchner/backyard-worlds-planet-9> | The Zooniverse citizen-science project cited by the challenge as the precedent for blinking by volunteers. |
| IRSA SPHEREx services | <https://irsa.ipac.caltech.edu/Missions/spherex.html> | SIA/TAP search, cutout tool, public S3 bucket; DR1 and QR2/QR3. Nearly every entry uses these. |
| IRSA tutorial notebooks | <https://caltech-ipac.github.io/irsa-tutorials/spherex/> | Python access examples cited by many READMEs. |
| Services reused across entries | n/a | IMCCE SkyBoT, JPL Horizons and SB Identification, Gaia DR3 (ESA archive, IRSA or MAST), CatWISE2020/AllWISE, SIMBAD/Sesame, Aladin Lite, Astropy/Photutils. |

### 3.7 Seen in search but not opened in detail

These appeared in the GitHub results with a description suggesting a challenge entry, but I
only saw the description or a short README, so no features are recorded:
`sancryption/spherex-change-lens` (README says scaffolding stage), `Adii1504/spherex-sky-investigator`,
`NihalShore/Open-sky-benchmark`, `Alijewa25/SPHEREx-EYE-NASA-2026`, `YosefGul/spherex-blink`,
`FearmessOp/blackhole-spherex` (demo 200), `HellFireInfernoStorm/space-monkeys` (README says
mock data by default), `Sammieblz/khonsu`, `catagfx/SPHEREx_Sky` (web and VR),
`WolfShaddows/VIA-SPHEREx-Mission-Explorer`, `ProgrammerJibon/NasaAppChallenge2026ChronoSpatial`,
`tnaverttrpg-ux/Nasa-Space-App-SphereX`, `M-Arham07/spherex-blink`, `muhammadmuhtasim/novochar`
(demo 200; README mentions simulated placeholder telemetry), `kisakosemedya/spherex-blink`,
`zohaiblazuli/noctilith`, `sumit7194/planetes-spherex`, `cafe2913/dokdo-gull`,
`KTapas27/spherex-blink-hunters`, `tya30122009/quickx`, `Yancovert/spherex-photometry`,
`themilan1337/spherex-flag-checker`, and roughly 150 more. Thirty-nine repositories had no
README at all. Could not open: `spherex-lens.fly.dev` (no connection), `skyshift.web.app`
(404), the Streamlit demo (login redirect for my client).

---

## 4. Conclusions

### 4.1 The five strongest competitors

Ranked by how well the public material covers the five judging criteria.

1. **ZENITH LABS ParallaX.** Covers every objective and all eight considerations with a
   published mapping table, runs for any coordinate with no server, has a method no one
   else has (chromatic template), publishes a false-alarm ledger including where its own
   method loses, recovers Europa and Pluto against Horizons, measures both variable stars,
   and ships deck, paper, report and user guide. Same name as this project.
2. **Driftnet.** The strongest "Planet X" story: a real survey with 571 catalogued movers,
   orbits with uncertainty, composition spectra, a detection-limit page built from 23,400
   injections and a measured false-candidate rate, in a polished public site. Weakness:
   no user-entered coordinates and no stellar movers.
3. **Muninn.** Live, good-looking, any coordinate, catalogue identification, spectra, a
   named blind slow-mover mode (*Hunter X*) and a quantified statement of how far SPHEREx
   is from seeing Planet Nine. Weakness: no completeness or false-alarm numbers seen.
4. **SPHEREx Blink 3.0** (if a 4.0 is submitted). The broadest feature set, including the
   only Earth-parallax distance search and per-source dossiers with provenance. Weakness
   by its own README: public demo is synthetic, and it says it is not a submission.
5. **EpochLoom.** Live any-coordinate tool with tours, mover finding, PM values with
   errors that match catalogues, calibrated-against-IRSA spectra and shareable URLs.

Next tier: **spherex-lens** (best validation statistics found, but no reachable demo and no
blink viewer described), **Nakshatra CHRONOS** (ranked explanations and self-falsification,
mostly on simulated sky), **Radians**, **SPHEREx Time-Lapse**, **SpectraShift**.

### 4.2 Features competitors have that PARALLAX, as described in the brief, lacks

"Not in the brief" items should be checked against the build before acting.

| # | Feature | Who has it | PARALLAX per the brief |
|---|---|---|---|
| 1 | Known solar-system object check on every candidate (SkyBoT, JPL SB Ident, Horizons from SPHEREx) | ZENITH, Driftnet, Muninn, Blink 3.0, Time-Lapse, Radians, spherex-lens, GhostShift | Not in the brief. Essential for a blind search: asteroids are the dominant real movers. |
| 2 | Completeness grid from injections into **real** frames, and a false-candidate rate per field or per deg2 for the **blind** search | Driftnet, spherex-lens, ZENITH, Radians, CHRONOS | Brief has synthetic injection tests and 33 controls with 0 false positives for the targeted pipeline; nothing yet for blind mode. |
| 3 | Recovery of a known mover found blind, compared with an ephemeris or catalogue | ZENITH (Europa, Pluto), Time-Lapse (Pluto), Muninn (Atala), Blink 3.0 (Barnard, Eps Indi B, Makemake) | Not in the brief for blind mode. |
| 4 | A distance or orbit estimate for a slow mover | Driftnet (orbit clones), Blink 3.0 (Earth-parallax fit), Muninn (rate to distance) | Brief has PM + parallax fits; a distance read-out in Planet X mode is not mentioned. |
| 5 | A quantified answer to "could SPHEREx see Planet Nine?" | Muninn, Driftnet, Blink 3.0, ZENITH, GhostShift | Not in the brief. |
| 6 | Variable-star measurements for RW Aurigae and R Draconis (two of the five test targets) | ZENITH (magnitude change with control star; period fit), EpochLoom (ratio view), Radians and Time-Lapse (light curves) | Not in the brief, which is mover-centred. |
| 7 | Coordinates in the URL plus embed mode and iframe snippet (consideration 6) | ZENITH, EpochLoom, Muninn, Slowsky, others | Not in the brief. |
| 8 | User-chosen field of view with transfer cost shown (consideration 4) | ZENITH, Radians, others | Not in the brief. |
| 9 | Per-detector stacks and an explicit all-six-detectors view (consideration 2) | ZENITH, Radians, EpochLoom, Blink 3.0 | Brief lists "stack"; per-detector not mentioned. |
| 10 | Contamination-flag overlay and on-image Gaia/WISE overlays at the frame date (considerations 5, 7) | ZENITH, Muninn, Radians, Slowsky | Not in the brief (the public README mentions flags and Gaia/AllWISE for saved targets). |
| 11 | Wavelength-aware differencing (chromatic template, or matched-wavelength pairs) | ZENITH, CHRONOS, Radians, SkyShift variants | Brief lists difference and per-pixel wavelength; matching not mentioned. |
| 12 | Serverless any-coordinate path that cannot cold-start | ZENITH, Time-Lapse | The public README says the hosted viewer can take about a minute to wake. |
| 13 | Survey-scale results: a browsable catalogue of what the search found and a map of where it looked and found nothing | Driftnet | Not in the brief. |
| 14 | Onboarding for non-experts: guided tour, glossary, second language, accessibility notes | EpochLoom, spherex-lens, Radians (EN/TR), Muninn (EN/RU), CHRONOS (EN/Bangla), Driftnet | Not in the brief. |
| 15 | Citizen-science loop: votes, game rounds, blind repeats | spherex-lens, Mahadi5577 SkyShift, BlinkSky, CHRONOS | Not in the brief. |
| 16 | Plain-language AI explanation constrained to measured numbers | Driftnet, EpochLoom, AetherX | Not in the brief. |
| 17 | Packaged deliverables: 7-slide deck, 30-second video, paper or report PDF, user guide, checklist table | ZENITH, CHRONOS, Muninn | Not in the brief. |
| 18 | Standards exports: ADES draft, VOTable, cone search | Driftnet, spherex-lens | Brief has JSON/CSV dossiers. |

What PARALLAX has that I did not find in any README I opened: **a prediction frozen in a
time-stamped commit before the sealed observation was downloaded**; a parallax fit reported
alongside proper motion (ZENITH and Blink 3.0 both say theirs is unreliable or limited);
a motion-corrected spectrum matched to brown-dwarf templates; and a negative-control set
as large as 33 stars. Closest equivalents: ZENITH's independent re-run review,
spherex-lens's held-out ML fields and CI gate, CHRONOS's hash seals.

### 4.3 Five concrete things, each feasible in a few hours

1. **Add a known-object veto and one blind ground-truth recovery to Planet X mode (2-3 h).**
   For every blind candidate, query IMCCE SkyBoT (or JPL SB Identification) at each
   exposure time and label it known asteroid/comet, unmatched, or likely artefact. Then
   show one known mover recovered blind and compared with its ephemeris or catalogue
   motion (an asteroid or Pluto field, as ZENITH and Time-Lapse do, or a cold brown dwarf
   not used in tuning). Without this, the first question a judge who has seen Driftnet or
   ZENITH will ask is how many candidates are just asteroids.

2. **Publish a one-page "Limits" scorecard for the blind search on real frames (3-4 h).**
   Reuse the injection harness: plant sources in real SPHEREx frames over a small grid of
   brightness and motion rate, report recovery with intervals, and run the blind search
   on the 33 control fields plus some empty fields to give false candidates per field.
   Add one sentence on Planet Nine detectability. Lead with the regime PARALLAX owns:
   Driftnet reports 0% recovery at or below 1 arcsec per hour because it links over about
   1.5 days, whereas PARALLAX fits proper motion and parallax across six-month passes, so
   show the distance with uncertainty that the parallax fit implies for each candidate.

3. **Close the literal checklist and show it (2-4 h).** Add whatever is missing from:
   `?ra=&dec=&fov=` deep links with an embed mode and copyable iframe; a field-of-view
   selector; per-detector stack; flag overlay; Gaia/WISE overlay at the frame date; a
   one-command note for picking up a new data release. Make RW Aurigae and R Draconis
   useful: a light curve in a fixed wavelength window with a comparison star, since they
   are variables and a mover pipeline says nothing about them. Then put a table in the
   README and the app mapping each objective and each of the eight considerations to a
   feature and a link, with one-click links for all five targets (ZENITH has this table).

4. **Make pre-registration the headline, verifiable in under a minute, and sync the public
   repo (1-2 h).** Add a "Verify" panel showing the frozen commit hash and timestamp, the
   sealed observation ID, predicted against measured position, and the tolerance, each
   linked. Push the current build so the public README matches the product; at retrieval it
   described an earlier, weaker state. Freeze one new prediction before running Planet X
   mode on a held-out field and report the outcome whichever way it goes. This is the one
   scientific claim no other opened entry makes, and it maps directly to the Best Use of
   Science definition.

5. **Ship the presentation and reliability pack (2-3 h).** A 30-second video or a deck of
   at most seven slides (over-limit entries are ineligible); a 60-second guided tour and a
   short glossary for non-astronomers; a static fallback with prebuilt packs for the five
   targets and one Planet X demo field so judging never waits on a cold-start server or on
   IRSA; a complete References list (including the ZENITH LABS sky index and FITS/WCS
   modules the public README says are reused) and the SI disclosure; and a distinctive
   subtitle, because at least four other entries are also called Parallax.

### 4.4 Where PARALLAX stands against the five criteria (my reading of the evidence)

| Criterion | Strongest rivals | PARALLAX's position |
|---|---|---|
| Impact | Driftnet (public catalogue), EpochLoom and Muninn (anyone, any coordinate) | Needs the non-expert path in recommendation 5. |
| Creativity | ZENITH (chromatic template), CHRONOS (falsification engine), Driftnet (orbits from hours-long arcs) | Pre-registered predictions and template-matched moving-object spectra are distinctive; say so first. |
| Validity | spherex-lens, Driftnet, ZENITH (published rates and failures) | Strong for targeted measurements; blind mode needs recommendations 1 and 2. |
| Relevance | ZENITH (checklist table, all five targets including variables) | Mover-centred; recommendation 3 closes the gap. |
| Presentation | ZENITH, Driftnet, Muninn (decks, talks, polished landings) | Recommendation 5. |

---

## 5. Sources

- Challenge: <https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/>
  (Details, Resources and Teams tabs)
- Judging & Awards Guide: <https://www.spaceappschallenge.org/resources/judging-awards-guide/>
- Awards overview: <https://www.spaceappschallenge.org/awards/>
- Project Submission Guide: <https://www.spaceappschallenge.org/resources/project-submission-guide/>
- IRSA SPHEREx: <https://irsa.ipac.caltech.edu/Missions/spherex.html>
- WiseView: <http://byw.tools/wiseview>, <https://github.com/backyardworlds/wiseview>
- Backyard Worlds: <http://backyardworlds.org/>,
  <https://www.zooniverse.org/projects/marckuchner/backyard-worlds-planet-9>
- Competitor repositories and demo sites: URLs given inline in section 3. READMEs were read
  from each repository's default branch on 14 Nov 2026; they change quickly during the
  hackathon, so re-check anything decisive before relying on it.
