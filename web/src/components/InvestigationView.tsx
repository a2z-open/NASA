import { useMemo, useState } from 'react';
import type { HaloVariability, Investigation, Hypothesis, Verdict } from '../api.ts';
import { exportUrl } from '../api.ts';
import { Link } from '../router.tsx';
import { formatDec, formatRA, wavelengthColor } from '../lib/astro.ts';
import { NA, date, dateTime, humanize, num, pm, sig, ujy, um, ujyWithError } from '../lib/format.ts';
import { MatchedComparisons, MotionPlot, NaiveLightCurve, SpectrumPlot, visitColor } from './Charts.tsx';
import { Term } from './Term.tsx';

const STRENGTH_LABEL: Record<Verdict['strength'], string> = {
  supported: 'Supported', tentative: 'Tentative', not_supported: 'Not supported', untestable: 'Not yet testable',
};

export function VerdictChip({ v }: { v: Verdict }) {
  return <span className={`chip chip--${v.strength}`} title={STRENGTH_LABEL[v.strength]}>{v.label}</span>;
}

const H_STATUS: Record<Hypothesis['status'], string> = {
  supported: 'Supported', disfavored: 'Disfavoured', possible: 'Possible', not_testable: 'Not testable',
};

function Stat({ label, value, hint }: { label: React.ReactNode; value: React.ReactNode; hint?: string }) {
  return (
    <div className="stat" title={hint}>
      <div className="stat__label">{label}</div>
      <div className="stat__value mono">{value}</div>
    </div>
  );
}

