import { useCallback, useEffect, useImperativeHandle, useRef, useState, forwardRef } from 'react';
import type { Grid } from '../api.ts';
import { gridToSky, skyToGrid, stretchValue, formatRA, formatDec, type SkyPoint, type StretchKind } from '../lib/astro.ts';

export type Colormap = 'gray' | 'ember' | 'diverging';

export interface Display {
  lo: number;
  hi: number;
  kind: StretchKind;
  colormap: Colormap;
}

export interface Marker {
  ra: number; dec: number;
  color: string;
  label?: string;
  shape?: 'circle' | 'cross' | 'diamond' | 'dot' | 'ring';
  size?: number;          // screen px
}

export interface Ellipse {
  ra: number; dec: number;
  cov_arcsec2: number[][];   // 2x2 covariance in (xi, eta) arcsec^2
  nsigma: number;
  color: string;
  label?: string;
  magnify?: number;         // draw the ellipse magnified (and say so in the label)
}

export interface Overlays {
  catalog?: { ra: number; dec: number; g: number | null }[];
  track?: { points: SkyPoint[]; label: string; color: string };
  measured?: { points: SkyPoint[]; color: string };
  markers?: Marker[];
  ellipses?: Ellipse[];
}

interface Props {
  grid: Grid;
  pixels: Float32Array | null;
  display: Display;
  overlays?: Overlays;
  showGrid?: boolean;
  showCatalog?: boolean;
  smoothing?: boolean;
  /** Crossfade from the previous image to the new one over this many milliseconds (display only). */
  fadeMs?: number;
  caption?: string;
  ariaLabel: string;
  onPick?: (p: SkyPoint) => void;
  hint?: { ra: number; dec: number; text: string } | null;
  emptyMessage?: { title: string; detail?: string; loading?: boolean } | null;
  compact?: boolean;
  /** Zoom on plain wheel (default true). When false, zoom needs Ctrl/Cmd + wheel so the page can scroll. */
  wheelZoom?: boolean;
}

export interface SkyCanvasHandle {
  resetView: () => void;
  zoom: (factor: number) => void;
}

function buildLut(map: Colormap): Uint8ClampedArray {
  const lut = new Uint8ClampedArray(256 * 3);
  const stops: [number, [number, number, number]][] =
    map === 'gray' ? [[0, [0, 0, 0]], [1, [255, 255, 255]]]
      : map === 'ember' ? [[0, [2, 3, 8]], [0.25, [24, 36, 74]], [0.5, [128, 64, 72]], [0.72, [232, 128, 64]], [0.9, [255, 214, 150]], [1, [255, 255, 245]]]
        : [[0, [96, 160, 255]], [0.3, [36, 70, 140]], [0.5, [10, 12, 16]], [0.7, [150, 70, 30]], [1, [255, 178, 110]]];
  for (let i = 0; i < 256; i++) {
    const t = i / 255;
    let k = 1;
    while (k < stops.length - 1 && t > stops[k][0]) k++;
    const [t0, c0] = stops[k - 1];
    const [t1, c1] = stops[k];
    const f = Math.min(1, Math.max(0, (t - t0) / (t1 - t0 || 1)));
    for (let c = 0; c < 3; c++) lut[i * 3 + c] = c0[c] + (c1[c] - c0[c]) * f;
  }
  return lut;
}

const LUTS: Record<Colormap, Uint8ClampedArray> = { gray: buildLut('gray'), ember: buildLut('ember'), diverging: buildLut('diverging') };

function niceStep(arcsec: number): number {
  const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
  return steps.find(s => s >= arcsec) ?? 3600;
}

