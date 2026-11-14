# Team review checklist: the approval gate

Claude Code built and tested PARALLAX locally. It did **not** push, deploy, publish, submit, register or contact anyone.
Work through this list, then decide separately on each gated action at the bottom.

## 1. Run it yourself
- [ ] `.venv/bin/python -m uvicorn api.app:app --port 8000`, then open http://127.0.0.1:8000.
- [ ] **Home:** the round window blinks two real images of Epsilon Indi B. The three numbers under it are filled in.
- [ ] **Search** a name ("WISE 0855") and coordinates ("331.09 -56.80").
- [ ] **Explore → Epsilon Indi B:** Play, Blink, Subtract, Add, Colour. Under "More controls": Known stars (Gaia),
      "What WISE saw around 2015", the Width box. Click the source: path, spectrum, "What else could it be?".
- [ ] **Planet X hunt:** the four tiles, the verdict sentence, open two or three fields and watch them blink. Read the
      "How faint and how slow" grid.
- [ ] **Proof:** guess, then "Open them" (PASS, 0.072″). Tests 2–5. Open one forecast.
- [ ] **RW Aurigae and R Draconis pages:** the brightness chart from the halo. Barnard's Star: "steady".
- [ ] **/deck:** seven slides; arrow keys move; print to PDF.
- [ ] **Embed:** `/explore?target=epsilon-indi-b&embed=1` shows only the viewer.
- [ ] **A coordinate of your choice:** progress shows, frames render, failures are reported.
- [ ] **Phone width:** usable, no sideways scrolling.

## 2. Check the science claims (VALIDATION.md, docs/HUNT_REPORT.md, RESULTS_LOG.md)
- [ ] Re-run `pytest -q` (85 tests) and `npm --prefix web test` (12 tests).
- [ ] Read docs/HUNT_REPORT.md. For every row of "Movers that no catalogue explains", open it in the app and decide
      whether to mention it at all. **None may be called a discovery.**
- [ ] Decide how to word the variable-star result. It is experimental; the control is one saturated star plus the bright
      field stars listed in `validation/halo_results.json`.
- [ ] WISE 0855's blind motion is 10.0 ± 0.6″/yr against 8.15″/yr in the catalogue. Keep that sentence in.
- [ ] Spot-check one exposure: open its `archive_url` and compare the SHA-256.
- [ ] Confirm nobody on the team opened Epsilon Indi B's visit-4 pixels before 00:37:57 PT on 14 Nov.
- [ ] Confirm the QR3 citation on the IRSA SPHEREx page (DATA_SOURCES.md).

## 3. Rules and eligibility
- [ ] **Organizer permission in writing** for overnight work and for reusing the Friday-night commit `dbec275`
      (DEVELOPMENT_HISTORY.md). A team member said overnight hacking was allowed; keep the message.
- [ ] **The public repository.** docs/COMPETITORS.md reports that the README at `github.com/a2z-open/NASA` describes an
      older state and credits reused code from another team (ZENITH). Check what was reused, whether its licence allows
      it, and that the submission discloses it.
- [ ] **The name.** At least four other entries are called Parallax, one in this same challenge. Keep it or add a subtitle.
- [ ] Registered team name, members and challenge are correct on the Space Apps site.
- [ ] Complete AI_USAGE.md with every tool the team used.
- [ ] LICENSE (MIT) is acceptable to all members.
- [ ] Font: Hanken Grotesk (Google Fonts, OFL). Photographs: 11 NASA images in `web/public/img/`, each credited in
      THIRD_PARTY_NOTICES.md and in the page footer. Two are artist's impressions and say so. Confirm the team is happy
      using NASA photographs as decoration (no NASA logo is used).
- [ ] At least one member attends in person on Sunday. Know the Seattle and global deadlines (Sun 15 Nov, 11:59 p.m.).

## 4. Gated actions (each needs its own explicit "yes")
- [ ] Push branch `parallax-build`. This publishes the code and gives the locked predictions (`ef75c76`, `4a5d715`,
      `bbfd25f`) an outside timestamp. The hunt results add about 20 MB.
- [ ] Deploy publicly (docs/DEPLOYMENT.md). No paid hosting without approval.
- [ ] Record the 30-second video, or export `/deck` to PDF (DEMO_SCRIPT.md).
- [ ] Submit on the Space Apps portal (SUBMISSION.md is a draft).
- [ ] Any contact with organizers, sponsors or scientists.

## 5. Added in the third session (14 Nov, no Git)

Nothing from this session is committed. The team asked that Git not be used for now, so all of it is in the working files.

**Look at these**
- [ ] **Planet X hunt page:** three searches. Open "Find a distant world by its parallax": each world's distance against JPL's,
      the wavy path, the spectrum. Check that the misses are shown as misses.
- [ ] **"The same search, pointed at Planet Nine":** it must read as *not found, and could not have been*. Read the reach table,
      the pretend-planet grid and the false alarms.
- [ ] **Proof page, Test 6:** Barnard's Star from its halo, on the visit that had been sealed.
- [ ] `python -m validation.ledger verify` prints "OK". Read `validation/distant/PROTOCOL.md` and `PROTOCOL_P9.md`.
- [ ] `docs/DISTANT_WORLDS.md` (generated), `docs/PLANET_NINE_RESEARCH.md` and `docs/JUDGING_NOTES.md` (written by AI helpers from
      public sources; both list what they could not confirm).

**Decide these**
- [ ] **The claim.** Suggested wording: "PARALLAX found a dwarf planet without being told where it was and measured its distance
      from parallax; pointed at Planet Nine it found nothing, and we show why." Never "we searched for Planet Nine and ruled it out".
- [ ] **The brightness rule in the Planet Nine mode was added after seeing two real candidates.** It is disclosed everywhere.
      Confirm you are comfortable presenting it that way.
- [ ] **Figures quoted from memory, to verify before the pitch:** the wavelengths of the methane-ice and water-ice bands
      (`validation/distant_report.py`, `SURFACE`), the references for each world's surface, and the V magnitudes used for the
      Neptune and Jupiter twins (`validation/planet_nine.py`, `reach`).
- [ ] **Barnard's Star is no longer sealed.** 36 exposures of its third visit were downloaded for the halo test. Say so if asked.
- [ ] **Slide 1 needs the team name and members** (the submission guide asks for them): fill `TEAM` in `web/src/pages/Deck.tsx`.
- [ ] **Eligibility, from `docs/JUDGING_NOTES.md`:** work before the official start, credit for any reused code, and the rule that
      AI must not supply the idea. These need the team's own answers, in writing.

**Gated, as before (each needs its own explicit yes)**
- [ ] Using Git again: commit this session's work, then push. Publishing the last ledger hash gives the locks an outside time-stamp.
- [ ] Deploy, record or export the demo, submit, contact anyone.
