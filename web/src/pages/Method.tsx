import type { ValidationReport, ValidationTarget } from '../api.ts';
import { niceTicks } from '../components/Charts.tsx';
import { Link } from '../router.tsx';
import { NA, date, dateTime, humanize, num, pm, shortHash } from '../lib/format.ts';

const FIELD_COLORS: Record<string, string> = {
  'epsilon-indi-b': '#8fb4ff', 'wise-0855': '#5fd4a8', 'rw-aurigae': '#f2c46b', 'r-draconis': '#ff9a76', 'barnards-star': '#d79bff',
};
const FIELD_NAMES: Record<string, string> = {
  'epsilon-indi-b': 'Epsilon Indi B field', 'wise-0855': 'WISE 0855 field', 'rw-aurigae': 'RW Aurigae field', 'r-draconis': 'R Draconis field', 'barnards-star': "Barnard's Star field",
};

function statusTone(s: string): string {
  const t = s.toLowerCase();
  if (t.startsWith('recovered')) return 'supported';
  if (t.startsWith('detected')) return 'tentative';
  if (t.startsWith('inconclusive')) return 'untestable';
  if (t.startsWith('not')) return 'not_supported';
  return 'untestable';
}

function flagSummary(t: ValidationTarget): string {
  const f = t.flag_counts_near_source ?? {};
  const n = t.cached_products ?? 0;
  const order = ['OVERFLOW', 'NONLINEAR', 'BLOOM', 'SUR_ERROR', 'PERSIST', 'HALO', 'TRANSIENT', 'NONFUNC', 'OUTLIER'];
  const parts = order.filter(k => f[k]).map(k => `${k} ${f[k]}/${n}`);
  return parts.slice(0, 4).join(' · ') || 'none';
}

