// Types mirror docs/API.md. Every numeric field may be null when the backend could not measure it.
import { decodeFrame } from './lib/astro.ts';

export interface Astrometry {
  ra_deg: number; dec_deg: number; epoch_jyear: number | null; epoch_mjd: number | null;
  pmra_masyr: number | null; pmdec_masyr: number | null; parallax_mas: number | null;
  pmra_err?: number | null; pmdec_err?: number | null; parallax_err?: number | null;
  source: string; source_url: string;
}

export interface Target {
  slug: string; title: string; kind: string; purpose: string; notes: string[];
  astrometry: Astrometry;
  field: { field_id: string; ra: number; dec: number; fov_arcmin: number } | null;
  status: 'cached' | 'missing';
  n_observations: number; n_visits: number; date_range: [string, string] | null;
  headline: { verdict: string; label: string; detail: string } | null;
  investigation_id: string | null;
}

export interface Grid {
  nx: number; ny: number; pixel_arcsec: number; ra0: number; dec0: number;
  projection: string; orientation: string; dtype: 'float16' | 'float32' | string; row0: string;
}

export interface Visit {
  id: string; start_utc: string; end_utc: string; n_products: number; releases: string[];
  per_detector: Record<string, number>; sealed: boolean;
}

export interface Frame {
  id: string; obs_id: string; detector: number; release: string; processing_version: string | null;
  mjd: number; time_utc: string; visit: string;
  wavelength_um: number | null; bandwidth_um: number | null; wavelength_range_um: [number, number] | null;
  data_url: string;
  stats: { median: number; sigma: number; p995: number; finite_fraction: number };
  flags_at_center: string[];
  archive_url: string; cutout_url: string; sha256: string;
}

export interface CatalogStar {
  source_id: string; ra: number; dec: number; g: number | null; pmra: number | null; pmdec: number | null; parallax: number | null;
}

export type DataState = 'cached' | 'live' | 'processing' | 'ready' | 'no_coverage' | 'insufficient' | 'archive_unavailable' | 'failed';

export interface Stack {
  id: string; label: string; n_frames: number; data_url: string; nx: number; ny: number; pixel_arcsec: number;
  dtype: string; row0: string; stats: { median: number; sigma: number; p995: number; finite_fraction: number };
  centered_on: string; note: string;
}

export interface Field {
  field_id: string; kind: 'curated' | 'live'; title: string | null;
  investigation_id?: string | null;
  stacks?: Stack[];
  frame_errors?: number;
  ra: number; dec: number; fov_arcmin: number;
  data_state: DataState; message: string | null;
  progress: { stage: string; done: number; total: number } | null;
  grid: Grid | null;
  archive: { n_products: number; collections: string[]; queried_utc: string; visits: Visit[] } | null;
  frames: Frame[];
  catalog: CatalogStar[];
  catalog_status?: 'loading' | 'ready' | 'unavailable';
  catalog_epoch_mjd: number;
}

export interface Verdict { code: string; label: string; strength: 'supported' | 'tentative' | 'not_supported' | 'untestable' }

export interface Detection {
  product_id: string; mjd: number; time_utc: string; visit: string; detector: number; release: string;
  wavelength_um: number | null; bandwidth_um: number | null;
  ra: number | null; dec: number | null; sigma_arcsec: number | null; snr: number | null;
  flux_ujy: number | null; flux_err_ujy: number | null;
  fixed_flux_ujy: number | null; fixed_flux_err_ujy: number | null;
  flags: string[]; used_for_motion: boolean; outcome: string;
}

export interface MotionModel {
  pmra_masyr?: number; pmra_err_masyr?: number; pmdec_masyr?: number; pmdec_err_masyr?: number;
  pm_total_masyr?: number; pm_total_err_masyr?: number; parallax_mas?: number; parallax_err_mas?: number;
  fixed_parallax_mas?: number;
  chi2_reduced: number; n_points: number; bic: number; reference: { ra_deg: number; dec_deg: number; t0_mjd: number };
  [key: string]: unknown;
}

export interface Motion {
  status: 'significant' | 'not_significant' | 'insufficient';
  preferred_model: string | null;
  reported_model?: string;
  n_visits?: number;
  thresholds?: Record<string, number>;
  models: Record<string, MotionModel>;
  significance: { delta_chi2: number; equivalent_sigma: number; pm_over_error: number | null; delta_bic: number } | null;
  catalog_comparison: { source: string; pmra_masyr: number; pmdec_masyr: number; parallax_mas: number | null;
    d_pmra_sigma: number | null; d_pmdec_sigma: number | null; d_parallax_sigma: number | null } | null;
  track: { mjd: number; xi: number; eta: number }[];
  points: { mjd: number; xi: number; eta: number; sigma: number; visit: string; product_id?: string }[];
  baseline_days: number;
}

