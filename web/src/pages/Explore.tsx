import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, cachedFrame, loadFrames, type Field, type Frame, type Investigation, type Target } from '../api.ts';
import { Header } from '../components/Shell.tsx';
import { SkyCanvas, type Colormap, type Overlays, type SkyCanvasHandle } from '../components/SkyCanvas.tsx';
import { Timeline } from '../components/Timeline.tsx';
import { DataStatePill } from '../components/DataState.tsx';
import { InvestigationView, Progress } from '../components/InvestigationView.tsx';
import { ArchiveFlight, ArchiveProgressText } from '../components/ArchiveFlight.tsx';
import { StackStill } from '../components/FieldImage.tsx';
import { resolveQuery } from '../components/SearchBox.tsx';
import { Term } from '../components/Term.tsx';
import { fetchTargets, useField, useInvestigation, usePrefersReducedMotion } from '../hooks.ts';
import { Link, navigate, replaceQuery, useLocation } from '../router.tsx';
import {
  angularSeparationArcsec, formatDec, formatRA, fromTangent, percentile, propagateLinear, wavelengthMatched, type SkyPoint, type StretchKind,
} from '../lib/astro.ts';
import { difference, sharedLimits, stack as stackFrames, subtractBackground } from '../lib/compose.ts';
import { NA, date, dateTime, month, num, um } from '../lib/format.ts';
import '../home.css';
import '../explore.css';

/* The Explore page (v2, 14 Nov 2026). Same look as the home page: a light grey page, data in black rounded cards,
   explanations on a light panel with pill tabs. Black, white and grey only. All viewing logic is unchanged from v1. */

type Mode = 'animate' | 'blink' | 'difference' | 'stack' | 'spectral';
const MODES: { id: Mode; label: string; title: string; say: string }[] = [
  { id: 'animate', label: 'Play', title: 'Watch it like a flip-book.', say: 'Every photo of this spot, in the order SPHEREx took them. Look for a dot that slides.' },
  { id: 'blink', label: 'Blink', title: 'Spot the jump.', say: 'Two dates flip back and forth. Stars stay still. The dot that jumps is moving.' },
  { id: 'difference', label: 'Subtract', title: 'Only changes are left.', say: 'Photo B minus photo A. Stars that stayed still cancel out. A mover leaves a dark spot beside a bright one.' },
  { id: 'stack', label: 'Add', title: 'See fainter things.', say: 'All the photos added together, so faint things show up. Anything that moves smears into a streak.' },
  { id: 'spectral', label: 'Colours', title: 'Short to long infrared.', say: 'The same spot in SPHEREx’s infrared colours, sorted by colour instead of date. Cold things glow at the long end.' },
];

/** NASA's five test targets, in NASA's order, each with one plain sentence and what to look for. */
const TARGET_ORDER = ['barnards-star', 'epsilon-indi-b', 'wise-0855', 'rw-aurigae', 'r-draconis'];
const ABOUT: Record<string, { say: string; look: string }> = {
  'barnards-star': { say: 'The fastest-moving star in our sky.', look: 'Look for motion' },
  'epsilon-indi-b': { say: 'Two cold brown dwarfs next door.', look: 'Look for motion' },
  'wise-0855': { say: 'The coldest brown dwarf known.', look: 'Look for motion' },
  'rw-aurigae': { say: 'A young star that flickers.', look: 'Look for brightness' },
  'r-draconis': { say: 'A giant star that brightens and fades.', look: 'Look for brightness' },
};

/** SPHEREx's six detectors and the infrared range each one covers (pipeline/spherex.py DETECTOR_RANGES). */
const DETECTORS: [number, number][] = [[0.75, 1.09], [1.10, 1.62], [1.63, 2.41], [2.42, 3.82], [3.83, 4.41], [4.42, 5.00]];

const WIDTHS = [6, 10, 20, 30];

const STACK_ORDER = (id: string) => ({ 'stack-short': 0, 'stack-long': 1, 'stack-mid': 2 } as Record<string, number>)[id] ?? 3;
const STACK_LIMIT = 240;

function jyearToMjd(j: number) { return (j - 2000) * 365.25 + 51544.5; }

function targetPosition(t: Target, mjd: number): SkyPoint {
  const a = t.astrometry;
  const epoch = a.epoch_mjd ?? (a.epoch_jyear != null ? jyearToMjd(a.epoch_jyear) : mjd);
  return propagateLinear(a.ra_deg, a.dec_deg, a.pmra_masyr, a.pmdec_masyr, epoch, mjd);
}

function bestDetector(frames: Frame[]): number | null {
  const counts = new Map<number, Set<string>>();
  const n = new Map<number, number>();
  frames.forEach(f => {
    if (!counts.has(f.detector)) counts.set(f.detector, new Set());
    counts.get(f.detector)!.add(f.visit);
    n.set(f.detector, (n.get(f.detector) ?? 0) + 1);
  });
  let best: number | null = null, score = -1;
  for (const [d, visits] of counts) {
    const s = visits.size * 1000 + (n.get(d) ?? 0);
    if (s > score) { score = s; best = d; }
  }
  return best;
}

function parseDets(s: string | null): number[] | null {
  if (!s) return null;
  const v = s.split(',').map(Number).filter(d => d >= 1 && d <= 6);
  return v.length ? v : null;
}

export function Explore() {
  const { search } = useLocation();
  const params = useMemo(() => new URLSearchParams(search), [search]);
  const targetSlug = params.get('target');
  const fieldParam = params.get('field');
  const raParam = params.get('ra');
  const decParam = params.get('dec');
  const fovParam = Number(params.get('fov') ?? '') || null;
  const invParam = params.get('inv');
  const embed = params.get('embed') === '1';

  const [targets, setTargets] = useState<Target[] | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [live, setLive] = useState<{ key: string; field_id?: string; job_id?: string; error?: string } | null>(null);
  const liveKey = !targetSlug && !fieldParam && raParam && decParam ? `${raParam},${decParam},${fovParam},${attempt}` : null;
  const target = targets?.find(t => t.slug === targetSlug) ?? null;

  useEffect(() => { fetchTargets().then(setTargets).catch(() => setTargets([])); }, []);

  // Live query: create (or reuse) a field for the requested coordinates.
  useEffect(() => {
    if (!liveKey || !raParam || !decParam) return;
    let alive = true;
    api.createField({ ra: raParam, dec: decParam, fov_arcmin: fovParam ?? 6 })
      .then(r => { if (alive) setLive({ key: liveKey, ...r }); })
      .catch(err => { if (alive) setLive({ key: liveKey, error: err.message }); });
    return () => { alive = false; };
  }, [liveKey, raParam, decParam, fovParam]);

  const liveResult = live?.key === liveKey ? live : null;
  const fieldId = fieldParam ?? (targetSlug ? (target?.field?.field_id ?? (targets ? targetSlug : null)) : liveResult?.field_id ?? null);
  const { data, error: fieldError } = useField(fieldId, liveResult?.job_id);
  const field = data?.field_id === fieldId ? data : null;

  const idle = !targetSlug && !fieldParam && !raParam;

  return (
    <div className={`e xp${embed ? ' xp--embed' : ''}`}>
      {!embed && <Header />}
      {embed && <a className="embed-link" href={window.location.pathname + window.location.search.replace(/[?&]embed=1/, '')} target="_blank" rel="noreferrer">Open in Aiges ↗</a>}
      {idle ? <ExploreIdle targets={targets} /> : (
        <ExploreWorkspace
          key={liveKey ?? fieldId ?? 'pending'}
          field={field}
          fieldError={(fieldId ? fieldError : null) ?? liveResult?.error ?? null}
          target={target}
          params={params}
          invParam={invParam}
          embed={embed}
          fov={fovParam ?? field?.fov_arcmin ?? 6}
          pendingLabel={raParam && decParam ? `${raParam}, ${decParam}` : targetSlug ?? ''}
          coordinateSearch={!!liveKey}
          onCoordinateSubmit={() => setAttempt(value => value + 1)}
        />
      )}
    </div>
  );
}

