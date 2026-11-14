# Demo scripts: drafts built only on what PARALLAX actually does

Every number below is a real result (VALIDATION.md, docs/HUNT_REPORT.md), filled in by `python -m validation.fill_docs`.
Re-check them before recording if anything is rebuilt.

## A. 30-second demo video

| Time | Screen (record the real app) | Caption |
|---|---|---|
| 0–5 s | Home page. The round window blinks two real images of Epsilon Indi B; the ring jumps. | "This star moved. NASA's SPHEREx saw it." |
| 5–11 s | Type a name, press Search. Images play; switch to Blink, then Subtract. | "Pick any patch of sky. Watch it change." |
| 11–17 s | Click the dot. The path, 4.6″ a year, the spectrum. | "Click a dot: its motion, distance and spectrum." |
| 17–23 s | Proof page: press "Open them". PASS, 0.072″. | "We locked our prediction before the images existed. It landed 0.07″ away." |
| 23–28 s | Planet X hunt: the tiles, then open one field and let it blink. | "A blind search found 13 of 19 known movers by itself." |
| 28–30 s | Home page title. | "PARALLAX. Find what moves. Then prove it." |

Use real recordings only. No mock-ups, no NASA logos.

## A2. Seven slides instead of a video

Open `/deck` in the app. Arrow keys or the buttons move between slides, and every number is live. Print to PDF from the
browser to upload it (landscape, background graphics on).

1. Title, with the real blink.
2. What we built, with the live viewer embedded.
3. Proof 1: the locked prediction.
4. Proof 2: the Planet X hunt.
5. The coldest brown dwarf, and the two variable stars.
6. Honest by design: what it cannot do.
7. Why it matters.

## B. Four-minute Seattle presentation

**0:00–0:25 Hook.** "In 1930 Pluto was found because one dot moved between two photographs. NASA's SPHEREx now
photographs the whole sky in 102 infrared colours, again and again. NASA asked for a tool that lets anyone blink it."

**0:25–1:10 The tool.** Home page. Type "Epsilon Indi B". *Real images from NASA's archive, lined up and dated.* Play,
then Blink: "Stars stay put. That one jumps." Switch on "What WISE saw around 2015". Show the address bar: "Any patch of
sky is a link." Type other coordinates to show it is not canned (only if the network was tested).

**1:10–1:50 Measure.** Click the dot. "4.6 arcseconds a year, and 12 light-years away, from SPHEREx alone." Show the
spectrum: "It follows the star as it moves. Its light matches a brown dwarf." Then WISE 0855: "The coldest brown dwarf
known. Nothing at short wavelengths. At 4 to 5 microns, there it is."

**1:50–2:35 Proof 1: predict, then check.** Proof page. "Before we downloaded SPHEREx's newest images of this star, we
locked a prediction." Ask the room: stays put, or keeps moving? Press "Open them". "0.07 arcseconds. And we have locked
new predictions for 2027, for images NASA has not taken yet."

**2:35–3:20 Proof 2: the Planet X hunt.** Hunt page. "We gave the search 25 patches of sky and nothing
else. It tested 5,195 sources. It found 13 of 19 known movers by itself, and
0 it could not explain." Open a field and let it blink. "It also raised false alarms. One looked
perfect: 13 sigma. Then we checked where Gaia saw that star in 2016. It had not moved. So now every mover must agree
with the sky of ten years ago."

**3:20–3:45 The variable stars.** "Two of NASA's five targets are variable stars, and both are too bright: they saturate
the camera. So we measured the ring of light around them. R Draconis faded by 42 percent, RW Aurigae by 36. Barnard's
Star, our control, did not change."

**3:45–4:00 Close.** "We did not find Planet X. We built the tool that would let you believe it if someone does. Find
what moves. Then prove it."

## C. Backup demo (if Wi-Fi or the archive fails)

1. Run from the laptop: `uvicorn api.app:app`. The five targets, the hunt, the proofs and `/deck` need no network.
2. If the laptop fails, use a screen recording of the same sequence. TEAM TODO: record it.
3. Do not type new coordinates on stage unless the venue network has been tested: a live query takes about 80 s and
   about one cutout in five can fail when the archive is busy.

## D. Likely judge questions (short answers)

- **Did you find Planet X?** No, and we say so. 0 movers remain unexplained after the checks. Planet
  Nine itself would move by arcminutes between SPHEREx visits and is expected to be too faint for one visit. What
  SPHEREx can find today is a cold neighbour like WISE 0855, and we showed the search finds that one blind.
- **How do you know the blind search works?** Known movers were hidden in the fields. It found 13 of
  19. We also hid 16 fake cold sources in a blank field: it found the ones bright and fast enough, and called
  none of the still ones movers.
- **False alarms?** 8 sources passed the 5σ motion test and were then rejected: by colour, by dropping
  one visit, by sitting next to a saturated star, or by being in the same place in Gaia or WISE ten years ago. Separately,
  0 of 33 still stars were flagged.
- **How is this different from Blink 3.0, Driftnet or WiseView?** They are good viewers and some search for movers.
  We don't claim those pieces. Ours checks itself: locked predictions, a graded blind search, the ten-year check.
- **Why trust the locked prediction?** The split was fixed first, the prediction was hashed and committed before the
  download, the same code measured both, and the pass rule was written in advance. Git times are self-reported until the
  repository is pushed.
- **Different wavelengths?** Each pixel's wavelength comes from the image's own spectral calibration. Brightness is
  compared only at matched wavelength, and the viewer warns when two frames differ.
- **How can you measure a saturated star?** Not its core. The light it scatters a few pixels away is not saturated and,
  at a fixed wavelength, is proportional to the star's brightness. It is experimental, and the control star stays flat.
- **What does AI do?** It helped write the code and documents. Nothing in the app is AI: every number comes from fixed
  code (AI_USAGE.md).
- **Does it scale?** New data releases are one line of configuration. Searching the whole sky would need the bulk
  archive and far more computing, which we do not claim.