export interface SpectrumBin {
  bin: number; center_um: number; width_um: number; n: number;
  flux_ujy: number | null; flux_err_ujy: number | null; fixed_flux_ujy: number | null; fixed_flux_err_ujy: number | null;
}

export interface Spectrum {
  status: 'measured' | 'partial' | 'insufficient';
  method: string;
  points: { wavelength_um: number; bandwidth_um: number | null; flux_ujy: number; flux_err_ujy: number; detector: number; mjd: number; visit: string }[];
  binned: SpectrumBin[];
  coverage: { n_bins_filled: number; n_bins_total: number; n_bins_detected?: number; range_um: [number, number] | null };
  n_saturated?: number; n_measured?: number;
  wing_attempt?: { n_attempted: number; n_converged: number; n_accepted: number; median_chi2r: number | null; acceptance: string; summary: string } | null;
  fixed_vs_follow: { median_ratio: number | null; note: string } | null;
  templates: {
    status: 'matched' | 'poor_fit' | 'out_of_domain' | 'insufficient'; library: string;
    best: { spectral_type: string; grid_type: string; reduced_chi2: number; n_used: number; scale: number; at_library_cold_limit?: boolean } | null;
    alternatives: { spectral_type: string; grid_type: string; reduced_chi2: number }[];
    model_curve: { wavelength_um: number; flux_ujy: number }[] | null;
    reason: string;
  } | null;
}

export interface Variability {
  status: 'variable' | 'not_detected' | 'insufficient' | 'saturated';
  naive: { description: string; max_ratio: number | null; max_ratio_basis?: string; points: { mjd: number; flux_ujy: number; wavelength_um: number }[] } | null;
  matched: {
    description: string;
    comparisons: { center_um: number; visit_a: string; visit_b: string; ratio: number; ratio_err: number; sigma: number }[];
    median_log_ratio: number | null; chi2_reduced: number | null;
    visit_pairs?: VisitPair[];
  } | null;
  thresholds?: Record<string, number>;
  light_curve: { mjd: number; flux_ujy: number; flux_err_ujy: number; wavelength_um: number; detector: number }[];
  [key: string]: unknown;
}

export interface VisitPair {
  visit_a: string; visit_b: string; n_bins: number; mean_ratio: number; mean_ratio_err: number;
  median_ratio?: number; significance_sigma: number; bin_scatter_chi2r?: number; variable: boolean;
}

export interface ModelEval {
  n_usable: number; residual_arcsec: number; mahalanobis_d2: number; equivalent_sigma: number; verdict: string;
  prediction_sigma_arcsec?: number; measurement_sigma_arcsec?: number;
  mean_residual_arcsec?: { dra_cosdec: number; ddec: number };
}

export interface ValidationTarget {
  target: string; slug: string; purpose: string;
  archive_products: number | null; cached_products: number | null; usable_positions: number | null;
  date_range: [string, string] | null; wavelength_coverage_um: [number, number] | null; visits: number | null;
  outcomes?: Record<string, number>; flag_counts_near_source?: Record<string, number>;
  motion_status: string | null; pm_total_masyr: number | null; pm_total_err_masyr: number | null;
  parallax_mas: number | null; parallax_err_mas: number | null;
  catalog_comparison?: Record<string, unknown> | null;
  spectrum_status: string | null; spectrum_bins_detected: number | null;
  template: string | null; template_status: string | null; template_rchi2: number | null;
  fixed_vs_follow_ratio: number | null; variability_status: string | null; variability_method: string | null;
  naive_max_ratio: number | null; recovery_status: string; headline?: string;
}

export interface ValidationReport {
  generated_utc: string;
  thresholds: Record<string, number | string>;
  targets: ValidationTarget[];
  extra_targets?: ValidationTarget[];
  experiments: {
    experiment: string; target: string; locked_utc: string; prediction_sha256: string;
    training_products: number; training_usable: number; heldout_products: number; heldout_usable?: number; heldout_downloaded?: number;
    criterion: string; primary_model: string; training_fit: Record<string, any>;
    result: Record<string, ModelEval>; primary_verdict: string; classification: string; disclosures?: string[];
  }[];
  negative_controls: {
    description: string; thresholds: Record<string, number>; n_controls: number; n_measured: number; n_insufficient: number;
    false_positives: number; false_positive_ids: string[]; pull_std: number | null; pull_median_abs: number | null;
    pm_residual_median_masyr: number | null;
    results: { field: string; source_id: string; g: number | null; pm_total: number | null; pm_total_err: number | null; equivalent_sigma: number | null; pm_over_error: number | null; flagged_as_moving: boolean; outcome: string }[];
  };
  injections: {
    label: string; description: string;
    results: { injected_pm_masyr: number; injected_flux_ujy: number; n_frames: number; n_detected: number; recovered_pm_masyr?: number | null; recovered_pm_err_masyr?: number | null; median_snr?: number | null; flagged_as_moving?: boolean; outcome: string }[];
  } | null;
  limitations: string[];
}

