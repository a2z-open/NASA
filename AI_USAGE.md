# AI usage disclosure

NASA Space Apps permits AI use but requires disclosure. Seattle organizers also asked for it in the submission's
"Super Intelligence" section. This file records how AI was used to build PARALLAX. **TEAM TODO:** before submitting,
review it and add your own tools (for example ChatGPT, or AI design tools) and your verification steps.

## Development-time AI

| Tool | What it did | Human review |
|---|---|---|
| Claude Code (Anthropic, model Claude Opus 5.5) in the Claude desktop app | Wrote most of the code on branch `parallax-build`: the archive client, FITS loading, quality flags, ePSF astrometry and photometry, Gaia registration, motion fits, spectra, evidence model, validation suite, FastAPI backend, React frontend and these documents. It also ran the data downloads, the held-out experiment (lock → commit → reveal) and the tests. A second Claude Code agent (a forked subagent) built most of the web frontend in parallel. | **TEAM TODO:** review the code, re-run the tests, and check the scientific claims in VALIDATION.md before submission. |
| ChatGPT (OpenAI) | Earlier research, planning and review, as stated in the team's master prompt. | TEAM TODO: describe. |
| Claude (claude.ai) | Earlier planning documents, including the team plan artifact and handoff. | TEAM TODO: describe. |

| Claude Code (Anthropic, model Claude Fable 5.2), same app, 14 Nov 2026 from about 03:20 PT | Wrote the blind search (`pipeline/hunt.py`), the hunt field list and runner, the halo photometry for saturated stars (`pipeline/halo.py`), the solar-system lookup, the catalogue checks, their tests, and redesigned the web interface (new home, Planet X hunt, Proof and About pages). A research sub-agent read public competitor pages and wrote `docs/COMPETITORS.md`. | TEAM TODO: review the new pages and the hunt results before presenting them. |

Commits that Claude Code helped write carry a `Co-Authored-By: Claude` trailer.

## Runtime AI

**None.** PARALLAX calls no language model or other AI model at runtime. Every measurement, classification and verdict
comes from deterministic, inspectable Python. The motion fits are weighted least squares and the template comparison is
SPIFF's chi-square. The evidence model is a set of rules with thresholds fixed in `pipeline/analysis.py`. All text in
the app's investigation summaries is generated from templates filled with measured numbers.

## AI-generated assets

No AI-generated images, logos, video or audio are used. Every sky image in the app is a real SPHEREx exposure,
reprojected for display. PARALLAX uses no NASA logos or mission branding.

## What AI did not do

- It did not choose or alter measurement results to look better. Thresholds were fixed in code before the validation
  runs, and failures (Barnard's Star, RW Aur, R Dra saturation) are reported as failures.
- It did not view any held-out pixel of the Epsilon Indi B experiment before the prediction was locked and committed
  (see `validation/experiments/epsilon-indi-b/prediction.json` → `disclosures`).
- It did not label anything a discovery. Sources the blind search cannot explain are called candidates, and movers
  that an older catalogue already lists are labelled as known.
- It did not submit the project, publish the repository, deploy anything publicly, or contact organizers, sponsors or
  scientists. Those steps wait for explicit team approval.
