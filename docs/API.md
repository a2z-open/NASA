# PARALLAX API contract (v1)

FastAPI backend (`api/app.py`), default `http://127.0.0.1:8000`. The Vite dev server proxies `/api` and `/files`.
All numbers are real measurements or `null`. The frontend must never invent a missing value: show "unavailable".

Units: angles in degrees (positions) or arcsec (offsets, uncertainties); proper motion in mas/yr; parallax in mas;
flux density in microjansky (µJy); wavelength in micrometres (µm); time as MJD (UTC) plus ISO strings.

## Health and targets

`GET /api/health` → `{ ok, version, cache: { targets: int, fields: int }, services: { irsa: "ok"|"unavailable"|"unknown", gaia: ... } }`

`GET /api/targets` → `Target[]`

```ts
interface Target {
  slug: string; title: string; kind: string; purpose: string; notes: string[];
  astrometry: { ra_deg: number; dec_deg: number; epoch_jyear: number|null; epoch_mjd: number|null;
                pmra_masyr: number|null; pmdec_masyr: number|null; parallax_mas: number|null; source: string; source_url: string };
  field: { field_id: string; ra: number; dec: number; fov_arcmin: number } | null;
  status: "cached" | "missing";
  n_observations: number; n_visits: number; date_range: [string, string] | null;
  headline: { verdict: string; label: string; detail: string } | null;   // from the investigation
  investigation_id: string | null;
}
```

`GET /api/resolve?q=NAME` → `{ name, ra, dec, epoch_note, source, pmra_masyr?, pmdec_masyr?, parallax_mas? }` or 404 `{message}`.
Also accepts coordinate strings: `q=331.0966 -56.8006` or `q=22h04m23.2s -56d48m02s`.

## Fields (a sky region with its observations)

`POST /api/fields` body `{ ra: number|string, dec: number|string, fov_arcmin?: number (2–30, default 6), max_frames?: number (default 24), wavelength_min_um?, wavelength_max_um? }`
→ `{ field_id, status }`. Starts a background job (archive query + cutouts + reprojection) unless cached.

`GET /api/fields/{field_id}` → `Field`

```ts
interface Field {
  field_id: string; kind: "curated" | "live"; title: string | null;
  ra: number; dec: number; fov_arcmin: number;
  data_state: "cached" | "live" | "processing" | "ready" | "no_coverage" | "insufficient" | "archive_unavailable" | "failed";
  message: string | null;
  progress: { stage: string; done: number; total: number } | null;
  grid: { nx: number; ny: number; pixel_arcsec: number; ra0: number; dec0: number;
          projection: "TAN"; orientation: "north-up east-left"; dtype: "float16" | "float32"; row0: "north" };
  archive: { n_products: number; collections: string[]; queried_utc: string;
             visits: { id: string; start_utc: string; end_utc: string; n_products: number; releases: string[];
                       per_detector: Record<string, number>; sealed: boolean }[] } | null;
  frames: Frame[];
  catalog: { source_id: string; ra: number; dec: number; g: number|null; pmra: number|null; pmdec: number|null; parallax: number|null }[]; // Gaia DR3, epoch J2016.0
  catalog_epoch_mjd: number;   // 57388.5
}

interface Frame {
  id: string;                 // product id, e.g. "2025W18_1B_0081_2-D6"
  obs_id: string; detector: number; release: "DR1" | "QR3" | string; processing_version: string | null;
  mjd: number; time_utc: string; visit: string;
  wavelength_um: number | null;        // spectral-WCS wavelength at the field centre
  bandwidth_um: number | null;
  wavelength_range_um: [number, number] | null;   // across this cutout (the LVF varies across the detector)
  data_url: string;            // raw little-endian array, ny*nx, row 0 = north, col 0 = east. NaN = masked/no data
  stats: { median: number; sigma: number; p995: number; finite_fraction: number };   // MJy/sr, robust
  flags_at_center: string[];
  archive_url: string; cutout_url: string; sha256: string;
}
```

