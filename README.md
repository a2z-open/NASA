# PARALLAX

Open a patch of sky and compare dated SPHEREx observations. Barnard’s Star is the lead case for a future prediction reveal. The first build plays earlier observations and keeps the candidate reserved visit out of the sequence.

## Start locally

From this directory, create an isolated Python 3.12 environment and build the web app.

```sh
uv venv --python 3.12
uv pip install -r requirements.txt
npm --prefix web ci
npm --prefix web run build
.venv/bin/python -m uvicorn api.lookup:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. The curated sequence uses cached display assets. New coordinates query the public IRSA archive. Inspect image sources and comparison status in the viewer before interpreting a change in pixels.

## Science record

- Start with Barnard’s Star. Use the earlier visits for fit development and reserve a later visit for testing. Save the actual predictions and empirical tolerances before opening reserved target pixels.
- Display images are reprojected and stretched for playback. Native-pixel science uses the SPHEREx calibration maps and documented quality bits. Wavelength comparability can remain unverified during playback.
- Treat fixed-versus-follow flux as a bonus after the independent photometry gate passes.

See the [five-target evidence log](validation/results.md) for the coverage and measurement status. To rebuild the early-frame cache, run the curation script. To reproduce the archived wavelength labels, first save the [D5 spectral calibration product](https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/dr1/spectral_wcs/cal-swcs-v5-2026-191/5/spectral_wcs_D5_spx_cal-swcs-v5-2026-191.fits) in `.parallax-cache/calibration/` using its original filename. Curation selects earlier visits from fresh metadata, so results can change as the archive updates.

```sh
.venv/bin/python -m pipeline.curate
.venv/bin/python -m pipeline.fit_screen validation/barnards-star-archive.json validation/barnards-fit-screen.json
```

## Tests

```sh
uv pip install pytest
.venv/bin/python -m pytest -q
npm --prefix web test
```

[NASA/IPAC IRSA SPHEREx archive](https://irsa.ipac.caltech.edu/Missions/spherex.html) · [IRSA data access](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/) · [IRSA data products](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/)
