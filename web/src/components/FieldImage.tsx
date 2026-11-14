import { useEffect, useRef, useState } from 'react';
import { api, loadFrame, loadFrames, type Field, type Frame, type Stack } from '../api.ts';
import { percentile, stretchValue } from '../lib/astro.ts';
import { stack as stackFrames } from '../lib/compose.ts';

const EMBER: [number, number, number][] = [[2, 3, 8], [24, 36, 74], [128, 64, 72], [232, 128, 64], [255, 214, 150], [255, 255, 245]];

function ember(t: number): [number, number, number] {
  const x = Math.max(0, Math.min(1, t)) * (EMBER.length - 1);
  const i = Math.min(EMBER.length - 2, Math.floor(x));
  const f = x - i;
  return [0, 1, 2].map(k => EMBER[i][k] + (EMBER[i + 1][k] - EMBER[i][k]) * f) as [number, number, number];
}

export function paint(canvas: HTMLCanvasElement, data: Float32Array, nx: number, ny: number, opts: { colormap?: 'gray' | 'ember'; hiPct?: number; loSigma?: number } = {}) {
  canvas.width = nx;
  canvas.height = ny;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const med = percentile(data, 50);
  const p16 = percentile(data, 16);
  const sigma = Math.max(med - p16, 1e-6);
  const hi = percentile(data, opts.hiPct ?? 99.7) - med;
  const lo = -(opts.loSigma ?? 1.2) * sigma;
  const img = ctx.createImageData(nx, ny);
  for (let i = 0; i < nx * ny; i++) {
    const t = stretchValue(data[i] - med, lo, hi, 'asinh', 14);
    const o = i * 4;
    if (!Number.isFinite(t)) { img.data[o + 3] = 0; continue; }
    if (opts.colormap === 'ember') {
      const [r, g, b] = ember(t);
      img.data[o] = r; img.data[o + 1] = g; img.data[o + 2] = b;
    } else {
      const v = Math.round(t * 255);
      img.data[o] = v; img.data[o + 1] = v; img.data[o + 2] = v;
    }
    img.data[o + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
}

export function pickFrames(frames: Frame[], n: number, detectors?: number[]): Frame[] {
  const counts = new Map<number, number>();
  frames.forEach(f => counts.set(f.detector, (counts.get(f.detector) ?? 0) + 1));
  let pool = frames;
  if (detectors?.length) pool = frames.filter(f => detectors.includes(f.detector));
  else {
    const best = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
    pool = frames.filter(f => f.detector === best);
  }
  pool = pool.filter(f => (f.stats?.finite_fraction ?? 1) > 0.6);
  if (pool.length <= n) return pool;
  const out: Frame[] = [];
  for (let i = 0; i < n; i++) out.push(pool[Math.round((i * (pool.length - 1)) / Math.max(n - 1, 1))]);
  return out;
}

/** A real-data still: the mean of several background-subtracted exposures of a field. */
export function FieldStill({ fieldId, field: given, frames = 8, detectors, className, alt, colormap = 'gray', onReady }: {
  fieldId?: string; field?: Field; frames?: number; detectors?: number[]; className?: string; alt: string; colormap?: 'gray' | 'ember'; onReady?: () => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const field = given ?? (fieldId ? await api.field(fieldId) : null);
        if (!field?.grid || !field.frames.length) throw new Error('no frames');
        const chosen = pickFrames(field.frames, frames, detectors);
        const loaded: { data: Float32Array; median: number }[] = [];
        await loadFrames(chosen.map(f => f.data_url), field.grid.dtype, (url, data) => {
          const f = chosen.find(c => c.data_url === url)!;
          loaded.push({ data, median: f.stats.median });
        });
        if (!alive || !ref.current || !loaded.length) throw new Error('no data');
        const s = stackFrames(loaded);
        paint(ref.current, s.data, field.grid.nx, field.grid.ny, { colormap });
        setState('ready');
        onReady?.();
      } catch {
        if (alive) setState('error');
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fieldId, given?.field_id]);
  return (
    <div className={`still ${className ?? ''}`} data-state={state}>
      <canvas ref={ref} role="img" aria-label={alt} />
      {state === 'error' && <span className="still__error">Image unavailable</span>}
    </div>
  );
}

/** A backend shift-and-stack image (co-moving with the source). */
export function StackStill({ stack, alt, colormap = 'gray' }: { stack: Stack; alt: string; colormap?: 'gray' | 'ember' }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  useEffect(() => {
    let alive = true;
    loadFrame(stack.data_url, stack.dtype)
      .then(data => {
        if (!alive || !ref.current) return;
        paint(ref.current, data, stack.nx, stack.ny, { colormap, hiPct: 99.9, loSigma: 1.5 });
        setState('ready');
      })
      .catch(() => alive && setState('error'));
    return () => { alive = false; };
  }, [stack.data_url, stack.dtype, stack.nx, stack.ny, colormap]);
  return (
    <div className="still still--stack" data-state={state}>
      <canvas ref={ref} role="img" aria-label={alt} />
      <span className="still__reticle" aria-hidden="true" />
      {state === 'error' && <span className="still__error">Stack unavailable</span>}
    </div>
  );
}
