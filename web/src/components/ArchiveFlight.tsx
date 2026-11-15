import { useEffect, useRef } from 'react';
import type { Field } from '../api.ts';
import './ArchiveFlight.css';

type ArchiveProgress = NonNullable<Field['progress']>;

export function ArchiveProgressText({ progress }: { progress: ArchiveProgress | null }) {
  const stage = progress?.stage === 'queued' ? 'Waiting for an archive worker' : progress?.stage;
  return (
    <div className="archive-progress">
      <p role="status">{stage ?? 'Opening the SPHEREx field'}{' '}
        {!!progress?.total && <span className="mono">{progress.done} of {progress.total} checked</span>}
      </p>
      {!!progress?.total && <progress value={progress.done} max={progress.total} aria-label="SPHEREx cutouts checked" />}
    </div>
  );
}

export function ArchiveFlight({ reducedMotion, progress, coordinates }: {
  reducedMotion: boolean; progress: ArchiveProgress | null; coordinates: string | null;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    const depth = 7;
    const near = 0.34;
    const colors = ['#e6ecff', '#bdcbed', '#a7b6db', '#f6d9b0'];
    let seed = 1329;
    function random() {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      return seed / 4294967296;
    }
    const stars = Array.from({ length: 420 }, (_, i) => ({
      x: (random() - .5) * 16,
      y: (random() - .5) * 13,
      z: near + random() * (depth - near),
      magnitude: .2 + random() ** 3 * .8,
      color: colors[i % colors.length],
    }));
    let width = 0, height = 0, raf = 0, last = 0;
    let inView = true;

    function draw(elapsed: number) {
      if (!ctx) return;
      ctx.clearRect(0, 0, width, height);
      const cx = width * .5, cy = height * .43;
      const focal = Math.min(width, height) * .82;
      for (const star of stars) {
        star.z -= elapsed * .0011;
        if (star.z < near) star.z += depth - near;
        const scale = focal / star.z;
        const x = cx + star.x * scale, y = cy + star.y * scale;
        if (x < -10 || x > width + 10 || y < -10 || y > height + 10) continue;
        const approach = 1 - star.z / depth;
        const size = .4 + approach * star.magnitude * 1.5;
        ctx.fillStyle = ctx.strokeStyle = star.color;
        ctx.globalAlpha = star.magnitude * (.26 + approach * .74);
        ctx.fillRect(x - size / 2, y - size / 2, size, size);
        if (!reducedMotion && approach > .34) {
          const tail = approach ** 3 * .32;
          ctx.globalAlpha *= .42;
          ctx.lineWidth = Math.max(.65, size * .7);
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(x + (cx - x) * tail, y + (cy - y) * tail);
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;
    }

    function tick(now: number) {
      const elapsed = last ? now - last : 0;
      if (!last || elapsed >= 24) {
        draw(Math.min(50, elapsed));
        last = now;
      }
      raf = requestAnimationFrame(tick);
    }

    function updateAnimation() {
      if (raf) cancelAnimationFrame(raf);
      raf = last = 0;
      if (inView && !document.hidden && !reducedMotion) raf = requestAnimationFrame(tick);
    }

    const resize = new ResizeObserver(([entry]) => {
      width = entry.contentRect.width;
      height = entry.contentRect.height;
      const ratio = Math.min(1.5, window.devicePixelRatio || 1);
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      draw(0);
    });
    const intersection = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      updateAnimation();
    });
    resize.observe(canvas);
    intersection.observe(canvas);
    document.addEventListener('visibilitychange', updateAnimation);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      resize.disconnect();
      intersection.disconnect();
      document.removeEventListener('visibilitychange', updateAnimation);
    };
  }, [reducedMotion]);

  return (
    <div className="sky archive-flight">
      <canvas ref={canvasRef} aria-hidden="true" />
      <div className="archive-flight__reticle" aria-hidden="true" />
      <div className="archive-flight__readout">
        <h2>Finding your sky field</h2>
        <ArchiveProgressText progress={progress} />
        {coordinates && <p className="archive-flight__coordinates mono">{coordinates}</p>}
      </div>
      <p className="archive-flight__caption">Simulated starfield</p>
    </div>
  );
}
