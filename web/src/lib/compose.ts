// Image composition for the viewer: background subtraction, difference and stacking.
// Display only — scientific measurements happen on native pixels in the backend.

export interface FrameStats { median: number; sigma: number; p995: number }

export function subtractBackground(data: Float32Array, median: number): Float32Array {
  const out = new Float32Array(data.length);
  for (let i = 0; i < data.length; i++) out[i] = data[i] - median;
  return out;
}

export function difference(a: Float32Array, am: number, b: Float32Array, bm: number): Float32Array {
  const n = Math.min(a.length, b.length);
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) out[i] = (a[i] - am) - (b[i] - bm);
  return out;
}

/** NaN-aware mean of background-subtracted frames. */
export function stack(frames: { data: Float32Array; median: number }[]): { data: Float32Array; count: Uint16Array } {
  const n = frames.length ? frames[0].data.length : 0;
  const sum = new Float64Array(n);
  const count = new Uint16Array(n);
  for (const f of frames) {
    const d = f.data;
    for (let i = 0; i < n; i++) {
      const v = d[i];
      if (Number.isFinite(v)) { sum[i] += v - f.median; count[i]++; }
    }
  }
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) out[i] = count[i] ? sum[i] / count[i] : NaN;
  return { data: out, count };
}

export function median(values: number[]): number {
  const v = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!v.length) return NaN;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}

/** Shared limits for a set of frames: black at -k·sigma, white at the typical bright tail. */
export function sharedLimits(stats: FrameStats[], black = 1.5, contrast = 1): { lo: number; hi: number } {
  const sigma = median(stats.map(s => s.sigma));
  const tail = median(stats.map(s => s.p995 - s.median));
  const lo = -black * (Number.isFinite(sigma) ? sigma : 1);
  const hi = Math.max((Number.isFinite(tail) ? tail : 10 * sigma) / Math.max(contrast, 0.05), Math.abs(lo) + 1e-6);
  return { lo, hi };
}
