import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Page } from '../components/Shell.tsx';
import { HowFar } from '../components/HowFar.tsx';
import { Link } from '../router.tsx';
import '../how.css';

/* ---------- data from /api/how, /api/distant and /api/coldspec (every part optional) ---------- */

interface Visit { n_images: number; mjd_start: number; span_days: number }
interface Inj { distance_au: number; flux_ujy: number; n_injected: number; n_measured: number; n_recovered: number }
interface Deep {
  field: string; ra: number; dec: number; visits: Visit[]; n_photos: number | null; n_images: number; n_visits: number; area_deg2: number;
  single_5sigma_ujy: number; n_candidates: number; n_still_changes: number; injection: Inj[] | null; injection_visit_images: number | null;
  n_passed_checks: number | null; chance_expected: number;
}
interface Running { n: number; snr: number[][] }
interface Example {
  name: string; V: number; class: string; n_images: number; stack_snr: number; best_single_snr: number; seen_single: boolean; pixel_arcsec: number;
  path: { running: Running[] }; control?: { running: Running[] };
}
interface HowDoc {
  still?: { patches: number; dots: number; still: number; left: number; example: { id: string; paired_detections: number; fixed_sources_removed: number; night_detections: number; epochs: number } | null };
  track?: { name: string; V: number; rate_arcsec_h: number; rms_arcsec: number; points: { mjd: number; x: number; y: number }[]; chance_tracks_expected: number | null };
  stack?: { by_V: { V: string; n: number; single: number; stack: number }[]; n_asteroids: number; n_seen_single: number; n_seen_stack: number; threshold_stack_snr: number;
    examples: Example[]; n_control_paths: number; n_seen_stack_snr5: number; n_control_snr5: number };
  deep: Deep[];
  planet_nine?: { flux_ujy: number; flux_range_ujy: [number, number]; r_au: number };
  ledger: { ok: boolean; n: number; last: { seq: number; label: string; hash: string; time_utc: string }[] };
}
interface DistantBody { body: string; title: string; match: { r_fit_au: number; r_true_au: number } | null }
interface Spec { um: number; ujy: number; err: number }
interface ColdDoc {
  cv: { held_out: { T_found: number; T_total: number; false_T: number; not_T_total: number } };
  wide: { candidates: { n_strong: number; candidates: { name: string; pred_type: string; grade: string; snr_J: number; spectrum: Spec[] }[] } | null } | null;
}

const json = <T,>(u: string) => fetch(u).then(r => (r.ok ? (r.json() as Promise<T>) : null)).catch(() => null);
const fmt = (n: number) => n.toLocaleString('en-US');
const month = (mjd: number) => new Date((mjd - 40587) * 86400000).toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });

/** The faintest synthetic planet found at least half the time (at 550 AU); null if none was. */
function depth50(inj: Inj[] | null): number | null {
  const at = (inj ?? []).filter(r => r.distance_au === 550 && r.n_measured > 0).sort((a, b) => a.flux_ujy - b.flux_ujy);
  const ok = at.find(r => r.n_recovered / r.n_measured >= 0.5);
  return ok ? ok.flux_ujy : null;
}

/* ---------- step layout ---------- */

function Step({ n, title, children, fig, id }: { n: number; title: string; children: ReactNode; fig: ReactNode; id: string }) {
  return (
    <li className="how-step rv" id={id} aria-labelledby={`${id}-h`}>
      <div className="how-step__text">
        <p className="how-step__n"><span>Step</span> {String(n).padStart(2, '0')}</p>
        <h2 id={`${id}-h`} className="how-step__h">{title}</h2>
        {children}
      </div>
      <div className="how-step__fig">{fig}</div>
    </li>
  );
}

function Fact({ v, t }: { v: ReactNode; t: ReactNode }) {
  return <p className="how-fact"><span className="how-fact__v">{v}</span><span className="how-fact__t">{t}</span></p>;
}

/* ---------- 01: many photos of one patch ---------- */

