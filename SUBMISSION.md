# Project submission: DRAFT for team review

> **Do not submit until the team has reviewed and approved this draft.** Fill in every item marked TEAM TODO.
> Check the current official Project Submission Guide in the event portal before submitting.
> Numbers in this file are filled from the result files by `python -m validation.fill_docs`.

**Project title:** PARALLAX. TEAM TODO: at least four other entries use this name (docs/COMPETITORS.md). Decide whether
to keep it, or add a subtitle such as "PARALLAX: find what moves, then prove it".
**Team name:** TEAM TODO. The team may be registered as "Aiges"; confirm the registered name.
**Challenge:** Planet X and SPHEREx (NASA Space Apps Challenge 2026)
**Local event:** Seattle
**Public demo:** TEAM TODO (deploy only after approval; see docs/DEPLOYMENT.md)
**Repository:** TEAM TODO. `github.com/a2z-open/NASA` is public and its README describes an older state; branch
`parallax-build` is local only until approved.
**Demo:** TEAM TODO. Either a 30-second video (DEMO_SCRIPT.md, part A) or the seven slides built into the app at `/deck`
(print to PDF from the browser).

## Short description (about 50 words)

PARALLAX plays NASA's SPHEREx images of any patch of sky like a short video, so moving objects stand out. Click one
and it measures the motion, distance and spectrum. A blind search tests every source for motion, and every claim is
checked: predictions are locked before the data exists, and movers must agree with ten-year-old catalogues.

## Problem

SPHEREx photographs the whole sky in 102 infrared colours, again and again. Pluto was found by blinking two
photographs; the same trick on SPHEREx could turn up comets, asteroids, nearby brown dwarfs, perhaps new planets. But
the data is hard to use, and spotting a dot that shifts is not the same as knowing it moved: it could be a blend of two
stars, a detector artifact, or just a different colour, because every SPHEREx image sees a different wavelength.

## Solution

One public web tool that does what the challenge asks, then goes further.

- **Play the sky.** Type a name or coordinates. Real DR1 and QR3 cutouts from the NASA archive are lined up on one
  north-up grid and played in time order. Blink two dates, subtract them, or add them up. Choose the width of the field.
  Every frame shows its true wavelength, and the tool warns when two frames are not the same colour.
- **Overlays and links.** Gaia DR3 stars moved to each frame's date, and what WISE saw around 2015. Every view is a
  link with the coordinates in it, and `embed=1` gives a viewer-only page for other sites.
- **Measure.** Click a source: its position in every image on the original pixels, its proper motion and parallax,
  and a 0.75–5 µm spectrum that follows the source as it moves, matched to brown-dwarf templates.
- **Hunt.** A blind search finds every source in a field, tests each one for motion, and only then looks it up.
- **Prove.** Locked predictions, control stars, hidden test sources, and checks against Gaia (2016) and WISE (2015).

## How the challenge's test targets came out

| Target | Result |
|---|---|
| Epsilon Indi B | Moves 4.63″/yr with parallax 298 ± 9 mas, from SPHEREx alone (434 exposures). Spectrum matches a T3 template. A locked prediction of its next visit landed 0.072″ away. The blind search finds it without being told. |
| WISE 0855 | Invisible at 0.75–3.8 µm, detected at 3.8–5.0 µm (460 ± 32 µJy at 4.4–5.0 µm, S/N 14). The blind search flags it as a cold-only mover; CatWISE confirms the motion over ten years. |
| Barnard's Star | Saturated in every exposure. PARALLAX says so and does not force a motion. Its brightness, from the halo, is steady (control). |
| RW Aurigae | Saturated, so measured from the unsaturated halo at matched wavelength: faded by 36 % between Sept 2025 and Sept 2026 (6.4σ). Experimental. |
| R Draconis | Same method: faded by 42 % between mid-2025 and mid-2026 (12.4σ). Experimental. |

## Scientific validation (actual results)

1. **A prediction locked before the data was downloaded: PASS.** Epsilon Indi B's motion was fitted from visits 1–3,
   hashed (`c902006d…`) and committed; then visit 4 was downloaded. It landed **0.072″** from the prediction (d² = 4.85
   against a limit of 11.83 set in advance). "It stays put" missed by 1.95″. A second experiment on 2MASS J0415−0935
   passed too.
2. **Predictions for data that does not exist yet.** Monthly positions for 2027 for both objects are locked in commit
   `bbfd25f`, with the date of the archive's newest image recorded.
