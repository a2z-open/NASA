import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Mark } from './Shell.tsx';
import './DiscoveryPanel.css';

interface Observation {
  mjd_utc: number;
  night: string;
  station: string;
  ra_deg: number;
  dec_deg: number;
  phase: 'fit' | 'test';
  stage?: string;
  line_sha256: string;
  predicted_ra_deg?: number;
  predicted_dec_deg?: number;
  residual_arcsec?: number;
}

interface Frame {
  file: string;
  epoch: string;
  source_url: string;
}

interface Candidate {
  id: string;
  display_label?: string;
  arc_days?: number;
  observations: Observation[];
  orbit: { rms_arcsec?: number; semimajor_axis_au?: number };
  catalog: { status: string; name?: string; source_url?: string; message?: string;
    matched_observations?: number; total_observations?: number };
  images: { status: string; frames: Frame[]; message?: string; combined_snr?: number;
    coverage: { night: string; source_url: string; message: string }[] };
}

interface Packet {
  kind?: 'linkage';
  candidates: Candidate[];
  request: { benchmark: boolean; start: string; end: string; chunks?: string[] };
  activity?: string[];
  followup?: Followup;
}

interface Followup {
  status: 'found' | 'no_results' | 'incomplete' | 'no_predictions';
  radius_arcmin: number;
  margin_minutes: number;
  checks: {
    status: 'found' | 'no_results' | 'incomplete';
    field: { candidate_id: string; night: string; ra: number; dec: number; station: string };
    products: { id: string; access_url: string; release: string; t_min: number }[];
    receipts: { collection: string; status: string; url?: string }[];
  }[];
}

interface OpticalPacket {
  kind: 'optical';
  request: { chunks: string[]; start: string; end: string };
  eligible_exposures: number;
  repeat_groups: number;
  receipts: { chunk: string; status: string }[];
  groups: { chunk: string; band: string; nights: number; first_night: string; last_night: string;
    depth_floor_mag: number; exposures: { exposure_id: number; utc: string; ra: number; dec: number; url: string }[] }[];
  limits: string[];
}

interface SearchRun {
  id: string;
  state: 'running' | 'complete' | 'error';
  message: string;
  activity?: string[];
  evidence?: Packet | OpticalPacket;
}

interface TaskDraft {
  chunks: string[];
  start: string | null;
  end: string | null;
  task: 'search' | 'search_followup';
  benchmark: boolean;
}

interface Conversation {
  turns: Turn[];
  draft?: TaskDraft;
  topic?: string;
}

interface Source { label: string; href: string }
interface Turn { role: 'user' | 'agent'; text: string; sources?: Source[]; runId?: string }
interface ChatReply { reply: string; sources?: Source[]; draft?: TaskDraft; space_topic?: string; run?: SearchRun }

const STORAGE_KEY = 'parallax-discovery-run';
const CHAT_STORAGE_KEY = 'parallax-discovery-chat';
const STARTERS = [
  ['Planet Nine', 'What do we know about Planet Nine?', 'question'],
  ['Deep optical images', 'Check DECam for deep optical images.', 'archive'],
  ['Replay NW034', 'Replay NW034 and look for follow-up images.', 'motion'],
] as const;
const secret = /\bsk-(?:proj-|svcacct-)?[\w-]{20,}/;
const files = (id: string, name: string) => `/api/discovery/runs/${id}/files/${name.split('/').map(encodeURIComponent).join('/')}`;
const toArcseconds = (ra: number, dec: number, origin: Observation) => [
  ((ra - origin.ra_deg + 540) % 360 - 180) * Math.cos(origin.dec_deg * Math.PI / 180) * 3600,
  (dec - origin.dec_deg) * 3600,
];
const utc = (mjd: number) => new Date((mjd - 40587) * 86400000).toISOString();
const utcTime = (mjd: number) => utc(mjd).slice(11, 19);

