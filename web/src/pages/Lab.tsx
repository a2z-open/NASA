import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { api, cachedFrame, loadFrames, type Field, type Frame, type LabExperiment } from '../api.ts';
import { SkyCanvas, type Overlays, type SkyCanvasHandle } from '../components/SkyCanvas.tsx';
import { ResidualPlot, niceTicks, visitColor, type ResidualPoint } from '../components/Charts.tsx';
import { Term } from '../components/Term.tsx';
import { useAsync, useField } from '../hooks.ts';
import { formatDec, formatRA, fromTangent, percentile } from '../lib/astro.ts';
import { stack as stackFrames } from '../lib/compose.ts';
import { NA, date, dateTime, num, pm, shortHash, sig } from '../lib/format.ts';
import { Link } from '../router.tsx';

type Guess = 'stays' | 'follows' | null;

/** The lock -> guess -> reveal experiments. Rendered inside the Proof page. */
export function Experiments() {
  const lab = useAsync(() => api.lab(), []);
  const exps = lab.data?.experiments ?? [];
  return (
    <>
      {lab.error && <p className="notice notice--bad">The experiments could not be loaded: {lab.error}</p>}
      {lab.loading && <p className="muted">Loading…</p>}
      {exps.map(e => <Experiment key={e.id} e={e} />)}
    </>
  );
}