/** The search pill and the sky-width chips. With a field open, a width chip reopens the same spot at that width. */
function ExploreSearch({ fov, here, onCoordinateSubmit }: { fov: number; here?: SkyPoint | null; onCoordinateSubmit?: () => void }) {
  const [q, setQ] = useState('');
  const [f, setF] = useState(Math.round(fov));
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => setF(Math.round(fov)), [fov]);
  const widths = WIDTHS.includes(f) ? WIDTHS : [...WIDTHS, f].sort((a, b) => a - b);
  async function go(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true); setErr(null);
    try {
      const r = await resolveQuery(q.trim());
      const fv = Math.min(30, Math.max(2, f || 6));
      if (r.moves) navigate(`/map?q=${encodeURIComponent(q.trim())}`);
      else if (r.target) navigate(`/explore?target=${r.target}`);
      else {
        onCoordinateSubmit?.();
        navigate(`/explore?ra=${r.ra.toFixed(6)}&dec=${r.dec.toFixed(6)}&fov=${fv}`);
      }
      setQ('');
    } catch (ex) { setErr((ex as Error).message); } finally { setBusy(false); }
  }
  function pickWidth(v: number) {
    setF(v);
    if (here && v !== Math.round(fov)) navigate(`/explore?ra=${here.ra.toFixed(6)}&dec=${here.dec.toFixed(6)}&fov=${v}`);
  }
  return (
    <div className="xp-find">
      <form className="e-search xp-search" onSubmit={go} role="search">
        <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="8.5" cy="8.5" r="6" stroke="currentColor" strokeWidth="1.8" /><path d="M13 13l5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
        <label className="visually-hidden" htmlFor="topq">Star name or sky position (right ascension and declination)</label>
        <input id="topq" value={q} onChange={e => setQ(e.target.value)} placeholder="Star name or sky position" autoComplete="off" spellCheck={false} aria-invalid={!!err} aria-describedby="topq-help" />
        <button className="e-btn e-btn--ink" disabled={busy}>{busy ? 'Finding…' : 'Go'}</button>
      </form>
      {err ? <p id="topq-help" className="xp-err" role="alert">{err}</p>
        : <p id="topq-help" className="xp-help">For example <em>Barnard's Star</em>, or <em>08h55m10.8s -07d14m42s</em>, or <em>133.795 -7.245</em></p>}
      <div className="xp-width" role="group" aria-label="Sky width (field of view, in arcminutes)">
        <span className="xp-width__k">Sky width</span>
        {widths.map(v => (
          <button key={v} type="button" aria-pressed={f === v} onClick={() => pickWidth(v)} title={`${v} arcminutes across`}>{v}′</button>
        ))}
        <span className="xp-width__note">Wider shows more sky but loads slower.</span>
      </div>
    </div>
  );
}

function ExploreIdle({ targets }: { targets: Target[] | null }) {
  const rank = (s: string) => { const i = TARGET_ORDER.indexOf(s); return i < 0 ? 99 : i; };
  const sorted = targets ? [...targets].sort((a, b) => rank(a.slug) - rank(b.slug)) : null;
  return (
    <main id="main" className="xp-idle">
      <section className="xp-idle__top">
        <div className="xp-idle__text">
          <p className="e-label e-label--dot">Explore</p>
          <h1 className="xp-idle__h">Pick a patch of sky.</h1>
          <p className="xp-idle__p">Type a star's name or a sky position. You'll see every SPHEREx photo of that spot, played in order like a flip-book.</p>
          <ExploreSearch fov={6} />
          <div className="xp-try">
            <span>Or try</span>
            <Link className="xp-chiplink" href="/explore?ra=266.4168&dec=-29.0078&fov=6">The centre of the Milky Way</Link>
            <Link className="xp-chiplink" href="/explore?ra=10.6847&dec=41.269&fov=8">The Andromeda galaxy</Link>
          </div>
        </div>
        <figure className="xp-idle__pic">
          <img src="/img/spherex-dust.webp" alt="A cloud of glowing dust among thousands of stars, imaged in infrared by SPHEREx" decoding="async" />
          <figcaption>Dust in the Large Magellanic Cloud, seen by SPHEREx at 3.29 microns.</figcaption>
        </figure>
      </section>

      <section className="xp-idle__targets" aria-labelledby="xp-targets-h">
        <div className="xp-idle__head">
          <h2 id="xp-targets-h" className="e-label">NASA's five test targets</h2>
          <p className="xp-idle__note">Start with one. Each opens with its real SPHEREx photos.</p>
        </div>
        <div className="xp-cards">
          {sorted ? sorted.map(t => (
            <Link key={t.slug} href={`/explore?target=${t.slug}`} className="e-card xp-card">
              <span className="e-card__n">{ABOUT[t.slug]?.look ?? 'Look closely'}</span>
              <span className="e-card__k">{t.title}</span>
              <span className="e-card__t">{ABOUT[t.slug]?.say ?? t.kind}</span>
              <span className="xp-card__go" aria-hidden="true">Open <span>→</span></span>
            </Link>
          )) : TARGET_ORDER.map(s => <div key={s} className="e-card xp-card xp-card--wait" aria-hidden="true" />)}
        </div>
      </section>
    </main>
  );
}

interface WorkspaceProps {
  field: Field | null;
  fieldError: string | null;
  target: Target | null;
  params: URLSearchParams;
  invParam: string | null;
  pendingLabel: string;
  embed: boolean;
  fov: number;
  coordinateSearch: boolean;
  onCoordinateSubmit: () => void;
}