export interface Hypothesis {
  id: string; name: string; status: 'supported' | 'disfavored' | 'possible' | 'not_testable'; evidence: string[];
}

export interface Investigation {
  id: string; kind: 'curated' | 'user'; title: string; field_id: string; created_utc: string;
  status: 'ready' | 'processing' | 'failed'; message: string | null;
  source: { ra: number; dec: number; label: string; catalog: Record<string, unknown> | null };
  summary: { headline: string; one_liner: string; verdicts: Verdict[] } | null;
  observations: {
    n_total: number; n_measured: number; n_usable_positions: number; date_range: [string, string] | null;
    wavelength_coverage_um: [number, number] | null; visits: Record<string, unknown>[]; quality: Record<string, unknown>;
  } | null;
  detections: Detection[];
  motion: Motion | null;
  spectrum: Spectrum | null;
  variability: Variability | null;
  hypotheses: Hypothesis[];
  limitations: string[]; follow_up: string[];
  provenance: { datasets: Record<string, unknown>[]; software: Record<string, unknown>[]; catalogs: Record<string, unknown>[]; n_files: number; manifest_url: string } | null;
  progress?: { stage: string; done: number; total: number } | null;
  demonstration?: {
    investigation_id: string; title: string; why: string; naive_max_ratio: number | null;
    matched_visit_pairs: VisitPair[]; variability_status: string;
  } | null;
  halo_variability?: HaloVariability | null;
  solar_system?: { status: string; n_epochs_checked: number; radius_arcsec: number; service: string; matches: { name: string; time_utc: string }[] } | null;
  cold_search?: {
    method: string;
    bands: { band: string; n: number; flux_ujy: number | null; flux_err_ujy: number | null; snr: number | null; detected: boolean; upper_limit_3sigma_ujy: number | null; ab_mag: number | null }[];
  } | null;
}

export interface HaloVisit {
  visit: string; n: number; start_utc: string; end_utc: string; ratio: number; err_vs_first?: number; sigma?: number | null; scatter: number;
}
export interface HaloVariability {
  status: 'variable' | 'not_detected' | 'insufficient'; ring: string | null; ring_pixels: [number, number] | null;
  n_exposures: number; n_used: number; n_core_saturated?: number; target?: string; visits?: HaloVisit[];
  light_curve?: { mjd: number; time_utc: string; relative: number; err: number; wavelength_um: number; visit: string; matched: boolean }[];
}
export interface HaloResults {
  generated_utc: string; targets: Record<string, HaloVariability>;
  controls: { field: string; source_id: string; g: number; status: string; visits: { visit: string; ratio: number; sigma: number; n: number }[] }[];
  control_summary: { n_stars: number; n_with_comparison: number; n_comparisons: number; n_flagged_variable: number; median_abs_change: number | null; max_abs_change: number | null };
}
export interface LabExperiment {
  id: string; target: string; title: string;
  prediction: any; prediction_sha256: string;
  prediction_commit: { hash: string; time: string } | null;
  result: any | null; result_commit: { hash: string; time: string } | null;
  field_id: string; training_frame_ids: string[]; heldout_frame_ids: string[];
  points: { mjd: number; xi: number; eta: number; sigma: number; set: 'training' | 'heldout'; product_id?: string; wavelength_um?: number }[];
  predicted_track: { mjd: number; xi: number; eta: number }[];
  predicted_at_mean_epoch?: { xi: number; eta: number; cov_arcsec2: number[][]; ra_deg: number; dec_deg: number };
  tangent_reference?: { ra_deg: number; dec_deg: number };
}

export interface ResolveResult {
  name: string | null; ra: number; dec: number; epoch_note?: string; source?: string; target?: string;
  pmra_masyr?: number | null; pmdec_masyr?: number | null; parallax_mas?: number | null;
  moves?: boolean; kind?: string; distance_au?: number | null; body_id?: string; position_utc?: string;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new ApiError('The PARALLAX service is not reachable. Check your connection and retry.', 0);
  }
  const text = await response.text();
  let body: any = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = null; }
  if (!response.ok) {
    const message = body?.message || body?.detail || `Request failed (${response.status}).`;
    throw new ApiError(typeof message === 'string' ? message : JSON.stringify(message), response.status);
  }
  return body as T;
}

