import { useEffect, useRef } from 'react';

/**
 * Ambient star layers that shift against each other when the pointer moves. That shift is
 * parallax, the apparent shift caused by a change in viewpoint. The starfield is decorative.
 */
export function Starfield() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let w = 0, h = 0, raf = 0, px = 0, py = 0, tx = 0, ty = 0;
    let stars: { x: number; y: number; z: number; r: number; a: number; tint: number }[] = [];
    let s = 20261114;
    const rnd = () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296;

    function draw() {
      ctx!.clearRect(0, 0, w, h);
      for (const st of stars) {
        const k = 8 + st.z * 46;
        let x = (st.x + px * k) % w; if (x < 0) x += w;
        let y = (st.y + py * k) % h; if (y < 0) y += h;
        ctx!.globalAlpha = st.a;
        ctx!.fillStyle = st.tint > 0.88 ? '#ffc98a' : st.tint < 0.14 ? '#9db3ff' : '#eef1fb';
        ctx!.beginPath();
        ctx!.arc(x, y, st.r, 0, 6.2832);
        ctx!.fill();
      }
      ctx!.globalAlpha = 1;
    }
    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas!.clientWidth; h = canvas!.clientHeight;
      canvas!.width = Math.max(1, Math.round(w * dpr)); canvas!.height = Math.max(1, Math.round(h * dpr));
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      s = 20261114;
      const n = Math.min(460, Math.round((w * h) / 4600));
      stars = Array.from({ length: n }, () => {
        const z = rnd();
        return { x: rnd() * w, y: rnd() * h, z, r: 0.3 + z * z * 1.3, a: 0.18 + z * 0.72, tint: rnd() };
      });
      draw();
    }
    function frame() {
      px += (tx - px) * 0.07; py += (ty - py) * 0.07;
      draw();
      raf = Math.abs(tx - px) + Math.abs(ty - py) > 0.0006 ? requestAnimationFrame(frame) : 0;
    }
    function move(e: PointerEvent) {
      tx = e.clientX / window.innerWidth - 0.5; ty = e.clientY / window.innerHeight - 0.5;
      if (!raf) raf = requestAnimationFrame(frame);
    }
    resize();
    window.addEventListener('resize', resize);
    if (!reduce) window.addEventListener('pointermove', move, { passive: true });
    return () => {
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', move);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);
  return <canvas ref={ref} className="starfield" aria-hidden="true" />;
}
