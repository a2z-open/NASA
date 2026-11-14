# Judging notes: how PARALLAX will be scored, and where it falls short

Retrieved Sat 14 Nov 2026 from the live official pages. All are the **2026 editions**, so no older year was needed.
Wording is closely paraphrased; one short verbatim quote is marked. Nothing was submitted, posted or sent, and no team
details went into any request. PARALLAX ratings come from the repo files as they stand today (branch `parallax-build`).

**Sources.** Each claim carries one of these tags.
- [C] Challenge page (Details and Resources tabs): <https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/>
- [J] Judging & Awards Guide: <https://www.spaceappschallenge.org/resources/judging-awards-guide/>
- [S] Project Submission Guide: <https://www.spaceappschallenge.org/resources/project-submission-guide/>
- [A] Awards overview: <https://www.spaceappschallenge.org/awards/> · [F] Participant FAQs: <https://www.spaceappschallenge.org/resources/participant-faqs/>
- [T] Participant Terms & Conditions: <https://www.spaceappschallenge.org/legal/> · [H] 2026 hackathon page: <https://www.spaceappschallenge.org/2026/>
- [L] Seattle local event page: <https://www.spaceappschallenge.org/2026/local-events/seattle/>
- [K] Seattle "Know Before You Go" (organisers' doc, updated 13 Nov 2026, linked from [L]): <https://docs.google.com/document/d/1_61zSn1_bYadMdAel59N7W0TSaQiZ8ZxkcHdcC_VKOQ/edit?tab=t.0>
- [W] Seattle organisers' site: <https://spaceappsseattle.org/> · [WA] its awards page: <https://spaceappsseattle.org/awards-and-winners/>

## 1. What the challenge asks [C]

**Required (the Objectives).**
- [ ] A public-facing web tool that shows SPHEREx sky images and makes it easy for anyone to see quickly how they change over time.
- [ ] The user enters the coordinates of a patch of sky (Right Ascension and declination).
- [ ] The tool shows a series of images of that patch like a short video, so moving objects are easy to spot.
- [ ] Test it on Barnard's Star, Epsilon Indi B, WISE 0855 (RA 08h55m10.831s, Dec −7d14m42.53s), RW Aurigae and R Draconis.

**Encouraged (optional considerations; the page says they are not required).**
- [ ] 1. Easy to update with the latest data releases, because new data arrives fast.
- [ ] 2. Show the 102 bands creatively, for example add together the data from each of the six detector arrays to raise signal-to-noise. Extra credit for spectra made on the fly.
- [ ] 3. Let users add together or subtract images taken at different times.
- [ ] 4. Let users choose the field of view (larger fields follow faster movers but take longer to transfer).
- [ ] 5. Offer overlays from other telescopes, such as Gaia or WISE.
- [ ] 6. Accept coordinates in the URL, so the tool can be embedded in other sites.
- [ ] 7. Show metadata such as contamination flags.
- [ ] 8. Look at existing public tools: Astropy for handling data, Aladin (CDS) for display.

The background text names the movers it has in mind: comets, asteroids, stars, brown dwarfs and new planets. Resources
tab: IRSA SPHEREx, IRSA tutorial notebooks, WiseView (offered as a model), Gaia DR3; partner resources from the Canadian
Space Agency (NEOSSat, CADC). The challenge is tagged Advanced.

## 2. How entries are judged

**Five criteria, each scored 1 to 5, at every level of judging [J].**

| Criterion | Definition | What earns a 5 |
|---|---|---|
| Impact | Size of the problem, quality and quantity of the effect, how many people it inspires or helps. | A significant problem, wide reach, a large audience, quality far above expectations. |
| Creativity | Originality: a new concept, or a meaningful improvement on existing ideas. | An approach not tried before that challenges the usual methods. |
| Validity | Grounded in science; technically feasible; does what it sets out to do; could work in the real world. Completeness and user-friendliness count here. | Scientifically sound, fully developed, ready for real use, highly usable. |
| Relevance | Fully and directly addresses the chosen challenge; NASA data is a core part, not an add-on. | Deep engagement with the challenge; NASA data is integral and well executed. |
| Presentation | How clearly the team conveys the challenge, the solution and why it matters. Judges use the demo **and** the full project. | Structured, engaging, polished storytelling. |

The guide tells teams to give Presentation the same attention as the other four [J]. Seattle's own summary moves
completeness, feasibility and usability under Relevance [K], so local judges may score "is it finished and usable" twice.

**Process [J].** Local judges pick Global Nominees (announced 3 Dec 2026). Global judges pick Finalists and Honorable
Mentions (17 Dec). An executive committee of NASA and partner agencies picks ten Global Winners (26 Jan 2027). Local
awards are optional and separate. Most of the judges' evaluation rests on the project page; the demo mainly lifts Presentation [S].

**The ten Global Awards [J][A].** Best Use of Science: best and most valid use of the scientific method. Best Use of
Data: best makes space data accessible or uses it in a unique way. Best Use of Technology: most innovative use of
technology. Galactic Impact: most potential to improve life on Earth or in the universe. Best Mission Concept: most
plausible concept and design. Most Inspirational: captures the judges' hearts. Best Storytelling: most creatively
communicates the potential of open data. Global Connection: best connects people around the world through technology.
Art & Technology: best combines technical and creative skills. Local Impact: greatest potential for the team's local community.

## 3. Submission requirements

- **Project page fields [S]:** Project Name · High-Level Project Summary (what, how it meets the challenge, why it matters) · Link to Project Demo · Link to Final Project · Detailed Project Description (what it does, how, benefits, goals, tools) · Use of Super Intelligence (SI) · NASA Data · Space Agency Partner Data and Other References. All required fields, all in English.
- **Demo [S][J]:** a video of 30 seconds or less, **or** at most 7 slides including title and intro. Over the limit means not eligible for Global Judging. Host it elsewhere with a public link: no password, permission or sign-up. Videos and documents cannot be uploaded to the site (images up to 10 MB can).
- **Slides must state** the team name, the names of the team members and the chosen challenge, and should show the project, the user experience and how NASA data makes it possible [S]. Suggested video order: who you are, the challenge, title and tagline, how it works with NASA data, then the future [S].
- **Final project link [S]:** public, tested in a private window. For a new website, an optional FortiGuard web-filter classification helps judges reach it.
- **Two tick-boxes [J]:** the Terms; and that the work is original, with all outside code, text and images listed in References.
- **NASA data [S]:** at least one NASA dataset or resource, or no Global Award. Partner-agency data is strongly encouraged; ESA is a 2026 partner.
- **AI ("Super Intelligence") [S][F]:** allowed, and its use must be described. It should not supply the idea for solving the challenge. No NASA branding in generated content. AI images and video need a visible watermark; AI audio, code and data must be acknowledged in descriptive text and metadata. Judges do not see the SI answer, but they see AI markers in the project and judge originality, intent and execution from them.
- **Licence [T]:** original content must be free of restrictions or under an OSI-approved licence; with none stated, NASA uses Apache 2.0. Third-party material must be open, its licence named, and every source cited; awards can be withdrawn for missing citations. Seattle adds: "Your project must be open source to qualify" [K].
- **Deadlines, Pacific time [S][L]:** submission opens Sat 14 Nov 9:00 a.m. and closes Sun 15 Nov 11:59 p.m. Resubmitting is allowed; the last saved version is judged; late means not judged.
- **Eligibility [J][F]:** an official challenge; every member registered at the same local event, not waitlisted, and on the team page; at most six; no new members after the deadline. Teams may not start work on the challenge before the hackathon [F].

## 4. Seattle local event

- **Where and who [L][W]:** F5 Tower, 801 5th Ave, in person, 386 registered (limit 400). Run by Space Northwest.
- **Format [K]:** each team presents for **4 minutes** (slides, video and live demo allowed), then **1 minute** of judges' questions. Judges may ask for more during deliberation. Talks are recorded for YouTube.
- **Schedule, PT [K]:** Sat 7:00 p.m. mandatory pitch lecture; venue closes 8:30 p.m. (hacking elsewhere overnight is allowed). Sun 10:30 a.m. mandatory pitch practice; project demos due by 1 p.m.; 1:00 p.m. mandatory tech check; 2:15 p.m. presentations; 4:30 deliberation; 5:00 awards; submit by 11:59 p.m. [L] shows slightly earlier times (practice 10:00, pitches 1:30); [K] is newer.
- **Judges [W]:** three, from Juno Propulsion (rocket propulsion founder), Blue Origin (guidance, navigation and control) and The Exploration Company (sales and strategy, bioastronautics background). None is listed as an astronomer.
- **Local awards [K]:** at least four, one per project, from Best Use of Data, Best Use of Technology, Best Mission Concept, Most Inspirational, Art & Technology, Local Impact, Best Storytelling. There is no local Best Use of Science. At least one project goes to global judging, with or without a local award; Seattle sent 2 in 2025 and 2024, 1 in 2023 and 2022 [WA].
- **Sponsors [W]:** F5 (Galactic sponsor); Integrate, TEKsystems, Parsimoni, CisLunar Industries and First Citizens Innovation Bank appear in the Orbital sponsor row. No sponsor prize or sponsor priority is published. Prizes mentioned: a raffle [K], and a possible Kennedy Space Center tour for global finalists [W], which the NASA pages do not confirm.

## 5. Competing projects not in `docs/COMPETITORS.md`

From each README on 14 Nov; none was tested. A GitHub search found about 135 more repositories pushed on 13–14 Nov.
- **Chronosphere**, <https://github.com/muhammetmucahitsoylu/chronosphere>: Aladin all-sky map, click anything to play it, a catalogue-free check of every star in the field, spectra, a ten-step guided tour.
- **BLINKSCOPE**, <https://github.com/asherbnsl/spherex-sky-eye>: per-detector stacks, a 2010 WISE frame for a 15-year blink, wing photometry for saturated stars, flag share per exposure, demo PDF.
- **SPHEREx Blink (Skill-Issue)**, <https://github.com/ArnavCodez/NASA-Space-Challenge>: name or coordinate search, per-visit and difference views, hosted pitch deck.
- **SkyShift (ngdev)**, <https://github.com/ayoubna99/spherex-skyshift>: flipbook plus temperatures of satellites from streaks seen by two cameras at once.
- **Wanderer**, <https://github.com/fromearth03/wanderer>: JPL-predicted asteroids drawn on each frame, a mover finder, tracks comet 3I/ATLAS.
- **SPHEREx Agent Hunt**, <https://github.com/mrfentmen/spherex-agent-hunt>: an agent pipeline whose gates include predicting a held-out epoch and re-running on scrambled data.
- **SPHEREx Sky Flipbook**, <https://github.com/CandiedOutlaw763/spherex-sky-flipbook>: any-coordinate movie, spectra, brightness histories, Gaia and WISE overlays, user guide.
- **InfraSphere**, <https://github.com/Radit-Raian/InfraSphere>: a planetarium view of the SPHEREx sky with SIMBAD labels and a blink inspector per tile.
- **Blinky**, <https://github.com/irfadox/blinky>: offline blink and spectrum viewer that also loads CSA NEOSSat fields (partner data).

## 6. Gap table: PARALLAX today

| Item | Rating | Where it stands | Most valuable improvement |
|---|---|---|---|
| **Impact** | adequate | Anyone-can-check story is clear, but nobody outside the team can use it, and there is no first-run guide (only tooltips in `Term.tsx`). | After deploying, add a three-step "start here" path on Home and say who uses it next (volunteers, the 2027 forecast check). |
| **Creativity** | strong | Predictions locked before the data, graded blind search, ten-year catalogue check. Agent Hunt has a weaker held-out gate. | Push the lock commits so the timestamps are public before the pitch. |
| **Validity** | adequate | Science is strong (33 controls, 0 false alarms, 13 of 19 found blind). Readiness is not: live queries take about 80 s, about 1 cutout in 5 fails, 3 of 5 targets saturate, 5 of 12 moving injections found. | Deploy with the five targets, hunt and proofs served from baked-in data, so the judged path never waits on IRSA. |
| **Relevance** | adequate | Every objective and 7 of 8 considerations exist locally, and NASA data is the core. The word "public" is unmet. | Deploy and put the URL in the Final Project field. |
| **Presentation** | weak | No video, no exported deck, no project page text. `/deck` slide 1 lacks the team name and members' names. The public repo README shows an older build. | Fix slide 1, export the PDF, host it publicly, paste SUBMISSION.md into the form. |
| Public web tool | weak | "Not deployed and not submitted" (README). | Deploy one container (docs/DEPLOYMENT.md). |
| Enter RA and Dec | strong | Names, decimal and sexagesimal input. | None needed. |
| Plays like a video | adequate | Instant for the five targets; other positions wait about 80 s and are capped at 48 cutouts. | Show frames as they arrive, or pre-cache a dozen showcase fields. |
| Five test targets | adequate | Epsilon Indi B and WISE 0855 fully measured; variables via the halo (experimental). Barnard's Star, the first one named, gets no motion while rivals quote about 10.2″/yr. | Fit Barnard's motion from the halo centroid and compare with Gaia; failing that, draw Gaia's predicted path on the blink. |
| Movers the text names | adequate | Stars and brown dwarfs only. The hunt rejects asteroids by design and no comet or asteroid is shown. | One showcase field where a known asteroid crosses, labelled from SkyBoT (`pipeline/solarsystem.py`). |
| 1 New releases | strong | One `RELEASES` table; DR1 and QR3 both searched. | None needed. |
| 2 Bands, detectors, spectra | strong | Wavelength on every frame, detector filter, Add mode, click-for-spectrum. | A one-click "stack each of the six detectors" row. |
| 3 Add and subtract | strong | Both, with a wavelength-mismatch warning. | None needed. |
| 4 Field of view | strong | Width box, 2′ to 30′. | Show the expected download time next to it. |
| 5 Overlays | strong | Gaia moved to each frame's date; CatWISE positions. | Add a WISE image frame for a 15-year blink (BLINKSCOPE has one). |
| 6 URL and embed | adequate | `?ra=&dec=&fov=` and `embed=1` work, locally only; no copyable iframe snippet. | Add a "Copy embed code" button once a public URL exists. |
| 7 Flags and metadata | adequate | Flags at the centre and per measurement, release, SHA-256. Flagged pixels are not drawn on the image. | A toggle that paints flagged pixels over the frame. |
| 8 Astropy, Aladin | adequate | Astropy throughout; Aladin unused (optional). | Add "open in Aladin Lite / WiseView" links. |
| Partner data [S] | adequate | ESA Gaia DR3 is used; CSA resources are not. | Name ESA Gaia in the partner-data field. |
| AI disclosure [S] | adequate | AI_USAGE.md is detailed, but says AI wrote most of the code and helped plan; human-review cells are TODO. | Write, in the team's words, which ideas and decisions were human. |
| Licence and citations [T] | adequate | MIT and notices are in order locally. The public README credits reused ZENITH LABS code. | Cite it in References, or confirm it is gone and update the public repo. |
| Start-time rule [F] | weak | Commit `dbec275` is Fri 13 Nov 22:25 PT and the build began 00:19 Sat, before the 9:00 a.m. opening. | Get the Seattle lead's written OK and keep it with DEVELOPMENT_HISTORY.md. |

## Could not confirm

- How many Global Nominees Seattle may send in 2026 (the page field is empty; [K] says at least one).
- Whether local judges fill in the 1-to-5 rubric or decide by discussion, and what exactly must be ready when [K] says demos are due by 1 p.m. on Sunday.
- Which schedule is right where [L] and [K] differ; follow the organisers on the day.
- Sponsor tiers beyond F5 and Parsimoni are read from the page layout; no sponsor prizes or priorities were found.
- That organisers approved the work done before Saturday 9:00 a.m.; no written record was seen.
- The competitor features in section 5 (README claims only) and the team count on the challenge page.
- What the "Global Offers" from Google, Microsoft, GoDaddy, Miro and Meteomatics include [H]; they may cover hosting.
- What past winning demos look like: the 2025 Global Winners page showed no winner list when fetched.