const post = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

export type ChunkAssignmentStatus = 'claimed' | 'in_progress' | 'reviewed';
export type ChunkAction = 'claim' | 'join' | 'leave' | 'start' | 'review' | 'reopen' | 'release';
export interface ChunkAssignment {
  status: ChunkAssignmentStatus;
  name: string;
  mine: boolean;
  teammates: { name: string; mine: boolean }[];
}

export const chunkApi = {
  list: (signal?: AbortSignal) => request<Record<string, ChunkAssignment>>('/api/chunks', { signal }),
  update: (id: string, action: ChunkAction, name?: string) =>
    request<ChunkAssignment | null>(`/api/chunks/${encodeURIComponent(id)}`, post({ action, name })),
};

export const api = {
  health: () => request<{ ok: boolean; version: string; cache?: Record<string, number>; services?: Record<string, string> }>('/api/health'),
  targets: () => request<Target[]>('/api/targets'),
  resolve: (q: string) => request<ResolveResult>(`/api/resolve?q=${encodeURIComponent(q)}`),
  createField: (body: { ra: number | string; dec: number | string; fov_arcmin?: number; max_frames?: number; wavelength_min_um?: number; wavelength_max_um?: number }) =>
    request<{ field_id: string; status: string; job_id?: string }>('/api/fields', post(body)),
  field: (id: string) => request<Field>(`/api/fields/${encodeURIComponent(id)}`),
  fieldWise: (id: string) => request<{ n: number; sources: { name: string; ra: number; dec: number; w2: number | null; pm_arcsec_yr: number; mover: boolean }[] }>(`/api/fields/${encodeURIComponent(id)}/wise`),
  job: (id: string) => request<{ job_id: string; kind: string; status: string; progress: { stage: string; done: number; total: number } | null; result_id: string | null; message: string | null }>(`/api/jobs/${encodeURIComponent(id)}`),
  createInvestigation: (body: { field_id: string; ra: number; dec: number; label?: string }) =>
    request<{ investigation_id: string; status: string; job_id?: string }>('/api/investigations', post(body)),
  investigation: (id: string) => request<Investigation>(`/api/investigations/${encodeURIComponent(id)}`),
  validation: () => request<ValidationReport>('/api/validation'),
  lab: () => request<{ experiments: LabExperiment[] }>('/api/lab'),
};

export function exportUrl(id: string, format: 'json' | 'csv'): string {
  return `/api/investigations/${encodeURIComponent(id)}/export?format=${format}`;
}

// ---------------------------------------------------------------------------
// Frame pixel cache (decoded Float32Array per data_url), bounded.
// ---------------------------------------------------------------------------

const frameCache = new Map<string, Float32Array>();
const inflight = new Map<string, Promise<Float32Array>>();
const MAX_FRAMES = 900;

export function cachedFrame(url: string): Float32Array | undefined {
  return frameCache.get(url);
}

export function loadFrame(url: string, dtype: string): Promise<Float32Array> {
  const hit = frameCache.get(url);
  if (hit) return Promise.resolve(hit);
  const pending = inflight.get(url);
  if (pending) return pending;
  const p = fetch(url)
    .then(r => {
      if (!r.ok) throw new ApiError(`Frame unavailable (${r.status})`, r.status);
      return r.arrayBuffer();
    })
    .then(buf => {
      const data = decodeFrame(buf, dtype);
      frameCache.set(url, data);
      if (frameCache.size > MAX_FRAMES) {
        const first = frameCache.keys().next().value;
        if (first !== undefined) frameCache.delete(first);
      }
      inflight.delete(url);
      return data;
    })
    .catch(err => {
      inflight.delete(url);
      throw err;
    });
  inflight.set(url, p);
  return p;
}

/** Load many frames with bounded concurrency; calls onEach as each arrives. */
export async function loadFrames(urls: string[], dtype: string, onEach?: (url: string, data: Float32Array) => void, concurrency = 6, signal?: AbortSignal): Promise<void> {
  let next = 0;
  async function worker() {
    while (next < urls.length) {
      if (signal?.aborted) return;
      const url = urls[next++];
      try {
        const data = await loadFrame(url, dtype);
        if (!signal?.aborted) onEach?.(url, data);
      } catch { /* missing frames are shown as unavailable */ }
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, urls.length) }, worker));
}

