import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, cachedFrame, loadFrames, type Field, type Frame, type Investigation, type Target } from '../api.ts';
import { Header } from '../components/Shell.tsx';
import { SkyCanvas, type Colormap, type Overlays, type SkyCanvasHandle } from '../components/SkyCanvas.tsx';
import { Timeline } from '../components/Timeline.tsx';
import { DataStatePill } from '../components/DataState.tsx';
import { InvestigationView, Progress } from '../components/InvestigationView.tsx';
import { StackStill } from '../components/FieldImage.tsx';
import { resolveQuery } from '../components/SearchBox.tsx';
import { Term } from '../components/Term.tsx';
import { fetchTargets, useField, useInvestigation, usePrefersReducedMotion } from '../hooks.ts';
import { Link, navigate, replaceQuery, useLocation } from '../router.tsx';
import {
  angularSeparationArcsec, formatDec, formatRA, fromTangent, percentile, propagateLinear, wavelengthColor, wavelengthMatched, type SkyPoint, type StretchKind,
} from '../lib/astro.ts';
import { difference, sharedLimits, stack as stackFrames, subtractBackground } from '../lib/compose.ts';
import { NA, dateTime, num, um } from '../lib/format.ts';

type Mode = 'animate' | 'blink' | 'difference' | 'stack' | 'spectral';
const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: 'animate', label: 'Play', hint: 'Play the images in the order they were taken' },
  { id: 'blink', label: 'Blink', hint: 'Flip between two dates. Anything that jumps has moved' },
  { id: 'difference', label: 'Subtract', hint: 'Later minus earlier. A mover leaves a dark spot next to a bright one' },
  { id: 'stack', label: 'Add', hint: 'Add all the images together to see fainter things' },
  { id: 'spectral', label: 'Colour', hint: 'Order the images by infrared colour instead of time' },
];

const STACK_ORDER = (id: string) => ({ 'stack-short': 0, 'stack-long': 1, 'stack-mid': 2 } as Record<string, number>)[id] ?? 3;

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

  const [targets, setTargets] = useState<Target[] | null>(null);
  const [liveFieldId, setLiveFieldId] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const target = targets?.find(t => t.slug === targetSlug) ?? null;

  useEffect(() => { fetchTargets().then(setTargets).catch(() => setTargets([])); }, []);

  // Live query: create (or reuse) a field for the requested coordinates.
  useEffect(() => {
    if (targetSlug || fieldParam || !raParam || !decParam) { setLiveFieldId(null); return; }
    let alive = true;
    setStartError(null);
    setLiveFieldId(null);
    api.createField({ ra: raParam, dec: decParam, fov_arcmin: fovParam ?? 6 })
      .then(r => { if (alive) setLiveFieldId(r.field_id); })
      .catch(err => { if (alive) setStartError(err.message); });
    return () => { alive = false; };
  }, [targetSlug, fieldParam, raParam, decParam, fovParam]);

  const fieldId = fieldParam ?? (targetSlug ? (target?.field?.field_id ?? (targets ? targetSlug : null)) : liveFieldId);
  const { data: field, error: fieldError } = useField(fieldId);

  const idle = !targetSlug && !fieldParam && !raParam;

  return (
    <div className="explore">
      <Header>
        <ExploreSearch fov={fovParam ?? field?.fov_arcmin ?? 6} />
      </Header>
      {idle ? <ExploreIdle targets={targets} /> : (
        <ExploreWorkspace
          key={fieldId ?? 'pending'}
          field={field}
          fieldError={fieldError ?? startError}
          target={target}
          params={params}
          invParam={invParam}
          pendingLabel={raParam && decParam ? `${raParam}, ${decParam}` : targetSlug ?? ''}
        />
      )}
    </div>
  );
}

