import { Page } from '../components/Shell.tsx';
import { useInvestigation } from '../hooks.ts';
import { exportUrl } from '../api.ts';
import { Link } from '../router.tsx';
import { formatDec, formatRA } from '../lib/astro.ts';
import { NA, date, dateTime, humanize, num, pm, sig } from '../lib/format.ts';
import { MotionPlot, SpectrumPlot } from '../components/Charts.tsx';

export function Evidence({ id }: { id: string }) {
  const { data: inv, error, loading } = useInvestigation(id);
  if (error) return <Page><p className="notice notice--bad">{error}</p></Page>;
  if (loading || !inv) return <Page><p className="muted">Loading evidence dossier…</p></Page>;
  const m = inv.motion;
  const modelId = m?.reported_model ?? m?.preferred_model;
  const rep = modelId ? m?.models[modelId] : null;
  const t = inv.spectrum?.templates;
  const used = inv.detections.filter(d => d.used_for_motion);
  return (
    <Page>
      <div className="dossier">
        <div className="dossier__tools no-print">
          <Link className="button button--ghost button--small" href={`/explore?field=${encodeURIComponent(inv.field_id)}&inv=${encodeURIComponent(inv.id)}`}>Open in viewer</Link>
          <a className="button button--ghost button--small" href={exportUrl(inv.id, 'json')}>Download JSON</a>
          <a className="button button--ghost button--small" href={exportUrl(inv.id, 'csv')}>Download CSV</a>
          <button className="button button--primary button--small" onClick={() => window.print()}>Print / save PDF</button>
        </div>
        <header className="dossier__head">
          <p className="eyebrow">PARALLAX evidence dossier</p>
          <h1>{inv.title}</h1>
          <p className="mono small">Candidate ID: {inv.id} · generated {dateTime(inv.created_utc)}</p>
        </header>

        <section>
          <h2>Verdict</h2>
          <p className="dossier__headline">{inv.summary?.headline ?? NA}</p>
          <p>{inv.summary?.one_liner}</p>
          <ul className="bullets">{inv.summary?.verdicts.map(v => <li key={v.code}><strong>{v.label}</strong> — {humanize(v.strength)}</li>)}</ul>
        </section>

        <section className="dossier__grid">
          <div>
            <h2>Position</h2>
            <dl className="kv">
              <dt>RA, Dec (ICRS)</dt><dd className="mono">{formatRA(inv.source.ra)} {formatDec(inv.source.dec)}</dd>
              <dt>Decimal</dt><dd className="mono">{inv.source.ra.toFixed(6)}°, {inv.source.dec.toFixed(6)}°</dd>
              <dt>Reference epoch</dt><dd className="mono">{rep ? `MJD ${num(rep.reference.t0_mjd, 2)}` : NA}</dd>
              <dt>Data source</dt><dd>NASA SPHEREx Level 2 spectral images (DR1, QR3) via NASA/IPAC IRSA</dd>
            </dl>
          </div>
          <div>
            <h2>Observations</h2>
            <dl className="kv">
              <dt>Exposures examined</dt><dd className="mono">{inv.observations?.n_total ?? NA}</dd>
              <dt>Usable positions</dt><dd className="mono">{inv.observations?.n_usable_positions ?? NA}</dd>
              <dt>Date range</dt><dd className="mono">{inv.observations?.date_range ? `${date(inv.observations.date_range[0])} – ${date(inv.observations.date_range[1])}` : NA}</dd>
              <dt>Wavelengths</dt><dd className="mono">{inv.observations?.wavelength_coverage_um ? `${inv.observations.wavelength_coverage_um[0].toFixed(2)}–${inv.observations.wavelength_coverage_um[1].toFixed(2)} µm` : NA}</dd>
            </dl>
          </div>
        </section>

        {m && (
          <section>
            <h2>Motion</h2>
            <p>Status: <strong>{humanize(m.status)}</strong>. Reported model: {modelId ? humanize(modelId) : NA}.</p>
            <dl className="kv">
              <dt>μα cos δ</dt><dd className="mono">{pm(rep?.pmra_masyr, rep?.pmra_err_masyr, 1, 'mas/yr')}</dd>
              <dt>μδ</dt><dd className="mono">{pm(rep?.pmdec_masyr, rep?.pmdec_err_masyr, 1, 'mas/yr')}</dd>
              <dt>Total</dt><dd className="mono">{pm(rep?.pm_total_masyr, rep?.pm_total_err_masyr, 1, 'mas/yr')}</dd>
              <dt>Parallax</dt><dd className="mono">{pm(rep?.parallax_mas, rep?.parallax_err_mas, 1, 'mas')}</dd>
              <dt>Reduced χ²</dt><dd className="mono">{num(rep?.chi2_reduced, 2)} ({rep?.n_points ?? NA} positions)</dd>
              <dt>vs stationary</dt><dd className="mono">{m.significance ? `Δχ² ${num(m.significance.delta_chi2, 1)} (${sig(m.significance.equivalent_sigma)})` : NA}</dd>
              <dt>Baseline</dt><dd className="mono">{num(m.baseline_days, 0)} days</dd>
              {m.catalog_comparison && <><dt>Catalogue</dt><dd className="small">{m.catalog_comparison.source}: {num(m.catalog_comparison.pmra_masyr, 1)}, {num(m.catalog_comparison.pmdec_masyr, 1)} mas/yr; Δ = {sig(m.catalog_comparison.d_pmra_sigma)}, {sig(m.catalog_comparison.d_pmdec_sigma)}</dd></>}
            </dl>
            {m.points.length > 0 && <MotionPlot motion={m} />}
          </section>
        )}

        {inv.spectrum && (
          <section>
            <h2>Spectrum</h2>
            <p className="small">{inv.spectrum.method}</p>
            {inv.spectrum.binned.some(b => b.flux_ujy != null) && <SpectrumPlot spectrum={inv.spectrum} showFixed={false} showRaw={false} />}
            <p className="small">Coverage {inv.spectrum.coverage.n_bins_filled}/{inv.spectrum.coverage.n_bins_total} channels. {t ? `Template: ${t.best ? `${t.best.spectral_type} (${t.best.grid_type}), χ²ᵣ ${num(t.best.reduced_chi2, 2)}` : humanize(t.status)} — ${t.reason}` : ''}</p>
          </section>
        )}

        <section>
          <h2>Hypotheses</h2>
          <table className="table">
            <thead><tr><th>ID</th><th>Explanation</th><th>Status</th><th>Evidence</th></tr></thead>
            <tbody>{inv.hypotheses.map(h => <tr key={h.id}><td className="mono">{h.id}</td><td>{h.name}</td><td>{humanize(h.status)}</td><td className="small">{h.evidence.join(' ')}</td></tr>)}</tbody>
          </table>
        </section>

        <section className="dossier__grid">
          <div><h2>Limitations</h2><ul className="bullets small">{inv.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></div>
          <div><h2>Follow-up</h2><ul className="bullets small">{inv.follow_up.map((l, i) => <li key={i}>{l}</li>)}</ul></div>
        </section>

        <section>
          <h2>Quality flags</h2>
          <p className="small">{Object.entries((inv.observations?.quality?.flag_counts_near_source as Record<string, number>) ?? {}).map(([k, v]) => `${k}: ${v}`).join(' · ') || NA}</p>
          <p className="small dim">Counts of exposures with each SPHEREx quality bit set within 1.5 px of the source.</p>
        </section>

        <section>
          <h2>Observation list</h2>
          <p className="small dim">{used.length} exposures used for motion; full table in the CSV export.</p>
          <div className="table-wrap">
            <table className="table table--dense">
              <thead><tr><th>Product</th><th>Time (UTC)</th><th>λ (µm)</th><th>RA</th><th>Dec</th><th>σ (″)</th><th>Outcome</th></tr></thead>
              <tbody>
                {inv.detections.slice(0, 60).map(d => (
                  <tr key={d.product_id}><td className="mono small">{d.product_id}</td><td className="mono small">{d.time_utc.slice(0, 19)}</td><td className="mono">{num(d.wavelength_um, 3)}</td><td className="mono">{num(d.ra, 6)}</td><td className="mono">{num(d.dec, 6)}</td><td className="mono">{num(d.sigma_arcsec, 2)}</td><td>{humanize(d.outcome)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          {inv.detections.length > 60 && <p className="small dim">… {inv.detections.length - 60} more in the export.</p>}
        </section>

        <section>
          <h2>Citations and provenance</h2>
          <ul className="bullets small">
            {inv.provenance?.datasets.map((d, i) => <li key={'d' + i}>{String(d.citation ?? d.name)}</li>)}
            {inv.provenance?.catalogs.map((d, i) => <li key={'c' + i}>{String(d.name)}{d.url ? <> — <a href={String(d.url)}>{String(d.url)}</a></> : null}</li>)}
            <li>Software: {inv.provenance?.software.map(s => `${s.name}${s.version ? ' ' + s.version : ''}`).join(', ')}</li>
          </ul>
          {inv.provenance && <p className="small">Per-file SHA-256 manifest: <a href={inv.provenance.manifest_url}>{inv.provenance.manifest_url}</a></p>}
          <p className="small dim">PARALLAX is not affiliated with or endorsed by NASA. Measurements are deterministic and reproducible from the listed files; no AI model produced any number in this dossier.</p>
        </section>
      </div>
    </Page>
  );
}
