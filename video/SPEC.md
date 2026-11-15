# PARALLAX demo video: design spec and storyboard

Skills used: product-feature-video (footage-driven pipeline), video-shotcraft (autonomous mode: pipeline, aesthetic rules),
demo-video (narrative patterns, gotchas), Remotion skills (create, markup, render).

## Brief (from the team, 15 Nov 2026)

- Space Apps Seattle judging. Whole presentation 4:00, then 1:00 of Q&A. Organisers' structure:
  Person + Problem 35 s, Solution + Proof 150 s, Possibility 40 s, Close 15 s.
- Judging criteria to cover: Impact, Creativity, Validity, Relevance (NASA data), Presentation.
- Story must answer WHO has a problem, WHAT we built, WHY it matters.
- Real PARALLAX recordings and real NASA data; working product and evidence before decoration.
- Must not repeat what presenters say live. Needs a reliable backup recording for the 1 PM tech check.

## Decisions (made autonomously, with reasons)

| Question | Decision | Why |
|---|---|---|
| Length | 7,200 frames = 4:00 at 30 fps, 1920 × 1080 | Matches the 4-minute slot exactly; the same file is the tech-check backup. |
| Structure | 0:00–0:35 Person + Problem · 0:35–3:05 Solution + Proof · 3:05–3:45 Possibility · 3:45–4:00 Close | The organisers' exact split. |
| Voice | No voiceover. Short on-screen captions only. | Presenters speak live; captions carry the facts, presenters carry the story (PRESENTER_SCRIPT.md), so nothing is said twice. |
| Music | A quiet ambient score composed in code (zero licence risk), plus a no-music version | Must sit under live speech; the shotcraft BGM set is house/hip-hop and would fight the speakers. Deliberate departure from aesthetic rule S1 (strong-beat BGM), recorded here. |
| Footage | Real Playwright captures of the running app (http://127.0.0.1:8000) and full-page 2x screenshots for camera moves | Q1 and product-feature-video's core rule: real footage first. No mock-ups of our own pages. |
| Hero moment | Makemake found blind: 52.72 AU, NASA JPL 52.72 AU | Validity in one number a judge can remember and check. |
| Team names | Not shown (not provided) | Never invent people. The close says PARALLAX, NASA SPHEREx, Space Apps 2026 Seattle. |
| Data | Only public NASA/ESA archive data and our own sealed results | No personal or private data appears. |

## Visual tokens (taken from web/src/theme.css)

- Black #000, surfaces #0a0a0b / #161617, text #f5f5f7, secondary #a1a1a6, tertiary #86868b, hairlines rgba(255,255,255,0.1–0.2).
- Type: Inter (stands in for SF Pro) for reading and display, weight 600 headings with tight tracking; Barlow 600 capitals,
  letter-spacing 0.2em, for labels (as on the site).
- No colour. Dashed lines are models or predictions; solid lines are measurements (the site's rule).
- Motion personality: "professional trust", calm. Entrances ~21–30 f, bezier(0.16, 1, 0.3, 1), no overshoot on fades;
  spring damping 200 for moves. Holds ≥ 1 s on every key number and on the wordmark (R1). No camera shake (Q3).
- Captions: ≥ 60 px for lines meant to be read, ≥ 34 px for supporting lines (Q11).

## Feature → shot map (one technique leads once, P4)

| Feature (judging criterion) | Shot | Technique |
|---|---|---|
| SPHEREx whole sky, 102 colours (Relevance) | S1 | Real sky-map recording of the 102-colour sweep |
| The problem: hundreds of separate images (Impact) | S2 | Real SPHEREx frames tiling in, accelerating like dealt cards (R2), count rolls up |
| Enter RA/Dec, images play like a video (Relevance) | S5 | Real Explore recording, NASA's checklist ticking on the left |
| Blink / subtract / add / 102 colours / overlays / flags | S5b | Real Explore recording, zoom cues |
| NASA's five test targets (Validity) | S6 | Real Proof-page scorecard, slow 2.5D pan |
| Prediction locked before looking (Validity, Creativity) | S7 | Real Proof-page interaction, number reveal |
| Makemake and Eris found blind (Validity) | S8 (climax) | Real Finds-page orbit, big number pair |
| 102 colours read by machine learning (Creativity) | S9 | Real methane spectra cards |
| 23 telescopes, JWST, archive lookups (Creativity) | S10 | Real sky-map recording: layers, JWST Pillars, other-telescopes panel |
| Honest limits, stacking (Validity) | S11 | Real How-page slider: asteroid appears as photos add up |
| Citizen science (Impact) | S12 | Real Check page and shared sky chunks |
| Explained, forecasts, open (Possibility) | S13 | Real How page, locked forecasts |
| Brand close (Presentation) | S14 | Wordmark, hold |

## Storyboard (timings are targets; final ones follow the real clip lengths)

| # | Time | Shot | Caption (on screen) |
|---|---|---|---|
| S1 | 0:00–0:09 | Sky map, SPHEREx layer sweeping its 102 colours | NASA's SPHEREx maps the whole sky every six months / in 102 infrared colours |
| S2 | 0:09–0:21 | Real SPHEREx images of one star dealt onto the screen, faster and faster; counter | One patch of sky. 446 separate images. / Different dates, colours and detectors |
| S3 | 0:21–0:30 | The images blur; two lines | Astronomers and volunteers hunt for things that move. / Finding one moving dot means lining up hundreds of files. |
| S4 | 0:30–0:35 | PARALLAX wordmark, hold | PARALLAX / Find what moves in the sky. |
| S5 | 0:35–1:00 | Explore: type coordinates → Go → images play; blink | What NASA asked for / checklist ticks |
| S6 | 1:00–1:15 | Proof scorecard, NASA's five targets | Tested on NASA's five targets |
| S7 | 1:15–1:35 | Proof Test 1: guess, open sealed images, result | Predicted before we looked: 0.072″ off |
| S8 | 1:35–2:03 | Finds: Makemake orbit; Eris stacked | Found blind: Makemake 52.72 AU · NASA JPL 52.72 AU |
| S9 | 2:03–2:23 | Methane spectra cards | Reading 102 colours: 59 of 66 methane dwarfs, 0 false alarms |
| S10 | 2:23–2:43 | Sky map: JWST layer at the Pillars; other telescopes at WISE 0855 | 23 telescopes on one map · Hubble 103, JWST 37 at WISE 0855 |
| S11 | 2:43–3:05 | How page: asteroid appears as photos add up; Planet Nine depth | Adding photos: 27 → 53 known asteroids · Planet Nine: still 8× too faint |
| S12 | 3:05–3:25 | Check a candidate; sky chunks | Anyone can check a real candidate in ten seconds |
| S13 | 3:25–3:45 | How we find them; locked forecasts | Every claim comes with its proof · Next test: Makemake, Dec 2026 |
| S14 | 3:45–4:00 | Wordmark close, hold | PARALLAX / Look twice. Find what moves. / Built on NASA SPHEREx · Space Apps 2026, Seattle |
