import { useMemo, useState } from 'react';
import type { Motion, Spectrum, Variability } from '../api.ts';
import { wavelengthColor } from '../lib/astro.ts';
import { num } from '../lib/format.ts';

// --------------------------------------------------------------------------
// Small SVG chart toolkit
// --------------------------------------------------------------------------

export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) return [min];
  const span = max - min;
  const step0 = span / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const norm = step0 / mag;
  const step = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-6; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  return out;
}

const M = { l: 58, r: 16, t: 14, b: 40 };

interface Frame { w: number; h: number }

function Axes({ w, h, xTicks, yTicks, sx, sy, xLabel, yLabel, xFmt, yFmt }: Frame & {
  xTicks: number[]; yTicks: number[]; sx: (v: number) => number; sy: (v: number) => number;
  xLabel: string; yLabel: string; xFmt?: (v: number) => string; yFmt?: (v: number) => string;
}) {
  return (
    <g className="axes">
      <rect x={M.l} y={M.t} width={w - M.l - M.r} height={h - M.t - M.b} className="axes__frame" />
      {xTicks.map(t => (
        <g key={'x' + t}>
          <line x1={sx(t)} x2={sx(t)} y1={M.t} y2={h - M.b} className="axes__grid" />
          <text x={sx(t)} y={h - M.b + 15} textAnchor="middle" className="axes__tick">{xFmt ? xFmt(t) : t}</text>
        </g>
      ))}
      {yTicks.map(t => (
        <g key={'y' + t}>
          <line x1={M.l} x2={w - M.r} y1={sy(t)} y2={sy(t)} className="axes__grid" />
          <text x={M.l - 7} y={sy(t) + 4} textAnchor="end" className="axes__tick">{yFmt ? yFmt(t) : t}</text>
        </g>
      ))}
      <text x={(M.l + w - M.r) / 2} y={h - 6} textAnchor="middle" className="axes__label">{xLabel}</text>
      <text x={14} y={(M.t + h - M.b) / 2} textAnchor="middle" transform={`rotate(-90 14 ${(M.t + h - M.b) / 2})`} className="axes__label">{yLabel}</text>
    </g>
  );
}

const VISIT_COLORS = ['#ffffff', '#a1a1a6', '#d1d1d6', '#6e6e73', '#e5e5ea', '#8e8e93'];

export function visitColor(visit: string, visits: string[]): string {
  const i = Math.max(0, visits.indexOf(visit));
  return VISIT_COLORS[i % VISIT_COLORS.length];
}

// --------------------------------------------------------------------------
// Motion: measured positions and fitted model in the tangent plane
// --------------------------------------------------------------------------