function Visits({ d }: { d: Deep }) {
  const t0 = d.visits[0].mjd_start, t1 = Math.max(...d.visits.map(v => v.mjd_start + v.span_days));
  const W = 640, x = (m: number) => 48 + ((m - t0) / (t1 - t0)) * (W - 96);
  return (
    <figure className="how-card">
      <svg viewBox={`0 0 ${W} 150`} className="how-svg" role="img" aria-label={`${d.n_photos ?? d.n_images} photos of one patch of sky, in ${d.visits.length} visits`}>
        <line x1={24} x2={W - 24} y1={96} y2={96} className="how-axis" />
        {d.visits.map((v, i) => {
          const a = x(v.mjd_start), b = Math.max(x(v.mjd_start + v.span_days), a + 6);
          const ticks = Array.from({ length: v.n_images }, (_, k) => a + ((b - a) * (k + 0.5)) / v.n_images);
          return (
            <g key={i}>
              {ticks.map((tx, k) => <line key={k} x1={tx} x2={tx} y1={70} y2={96} className="how-tick" />)}
              {v.n_images >= 10 && (
                <>
                  <text x={(a + b) / 2} y={56} textAnchor="middle" className="how-svg__big">{v.n_images}</text>
                  <text x={(a + b) / 2} y={122} textAnchor="middle" className="how-svg__small">{month(v.mjd_start)}</text>
                </>
              )}
            </g>
          );
        })}
      </svg>
      <figcaption>Every line is one photo of the same patch of sky (RA {d.ra}°, Dec {d.dec}°), on Planet Nine's predicted path.</figcaption>
    </figure>
  );
}

/* ---------- 02: remove what stays still ---------- */

function Waffle({ dots, left }: { dots: number; left: number }) {
  const per = 10, n = Math.round(dots / per), lit = Math.max(1, Math.round(left / per)), cols = 46;
  const on = useMemo(() => {
    let s = 7; const pick = new Set<number>();
    while (pick.size < lit) { s = (s * 16807) % 2147483647; pick.add(s % n); }
    return pick;
  }, [n, lit]);
  const rows = Math.ceil(n / cols), c = 13;
  return (
    <figure className="how-card">
      <svg viewBox={`0 0 ${cols * c} ${rows * c}`} className="how-svg" role="img" aria-label={`${fmt(dots)} dots; ${fmt(dots - left)} stayed still; ${fmt(left)} left`}>
        {Array.from({ length: n }, (_, i) => (
          <rect key={i} x={(i % cols) * c + 1.5} y={Math.floor(i / cols) * c + 1.5} width={c - 3} height={c - 3} rx={2} className={on.has(i) ? 'how-w how-w--on' : 'how-w'} />
        ))}
      </svg>
      <figcaption>Each square is {per} dots. Grey: stayed still, so removed. White: left over.</figcaption>
    </figure>
  );
}

/* ---------- 03: join the dots ---------- */

function Track({ t }: { t: NonNullable<HowDoc['track']> }) {
  const xs = t.points.map(p => p.x), ys = t.points.map(p => p.y);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) * 1.25;
  const W = 640, H = 360, s = Math.min(W, H * 1.6) / span;
  const px = (x: number) => W / 2 + (x - cx) * s, py = (y: number) => H / 2 - (y - cy) * s;
  const t0 = t.points[0].mjd;
  return (
    <figure className="how-card">
      <svg viewBox={`0 0 ${W} ${H}`} className="how-svg" role="img" aria-label={`${t.name}: four nights, one straight line`}>
        <line x1={px(xs[0])} y1={py(ys[0])} x2={px(xs[xs.length - 1])} y2={py(ys[ys.length - 1])} className="how-track" />
        {t.points.map((p, i) => {
          const last = i === t.points.length - 1;
          return (
            <g key={i}>
              <circle cx={px(p.x)} cy={py(p.y)} r={last ? 9 : 8} className={last ? 'how-dot how-dot--now' : 'how-dot'} />
              <text x={px(p.x)} y={py(p.y) + (i % 2 ? 34 : -22)} textAnchor="middle" className="how-svg__small">{i === 0 ? 'First seen' : `+${((p.mjd - t0) * 24).toFixed(0)} hours`}</text>
            </g>
          );
        })}
        <line x1={24} x2={24 + 60 * s} y1={H - 24} y2={H - 24} className="how-scale" />
        <text x={24} y={H - 34} className="how-svg__small">1 arcminute</text>
      </svg>
      <figcaption>{t.name}, a main-belt asteroid, found by our software with no hints: seen {t.points.length} times over {Math.round((t.points[t.points.length - 1].mjd - t0) * 24)} hours, on one straight line, moving {Math.round(t.rate_arcsec_h)}″ an hour.</figcaption>
    </figure>
  );
}