Display frames are reprojected (bilinear) onto the common grid for viewing only. Every scientific
measurement is made on native pixels. Pixel values are MJy/sr with zodiacal light NOT subtracted: subtract
each frame's `stats.median` before differencing or stacking.

## Investigations (one source in one field)

`POST /api/investigations` body `{ field_id, ra, dec, label? }` → `{ investigation_id, status }` (background job)

`GET /api/investigations/{id}` → `Investigation` (curated targets use their slug as id)

```ts
interface Investigation {
  id: string; kind: "curated" | "user"; title: string; field_id: string; created_utc: string;
  status: "ready" | "processing" | "failed"; message: string | null;
  source: { ra: number; dec: number; label: string; catalog: object | null };
  summary: { headline: string; one_liner: string; verdicts: { code: string; label: string; strength: "supported" | "tentative" | "not_supported" | "untestable" }[] };
  observations: { n_total: number; n_measured: number; n_usable_positions: number; date_range: [string,string] | null;
                  wavelength_coverage_um: [number, number] | null; visits: object[]; quality: object };
  detections: Detection[];
  motion: Motion | null;
  spectrum: Spectrum | null;
  variability: Variability | null;
  hypotheses: { id: "H0"|"H1"|"H2"|"H3"|"H4"|"H5"|"H6"; name: string; status: "supported"|"disfavored"|"possible"|"not_testable"; evidence: string[] }[];
  limitations: string[]; follow_up: string[];
  provenance: { datasets: object[]; software: object[]; catalogs: object[]; n_files: number; manifest_url: string };
}
interface Detection {
  product_id: string; mjd: number; time_utc: string; visit: string; detector: number; release: string;
  wavelength_um: number|null; bandwidth_um: number|null;
  ra: number|null; dec: number|null; sigma_arcsec: number|null; snr: number|null;
  flux_ujy: number|null; flux_err_ujy: number|null;          // forced ePSF photometry on the motion-corrected track
  fixed_flux_ujy: number|null; fixed_flux_err_ujy: number|null;   // forced at one fixed sky position
  flags: string[]; used_for_motion: boolean; outcome: string;   // "ok" | "low_snr" | "core_saturated" | ...
}
interface Motion {
  status: "significant" | "not_significant" | "insufficient";
  preferred_model: string;
  models: Record<string, { pmra_masyr?: number; pmra_err_masyr?: number; pmdec_masyr?: number; pmdec_err_masyr?: number;
                           pm_total_masyr?: number; pm_total_err_masyr?: number; parallax_mas?: number; parallax_err_mas?: number;
                           chi2_reduced: number; n_points: number; bic: number; reference: { ra_deg: number; dec_deg: number; t0_mjd: number } }>;
  significance: { delta_chi2: number; equivalent_sigma: number; pm_over_error: number|null; delta_bic: number };
  catalog_comparison: { source: string; pmra_masyr: number; pmdec_masyr: number; parallax_mas: number|null;
                        d_pmra_sigma: number|null; d_pmdec_sigma: number|null; d_parallax_sigma: number|null } | null;
  track: { mjd: number; xi: number; eta: number }[];      // fitted model, arcsec, tangent plane at models[preferred].reference
  points: { mjd: number; xi: number; eta: number; sigma: number; visit: string }[];   // measured positions
  baseline_days: number;
}
interface Spectrum {
  status: "measured" | "partial" | "insufficient";
  method: string;
  points: { wavelength_um: number; bandwidth_um: number|null; flux_ujy: number; flux_err_ujy: number; detector: number; mjd: number; visit: string }[];
  binned: { bin: number; center_um: number; width_um: number; n: number; flux_ujy: number|null; flux_err_ujy: number|null; fixed_flux_ujy: number|null; fixed_flux_err_ujy: number|null }[];  // 102 SPIFF/SPHEREx bins, null = no data
  coverage: { n_bins_filled: number; n_bins_total: 102; range_um: [number, number] | null };
  fixed_vs_follow: { median_ratio: number|null; note: string } | null;
  templates: { status: "matched" | "poor_fit" | "out_of_domain" | "insufficient"; library: string;
               best: { spectral_type: string; grid_type: string; reduced_chi2: number; n_used: number; scale: number } | null;
               alternatives: { spectral_type: string; grid_type: string; reduced_chi2: number }[];
               model_curve: { wavelength_um: number; flux_ujy: number }[] | null;   // best template scaled to the data
               reason: string };
}
interface Variability {
  status: "variable" | "not_detected" | "insufficient" | "saturated";
  naive: { description: string; max_ratio: number|null; points: { mjd: number; flux_ujy: number; wavelength_um: number }[] };
  matched: { description: string; comparisons: { center_um: number; visit_a: string; visit_b: string; ratio: number; ratio_err: number; sigma: number }[];
             median_log_ratio: number|null; chi2_reduced: number|null };
  light_curve: { mjd: number; flux_ujy: number; flux_err_ujy: number; wavelength_um: number; detector: number }[];
}
```