export function MotionPlot({ motion, extra }: { motion: Motion; extra?: { xi: number; eta: number; label: string; color: string; sigma?: number }[] }) {
  const w = 560, h = 420;
  const visits = useMemo(() => [...new Set(motion.points.map(p => p.visit))], [motion]);
  const [binned, setBinned] = useState(true);
  const display = useMemo(() => {
    if (!binned) return motion.points.map(p => ({ ...p, n: 1 }));
    // Weighted mean per visit (display aid only; the fit uses every exposure)
    return visits.map(v => {
      const pts = motion.points.filter(p => p.visit === v);
      const wts = pts.map(p => 1 / (p.sigma * p.sigma));
      const W = wts.reduce((a, b) => a + b, 0);
      return {
        visit: v, n: pts.length,
        xi: pts.reduce((a, p, i) => a + p.xi * wts[i], 0) / W,
        eta: pts.reduce((a, p, i) => a + p.eta * wts[i], 0) / W,
        sigma: 1 / Math.sqrt(W),
        mjd: pts.reduce((a, p, i) => a + p.mjd * wts[i], 0) / W,
      };
    });
  }, [binned, motion, visits]);
  const all = [...motion.points, ...motion.track, ...(extra ?? [])];
  // East to the left: plot x = -xi
  let xmin = Math.min(...all.map(p => -p.xi)), xmax = Math.max(...all.map(p => -p.xi));
  let ymin = Math.min(...all.map(p => p.eta)), ymax = Math.max(...all.map(p => p.eta));
  const pad = 0.12 * Math.max(xmax - xmin, ymax - ymin, 0.5);
  xmin -= pad; xmax += pad; ymin -= pad; ymax += pad;
  // equal aspect
  const pw = w - M.l - M.r, ph = h - M.t - M.b;
  const span = Math.max((xmax - xmin) / pw, (ymax - ymin) / ph);
  const cx = (xmin + xmax) / 2, cy = (ymin + ymax) / 2;
  xmin = cx - span * pw / 2; xmax = cx + span * pw / 2; ymin = cy - span * ph / 2; ymax = cy + span * ph / 2;
  const sx = (v: number) => M.l + ((v - xmin) / (xmax - xmin)) * pw;
  const sy = (v: number) => M.t + (1 - (v - ymin) / (ymax - ymin)) * ph;
  const r = (s: number) => Math.max(1.2, s / span);
  const path = motion.track.map((p, i) => `${i ? 'L' : 'M'}${sx(-p.xi).toFixed(1)},${sy(p.eta).toFixed(1)}`).join('');
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Measured positions and fitted motion model on the sky">
        <Axes w={w} h={h} xTicks={niceTicks(xmin, xmax, 6)} yTicks={niceTicks(ymin, ymax, 5)} sx={sx} sy={sy}
          xLabel="Δα cos δ  (arcsec, east ←)" yLabel="Δδ  (arcsec, north ↑)" xFmt={v => num(-v, Math.abs(xmax - xmin) < 3 ? 1 : 0)} yFmt={v => num(v, Math.abs(ymax - ymin) < 3 ? 1 : 0)} />
        <path d={path} className="chart__model" />
        {display.map((p, i) => (
          <g key={i}>
            <circle cx={sx(-p.xi)} cy={sy(p.eta)} r={r(p.sigma)} fill="none" stroke={visitColor(p.visit, visits)} strokeOpacity={0.55} />
            <circle cx={sx(-p.xi)} cy={sy(p.eta)} r={binned ? 3.4 : 1.7} fill={visitColor(p.visit, visits)} />
          </g>
        ))}
        {extra?.map((p, i) => (
          <g key={'e' + i}>
            {p.sigma != null && <circle cx={sx(-p.xi)} cy={sy(p.eta)} r={r(p.sigma)} fill="none" stroke={p.color} strokeDasharray="3 2" />}
            <path d={`M${sx(-p.xi) - 6},${sy(p.eta)}h12M${sx(-p.xi)},${sy(p.eta) - 6}v12`} stroke={p.color} strokeWidth={1.6} />
            <text x={sx(-p.xi) + 8} y={sy(p.eta) - 8} className="chart__note" fill={p.color}>{p.label}</text>
          </g>
        ))}
      </svg>
      <figcaption>
        <span className="legend"><span className="legend__dash" /> fitted model</span>
        {visits.map(v => <span key={v} className="legend"><span className="legend__dot" style={{ background: visitColor(v, visits) }} /> {v}</span>)}
        <label className="chart__toggle"><input type="checkbox" checked={binned} onChange={e => setBinned(e.target.checked)} /> Show visit means (fit uses every exposure)</label>
      </figcaption>
    </figure>
  );
}

// --------------------------------------------------------------------------
// Spectrum: binned points, gaps preserved, optional template curve
// --------------------------------------------------------------------------

const DETECTOR_RANGES: [number, number][] = [[0.75, 1.09], [1.10, 1.62], [1.63, 2.41], [2.42, 3.82], [3.83, 4.41], [4.42, 5.0]];

