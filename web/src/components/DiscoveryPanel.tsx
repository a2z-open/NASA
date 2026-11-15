import { useEffect, useRef, useState, type FormEvent } from 'react';
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
  candidates: Candidate[];
  request: { benchmark: boolean; start: string; end: string; chunks?: string[] };
  planner: { status: string; model?: string; requested_model?: string; reason?: string; failure?: string; order: string[] };
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

interface Settings {
  archive_ready: boolean;
  planner_ready: boolean;
  planner_default_model: string;
  planner_models: Record<string, string>;
}

interface SearchRun {
  id: string;
  state: 'running' | 'complete' | 'error';
  message: string;
  activity?: string[];
  evidence?: Packet;
}

interface TaskDraft {
  chunks: string[];
  start: string | null;
  end: string | null;
  task: 'search' | 'search_followup';
  benchmark: boolean;
}

interface Conversation {
  turns: { role: 'user' | 'agent'; text: string }[];
  draft?: TaskDraft;
}

const STORAGE_KEY = 'parallax-discovery-run';
const CHAT_STORAGE_KEY = 'parallax-discovery-chat';
const REPLAY_EXAMPLE = 'Replay NW034 and look for follow-up images.';
const plannerFailures: Record<string, string> = {
  authentication: 'OpenAI rejected the server credential.',
  model_access: 'OpenAI did not grant this project access to the selected model.',
  rate_limit: 'OpenAI reported a request or quota limit.',
};
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
  const message = error.message ?? error.detail?.[0]?.msg;
  throw new Error(typeof message === 'string' ? message : 'The search service is unavailable.');
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