export function InvestigationView({ inv, compact = false }: { inv: Investigation; compact?: boolean }) {
  const [showFixed, setShowFixed] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [allRows, setAllRows] = useState(false);
  const m = inv.motion;
  const modelId = m?.reported_model ?? m?.preferred_model;
  const pref = modelId ? m?.models[modelId] : undefined;
  const obs = inv.observations;
  const tmpl = inv.spectrum?.templates;
  const visits = useMemo(() => [...new Set((inv.detections ?? []).map(d => d.visit))], [inv.detections]);
  const haloOk = !!inv.halo_variability && (inv.halo_variability.status === 'variable' || inv.halo_variability.status === 'not_detected');

  if (inv.status === 'processing') {
    return (
      <div className="inv inv--processing" aria-busy="true">
        <p className="eyebrow">Measuring</p>
        <h2>{inv.title ?? 'This source'}</h2>
        <p className="muted">{inv.message ?? 'Measuring this source in every image…'}</p>
        {inv.progress && <Progress {...inv.progress} />}
      </div>
    );
  }
  if (inv.status === 'failed') {
    return (
      <div className="inv">
        <p className="eyebrow">Could not measure this</p>
        <h2>{inv.title}</h2>
        <p className="notice notice--bad">{inv.message ?? 'The measurement failed, so no result is shown.'}</p>
      </div>
    );
  }

  return (
    <article className={`inv${compact ? ' inv--compact' : ''}`}>
      <header className="inv__head">
        <p className="eyebrow">{inv.kind === 'curated' ? 'NASA test target' : 'Your pick'}</p>
        <h2>{inv.title}</h2>
        <p className="mono dim small">{formatRA(inv.source.ra)} {formatDec(inv.source.dec)} · {inv.source.ra.toFixed(5)}°, {inv.source.dec.toFixed(5)}° (ICRS)</p>
      </header>

      {inv.summary && (
        <section className="inv__summary" aria-label="Summary">
          <p className="inv__headline">{inv.summary.headline}</p>
          {inv.summary.one_liner && <p className="inv__oneliner">{inv.summary.one_liner}</p>}
          <div className="chips">{inv.summary.verdicts.map(v => <VerdictChip key={v.code} v={v} />)}</div>
        </section>
      )}

      {inv.spectrum?.wing_attempt && inv.spectrum.status !== 'measured' && (
        <details className="more">
          <summary>Why the usual measurement fails on this star</summary>
          <p className="small">{inv.spectrum.wing_attempt.summary} <span className="dim">(Rule set in advance: {inv.spectrum.wing_attempt.acceptance}.)</span></p>
        </details>
      )}

      <div className="stats">
        <Stat label="Images used" value={obs ? `${obs.n_usable_positions} / ${obs.n_total}` : NA} hint="usable positions / exposures examined" />
        <Stat label="Dates" value={obs?.date_range ? `${date(obs.date_range[0])} → ${date(obs.date_range[1])}` : NA} />
        <Stat label="Colours" value={obs?.wavelength_coverage_um ? `${obs.wavelength_coverage_um[0].toFixed(2)}–${obs.wavelength_coverage_um[1].toFixed(2)} µm` : NA} />
        <Stat label={<Term t="proper motion">Speed across the sky</Term>} value={pref?.pm_total_masyr != null ? pm(pref.pm_total_masyr, pref.pm_total_err_masyr, 0, 'mas/yr') : NA} />
        <Stat label={<Term t="parallax">Parallax</Term>} value={pref?.parallax_mas != null ? pm(pref.parallax_mas, pref.parallax_err_mas, 0, 'mas') : NA} />
        <Stat label="Best match" value={tmpl?.best && (tmpl.status === 'matched' || tmpl.status === 'poor_fit') ? `${tmpl.best.spectral_type}${tmpl.status === 'poor_fit' ? ' (poor fit)' : ''}` : tmpl ? humanize(tmpl.status) : NA} />
      </div>

      <div className="inv__actions">
        <Link className="button button--ghost" href={`/evidence/${encodeURIComponent(inv.id)}`}>Printable report</Link>
        <a className="button button--ghost" href={exportUrl(inv.id, 'json')}>Download JSON</a>
        <a className="button button--ghost" href={exportUrl(inv.id, 'csv')}>Download CSV</a>
      </div>

      {haloOk && <HaloSection halo={inv.halo_variability!} />}

      {m && (
        <details className="section" open={m.status !== 'insufficient'}>
          <summary><h3>Is it moving?</h3><span className={`tag tag--${m.status}`}>{humanize(m.status)}</span></summary>
          {m.points.length > 0 && <MotionPlot motion={m} />}
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Model</th><th>μα cos δ (mas/yr)</th><th>μδ (mas/yr)</th><th>Parallax (mas)</th><th><Term t="reduced chi-square">χ²ᵣ</Term></th><th>N</th></tr></thead>
            <tbody>
              {Object.entries(m.models).map(([k, v]) => (
                <tr key={k} className={k === modelId ? 'is-preferred' : ''}>
                  <td>{humanize(k)}{k === modelId ? ' · reported' : ''}</td>
                  <td className="mono">{v.pmra_masyr != null ? pm(v.pmra_masyr, v.pmra_err_masyr) : '—'}</td>
                  <td className="mono">{v.pmdec_masyr != null ? pm(v.pmdec_masyr, v.pmdec_err_masyr) : '—'}</td>
                  <td className="mono">{v.parallax_mas != null ? pm(v.parallax_mas, v.parallax_err_mas) : v.fixed_parallax_mas != null ? `${num(v.fixed_parallax_mas, 1)} (fixed)` : '—'}</td>
                  <td className="mono">{num(v.chi2_reduced, 2)}</td>
                  <td className="mono">{v.n_points ?? NA}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
          {m.significance && (
            <p className="small muted">
              Moving vs stationary: Δχ² = {num(m.significance.delta_chi2, 1)} (≈ {sig(m.significance.equivalent_sigma)}), ΔBIC = {num(m.significance.delta_bic, 1)}.
              Baseline {num(m.baseline_days, 0)} days. Uncertainties are scaled by √χ²ᵣ when χ²ᵣ &gt; 1.
            </p>
          )}
          {m.catalog_comparison && (
            <p className="small">
              Catalogue ({m.catalog_comparison.source}): μα cos δ = {num(m.catalog_comparison.pmra_masyr, 1)}, μδ = {num(m.catalog_comparison.pmdec_masyr, 1)} mas/yr
              {m.catalog_comparison.parallax_mas != null && <>, ϖ = {num(m.catalog_comparison.parallax_mas, 1)} mas</>}.
              Differences: {sig(m.catalog_comparison.d_pmra_sigma)} / {sig(m.catalog_comparison.d_pmdec_sigma)}
              {m.catalog_comparison.d_parallax_sigma != null && <> / {sig(m.catalog_comparison.d_parallax_sigma)}</>} (RA / Dec / parallax).
            </p>
          )}
        </details>
      )}

      {inv.spectrum && (
        <details className="section" open={inv.spectrum.status !== 'insufficient' && (inv.spectrum.status as string) !== 'saturated'}>
          <summary><h3>What kind of object is it?</h3><span className={`tag tag--${inv.spectrum.status}`}>{humanize(inv.spectrum.status)}</span></summary>
          <p className="small muted">{inv.spectrum.method}</p>
          {inv.spectrum.binned.some(b => b.flux_ujy != null) ? (
            <>
              <div className="toggles">
                <label><input type="checkbox" checked={showFixed} onChange={e => setShowFixed(e.target.checked)} /> Compare with fixed-position extraction</label>
                <label><input type="checkbox" checked={showRaw} onChange={e => setShowRaw(e.target.checked)} /> Show individual exposures</label>
              </div>
              <SpectrumPlot spectrum={inv.spectrum} showFixed={showFixed} showRaw={showRaw} />
            </>
          ) : <p className="notice">No spectral measurement passed the quality checks.</p>}
          <p className="small">Coverage: {inv.spectrum.coverage.n_bins_filled} of {inv.spectrum.coverage.n_bins_total} channels
            {inv.spectrum.coverage.range_um ? ` (${inv.spectrum.coverage.range_um[0].toFixed(2)}–${inv.spectrum.coverage.range_um[1].toFixed(2)} µm)` : ''}. Empty channels are gaps, not zeros.</p>
          {inv.spectrum.fixed_vs_follow && <p className="small">Fixed vs follow: {inv.spectrum.fixed_vs_follow.note}{inv.spectrum.fixed_vs_follow.median_ratio != null ? ` (median fixed/follow = ${num(inv.spectrum.fixed_vs_follow.median_ratio, 2)})` : ''}</p>}
          {tmpl && (
            <div className="template">
              <p><strong>Template comparison</strong> <span className="dim">· {tmpl.library}</span></p>
              {tmpl.best && <p className="mono small">Best: {tmpl.best.spectral_type} ({tmpl.best.grid_type}), χ²ᵣ = {num(tmpl.best.reduced_chi2, 2)}, {tmpl.best.n_used} channels</p>}
              {tmpl.best?.at_library_cold_limit && (
                <p className="coldnote small"><strong>Coldest template in the library.</strong> {tmpl.best.spectral_type} is the coldest type SPIFF provides, so read this as “at least as cold as {tmpl.best.spectral_type}”, not as a precise type.</p>
              )}
              {tmpl.alternatives?.length > 0 && <p className="small dim">Next: {tmpl.alternatives.slice(0, 4).map(a => `${a.spectral_type} (χ²ᵣ ${num(a.reduced_chi2, 1)})`).join(' · ')}</p>}
              <p className="small">{tmpl.reason}</p>
            </div>
          )}
        </details>
      )}

      {inv.cold_search && (
        <details className="section" open>
          <summary><h3>Is it a cold world?</h3><span className="tag">measured where it should be</span></summary>
          <p className="small muted">{inv.cold_search.method}</p>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Wavelength band</th><th>N</th><th>Flux</th><th>S/N</th><th>Result</th><th>AB mag</th></tr></thead>
              <tbody>
                {inv.cold_search.bands.map(b => (
                  <tr key={b.band}>
                    <td>{b.band}</td>
                    <td className="mono">{b.n}</td>
                    <td className="mono">{b.flux_ujy != null ? `${num(b.flux_ujy, 0)} ± ${num(b.flux_err_ujy, 0)} µJy` : NA}</td>
                    <td className="mono">{num(b.snr, 1)}</td>
                    <td>{b.detected ? 'Detected (S/N ≥ 5)' : b.upper_limit_3sigma_ujy != null ? `Not detected · 3σ limit ${num(b.upper_limit_3sigma_ujy, 0)} µJy` : 'Not detected'}</td>
                    <td className="mono">{num(b.ab_mag, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small dim">Forced photometry measures whatever light falls at the predicted position, including any background source the track crosses. A detection at short wavelengths, where a Y dwarf is expected to be extremely faint, points to contamination and must be checked against the images.</p>
        </details>
      )}

      {inv.demonstration && (
        <section className="demo" aria-label="Wavelength comparison demonstration">
          <p className="eyebrow">A real comparison star</p>
          <h3>Why colour matters, shown on an ordinary star nearby</h3>
          <p className="small">{inv.demonstration.why}</p>
          <div className="demo__cols">
            <div className="demo__col">
              <span className="demo__k">Naive (time order, mixed wavelengths)</span>
              <span className="demo__v mono">{inv.demonstration.naive_max_ratio != null ? `${num(inv.demonstration.naive_max_ratio, 1)}×` : NA}</span>
              <span className="small dim">apparent max/min brightness ratio</span>
            </div>
            <div className="demo__col">
              <span className="demo__k">Wavelength-matched, visit to visit</span>
              {inv.demonstration.matched_visit_pairs.map(v => (
                <span key={v.visit_a + v.visit_b} className="mono small">{v.visit_a} → {v.visit_b}: {pm(v.mean_ratio, v.mean_ratio_err, 3)} ({sig(v.significance_sigma)}, {v.n_bins} channels)</span>
              ))}
              <span className="small dim">Verdict: {humanize(inv.demonstration.variability_status)}</span>
            </div>
          </div>
          <p className="small"><Link href={`/investigation/${encodeURIComponent(inv.demonstration.investigation_id)}`}>Open the comparison star's investigation: {inv.demonstration.title} →</Link></p>
        </section>
      )}

      {inv.variability && !haloOk && (
        <details className="section" open={inv.variability.status === 'variable' || (!compact && inv.variability.status !== 'insufficient')}>
          <summary><h3>Does its brightness change?</h3><span className={`tag tag--${inv.variability.status}`}>{humanize(inv.variability.status)}</span></summary>
          <div className="compare">
            <div>
              <h4>The wrong way: compare any two images</h4>
              <p className="small muted">{inv.variability.naive?.description ?? 'SPHEREx sees each source at a different wavelength in every exposure, so a raw sequence mixes spectral shape with time.'}</p>
              {inv.variability.naive?.max_ratio != null && <p className="small mono">Apparent max/min ratio: {num(inv.variability.naive.max_ratio, 2)}×{inv.variability.naive.max_ratio_basis ? <span className="dim"> ({inv.variability.naive.max_ratio_basis})</span> : null}</p>}
              <NaiveLightCurve variability={inv.variability} />
            </div>
            <div>
              <h4>The right way: compare the same colour</h4>
              <p className="small muted">{inv.variability.matched?.description ?? 'Only exposures at the same wavelength are compared between visits.'}</p>
              {inv.variability.matched?.median_log_ratio != null && (
                <p className="small mono">Median matched change: {num((Math.exp(inv.variability.matched.median_log_ratio) - 1) * 100, 1)}%{inv.variability.matched.chi2_reduced != null ? ` · χ²ᵣ of constancy ${num(inv.variability.matched.chi2_reduced, 1)}` : ''}</p>
              )}
              <MatchedComparisons variability={inv.variability} />
              {inv.variability.matched?.visit_pairs && inv.variability.matched.visit_pairs.length > 0 && (
                <div className="table-wrap"><table className="table table--dense">
                  <thead><tr><th>Visits</th><th>Bins</th><th>Mean ratio</th><th>Significance</th><th>Variable?</th></tr></thead>
                  <tbody>
                    {inv.variability.matched.visit_pairs.map(v => (
                      <tr key={v.visit_a + v.visit_b}>
                        <td>{v.visit_a} → {v.visit_b}</td><td className="mono">{v.n_bins}</td>
                        <td className="mono">{pm(v.mean_ratio, v.mean_ratio_err, 3)}</td>
                        <td className="mono">{sig(v.significance_sigma)}</td><td>{v.variable ? 'Yes' : 'No'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table></div>
              )}
            </div>
          </div>
        </details>
      )}

      {inv.hypotheses?.length > 0 && (
        <details className="section" open>
          <summary><h3>What else could it be?</h3></summary>
          <ul className="hyps">
            {inv.hypotheses.map(h => (
              <li key={h.id} className={`hyp hyp--${h.status}`}>
                <div className="hyp__head"><span className="hyp__id mono">{h.id}</span><span className="hyp__name">{h.name}</span><span className={`tag tag--${h.status}`}>{H_STATUS[h.status] ?? humanize(h.status)}</span></div>
                <ul className="hyp__ev">{h.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>
              </li>
            ))}
          </ul>
        </details>
      )}

      {inv.limitations?.length > 0 && (
        <details className="section">
          <summary><h3>What we can't say</h3></summary>
          <ul className="bullets">{inv.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
        </details>
      )}
      {inv.follow_up?.length > 0 && (
        <details className="section">
          <summary><h3>What to check next</h3></summary>
          <ul className="bullets">{inv.follow_up.map((l, i) => <li key={i}>{l}</li>)}</ul>
        </details>
      )}

      {inv.detections.length > 0 && (
        <details className="section">
          <summary><h3>Every measurement</h3><span className="tag">{inv.detections.length} exposures</span></summary>
          <div className="table-wrap">
            <table className="table table--dense">
              <thead><tr><th>Time (UTC)</th><th>Visit</th><th>Det.</th><th>λ (µm)</th><th>S/N</th><th>σ pos (″)</th><th>Flux (follow)</th><th>Flux (fixed)</th><th>Outcome</th><th>Flags</th></tr></thead>
              <tbody>
                {(allRows ? inv.detections : inv.detections.slice(0, 40)).map(d => (
                  <tr key={d.product_id} className={d.used_for_motion ? '' : 'is-excluded'}>
                    <td className="mono" title={d.product_id}>{dateTime(d.time_utc).replace(' UTC', '')}</td>
                    <td>{d.visit}</td>
                    <td className="mono">D{d.detector}</td>
                    <td className="mono"><span className="swatch" style={{ background: wavelengthColor(d.wavelength_um) }} />{num(d.wavelength_um, 3)}</td>
                    <td className="mono">{num(d.snr, 0)}</td>
                    <td className="mono">{num(d.sigma_arcsec, 2)}</td>
                    <td className="mono">{ujyWithError(d.flux_ujy, d.flux_err_ujy)}</td>
                    <td className="mono">{ujy(d.fixed_flux_ujy)}</td>
                    <td>{humanize(d.outcome)}</td>
                    <td className="small">{d.flags.filter(f => f !== 'SOURCE').join(', ') || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {inv.detections.length > 40 && <button className="button button--ghost" onClick={() => setAllRows(x => !x)}>{allRows ? 'Show first 40' : `Show all ${inv.detections.length}`}</button>}
          <p className="small dim">Greyed rows were not used for the motion fit. Flags are SPHEREx quality bits within 1.5 px of the source (SOURCE is informational and hidden).</p>
        </details>
      )}

      {inv.provenance && (
        <details className="section">
          <summary><h3>Where the data came from</h3></summary>
          <p className="small">{inv.provenance.n_files} native SPHEREx cutouts with SHA-256 checksums. <a href={inv.provenance.manifest_url}>Machine-readable manifest</a>.</p>
          <ProvList title="Datasets" items={inv.provenance.datasets} />
          <ProvList title="Catalogues" items={inv.provenance.catalogs} />
          <ProvList title="Software" items={inv.provenance.software} />
          <p className="small dim">Visits: {visits.join(', ') || NA}</p>
        </details>
      )}
    </article>
  );
}

function ProvList({ title, items }: { title: string; items: Record<string, unknown>[] }) {
  if (!items?.length) return null;
  return (
    <>
      <h4>{title}</h4>
      <ul className="bullets small">
        {items.map((it, i) => (
          <li key={i}>
            {Object.entries(it).filter(([, v]) => v != null && v !== '').map(([k, v]) => {
              const s = typeof v === 'string' ? v : JSON.stringify(v);
              return <span key={k} className="prov-kv"><span className="dim">{humanize(k)}:</span> {s.startsWith('http') ? <a href={s} target="_blank" rel="noreferrer">{s}</a> : s} </span>;
            })}
          </li>
        ))}
      </ul>
    </>
  );
}

export function Progress({ stage, done, total }: { stage: string; done: number; total: number }) {
  const pct = total > 0 ? Math.round((100 * done) / total) : null;
  return (
    <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total || 100} aria-valuenow={done} aria-valuetext={`${humanize(stage)} ${done} of ${total}`}>
      <div className="progress__label"><span>{humanize(stage)}</span><span className="mono">{total > 0 ? `${done}/${total}` : '…'}</span></div>
      <div className="progress__bar"><span style={{ width: pct != null ? `${pct}%` : '30%' }} className={pct == null ? 'is-indeterminate' : ''} /></div>
    </div>
  );
}

export function um2(v: number | null | undefined) { return um(v); }


const monthYear = (iso: string) => new Date(iso).toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });

/** Brightness of a saturated star, measured from the unsaturated ring of light around it. */
function HaloSection({ halo }: { halo: HaloVariability }) {
  const vs = (halo.visits ?? []).filter(v => v.n >= 5);
  const later = vs.slice(1).filter(v => v.sigma != null);
  const big = later.slice().sort((a, b) => Math.abs(b.ratio - 1) - Math.abs(a.ratio - 1))[0];
  const pts = (halo.light_curve ?? []).filter(p => p.matched && p.relative > 0);
  const names = vs.map(v => v.visit);
  const w = 560, h = 250, m = { l: 52, r: 12, t: 12, b: 34 };
  const t0 = Math.min(...pts.map(p => p.mjd)), t1 = Math.max(...pts.map(p => p.mjd));
  const sorted = pts.map(p => Math.log(p.relative)).sort((a, b) => a - b);
  const lo = Math.min(sorted[Math.floor(sorted.length * 0.02)] ?? -0.3, -0.15) - 0.1;
  const hi = Math.max(sorted[Math.floor(sorted.length * 0.98)] ?? 0.3, 0.15) + 0.1;
  const sx = (t: number) => m.l + ((t - t0) / (t1 - t0 || 1)) * (w - m.l - m.r);
  const sy = (r: number) => m.t + (1 - (Math.log(r) - lo) / (hi - lo)) * (h - m.t - m.b);
  const ticks = [0.25, 0.4, 0.6, 0.8, 1, 1.25, 1.6, 2].filter(v => Math.log(v) > lo && Math.log(v) < hi);
  return (
    <details className="section" open>
      <summary><h3>Does its brightness change?</h3><span className={`tag tag--${halo.status === 'variable' ? 'variable' : 'not_detected'}`}>{halo.status === 'variable' ? 'Yes' : 'Steady'}</span></summary>
      <p>
        {halo.status === 'variable' && big
          ? <>It <strong>{big.ratio < 1 ? 'faded' : 'brightened'} by {Math.round(Math.abs(big.ratio - 1) * 100)}%</strong> between {monthYear(vs[0].start_utc)} and {monthYear(big.start_utc)} ({num(big.sigma ?? 0, 1)}σ). </>
          : <>No change larger than the noise{later[0] ? ` (${Math.round(Math.abs(later[0].ratio - 1) * 100)}% between visits)` : ''}. </>}
        The star's core is saturated, so this is measured from the ring of light it scatters {halo.ring_pixels?.[0]}–{halo.ring_pixels?.[1]} pixels away, comparing only images of the same colour.
      </p>
      {pts.length > 3 && (
        <figure className="chart">
          <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Brightness relative to the first visit, against date">
            <rect x={m.l} y={m.t} width={w - m.l - m.r} height={h - m.t - m.b} className="axes__frame" />
            {ticks.map(v => <g key={v}><line x1={m.l} x2={w - m.r} y1={sy(v)} y2={sy(v)} className="axes__grid" /><text x={m.l - 7} y={sy(v) + 4} textAnchor="end" className="axes__tick">{v}×</text></g>)}
            <line x1={m.l} x2={w - m.r} y1={sy(1)} y2={sy(1)} stroke="#8f97ae" strokeDasharray="4 4" />
            {pts.map((p, i) => Math.log(p.relative) > lo && Math.log(p.relative) < hi
              ? <circle key={i} cx={sx(p.mjd)} cy={sy(p.relative)} r={2.6} fill={visitColor(p.visit, names)} fillOpacity={0.85} /> : null)}
            {vs.map(v => {
              const a = Date.parse(v.start_utc) / 86400000 + 40587, b = Date.parse(v.end_utc) / 86400000 + 40587;
              return <line key={v.visit} x1={sx(a) - 4} x2={sx(b) + 4} y1={sy(v.ratio)} y2={sy(v.ratio)} stroke="#f5f5f7" strokeWidth={2} />;
            })}
            {vs.map(v => <text key={v.visit} x={sx(Date.parse(v.start_utc) / 86400000 + 40587)} y={h - 12} className="axes__tick">{monthYear(v.start_utc)}</text>)}
            <text x={14} y={(m.t + h - m.b) / 2} textAnchor="middle" transform={`rotate(-90 14 ${(m.t + h - m.b) / 2})`} className="axes__label">Brightness vs first visit</text>
          </svg>
          <figcaption><span className="legend">Each dot is one image. White bars: the average of each visit.</span></figcaption>
        </figure>
      )}
      <table className="table">
        <thead><tr><th>Visit</th><th>Dates</th><th>Images</th><th>Brightness vs first visit</th></tr></thead>
        <tbody>
          {vs.map((v, i) => (
            <tr key={v.visit}>
              <td>{i + 1}</td><td className="small">{date(v.start_utc)} – {date(v.end_utc)}</td><td className="mono">{v.n}</td>
              <td className="mono">{i === 0 ? '1 (reference)' : `${num(v.ratio, 2)} ± ${num(v.ratio * (v.err_vs_first ?? 0), 2)}${v.sigma != null ? ` (${num(v.sigma, 1)}σ)` : ''}`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small dim">An experimental method. <Link href="/proof">See how it behaves on stars that do not vary →</Link></p>
    </details>
  );
}
