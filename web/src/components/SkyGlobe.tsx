import { useEffect, useRef } from 'react';

export interface GlobePoint { ra: number; dec: number; label?: string; big?: boolean }

const RAD = Math.PI / 180;
// Planet Nine's predicted track (Brown & Batygin 2021; derived in docs/PLANET_NINE_RESEARCH.md, approximate)
const P9: [number, number][] = [[33, -2], [46, 4], [60, 11], [74, 16], [90, 21], [107, 25]];
// the ecliptic: where the planets travel
const ECL: [number, number][] = Array.from({ length: 73 }, (_, i) => {
  const l = i * 5 * RAD, e = 23.44 * RAD;
  return [Math.atan2(Math.sin(l) * Math.cos(e), Math.cos(l)) / RAD, Math.asin(Math.sin(e) * Math.sin(l)) / RAD] as [number, number];
});

/** The sky as a line-drawn sphere, seen from outside. Drag to turn it. Dots are places PARALLAX searched. */
const LIGHT = { front: 'rgba(10,10,10,0.55)', back: 'rgba(10,10,10,0.12)', rim: '#0a0a0a', ecl: 'rgba(10,10,10,0.9)', eclBack: 'rgba(10,10,10,0.2)', p9: 'rgba(10,10,10,0.95)', p9Back: 'rgba(10,10,10,0.2)', dot: '#0a0a0a', dotBack: 'rgba(10,10,10,0.18)', big: '#0a0a0a', ring: 'rgba(10,10,10,0.5)', tag: 'rgba(244,244,244,0.9)', text: '#0a0a0a', p9Text: '#0a0a0a' };
// on the navy block: pale blue lines, sky-blue patches, orange for named worlds and the Planet Nine track
const DARK = { front: 'rgba(205,218,255,0.5)', back: 'rgba(205,218,255,0.1)', rim: 'rgba(225,233,255,0.95)', ecl: 'rgba(255,255,255,0.75)', eclBack: 'rgba(255,255,255,0.16)', p9: '#ff7a3d', p9Back: 'rgba(255,122,61,0.25)', dot: '#9fbcff', dotBack: 'rgba(159,188,255,0.22)', big: '#ff6a2b', ring: 'rgba(255,150,100,0.65)', tag: 'rgba(11,21,48,0.88)', text: '#ffffff', p9Text: '#ffb08a' };

