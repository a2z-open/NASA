# Team review checklist: the approval gate

Claude Code built and tested PARALLAX locally. It did **not** push, deploy, publish, submit, register or contact anyone.
Work through this list, then decide separately on each gated action at the bottom.

## 1. Run it yourself
- [ ] `.venv/bin/python -m uvicorn api.app:app --port 8000`, then open http://127.0.0.1:8000.
- [ ] Home: the five target cards show real thumbnails and current headlines.
- [ ] Explore → Epsilon Indi B: playback, Blink, Difference (the dipole), Stack, Spectral sort, Gaia overlay, the fitted track.
- [ ] Click the source: motion plot, spectrum (fixed vs follow), H0–H6, export JSON/CSV.
- [ ] Discovery Lab: lock details → your guess → Reveal (PASS, 0.072″).
- [ ] WISE 0855: the cold-object table (no short-λ detection; 4.4–5.0 µm S/N 14) and the side-by-side stacks.
- [ ] RW Aur / R Dra / Barnard: saturation is stated plainly. The comparison-star demonstration opens.
- [ ] Live query on a coordinate of your choice: progress shows, frames render, failures are reported.
- [ ] Phone width: usable, with no horizontal scroll.

## 2. Check the science claims (VALIDATION.md, RESULTS_LOG.md)
- [ ] Re-run `pytest -q` (45 tests) and `npm --prefix web test` (12 tests).
- [ ] Spot-check one Epsilon Indi B exposure: open its `archive_url` and confirm the SHA-256 in `provenance.json`.
- [ ] Read `validation/experiments/epsilon-indi-b/prediction.json` → `disclosures`, and agree with the wording.
- [ ] Confirm nobody on the team opened the Epsilon Indi B visit-4 pixels before 00:37:57 PT on 14 Nov. If anyone did, relabel the experiment.
- [ ] Decide whether "WISE 0855 detected at 4.4–5.0 µm" is phrased cautiously enough. It is forced photometry on a catalogue track.
- [ ] Confirm the QR3 citation/DOI on the IRSA SPHEREx page (DATA_SOURCES.md TEAM TODO).

## 3. Rules and eligibility
- [ ] **Organizer authorization in writing** for building before 9:00 a.m. Saturday, and for reusing commit `dbec275`, at both
      local and Global level (DEVELOPMENT_HISTORY.md).
- [ ] Registered team name, members and challenge are correct on the Space Apps site. The team was possibly registered as "Aiges".
- [ ] Complete AI_USAGE.md with every tool the team used.
- [ ] LICENSE (MIT) is acceptable to all members.
- [ ] Fonts loaded: IBM Plex Sans, IBM Plex Mono, Instrument Serif (Google Fonts, OFL). Already listed in THIRD_PARTY_NOTICES.md.
- [ ] At least one member attends in person on Sunday. Know the Seattle presentation deadline and the global deadline (Sun 15 Nov, 11:59 p.m.).

## 4. Gated actions (each needs its own explicit "yes")
- [ ] Push branch `parallax-build` to `github.com/a2z-open/NASA`. This publishes the code and makes the prediction commit externally timestamped.
- [ ] Deploy publicly (docs/DEPLOYMENT.md). No paid hosting without approval.
- [ ] Record the 30-second video and the backup demo (DEMO_SCRIPT.md).
- [ ] Submit on the Space Apps portal (SUBMISSION.md is a draft).
- [ ] Any outreach to organizers, sponsors or scientists.