/* ---------- 05: stacking, with real pictures ---------- */

function Stamp({ snr, label }: { snr: number[][]; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current; if (!c) return;
    const n = snr.length, g = c.getContext('2d'); if (!g) return;
    c.width = n; c.height = n;
    const img = g.createImageData(n, n);
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
      const v = Math.max(0, Math.min(1, (snr[n - 1 - y][x] + 3) / 11));      // fixed scale for every frame: -3 to +8 sigma
      const k = (y * n + x) * 4, b = Math.round(255 * Math.pow(v, 1.4));
      img.data[k] = b; img.data[k + 1] = b; img.data[k + 2] = b; img.data[k + 3] = 255;
    }
    g.putImageData(img, 0, 0);
  }, [snr]);
  return (
    <div className="how-stamp">
      <div className="how-stamp__box">
        <canvas ref={ref} role="img" aria-label={label} />
        <i className="how-stamp__tick how-stamp__tick--t" /><i className="how-stamp__tick how-stamp__tick--b" />
        <i className="how-stamp__tick how-stamp__tick--l" /><i className="how-stamp__tick how-stamp__tick--r" />
      </div>
      <p className="how-stamp__cap">{label}</p>
    </div>
  );
}

function StackViewer({ e }: { e: Example }) {
  const steps = e.path.running;
  const [k, setK] = useState(0);
  const cur = steps[k], ctl = e.control?.running.find(r => r.n === cur.n);
  const centre = (m: number[][]) => m[Math.floor(m.length / 2)][Math.floor(m.length / 2)];
  return (
    <figure className="how-card">
      <div className="how-stack">
        <Stamp snr={cur.snr} label="Along its path" />
        {ctl && <Stamp snr={ctl.snr} label="60″ away (no asteroid)" />}
      </div>
      <div className="how-slider">
        <label htmlFor="how-n">Photos added: <b>{cur.n}</b></label>
        <input id="how-n" type="range" min={0} max={steps.length - 1} step={1} value={k} onChange={ev => setK(Number(ev.target.value))}
          aria-valuetext={`${cur.n} photos`} />
        <span className="how-slider__snr">Signal {centre(cur.snr).toFixed(1)}σ</span>
      </div>
      <figcaption>Asteroid {e.name} (magnitude {e.V}). In single photos it never passes {e.best_single_snr.toFixed(1)}σ; measured over all {e.n_images} of its photos, {e.stack_snr.toFixed(1)}σ. The ticks point at where it should be. Real SPHEREx photos, shifted to follow it.</figcaption>
    </figure>
  );
}

/* ---------- 06: 102 colours ---------- */

function Spectrum({ s, name, type }: { s: Spec[]; name: string; type: string }) {
  const p = s.filter(q => q.ujy > -4 * q.err);
  const W = 640, H = 300, L = 44, R = 16, T = 18, B = 40;
  const x0 = 0.7, x1 = 5.1, top = Math.max(...p.map(q => q.ujy + q.err)) * 1.08;
  const sx = (u: number) => L + ((u - x0) / (x1 - x0)) * (W - L - R), sy = (v: number) => H - B - (Math.max(v, 0) / top) * (H - T - B);
  const bands: [number, number, string][] = [[1.62, 1.85, 'methane'], [2.18, 2.45, 'methane'], [3.15, 3.45, 'methane']];
  return (
    <figure className="how-card">
      <svg viewBox={`0 0 ${W} ${H}`} className="how-svg" role="img" aria-label={`SPHEREx spectrum of ${name}: dark dips where methane absorbs`}>
        {bands.map(([a, b, l], i) => (
          <g key={i}>
            <rect x={sx(a)} y={T} width={sx(b) - sx(a)} height={H - T - B} className="how-band" />
            <text x={(sx(a) + sx(b)) / 2} y={T + 14} textAnchor="middle" className="how-svg__small">{l}</text>
          </g>
        ))}
        <line x1={L} x2={W - R} y1={H - B} y2={H - B} className="how-axis" />
        {[1, 2, 3, 4, 5].map(u => <text key={u} x={sx(u)} y={H - B + 22} textAnchor="middle" className="how-svg__num">{u} µm</text>)}
        {p.map((q, i) => <line key={'e' + i} x1={sx(q.um)} x2={sx(q.um)} y1={sy(q.ujy - q.err)} y2={sy(q.ujy + q.err)} className="how-err" />)}
        <polyline points={p.map(q => `${sx(q.um).toFixed(1)},${sy(q.ujy).toFixed(1)}`).join(' ')} className="how-line" />
        {p.map((q, i) => <circle key={i} cx={sx(q.um)} cy={sy(q.ujy)} r={3} className="how-pt" />)}
      </svg>
      <figcaption>{name}: our model reads it as type {type}, a cold brown dwarf. The grey bands are where methane eats the light.</figcaption>
    </figure>
  );
}