export function SkyGlobe({ points, dark = false }: { points: GlobePoint[]; dark?: boolean }) {
  const C = dark ? DARK : LIGHT;
  const ref = useRef<HTMLCanvasElement>(null);
  const pts = useRef(points);
  pts.current = points;

  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    let yaw = 200 * RAD, pitch = 18 * RAD, vel = 0.0016, drag: { x: number; y: number } | null = null, raf = 0, alive = true;
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const project = (ra: number, dec: number, R: number, cx: number, cy: number) => {
      const a = ra * RAD + yaw, d = dec * RAD;
      const x = Math.cos(d) * Math.sin(a), y0 = Math.sin(d), z0 = Math.cos(d) * Math.cos(a);
      const y = y0 * Math.cos(pitch) - z0 * Math.sin(pitch), z = y0 * Math.sin(pitch) + z0 * Math.cos(pitch);
      return { x: cx + R * x, y: cy - R * y, z };
    };

    const draw = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = c.clientWidth, h = c.clientHeight;
      if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const R = Math.min(w, h) * 0.44, cx = w / 2, cy = h / 2;
      const line = (path: [number, number][], front: string, back: string, width: number, dash: number[] = []) => {
        for (const side of [false, true]) {
          ctx.beginPath();
          let pen = false;
          for (const [ra, dec] of path) {
            const p = project(ra, dec, R, cx, cy);
            if ((p.z >= 0) === side) { if (pen) ctx.lineTo(p.x, p.y); else { ctx.moveTo(p.x, p.y); pen = true; } } else pen = false;
          }
          ctx.strokeStyle = side ? front : back;
          ctx.lineWidth = width;
          ctx.setLineDash(dash);
          ctx.stroke();
        }
        ctx.setLineDash([]);
      };
      // graticule
      for (let dec = -60; dec <= 60; dec += 30) line(Array.from({ length: 121 }, (_, i) => [i * 3, dec] as [number, number]), C.front, C.back, dec === 0 ? 1.3 : 0.9);
      for (let ra = 0; ra < 360; ra += 30) line(Array.from({ length: 61 }, (_, i) => [ra, -90 + i * 3] as [number, number]), C.front, C.back, 0.9);
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.strokeStyle = C.rim; ctx.lineWidth = 1.6; ctx.stroke();
      line(ECL, C.ecl, C.eclBack, 1.2, [5, 5]);
      line(P9, C.p9, C.p9Back, 3);
      // places
      ctx.font = '600 11px Barlow, sans-serif';
      for (const p of pts.current) {
        const q = project(p.ra, p.dec, R, cx, cy);
        const front = q.z >= 0;
        ctx.beginPath(); ctx.arc(q.x, q.y, p.big ? 5 : 2.6, 0, Math.PI * 2);
        ctx.fillStyle = front ? (p.big ? C.big : C.dot) : C.dotBack; ctx.fill();
        if (p.big && front) {
          ctx.beginPath(); ctx.arc(q.x, q.y, 10, 0, Math.PI * 2); ctx.strokeStyle = C.ring; ctx.lineWidth = 1; ctx.stroke();
          if (p.label) {
            const right = q.x >= cx;
            const tx = q.x + (right ? 18 : -18);
            ctx.beginPath(); ctx.moveTo(q.x + (right ? 10 : -10), q.y); ctx.lineTo(tx - (right ? 3 : -3), q.y); ctx.strokeStyle = C.ring; ctx.stroke();
            ctx.textAlign = right ? 'left' : 'right'; ctx.textBaseline = 'middle';
            const text = p.label.toUpperCase();
            const tw = ctx.measureText(text).width + 12;
            ctx.fillStyle = C.tag; ctx.fillRect(right ? tx - 3 : tx - tw + 3, q.y - 9, tw, 18);
            ctx.fillStyle = C.text;
            // letter-spaced capitals
            (ctx as CanvasRenderingContext2D & { letterSpacing?: string }).letterSpacing = '1.6px';
            ctx.fillText(text, tx + (right ? 3 : -3), q.y + 0.5);
          }
        }
      }
      const pn = project(60, 11, R, cx, cy);
      if (pn.z >= 0) {
        ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillStyle = C.p9Text;
        ctx.fillText('PLANET NINE ZONE', pn.x + 12, pn.y - 14);
      }
    };

    let seen = true;
    const loop = () => {
      raf = 0;
      if (!alive || !seen) return;
      if (!drag && !still) yaw += vel;
      draw();
      raf = requestAnimationFrame(loop);
    };
    const io = new IntersectionObserver(([e]) => { seen = e.isIntersecting; if (seen && !raf) raf = requestAnimationFrame(loop); });
    io.observe(c);
    const down = (e: PointerEvent) => { drag = { x: e.clientX, y: e.clientY }; c.setPointerCapture(e.pointerId); };
    const move = (e: PointerEvent) => {
      if (!drag) return;
      yaw += (e.clientX - drag.x) * 0.006;
      pitch = Math.max(-1.2, Math.min(1.2, pitch + (e.clientY - drag.y) * 0.006));
      drag = { x: e.clientX, y: e.clientY };
      if (still) draw();
    };
    const up = () => { drag = null; };
    c.addEventListener('pointerdown', down);
    c.addEventListener('pointermove', move);
    c.addEventListener('pointerup', up);
    c.addEventListener('pointercancel', up);
    loop();
    return () => { alive = false; io.disconnect(); cancelAnimationFrame(raf); c.removeEventListener('pointerdown', down); c.removeEventListener('pointermove', move); c.removeEventListener('pointerup', up); c.removeEventListener('pointercancel', up); };
  }, [C]);

  return <canvas ref={ref} role="img" aria-label="A line-drawn sphere of the whole sky that slowly turns. Dots mark the patches PARALLAX searched; labels mark Makemake, Eris, the coldest brown dwarf and the zone where Planet Nine is predicted." />;
}