export function TargetsTable({ targets }: { targets: ValidationTarget[] }) {
  return (
    <div className="table-wrap">
      <table className="table vtable">
        <thead>
          <tr><th>Target</th><th>Data</th><th>Usable positions</th><th>Result</th><th>Key numbers</th><th>Quality flags near source</th></tr>
        </thead>
        <tbody>
          {targets.map(t => (
            <tr key={t.slug}>
              <td>
                <Link href={`/explore?target=${t.slug}`} className="vtable__name">{t.target}</Link>
                <div className="small dim">{t.purpose}</div>
              </td>
              <td className="small">
                <div className="mono">{t.archive_products ?? NA} in archive</div>
                <div className="mono">{t.cached_products ?? NA} cached · {t.visits ?? NA} visits</div>
                <div className="dim">{t.date_range ? `${date(t.date_range[0])} – ${date(t.date_range[1])}` : NA}</div>
              </td>
              <td className="mono vtable__num">{t.usable_positions ?? NA}</td>
              <td><span className={`vstatus tone--${statusTone(t.recovery_status)}`}>{t.recovery_status}</span></td>
              <td className="small">
                <dl className="kn">
                  <dt>Proper motion</dt><dd className="mono">{t.pm_total_masyr != null ? pm(t.pm_total_masyr, t.pm_total_err_masyr, 0, 'mas/yr') : NA}</dd>
                  <dt>Parallax</dt><dd className="mono">{t.parallax_mas != null ? pm(t.parallax_mas, t.parallax_err_mas, 0, 'mas') : NA}</dd>
                  <dt>Template</dt><dd className="mono">{t.template ? `${t.template}${t.template_rchi2 != null ? ` (χ²ᵣ ${num(t.template_rchi2, 2)})` : ''}` : NA}</dd>
                  <dt>Fixed / follow</dt><dd className="mono">{t.fixed_vs_follow_ratio != null ? num(t.fixed_vs_follow_ratio, 2) : NA}</dd>
                  <dt>Variability</dt><dd>{t.variability_status ? humanize(t.variability_status) : NA}</dd>
                </dl>
              </td>
              <td className="small mono">{flagSummary(t)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const MODEL_LABELS: [string, string, string][] = [
  ['primary', 'SPHEREx-only motion + parallax', 'independent'],
  ['catalog_parallax', 'SPHEREx motion, catalogue parallax', 'catalogue-assisted'],
  ['catalog_full', 'Gaia DR3 propagation', 'catalogue-assisted'],
  ['stationary_null', '“Stays here” (stationary)', 'null'],
];

export function ExperimentCard({ e }: { e: ValidationReport['experiments'][number] }) {
  return (
    <div className="vcard">
      <div className="vcard__head">
        <div>
          <p className="eyebrow">Held-out prediction · {e.target}</p>
          <h3>{e.classification}</h3>
        </div>
        <span className={`vbig vbig--${e.primary_verdict === 'PASS' ? 'pass' : 'fail'}`}>{e.primary_verdict}</span>
      </div>
      <div className="vnums">
        <div><span className="vnums__n mono">{e.training_usable}</span><span>usable training exposures (of {e.training_products})</span></div>
        <div><span className="vnums__n mono">{e.heldout_usable ?? e.result?.primary?.n_usable ?? NA}</span><span>usable held-out exposures (of {e.heldout_products})</span></div>
        <div><span className="vnums__n mono">{num(e.result?.primary?.residual_arcsec, 3)}″</span><span>residual from the locked prediction</span></div>
      </div>
      <p className="small"><strong>Criterion:</strong> {e.criterion}</p>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Locked prediction</th><th>Kind</th><th>Residual</th><th>d²</th><th>Verdict</th></tr></thead>
          <tbody>
            {MODEL_LABELS.map(([k, label, kind]) => {
              const r = e.result?.[k];
              if (!r) return null;
              return (
                <tr key={k} className={k === 'primary' ? 'is-preferred' : ''}>
                  <td>{label}</td><td className="small">{kind}</td>
                  <td className="mono">{num(r.residual_arcsec, 3)}″</td>
                  <td className="mono">{r.mahalanobis_d2 > 9999 ? num(r.mahalanobis_d2, 0) : num(r.mahalanobis_d2, 2)}</td>
                  <td><span className={`tag tag--${r.verdict === 'PASS' ? 'supported' : 'disfavored'}`}>{r.verdict}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="small dim">Locked {dateTime(e.locked_utc)} · SHA-256 <span className="mono">{shortHash(e.prediction_sha256, 16)}…</span> · </p>
    </div>
  );
}

export function ControlsScatter({ results, sigma }: { results: ValidationReport['negative_controls']['results']; sigma: number }) {
  const pts = results.filter(r => r.pm_total != null && r.pm_total_err != null && Number.isFinite(r.pm_total) && Number.isFinite(r.pm_total_err));
  if (!pts.length) return null;
  const w = 460, h = 320, m = { l: 58, r: 14, t: 14, b: 42 };
  const xmax = Math.max(...pts.map(p => p.pm_total_err!)) * 1.15;
  const ymax = Math.max(...pts.map(p => p.pm_total!)) * 1.35;
  const sx = (v: number) => m.l + (v / xmax) * (w - m.l - m.r);
  const sy = (v: number) => m.t + (1 - v / ymax) * (h - m.t - m.b);
  const fields = [...new Set(pts.map(p => p.field))];
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Negative controls: measured proper motion versus its uncertainty">
        <rect x={m.l} y={m.t} width={w - m.l - m.r} height={h - m.t - m.b} className="axes__frame" />
        {niceTicks(0, xmax, 5).map(t => <g key={'x' + t}><line x1={sx(t)} x2={sx(t)} y1={m.t} y2={h - m.b} className="axes__grid" /><text x={sx(t)} y={h - m.b + 15} textAnchor="middle" className="axes__tick">{t}</text></g>)}
        {niceTicks(0, ymax, 5).map(t => <g key={'y' + t}><line x1={m.l} x2={w - m.r} y1={sy(t)} y2={sy(t)} className="axes__grid" /><text x={m.l - 7} y={sy(t) + 4} textAnchor="end" className="axes__tick">{t}</text></g>)}
        <polygon points={`${sx(0)},${sy(0)} ${sx(xmax)},${sy(Math.min(sigma * xmax, ymax))} ${sx(xmax)},${sy(ymax)} ${sx(0)},${sy(ymax)}`} className="vscatter__zone" />
        <line x1={sx(0)} y1={sy(0)} x2={sx(Math.min(xmax, ymax / sigma))} y2={sy(Math.min(sigma * xmax, ymax))} className="vscatter__line" />
        <text x={sx(Math.min(xmax, ymax / sigma)) - 6} y={sy(Math.min(sigma * xmax, ymax)) + 14} textAnchor="end" className="chart__note" fill="#ff8a7a">{sigma}σ: would be flagged as moving</text>
        {pts.map((p, i) => <circle key={i} cx={sx(p.pm_total_err!)} cy={sy(p.pm_total!)} r={3.6} fill={FIELD_COLORS[p.field] ?? '#ccc'} fillOpacity={0.85} stroke="#05070a" />)}
        <text x={(m.l + w - m.r) / 2} y={h - 6} textAnchor="middle" className="axes__label">Uncertainty of measured proper motion (mas/yr)</text>
        <text x={14} y={(m.t + h - m.b) / 2} textAnchor="middle" transform={`rotate(-90 14 ${(m.t + h - m.b) / 2})`} className="axes__label">Measured |μ| (mas/yr)</text>
      </svg>
      <figcaption>{fields.map(f => <span key={f} className="legend"><span className="legend__dot" style={{ background: FIELD_COLORS[f] ?? '#ccc' }} /> {FIELD_NAMES[f] ?? f}</span>)}</figcaption>
    </figure>
  );
}

const PM_ROWS = [0, 300, 1000, 4000];
const FLUX_COLS = [30, 100, 300, 1000];
const OUTCOME_LABEL: Record<string, string> = {
  recovered: 'Recovered', missed: 'Missed', correctly_stationary: 'Correctly stationary', false_positive: 'False positive', not_detected: 'Not detected',
};

export function InjectionGrid({ inj }: { inj: NonNullable<ValidationReport['injections']> }) {
  const cell = (pmv: number, f: number) => inj.results.find(r => r.injected_pm_masyr === pmv && r.injected_flux_ujy === f);
  return (
    <div className="inj">
      <div className="inj__label" role="note"><strong>{inj.label || 'SYNTHETIC — not real sources'}</strong></div>
      <p className="small muted">{inj.description}</p>
      <div className="inj__wrap">
        <div className="inj__grid" role="table" aria-label="Synthetic injection outcomes">
          <div className="inj__corner small dim" role="columnheader">injected μ ↓ · flux →</div>
          {FLUX_COLS.map(f => <div key={f} className="inj__colh mono small" role="columnheader">{f} µJy</div>)}
          {PM_ROWS.map(pmv => (
            <div key={pmv} className="inj__row" role="row">
              <div className="inj__rowh mono small" role="rowheader">{pmv === 0 ? 'stationary' : `${pmv} mas/yr`}</div>
              {FLUX_COLS.map(f => {
                const r = cell(pmv, f);
                const o = r?.outcome ?? 'missing';
                return (
                  <div key={f} className={`inj__cell inj--${o}`} role="cell" title={r ? `${r.n_detected}/${r.n_frames} exposures detected${r.median_snr != null ? `, median S/N ${num(r.median_snr, 1)}` : ''}` : 'not run'}>
                    <span className="inj__o">{OUTCOME_LABEL[o] ?? (r ? humanize(o) : 'not run')}</span>
                    {r?.recovered_pm_masyr != null && <span className="mono inj__pm">{num(r.recovered_pm_masyr, 0)} ± {num(r.recovered_pm_err_masyr, 0)}</span>}
                    {r && <span className="inj__n small">{r.n_detected}/{r.n_frames} det.</span>}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
      <p className="small dim">Cells show the outcome and the recovered proper motion (mas/yr). “Missed” means the source was measured but its motion did not pass the pre-set thresholds.</p>
    </div>
  );
}

export const THRESHOLD_LABELS: Record<string, string> = {
  motion_equivalent_sigma: 'Motion: stationary model rejected at ≥ (σ)',
  motion_pm_over_error: 'Motion: |μ| / σ_μ ≥',
  position_snr_min: 'Usable position: S/N ≥',
  min_positions: 'Minimum usable positions for a motion fit',
  variability_sigma: 'Variability: wavelength-matched change ≥ (σ)',
  variability_min_amplitude: 'Variability: minimum fractional amplitude',
  template_max_reduced_chi2: 'Template accepted if reduced χ² <',
};