/* ---------- 07: the seal ---------- */

function Chain({ l }: { l: HowDoc['ledger'] }) {
  return (
    <figure className="how-card">
      <ol className="how-chain">
        {l.last.map((e, i) => (
          <li key={e.seq} className="how-chain__b">
            <span className="how-chain__seq">#{e.seq}</span>
            <span className="how-chain__lab">{e.label}</span>
            <code className="how-chain__hash">{e.hash}…</code>
            {i < l.last.length - 1 && <span className="how-chain__link" aria-hidden="true" />}
          </li>
        ))}
      </ol>
      <figcaption>The last {l.last.length} of {l.n} seals. Each one includes the fingerprint of the one before, so nothing can be quietly changed. {l.ok ? 'Right now every seal checks out.' : 'A seal does not check out right now.'}</figcaption>
    </figure>
  );
}

/* ---------- 08: what we cannot see ---------- */

function Depth({ single, stack, p9 }: { single: number; stack: number | null; p9: NonNullable<HowDoc['planet_nine']> }) {
  const lo = 1, hi = 1000;
  const at = (f: number) => `${((Math.log10(f) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * 100}%`;
  const reach = stack ?? single;
  const rows: { f: number; lab: string; us: boolean }[] = [
    { f: single, lab: 'One photo', us: true },
    ...(stack ? [{ f: stack, lab: 'One visit, photos added', us: true }] : []),
    { f: p9.flux_range_ujy[1], lab: 'Planet Nine, brightest guess', us: false },
    { f: p9.flux_ujy, lab: 'Planet Nine, best guess', us: false },
  ];
  return (
    <figure className="how-card">
      <div className="how-depth" role="img" aria-label={`We can see down to about ${Math.round(reach)} microjansky. Planet Nine is predicted at ${p9.flux_ujy.toFixed(1)}.`}>
        {rows.map(r => (
          <div key={r.lab} className="how-depth__row">
            <p className="how-depth__lab"><span>{r.lab}</span><b>{r.f < 10 ? r.f.toFixed(1) : Math.round(r.f)} µJy</b></p>
            <div className="how-depth__track">
              <i className="how-depth__dark" style={{ width: at(reach) }} />
              <i className={`how-depth__mark${r.us ? '' : ' how-depth__mark--p9'}`} style={{ left: at(r.f) }} />
            </div>
          </div>
        ))}
        <div className="how-depth__axis" aria-hidden="true">
          {[1, 10, 100, 1000].map(f => <span key={f} style={{ left: at(f) }}>{fmt(f)}</span>)}
        </div>
        <p className="how-depth__ends" aria-hidden="true"><span>← fainter</span><span>too faint for us: shaded</span><span>brighter →</span></p>
      </div>
      <figcaption>Brightness in microjansky (µJy) near 1 micron, on a scale where each step is ten times brighter. Solid marks: what we reach. Dashed: the Planet Nine prediction (Brown, Holman &amp; Batygin 2024).</figcaption>
    </figure>
  );
}

/* ---------- the page ---------- */

