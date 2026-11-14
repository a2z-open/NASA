import { useMemo, useRef, type KeyboardEvent, type PointerEvent } from 'react';
import type { Frame } from '../api.ts';
import { wavelengthColor } from '../lib/astro.ts';
import { month } from '../lib/format.ts';

interface Props {
  frames: Frame[];              // in display order
  index: number;
  onSelect: (i: number) => void;
  axis: 'time' | 'wavelength';
  markA?: number | null;
  markB?: number | null;
}

interface Segment { visit: string; start: number; end: number; x0: number; x1: number; frames: number[] }

const GAP = 0.035;

export function Timeline({ frames, index, onSelect, axis, markA, markB }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  const layout = useMemo(() => {
    const xs = new Array<number>(frames.length).fill(0);
    if (!frames.length) return { xs, segments: [] as Segment[] };
    if (axis === 'wavelength') {
      const lmin = Math.log(0.72), lmax = Math.log(5.05);
      frames.forEach((f, i) => {
        xs[i] = f.wavelength_um ? (Math.log(f.wavelength_um) - lmin) / (lmax - lmin) : 0;
      });
      return { xs, segments: [] as Segment[] };
    }
    // Broken time axis: one segment per visit, widths proportional to frame counts (min width).
    const byVisit = new Map<string, number[]>();
    frames.forEach((f, i) => {
      const k = f.visit || 'visit';
      if (!byVisit.has(k)) byVisit.set(k, []);
      byVisit.get(k)!.push(i);
    });
    const groups = [...byVisit.entries()].sort((a, b) => frames[a[1][0]].mjd - frames[b[1][0]].mjd);
    const totalGap = GAP * Math.max(groups.length - 1, 0);
    const weights = groups.map(([, idx]) => Math.max(idx.length, frames.length * 0.08));
    const wsum = weights.reduce((a, b) => a + b, 0);
    let x = 0;
    const segments: Segment[] = [];
    groups.forEach(([visit, idx], g) => {
      const w = (1 - totalGap) * weights[g] / wsum;
      const t0 = Math.min(...idx.map(i => frames[i].mjd));
      const t1 = Math.max(...idx.map(i => frames[i].mjd));
      for (const i of idx) xs[i] = x + (t1 > t0 ? (frames[i].mjd - t0) / (t1 - t0) : 0.5) * w;
      segments.push({ visit, start: t0, end: t1, x0: x, x1: x + w, frames: idx });
      x += w + GAP;
    });
    return { xs, segments };
  }, [frames, axis]);

  function pick(e: PointerEvent<HTMLDivElement>) {
    const el = ref.current;
    if (!el || !frames.length) return;
    const r = el.getBoundingClientRect();
    const t = (e.clientX - r.left - 12) / Math.max(r.width - 24, 1);
    let best = 0, bd = Infinity;
    layout.xs.forEach((x, i) => {
      const d = Math.abs(x - t);
      if (d < bd) { bd = d; best = i; }
    });
    onSelect(best);
  }

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Home') { onSelect(0); e.preventDefault(); }
    if (e.key === 'End') { onSelect(frames.length - 1); e.preventDefault(); }
  }

  const current = frames[index];

  return (
    <div className="timeline">
      <div
        className="timeline__track"
        ref={ref}
        role="slider"
        tabIndex={0}
        aria-label={axis === 'time' ? 'Observation time' : 'Observation wavelength'}
        aria-valuemin={1}
        aria-valuemax={Math.max(frames.length, 1)}
        aria-valuenow={index + 1}
        aria-valuetext={current ? `${current.time_utc.slice(0, 10)}, ${current.wavelength_um?.toFixed(3) ?? 'unknown'} micrometres` : 'no frames'}
        onPointerDown={e => { (e.target as Element).setPointerCapture?.(e.pointerId); pick(e); }}
        onPointerMove={e => { if (e.buttons) pick(e); }}
        onKeyDown={onKey}
      >
        {layout.segments.map((s, i) => (
          <div key={s.visit + i} className="timeline__segment" style={{ left: `calc(12px + (100% - 24px) * ${s.x0})`, width: `calc((100% - 24px) * ${s.x1 - s.x0})` }}>
            <span className="timeline__visit">{month(new Date((s.start - 40587) * 86400000).toISOString())}{s.end - s.start > 20 ? ` – ${month(new Date((s.end - 40587) * 86400000).toISOString())}` : ''}</span>
          </div>
        ))}
        {axis === 'wavelength' && [0.75, 1, 1.5, 2, 3, 4, 5].map(w => {
          const x = (Math.log(w) - Math.log(0.72)) / (Math.log(5.05) - Math.log(0.72));
          return <span key={w} className="timeline__axis-label" style={{ left: `calc(12px + (100% - 24px) * ${x})` }}>{w} µm</span>;
        })}
        {frames.map((f, i) => (
          <span
            key={f.id}
            className={`timeline__tick${i === index ? ' is-current' : ''}${i === markA ? ' is-a' : ''}${i === markB ? ' is-b' : ''}`}
            style={{ left: `calc(12px + (100% - 24px) * ${layout.xs[i]})`, background: wavelengthColor(f.wavelength_um, i === index ? 1 : 0.75) }}
          />
        ))}
        {markA != null && frames[markA] && <span className="timeline__mark" style={{ left: `calc(12px + (100% - 24px) * ${layout.xs[markA]})` }}>A</span>}
        {markB != null && frames[markB] && <span className="timeline__mark" style={{ left: `calc(12px + (100% - 24px) * ${layout.xs[markB]})` }}>B</span>}
      </div>
    </div>
  );
}
