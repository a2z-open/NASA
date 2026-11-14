# Deployment (prepared, not executed)

Nothing has been deployed. Public deployment needs the team's explicit approval (see REVIEW_CHECKLIST.md).

## What the app needs

- **One process.** FastAPI (`api.app:app`) serves both the API and the built React app from `web/dist`.
- **No secrets, API keys or logins.** Every upstream service is public: IRSA, the Gaia TAP service, and the Sesame CfA mirror.
- **Outbound HTTPS** to `irsa.ipac.caltech.edu` (images and the WISE catalogue), `gea.esac.esa.int` (Gaia),
  `vizier.cfa.harvard.edu` (names) and `ssp.imcce.fr` (known asteroids). These are needed for live queries and for
  measuring new sources. The five targets, the hunt, the proofs and `/deck` work without them.
- **Memory.** About 400 MB at idle (numpy, astropy, scipy, pandas). Live investigations start up to 6 worker processes, each
  about 150 MB, so plan on 1–2 GB, or lower the worker count. Search for `workers=6` in `api/app.py`.
- **Disk.** The image carries `data/` (about 45 MB: the five targets and every hunt field). Live queries cache cutouts in `.parallax-cache/` (about 4 MB each,
  up to 48 per query). Ephemeral disk is fine. Each cutout is re-verified by SHA-256 when it is re-fetched.
- **Long operations run as background jobs.** The browser polls `/api/jobs/{id}`, so no HTTP request is held open past about
  1 s. Live field queries take about 60–120 s, mostly IRSA download time.

## Option A: one container (recommended)

```sh
docker build -t parallax .
docker run -p 8000:8000 parallax        # http://localhost:8000
```

Any container host that supports outbound HTTPS and about 1–2 GB of RAM can run it, for example Render, Fly.io, Railway or Google
Cloud Run (set a minimum of 1 instance and a request timeout of at least 60 s). Do not buy hosting or enable paid tiers without team approval.

## Option B: static frontend plus API

Build `web/` (`npm --prefix web run build`) and host `web/dist` on any static host. Proxy `/api` and `/files` to the API
container. Same-origin proxying is the simplest setup; otherwise CORS must be added to `api/app.py`.

## Before going public

1. Run `pytest -q` and `npm --prefix web test`, plus the smoke test: `/`, `/explore?target=epsilon-indi-b`, `/hunt`, `/proof`,
   `/about`, `/deck` and `/explore?target=epsilon-indi-b&embed=1`.
2. Open the public URL in a logged-out, private browser window, on both desktop and phone.
3. Run one live query, such as `RA 270.0, Dec −23.5`, from the deployed site to confirm outbound access to IRSA.
