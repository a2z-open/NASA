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

## Third session (14 Nov 2026): helpers and what they did

- Claude Code (model Fable 5.2) wrote the distant-world search, the Planet Nine mode, the Barnard's Star halo test, the lock
  ledger and the new pages, and fixed the defects listed in RESULTS_LOG.md.
- Three AI helper agents ran in parallel, each with a narrow, read-mostly job:
  1. a literature search on Planet Nine, which wrote `docs/PLANET_NINE_RESEARCH.md` with sources and flagged what it could not confirm;
  2. a search of the official Space Apps pages, which wrote `docs/JUDGING_NOTES.md`;
  3. an independent audit of the code and documents, which changed nothing and returned a list of defects. That list is the
     source of the corrections in RESULTS_LOG.md, including claims that had overreached.
- No AI runs inside the app. The orbit fit, the linking and every threshold are fixed, readable code.
- TEAM TODO: the idea, the direction and the approval of every claim must be the team's own. State in your own words what
  each member decided and checked. The official FAQ says AI must not supply the idea (see `docs/JUDGING_NOTES.md`).

## Fourth session (14 Nov 2026): redesign, sky map, cold-world spectra, check a candidate

- Claude Code (models Opus 5.5 and Fable 5.2) rewrote the website (monochrome design, home page, Google-Maps-style sky map),
  fixed the name search for Solar System bodies, and wrote the cold-world spectral search (`pipeline/cubespec.py`,
  `validation/coldspec.py`, `validation/coldspec_after.py`) and the "Check a candidate" page.
- Machine learning in this session: gradient-boosted trees (scikit-learn) that read a spectral type from a SPHEREx spectrum.
  It was trained on objects with published types, cross-validated by object, and hash-locked before it scored any unclassified
  object. Its outputs are labelled as model readings everywhere. It found no new object; the vetting that showed this is in
  VALIDATION.md, section 12.
- No AI runs inside the app at request time. The page "Check a candidate" collects human opinions; it does not use a model to
  judge them.
- No large-language-model API is called by the pipeline or the app.

## Fifth session (14–15 Nov 2026): asteroid hunt, Planet Nine deep stack, "How we find them"

- Claude Code (model Opus 5.5) wrote the asteroid hunt, the Planet Nine deep stack, the stacking test along known asteroid paths,
  the `/api/how` endpoint and the `/how` page. No machine-learning model was added: the deep stack is a matched filter and a sum
  along predicted paths, checked with control motions and synthetic planets.
- No AI runs inside the app at request time, and no large-language-model API is called by the pipeline or the app.
- Also in the fifth session: Claude Code wrote `pipeline/archives.py` (live archive lookups), the extra sky-map layers, the
  "What other telescopes saw here" panel and `validation/coldspec_others.py`. No AI runs inside the app.