function Experiment({ e }: { e: LabExperiment }) {
  const [guess, setGuess] = useState<Guess>(null);
  const [revealed, setRevealed] = useState(false);
  const P = e.prediction;
  const R = e.result;
  const primary = P?.predictions?.primary;
  const crit = P?.protocol?.criterion as string | undefined;
  const trainingVisits = (P?.training?.visits ?? []) as { id: string; start_utc: string; end_utc: string; n_products: number }[];
  const held = P?.held_out;
  const evals = R?.evaluations ?? {};
  const pe = evals.primary;
  const pred = e.predicted_at_mean_epoch;
  const canReveal = !!R;

  return (
    <section className="exp" aria-labelledby={`exp-${e.id}`}>
      <div className="exp__head">
        <h2 id={`exp-${e.id}`}>{e.title}</h2>
        <p className="mono small dim">{e.id}</p>
      </div>

      {/* Stage 2 */}
      <div className="stage">
        <div className="stage__n mono">1</div>
        <div className="stage__body">
          <h3>Your guess</h3>
          <p className="muted">New images of this star were sealed. Where will it be in them?</p>
          <div className="guess" role="radiogroup" aria-label="Your prediction">
            <button role="radio" aria-checked={guess === 'stays'} className={`guess__btn${guess === 'stays' ? ' is-on' : ''}`} onClick={() => !revealed && setGuess('stays')} disabled={revealed}>
              <strong>It stays put</strong><span>It is a distant background star.</span>
            </button>
            <button role="radio" aria-checked={guess === 'follows'} className={`guess__btn${guess === 'follows' ? ' is-on' : ''}`} onClick={() => !revealed && setGuess('follows')} disabled={revealed}>
              <strong>It keeps moving</strong><span>It will be on the predicted path.</span>
            </button>
          </div>
        </div>
      </div>

      {/* Stage 3 */}
      <div className="stage">
        <div className="stage__n mono">2</div>
        <div className="stage__body">
          <h3>Open the sealed images</h3>
          {!canReveal && <p className="notice">This prediction is locked. The sealed images have not been opened yet.</p>}
          {canReveal && !revealed && (
            <button className="button button--primary button--reveal" onClick={() => setRevealed(true)}>Open them</button>
          )}
          {canReveal && revealed && pe && (
            <div className="reveal">
              <div className={`verdict-banner verdict-banner--${pe.verdict === 'PASS' ? 'pass' : pe.verdict === 'FAIL' ? 'fail' : 'neutral'}`}>
                <span className="verdict-banner__v">{pe.verdict}</span>
                <span>
                  The star landed <strong className="mono">{num(pe.residual_arcsec, 3)}″</strong> from the locked prediction, inside the limit set in advance.
                  {evals.stationary_null && <> “It stays put” missed by <strong className="mono">{num(evals.stationary_null.residual_arcsec, 2)}″</strong>.</>}
                  <span className="small dim"> {pe.n_usable} new images; <Term t="d²">d²</Term> = {num(pe.mahalanobis_d2, 2)}, limit 11.83.</span>
                </span>
              </div>
              {guess && (
                <p className="guess-result">
                  You guessed <strong>{guess === 'stays' ? '“it stays put”' : '“it keeps moving”'}</strong>.{' '}
                  {evals.stationary_null?.verdict === 'FAIL' && pe.verdict === 'PASS'
                    ? (guess === 'follows' ? 'Right: it kept moving.' : `It moved. “Stays put” would have missed by ${num(evals.stationary_null.residual_arcsec, 2)}″.`)
                    : 'See the table below for how each prediction fared.'}
                </p>
              )}
              <p className="classification">{R.classification}</p>
              <div className="reveal__grid">
                <RevealSky e={e} />
                <div>
                  {pred && (
                    <ResidualPlot
                      cov={[[pred.cov_arcsec2[0][0] + (pe.measurement_sigma_arcsec ?? 0) ** 2, pred.cov_arcsec2[0][1]], [pred.cov_arcsec2[1][0], pred.cov_arcsec2[1][1] + (pe.measurement_sigma_arcsec ?? 0) ** 2]]}
                      nsigma={Math.sqrt(11.83)}
                      measurementSigma={pe.measurement_sigma_arcsec ?? null}
                      points={residualPoints(evals)}
                    />
                  )}
                  <p className="small dim">Origin = locked SPHEREx-only prediction. Ellipses use prediction + measurement covariance. Squares show where the other locked predictions put the source.</p>
                </div>
              </div>
              <TrackPlot e={e} />
              <details className="more">
                <summary>All four locked predictions, compared</summary>
              <table className="table">
                <thead><tr><th>Locked prediction</th><th>Kind</th><th>Residual</th><th>d²</th><th>Result</th></tr></thead>
                <tbody>
                  {[
                    ['primary', 'SPHEREx-only motion + parallax', 'independent'],
                    ['catalog_parallax', 'SPHEREx motion, catalogue parallax', 'catalogue-assisted'],
                    ['catalog_full', 'Gaia DR3 propagation', 'catalogue-assisted'],
                    ['stationary_null', '“Stays here”', 'null'],
                  ].map(([k, label, kind]) => {
                    const v = evals[k];
                    if (!v) return null;
                    return (
                      <tr key={k} className={k === 'primary' ? 'is-preferred' : ''}>
                        <td>{label}</td><td className="small">{kind}</td>
                        <td className="mono">{num(v.residual_arcsec, 3)}″</td>
                        <td className="mono">{v.mahalanobis_d2 > 9999 ? num(v.mahalanobis_d2, 0) : num(v.mahalanobis_d2, 2)}</td>
                        <td><span className={`tag tag--${v.verdict === 'PASS' ? 'supported' : 'disfavored'}`}>{v.verdict}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="small">The Gaia DR3 propagation misses by {num(evals.catalog_full?.residual_arcsec, 2)}″ with only its tiny formal errors. Epsilon Indi B is an unresolved brown-dwarf binary (Gaia RUWE 4.3): its light centre moves with the orbit and differs between Gaia's optical band and SPHEREx's infrared, so a catalogue position is not a substitute for measuring the source in the same instrument.</p>
              </details>
              <details className="more">
                <summary>Protocol and disclosures</summary>
                <dl className="kv small">
                  <dt>Held-out rule</dt><dd>{P?.protocol?.held_out_rule}</dd>
                  <dt>Training rule</dt><dd>{P?.protocol?.training_rule}</dd>
                  {P?.protocol?.measurement && Object.entries(P.protocol.measurement as Record<string, string>).map(([k, v]) => <Fragment key={k}><dt>{k.replace(/_/g, ' ')}</dt><dd>{v}</dd></Fragment>)}
                  <dt>Held-out pixels before lock</dt><dd>{held?.pixels_inspected_before_lock === false ? 'None inspected. ' : ''}{held?.note}</dd>
                  <dt>Revealed</dt><dd className="mono">{dateTime(R?.revealed_utc)} · result commit {e.result_commit ? shortHash(e.result_commit.hash) : NA}</dd>
                  <dt>Held-out data</dt><dd>{R?.held_out_measured?.n_downloaded} of {R?.held_out_measured?.n_products} products downloaded, {R?.held_out_measured?.n_usable} usable.</dd>
                </dl>
                <p className="eyebrow">Disclosures (verbatim)</p>
                <ul className="bullets small">{(P?.disclosures ?? []).map((d: string, i: number) => <li key={i}>{d}</li>)}</ul>
              </details>
            </div>
          )}
        </div>
      </div>
      <details className="more">
        <summary>How the prediction was locked</summary>
        <p className="small muted" style={{ marginBottom: 12 }}>The prediction was computed from the earlier visits only, hashed, and committed to git before any image of the new visit was downloaded.</p>
        <div className="lock">
            <dl className="kv">
              <dt>Target</dt><dd>{P?.target?.title} <span className="dim small">({P?.target?.catalogue})</span></dd>
              <dt>Training visits</dt><dd className="small">{trainingVisits.map(v => `${date(v.start_utc)} – ${date(v.end_utc)}`).join(' · ')} <span className="dim">({P?.training?.n_products} exposures, {P?.training?.n_usable_positions} usable positions)</span></dd>
              <dt>Held-out visit</dt><dd className="small">{held?.visit ? `${date(held.visit.start_utc)} – ${date(held.visit.end_utc)}` : NA} · {held?.n_products} products · mean epoch {dateTime(held?.mean_epoch_utc)}</dd>
              <dt>Predicted position</dt><dd className="mono">{primary ? `${formatRA(primary.ra_deg, 3)} ${formatDec(primary.dec_deg, 2)}` : NA}<br /><span className="small dim">{primary ? `${primary.ra_deg.toFixed(7)}°, ${primary.dec_deg.toFixed(7)}°` : ''}</span></dd>
              <dt>Uncertainty (1σ)</dt><dd className="mono">{primary ? `${num(Math.sqrt(primary.cov_arcsec2[0][0]), 3)}″ (RA) × ${num(Math.sqrt(primary.cov_arcsec2[1][1]), 3)}″ (Dec)` : NA}</dd>
              <dt>Model</dt><dd className="small">{P?.protocol?.primary_model}</dd>
              <dt>From training alone</dt><dd className="mono small">μ = {pm(primary?.summary?.pm_total_masyr, primary?.summary?.pm_total_err_masyr, 0, 'mas/yr')} · ϖ = {pm(primary?.summary?.parallax_mas, primary?.summary?.parallax_err_mas, 0, 'mas')}</dd>
              <dt>Locked</dt><dd className="mono small">{dateTime(P?.locked_utc)}</dd>
              <dt>SHA-256</dt><dd className="mono small hash">{e.prediction_sha256}</dd>
              <dt>Git commit</dt><dd className="mono small">{e.prediction_commit ? `${shortHash(e.prediction_commit.hash)} · ${e.prediction_commit.time}` : 'not committed'}</dd>
            </dl>
            <div className="criterion">
              <p className="eyebrow">Pre-registered criterion (verbatim)</p>
              <blockquote>{crit ?? NA}</blockquote>
              <p className="small dim">Comparison predictions were locked at the same time: SPHEREx motion with catalogue parallax, full Gaia DR3 propagation (catalogue-assisted), and “stays here” (stationary null).</p>
            </div>
        </div>
      </details>
      <p className="small dim">Open this field in the <Link href={`/explore?field=${encodeURIComponent(e.field_id)}&inv=${encodeURIComponent(e.target)}`}>viewer</Link> · files: <code>validation/experiments/{e.target}/prediction.json</code>, <code>result.json</code>.</p>
    </section>
  );
}

function residualPoints(evals: Record<string, any>): ResidualPoint[] {
  const p = evals.primary;
  if (!p) return [];
  const r0 = p.mean_residual_arcsec;
  const pts: ResidualPoint[] = [{ dx: r0.dra_cosdec, dy: r0.ddec, label: 'measured (held-out mean)', color: '#5fd4a8', kind: 'measured' }];
  const add = (k: string, label: string, color: string) => {
    const v = evals[k];
    if (!v?.mean_residual_arcsec) return;
    // model position relative to primary = r_primary - r_model
    pts.push({ dx: r0.dra_cosdec - v.mean_residual_arcsec.dra_cosdec, dy: r0.ddec - v.mean_residual_arcsec.ddec, label, color, kind: 'model' });
  };
  add('catalog_full', 'Gaia DR3 propagation', '#8fb4ff');
  add('stationary_null', '“stays here”', '#ff8a7a');
  return pts;
}

function TrackPlot({ e }: { e: LabExperiment }) {
  const w = 720, h = 380, m = { l: 56, r: 16, t: 14, b: 40 };
  const train = e.points.filter(p => p.set === 'training');
  const held = e.points.filter(p => p.set === 'heldout');
  const all = [...e.points, ...e.predicted_track];
  let xmin = Math.min(...all.map(p => -p.xi)), xmax = Math.max(...all.map(p => -p.xi));
  let ymin = Math.min(...all.map(p => p.eta)), ymax = Math.max(...all.map(p => p.eta));
  const pad = 0.6; xmin -= pad; xmax += pad; ymin -= pad; ymax += pad;
  const pw = w - m.l - m.r, ph = h - m.t - m.b;
  const span = Math.max((xmax - xmin) / pw, (ymax - ymin) / ph);
  const cx = (xmin + xmax) / 2, cy = (ymin + ymax) / 2;
  xmin = cx - span * pw / 2; xmax = cx + span * pw / 2; ymin = cy - span * ph / 2; ymax = cy + span * ph / 2;
  const sx = (v: number) => m.l + ((v - xmin) / (xmax - xmin)) * pw;
  const sy = (v: number) => m.t + (1 - (v - ymin) / (ymax - ymin)) * ph;
  const lastTrainMjd = Math.max(...train.map(p => p.mjd));
  const pathTrain = e.predicted_track.filter(p => p.mjd <= lastTrainMjd).map((p, i) => `${i ? 'L' : 'M'}${sx(-p.xi).toFixed(1)},${sy(p.eta).toFixed(1)}`).join('');
  const pathPred = e.predicted_track.filter(p => p.mjd >= lastTrainMjd - 1).map((p, i) => `${i ? 'L' : 'M'}${sx(-p.xi).toFixed(1)},${sy(p.eta).toFixed(1)}`).join('');
  const visits = ['training', 'heldout'];
  const ticksX = niceTicks(xmin, xmax, 8);
  const ticksY = niceTicks(ymin, ymax, 5);
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Training positions, the locked track and the held-out positions">
        <rect x={m.l} y={m.t} width={pw} height={ph} className="axes__frame" />
        {[...new Set(ticksX)].map(t => <g key={'x' + t}><line x1={sx(t)} x2={sx(t)} y1={m.t} y2={h - m.b} className="axes__grid" /><text x={sx(t)} y={h - m.b + 15} textAnchor="middle" className="axes__tick">{-t || 0}</text></g>)}
        {[...new Set(ticksY)].map(t => <g key={'y' + t}><line x1={m.l} x2={w - m.r} y1={sy(t)} y2={sy(t)} className="axes__grid" /><text x={m.l - 7} y={sy(t) + 4} textAnchor="end" className="axes__tick">{t}</text></g>)}
        <text x={(m.l + w - m.r) / 2} y={h - 6} textAnchor="middle" className="axes__label">Δα cos δ (arcsec, east ←)</text>
        <text x={14} y={(m.t + h - m.b) / 2} textAnchor="middle" transform={`rotate(-90 14 ${(m.t + h - m.b) / 2})`} className="axes__label">Δδ (arcsec)</text>
        <path d={pathTrain} className="chart__model" />
        <path d={pathPred} className="chart__model chart__model--pred" />
        {train.map((p, i) => <circle key={'t' + i} cx={sx(-p.xi)} cy={sy(p.eta)} r={1.6} fill={visitColor('training', visits)} opacity={0.7} />)}
        {held.map((p, i) => <circle key={'h' + i} cx={sx(-p.xi)} cy={sy(p.eta)} r={2} fill="#5fd4a8" className="reveal-dot" style={{ animationDelay: `${Math.min(i * 8, 900)}ms` }} />)}
        {e.predicted_at_mean_epoch && (
          <g>
            <path d={`M${sx(-e.predicted_at_mean_epoch.xi) - 8},${sy(e.predicted_at_mean_epoch.eta)}h16M${sx(-e.predicted_at_mean_epoch.xi)},${sy(e.predicted_at_mean_epoch.eta) - 8}v16`} stroke="#ffa269" strokeWidth={1.6} />
            <text x={sx(-e.predicted_at_mean_epoch.xi) + 10} y={sy(e.predicted_at_mean_epoch.eta) - 10} className="chart__note" fill="#ffa269">locked prediction</text>
          </g>
        )}
      </svg>
      <figcaption>
        <span className="legend"><span className="legend__dot" style={{ background: visitColor('training', visits) }} /> training exposures ({train.length})</span>
        <span className="legend"><span className="legend__dot" style={{ background: '#5fd4a8' }} /> held-out exposures ({held.length})</span>
        <span className="legend"><span className="legend__dash" /> fitted model (training) and its extrapolation</span>
        <span className="legend">The wiggle is parallax: Earth's orbit shifts the apparent position each year.</span>
      </figcaption>
    </figure>
  );
}

function RevealSky({ e }: { e: LabExperiment }) {
  const { data: field } = useField(e.field_id);
  const [which, setWhich] = useState<'heldout' | 'training'>('heldout');
  const [blink, setBlink] = useState(false);
  const [tick, setTick] = useState(0);
  const sky = useRef<SkyCanvasHandle>(null);
  const sets = useMemo(() => pickSets(field, e), [field, e]);
  useEffect(() => {
    if (!field?.grid) return;
    const urls = [...sets.heldout, ...sets.training].map(f => f.data_url);
    loadFrames(urls, field.grid.dtype, undefined, 6).then(() => setTick(t => t + 1));
  }, [field, sets]);
  useEffect(() => {
    if (!blink) return;
    const id = window.setInterval(() => setWhich(w => (w === 'heldout' ? 'training' : 'heldout')), 700);
    return () => window.clearInterval(id);
  }, [blink]);
  const images = useMemo(() => {
    const mk = (frames: Frame[]) => {
      const loaded = frames.map(f => ({ d: cachedFrame(f.data_url), m: f.stats.median })).filter(x => x.d);
      return loaded.length ? stackFrames(loaded.map(x => ({ data: x.d!, median: x.m }))).data : null;
    };
    return { heldout: mk(sets.heldout), training: mk(sets.training) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sets, tick]);
  const pixels = images[which];
  const display = useMemo(() => {
    const d = images.heldout ?? images.training;
    if (!d) return { lo: -1, hi: 1, kind: 'asinh' as const, colormap: 'gray' as const };
    const med = percentile(d, 50), sigma = Math.max(med - percentile(d, 16), 1e-6);
    return { lo: -1.5 * sigma, hi: percentile(d, 99.8) - med, kind: 'asinh' as const, colormap: 'gray' as const };
  }, [images]);
  if (!field?.grid) return <div className="sky sky--lab"><div className="sky__message" data-loading="true"><p className="sky__message-title">Loading held-out exposures…</p></div></div>;
  const P = e.prediction?.predictions ?? {};
  const meas = e.result?.held_out_measured?.weighted_mean_position;
  const pred = e.predicted_at_mean_epoch;
  const overlays: Overlays = { markers: [], ellipses: [] };
  if (pred) overlays.ellipses!.push({ ra: pred.ra_deg, dec: pred.dec_deg, cov_arcsec2: pred.cov_arcsec2, nsigma: 3.44, color: '#ffa269', magnify: 30 });
  if (meas) overlays.markers!.push({ ra: meas.ra_deg, dec: meas.dec_deg, color: '#5fd4a8', shape: 'dot', size: 9, label: 'measured' });
  if (P.stationary_null) overlays.markers!.push({ ra: P.stationary_null.ra_deg, dec: P.stationary_null.dec_deg, color: '#ff8a7a', shape: 'diamond', size: 7 });
  if (e.tangent_reference && e.predicted_track.length) {
    const ref = e.tangent_reference;
    overlays.track = { points: e.predicted_track.map(p => fromTangent(p.xi, p.eta, ref.ra_deg, ref.dec_deg)), label: '', color: 'rgba(255,178,126,0.75)' };
  }
  return (
    <div className="labsky">
      <SkyCanvas ref={sky} grid={field.grid} pixels={pixels} display={display} overlays={overlays} smoothing compact
        caption={`${which === 'heldout' ? 'Held-out visit' : 'Last training visit'} · mean of ${which === 'heldout' ? sets.heldout.length : sets.training.length} exposures (D${sets.detector}) · reprojected display`}
        ariaLabel="Stacked held-out SPHEREx exposures with the locked prediction and the measured position" />
      <div className="row-btns">
        <button className={`button button--small ${which === 'training' && !blink ? 'button--primary' : 'button--ghost'}`} onClick={() => { setBlink(false); setWhich('training'); }}>Last training visit</button>
        <button className={`button button--small ${which === 'heldout' && !blink ? 'button--primary' : 'button--ghost'}`} onClick={() => { setBlink(false); setWhich('heldout'); }}>Held-out visit</button>
        <button className={`button button--small ${blink ? 'button--primary' : 'button--ghost'}`} onClick={() => setBlink(b => !b)}>Blink</button>
        <button className="button button--ghost button--small" onClick={() => sky.current?.zoom(2)} aria-label="Zoom in">Zoom +</button>
        <button className="button button--ghost button--small" onClick={() => sky.current?.zoom(0.5)} aria-label="Zoom out">Zoom −</button>
        <button className="button button--ghost button--small" onClick={() => sky.current?.resetView()}>Fit</button>
      </div>
      <p className="small"><span style={{ color: '#ffa269' }}>Orange ellipse</span>: locked prediction, 3.4σ region drawn 30× larger than true size; dashed line: fitted model (training) and its extrapolation; <span style={{ color: '#5fd4a8' }}>green dot</span>: measured held-out position; <span style={{ color: '#ff8a7a' }}>red diamond</span>: “stays here”.</p>
      <p className="small dim">The source moves about {num(e.result?.evaluations?.stationary_null?.residual_arcsec, 1)}″ between these visits — a third of a 6.15″ pixel. Ctrl/⌘ + scroll or the zoom buttons to zoom in on the source.</p>
    </div>
  );
}

function pickSets(field: Field | null, e: LabExperiment): { heldout: Frame[]; training: Frame[]; detector: number } {
  if (!field) return { heldout: [], training: [], detector: 0 };
  const held = new Set(e.heldout_frame_ids);
  const train = new Set(e.training_frame_ids);
  const hf = field.frames.filter(f => held.has(f.id));
  const tf = field.frames.filter(f => train.has(f.id));
  // the detector with most held-out frames, then the last training visit in that detector
  const counts = new Map<number, number>();
  hf.forEach(f => counts.set(f.detector, (counts.get(f.detector) ?? 0) + 1));
  const det = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? 2;
  const lastVisit = tf.slice().sort((a, b) => a.mjd - b.mjd).pop()?.visit ?? '';
  return {
    heldout: hf.filter(f => f.detector === det).slice(0, 40),
    training: tf.filter(f => f.detector === det && f.visit === lastVisit).slice(0, 40),
    detector: det,
  };
}