export function SpectrumPlot({ spectrum, showFixed, showRaw }: { spectrum: Spectrum; showFixed: boolean; showRaw: boolean }) {
  const w = 640, h = 380;
  const [logY, setLogY] = useState(false);
  const bins = spectrum.binned.filter(b => b.flux_ujy != null && Number.isFinite(b.flux_ujy));
  const fixed = spectrum.binned.filter(b => b.fixed_flux_ujy != null && Number.isFinite(b.fixed_flux_ujy));
  const model = spectrum.templates?.model_curve ?? null;
  const ys: number[] = [];
  bins.forEach(b => { ys.push(b.flux_ujy! + (b.flux_err_ujy ?? 0), b.flux_ujy! - (b.flux_err_ujy ?? 0)); });
  if (showFixed) fixed.forEach(b => ys.push(b.fixed_flux_ujy!));
  if (showRaw) spectrum.points.forEach(p => ys.push(p.flux_ujy));
  model?.forEach(m => ys.push(m.flux_ujy));
  const finite = ys.filter(Number.isFinite);
  let ymin = finite.length ? Math.min(...finite) : 0;
  let ymax = finite.length ? Math.max(...finite) : 1;
  const useLog = logY && ymin > 0;
  if (useLog) { ymin = Math.log10(ymin * 0.8); ymax = Math.log10(ymax * 1.25); }
  else { const p = 0.08 * (ymax - ymin || 1); ymin = Math.min(0, ymin - p); ymax += p; }
  const lmin = Math.log(0.72), lmax = Math.log(5.08);
  const pw = w - M.l - M.r, ph = h - M.t - M.b;
  const sx = (um: number) => M.l + ((Math.log(um) - lmin) / (lmax - lmin)) * pw;
  const yv = (f: number) => (useLog ? Math.log10(Math.max(f, 1e-6)) : f);
  const sy = (f: number) => M.t + (1 - (yv(f) - ymin) / (ymax - ymin)) * ph;
  const xt = [0.75, 1, 1.5, 2, 3, 4, 5];
  const ytRaw = useLog ? niceTicks(ymin, ymax, 4).map(v => 10 ** v) : niceTicks(ymin, ymax, 5);
  const syTick = (t: number) => sy(t);
  // model path, split at gaps > 0.2 dex
  let modelPath = '';
  if (model) {
    model.forEach((m, i) => {
      const prev = model[i - 1];
      const jump = !prev || Math.log(m.wavelength_um / prev.wavelength_um) > 0.12;
      modelPath += `${jump ? 'M' : 'L'}${sx(m.wavelength_um).toFixed(1)},${sy(m.flux_ujy).toFixed(1)}`;
    });
  }
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="SPHEREx spectrum of the selected source">
        {DETECTOR_RANGES.map(([a, b], i) => (
          <g key={i}>
            <rect x={sx(a)} y={h - M.b - 6} width={sx(b) - sx(a)} height={6} fill={wavelengthColor((a + b) / 2, 0.35)} />
            <text x={(sx(a) + sx(b)) / 2} y={M.t + 12} textAnchor="middle" className="chart__band">D{i + 1}</text>
          </g>
        ))}
        <Axes w={w} h={h} xTicks={xt} yTicks={ytRaw} sx={sx} sy={syTick} xLabel="Wavelength (µm, log scale)" yLabel="Flux density (µJy)"
          xFmt={v => String(v)} yFmt={v => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k` : num(v, Math.abs(v) < 10 && v !== 0 ? 1 : 0))} />
        {showRaw && spectrum.points.map((p, i) => (
          <circle key={'r' + i} cx={sx(p.wavelength_um)} cy={sy(p.flux_ujy)} r={1.4} fill={wavelengthColor(p.wavelength_um, 0.35)} />
        ))}
        {model && <path d={modelPath} className="chart__template" />}
        {showFixed && fixed.map(b => (
          <rect key={'f' + b.bin} x={sx(b.center_um) - 3} y={sy(b.fixed_flux_ujy!) - 3} width={6} height={6} className="chart__fixed" />
        ))}
        {bins.map(b => {
          const x = sx(b.center_um);
          const e = b.flux_err_ujy ?? 0;
          return (
            <g key={b.bin}>
              <line x1={x} x2={x} y1={sy(b.flux_ujy! - e)} y2={sy(b.flux_ujy! + e)} stroke={wavelengthColor(b.center_um)} strokeWidth={1.2} />
              <circle cx={x} cy={sy(b.flux_ujy!)} r={2.8} fill={wavelengthColor(b.center_um)} />
            </g>
          );
        })}
      </svg>
      <figcaption>
        <span className="legend"><span className="legend__dot" style={{ background: wavelengthColor(2.5) }} /> motion-corrected (“follow”) extraction, binned to 102 SPHEREx channels</span>
        {showFixed && <span className="legend"><span className="legend__square" /> fixed sky position</span>}
        {model && <span className="legend"><span className="legend__line" /> best template ({spectrum.templates?.best?.spectral_type}, scaled)</span>}
        <label className="chart__toggle"><input type="checkbox" checked={logY} onChange={e => setLogY(e.target.checked)} /> log flux axis</label>
      </figcaption>
    </figure>
  );
}

// --------------------------------------------------------------------------
// Variability: naive (mixed wavelengths) vs wavelength-matched
// --------------------------------------------------------------------------

export function NaiveLightCurve({ variability }: { variability: Variability }) {
  const pts = variability.naive?.points?.length ? variability.naive.points : variability.light_curve;
  if (!pts?.length) return null;
  const w = 560, h = 300;
  const t0 = Math.min(...pts.map(p => p.mjd)), t1 = Math.max(...pts.map(p => p.mjd));
  const fs = pts.map(p => p.flux_ujy).filter(Number.isFinite);
  let ymin = Math.min(...fs), ymax = Math.max(...fs);
  const pad = 0.08 * (ymax - ymin || 1); ymin -= pad; ymax += pad;
  const pw = w - M.l - M.r, ph = h - M.t - M.b;
  const sx = (t: number) => M.l + ((t - t0) / (t1 - t0 || 1)) * pw;
  const sy = (f: number) => M.t + (1 - (f - ymin) / (ymax - ymin)) * ph;
  const xt = niceTicks(t0, t1, 5);
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Naive light curve mixing wavelengths">
        <Axes w={w} h={h} xTicks={xt} yTicks={niceTicks(ymin, ymax, 4)} sx={sx} sy={sy} xLabel="Observation date (MJD)" yLabel="Flux density (µJy)"
          xFmt={v => String(Math.round(v))} yFmt={v => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : num(v, 0))} />
        {pts.map((p, i) => <circle key={i} cx={sx(p.mjd)} cy={sy(p.flux_ujy)} r={2.2} fill={wavelengthColor(p.wavelength_um, 0.85)} />)}
      </svg>
      <figcaption><span className="legend">Colour = wavelength of each exposure. Mixing wavelengths makes a spectrum look like a light curve.</span></figcaption>
    </figure>
  );
}

export function MatchedComparisons({ variability }: { variability: Variability }) {
  const comps = variability.matched?.comparisons ?? [];
  if (!comps.length) return null;
  const w = 560, h = 300;
  const rs = comps.flatMap(c => [c.ratio - c.ratio_err, c.ratio + c.ratio_err]).filter(Number.isFinite);
  let ymin = Math.min(...rs, 0.9), ymax = Math.max(...rs, 1.1);
  const pad = 0.06 * (ymax - ymin); ymin -= pad; ymax += pad;
  const lmin = Math.log(0.72), lmax = Math.log(5.08);
  const pw = w - M.l - M.r, ph = h - M.t - M.b;
  const sx = (um: number) => M.l + ((Math.log(um) - lmin) / (lmax - lmin)) * pw;
  const sy = (r: number) => M.t + (1 - (r - ymin) / (ymax - ymin)) * ph;
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Wavelength-matched flux ratios between visits">
        <Axes w={w} h={h} xTicks={[0.75, 1, 1.5, 2, 3, 4, 5]} yTicks={niceTicks(ymin, ymax, 5)} sx={sx} sy={sy} xLabel="Matched wavelength (µm)" yLabel="Flux ratio between visits"
          xFmt={v => String(v)} yFmt={v => num(v, 2)} />
        <line x1={M.l} x2={w - M.r} y1={sy(1)} y2={sy(1)} className="chart__unity" />
        {comps.map((c, i) => (
          <g key={i}>
            <line x1={sx(c.center_um)} x2={sx(c.center_um)} y1={sy(c.ratio - c.ratio_err)} y2={sy(c.ratio + c.ratio_err)} stroke={wavelengthColor(c.center_um)} />
            <circle cx={sx(c.center_um)} cy={sy(c.ratio)} r={2.6} fill={wavelengthColor(c.center_um)} />
          </g>
        ))}
      </svg>
      <figcaption><span className="legend">Each point compares the same source at the same wavelength in two different visits. Ratio 1 = no change.</span></figcaption>
    </figure>
  );
}

// --------------------------------------------------------------------------
// Lab residual plot: prediction ellipse, measured position and comparison models (arcsec)
// --------------------------------------------------------------------------

export interface ResidualPoint { dx: number; dy: number; label: string; color: string; kind: 'measured' | 'model' }

export function ResidualPlot({ cov, nsigma, points, measurementSigma }: { cov: number[][]; nsigma: number; points: ResidualPoint[]; measurementSigma: number | null }) {
  const w = 420, h = 420;
  const a = cov[0][0], b = cov[0][1], d = cov[1][1];
  const tr = (a + d) / 2, det = Math.sqrt(Math.max(0, ((a - d) / 2) ** 2 + b * b));
  const l1 = tr + det, l2 = Math.max(tr - det, 0);
  const ang = 0.5 * Math.atan2(2 * b, a - d);
  const extent = Math.max(nsigma * Math.sqrt(l1) * 1.6, ...points.filter(p => p.kind === 'measured').map(p => Math.hypot(p.dx, p.dy) * 1.4), 0.05);
  const pw = w - M.l - M.r, ph = h - M.t - M.b;
  const s = Math.min(pw, ph) / (2 * extent);
  const cx = M.l + pw / 2, cy = M.t + ph / 2;
  const X = (dx: number) => cx - dx * s;   // east left
  const Y = (dy: number) => cy - dy * s;
  const ticks = niceTicks(-extent, extent, 4);
  return (
    <figure className="chart chart--square">
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Held-out residuals relative to the locked prediction">
        <rect x={M.l} y={M.t} width={pw} height={ph} className="axes__frame" />
        {ticks.map(t => (
          <g key={t}>
            <line x1={X(t)} x2={X(t)} y1={M.t} y2={h - M.b} className="axes__grid" />
            <line x1={M.l} x2={w - M.r} y1={Y(t)} y2={Y(t)} className="axes__grid" />
            <text x={X(t)} y={h - M.b + 15} textAnchor="middle" className="axes__tick">{num(t, extent < 0.5 ? 2 : 1)}</text>
            <text x={M.l - 7} y={Y(t) + 4} textAnchor="end" className="axes__tick">{num(t, extent < 0.5 ? 2 : 1)}</text>
          </g>
        ))}
        <text x={(M.l + w - M.r) / 2} y={h - 6} textAnchor="middle" className="axes__label">Δα cos δ from prediction (arcsec, east ←)</text>
        <text x={14} y={(M.t + h - M.b) / 2} textAnchor="middle" transform={`rotate(-90 14 ${(M.t + h - M.b) / 2})`} className="axes__label">Δδ (arcsec)</text>
        <ellipse cx={cx} cy={cy} rx={nsigma * Math.sqrt(l1) * s} ry={nsigma * Math.sqrt(l2) * s} transform={`rotate(${(ang * 180) / Math.PI} ${cx} ${cy})`} className="chart__ellipse" />
        <ellipse cx={cx} cy={cy} rx={Math.sqrt(l1) * s} ry={Math.sqrt(l2) * s} transform={`rotate(${(ang * 180) / Math.PI} ${cx} ${cy})`} className="chart__ellipse chart__ellipse--inner" />
        <path d={`M${cx - 7},${cy}h14M${cx},${cy - 7}v14`} stroke="#f5f5f7" strokeWidth={1.5} />
        {points.map((p, i) => {
          const r = Math.hypot(p.dx, p.dy);
          const lim = extent * 0.86;
          if (p.kind === 'model' && r > lim) {
            // Off-scale comparison prediction: arrow at the edge pointing towards it.
            const ux = p.dx / r, uy = p.dy / r;
            const ex = X(ux * lim), ey = Y(uy * lim);
            const ang = Math.atan2(-(uy), -(ux)) * 180 / Math.PI; // screen angle of the direction (east-left, north-up)
            return (
              <g key={i}>
                <g transform={`translate(${ex} ${ey}) rotate(${ang})`}>
                  <path d="M10,0 L-4,-6 L-4,6 Z" fill={p.color} />
                </g>
                <text x={ex + (ux > 0 ? 10 : -10)} y={ey + (uy > 0 ? 16 : -10)} textAnchor={ux > 0 ? 'start' : 'end'} className="chart__note" fill={p.color}>{p.label}: {r.toFixed(2)}″ off-scale</text>
              </g>
            );
          }
          return (
            <g key={i}>
              {p.kind === 'measured' && measurementSigma != null && <circle cx={X(p.dx)} cy={Y(p.dy)} r={Math.max(2, measurementSigma * s)} fill="none" stroke={p.color} strokeOpacity={0.6} />}
              {p.kind === 'measured'
                ? <circle cx={X(p.dx)} cy={Y(p.dy)} r={4.5} fill={p.color} />
                : <rect x={X(p.dx) - 4} y={Y(p.dy) - 4} width={8} height={8} fill="none" stroke={p.color} strokeWidth={1.6} />}
              <text x={X(p.dx) + 9} y={Y(p.dy) + 4} className="chart__note" fill={p.color}>{p.label}</text>
            </g>
          );
        })}
      </svg>
      <figcaption>
        <span className="legend"><span className="legend__ring" /> locked prediction: 1σ and {nsigma.toFixed(2)}σ (d² = 11.83) regions</span>
      </figcaption>
    </figure>
  );
}
