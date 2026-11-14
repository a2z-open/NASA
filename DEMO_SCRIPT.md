# Demo scripts: drafts built only on what PARALLAX actually does

Every number below is a real result (see VALIDATION.md). Re-check them before recording if the data is rebuilt.

## A. 30-second global demo video

| Time | Screen (real app recording) | Narration / caption |
|---|---|---|
| 0–4 s | Home page over the real stacked SPHEREx image, then the PARALLAX title. | "The universe is moving." |
| 4–10 s | Type "Epsilon Indi B", then Explore. Real frames play. Switch to Difference: the dark/bright dipole of a moving source. | "But seeing movement isn't the same as understanding it." |
| 10–19 s | Click the source. The drawer shows the motion track (4.6″/yr, parallax 298 mas) and the 102-bin spectrum with the T3 template. Toggle fixed vs follow: 55 % of the light. | "PARALLAX combines NASA's infrared observations with motion analysis and spectral evidence." |
| 19–26 s | Discovery Lab: the locked hash, then Reveal. The prediction ellipse and the measured point land 0.07″ apart: PASS. "Stays here" misses by 1.95″. | "Every investigation is testable, traceable and honest about uncertainty." |
| 26–30 s | The evidence dossier, then the logo. | "PARALLAX. Discover why the sky changes." |

Use English captions. Use real recordings only, with no mock-ups. If time allows, swap in WISE 0855 at 19–26 s: the
short-wavelength stack shows nothing and the long-wavelength stack shows the source.

## B. Four-minute Seattle presentation

**0:00–0:25 Hook.** "In 1930, Pluto was found because one point of light moved between two photographs. NASA's SPHEREx now
maps the whole sky in 102 infrared colours. Somewhere in that data are discoveries nobody has made yet."

**0:25–0:50 Problem.** "Spotting a changing dot isn't enough. Did it really move? Is it a variable star? Two stars blended
in one 6-arcsecond pixel? A detector artifact? And SPHEREx adds a trap: every exposure sees a different wavelength, so a
'brightness change' is usually just colour."

**0:50–1:10 PARALLAX.** Show the home page, then type coordinates. *Real observations from IRSA, aligned and dated. Every frame
shows its true wavelength.*

**1:10–2:15 Scientific demo, Epsilon Indi B.**
- Show playback, then Difference mode (the dipole).
- Click the source. "4.6 arcseconds per year and 298 milliarcseconds of parallax, measured by SPHEREx alone from 434 exposures."
- Show the spectrum. "Following the motion recovers the whole spectrum. Measuring at a fixed spot would lose 45 % of the light.
  The spectrum matches a T3 brown-dwarf template, which fits two brown dwarfs we can't separate."
- Then WISE 0855: "The coldest known brown dwarf. Invisible at short wavelengths, detected at 4 to 5 microns, exactly where a
  250-kelvin object should shine. It sits at the cold edge of the template library."

**2:15–2:55 Scientific method: Lock → Predict → Reveal.**
- "Before downloading SPHEREx's most recent visit, we fitted the motion from earlier visits, hashed the prediction and committed it."
- Ask the room: "Will the dot stay here, or follow the track?" Then press Reveal.
- "It landed 0.07 arcseconds from the prediction, under a criterion we fixed in advance. 'Stays here' missed by almost
  2 arcseconds. Even the Gaia catalogue missed by half an arcsecond, because this is a binary."

**2:55–3:25 Validation and honesty.**
- "33 stationary stars, measured the same way: zero false alarms, and the error bars check out."
- "Three of NASA's five targets saturate SPHEREx. We say so instead of inventing numbers. Here is the wavelength trap on a
  real star: a 9× 'change' becomes 2 % once the comparison is matched in wavelength."

**3:25–3:45 Impact.** "Citizen scientists shouldn't need a whole astronomy software stack to investigate a real object.
PARALLAX brings NASA observations, measurements and reproducible evidence into one workflow, and every number links back to
the archive file it came from."

**3:45–4:00 Close.** "Motion tells you something moved. Spectroscopy helps tell you what it is. PARALLAX gives everyone
the tools to investigate the changing universe." End on the live product.

## C. Backup demo (if Wi-Fi or IRSA fails)

1. Run everything from cached real data: `uvicorn api.app:app` on a laptop. The five targets and the Lab need no network.
2. If even the laptop fails, use a pre-recorded screen capture of the same sequence. TEAM TODO: record it.
3. Do not attempt the live arbitrary-coordinate query on stage unless the venue network has been tested. A query takes about 80 s.

## D. Likely judge questions (short answers)

- **Why SPHEREx instead of WISE?** SPHEREx gives 102 narrow channels from 0.75 to 5 µm in each exposure, so a mover's
  spectrum comes from the same data. WISE gives a longer baseline in two broad bands. That baseline is future work, used for positions, not to compare fluxes.
- **How is this different from IRSA's tools or Blink 3.0?** They are excellent viewers and have path-following photometry.
  We don't claim those pieces. What we add is the integrated workflow: wavelength-aware comparison, the evidence model,
  pre-registered prediction, and dossiers with provenance.
- **How do you know it really moved?**
  - Native-pixel ePSF centroids.
  - Per-exposure registration to Gaia, about 0.25″ RMS.
  - Hundreds of independent exposures across four visits.
  - Proper motion and parallax fitted with honest errors (pull σ 0.93 on controls).
  - The held-out prediction passed (residual 1.7σ).
- **Different wavelengths?** We read each pixel's wavelength from the spectral WCS. We compare brightness only within the same
  wavelength bin across visits, and the viewer warns when a difference image isn't matched.
- **What does AI do?** It helped write code. No AI runs in the product, and every number comes from deterministic code (AI_USAGE.md).
- **Can you find Planet Nine?** No. Single SPHEREx exposures are several magnitudes too shallow. Our realistic target is
  WISE-0855-like cold objects near the Sun, and we showed SPHEREx can see one at 4–5 µm.
- **False positives?** Quality flags, saturation refusal, neighbour deblending, repeat detections across visits, a 5σ and 5×
  threshold, 0 of 33 control stars flagged, and 0 of 4 stationary injections flagged.
- **Why is the held-out test valid?**
  - The split rule was set in advance (the last visit is held out).
  - The code was committed and then the prediction committed, both before download.
  - Same measurement code.
  - A pre-registered criterion.
  - The lock script refuses to run if held-out pixels exist.
  - Caveat: Git timestamps are self-reported until pushed.
- **Insufficient data?** The investigation says "Insufficient evidence" and recommends follow-up, as for Barnard's Star.
- **Scaling?** Releases are configurable, and caching and modules are reusable. A full-sky search would need the S3 bulk
  archive and much more compute, which we don't claim.
- **Commercial future?** A general evidence engine for multispectral change detection, possibly onboard triage. Exploratory only:
  no customers and no integrations are claimed.