function readConversation(): Conversation {
  try {
    const data = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) ?? 'null');
    if (Array.isArray(data?.turns)) return data;
  } catch { /* Start a fresh conversation when browser storage is unavailable. */ }
  return { turns: [] };
}

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/discovery${path}`, options);
  if (response.ok) return response.json();
  const error = await response.json().catch(() => ({}));
  const message = error.message ?? (typeof error.detail === 'string' ? error.detail : error.detail?.[0]?.msg);
  throw new Error(typeof message === 'string' ? message : 'Aiges couldn’t reach the service. Try again.');
}

function Blink({ runId, frames }: { runId: string; frames: Frame[] }) {
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => setFrame(current => (current + 1) % frames.length), 650);
    return () => window.clearInterval(timer);
  }, [playing, frames.length]);
  const active = frames[frame];
  return <figure className="discovery-blink">
    <div className="discovery-blink__plate">
      {frames.map((item, index) => <img key={item.file} src={files(runId, item.file)}
        alt={`Original exposure cutout at ${item.epoch} UTC`} hidden={index !== frame} />)}
    </div>
    <figcaption>
      <button className="discovery-secondary" type="button" disabled={frames.length < 2} onClick={() => setPlaying(value => !value)}>{playing ? 'Pause' : 'Blink'}</button>
      <button className="discovery-secondary" type="button" disabled={frames.length < 2} onClick={() => {
        setPlaying(false); setFrame(current => (current + 1) % frames.length);
      }}>Next frame</button>
      <a href={active.source_url} target="_blank" rel="noreferrer">Original FITS</a>
      <span>{frame + 1} / {frames.length} · {active.epoch.replace('T', ' ').replace(/Z$/, '')} UTC</span>
    </figcaption>
  </figure>;
}

function ForecastPlot({ rows }: { rows: Observation[] }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const groups = [...new Set(rows.map(row => `${row.night} · ${row.station}`))];
  const [group, setGroup] = useState(groups[0]);
  useEffect(() => {
    const ctx = canvas.current?.getContext('2d');
    const sample = rows.filter(row => `${row.night} · ${row.station}` === group);
    if (!ctx || !sample.length) return;
    const points = sample.map(row => ({
      actual: toArcseconds(row.ra_deg, row.dec_deg, sample[0]),
      predicted: toArcseconds(row.predicted_ra_deg!, row.predicted_dec_deg!, sample[0]),
    }));
    const xs = points.flatMap(p => [p.actual[0], p.predicted[0]]);
    const ys = points.flatMap(p => [p.actual[1], p.predicted[1]]);
    const midX = (Math.max(...xs) + Math.min(...xs)) / 2;
    const midY = (Math.max(...ys) + Math.min(...ys)) / 2;
    const scale = Math.min(496 / Math.max(4, Math.max(...xs) - Math.min(...xs)),
      200 / Math.max(4, Math.max(...ys) - Math.min(...ys)));
    const pixel = (p: number[]) => [342 + (p[0] - midX) * scale, 135 - (p[1] - midY) * scale] as const;
    ctx.fillStyle = '#101112';
    ctx.fillRect(0, 0, 640, 320);
    ctx.lineWidth = 1;
    ctx.strokeStyle = '#424548';
    ctx.strokeRect(59, 12, 566, 246);
    ctx.fillStyle = '#bec4c8';
    ctx.font = '18px system-ui';
    ctx.textAlign = 'center';
    ctx.fillText('East offset (arcsec)', 342, 305);
    ctx.save();
    ctx.translate(22, 135);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('North offset (arcsec)', 0, 0);
    ctx.restore();
    ctx.font = '14px system-ui';
    for (let tick = 0; tick <= 4; tick++) {
      const x = 59 + 566 * tick / 4, y = 12 + 246 * tick / 4;
      ctx.textAlign = 'center';
      ctx.fillText((midX + (x - 342) / scale).toFixed(1), x, 278);
      ctx.textAlign = 'right';
      ctx.fillText((midY + (135 - y) / scale).toFixed(1), 55, y + 5);
    }
    for (const point of points) {
      const actual = pixel(point.actual), expected = pixel(point.predicted);
      ctx.beginPath(); ctx.moveTo(...expected); ctx.lineTo(...actual);
      ctx.strokeStyle = '#9a9da0'; ctx.stroke();
      ctx.beginPath(); ctx.arc(...expected, 7, 0, Math.PI * 2);
      ctx.lineWidth = 2; ctx.strokeStyle = '#8fcdf2'; ctx.stroke();
      ctx.beginPath(); ctx.arc(...actual, 4.5, 0, Math.PI * 2);
      ctx.fillStyle = '#ffc477'; ctx.fill();
    }
  }, [rows, group]);

  return <section className="discovery-section">
    <h3>Predicted and measured positions</h3>
    <label className="discovery-field">Holdout session
      <select value={group} onChange={e => setGroup(e.target.value)}>{groups.map(item => <option key={item}>{item}</option>)}</select>
    </label>
    <p className="discovery-legend"><span>Ring · Predicted</span><span>Dot · Measured</span></p>
    <canvas ref={canvas} width={640} height={320} role="img" aria-label="Predicted and measured positions on east and north axes. Observations appear below." />
  </section>;
}

const catalogLabel: Record<string, string> = {
  known_object: 'Known object',
  known_contamination: 'Known-object contamination',
  partial_match: 'Partial catalog match',
  no_match_in_checked_catalogs: 'No match in the checked catalogs',
  unverified: 'Catalog identification unverified',
};

function Review({ runId, candidate }: { runId: string; candidate: Candidate }) {
  const rows = [...candidate.observations].sort((a, b) => a.mjd_utc - b.mjd_utc);
  const tests = rows.filter(row => row.phase === 'test' && row.predicted_ra_deg != null && row.predicted_dec_deg != null);
  return <>
    <p className="discovery-vet"><strong>{catalogLabel[candidate.catalog.status] ?? 'Catalog status'}{candidate.catalog.name && ` · ${candidate.catalog.name}`}</strong>
      {candidate.catalog.message && <span>{candidate.catalog.message}</span>}
      {candidate.catalog.matched_observations != null && <span>{candidate.catalog.matched_observations} of {candidate.catalog.total_observations} positions match.</span>}
      {candidate.catalog.source_url && <a href={candidate.catalog.source_url} target="_blank" rel="noreferrer">Catalog source</a>}</p>
    <section className="discovery-section">
      <h3>Original exposures</h3>
      {candidate.images.frames.length > 0 && <Blink runId={runId} frames={candidate.images.frames} />}
      {candidate.images.combined_snr != null && <p>Combined signal-to-noise · {candidate.images.combined_snr.toFixed(2)}</p>}
      <p>{candidate.images.message || 'Usable original images have not been verified for this linkage.'}</p>
      {candidate.images.coverage.map(item => <p key={item.source_url}><a href={item.source_url} target="_blank" rel="noreferrer">{item.night} archive</a> · {item.message}</p>)}
    </section>
    {tests.length > 0 && <ForecastPlot rows={tests} />}
    <section className="discovery-section">
      <h3>Observation timeline</h3>
      {candidate.orbit.rms_arcsec != null && candidate.arc_days != null &&
        <p>{candidate.arc_days.toFixed(2)} day arc · Final fit RMS {candidate.orbit.rms_arcsec.toFixed(3)}″</p>}
      <p>Holdout offsets use the orbit frozen before those observations were included in the final fit.</p>
      <div className="discovery-table" tabIndex={0} role="region" aria-label="Observation timeline table">
        <table>
          <thead><tr><th scope="col">Date and time UTC</th><th scope="col">Site</th><th scope="col">Role</th><th scope="col">Offset</th></tr></thead>
          <tbody>{rows.map(row => <tr key={`${row.line_sha256}-${row.phase}`}>
            <td>{row.night} <small>{utcTime(row.mjd_utc)}</small></td><td>{row.station}</td>
            <td>{row.phase === 'test' ? 'Holdout' : 'Fit'}</td>
            <td>{row.residual_arcsec != null ? `${row.residual_arcsec.toFixed(2)}″` : '—'}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>
  </>;
}

const followupStatus = {
  found: 'Possible exposures found',
  no_results: 'No matching metadata in the checked releases',
  incomplete: 'Some archive queries could not be completed',
  no_predictions: 'The search found no held-out prediction to check',
};

function FollowupReport({ result }: { result: Followup }) {
  return <section className="discovery-section">
    <h3>SPHEREx follow-up</h3>
    <p>{followupStatus[result.status]}.</p>
    {result.checks.length > 0 && <p>Archive footprints within {result.radius_arcmin}′ and ±{Math.round(result.margin_minutes)} minutes of a fixed prediction.
      {result.status === 'found' && ' Inspect the original FITS data to check for the object.'}</p>}
    {result.checks.map(check => <div className="discovery-followup-check" key={check.field.night}>
      <h4>{check.field.candidate_id} · {check.field.night} UTC</h4>
      <p>RA {check.field.ra.toFixed(4)}°, Dec {check.field.dec.toFixed(4)}° · Prediction from {check.field.station}</p>
      <p>{followupStatus[check.status]}.</p>
      {check.receipts.map(receipt => <p key={receipt.collection}>
        {receipt.url ? <a href={receipt.url} target="_blank" rel="noreferrer">{receipt.collection}</a> : receipt.collection} · {receipt.status}
      </p>)}
      {check.products.length > 0 && <ul>{check.products.map(product => <li key={product.id}>
        <a href={product.access_url} target="_blank" rel="noreferrer">{product.id} FITS</a>
        <span> · {product.release} · {utc(product.t_min).slice(0, 16).replace('T', ' ')} UTC</span>
      </li>)}</ul>}
    </div>)}
  </section>;
}

function OpticalReport({ packet }: { packet: OpticalPacket }) {
  const failed = packet.receipts.every(item => item.status === 'unavailable');
  const partial = packet.receipts.some(item => item.status !== 'complete');
  return <div className="discovery-section">
    <h3>{failed ? 'NOIRLab was unavailable' : `${packet.eligible_exposures} DECam exposures • ${packet.repeat_groups} repeat-night groups`}</h3>
    <p>{packet.request.chunks.join(' and ')} · {packet.request.start} to {packet.request.end} UTC</p>
    {partial && <p>Coverage is incomplete for this request.</p>}
    <ul className="discovery-optical-list">
      {packet.groups.slice(0, 3).map((group, index) => <li key={index}>
        <strong>{group.chunk} · {group.band} band · {group.nights} {group.nights === 1 ? 'night' : 'nights'}</strong>
        <p>RA {group.exposures[0].ra.toFixed(3)}°, Dec {group.exposures[0].dec.toFixed(3)}°</p>
        <p>{group.first_night} to {group.last_night} · Reported depth ≥ {group.depth_floor_mag.toFixed(1)} mag</p>
        <a href={group.exposures[0].url} target="_blank" rel="noreferrer">NOIRLab exposure {group.exposures[0].exposure_id}</a>
      </li>)}
    </ul>
    <p>Next test: verify the CCD coverage and recover simulated objects in those images.</p>
    <details className="discovery-activity">
      <summary>Coverage and limits</summary>
      <ul>{packet.receipts.map(item => <li key={item.chunk}>{item.chunk} · {item.status}</li>)}
        {packet.limits.map(limit => <li key={limit}>{limit}</li>)}</ul>
    </details>
  </div>;
}

function RunReport({ run }: { run: SearchRun }) {
  const packet = run.evidence;
  const linkage = packet?.kind !== 'optical' ? packet : undefined;
  const [selected, setSelected] = useState('');
  const candidate = linkage?.candidates.find(item => item.id === selected) ?? linkage?.candidates[0];
  const running = run.state === 'running';
  return <section className="discovery-run" aria-label="Research run">
    <div className="discovery-run__label">
      <span className="discovery-run__dot" data-state={run.state} />
      <strong>{running ? 'Research in progress' : run.state === 'error' ? 'Research interrupted' : 'Evidence ready'}</strong>
      {packet && <a href={files(run.id, 'evidence.zip')} download>Download packet</a>}
    </div>
    <a className="discovery-run__link" href={`/map?agent=1&run=${encodeURIComponent(run.id)}`}>Run link</a>
    {(running || run.state === 'error') && <p role={running ? 'status' : 'alert'}>{run.message}</p>}
    {!!run.activity?.length && <details className="discovery-activity">
      <summary>Work log</summary>
      <ol>{run.activity.map((item, index) => <li key={index}>{item}</li>)}</ol>
    </details>}
    {packet?.kind === 'optical' && <OpticalReport packet={packet} />}
    {linkage && <>
      <p>{linkage.request.benchmark ? 'NW034 replay' : linkage.request.chunks?.join(' and ')} · {linkage.request.start} to {linkage.request.end}</p>
      <details className="discovery-evidence">
        <summary>{linkage.candidates.length} {linkage.candidates.length === 1 ? 'ranked linkage' : 'ranked linkages'}</summary>
        {linkage.followup && <FollowupReport result={linkage.followup} />}
        {candidate ? <>
          <label className="discovery-field">Review candidate
            <select value={candidate.id} onChange={event => setSelected(event.target.value)}>
              {linkage.candidates.map((item, index) => <option key={item.id} value={item.id}>
                {index + 1}. {item.display_label ?? item.id} · {item.observations.length} observations
              </option>)}
            </select>
          </label>
          <Review key={candidate.id} candidate={candidate} runId={run.id} />
        </> : <p>No linkages passed the orbit checks in this snapshot and date range.</p>}
      </details>
    </>}
  </section>;
}

function StarterIcon({ kind }: { kind: typeof STARTERS[number][2] }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    {kind === 'question' ? <><circle cx="12" cy="12" r="5" /><path d="M4 14c-2 3 0 4 3 3s8-4 12-7 2-5-2-3" /></>
      : kind === 'archive' ? <><rect x="5" y="4" width="14" height="16" rx="2" /><path d="M9 9h6M9 13h6M9 17h3" /></>
      : <><circle cx="7" cy="16" r="2" /><circle cx="17" cy="7" r="2" /><path d="M9 14.5 15.5 9M4 20l.5-.5M20 4l.5-.5" /></>}
  </svg>;
}

const safeSource = (href: string) => /^https:\/\//i.test(href) || /^\/(?!\/)/.test(href);

export function DiscoveryPanel({ initialChunk, onClose }: { initialChunk: string; onClose: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const utterance = useRef<SpeechSynthesisUtterance>();
  const sending = useRef(false);
  const [chat, setChat] = useState(readConversation);
  const [message, setMessage] = useState('');
  const [runId, setRunId] = useState(() => {
    const requested = new URLSearchParams(window.location.search).get('run');
    if (requested && /^[a-f0-9]{32}$/.test(requested)) return requested;
    try { return localStorage.getItem(STORAGE_KEY); } catch { return null; }
  });
  const [run, setRun] = useState<SearchRun>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [speaking, setSpeaking] = useState<number | null>(null);
  const currentRun = run?.id === runId ? run : undefined;
  const canSpeak = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;

  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
    return () => { if (utterance.current) window.speechSynthesis.cancel(); };
  }, []);

  useEffect(() => {
    try { localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(chat)); } catch { /* Browser storage is optional. */ }
  }, [chat]);

  useEffect(() => {
    const el = body.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [chat.turns, submitting]);

  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    let timer: number | undefined;
    let failures = 0;
    const refresh = async () => {
      try {
        const next = await api<SearchRun>(`/runs/${encodeURIComponent(runId)}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        failures = 0;
        setRun(next);
        if (next.state === 'running') timer = window.setTimeout(refresh, 1800);
      } catch (cause) {
        if (controller.signal.aborted) return;
        if (++failures < 3) timer = window.setTimeout(refresh, 2400);
        else setRun({ id: runId, state: 'error', message: cause instanceof Error ? cause.message : 'Couldn’t load this run.' });
      }
    };
    void refresh();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [runId]);

  function openRun(id: string) {
    setRunId(id);
    try { localStorage.setItem(STORAGE_KEY, id); } catch { /* The run stays available in this view. */ }
  }

  function readAloud(index: number, text: string) {
    if (!canSpeak) return;
    window.speechSynthesis.cancel();
    if (speaking === index) {
      utterance.current = undefined;
      setSpeaking(null);
      return;
    }
    const next = new SpeechSynthesisUtterance(text);
    next.lang = 'en-US';
    next.onend = next.onerror = () => {
      if (utterance.current === next) {
        utterance.current = undefined;
        setSpeaking(null);
      }
    };
    utterance.current = next;
    setSpeaking(index);
    window.speechSynthesis.speak(next);
  }

  async function send(raw: string) {
    const text = raw.trim();
    if (!text || sending.current) return;
    if (secret.test(text)) { setError('Remove the API key before sending.'); return; }
    const userTurn = { role: 'user' as const, text };
    const recent = chat.turns.slice(-8).map(turn => ({ role: turn.role, text: turn.text.slice(0, 2200) }));
    setError('');
    sending.current = true;
    setSubmitting(true);
    setMessage('');
    setChat(current => ({ ...current, turns: [...current.turns, userTurn].slice(-32) }));
    try {
      const next = await api<ChatReply>('/tasks', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, draft: chat.draft, previous_run: runId ?? undefined,
          map_chunk: initialChunk || undefined, history: recent, space_topic: chat.topic }),
      });
      setChat(current => ({
        turns: [...current.turns, { role: 'agent' as const, text: next.reply, sources: next.sources, runId: next.run?.id }].slice(-32),
        draft: next.draft, topic: next.space_topic || current.topic,
      }));
      if (next.run?.id) {
        setRun(next.run);
        openRun(next.run.id);
      }
    } catch (cause) {
      setChat(current => ({ ...current, turns: current.turns.filter(turn => turn !== userTurn) }));
      setMessage(current => current || text);
      setError(cause instanceof Error ? cause.message : 'Couldn’t send your message.');
    } finally {
      sending.current = false;
      setSubmitting(false);
    }
  }

  const linkedRun = chat.turns.some(turn => turn.runId === runId);
  return <aside className="gm-card discovery-panel" aria-labelledby="discovery-heading" onKeyDown={event => {
    if (event.key === 'Escape') { event.stopPropagation(); onClose(); }
  }}>
    <header className="discovery-header">
      <div className="discovery-header__mark"><Mark size={22} /></div>
      <div className="discovery-header__title">
        <h2 id="discovery-heading" ref={heading} tabIndex={-1}>Aiges</h2>
        <p>Astronomy research</p>
      </div>
      {initialChunk && <span className="discovery-context">Chunk {initialChunk}</span>}
      <button className="gm-ic discovery-close" type="button" aria-label="Close Aiges" onClick={onClose}>
        <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="m6 6 12 12M18 6 6 18" /></svg>
      </button>
    </header>
    <div className="discovery-scroll" ref={body}>
      {!chat.turns.length && <div className="discovery-start">
        <h3>What are you curious about?</h3>
        <p>Ask about space, find a paper, or investigate a patch of sky.</p>
        <div className="discovery-starters">
          {STARTERS.map(([label, example, icon]) => <button type="button" key={label} disabled={submitting} onClick={() => void send(example)}>
            <StarterIcon kind={icon} /><span>{label}</span>
            <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M6 12h12m-5-5 5 5-5 5" /></svg>
          </button>)}
        </div>
      </div>}
      <div role="log" aria-label="Conversation with Aiges" className="discovery-conversation">
        {chat.turns.map((turn, index) => <div className="discovery-turn" data-role={turn.role} key={index}>
          <p className="discovery-message"><span className="visually-hidden">{turn.role === 'user' ? 'You: ' : 'Aiges: '}</span>{turn.text}</p>
          {!!turn.sources?.length && <ul className="discovery-sources" aria-label="Sources">
            {turn.sources.filter(item => safeSource(item.href)).map((item, n) => <li key={item.href}>
              <a href={item.href} target={item.href.startsWith('/') ? undefined : '_blank'} rel="noreferrer">
                <span>{n + 1}</span>{item.label}
              </a>
            </li>)}
          </ul>}
          {turn.runId && (turn.runId === runId && currentRun
            ? <RunReport key={currentRun.id} run={currentRun} />
            : <button className="discovery-secondary" type="button" onClick={() => openRun(turn.runId!)}>Open research run</button>)}
          {turn.role === 'agent' && canSpeak && <button type="button" className="discovery-listen" aria-label={speaking === index ? 'Stop reading aloud' : 'Read reply aloud'} onClick={() => readAloud(index, turn.text)}>
            <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 9h4l5-4v14l-5-4H4zM16 9a4 4 0 0 1 0 6m2-9a8 8 0 0 1 0 12" />
            </svg>
            {speaking === index ? 'Stop reading' : 'Listen'}
          </button>}
        </div>)}
        {submitting && <p className="discovery-pending" role="status"><span />Aiges is working on your message</p>}
      </div>
      {currentRun && !linkedRun && <RunReport key={currentRun.id} run={currentRun} />}
    </div>
    <form className="discovery-composer" onSubmit={(event: FormEvent) => { event.preventDefault(); void send(message); }}>
      {error && <p className="discovery-error" role="alert">{error}</p>}
      <div className="discovery-composer__input">
        <label className="visually-hidden" htmlFor="aiges-input">Message Aiges</label>
        <textarea id="aiges-input" ref={composer} value={message} maxLength={1600} rows={2}
          placeholder="Ask Aiges or describe a search…"
          onChange={event => setMessage(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault(); void send(message);
            }
          }} />
        <button className="discovery-send" type="submit" disabled={submitting || !message.trim()} aria-label="Send message">
          <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 19V5m-5 5 5-5 5 5" /></svg>
        </button>
      </div>
    </form>
  </aside>;
}