`GET /api/investigations/{id}/export?format=json|csv` → dossier download.

## Validation and Discovery Lab

`GET /api/validation` → `{ generated_utc, targets: object[], negative_controls: object, experiments: object[], limitations: string[] }`

`GET /api/lab` → `{ experiments: LabExperiment[] }`

```ts
interface LabExperiment {
  id: string; target: string; title: string;
  prediction: object;            // the locked prediction.json verbatim
  prediction_sha256: string; prediction_commit: { hash: string; time: string } | null;
  result: object | null;         // result.json verbatim (null if not yet revealed)
  result_commit: { hash: string; time: string } | null;
  field_id: string;              // curated field with training + held-out frames
  training_frame_ids: string[]; heldout_frame_ids: string[];
  points: { mjd: number; xi: number; eta: number; sigma: number; set: "training" | "heldout" }[];  // tangent plane at prediction reference
  predicted_track: { mjd: number; xi: number; eta: number }[];
}
```

## Planet X hunt (blind search) and halo photometry

| Method | Path | Returns |
|---|---|---|
| GET | `/api/hunt` | The hunt index: totals (fields, area, exposures, sources, sources motion-tested), counts per class, `recovery` (known movers found blind), `unexplained` (candidates no catalogue explains), `reach`, thresholds, and one row per field with its movers. 404 until `python -m validation.hunt_fields run all` has been run. |
| GET | `/api/hunt/{field_id}` | One field: `grid`, `visits`, `stacks` (per visit and band, with `data_url`), every `sources[]` entry (class, flags, motion, `robust`, `chromatic`, `external` catalogue checks, `track`), `truth` (catalogue comparison made after the search), and every exposure used with its SHA-256. |
| GET | `/files/hunt/{field_id}/frames/{visit}-{band}.bin` | A stack as little-endian float32, row 0 = north, `grid.nx` × `grid.ny`. |
| GET | `/api/halo` | Halo-brightness results for the saturated targets and the control stars (`validation/halo_results.json`). |

Source classes: `candidate` (passes every test, not matched to truth), `stack_candidate` and `two_visit_candidate`
(weaker tiers), `known_mover` (Gaia shows the same motion), `suspect` (failed a vetting test; `flags` says which),
`slow_drift`, `static`, `too_faint`, `intermittent`. A candidate with `catalogued_as` set was found in Gaia or CatWISE
with the same motion and is not counted as unexplained.

Investigations now also carry `solar_system` (the SkyBoT check used by hypothesis H5) and, for saturated targets,
`halo_variability`.

## Jobs

`GET /api/jobs/{job_id}` → `{ job_id, kind, status: "queued"|"running"|"done"|"failed", progress: {stage, done, total}, result_id, message }`
