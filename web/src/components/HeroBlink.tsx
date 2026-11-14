import { useEffect, useRef, useState } from 'react';
import { api, loadFrame, type Frame } from '../api.ts';
import { paint } from './FieldImage.tsx';
import { Link } from '../router.tsx';

const N = 29; // native SPHEREx pixels across the porthole

/** Two real SPHEREx exposures of Epsilon Indi B, same wavelength, 17 months apart, blinking. */
export function HeroBlink() {
  const ref = useRef<HTMLCanvasElement>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [k, setK] = useState(0);
  const [meta, setMeta] = useState<{ dates: string[]; rings: [number, number][]; lam: number } | null>(null);

  useEffect(() => {
    let alive = true;
    let timer = 0;
    (async () => {
      try {
        const field = await api.field('epsilon-indi-b');
        const g = field.grid;
        if (!g) throw new Error('no grid');
        const pool = field.frames.filter(f => f.detector === 3 && f.wavelength_um != null && (f.stats?.finite_fraction ?? 1) > 0.6);
        let best: [Frame, Frame] | null = null;
        let span = 0;
        for (const a of pool.slice(0, 40)) for (const b of pool.slice(-40)) {
          if (Math.abs(a.wavelength_um! - b.wavelength_um!) < 0.02 && b.mjd - a.mjd > span) { best = [a, b]; span = b.mjd - a.mjd; }
        }
        if (!best) throw new Error('no matched pair');
        const data = await Promise.all(best.map(f => loadFrame(f.data_url, g.dtype)));
        const x0 = Math.floor((g.nx - N) / 2), y0 = Math.floor((g.ny - N) / 2), mid = (N - 1) / 2;
        const layers: HTMLCanvasElement[] = [];
        const rings: [number, number][] = [];
        data.forEach((d, i) => {
          const crop = new Float32Array(N * N);
          for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) crop[y * N + x] = d[(y0 + y) * g.nx + x0 + x] - best![i].stats.median;
          // light-weighted centre of the source inside the central 7x7 pixels
          let sw = 0, sx = 0, sy = 0;
          for (let y = mid - 3; y <= mid + 3; y++) for (let x = mid - 3; x <= mid + 3; x++) {
            const v = Math.max(crop[y * N + x], 0) ** 2;
            sw += v; sx += v * x; sy += v * y;
          }
          rings.push(sw > 0 ? [(sx / sw + 0.5) / N, (sy / sw + 0.5) / N] : [0.5, 0.5]);
          const el = document.createElement('canvas');
          paint(el, crop, N, N, { colormap: 'ember', hiPct: 99.9 });
          layers.push(el);
        });
        if (!alive) return;
        const fmt = (iso: string) => new Date(iso).toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });
        setMeta({ dates: best.map(f => fmt(f.time_utc)), rings, lam: best[0].wavelength_um! });
        let i = 0;
        const show = () => {
          const c = ref.current;
          if (!c) return;
          c.width = N; c.height = N;
          c.getContext('2d')?.drawImage(layers[i], 0, 0);
          setK(i);
          i = 1 - i;
        };
        show();
        setState('ready');
        if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) timer = window.setInterval(show, 1100);
      } catch {
        if (alive) setState('error');
      }
    })();
    return () => { alive = false; window.clearInterval(timer); };
  }, []);

  return (
    <figure className="porthole" data-state={state}>
      <Link href="/explore?target=epsilon-indi-b" className="porthole__glass" aria-label="Open Epsilon Indi B in the explorer">
        <canvas ref={ref} role="img" aria-label="Two real SPHEREx exposures of Epsilon Indi B, 17 months apart, alternating. The star shifts by about one pixel." />
        {meta && <span className="porthole__ring" style={{ left: `${meta.rings[k][0] * 100}%`, top: `${meta.rings[k][1] * 100}%` }} aria-hidden="true" />}
        {state === 'error' && <span className="porthole__error">Image unavailable</span>}
      </Link>
      <span className="porthole__mark porthole__mark--tl" aria-hidden="true" />
      <span className="porthole__mark porthole__mark--tr" aria-hidden="true" />
      <span className="porthole__mark porthole__mark--bl" aria-hidden="true" />
      <span className="porthole__mark porthole__mark--br" aria-hidden="true" />
      <figcaption className="porthole__caption">
        <span className="porthole__dates mono">
          <b className={k === 0 ? 'is-on' : ''}>{meta?.dates[0] ?? '—'}</b>
          <i aria-hidden="true" />
          <b className={k === 1 ? 'is-on' : ''}>{meta?.dates[1] ?? '—'}</b>
        </span>
        <span><strong>Epsilon Indi B</strong>, 12 light-years away. Real SPHEREx pixels{meta ? ` at ${meta.lam.toFixed(2)} µm` : ''}; each square is 6 arcseconds.</span>
      </figcaption>
    </figure>
  );
}