function ExploreSearch({ fov }: { fov: number }) {
  const [q, setQ] = useState('');
  const [f, setF] = useState(String(fov));
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => setF(String(fov)), [fov]);
  async function go(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true); setErr(null);
    try {
      const r = await resolveQuery(q.trim());
      const fv = Math.min(30, Math.max(2, Number(f) || 6));
      if (r.target) navigate(`/explore?target=${r.target}`);
      else navigate(`/explore?ra=${r.ra.toFixed(6)}&dec=${r.dec.toFixed(6)}&fov=${fv}`);
      setQ('');
    } catch (ex) { setErr((ex as Error).message); } finally { setBusy(false); }
  }
  return (
    <form className="topsearch" onSubmit={go} role="search">
      <label className="visually-hidden" htmlFor="topq">Object name or coordinates</label>
      <input id="topq" value={q} onChange={e => setQ(e.target.value)} placeholder="A name or coordinates" autoComplete="off" spellCheck={false} aria-invalid={!!err} />
      <label className="topsearch__fov" title="Field of view for new queries (arcmin). Larger fields mean bigger downloads.">
        <span>Width</span>
        <input type="number" min={2} max={30} step={1} value={f} onChange={e => setF(e.target.value)} aria-label="Field of view in arcminutes" />
        <span>′</span>
      </label>
      <button className="button button--primary button--small" disabled={busy}>{busy ? '…' : 'Go'}</button>
      {err && <span className="topsearch__error" role="alert">{err}</span>}
    </form>
  );
}

function ExploreIdle({ targets }: { targets: Target[] | null }) {
  return (
    <main id="main" className="page"><div className="page__inner">
      <div className="idle">
        <p className="eyebrow">Explore</p>
        <h1>Pick a patch of sky</h1>
        <p className="muted">Type a name or coordinates above. Or start with one of NASA's test targets.</p>
        <div className="idle__targets">
          {targets?.map(t => (
            <Link key={t.slug} href={`/explore?target=${t.slug}`} className="idle__target">
              <strong>{t.title}</strong><span>{t.kind}</span>
            </Link>
          ))}
        </div>
        <p className="small dim">Or try anywhere: <Link href="/explore?ra=270.0&dec=-23.5&fov=6">the centre of the Milky Way</Link> · <Link href="/explore?ra=10.6847&dec=41.269&fov=8">the Andromeda galaxy</Link></p>
      </div>
    </div></main>
  );
}

interface WorkspaceProps {
  field: Field | null;
  fieldError: string | null;
  target: Target | null;
  params: URLSearchParams;
  invParam: string | null;
  pendingLabel: string;
}