3. **The blind search.** Across 25 fields (2.3 square degrees, 2,891 exposures) the search tested **5,195 sources** for motion with no catalogue input. It found **13 of 19 known fast movers** on its own, including the free-floating planetary-mass object SIMP 0136, flagged **0 movers that no catalogue explains**, and rejected 8 false alarms with its vetting tests. Hidden synthetic cold sources were recovered down to 600 µJy at 3–8″/yr, with no stationary one called a mover.
4. **Decade check.** Every mover is compared with Gaia 2016.0 and CatWISE2020. It rejected a convincing false alarm
   (1.39″/yr at 13σ) and confirmed the real movers.
5. **Variable stars.** R Draconis 0.58 ± 0.03 and RW Aurigae 0.64 ± 0.04 of their first-visit brightness; the control
   1.04 ± 0.03. Of 6 other bright stars measured the same way (11 visit comparisons), 0 were flagged variable; their median change was 3 % and the largest 8 %.
6. **Controls.** 33 still stars measured: 0 flagged as moving; error bars behave as quoted (pull spread 0.93).
7. **Solar-system check.** No known asteroid or comet within 60″ of any target at the sampled observation times.
8. **Tests.** 71 Python tests and 12 web tests pass.

Mistakes found and fixed along the way are in RESULTS_LOG.md.

## How NASA data is used

SPHEREx Spectral Images, DR1 (doi:10.26131/IRSA678) and QR3, from NASA/IPAC IRSA through its search and cutout
services: 913 exposures for the five targets, 2,891 for the hunt, and live queries for any other position.
PARALLAX reads the image, variance, flags, the release ePSF and the per-pixel wavelength of every exposure. Gaia DR3
registers each exposure. CatWISE2020 (WISE and NEOWISE) supplies the ten-year check and the WISE overlay. Each file's
SHA-256 and archive URL are recorded. Full citations: DATA_SOURCES.md.

## Impact

Anyone with a browser can watch real NASA images of any patch of sky and measure what moved, without installing
astronomy software. What they get is evidence a researcher can check, down to the archive file. The same engine can be
pointed at each new SPHEREx release.

## Innovation

Viewers, blink tools and mover searches for SPHEREx and WISE already exist, and we do not claim them
(docs/COMPETITORS.md). What is new here: the tool **tests itself in public**. Predictions are locked before the data
exists; the blind search is graded on known movers it was not told about; every mover must agree with catalogues from
ten years ago; and saturated variable stars are measured from their halo, at matched wavelength, with a control.

## AI disclosure

AI coding assistants (Claude Code; ChatGPT for planning and research) helped write the code and documents. No AI runs
inside the app: every measurement comes from fixed, readable code with rules set in advance. No AI-generated images or
NASA branding are used. See AI_USAGE.md. TEAM TODO: complete it with your own tools and checks.

## Limitations

- No new object is claimed. Unexplained movers are candidates only.
- Three of the five test targets saturate SPHEREx; the halo method for them is experimental.
- 6.15″ pixels blend close pairs.
- With fewer than three visits, motion and parallax cannot be separated (WISE 0855 comes out about 3σ too fast).
- The hunt's fields were chosen around known objects and blank sky. It measures how well the search works, not how
  many new objects exist.
- Not a Planet Nine search yet: such a planet would move by arcminutes between visits and is expected to be too faint.

## Future work

- Follow moving objects within a visit, for comets, asteroids and distant planets.
- Search wider fields from the bulk archive instead of small cutouts.
- Check the 2027 forecasts when the next SPHEREx visit is released.
- A queue where volunteers vet candidates, as in Backyard Worlds.

## References

- SPHEREx DR1 Spectral Images, doi:10.26131/IRSA678; QR3 per IRSA guidance.
- Gaia Collaboration, Vallenari et al. 2023, A&A 674, A1.
- Marocco et al. 2021, ApJS 253, 8 (CatWISE2020).
- Kirkpatrick et al. 2021, ApJS 253, 7.
- Gagné et al. 2026, arXiv:2604.22012 (SPIFF).
- Berthier et al. 2006 (SkyBoT); Wenger et al. 2000 (SIMBAD).
- Astropy Collaboration 2022; Virtanen et al. 2020 (SciPy); Harris et al. 2020 (NumPy).

*This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of
Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California
Institute of Technology, and is funded by the National Aeronautics and Space Administration.* PARALLAX is not affiliated
with or endorsed by NASA.
