# Development history and authorization record

The Space Apps rules and the Seattle organizers care about **when** work was done. This record exists so the team can show
the organizers exactly what existed before the official start. Git history is preserved and nothing has been squashed or rewritten.

## Timeline (Pacific time)

| When | Who | What | Evidence |
|---|---|---|---|
| Fri 13 Nov 2026, 22:25 | hibutwhy (teammate) | Initial PARALLAX scaffold: IRSA SIA2 lookup, a Barnard's Star playback with two frames, Barnard calibration and fit screens, and coverage-only entries for the other four targets. | Commit `dbec275` on `origin/main` (pushed 22:28 per team notes). |
| Sat 14 Nov 2026, from 00:19 | Claude Code, working for the team in the team's local clone | Everything on branch `parallax-build`: science pipeline, held-out experiment, validation, API, frontend and documents. | Local commits on `parallax-build`, starting at `1039625`. |
| Sat 14 Nov 2026, 00:37:57 | Claude Code | Epsilon Indi B prediction **locked and committed** before any held-out pixel was downloaded. | Commit `ef75c76`; SHA-256 `c902006d2cb11e96db29bace24b4a2f8111ae4d0cc84ccd744563203c95798d5` |
| Sat 14 Nov 2026, 00:39:41 | Claude Code | Held-out visit downloaded, measured and evaluated. | Commit `51d8ea1`; `validation/experiments/epsilon-indi-b/result.json` |
| Sat 14 Nov 2026, 01:21:13 | Claude Code | Second experiment (2MASS J0415−0935) locked before its held-out visit was downloaded. | Commit `4a5d715`; SHA-256 `c9beae2e2bb8d75321b9d96b1d18ea20831fc0000e121ce6073483acff6b3b8c` |
| Sat 14 Nov 2026, 01:29:42 | Claude Code | Second held-out visit revealed and evaluated. | Commit `ce84964` |
| Sat 14 Nov 2026, 03:19 – about 08:00 | Claude Code | Blind search ("Planet X hunt") with 6 cached and 20 newly downloaded fields, halo photometry of the two saturated variable stars, solar-system and catalogue checks, interface redesign, and updated documents. | Local commits from `7bb4516` onwards. |

## Authorization: TEAM ACTION REQUIRED

- The team's own handoff rule says: *"No project code, repo or demo assets before Sat Nov 14, 9:00 a.m. Pacific … Don't
  reuse any pre-event code or data without the Seattle lead's OK."*
- Both commit `dbec275` (Friday night) and all work on `parallax-build` (from 00:19 Saturday) **predate** 9:00 a.m. Saturday.
- The master build prompt states that *"the organizers have authorized us to begin building now."* Claude Code acted on
  that statement but **cannot verify it**.
- On 14 Nov 2026 a team member told Claude Code that the organizers **allowed hacking overnight**. Claude Code cannot
  verify this either; it is recorded here so the team can attach the evidence.
- **Before submission, keep the organizers' written authorization** and confirm with the Seattle lead that it covers:
  1. building before the official start,
  2. reusing commit `dbec275`,
  3. Global Award eligibility, which local permission may not cover.
- If the authorization does not cover this work, tell the organizers and follow their guidance.

## Timestamps

Git commit times are self-reported by the machine that made them. Nothing on `parallax-build` has been pushed: the team
asked that nothing be published without approval. To prove publicly when the Epsilon Indi B prediction was frozen, the
team can push commit `ef75c76` (or publish its SHA-256). Until then, the lock time rests on the local commit and this record.
