import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';

interface Frame { src: string; x: number; y: number; date: string; wavelength_um: number; obs_id: string }
interface Streak { in: 'a' | 'b'; x1: number; y1: number; x2: number; y2: number }
export interface Level {
  id: string; title: string; what: string; note: string; w: number; h: number; frames: Frame[];
  moved_arcsec: number; hours: number; distance_au: number | null; streaks?: Streak[];
}

const BLINK_MS = 700;
const HIT_PX = 10;   // native SPHEREx pixels (6.15″ each) around either position, or along the hop between them
const SAT_PX = 5;

function distToSegment(px: number, py: number, ax: number, ay: number, bx: number, by: number) {
  const dx = bx - ax, dy = by - ay;
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy || 1)));
  return Math.hypot(px - ax - t * dx, py - ay - t * dy);
}
const day = (s: string) => s.replace(/, \d\d:\d\d UTC$/, '');
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** "Spot what moves": two real NASA SPHEREx photos of the same sky, flipping. Tap the dot that hops. */
export function SpotGame({ onMeasure }: { onMeasure?: () => void } = {}) {
  const [level, setLevel] = useState<Level | null>(null);
  const [failed, setFailed] = useState(false);
  const [k, setK] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [found, setFound] = useState<'found' | 'shown' | null>(null);
  const [misses, setMisses] = useState(0);
  const [toast, setToast] = useState<string | null>(null);
  const [pings, setPings] = useState<{ x: number; y: number; id: number }[]>([]);
  const [box, setBox] = useState({ w: 0, h: 0 });
  const win = useRef<HTMLDivElement>(null);
  const toastTimer = useRef(0);

  useEffect(() => {
    fetch('/blink/levels.json')
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((ls: Level[]) => (ls[0] ? setLevel(ls[0]) : setFailed(true)))
      .catch(() => setFailed(true));
    if (reduced()) setPlaying(false);
  }, []);

  useEffect(() => {
    if (!playing || !level) return;
    const id = window.setInterval(() => setK(v => 1 - v), BLINK_MS);
    return () => window.clearInterval(id);
  }, [playing, level]);

  useLayoutEffect(() => {
    const el = win.current;
    if (!el) return;
    const update = () => setBox({ w: el.clientWidth, h: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  function say(text: string) {
    setToast(text);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 3200);
  }

  // Fill the window, zoomed in a little and centred on the hop, never showing an empty edge.
  const geo = (() => {
    if (!level || !box.w) return null;
    const [a, b] = level.frames;
    const fx = (a.x + b.x) / 2, fy = (a.y + b.y) / 2;
    const zoom = box.w / box.h > 1.2 ? 1.3 : 1.2;
    const s = Math.max(box.w / level.w, box.h / level.h) * zoom;
    const dw = level.w * s, dh = level.h * s;
    const ox = Math.min(0, Math.max(box.w - dw, box.w / 2 - fx * dw));
    const oy = Math.min(0, Math.max(box.h - dh, box.h / 2 - fy * dh));
    return { s, dw, dh, ox, oy };
  })();
  const at = (f: { x: number; y: number }) => (geo ? { left: geo.ox + f.x * geo.dw, top: geo.oy + f.y * geo.dh } : { left: 0, top: 0 });

  function onTap(e: PointerEvent<HTMLDivElement>) {
    if (!level || !geo || found) return;
    const r = e.currentTarget.getBoundingClientRect();
    const sx = e.clientX - r.left, sy = e.clientY - r.top;
    const px = ((sx - geo.ox) / geo.dw) * level.w, py = ((sy - geo.oy) / geo.dh) * level.h;
    const [a, b] = level.frames;
    const id = Date.now();
    setPings(p => [...p.slice(-3), { x: sx, y: sy, id }]);
    window.setTimeout(() => setPings(p => p.filter(q => q.id !== id)), 700);
    if (distToSegment(px, py, a.x * level.w, a.y * level.h, b.x * level.w, b.y * level.h) <= HIT_PX) {
      setFound('found'); setToast(null); return;
    }
    if ((level.streaks ?? []).some(t => distToSegment(px, py, t.x1 * level.w, t.y1 * level.h, t.x2 * level.w, t.y2 * level.h) <= SAT_PX)) {
      say('That streak is probably a satellite, crossing in a few seconds. Look for a dot that hops.');
      return;
    }
    const n = misses + 1;
    setMisses(n);
    say(n >= 2 ? 'Close. Look inside the dashed circle.' : 'That one is a star. It stays put.');
  }

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); setPlaying(false); setK(v => 1 - v); }
  }

  function again() { setFound(null); setMisses(0); setToast(null); setPlaying(!reduced()); }

  const [a, b] = level?.frames ?? [];
  const ringR = geo ? Math.max(20, 9 * geo.s) : 24;
  const mid = level ? at({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }) : null;
  const pos = () => geo ? { left: geo.ox, top: geo.oy, width: geo.dw, height: geo.dh } : { left: 0, top: 0, width: '100%', height: '100%' };

  return (
    <div className="game">
      <div
        ref={win}
        className="game__win"
        onPointerDown={onTap}
        onKeyDown={onKey}
        tabIndex={0}
        role="img"
        aria-label={level ? `Two NASA SPHEREx photos of the same patch of sky, taken ${day(a.date)} and ${day(b.date)}, shown one after the other. One dot moves. Press space to flip by hand, or use Show me.` : 'Loading two photos of the sky'}
      >
        {level && level.frames.map((f, i) => (
          <img key={f.src} src={f.src} alt="" draggable={false} className={i === k ? '' : 'is-hidden'} style={pos()} />
        ))}
        {failed && <p className="game__toast" style={{ animation: 'none' }}>The photos could not be loaded.</p>}
        {level && (
          <div className="game__hud" aria-hidden="true">
            <span className={`game__frame game__frame--${k === 0 ? 'then' : 'now'}`}>{day(level.frames[k].date)}</span>
            <span className="game__src">NASA SPHEREx · real data</span>
          </div>
        )}
        {level && geo && !found && misses >= 2 && mid && (
          <span className="game__hint" style={{ left: mid.left, top: mid.top, width: ringR * 6, height: ringR * 6 }} />
        )}
        {level && geo && found && level.frames.map((f, i) => {
          const p = at(f);
          return <span key={f.src} className={`game__ring game__ring--${i ? 'now' : 'then'}${i === k ? '' : ' is-dim'}`} style={{ left: p.left, top: p.top, width: ringR * 2, height: ringR * 2 }} />;
        })}
        {pings.map(p => <span key={p.id} className="game__ping" style={{ left: p.x, top: p.y }} />)}
        {toast && <p className="game__toast" role="status">{toast}</p>}
      </div>

      {level && !found && (
        <div className="game__bar">
          <div className="seg" role="group" aria-label="Which photo">
            <button type="button" aria-pressed={k === 0} onClick={() => { setPlaying(false); setK(0); }}>{day(a.date)}</button>
            <button type="button" aria-pressed={k === 1} onClick={() => { setPlaying(false); setK(1); }}>{day(b.date)}</button>
          </div>
          <button type="button" className="pill pill--quiet pill--sm" onClick={() => setPlaying(v => !v)}>{playing ? 'Pause' : 'Flip'}</button>
          <button type="button" className="pill pill--line pill--sm" onClick={() => { setFound('shown'); setToast(null); }}>Show me</button>
        </div>
      )}

      {level && found && (
        <div className="result" role="status">
          <div>
            <p className="eyebrow-x">{found === 'found' ? 'You found it' : 'Here it is'}</p>
            <h2>{level.title}, a dwarf planet.</h2>
          </div>
          <div className="result__facts">
            <div><b>{level.distance_au ? (level.distance_au * 0.1496).toFixed(1) : '—'} bn km</b><span>from the Sun. {level.distance_au ? Math.round(level.distance_au) : '—'} times Earth's distance.</span></div>
            <div><b>{Math.round(level.moved_arcsec)}″</b><span>moved in {Math.round(level.hours / 24 * 2) / 2} days, from the <i className="c-then">dashed</i> ring to the <i className="c-now">solid</i> one.</span></div>
            <div><b>81 images</b><span>Our software searched them and found it the same way, with no hints.</span></div>
          </div>
          <div className="result__go">
            {onMeasure
              ? <button type="button" className="pill pill--solid pill--sm" onClick={onMeasure}>How far is that?</button>
              : <a className="pill pill--solid pill--sm" href="#how-far">How far is that?</a>}
            <button type="button" className="pill pill--line pill--sm" onClick={again}>Play again</button>
          </div>
        </div>
      )}
    </div>
  );
}