function ExploreWorkspace({ field, fieldError, target, params, invParam, pendingLabel }: WorkspaceProps) {
  const reduced = usePrefersReducedMotion();
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
  const [smooth, setSmooth] = useState(false);
  const [showGrid, setShowGrid] = useState(false);
  const [showCatalog, setShowCatalog] = useState(false);
  const [fps, setFps] = useState(4);
  const [playing, setPlaying] = useState(false);
  const [index, setIndex] = useState(0);
  const [aId, setAId] = useState<string | null>(params.get('a'));
  const [bId, setBId] = useState<string | null>(params.get('b'));
  const [blinkPhase, setBlinkPhase] = useState(0);
  const [loadedTick, setLoadedTick] = useState(0);
  const [selected, setSelected] = useState<SkyPoint | null>(params.get('src_ra') && params.get('src_dec') ? { ra: Number(params.get('src_ra')), dec: Number(params.get('src_dec')) } : null);
  const [invId, setInvId] = useState<string | null>(invParam);
  const [invError, setInvError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [copied, setCopied] = useState(false);
  const initialFrameId = useRef(params.get('frame'));
  const urlHasView = useRef(['mode', 'det', 'wmin', 'wmax', 'a', 'b'].some(k => params.has(k)));
  const defaultsDone = useRef(false);
  const [pendingPair, setPendingPair] = useState(false);
  const [showTrack, setShowTrack] = useState(params.get('track') !== '0');

  // Default detector for curated fields: the detector covering most visits.
  useEffect(() => {
    if (dets === null && wmin === null && wmax === null && allFrames.length > 40) {
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

  // Restore the shared frame from the URL once.
  useEffect(() => {
    if (initialFrameId.current && frames.length) {
      const i = frames.findIndex(f => f.id === initialFrameId.current);
      if (i >= 0) setIndex(i);
      initialFrameId.current = null;
    }
  }, [frames]);

  const safeIndex = Math.min(index, Math.max(frames.length - 1, 0));
  const current = frames[safeIndex] ?? null;
  const aIdx = aId ? frames.findIndex(f => f.id === aId) : -1;
  const bIdx = bId ? frames.findIndex(f => f.id === bId) : -1;
  const frameA = aIdx >= 0 ? frames[aIdx] : frames[0] ?? null;
  const frameB = bIdx >= 0 ? frames[bIdx] : frames[frames.length - 1] ?? null;

  // ---------- load frames for the current filter (current first) ----------
  useEffect(() => {
    if (!grid || !frames.length) return;
    const ctl = new AbortController();
    const order = [...frames.slice(safeIndex), ...frames.slice(0, safeIndex)];
    const urls = (mode === 'stack' ? order.slice(0, 240) : order).map(f => f.data_url);
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
    if (!playing || frames.length < 2) return;
    if (mode === 'blink') {
      const id = window.setInterval(() => setBlinkPhase(p => 1 - p), 700);
      return () => window.clearInterval(id);
    }
    const id = window.setInterval(() => setIndex(i => (i + 1) % frames.length), 1000 / fps);
    return () => window.clearInterval(id);
  }, [playing, fps, frames.length, mode]);

  useEffect(() => { if (reduced) setPlaying(false); }, [reduced]);

  // ---------- keep the share URL current ----------
  useEffect(() => {
    replaceQuery({
      mode: mode === 'animate' ? null : mode,
      det: dets?.length ? dets.join(',') : null,
      wmin: wmin != null ? wmin.toFixed(3) : null,
      wmax: wmax != null ? wmax.toFixed(3) : null,
      frame: current?.id ?? null,
      stretch: stretch === 'asinh' ? null : stretch,
      cmap: cmap === 'gray' ? null : cmap,
      a: mode === 'blink' || mode === 'difference' ? frameA?.id ?? null : null,
      b: mode === 'blink' || mode === 'difference' ? frameB?.id ?? null : null,
      inv: invId,
      src_ra: selected ? selected.ra.toFixed(6) : null,
      src_dec: selected ? selected.dec.toFixed(6) : null,
      track: showTrack ? null : '0',
    });
  }, [mode, dets, wmin, wmax, current?.id, stretch, cmap, frameA?.id, frameB?.id, invId, selected, showTrack]);

  // ---------- compose pixels ----------
  const composed = useMemo(() => {
    if (!grid || !frames.length) return null;
    if (mode === 'stack') {
      const loaded = frames.slice(0, 240).map(f => ({ f, d: cachedFrame(f.data_url) })).filter(x => x.d);
      if (!loaded.length) return null;
      const s = stackFrames(loaded.map(x => ({ data: x.d!, median: x.f.stats.median })));
      return { data: s.data, kind: 'stack' as const, n: loaded.length };
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
    if (!field || !grid) return;
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
  }, [field, grid, targetHere, curatedInvId]);

  // ---------- keyboard ----------
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'SELECT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      if (e.key === ' ') { e.preventDefault(); setPlaying(p => !p); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); setPlaying(false); setIndex(i => (i + 1) % Math.max(frames.length, 1)); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); setPlaying(false); setIndex(i => (i - 1 + frames.length) % Math.max(frames.length, 1)); }
      else if (e.key.toLowerCase() === 'b') setMode(m => (m === 'blink' ? 'animate' : 'blink'));
      else if (e.key.toLowerCase() === 'd') setMode(m => (m === 'difference' ? 'animate' : 'difference'));
      else if (e.key === '+' || e.key === '=') canvasRef.current?.zoom(1.25);
      else if (e.key === '-') canvasRef.current?.zoom(0.8);
      else if (e.key === '0') canvasRef.current?.resetView();
      else if (e.key === 'Escape') setInvId(null);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [frames.length]);

  // ---------- overlays ----------
  const overlays = useMemo<Overlays>(() => {
    const o: Overlays = { markers: [] };
    const epoch = composed?.kind === 'single' && composed.frame ? composed.frame.mjd : current?.mjd;
    if (field?.catalog && epoch != null) {
      o.catalog = field.catalog.map(s => ({ ...propagateLinear(s.ra, s.dec, s.pmra, s.pmdec, field.catalog_epoch_mjd, epoch), g: s.g }));
    }
    const m = showTrack && trackSource ? trackSource.motion : null;
    if (m && m.track.length > 1) {
      const ref = m.models[m.reported_model ?? m.preferred_model]?.reference;
      if (ref) {
        o.track = { points: m.track.map(p => fromTangent(p.xi, p.eta, ref.ra_deg, ref.dec_deg)), label: '', color: 'rgba(255,178,126,0.9)' };
        o.measured = { points: m.points.map(p => fromTangent(p.xi, p.eta, ref.ra_deg, ref.dec_deg)), color: 'rgba(143,180,255,0.55)' };
        if (epoch != null && m.track.length) {
          // model position at this frame's epoch (nearest track sample)
          let best = m.track[0];
          for (const p of m.track) if (Math.abs(p.mjd - epoch) < Math.abs(best.mjd - epoch)) best = p;
          const sp = fromTangent(best.xi, best.eta, ref.ra_deg, ref.dec_deg);
          o.markers!.push({ ...sp, color: '#ffa269', shape: 'cross', size: 12 });
        }
      }
    }
    if (selected && !(m && m.track.length > 1 && invId === curatedInvId)) o.markers!.push({ ...selected, color: '#ffa269', shape: 'ring', size: 11, label: invId ? 'selected' : undefined });
    return o;
  }, [field, trackSource, showTrack, current?.mjd, composed, selected, invId, curatedInvId]);

  const hint = targetHere && !invId && field?.kind === 'curated' ? { ...targetHere, text: `${target?.title} · click to measure` } : null;

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
  const state = field?.data_state ?? (fieldError ? 'failed' : 'processing');
  const detCounts = useMemo(() => {
    const c = new Map<number, number>();
    allFrames.forEach(f => c.set(f.detector, (c.get(f.detector) ?? 0) + 1));
    return c;
  }, [allFrames]);
  const loadedNow = composed !== null;

  let emptyMessage: { title: string; detail?: string; loading?: boolean } | null = null;
  if (fieldError) emptyMessage = { title: 'Could not open this field', detail: fieldError };
  else if (!field) emptyMessage = { title: 'Contacting the archive…', detail: pendingLabel ? `Field: ${pendingLabel}` : undefined, loading: true };
  else if (state === 'processing' && !allFrames.length) emptyMessage = { title: 'Retrieving real SPHEREx observations', detail: field.message ?? 'Querying IRSA (DR1 + QR3), downloading cutouts and aligning them on a common grid. This takes 10–60 s.', loading: true };
  else if (state === 'no_coverage') emptyMessage = { title: 'No SPHEREx observations here yet', detail: field.message ?? 'IRSA returned no DR1/QR3 spectral images covering this position.' };
  else if (state === 'archive_unavailable') emptyMessage = { title: 'Archive temporarily unavailable', detail: field.message ?? 'IRSA did not respond. Try a cached target or retry shortly.' };
  else if (state === 'failed') emptyMessage = { title: 'Processing failed', detail: field.message ?? undefined };
  else if (!frames.length && allFrames.length) emptyMessage = { title: 'No exposures match this filter', detail: 'Widen the wavelength range or select more detectors.' };
  else if (!pixels && frames.length) emptyMessage = { title: 'Loading exposures…', loading: true };

  const shownFrame = composed?.kind === 'single' ? composed.frame : mode === 'difference' ? null : current;

  return (
    <main id="main" className={`ws${invId ? ' ws--inv' : ''}${panelOpen ? '' : ' ws--panel-closed'}`}>
      {/* Field bar */}
      <div className="ws__bar">
        <div className="ws__title">
          <h1>{field?.title ?? target?.title ?? (field && Number.isFinite(field.ra) ? `${formatRA(field.ra, 1)} ${formatDec(field.dec, 0)}` : 'Opening field')}</h1>
          {field && Number.isFinite(field.ra) && <p className="mono small dim">{allFrames.length} images · {num(field.fov_arcmin, 0)}′ wide · {field.ra.toFixed(5)}°, {field.dec.toFixed(5)}°</p>}
        </div>
        <div className="ws__bar-right">
          <DataStatePill state={state} progress={field?.progress} />
          <button className="button button--ghost button--small" onClick={share}>{copied ? 'Link copied' : 'Share'}</button>
          <button className="button button--ghost button--small ws__panel-toggle" onClick={() => setPanelOpen(o => !o)} aria-expanded={panelOpen}>{panelOpen ? 'Hide controls' : 'Controls'}</button>
        </div>
      </div>

      {field?.message && state !== 'processing' && allFrames.length > 0 && <p className="ws__note small" role="status">{field.message}</p>}
      {mode === 'blink' && frameA && frameB && matched && field?.kind === 'curated' && (
        <p className="ws__hintbar small" role="status">
          Flipping between {frameA.time_utc.slice(0, 7)} and {frameB.time_utc.slice(0, 7)}. Stars stay put. <strong>The dot that jumps is moving.</strong> Click it to measure it.
        </p>
      )}
      <div className="ws__body">
        <section className="ws__stage" aria-label="Sky viewer">
          {grid ? (
            <SkyCanvas
              ref={canvasRef}
              grid={grid}
              pixels={pixels}
              display={display}
              overlays={overlays}
              showGrid={showGrid}
              showCatalog={showCatalog}
              smoothing={smooth}
              hint={hint}
              onPick={pick}
              emptyMessage={emptyMessage}
              caption={`${mode === 'stack' ? `${composed?.n ?? 0} images added together` : mode === 'difference' ? 'Later image minus earlier image' : 'Aligned for viewing. Measurements use the original pixels.'}${overlays.track ? ' Dashed line: fitted path (a model, not an observation).' : ''}`}
              ariaLabel={`SPHEREx image of ${field?.title ?? 'the selected field'}. Click a source to measure it.`}
            />
          ) : (
            <div className="sky"><div className="sky__message" data-loading={emptyMessage?.loading ? 'true' : 'false'}>
              <p className="sky__message-title">{emptyMessage?.title ?? 'Opening field'}</p>
              {emptyMessage?.detail && <p className="sky__message-detail">{emptyMessage.detail}</p>}
              {field?.progress && <Progress {...field.progress} />}
            </div></div>
          )}
          {field?.progress && state === 'processing' && grid && <div className="ws__progress"><Progress {...field.progress} /></div>}

          {/* Frame readout */}
          <div className="ws__readout">
            {mode === 'difference' && frameA && frameB ? (
              <>
                <span className="mono">B {frameB.time_utc.slice(0, 10)} {um(frameB.wavelength_um, 3)} − A {frameA.time_utc.slice(0, 10)} {um(frameA.wavelength_um, 3)}</span>
                <span className={`badge ${matched ? 'badge--ok' : 'badge--warn'}`}>
                  <Term t="wavelength-matched">{matched === null ? 'Wavelength match unknown' : matched ? 'Wavelength-matched' : 'Different wavelengths: brightness not directly comparable'}</Term>
                </span>
              </>
            ) : mode === 'stack' ? (
              <span className="mono">{composed?.n ?? 0} exposures · {frames[0] && frames[frames.length - 1] ? `${frames[0].time_utc.slice(0, 10)} → ${frames[frames.length - 1].time_utc.slice(0, 10)}` : ''} · moving sources smear in a sky-frame stack</span>
            ) : shownFrame ? (
              <>
                <span className="mono">{dateTime(shownFrame.time_utc)}</span>
                <span className="mono"><span className="swatch" style={{ background: wavelengthColor(shownFrame.wavelength_um) }} />{um(shownFrame.wavelength_um, 3)} <span className="dim">± {num((shownFrame.bandwidth_um ?? NaN) / 2, 3)}</span></span>
                <span className="mono">D{shownFrame.detector} · {shownFrame.release} · {shownFrame.visit}</span>
                {mode === 'blink' && <span className="badge">{blinkPhase ? 'B · later' : 'A · earlier'}</span>}
                {mode === 'blink' && <span className={`badge ${matched ? 'badge--ok' : 'badge--warn'}`}>{matched ? 'A/B wavelength-matched' : 'A/B at different wavelengths'}</span>}
                {independent && <span className="badge badge--warn">Independent scaling: brightness not comparable between frames</span>}
                {!loadedNow && <span className="dim small">loading…</span>}
              </>
            ) : null}
          </div>

          {/* Transport + timeline */}
          <div className="ws__transport">
            <div className="transport" role="group" aria-label="Playback">
              <button className="icon" onClick={() => { setPlaying(false); setIndex(i => (i - 1 + frames.length) % Math.max(frames.length, 1)); }} disabled={frames.length < 2} aria-label="Previous exposure (←)">‹</button>
              <button className="button button--primary button--play" onClick={() => setPlaying(p => !p)} disabled={frames.length < 2 || mode === 'stack' || mode === 'difference'} aria-label={playing ? 'Pause (space)' : 'Play (space)'}>{playing ? 'Pause' : 'Play'}</button>
              <button className="icon" onClick={() => { setPlaying(false); setIndex(i => (i + 1) % Math.max(frames.length, 1)); }} disabled={frames.length < 2} aria-label="Next exposure (→)">›</button>
              <label className="transport__speed"><span className="visually-hidden">Speed</span>
                <select value={fps} onChange={e => setFps(Number(e.target.value))} aria-label="Playback speed">
                  {[1, 2, 4, 8, 12].map(v => <option key={v} value={v}>{v} fps</option>)}
                </select>
              </label>
              <span className="transport__count mono">{frames.length ? `${safeIndex + 1} / ${frames.length}` : '0 / 0'}</span>
            </div>
            <Timeline frames={frames} index={safeIndex} onSelect={i => { setPlaying(false); setIndex(i); }} axis={mode === 'spectral' ? 'wavelength' : 'time'}
              markA={mode === 'blink' || mode === 'difference' ? (aIdx >= 0 ? aIdx : 0) : null}
              markB={mode === 'blink' || mode === 'difference' ? (bIdx >= 0 ? bIdx : frames.length - 1) : null} />
          </div>
        </section>

        {/* Control panel */}
        <aside className="ws__panel" aria-label="Viewer controls" hidden={!panelOpen}>
          <div className="panel-sec">
            <p className="panel-tip"><strong>Click any dot</strong> in the image to measure how it moves.</p>
            <h2 className="panel-h">View</h2>
            <div className="seg" role="radiogroup" aria-label="Display mode">
              {MODES.map(m => (
                <button key={m.id} role="radio" aria-checked={mode === m.id} className={`seg__btn${mode === m.id ? ' is-on' : ''}`} onClick={() => { setMode(m.id); if (m.id === 'stack' || m.id === 'difference') setPlaying(false); }} title={m.hint}>{m.label}</button>
              ))}
            </div>
            <p className="small dim">{MODES.find(m => m.id === mode)?.hint}.</p>
            {(mode === 'blink' || mode === 'difference') && (
              <div className="ab">
                <div className="ab__row"><span className="ab__tag">A</span><span className="mono small">{frameA ? `${frameA.time_utc.slice(0, 10)} · ${um(frameA.wavelength_um)}` : NA}</span><button className="button button--ghost button--tiny" onClick={() => current && setAId(current.id)}>Use current</button></div>
                <div className="ab__row"><span className="ab__tag">B</span><span className="mono small">{frameB ? `${frameB.time_utc.slice(0, 10)} · ${um(frameB.wavelength_um)}` : NA}</span><button className="button button--ghost button--tiny" onClick={() => current && setBId(current.id)}>Use current</button></div>
                <button className="button button--ghost button--small" onClick={() => { if (!autoMatchedPair()) alert('No two images of the same colour were found.'); }}>Use the first and last dates</button>
              </div>
            )}
          </div>

          <details className="panel-more">
          <summary>More controls</summary>
          <div className="panel-sec">
            <h2 className="panel-h">Infrared colour</h2>
            <div className="dets">
              {[1, 2, 3, 4, 5, 6].map(d => {
                const on = !dets || dets.includes(d);
                const n = detCounts.get(d) ?? 0;
                const mid = [0.92, 1.36, 2.02, 3.12, 4.12, 4.71][d - 1];
                return (
                  <button key={d} className={`det${on ? ' is-on' : ''}`} disabled={!n} aria-pressed={on}
                    onClick={() => setDets(prev => {
                      const cur = prev ?? [1, 2, 3, 4, 5, 6];
                      const next = cur.includes(d) ? cur.filter(x => x !== d) : [...cur, d].sort();
                      return next.length === 6 ? null : next.length ? next : [d];
                    })}
                    style={{ ['--det' as string]: wavelengthColor(mid) }} title={`Detector ${d}: ${n} exposures`}>
                    D{d}<span className="det__n mono">{n}</span>
                  </button>
                );
              })}
            </div>
            <div className="wrange">
              <label>λ min <input type="number" step={0.01} min={0.7} max={5.1} value={wmin ?? ''} placeholder="0.75" onChange={e => setWmin(e.target.value ? Number(e.target.value) : null)} /> µm</label>
              <label>λ max <input type="number" step={0.01} min={0.7} max={5.1} value={wmax ?? ''} placeholder="5.00" onChange={e => setWmax(e.target.value ? Number(e.target.value) : null)} /> µm</label>
            </div>
            <div className="row-btns">
              <button className="button button--ghost button--small" disabled={!current?.wavelength_um} onClick={() => {
                if (!current?.wavelength_um) return;
                const hw = Math.max(current.bandwidth_um ?? 0.02, 0.01);
                setDets(null); setWmin(+(current.wavelength_um - hw).toFixed(3)); setWmax(+(current.wavelength_um + hw).toFixed(3));
              }}>Only this colour</button>
              <button className="button button--ghost button--small" onClick={() => { setDets(null); setWmin(null); setWmax(null); }}>All</button>
            </div>
            <p className="small dim">{frames.length} of {allFrames.length} images shown. <Term t="wavelength-matched">Why wavelength matters</Term></p>
          </div>

          <div className="panel-sec">
            <h2 className="panel-h">Brightness and overlays</h2>
            <div className="ctl-grid">
              <label>Stretch
                <select value={stretch} onChange={e => setStretch(e.target.value as StretchKind)}>
                  <option value="asinh">asinh</option><option value="linear">linear</option><option value="log">log</option>
                </select>
              </label>
              <label>Colour
                <select value={cmap} onChange={e => setCmap(e.target.value as Colormap)} disabled={mode === 'difference'}>
                  <option value="gray">grey</option><option value="ember">ember</option>
                </select>
              </label>
              <label>Black point <span className="mono dim">−{black.toFixed(1)}σ</span>
                <input type="range" min={0} max={5} step={0.1} value={black} onChange={e => setBlack(Number(e.target.value))} />
              </label>
              <label>Contrast <span className="mono dim">{contrast.toFixed(2)}×</span>
                <input type="range" min={0.2} max={8} step={0.05} value={contrast} onChange={e => setContrast(Number(e.target.value))} />
              </label>
            </div>
            <div className="checks">
              <label><input type="checkbox" checked={showTrack} onChange={e => setShowTrack(e.target.checked)} disabled={!trackSource?.motion} /> Fitted path (a model)</label>
              <label><input type="checkbox" checked={showCatalog} onChange={e => setShowCatalog(e.target.checked)} /> Known stars (Gaia)</label>
              <label><input type="checkbox" checked={showGrid} onChange={e => setShowGrid(e.target.checked)} /> Coordinate grid</label>
              <label><input type="checkbox" checked={smooth} onChange={e => setSmooth(e.target.checked)} /> Smooth pixels</label>
              <label><input type="checkbox" checked={independent} onChange={e => setIndependent(e.target.checked)} /> Rescale every image on its own</label>
            </div>
            <div className="row-btns">
              <button className="button button--ghost button--small" onClick={() => canvasRef.current?.zoom(1.4)} aria-label="Zoom in">Zoom +</button>
              <button className="button button--ghost button--small" onClick={() => canvasRef.current?.zoom(0.7)} aria-label="Zoom out">Zoom −</button>
              <button className="button button--ghost button--small" onClick={() => canvasRef.current?.resetView()}>Fit</button>
            </div>
          </div>

          {shownFrame && (
            <div className="panel-sec">
              <h2 className="panel-h">This image</h2>
              <dl className="kv">
                <dt>Product</dt><dd className="mono small">{shownFrame.id}</dd>
                <dt>Observed</dt><dd className="mono small">{dateTime(shownFrame.time_utc)}</dd>
                <dt>Wavelength</dt><dd className="mono small">{um(shownFrame.wavelength_um)} (bandwidth {um(shownFrame.bandwidth_um)})</dd>
                <dt>Across cutout</dt><dd className="mono small">{shownFrame.wavelength_range_um ? `${shownFrame.wavelength_range_um[0].toFixed(3)}–${shownFrame.wavelength_range_um[1].toFixed(3)} µm` : NA}</dd>
                <dt>Release</dt><dd className="small">{shownFrame.release} {shownFrame.processing_version ?? ''}</dd>
                <dt>Flags at centre</dt><dd className="small">{shownFrame.flags_at_center.length ? shownFrame.flags_at_center.join(', ') : 'none'}</dd>
                <dt>Source</dt><dd className="small"><a href={shownFrame.cutout_url} target="_blank" rel="noreferrer">FITS cutout ↗</a> · <span className="mono" title={shownFrame.sha256}>sha256 {shownFrame.sha256?.slice(0, 10)}…</span></dd>
              </dl>
            </div>
          )}

          {field?.stacks && field.stacks.length > 0 && (
            <div className="panel-sec">
              <h2 className="panel-h">Images added along the source's path</h2>
              <p className="small dim">{field.stacks[0].note}</p>
              <div className="stacks">
                {field.stacks.slice().sort((a, b) => STACK_ORDER(a.id) - STACK_ORDER(b.id)).map(s => (
                  <figure key={s.id} className="stackfig">
                    <StackStill stack={s} alt={`Shift-and-stack of ${s.n_frames} exposures, ${s.label}`} />
                    <figcaption><strong>{s.label}</strong><span className="mono dim"> · {s.n_frames} exp.</span></figcaption>
                  </figure>
                ))}
              </div>
              <p className="small dim">Centre = the predicted source position. {field.stacks[0].pixel_arcsec}″ pixels.</p>
            </div>
          )}

          {field?.archive && (
            <div className="panel-sec">
              <h2 className="panel-h">Where the data comes from</h2>
              <ul className="visits">
                {field.archive.visits.map(v => (
                  <li key={v.id}><span>{v.id}</span><span className="mono small">{v.start_utc.slice(0, 10)} → {v.end_utc.slice(0, 10)}</span><span className="mono small dim">{v.n_products} · {(v.releases ?? []).join('/')}</span>{v.sealed && <span className="badge badge--warn">sealed</span>}</li>
                ))}
              </ul>
              <p className="small dim">{field.archive.n_products} products from {(field.archive.collections ?? []).join(', ')} (IRSA SIA2), queried {field.archive.queried_utc?.slice(0, 16).replace('T', ' ')} UTC.</p>
            </div>
          )}
          </details>
          <p className="small dim panel-keys">Keys: space plays · ← → step · B blinks · + − zoom</p>
        </aside>

        {/* Investigation drawer */}
        {(invId || invError) && (
          <aside className="drawer" aria-label="Investigation">
            <div className="drawer__bar">
              <span className="eyebrow">Measurement</span>
              <div className="row-btns">
                {invId && investigation?.status === 'ready' && <Link className="button button--ghost button--small" href={`/investigation/${encodeURIComponent(invId)}`}>Full page</Link>}
                <button className="button button--ghost button--small" onClick={() => { setInvId(null); setInvError(null); }} aria-label="Close investigation (Esc)">Close</button>
              </div>
            </div>
            <div className="drawer__body">
              {invError && <p className="notice notice--bad">{invError}</p>}
              {inv.error && <p className="notice notice--bad">{inv.error}</p>}
              {!investigation && inv.loading && <div className="inv inv--processing"><p className="eyebrow">Measuring</p><Progress stage="loading" done={0} total={0} /></div>}
              {investigation && <InvestigationView inv={investigation} compact />}
            </div>
          </aside>
        )}
      </div>
    </main>
  );
}