// ---------------------------------------------------------------------------
// Planet X hunt (blind search)
// ---------------------------------------------------------------------------
export interface HuntMover {
  id: string; class: string; ra: number; dec: number; pm_arcsec_yr?: number | null; sigma?: number | null;
  pm_over_error?: number | null; stack_snr: number; best_band: string; cold_only?: boolean; flags: string[];
  truth_match?: string | null; n_native_positions?: number; catalogued_as?: string | null; decade_confirmed?: boolean | null;
  parallax_mas?: number | null; parallax_err_mas?: number | null;
  gaia?: { source_id: string; g: number | null; pmra_masyr: number | null; pmdec_masyr: number | null } | null;
  stack_motion?: { pm_arcsec_yr: number; pm_err_arcsec_yr: number; significance: number; n_visits: number } | null;
  field_id?: string;
}
export interface HuntTruth {
  name: string; catalogue_pm_arcsec_yr: number; spectral_type?: string | null; detected: boolean; recovered: boolean;
  recovered_class: string | null; measured_pm_arcsec_yr: number | null; measured_sigma: number | null; separation_arcsec: number | null;
  nearest_source: string | null; field_id?: string;
}
export interface HuntFieldRow {
  field_id: string; title: string; kind: 'validation' | 'recovery' | 'control' | string; notes: string | null;
  ra: number; dec: number; fov_arcmin: number; area_deg2: number; n_visits: number; baseline_days: number;
  n_exposures: number; n_sources: number; n_motion_tested: number; counts: Record<string, number>;
  depth_5sigma_ujy: Record<string, number>; truth: HuntTruth | null; movers: HuntMover[];
}
export interface HuntIndex {
  generated_utc: string;
  totals: { fields: number; area_deg2: number; exposures: number; sources: number; motion_tested: number };
  classes: Record<string, number>;
  recovery: { n_known: number; n_detected: number; n_recovered: number };
  unexplained: HuntMover[];
  reach?: { median_depth_ujy: number; reach_ly: number; reference: string } | null;
  thresholds: Record<string, number>;
  fields: HuntFieldRow[];
}
export interface HuntStack {
  id: string; visit: string; band: string; wavelength_range_um: [number, number]; n_exposures: number; time_utc: string;
  data_url: string; stats: { median: number; sigma: number; p995: number };
}
export interface HuntField extends Omit<HuntFieldRow, 'movers' | 'n_visits'> {
  grid: Grid; stacks: HuntStack[]; sources: (HuntMover & { motion_status: string; track?: { visit: string; ra: number; dec: number }[] })[];
  visits: { id: string; start_utc: string; end_utc: string; n_exposures: number }[];
}
export interface Forecast {
  target: string; title: string; locked_utc: string; model: string; model_note: string;
  data_used: { n_usable_positions: number; first_observation_utc: string; last_observation_utc: string };
  archive_at_lock: { n_products_covering_the_source: number; latest_exposure_utc: string };
  fit: { pm_total_masyr?: number; pm_total_err_masyr?: number; parallax_mas?: number; parallax_err_mas?: number };
  criterion: string; sha256: string | null; commit: { hash: string; time: string } | null;
  kind?: string; spherex_windows?: { start_utc: string; end_utc: string }[];
  ledger?: { seq: number; time_utc: string; hash: string } | null;
  jpl_check?: { note: string; rows: { date: string; offset_from_jpl_arcsec: number; forecast_sigma_arcsec: number; in_spherex_window: boolean }[] } | null;
  predictions: { date_utc: string; ra_deg: number; dec_deg: number; sigma_ra_arcsec: number; sigma_dec_arcsec: number; offset_from_stays_here_arcsec: number; in_spherex_window?: boolean }[];
}
export interface HuntInjection {
  label: string; description: string; field: string; n_exposures: number; n_visits: number; baseline_days: number;
  speeds_arcsec_yr: number[]; fluxes_ujy: number[]; other_movers_reported: number;
  results: { speed_arcsec_yr: number; flux_ujy: number; outcome: string; measured_pm_arcsec_yr: number | null; n_native_positions: number | null }[];
}
export const huntApi = {
  injection: () => request<HuntInjection>('/api/hunt-injection'),
  forecasts: () => request<{ forecasts: Forecast[] }>('/api/forecasts'),
  index: () => request<HuntIndex>('/api/hunt'),
  halo: () => request<HaloResults>('/api/halo'),
  field: (id: string) => request<HuntField>(`/api/hunt/${encodeURIComponent(id)}`),
};