function ExploreWorkspace({ field, fieldError, target, params, invParam, pendingLabel, embed, fov, coordinateSearch, onCoordinateSubmit }: WorkspaceProps) {
  const reduced = usePrefersReducedMotion();
  const state = field?.data_state ?? (fieldError ? 'failed' : 'processing');
  const canvasRef = useRef<SkyCanvasHandle>(null);
  const grid = field?.grid ?? null;
  const allFrames = useMemo(() => (field?.frames ?? []).filter(f => f && f.data_url && f.stats).slice().sort((a, b) => a.mjd - b.mjd), [field]);

  // ---------- view state (initialised from the URL) ----------
  const [mode, setMode] = useState<Mode>((params.get('mode') as Mode) || 'animate');
  const [dets, setDets] = useState<number[] | null>(parseDets(params.get('det')));
  const [wmin, setWmin] = useState<number | null>(params.get('wmin') ? Number(params.get('wmin')) : null);
  const [wmax, setWmax] = useState<number | null>(params.get('wmax') ? Number(params.get('wmax')) : null);
  const [stretch, setStretch] = useState<StretchKind>((params.get('stretch') as StretchKind) || 'asinh');
  const [cmap, setCmap] = useState<Colormap>((params.get('cmap') as Colormap) === 'ember' ? 'ember' : 'gray');
  const [black, setBlack] = useState(1.5);
  const [contrast, setContrast] = useState(1);
  const [independent, setIndependent] = useState(false);
  const [smooth, setSmooth] = useState(params.get('smooth') !== '0');
  const [fade, setFade] = useState(params.get('fade') !== '0');
  const [showGrid, setShowGrid] = useState(params.get('grid') === '1');
  const [showCatalog, setShowCatalog] = useState(params.get('gaia') === '1');
  const [showWise, setShowWise] = useState(false);
  const [wise, setWise] = useState<{ ra: number; dec: number; mover: boolean; pm_arcsec_yr: number }[] | null>(null);
  const [wiseError, setWiseError] = useState<string | null>(null);
  useEffect(() => {
    if (!showWise || wise || !field?.field_id) return;
    let alive = true;
    setWiseError(null);
    api.fieldWise(field.field_id).then(d => { if (alive) setWise(d.sources); }).catch(e => { if (alive) { setWiseError((e as Error).message); setShowWise(false); } });
    return () => { alive = false; };
  }, [showWise, wise, field?.field_id]);
  const [fps, setFps] = useState(4);
  const [playing, setPlaying] = useState(false);
  const [activeFrameId, setActiveFrameId] = useState<string | null>(params.get('frame'));
  const [aId, setAId] = useState<string | null>(params.get('a'));
  const [bId, setBId] = useState<string | null>(params.get('b'));
  const [blinkPhase, setBlinkPhase] = useState(0);
  const [loadedTick, setLoadedTick] = useState(0);
  const [selected, setSelected] = useState<SkyPoint | null>(params.get('src_ra') && params.get('src_dec') ? { ra: Number(params.get('src_ra')), dec: Number(params.get('src_dec')) } : null);
  const [invId, setInvId] = useState<string | null>(invParam);
  const [invError, setInvError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const initialFrameId = useRef(params.get('frame'));
  const urlHasView = useRef(['mode', 'det', 'wmin', 'wmax', 'frame', 'a', 'b'].some(k => params.has(k)));
  const defaultsDone = useRef(false);
  const [pendingPair, setPendingPair] = useState(false);
  const [showTrack, setShowTrack] = useState(params.get('track') !== '0');

  // Default detector for curated fields: the detector covering most visits.
  useEffect(() => {
    if (!urlHasView.current && dets === null && wmin === null && wmax === null && allFrames.length > 40) {
      const d = bestDetector(allFrames);
      if (d) setDets([d]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allFrames.length]);

  const frames = useMemo(() => {
    let f = allFrames;
    if (dets?.length) f = f.filter(x => dets.includes(x.detector));
    if (wmin != null) f = f.filter(x => x.wavelength_um == null || x.wavelength_um >= wmin);
    if (wmax != null) f = f.filter(x => x.wavelength_um == null || x.wavelength_um <= wmax);
    if (mode === 'spectral') f = f.slice().sort((a, b) => (a.wavelength_um ?? 0) - (b.wavelength_um ?? 0));
    return f;
  }, [allFrames, dets, wmin, wmax, mode]);

  // Keep the active photo selected as earlier exposures arrive.
  useEffect(() => {
    if (!frames.length) return;
    if (initialFrameId.current && frames.some(f => f.id === initialFrameId.current)) {
      setActiveFrameId(initialFrameId.current);
      initialFrameId.current = null;
    } else {
      if (state !== 'processing') initialFrameId.current = null;
      if (!frames.some(f => f.id === activeFrameId)) setActiveFrameId(frames[0].id);
    }
  }, [frames, state, activeFrameId]);

  const safeIndex = Math.max(0, frames.findIndex(f => f.id === activeFrameId));
  const current = frames[safeIndex] ?? null;
  const step = useCallback((offset: number) => {
    if (!frames.length) return;
    initialFrameId.current = null;
    setActiveFrameId(id => {
      const index = Math.max(0, frames.findIndex(f => f.id === id));
      return frames[(index + offset + frames.length) % frames.length].id;
    });
  }, [frames]);
  const aIdx = aId ? frames.findIndex(f => f.id === aId) : -1;
  const bIdx = bId ? frames.findIndex(f => f.id === bId) : -1;
  const frameA = aIdx >= 0 ? frames[aIdx] : frames[0] ?? null;
  const frameB = bIdx >= 0 ? frames[bIdx] : frames[frames.length - 1] ?? null;
  const canPlay = frames.length > 1 && mode !== 'stack' && mode !== 'difference';

  // ---------- load frames for the current filter (current first) ----------
  useEffect(() => {
    if (!grid || !frames.length) return;
    const ctl = new AbortController();
    const order = [...frames.slice(safeIndex), ...frames.slice(0, safeIndex)];
    const urls = (mode === 'stack' ? frames.slice(0, STACK_LIMIT) : order).map(f => f.data_url);
    let n = 0;
    loadFrames(urls, grid.dtype, () => {
      n++;
      if (n <= 3 || n % 12 === 0) setLoadedTick(t => t + 1);
    }, 6, ctl.signal).then(() => setLoadedTick(t => t + 1));
    return () => ctl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frames, grid?.dtype, mode]);

  // ---------- playback ----------
  useEffect(() => {
    if (!playing || !canPlay) return;
    if (mode === 'blink') {
      const id = window.setInterval(() => setBlinkPhase(p => 1 - p), 700);
      return () => window.clearInterval(id);
    }
    const id = window.setInterval(() => step(1), 1000 / fps);
    return () => window.clearInterval(id);
  }, [playing, fps, step, mode, canPlay]);

  useEffect(() => { if (reduced) setPlaying(false); }, [reduced]);

  // ---------- keep the share URL current ----------
  useEffect(() => {
    replaceQuery({
      mode: mode === 'animate' ? null : mode,
      det: dets?.length ? dets.join(',') : 'all',
      wmin: wmin != null ? wmin.toFixed(3) : null,
      wmax: wmax != null ? wmax.toFixed(3) : null,
      frame: initialFrameId.current ?? current?.id ?? null,
      stretch: stretch === 'asinh' ? null : stretch,
      cmap: cmap === 'gray' ? null : cmap,
      a: mode === 'blink' || mode === 'difference' ? frameA?.id ?? null : null,
      b: mode === 'blink' || mode === 'difference' ? frameB?.id ?? null : null,
      inv: invId,
      src_ra: selected ? selected.ra.toFixed(6) : null,
      src_dec: selected ? selected.dec.toFixed(6) : null,
      track: showTrack ? null : '0',
      grid: showGrid ? '1' : null,
      gaia: showCatalog ? '1' : null,
      smooth: smooth ? null : '0',
      fade: fade ? null : '0',
    });
  }, [mode, dets, wmin, wmax, current?.id, state, stretch, cmap, frameA?.id, frameB?.id, invId, selected, showTrack, showGrid, showCatalog, smooth, fade]);

  // ---------- compose pixels ----------
  const composed = useMemo(() => {
    if (!grid || !frames.length) return null;
    if (mode === 'stack') {
      const loaded = frames.slice(0, STACK_LIMIT).map(f => ({ f, d: cachedFrame(f.data_url) })).filter(x => x.d);
      if (!loaded.length) return null;
      const s = stackFrames(loaded.map(x => ({ data: x.d!, median: x.f.stats.median })));
      return { data: s.data, kind: 'stack' as const, n: loaded.length,
        firstDate: loaded[0].f.time_utc, lastDate: loaded[loaded.length - 1].f.time_utc };
    }
    if (mode === 'difference') {
      if (!frameA || !frameB) return null;
      const a = cachedFrame(frameA.data_url), b = cachedFrame(frameB.data_url);
      if (!a || !b) return null;
      return { data: difference(b, frameB.stats.median, a, frameA.stats.median), kind: 'difference' as const, n: 2 };
    }
    const f = mode === 'blink' ? (blinkPhase ? frameB : frameA) : current;
    if (!f) return null;
    const d = cachedFrame(f.data_url);
    if (!d) return null;
    return { data: subtractBackground(d, f.stats.median), kind: 'single' as const, n: 1, frame: f };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [grid, frames, mode, current, frameA, frameB, blinkPhase, mode === 'stack' ? loadedTick : 0, cachedFrame(current?.data_url ?? ''), cachedFrame(frameA?.data_url ?? ''), cachedFrame(frameB?.data_url ?? '')]);

  // Keep the last good image on screen while the next frame loads.
  const lastPixels = useRef<Float32Array | null>(null);
  if (composed?.data) lastPixels.current = composed.data;
  const pixels = composed?.data ?? lastPixels.current;

  const display = useMemo(() => {
    const cm: Colormap = mode === 'difference' ? 'diverging' : cmap;
    if (!frames.length) return { lo: -1, hi: 1, kind: stretch, colormap: cm };
    if (mode === 'difference' && composed?.data) {
      const absP = percentile(Array.from(composed.data, v => Math.abs(v)), 99.7);
      return { lo: -absP / contrast, hi: absP / contrast, kind: stretch, colormap: cm };
    }
    if (mode === 'stack' && composed?.data) {
      const med = percentile(composed.data, 50);
      const sig = Math.max(med - percentile(composed.data, 16), 1e-6);
      return { lo: -black * sig, hi: Math.max((percentile(composed.data, 99.7) - med) / contrast, sig), kind: stretch, colormap: cm };
    }
    const base = independent && composed?.kind === 'single' && composed.frame ? [composed.frame.stats] : frames.map(f => f.stats);
    const lim = sharedLimits(base, black, contrast);
    return { ...lim, kind: stretch, colormap: cm };
  }, [frames, mode, composed, stretch, cmap, black, contrast, independent]);

  // ---------- investigation ----------
  const inv = useInvestigation(invId);
  const investigation: Investigation | null = inv.data;

  const curatedInvId = field?.investigation_id ?? target?.investigation_id ?? null;
  // The curated investigation also drives the default view and the fitted-track overlay.
  const trackInv = useInvestigation(field?.kind === 'curated' ? curatedInvId : null);
  const trackSource: Investigation | null = investigation?.status === 'ready' && investigation.motion ? investigation : trackInv.data?.status === 'ready' ? trackInv.data : null;

  useEffect(() => {
    if (defaultsDone.current || urlHasView.current || field?.kind !== 'curated' || !allFrames.length) return;
    const ti = trackInv.data;
    if (!ti || ti.status !== 'ready') return;
    defaultsDone.current = true;
    if (ti.cold_search) {
      // A cold object is only visible at the longest wavelengths.
      setDets([6]);
      return;
    }
    const m = ti.motion;
    if (m && m.status === 'significant' && m.points.length >= 50) {
      const d = bestDetector(allFrames);
      if (d) setDets([d]);
      setMode('blink');
      setPendingPair(true);
      if (!reduced) setPlaying(true);
    }
  }, [field?.kind, allFrames, trackInv.data, reduced]);

  useEffect(() => {
    if (!pendingPair || !frames.length) return;
    autoMatchedPair();
    setPendingPair(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingPair, frames]);
  const epochForHint = current?.mjd ?? allFrames[0]?.mjd ?? null;
  const targetHere = target && epochForHint != null ? targetPosition(target, epochForHint) : null;

  const pick = useCallback(async (p: SkyPoint) => {
    if (!field || !grid || state === 'processing' || state === 'failed') return;
    setSelected(p);
    setInvError(null);
    // Near the curated target? open its precomputed investigation.
    if (targetHere && curatedInvId && angularSeparationArcsec(p, targetHere) < 2.5 * grid.pixel_arcsec) {
      setSelected(targetHere);
      setInvId(curatedInvId);
      return;
    }
    try {
      const r = await api.createInvestigation({ field_id: field.field_id, ra: p.ra, dec: p.dec });
      setInvId(r.investigation_id);
    } catch (err) {
      setInvError((err as Error).message);
      setInvId(null);
    }
  }, [field, grid, state, targetHere, curatedInvId]);

  // ---------- keyboard ----------
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'SELECT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;                       // leave browser shortcuts alone
      const onControl = !!t && (t.tagName === 'BUTTON' || t.tagName === 'A' || t.tagName === 'SUMMARY');
      if (onControl && (e.key === ' ' || e.key === 'Enter')) return;      // Space and Enter press the focused control
      if (e.key === ' ') { if (canPlay) { e.preventDefault(); setPlaying(p => !p); } }
      else if (e.key === 'ArrowRight') { e.preventDefault(); setPlaying(false); step(1); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); setPlaying(false); step(-1); }
      else if (e.key.toLowerCase() === 'b') setMode(m => (m === 'blink' ? 'animate' : 'blink'));
      else if (e.key.toLowerCase() === 'd') { setPlaying(false); setMode(m => (m === 'difference' ? 'animate' : 'difference')); }
      else if (e.key === '+' || e.key === '=') canvasRef.current?.zoom(1.25);
      else if (e.key === '-') canvasRef.current?.zoom(0.8);
      else if (e.key === '0') canvasRef.current?.resetView();
      else if (e.key === 'Escape') setInvId(null);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [step, canPlay]);

  // ---------- overlays ----------
  const overlays = useMemo<Overlays>(() => {
    const o: Overlays = { markers: [] };
    const epoch = composed?.kind === 'single' && composed.frame ? composed.frame.mjd : current?.mjd;
    if (field?.catalog && epoch != null) {
      o.catalog = field.catalog.map(s => ({ ...propagateLinear(s.ra, s.dec, s.pmra, s.pmdec, field.catalog_epoch_mjd, epoch), g: s.g }));
    }
    const m = showTrack && trackSource ? trackSource.motion : null;
    if (m && m.track.length > 1) {
      const modelId = m.reported_model ?? m.preferred_model;
      const ref = modelId ? m.models[modelId]?.reference : undefined;
      if (ref) {
        o.track = { points: m.track.map(p => fromTangent(p.xi, p.eta, ref.ra_deg, ref.dec_deg)), label: '', color: 'rgba(245,245,247,0.9)' };
        o.measured = { points: m.points.map(p => fromTangent(p.xi, p.eta, ref.ra_deg, ref.dec_deg)), color: 'rgba(245,245,247,0.45)' };
        if (epoch != null && m.track.length) {
          // model position at this frame's epoch (nearest track sample)
          let best = m.track[0];
          for (const p of m.track) if (Math.abs(p.mjd - epoch) < Math.abs(best.mjd - epoch)) best = p;
          const sp = fromTangent(best.xi, best.eta, ref.ra_deg, ref.dec_deg);
          o.markers!.push({ ...sp, color: '#f5f5f7', shape: 'cross', size: 12 });
        }
      }
    }
    if (selected && !(m && m.track.length > 1 && invId === curatedInvId)) o.markers!.push({ ...selected, color: '#f5f5f7', shape: 'ring', size: 11, label: invId ? 'selected' : undefined });
    if (showWise && wise) {
      for (const w of wise) {
        o.markers!.push(w.mover
          ? { ra: w.ra, dec: w.dec, color: '#f5f5f7', shape: 'diamond', size: 9, label: `WISE saw a mover here in 2015 (${w.pm_arcsec_yr.toFixed(1)}″/yr)` }
          : { ra: w.ra, dec: w.dec, color: 'rgba(245,245,247,0.55)', shape: 'circle', size: 5 });
      }
    }
    return o;
  }, [field, trackSource, showTrack, current?.mjd, composed, selected, invId, curatedInvId, showWise, wise]);

  const hint = targetHere && !invId && field?.kind === 'curated' ? { ...targetHere, text: `${target?.title} · tap to measure` } : null;

  async function share() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch { setCopied(false); }
  }

  function autoMatchedPair() {
    // Earliest and latest exposures whose wavelengths agree within a bandwidth.
    const sorted = frames.slice().sort((a, b) => a.mjd - b.mjd);
    let best: [Frame, Frame] | null = null, span = -1;
    for (let i = sorted.length - 1; i >= 0 && i > sorted.length - 60; i--) {
      for (let j = 0; j < Math.min(sorted.length, 60); j++) {
        const a = sorted[j], b = sorted[i];
        if (b.mjd - a.mjd <= span) continue;
        if (wavelengthMatched(a, b) && a.detector === b.detector) { span = b.mjd - a.mjd; best = [a, b]; }
      }
    }
    if (best) { setAId(best[0].id); setBId(best[1].id); }
    return !!best;
  }

  const matched = frameA && frameB ? wavelengthMatched(frameA, frameB) : null;
  const detCounts = useMemo(() => {
    const c = new Map<number, number>();
    allFrames.forEach(f => c.set(f.detector, (c.get(f.detector) ?? 0) + 1));
    return c;
  }, [allFrames]);
  const loadedNow = composed !== null;

  let emptyMessage: { title: string; detail?: string; loading?: boolean } | null = null;
  if (fieldError) emptyMessage = { title: 'Could not open this patch of sky', detail: fieldError };
  else if (!field) emptyMessage = { title: "Asking NASA's archive…", detail: pendingLabel ? `Position: ${pendingLabel}` : undefined, loading: true };
  else if (state === 'processing' && !allFrames.length) emptyMessage = { title: 'Getting SPHEREx photos from NASA', loading: true };
  else if (state === 'no_coverage') emptyMessage = { title: 'SPHEREx has no photos of this spot yet', detail: field.message ?? "NASA's archive (DR1 and QR3) has no SPHEREx images covering this position yet." };
  else if (state === 'archive_unavailable') emptyMessage = { title: "NASA's archive is not answering", detail: field.message ?? 'Try one of the five test targets (they are saved here), or try again in a minute.' };
  else if (state === 'failed') emptyMessage = { title: 'Something went wrong', detail: field.message ?? undefined };
  else if (state === 'insufficient' && !allFrames.length) emptyMessage = { title: 'No usable exposures', detail: field.message ?? undefined };
  else if (!frames.length && allFrames.length) emptyMessage = { title: 'No photos in these colours', detail: 'Choose more detectors or a wider colour range under More tools.' };
  else if (!pixels && frames.length) emptyMessage = { title: 'Loading photos…', loading: true };

  const progress = field?.progress ?? null;
  const archiveFlight = !pixels && (coordinateSearch || field?.kind === 'live')
    && (state === 'processing' || (emptyMessage?.loading && frames.length > 0));
  const canMeasure = !!pixels && state !== 'processing' && state !== 'failed';
  const shownFrame = composed?.kind === 'single' ? composed.frame : mode === 'difference' ? null : current;
  const modeInfo = MODES.find(m => m.id === mode) ?? MODES[0];
  const here: SkyPoint | null = field && Number.isFinite(field.ra) && Number.isFinite(field.dec) ? { ra: field.ra, dec: field.dec } : null;
  const title = field?.title ?? target?.title ?? (here ? `${formatRA(here.ra, 1)} ${formatDec(here.dec, 0)}` : 'Opening this patch of sky');
  const firstF = allFrames[0] ?? null, lastF = allFrames[allFrames.length - 1] ?? null;
  const blurb = target ? ABOUT[target.slug]?.say : null;
  const lede = [
    blurb,
    firstF && lastF ? `${allFrames.length} SPHEREx photos, ${month(firstF.time_utc)} to ${month(lastF.time_utc)}.` : emptyMessage?.loading ? "Getting the photos from NASA's archive…" : null,
    field?.kind === 'live' ? 'Photos of this exact sky position. Each one shows the date it was taken.' : null,
  ].filter(Boolean).join(' ');
  const showPill = state !== 'cached' && state !== 'live' && state !== 'ready' && state !== 'processing';   // loading shows its own progress on the image
  const pairMode = mode === 'blink' || mode === 'difference';
  const tapLine = target && field?.kind === 'curated' ? `Tap the ring to measure ${target.title}.` : 'Tap any dot to measure it.';
  const closeMeasure = () => { setInvId(null); setInvError(null); };

  return (
    <main id="main" className={`xp-ws${invId || invError ? ' xp-ws--inv' : ''}`}>
      {!embed && (
        <section className="xp-head">
          <div className="xp-head__text">
            <p className="e-label e-label--dot">Explore · NASA SPHEREx photos</p>
            <h1 className="xp-h1">{title}</h1>
            {lede && <p className="xp-lede">{lede}</p>}
            <div className="xp-meta">
              {here && <p className="xp-where"><span>RA {formatRA(here.ra, 1)}</span><span>Dec {formatDec(here.dec, 0)}</span>{field?.fov_arcmin ? <span>{num(field.fov_arcmin, 0)}′ wide</span> : null}</p>}
              {showPill && <DataStatePill state={state} progress={field?.progress} />}
              <button className="xp-share" type="button" onClick={share}>{copied ? 'Link copied' : 'Share this view'}</button>
            </div>
          </div>
          <ExploreSearch fov={fov} here={here} onCoordinateSubmit={onCoordinateSubmit} />
        </section>
      )}

      {field?.message && state !== 'processing' && allFrames.length > 0 && <p className="xp-note" role="status">{field.message}</p>}

      <div className="xp-body">
        <section className="xp-split">
          <div className="xp-stage xp-dark" role="region" aria-label="Sky viewer">
            <div className="xp-stage__top" aria-live="polite">
              {mode === 'difference' && frameA && frameB ? (
                <>
                  <span className="xp-chip">{date(frameB.time_utc)} minus {date(frameA.time_utc)}</span>
                  {matched === false && <span className="xp-chip xp-chip--warn"><Term t="wavelength-matched">Different colours: brightness can't be compared</Term></span>}
                </>
              ) : mode === 'stack' ? (
                <span className="xp-chip">{composed?.n ?? 0} photos added{composed?.kind === 'stack' ? ` · ${month(composed.firstDate)} to ${month(composed.lastDate)}` : ''}{frames.length > STACK_LIMIT ? ` · first ${STACK_LIMIT} of ${frames.length}` : ''}</span>
              ) : shownFrame ? (
                <>
                  <span className="xp-chip">{dateTime(shownFrame.time_utc)}</span>
                  <span className="xp-chip">{um(shownFrame.wavelength_um, 2)} infrared</span>
                  {mode === 'blink' && <span className="xp-chip xp-chip--on">{blinkPhase ? 'Later photo · B' : 'Earlier photo · A'}</span>}
                  {mode === 'blink' && matched === false && <span className="xp-chip xp-chip--warn"><Term t="wavelength-matched">A and B are different colours</Term></span>}
                  {independent && <span className="xp-chip xp-chip--warn">Each photo scaled on its own</span>}
                  {!loadedNow && <span className="xp-chip xp-chip--dim">loading…</span>}
                </>
              ) : null}
            </div>

            {archiveFlight ? (
              <ArchiveFlight reducedMotion={reduced} progress={progress} coordinates={pendingLabel || null} />
            ) : grid ? (
              <SkyCanvas
                ref={canvasRef}
                grid={grid}
                pixels={pixels}
                display={display}
                overlays={overlays}
                showGrid={showGrid}
                showCatalog={showCatalog}
                smoothing={smooth}
                fadeMs={fade && mode !== 'difference' && mode !== 'stack' ? Math.min(900 / fps, mode === 'blink' ? 350 : 600) : 0}
                hint={hint}
                wheelZoom={false}
                onPick={canMeasure ? pick : undefined}
                emptyMessage={emptyMessage}
                caption={overlays.track ? 'Dashed line: the fitted path (a model, not a photo)' : undefined}
                ariaLabel={`SPHEREx image of ${field?.title ?? 'the selected field'}.${canMeasure ? ' Click a source to measure it.' : ''}`}
              />
            ) : (
              <div className="sky"><div className="sky__message" data-loading={emptyMessage?.loading ? 'true' : 'false'}>
                <p className="sky__message-title">{emptyMessage?.title ?? 'Opening this patch of sky'}</p>
                {emptyMessage?.detail && <p className="sky__message-detail">{emptyMessage.detail}</p>}
                {field?.progress && <Progress {...field.progress} />}
              </div></div>
            )}
            {!archiveFlight && progress && state === 'processing' && <div className="xp-progress"><ArchiveProgressText progress={progress} /></div>}

            <div className="xp-transport">
              <div className="xp-transport__btns" role="group" aria-label="Playback">
                <button className="xp-round" onClick={() => { setPlaying(false); step(-1); }} disabled={frames.length < 2} aria-label="Previous photo (←)">‹</button>
                <button className="e-btn e-btn--white xp-play" onClick={() => setPlaying(p => !p)} disabled={!canPlay} aria-label={playing ? 'Pause (space)' : 'Play (space)'}>{playing ? 'Pause' : 'Play'}</button>
                <button className="xp-round" onClick={() => { setPlaying(false); step(1); }} disabled={frames.length < 2} aria-label="Next photo (→)">›</button>
                <label className="xp-speed"><span className="visually-hidden">Speed</span>
                  <select value={fps} onChange={e => setFps(Number(e.target.value))} aria-label="Playback speed, photos per second">
                    {[1, 2, 4, 8, 12, 20, 30].map(v => <option key={v} value={v}>{v} per sec</option>)}
                  </select>
                </label>
              </div>
              <Timeline frames={frames} index={safeIndex} onSelect={i => { initialFrameId.current = null; setPlaying(false); setActiveFrameId(frames[i].id); }} axis={mode === 'spectral' ? 'wavelength' : 'time'}
                markA={pairMode ? (aIdx >= 0 ? aIdx : 0) : null}
                markB={pairMode ? (bIdx >= 0 ? bIdx : frames.length - 1) : null} />
              <span className="xp-count">{frames.length ? `${safeIndex + 1} of ${frames.length}` : '0 of 0'}</span>
            </div>
          </div>

          {invId || invError ? (
            <aside className="xp-meas xp-dark" aria-label="Measurement">
              <div className="xp-meas__bar">
                <p className="e-label">Measurement</p>
                <div className="xp-meas__acts">
                  {invId && investigation?.status === 'ready' && <Link className="xp-ghost" href={`/investigation/${encodeURIComponent(invId)}`}>Full page</Link>}
                  <button className="e-btn e-btn--white xp-close" type="button" onClick={closeMeasure} aria-label="Close the measurement (Esc)">Close</button>
                </div>
              </div>
              <div className="xp-meas__body">
                {invError && <p className="notice notice--bad">{invError}</p>}
                {inv.error && <p className="notice notice--bad">{inv.error}</p>}
                {!investigation && inv.loading && <div className="inv inv--processing"><p className="eyebrow">Measuring</p><Progress stage="loading" done={0} total={0} /></div>}
                {investigation && <InvestigationView inv={investigation} compact />}
              </div>
            </aside>
          ) : (
            <aside className="xp-panel" aria-label="How to look">
              <div className="e-tabs xp-tabs" role="radiogroup" aria-label="How to look at the photos">
                {MODES.map(m => (
                  <button key={m.id} type="button" role="radio" aria-checked={mode === m.id} title={m.say}
                    onClick={() => { setMode(m.id); if (m.id === 'stack' || m.id === 'difference') setPlaying(false); }}>{m.label}</button>
                ))}
              </div>
              <h2 className="xp-panel__h">{modeInfo.title}</h2>
              <p className="xp-panel__p">{modeInfo.say}</p>

              {pairMode && (
                <div className="xp-ab">
                  <div className="xp-ab__row">
                    <span className="xp-ab__tag">A</span>
                    <span className="xp-ab__d"><strong>{frameA ? date(frameA.time_utc) : NA}</strong><span>Earlier · {frameA ? um(frameA.wavelength_um, 2) : NA}</span></span>
                    <button className="xp-mini" type="button" onClick={() => current && setAId(current.id)} title="Use the photo picked on the timeline">Use timeline photo</button>
                  </div>
                  <div className="xp-ab__row">
                    <span className="xp-ab__tag">B</span>
                    <span className="xp-ab__d"><strong>{frameB ? date(frameB.time_utc) : NA}</strong><span>Later · {frameB ? um(frameB.wavelength_um, 2) : NA}</span></span>
                    <button className="xp-mini" type="button" onClick={() => current && setBId(current.id)} title="Use the photo picked on the timeline">Use timeline photo</button>
                  </div>
                  <button className="xp-link" type="button" onClick={() => { if (!autoMatchedPair()) alert('No two photos in the same colour were found.'); }}>Use the first and last dates</button>
                </div>
              )}

              <div className="xp-tap">
                <span className="xp-tap__ring" aria-hidden="true" />
                <div>
                  <p className="xp-tap__h">{tapLine}</p>
                  <p className="xp-tap__p">See how far it moved and how its brightness changed.</p>
                </div>
              </div>
              {!embed && (
                <button className="xp-more" type="button" onClick={() => document.getElementById('tools')?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })}>
                  More tools <span aria-hidden="true">↓</span>
                </button>
              )}
            </aside>
          )}
        </section>
      </div>

      {!embed && (
        <section className="xp-tools" id="tools" aria-labelledby="xp-tools-h">
          <div className="xp-tools__head">
            <p className="e-label">More tools</p>
            <h2 id="xp-tools-h" className="xp-tools__h">For a closer look.</h2>
            <p className="xp-tools__p">All optional. Choose colours, change the brightness, add other telescopes, and see where every photo comes from.</p>
          </div>
          <div className="xp-tools__grid">
            <details className="xp-tool">
              <summary><span className="xp-tool__k">Infrared colours</span><span className="xp-tool__t">SPHEREx sees 102 infrared colours with 6 detectors. Pick which ones to show.</span></summary>
              <div className="xp-tool__body">
                <div className="xp-dets">
                  {DETECTORS.map(([lo, hi], k) => {
                    const d = k + 1;
                    const on = !dets || dets.includes(d);
                    const n = detCounts.get(d) ?? 0;
                    return (
                      <button key={d} type="button" className="xp-det" disabled={!n} aria-pressed={on}
                        onClick={() => setDets(prev => {
                          const cur = prev ?? [1, 2, 3, 4, 5, 6];
                          const next = cur.includes(d) ? cur.filter(x => x !== d) : [...cur, d].sort();
                          return next.length === 6 ? null : next.length ? next : [d];
                        })}
                        title={`Detector ${d}: ${n} photos`}>
                        <strong>Detector {d}</strong><span>{lo.toFixed(2)}–{hi.toFixed(2)} µm</span><span>{n} photos</span>
                      </button>
                    );
                  })}
                </div>
                <div className="xp-grid2">
                  <label>From (µm)<input type="number" step={0.01} min={0.7} max={5.1} value={wmin ?? ''} placeholder="0.75" onChange={e => setWmin(e.target.value ? Number(e.target.value) : null)} /></label>
                  <label>To (µm)<input type="number" step={0.01} min={0.7} max={5.1} value={wmax ?? ''} placeholder="5.00" onChange={e => setWmax(e.target.value ? Number(e.target.value) : null)} /></label>
                </div>
                <div className="xp-row">
                  <button className="xp-pill" type="button" disabled={!current?.wavelength_um} onClick={() => {
                    if (!current?.wavelength_um) return;
                    const hw = Math.max(current.bandwidth_um ?? 0.02, 0.01);
                    setDets(null); setWmin(+(current.wavelength_um - hw).toFixed(3)); setWmax(+(current.wavelength_um + hw).toFixed(3));
                  }}>Only this photo's colour</button>
                  <button className="xp-pill" type="button" onClick={() => { setDets(null); setWmin(null); setWmax(null); }}>All colours</button>
                </div>
                <p className="xp-small">{frames.length} of {allFrames.length} photos shown. <Term t="wavelength-matched">Why the colour matters</Term></p>
              </div>
            </details>

            <details className="xp-tool">
              <summary><span className="xp-tool__k">Brightness</span><span className="xp-tool__t">Make faint things easier to see.</span></summary>
              <div className="xp-tool__body">
                <div className="xp-grid2">
                  <label>Stretch
                    <select value={stretch} onChange={e => setStretch(e.target.value as StretchKind)}>
                      <option value="asinh">asinh (default)</option><option value="linear">linear</option><option value="log">log</option>
                    </select>
                  </label>
                  <label>Tint
                    <select value={cmap} onChange={e => setCmap(e.target.value as Colormap)} disabled={mode === 'difference'}>
                      <option value="gray">grey</option><option value="ember">ember</option>
                    </select>
                  </label>
                  <label>Black point <span className="xp-val">−{black.toFixed(1)}σ</span>
                    <input type="range" min={0} max={5} step={0.1} value={black} onChange={e => setBlack(Number(e.target.value))} />
                  </label>
                  <label>Contrast <span className="xp-val">{contrast.toFixed(2)}×</span>
                    <input type="range" min={0.2} max={8} step={0.05} value={contrast} onChange={e => setContrast(Number(e.target.value))} />
                  </label>
                </div>
                <div className="xp-checks">
                  <label><input type="checkbox" checked={independent} onChange={e => setIndependent(e.target.checked)} /><span>Scale every photo on its own<small>Brightness can then no longer be compared between photos.</small></span></label>
                </div>
                <div className="xp-row">
                  <button className="xp-pill" type="button" onClick={() => canvasRef.current?.zoom(1.4)} aria-label="Zoom in">Zoom in</button>
                  <button className="xp-pill" type="button" onClick={() => canvasRef.current?.zoom(0.7)} aria-label="Zoom out">Zoom out</button>
                  <button className="xp-pill" type="button" onClick={() => canvasRef.current?.resetView()}>Fit</button>
                </div>
              </div>
            </details>

            <details className="xp-tool">
              <summary><span className="xp-tool__k">Show on the photo</span><span className="xp-tool__t">Known stars from ESA Gaia, what NASA's WISE saw, and the measured path.</span></summary>
              <div className="xp-tool__body">
                <div className="xp-checks">
                  <label><input type="checkbox" checked={showCatalog} onChange={e => setShowCatalog(e.target.checked)} /><span>Known stars (ESA Gaia DR3)<small>Moved to each photo's date using their measured motion.</small></span></label>
                  {showCatalog && field?.catalog_status === 'loading' && <p className="xp-small" role="status">Loading the Gaia overlay…</p>}
                  {showCatalog && field?.catalog_status === 'unavailable' && <p className="xp-small" role="status">Gaia overlay unavailable for this field.</p>}
                  <label><input type="checkbox" checked={showWise} onChange={e => setShowWise(e.target.checked)} /><span>What NASA's WISE saw around 2015{showWise && !wise ? ' (loading…)' : ''}<small>Diamonds mark things WISE saw moving.</small></span></label>
                  {wiseError && <span className="xp-small">{wiseError}</span>}
                  <label><input type="checkbox" checked={showTrack} onChange={e => setShowTrack(e.target.checked)} disabled={!trackSource?.motion} /><span>Fitted path<small>A model, drawn dashed. Not a photo.</small></span></label>
                  <label><input type="checkbox" checked={showGrid} onChange={e => setShowGrid(e.target.checked)} /><span>Sky grid (RA and Dec)</span></label>
                  <label><input type="checkbox" checked={smooth} onChange={e => setSmooth(e.target.checked)} /><span>Smooth pixels<small>For viewing only. Measurements use the original pixels.</small></span></label>
                  <label><input type="checkbox" checked={fade} onChange={e => setFade(e.target.checked)} /><span>Smooth playback<small>Each photo fades into the next.</small></span></label>
                </div>
              </div>
            </details>

            {shownFrame && (
              <details className="xp-tool">
                <summary><span className="xp-tool__k">About this photo</span><span className="xp-tool__t">Date, colour, quality flags and the original NASA file.</span></summary>
                <div className="xp-tool__body">
                  <dl className="xp-kv">
                    <dt>Taken</dt><dd>{dateTime(shownFrame.time_utc)}</dd>
                    <dt>Colour</dt><dd>{um(shownFrame.wavelength_um)} (band {um(shownFrame.bandwidth_um)} wide)</dd>
                    <dt>Across the photo</dt><dd>{shownFrame.wavelength_range_um ? `${shownFrame.wavelength_range_um[0].toFixed(3)}–${shownFrame.wavelength_range_um[1].toFixed(3)} µm` : NA}</dd>
                    <dt>Detector</dt><dd>{shownFrame.detector}</dd>
                    <dt>Visit</dt><dd>{shownFrame.visit}</dd>
                    <dt>Data release</dt><dd>{shownFrame.release} {shownFrame.processing_version ?? ''}</dd>
                    <dt>Quality flags</dt><dd>{shownFrame.flags_at_center.length ? shownFrame.flags_at_center.join(', ') : 'none at the centre'}</dd>
                    <dt>Photo ID</dt><dd className="mono">{shownFrame.id}</dd>
                    <dt>Original file</dt><dd><a href={shownFrame.cutout_url} target="_blank" rel="noreferrer">FITS cutout ↗</a> <span className="mono xp-dim" title={shownFrame.sha256}>sha256 {shownFrame.sha256?.slice(0, 10)}…</span></dd>
                  </dl>
                  <p className="xp-small">Photos are lined up and smoothed for viewing. Every measurement uses the original pixels.</p>
                </div>
              </details>
            )}

            {field?.stacks && field.stacks.length > 0 && (
              <details className="xp-tool">
                <summary><span className="xp-tool__k">Photos added along its path</span><span className="xp-tool__t">Many photos lined up on the moving object, so it shows clearly.</span></summary>
                <div className="xp-tool__body">
                  <p className="xp-small">{field.stacks[0].note}</p>
                  <div className="xp-stacks">
                    {field.stacks.slice().sort((a, b) => STACK_ORDER(a.id) - STACK_ORDER(b.id)).map(s => (
                      <figure key={s.id}>
                        <StackStill stack={s} alt={`Shift-and-stack of ${s.n_frames} exposures, ${s.label}`} />
                        <figcaption><strong>{s.label}</strong> · {s.n_frames} photos</figcaption>
                      </figure>
                    ))}
                  </div>
                  <p className="xp-small">Centre = where it was predicted to be. {field.stacks[0].pixel_arcsec}″ pixels.</p>
                </div>
              </details>
            )}

            {field?.archive && (
              <details className="xp-tool">
                <summary><span className="xp-tool__k">Where the photos come from</span><span className="xp-tool__t">Every SPHEREx visit to this spot, from NASA's IRSA archive.</span></summary>
                <div className="xp-tool__body">
                  <ul className="xp-visits">
                    {field.archive.visits.map(v => (
                      <li key={v.id}><strong>{v.id}</strong><span>{v.start_utc.slice(0, 10)} to {v.end_utc.slice(0, 10)}</span><span className="xp-dim">{v.n_products} photos · {(v.releases ?? []).join('/')}</span>{v.sealed && <span className="xp-tag">sealed</span>}</li>
                    ))}
                  </ul>
                  <p className="xp-small">{field.archive.n_products} files from {(field.archive.collections ?? []).join(', ')} (IRSA SIA2), asked {field.archive.queried_utc?.slice(0, 16).replace('T', ' ')} UTC.</p>
                </div>
              </details>
            )}
          </div>
          <p className="xp-keys">Keys: Space plays · ← → step · B blinks · D subtracts · + − zoom (or pinch, or Ctrl + scroll) · 0 fits · Esc closes</p>
        </section>
      )}
    </main>
  );
}