export function How() {
  const [how, setHow] = useState<HowDoc | null>(null);
  const [dist, setDist] = useState<{ bodies: DistantBody[] } | null>(null);
  const [cold, setCold] = useState<ColdDoc | null>(null);
  useEffect(() => {
    json<HowDoc>('/api/how').then(setHow);
    json<{ bodies: DistantBody[] }>('/api/distant').then(setDist);
    json<ColdDoc>('/api/coldspec').then(setCold);
  }, []);
  // A link like /how#s5 should land on that step once the page has drawn (the browser tries before the page exists).
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (!id || !how) return;
    const t = window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: 'start' }), 60);
    return () => window.clearTimeout(t);
  }, [how]);
  const deep = how?.deep ?? [];
  const busiest = deep.length ? deep.reduce((a, b) => ((b.n_photos ?? 0) > (a.n_photos ?? 0) ? b : a)) : null;
  // the patch whose added-up photos reach deepest (synthetic planets found half the time), with its own single-photo depth
  const ranked = deep.map(d => ({ d, h: depth50(d.injection) })).sort((a, b) => (a.h ?? 1e9) - (b.h ?? 1e9) || a.d.single_5sigma_ujy - b.d.single_5sigma_ujy);
  const cleanest = ranked.length ? ranked[0].d : null;
  const stack50 = ranked.length ? ranked[0].h : null;
  const mk = dist?.bodies.find(b => b.body === 'makemake')?.match, er = dist?.bodies.find(b => b.body === 'eris')?.match;
  const cand = cold?.wide?.candidates?.candidates.filter(c => c.grade === 'strong').sort((a, b) => b.snr_J - a.snr_J)[0];
  const ex = how?.stack?.examples.find(e => !e.seen_single) ?? how?.stack?.examples[0];
  const photos = deep.reduce((s, d) => s + (d.n_photos ?? 0), 0);

  return (
    <Page wide>
      <header className="how-hero">
        <p className="how-label">How it works</p>
        <h1 className="how-hero__h">How we find them.</h1>
        <p className="how-hero__p">Planets, dwarfs and asteroids, in eight steps. Real SPHEREx photos, real numbers, nothing hidden.</p>
        <nav className="how-jump" aria-label="Steps">
          {['Look', 'Remove', 'Join', 'Measure', 'Add up', 'Colours', 'Seal', 'Limits'].map((w, i) => <a key={w} href={`#s${i + 1}`}>{String(i + 1).padStart(2, '0')} {w}</a>)}
        </nav>
      </header>

      <ol className="how-steps">
        <Step n={1} id="s1" title="Look again and again." fig={busiest ? <Visits d={busiest} /> : null}>
          <p className="how-p">SPHEREx photographs the whole sky every six months. Each patch gets dozens of photos.</p>
          {busiest && <Fact v={fmt(busiest.n_photos ?? busiest.n_images)} t="photos of one patch on Planet Nine's path" />}
        </Step>

        <Step n={2} id="s2" title="Remove what stays still." fig={how?.still?.example ? <Waffle dots={how.still.example.paired_detections} left={how.still.example.night_detections} /> : null}>
          <p className="how-p">Stars and galaxies do not move. A dot that sits in the same place on another night is thrown away. No star catalogue needed.</p>
          {how?.still && <Fact v={`${fmt(how.still.left)} of ${fmt(how.still.dots)}`} t={`dots left after removing what stayed still, in ${how.still.patches} patches`} />}
        </Step>

        <Step n={3} id="s3" title="Join the dots." fig={how?.track ? <Track t={how.track} /> : null}>
          <p className="how-p">Something real moves in a steady line, look after look. We also shuffle the dots to count how often chance makes a line.</p>
          {how?.track && <Fact v={how.track.name} t={`found blind, then matched to the known asteroid. Chance lines expected: ${how.track.chance_tracks_expected ?? 0}.`} />}
        </Step>

        <Step n={4} id="s4" title="Measure the wobble." fig={<div className="how-card how-card--live"><HowFar /></div>}>
          <p className="how-p">Earth goes around the Sun, so near things seem to wobble. A small wobble means far away.</p>
          {mk && <Fact v={`${mk.r_fit_au.toFixed(1)} AU`} t={`Makemake's distance from the wobble. NASA JPL: ${mk.r_true_au.toFixed(1)} AU.`} />}
          {er && <Fact v={`${er.r_fit_au.toFixed(1)} AU`} t={`Eris. NASA JPL: ${er.r_true_au.toFixed(1)} AU.`} />}
        </Step>

        <Step n={5} id="s5" title="Add photos together." fig={ex ? <StackViewer e={ex} /> : <div className="how-card how-wait">The stacking test is still running.</div>}>
          <p className="how-p">One photo is too noisy for faint things. Shift each photo to follow the path, add them up, and the noise cancels out.</p>
          {how?.stack && <Fact v={`${how.stack.n_seen_single} → ${how.stack.n_seen_stack_snr5}`} t={`known asteroids clearly seen (S/N 5): one photo at a time, then added up. ${fmt(how.stack.n_asteroids)} were in view. Empty sky reached S/N 5 on only ${how.stack.n_control_snr5} of ${fmt(how.stack.n_control_paths)} test paths.`} />}
        </Step>

        <Step n={6} id="s6" title="Read 102 colours." fig={cand ? <Spectrum s={cand.spectrum} name={cand.name} type={cand.pred_type} /> : null}>
          <p className="how-p">SPHEREx splits light into 102 colours. Cold worlds hold methane, which leaves dark dips. Our model learned those dips from known dwarfs.</p>
          {cold && <Fact v={`${cold.cv.held_out.T_found} of ${cold.cv.held_out.T_total}`} t={`known methane dwarfs recognised, with ${cold.cv.held_out.false_T} false alarms in ${fmt(cold.cv.held_out.not_T_total)} warmer ones`} />}
          {cold?.wide?.candidates && <Fact v={String(cold.wide.candidates.n_strong)} t="brown dwarfs seen in methane for the first time" />}
        </Step>

        <Step n={7} id="s7" title="Seal it, then check." fig={how?.ledger ? <Chain l={how.ledger} /> : null}>
          <p className="how-p">Every result gets a fingerprint before we compare it with what astronomers already know. So we cannot quietly change an answer later.</p>
          {how?.ledger && <Fact v={String(how.ledger.n)} t="sealed results so far" />}
        </Step>

        <Step n={8} id="s8" title="Say what we can't see." fig={how?.planet_nine && cleanest ? <Depth single={cleanest.single_5sigma_ujy} stack={stack50} p9={how.planet_nine} /> : null}>
          <p className="how-p">Planet Nine, if it is there, is fainter than our deepest stack. So we show how faint we can see, and never guess.</p>
          {deep.length > 0 && (() => {
            const flagged = deep.reduce((s, d) => s + d.n_candidates, 0);
            const chance = deep.reduce((s, d) => s + (typeof d.chance_expected === 'number' ? d.chance_expected : d.n_visits / 3), 0);
            const checked = deep.every(d => d.n_candidates === 0 || typeof d.n_passed_checks === 'number');
            const passed = deep.reduce((s, d) => s + (d.n_passed_checks ?? 0), 0);
            return checked
              ? passed === 0
                ? <Fact v="0" t={`planets found in ${deep.length} patches on its predicted path (${fmt(photos)} photos).${flagged ? ` The search flagged ${flagged} spots, about what chance alone gives (${Math.round(chance)}), and ${flagged === 2 ? 'both' : `all ${flagged}`} failed the checks.` : ''}`} />
                : <Fact v={`${passed} of ${flagged}`} t={`flagged spots pass our checks so far. Chance alone flags about ${Math.round(chance)}. Not planets: each needs another visit to confirm.`} />
              : <Fact v={`${flagged} flagged`} t={`in ${deep.length} patches (${fmt(photos)} photos), still being checked. Chance alone flags about ${Math.round(chance)}.`} />;
          })()}
        </Step>
      </ol>

      <section className="how-end rv" aria-labelledby="end-h">
        <h2 id="end-h" className="how-end__h">Now you try.</h2>
        <div className="how-end__row">
          <Link className="how-btn how-btn--ink" href="/#try">Spot what moves</Link>
          <Link className="how-btn" href="/check">Check a candidate</Link>
          <Link className="how-btn" href="/proof">See every test</Link>
        </div>
      </section>
    </Page>
  );
}