export const SkyCanvas = forwardRef<SkyCanvasHandle, Props>(function SkyCanvas(props, ref) {
  const { grid, pixels, display, overlays, showGrid, showCatalog, smoothing, caption, ariaLabel, onPick, hint, emptyMessage, compact } = props;
  const fadeMs = props.fadeMs ?? 0;
  const fadeMsRef = useRef(fadeMs);
  fadeMsRef.current = fadeMs;
  const prevRef = useRef<HTMLCanvasElement | null>(null);
  const fadeRef = useRef({ start: 0, t: 1 });
  const fadeRaf = useRef(0);
  const wheelZoom = props.wheelZoom ?? !compact;
  const wheelZoomRef = useRef(wheelZoom);
  wheelZoomRef.current = wheelZoom;
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const offRef = useRef<HTMLCanvasElement | null>(null);
  const viewRef = useRef({ scale: 1, ox: 0, oy: 0, fitted: false });
  const [size, setSize] = useState({ w: 600, h: 600 });
  const [hover, setHover] = useState<SkyPoint | null>(null);
  const dragRef = useRef<{ x: number; y: number; ox: number; oy: number; moved: boolean } | null>(null);
  const [, force] = useState(0);
  const raf = useRef(0);

  // Resize observer
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      const r = entries[0].contentRect;
      setSize({ w: Math.max(50, Math.round(r.width)), h: Math.max(50, Math.round(r.height)) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const fit = useCallback(() => {
    const s = Math.min(size.w / grid.nx, size.h / grid.ny);
    viewRef.current = { scale: s, ox: (size.w - grid.nx * s) / 2, oy: (size.h - grid.ny * s) / 2, fitted: true };
  }, [size, grid.nx, grid.ny]);

  useEffect(() => { fit(); force(x => x + 1); }, [fit]);

  useImperativeHandle(ref, () => ({
    resetView: () => { fit(); force(x => x + 1); },
    zoom: (factor: number) => {
      const v = viewRef.current;
      const cx = size.w / 2, cy = size.h / 2;
      const ns = Math.min(80, Math.max(0.2, v.scale * factor));
      v.ox = cx - (cx - v.ox) * (ns / v.scale);
      v.oy = cy - (cy - v.oy) * (ns / v.scale);
      v.scale = ns;
      force(x => x + 1);
    },
  }), [fit, size]);

  // Rebuild the offscreen image when pixels or display change
  useEffect(() => {
    if (!pixels) { offRef.current = null; prevRef.current = null; force(x => x + 1); return; }
    // keep a copy of the image now on screen, so the new one can fade in over it
    const old = offRef.current;
    if (old && fadeMsRef.current > 0 && old.width === grid.nx && old.height === grid.ny) {
      const keep = prevRef.current ?? document.createElement('canvas');
      keep.width = old.width; keep.height = old.height;
      keep.getContext('2d')?.drawImage(old, 0, 0);
      prevRef.current = keep;
      fadeRef.current = { start: performance.now(), t: 0 };
    } else {
      fadeRef.current = { start: 0, t: 1 };
    }
    const off = offRef.current ?? document.createElement('canvas');
    off.width = grid.nx;
    off.height = grid.ny;
    const ctx = off.getContext('2d');
    if (!ctx) return;
    const img = ctx.createImageData(grid.nx, grid.ny);
    const lut = LUTS[display.colormap];
    const n = Math.min(pixels.length, grid.nx * grid.ny);
    const diverging = display.colormap === 'diverging';
    const L = Math.max(Math.abs(display.lo), Math.abs(display.hi), 1e-9);
    const soft = 6;
    const norm = Math.asinh(soft);
    for (let i = 0; i < n; i++) {
      const v = pixels[i];
      const o = i * 4;
      if (!Number.isFinite(v)) {
        img.data[o] = 22; img.data[o + 1] = 26; img.data[o + 2] = 34; img.data[o + 3] = 255;
        continue;
      }
      let t: number;
      if (diverging) {
        const s = Math.asinh(soft * Math.max(-1, Math.min(1, v / L))) / norm;
        t = (s + 1) / 2;
      } else {
        t = stretchValue(v, display.lo, display.hi, display.kind);
      }
      const k = Math.max(0, Math.min(255, Math.round(t * 255))) * 3;
      img.data[o] = lut[k]; img.data[o + 1] = lut[k + 1]; img.data[o + 2] = lut[k + 2]; img.data[o + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    offRef.current = off;
    force(x => x + 1);
    if (fadeRef.current.t < 1) {
      cancelAnimationFrame(fadeRaf.current);
      const step = () => {
        const t = Math.min(1, (performance.now() - fadeRef.current.start) / Math.max(fadeMsRef.current, 1));
        fadeRef.current.t = t;
        force(x => x + 1);
        if (t < 1) fadeRaf.current = requestAnimationFrame(step);
      };
      fadeRaf.current = requestAnimationFrame(step);
    }
  }, [pixels, display.lo, display.hi, display.kind, display.colormap, grid.nx, grid.ny]);

  const toScreen = useCallback((col: number, row: number) => {
    const v = viewRef.current;
    return { x: v.ox + (col + 0.5) * v.scale, y: v.oy + (row + 0.5) * v.scale };
  }, []);

  const skyToScreen = useCallback((p: SkyPoint) => {
    const g = skyToGrid(grid, p.ra, p.dec);
    return toScreen(g.col, g.row);
  }, [grid, toScreen]);

  // Draw
  useEffect(() => {
    cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(() => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(size.w * dpr);
      canvas.height = Math.round(size.h * dpr);
      canvas.style.width = `${size.w}px`;
      canvas.style.height = `${size.h}px`;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = '#04060a';
      ctx.fillRect(0, 0, size.w, size.h);
      const v = viewRef.current;
      const off = offRef.current;
      if (off) {
        ctx.imageSmoothingEnabled = !!smoothing;
        ctx.imageSmoothingQuality = 'high';
        const prev = prevRef.current;
        const t = fadeRef.current.t;
        if (prev && t < 1) {
          ctx.drawImage(prev, v.ox, v.oy, grid.nx * v.scale, grid.ny * v.scale);
          ctx.globalAlpha = t;
        }
        ctx.drawImage(off, v.ox, v.oy, grid.nx * v.scale, grid.ny * v.scale);
        ctx.globalAlpha = 1;
      }
      ctx.lineWidth = 1;
      // Coordinate grid
      if (showGrid && off) {
        const fovArcsec = grid.nx * grid.pixel_arcsec;
        const stepDec = niceStep(fovArcsec / 5);
        const cosd = Math.cos(grid.dec0 * Math.PI / 180) || 1e-3;
        const stepRaSec = niceStep(fovArcsec / 5 / cosd);
        ctx.strokeStyle = 'rgba(160, 190, 230, 0.22)';
        ctx.fillStyle = 'rgba(190, 210, 235, 0.7)';
        ctx.font = '10px "IBM Plex Mono", ui-monospace, monospace';
        const halfDeg = fovArcsec / 3600 * 0.75;
        const decMin = grid.dec0 - halfDeg, decMax = grid.dec0 + halfDeg;
        const raHalf = halfDeg / cosd;
        // Dec lines
        const d0 = Math.ceil(decMin * 3600 / stepDec) * stepDec;
        for (let d = d0; d <= decMax * 3600; d += stepDec) {
          ctx.beginPath();
          for (let k = 0; k <= 24; k++) {
            const ra = grid.ra0 - raHalf + (2 * raHalf * k) / 24;
            const s = skyToScreen({ ra, dec: d / 3600 });
            if (k === 0) ctx.moveTo(s.x, s.y); else ctx.lineTo(s.x, s.y);
          }
          ctx.stroke();
          const s = skyToScreen({ ra: grid.ra0 - raHalf * 0.62, dec: d / 3600 });
          if (s.x > 0 && s.x < size.w - 60 && s.y > 12 && s.y < size.h - 4) ctx.fillText(formatDec(d / 3600, 0), s.x + 3, s.y - 3);
        }
        // RA lines (step in seconds of time *15 => arcsec of RA)
        const raStepDeg = stepRaSec / 3600;
        const r0 = Math.ceil((grid.ra0 - raHalf) / raStepDeg) * raStepDeg;
        for (let r = r0; r <= grid.ra0 + raHalf; r += raStepDeg) {
          ctx.beginPath();
          for (let k = 0; k <= 24; k++) {
            const dec = decMin + ((decMax - decMin) * k) / 24;
            const s = skyToScreen({ ra: r, dec });
            if (k === 0) ctx.moveTo(s.x, s.y); else ctx.lineTo(s.x, s.y);
          }
          ctx.stroke();
          const s = skyToScreen({ ra: r, dec: grid.dec0 - halfDeg * 0.6 });
          if (s.x > 4 && s.x < size.w - 70 && s.y > 12 && s.y < size.h - 4) ctx.fillText(formatRA(((r % 360) + 360) % 360, 0), s.x + 3, s.y - 3);
        }
      }
      // Catalog overlay
      if (showCatalog && overlays?.catalog && off) {
        ctx.strokeStyle = 'rgba(140, 200, 255, 0.55)';
        for (const s of overlays.catalog) {
          const p = skyToScreen(s);
          if (p.x < -10 || p.y < -10 || p.x > size.w + 10 || p.y > size.h + 10) continue;
          const r = Math.max(3, Math.min(9, 11 - (s.g ?? 18) * 0.4)) * Math.min(1.6, Math.max(0.7, v.scale / 5));
          ctx.beginPath();
          ctx.arc(p.x, p.y, r + 3, 0, Math.PI * 2);
          ctx.stroke();
        }
      }
      // Track
      if (overlays?.track && overlays.track.points.length > 1) {
        ctx.save();
        ctx.setLineDash([5, 4]);
        ctx.strokeStyle = overlays.track.color;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        overlays.track.points.forEach((p, i) => {
          const s = skyToScreen(p);
          if (i === 0) ctx.moveTo(s.x, s.y); else ctx.lineTo(s.x, s.y);
        });
        ctx.stroke();
        ctx.restore();
        const last = skyToScreen(overlays.track.points[overlays.track.points.length - 1]);
        ctx.fillStyle = overlays.track.color;
        ctx.font = '11px "IBM Plex Sans", system-ui, sans-serif';
        ctx.fillText(overlays.track.label, last.x + 8, last.y + 14);
      }
      if (overlays?.measured) {
        ctx.fillStyle = overlays.measured.color;
        for (const p of overlays.measured.points) {
          const s = skyToScreen(p);
          ctx.beginPath();
          ctx.arc(s.x, s.y, 1.6, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      // Ellipses
      for (const e of overlays?.ellipses ?? []) {
        const c = e.cov_arcsec2;
        const a = c[0][0], b = c[0][1], d = c[1][1];
        const tr = (a + d) / 2, det = Math.sqrt(Math.max(0, ((a - d) / 2) ** 2 + b * b));
        const l1 = tr + det, l2 = Math.max(tr - det, 0);
        const ang = 0.5 * Math.atan2(2 * b, a - d);
        const mag = e.magnify ?? 1;
        const px = v.scale / grid.pixel_arcsec;   // screen px per arcsec
        const r1 = Math.max(2, e.nsigma * Math.sqrt(l1) * px * mag);
        const r2 = Math.max(2, e.nsigma * Math.sqrt(l2) * px * mag);
        const s = skyToScreen(e);
        ctx.save();
        ctx.translate(s.x, s.y);
        // Screen axes are (-xi, -eta): flipping both leaves the covariance unchanged.
        ctx.rotate(ang);
        ctx.strokeStyle = e.color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.ellipse(0, 0, r1, r2, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
        if (e.label) {
          ctx.fillStyle = e.color;
          ctx.font = '11px "IBM Plex Sans", system-ui, sans-serif';
          ctx.fillText(e.label, s.x + r1 + 6, s.y - 6);
        }
      }
      // Markers
      for (const m of overlays?.markers ?? []) {
        const s = skyToScreen(m);
        const r = m.size ?? 9;
        ctx.strokeStyle = m.color;
        ctx.fillStyle = m.color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        if (m.shape === 'cross') {
          ctx.moveTo(s.x - r, s.y); ctx.lineTo(s.x - r * 0.35, s.y);
          ctx.moveTo(s.x + r * 0.35, s.y); ctx.lineTo(s.x + r, s.y);
          ctx.moveTo(s.x, s.y - r); ctx.lineTo(s.x, s.y - r * 0.35);
          ctx.moveTo(s.x, s.y + r * 0.35); ctx.lineTo(s.x, s.y + r);
          ctx.stroke();
        } else if (m.shape === 'diamond') {
          ctx.moveTo(s.x, s.y - r); ctx.lineTo(s.x + r, s.y); ctx.lineTo(s.x, s.y + r); ctx.lineTo(s.x - r, s.y); ctx.closePath();
          ctx.stroke();
        } else if (m.shape === 'dot') {
          ctx.arc(s.x, s.y, r / 3, 0, Math.PI * 2); ctx.fill();
        } else {
          ctx.arc(s.x, s.y, r, 0, Math.PI * 2); ctx.stroke();
        }
        if (m.label) {
          ctx.font = '11px "IBM Plex Sans", system-ui, sans-serif';
          const w = ctx.measureText(m.label).width;
          const lx = Math.min(s.x + r + 6, size.w - w - 6);
          ctx.fillStyle = 'rgba(4,6,10,0.72)';
          ctx.fillRect(lx - 3, s.y - r - 16, w + 6, 15);
          ctx.fillStyle = m.color;
          ctx.fillText(m.label, lx, s.y - r - 5);
        }
      }
      // Hint
      if (hint && off) {
        const s = skyToScreen(hint);
        ctx.strokeStyle = 'rgba(245, 245, 247, 0.9)';
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.arc(s.x, s.y, 16, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.font = '12px "IBM Plex Sans", system-ui, sans-serif';
        const w = ctx.measureText(hint.text).width;
        const lx = Math.min(Math.max(6, s.x - w / 2), size.w - w - 6);
        const ly = s.y + 34;
        ctx.fillStyle = 'rgba(4,6,10,0.8)';
        ctx.fillRect(lx - 6, ly - 13, w + 12, 19);
        ctx.fillStyle = '#ffffff';
        ctx.fillText(hint.text, lx, ly);
      }
      // Crosshair at field centre
      if (off) {
        const c = toScreen((grid.nx - 1) / 2, (grid.ny - 1) / 2);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.28)';
        ctx.beginPath();
        ctx.moveTo(c.x - 22, c.y); ctx.lineTo(c.x - 9, c.y);
        ctx.moveTo(c.x + 9, c.y); ctx.lineTo(c.x + 22, c.y);
        ctx.moveTo(c.x, c.y - 22); ctx.lineTo(c.x, c.y - 9);
        ctx.moveTo(c.x, c.y + 9); ctx.lineTo(c.x, c.y + 22);
        ctx.stroke();
      }
      // Scale bar + compass
      if (off && !compact) {
        const pxPerArcsec = v.scale / grid.pixel_arcsec;
        const target = 110 / pxPerArcsec;
        const bar = [10, 15, 30, 60, 120, 180, 300, 600].find(b => b >= target * 0.6) ?? 600;
        const len = bar * pxPerArcsec;
        const x0 = size.w - len - 18, y0 = size.h - 20;
        ctx.strokeStyle = 'rgba(233,238,244,0.85)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(x0, y0); ctx.lineTo(x0 + len, y0);
        ctx.moveTo(x0, y0 - 4); ctx.lineTo(x0, y0 + 4);
        ctx.moveTo(x0 + len, y0 - 4); ctx.lineTo(x0 + len, y0 + 4);
        ctx.stroke();
        ctx.fillStyle = 'rgba(233,238,244,0.9)';
        ctx.font = '11px "IBM Plex Mono", ui-monospace, monospace';
        const label = bar >= 60 ? `${bar / 60}′` : `${bar}″`;
        ctx.fillText(label, x0 + len / 2 - ctx.measureText(label).width / 2, y0 - 7);
        // compass
        const cx = 50, cy = size.h - 20;
        ctx.beginPath();
        ctx.moveTo(cx, cy); ctx.lineTo(cx, cy - 22);
        ctx.moveTo(cx, cy); ctx.lineTo(cx - 22, cy);
        ctx.stroke();
        ctx.fillText('N', cx - 4, cy - 26);
        ctx.fillText('E', cx - 34, cy + 4);
      }
    });
  });

  function eventPos(e: { clientX: number; clientY: number }) {
    const r = canvasRef.current!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  function screenToSky(x: number, y: number): SkyPoint | null {
    const v = viewRef.current;
    const col = (x - v.ox) / v.scale - 0.5;
    const row = (y - v.oy) / v.scale - 0.5;
    if (col < -0.5 || row < -0.5 || col > grid.nx - 0.5 || row > grid.ny - 0.5) return null;
    return gridToSky(grid, col, row);
  }

  function onWheel(e: React.WheelEvent) {
    if (!wheelZoomRef.current && !(e.ctrlKey || e.metaKey)) return;
    const p = eventPos(e);
    const v = viewRef.current;
    const factor = Math.exp(-e.deltaY * 0.0015);
    const ns = Math.min(80, Math.max(0.2, v.scale * factor));
    v.ox = p.x - (p.x - v.ox) * (ns / v.scale);
    v.oy = p.y - (p.y - v.oy) * (ns / v.scale);
    v.scale = ns;
    force(x => x + 1);
  }

  // Prevent page scroll while zooming the canvas
  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const stop = (e: WheelEvent) => { if (wheelZoomRef.current || e.ctrlKey || e.metaKey) e.preventDefault(); };
    el.addEventListener('wheel', stop, { passive: false });
    return () => el.removeEventListener('wheel', stop);
  }, []);

  function onPointerDown(e: React.PointerEvent) {
    const p = eventPos(e);
    const v = viewRef.current;
    dragRef.current = { x: p.x, y: p.y, ox: v.ox, oy: v.oy, moved: false };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  }
  function onPointerMove(e: React.PointerEvent) {
    const p = eventPos(e);
    const d = dragRef.current;
    if (d) {
      const dx = p.x - d.x, dy = p.y - d.y;
      if (Math.hypot(dx, dy) > 4) d.moved = true;
      if (d.moved) {
        viewRef.current.ox = d.ox + dx;
        viewRef.current.oy = d.oy + dy;
        force(x => x + 1);
      }
    }
    setHover(screenToSky(p.x, p.y));
  }
  function onPointerUp(e: React.PointerEvent) {
    const d = dragRef.current;
    dragRef.current = null;
    if (d && !d.moved && onPick) {
      const p = eventPos(e);
      const sky = screenToSky(p.x, p.y);
      if (sky) onPick(sky);
    }
  }

  return (
    <div className={`sky${compact ? ' sky--compact' : ''}`} ref={wrapRef}>
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={ariaLabel}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => { setHover(null); }}
        onDoubleClick={() => { fit(); force(x => x + 1); }}
        style={{ cursor: onPick ? 'crosshair' : 'grab', touchAction: 'none' }}
      />
      {caption && <div className="sky__caption">{caption}</div>}
      {!compact && (
        <div className="sky__readout mono" aria-live="off">
          {hover ? <>{formatRA(hover.ra)} {formatDec(hover.dec)}<span className="dim"> · {hover.ra.toFixed(5)}°, {hover.dec.toFixed(5)}°</span></> : <span className="dim">Move over the image for coordinates</span>}
        </div>
      )}
      {emptyMessage && (
        <div className="sky__message" data-loading={emptyMessage.loading ? 'true' : 'false'}>
          <p className="sky__message-title">{emptyMessage.title}</p>
          {emptyMessage.detail && <p className="sky__message-detail">{emptyMessage.detail}</p>}
        </div>
      )}
    </div>
  );
});