export function DiscoveryPanel({ initialChunk, onClose }: { initialChunk: string; onClose: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null);
  const recentTurn = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const [chat, setChat] = useState(readConversation);
  const [message, setMessage] = useState('');
  const [settings, setSettings] = useState<Settings>();
  const [plannerModel, setPlannerModel] = useState<string>();
  const [runId, setRunId] = useState(() => localStorage.getItem(STORAGE_KEY));
  const [run, setRun] = useState<SearchRun>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState('');
  const pending = submitting || (!!runId && (!run || run.state === 'running'));
  const candidate = run?.evidence?.candidates.find(item => item.id === selected) ?? run?.evidence?.candidates[0];
  const planner = run?.evidence?.planner;
  const activity = run?.activity ?? run?.evidence?.activity ?? [];
  const modelLabel = (id: string) => settings?.planner_models[id] ?? id;

  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
    const controller = new AbortController();
    api<Settings>('/settings', { signal: controller.signal }).then(setSettings).catch(cause => {
      if (!controller.signal.aborted) setError(cause.message);
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (chat.turns.length) recentTurn.current?.scrollIntoView({ block: 'nearest' });
    try { localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(chat)); } catch { /* Keep this session usable. */ }
  }, [chat]);

  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    let timer: number | undefined;
    const refresh = async () => {
      try {
        const next = await api<SearchRun>(`/runs/${encodeURIComponent(runId)}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setRun(next);
        if (next.state === 'running') timer = window.setTimeout(refresh, 1800);
      } catch (cause) {
        if (controller.signal.aborted) return;
        setRun({ id: runId, state: 'error', message: cause instanceof Error ? cause.message : 'Couldn’t load the search run.' });
      }
    };
    void refresh();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [runId]);

  async function send(raw: string) {
    setError('');
    const text = raw.trim();
    if (!text || pending) return;
    setSubmitting(true);
    try {
      const request = { message: text, draft: chat.draft, previous_run: runId ?? undefined,
        map_chunk: initialChunk || undefined, planner_model: plannerModel };
      const next = await api<{ reply: string; draft?: TaskDraft; run?: SearchRun }>('/tasks', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request),
      });
      setChat(current => ({
        turns: [...current.turns, { role: 'user' as const, text }, { role: 'agent' as const, text: next.reply }].slice(-16),
        draft: next.draft,
      }));
      setMessage('');
      if (next.run) {
        localStorage.setItem(STORAGE_KEY, next.run.id);
        setSelected('');
        setRun(next.run);
        setRunId(next.run.id);
      } else {
        window.requestAnimationFrame(() => composer.current?.focus());
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Couldn’t send the task.');
    } finally {
      setSubmitting(false);
    }
  }

  return <aside className="gm-card discovery-panel" aria-labelledby="discovery-heading" onKeyDown={event => {
    if (event.key === 'Escape') onClose();
  }}>
    <div className="gm-list__hd">
      <h2 id="discovery-heading" ref={heading} tabIndex={-1}>Search agent</h2>
      <button type="button" className="gm-ic" aria-label="Close search agent" onClick={onClose}>
        <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="m6 6 12 12M18 6 6 18" /></svg>
      </button>
    </div>
    <div className="gm-card__scroll discovery-scroll">
      {!chat.turns.length && <div className="discovery-start">
        <p>Tell me which chunks and dates to search. I can look for moving objects or check archived images near a saved prediction.</p>
        <button className="discovery-secondary" type="button" disabled={pending || !settings?.archive_ready}
          onClick={() => void send(REPLAY_EXAMPLE)}>Replay NW034 with follow-up</button>
      </div>}
      <div role="log" aria-label="Task conversation" className="discovery-conversation">
        {chat.turns.map((turn, index) => <p className="discovery-message" data-role={turn.role} key={index}>
          <span className="visually-hidden">{turn.role === 'user' ? 'You' : 'Search agent'} </span>{turn.text}
        </p>)}
        <div ref={recentTurn} />
      </div>
      {settings?.archive_ready === false && <p role="alert">This server needs the MPC snapshot and HelioLinC3D tools to start a new search.</p>}
      {(pending || run?.state === 'error') && <p className="discovery-progress" role={run?.state === 'error' ? 'alert' : 'status'}>{submitting ? 'Reading the task…' : run?.message ?? 'Loading search…'}</p>}
      {activity.length > 0 && <details className="discovery-activity" open={pending}>
        <summary>Work log</summary>
        <ol>{activity.map((item, index) => <li key={index}>{item}</li>)}</ol>
      </details>}
      {runId && run?.evidence && <section className="discovery-results">
        <div className="discovery-results__head">
          <h3>{run.evidence.candidates.length} ranked linkages</h3>
          <a href={files(runId, 'evidence.zip')} download>Download evidence</a>
        </div>
        <p>{run.evidence.request.benchmark ? 'NW034 replay' : run.evidence.request.chunks?.join(' and ')} · {run.evidence.request.start} to {run.evidence.request.end}</p>
        {planner?.status === 'used' && <p>{planner.model ? modelLabel(planner.model) : 'OpenAI planner'} · {planner.reason}</p>}
        {planner?.status === 'fallback' && <p>{plannerFailures[planner.failure ?? ''] ?? 'The planner was unavailable.'} The search used the fixed evidence order.</p>}
        {planner?.status === 'unconfigured' && planner.requested_model && <p>Requested {modelLabel(planner.requested_model)} · Fixed evidence order used</p>}
        {run.evidence.followup && <FollowupReport result={run.evidence.followup} />}
        {candidate ? <>
          <label className="discovery-field">Review candidate
            <select value={candidate.id} onChange={event => setSelected(event.target.value)}>
              {run.evidence.candidates.map((item, index) => <option key={item.id} value={item.id}>
                {index + 1}. {item.display_label ?? item.id} · {item.observations.length} observations
              </option>)}
            </select>
          </label>
          <Review key={`${runId}/${candidate.id}`} candidate={candidate} runId={runId} />
        </> : <p>No linkages passed the orbit checks in this archive snapshot and date range.</p>}
      </section>}
    </div>
    <form className="discovery-composer" onSubmit={(event: FormEvent) => { event.preventDefault(); void send(message); }}>
      <label className="discovery-field">Describe the task
        <textarea ref={composer} value={message} maxLength={800} rows={3}
          placeholder="Search H-02 and H-03 from Oct 20 to Nov 13, 2026, and look for follow-up images."
          onChange={event => setMessage(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              void send(message);
            }
          }} />
      </label>
      {error && <p className="discovery-error" role="alert">{error}</p>}
      <div className="discovery-composer__actions">
        {settings && <label className="discovery-field">
          <span className="visually-hidden">Planner model</span>
          <select value={plannerModel ?? ''} disabled={pending} aria-describedby="discovery-planner-status"
            onChange={event => setPlannerModel(event.target.value || undefined)}>
            <option value="">{modelLabel(settings.planner_default_model)} (default)</option>
            {Object.entries(settings.planner_models).filter(([id]) => id !== settings.planner_default_model)
              .map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>}
        <button className="gm-btn" type="submit" disabled={pending || !message.trim()}>Send task</button>
      </div>
      {settings && <p id="discovery-planner-status" className="discovery-mode">{settings.planner_ready
        ? 'The model chooses which evidence to check first.'
        : 'The server uses a fixed evidence order until a key is configured.'}</p>}
    </form>
  </aside>;
}
