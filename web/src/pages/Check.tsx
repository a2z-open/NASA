import { useEffect, useMemo, useState } from 'react';
import { Page } from '../components/Shell.tsx';
import { Link } from '../router.tsx';

type Answer = 'dips' | 'smooth' | 'unsure';
interface Bin { um: number; ujy: number; err: number }
interface Item { id: string; kind: 'known' | 'unknown'; snr: number; ra: number; dec: number; spectrum: Bin[]; votes: number; flagged?: boolean }
interface Queue { question: string; reference: { cold: { um: number; v: number }[]; warm: { um: number; v: number }[] }; bands_um: [number, number][]; note: string; items: Item[]; total_votes: number }
interface Reply {
  id: string; tally: { dips: number; smooth: number; unsure: number; n: number }; kind: 'known' | 'unknown'; name: string; truth: Answer | null; truth_label: string | null;
  model: { type: string; p_T: number } | null; flagged: boolean; first_spectrum?: boolean; agrees_with_known: boolean | null;
}

const LABEL: Record<Answer, string> = { dips: 'Yes, it goes dark', smooth: 'No, it stays bright', unsure: "Can't tell" };
const store = {
  get: (k: string) => { try { return window.localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string) => { try { window.localStorage.setItem(k, v); } catch { /* private window: fine */ } },
};

/** Scale a reference shape to the object's spectrum (least squares, weighted by the errors). */
function fit(ref: { um: number; v: number }[], s: Bin[]) {
  let a = 0, b = 0;
  const at = new Map(ref.map(r => [r.um, r.v]));
  for (const p of s) { const v = at.get(p.um); if (v == null) continue; const w = 1 / Math.max(p.err, 1) ** 2; a += w * v * p.ujy; b += w * v * v; }
  const k = b > 0 ? a / b : 0;
  return ref.map(r => ({ um: r.um, y: r.v * k }));
}

function Spectrum({ s: raw, q }: { s: Bin[]; q: Queue }) {
  const s = useMemo(() => raw.filter(p => p.ujy > -4 * p.err), [raw]);      // a flux far below zero is a corrupted band: not drawn
  const w = 760, h = 340, m = { l: 14, r: 14, t: 34, b: 34 };
  const cold = useMemo(() => fit(q.reference.cold, s), [q, s]);
  const warm = useMemo(() => fit(q.reference.warm, s), [q, s]);
  const top = Math.max(...s.map(p => p.ujy + p.err), ...cold.map(p => p.y), ...warm.map(p => p.y)) * 1.06;
  const bot = Math.min(0, ...s.map(p => p.ujy - p.err));
  const sx = (um: number) => m.l + ((um - 0.75) / (5 - 0.75)) * (w - m.l - m.r);
  const sy = (v: number) => h - m.b - ((v - bot) / (top - bot || 1)) * (h - m.t - m.b);
  const line = (pts: { um: number; y: number }[]) => pts.map(p => `${sx(p.um).toFixed(1)},${sy(p.y).toFixed(1)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="The object's brightness at each infrared colour from 0.75 to 5 microns. Two grey bands mark where methane absorbs light.">
      {q.bands_um.map(([a, b]) => (
        <g key={a}>
          <rect x={sx(a)} y={m.t} width={sx(b) - sx(a)} height={h - m.t - m.b} fill="rgba(245,245,247,0.13)" />
          <text x={(sx(a) + sx(b)) / 2} y={m.t - 10} textAnchor="middle" className="ck-ax ck-ax--b">METHANE</text>
        </g>
      ))}
      <line x1={m.l} x2={w - m.r} y1={sy(0)} y2={sy(0)} stroke="rgba(245,245,247,0.3)" />
      <polyline points={line(warm)} fill="none" stroke="rgba(245,245,247,0.5)" strokeWidth={1.4} strokeDasharray="2 5" />
      <polyline points={line(cold)} fill="none" stroke="rgba(245,245,247,0.6)" strokeWidth={1.4} strokeDasharray="9 6" />
      {s.map((p, i) => <line key={'e' + i} x1={sx(p.um)} x2={sx(p.um)} y1={sy(p.ujy - p.err)} y2={sy(p.ujy + p.err)} stroke="rgba(245,245,247,0.55)" />)}
      <polyline points={line(s.map(p => ({ um: p.um, y: p.ujy })))} fill="none" stroke="#f5f5f7" strokeWidth={2.2} />
      {s.map((p, i) => <circle key={i} cx={sx(p.um)} cy={sy(p.ujy)} r={3.4} fill="#f5f5f7" />)}
      {[1, 2, 3, 4, 5].map(v => <text key={v} x={sx(v)} y={h - 10} textAnchor="middle" className="ck-ax">{v} µm</text>)}
    </svg>
  );
}

/** Check a candidate: one real SPHEREx spectrum, one question. Known objects give feedback; unknown ones are the real task. */
export function Check() {
  const [q, setQ] = useState<Queue | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [i, setI] = useState(0);
  const [reply, setReply] = useState<Reply | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState(() => store.get('parallax.name') ?? '');
  const [score, setScore] = useState({ checked: 0, knownRight: 0, knownSeen: 0, unknown: 0 });

  useEffect(() => {
    fetch('/api/check').then(async r => (r.ok ? r.json() : Promise.reject(new Error((await r.json()).message ?? 'Not available')))).then(setQ).catch(e => setErr(String(e.message ?? e)));
  }, []);

  async function answer(a: Answer) {
    if (!q || busy || reply) return;
    setBusy(true);
    try {
      const r = await fetch('/api/check', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: q.items[i].id, answer: a, name: name.trim() || undefined }) });
      if (!r.ok) throw new Error((await r.json()).message ?? 'Could not save');
      const d: Reply = await r.json();
      setReply(d);
      setScore(s => ({ checked: s.checked + 1, knownRight: s.knownRight + (d.agrees_with_known ? 1 : 0), knownSeen: s.knownSeen + (d.agrees_with_known != null ? 1 : 0), unknown: s.unknown + (d.kind === 'unknown' ? 1 : 0) }));
    } catch (e) { setErr(String((e as Error).message)); } finally { setBusy(false); }
  }
  const next = () => { setReply(null); setI(v => v + 1); };

  const done = q != null && i >= q.items.length;
  const item = q && !done ? q.items[i] : null;

  return (
    <Page>
      <div className="ck">
        <header className="ck-head">
          <p className="eyebrow-x">Check a candidate</p>
          <h1 className="h-sec">Is this a cold world?</h1>
          <p className="lede-x">Real objects, real NASA SPHEREx data. Methane swallows the light of a cold world at two infrared colours. Look at the two grey bands and tell us what you see.</p>
        </header>

        {err && <p className="ck-msg" role="alert">{err}</p>}
        {!q && !err && <p className="ck-msg">Loading objects…</p>}

        {item && q && (
          <div className="ck-main">
            <section className="ck-card" aria-label={`Object ${i + 1} of ${q.items.length}`}>
              <div className="ck-top">
                <span className="eyebrow-x">Object {i + 1} of {q.items.length}</span>
                <span className="ck-legend"><i className="ck-l ck-l--obj" />this object <i className="ck-l ck-l--cold" />a cold world <i className="ck-l ck-l--warm" />a star</span>
              </div>
              <Spectrum s={item.spectrum} q={q} />
              {!reply ? (
                <>
                  <h2 className="ck-q">{q.question}</h2>
                  <div className="ck-btns">
                    <button type="button" className="pill pill--solid" disabled={busy} onClick={() => answer('dips')}>{LABEL.dips}</button>
                    <button type="button" className="pill pill--line" disabled={busy} onClick={() => answer('smooth')}>{LABEL.smooth}</button>
                    <button type="button" className="pill pill--quiet" disabled={busy} onClick={() => answer('unsure')}>{LABEL.unsure}</button>
                  </div>
                </>
              ) : (
                <div className="ck-reply" role="status">
                  <h2 className="ck-q">
                    {reply.kind === 'known'
                      ? reply.agrees_with_known === true ? 'You agree with the astronomers.' : reply.agrees_with_known === false ? 'Astronomers see it differently.' : 'Here is what astronomers say.'
                      : 'Saved. Nobody knows the answer yet.'}
                  </h2>
                  <p>
                    <strong>{reply.name}</strong>{' '}
                    {reply.kind === 'known' ? <>is {reply.truth_label}.</> : reply.first_spectrum ? <>was picked out by another survey from its colours alone. We found no published spectrum of it. Our model flagged it as a cold world.</> : <>has no spectral type in the catalogues. {reply.flagged ? 'Our model flagged it as a possible cold world.' : ''}</>}
                    {reply.model && <> Our model reads it as type {reply.model.type}, {Math.round(reply.model.p_T * 100)}% likely a methane dwarf.</>}
                  </p>
                  <p className="ck-tally">
                    {reply.tally.n === 1 ? 'You are the first person to check this one.' : `${reply.tally.n} people have checked this one: ${reply.tally.dips} said it goes dark, ${reply.tally.smooth} said it stays bright, ${reply.tally.unsure} could not tell.`}
                  </p>
                  <div className="ck-btns">
                    <button type="button" className="pill pill--solid" onClick={next}>{i + 1 < q.items.length ? 'Next object' : 'Finish'}</button>
                    <Link className="pill pill--line" href={`/map?ra=${item.ra.toFixed(5)}&dec=${item.dec.toFixed(5)}&fov=0.5`}>See it on the sky map</Link>
                  </div>
                </div>
              )}
            </section>

            <aside className="ck-side">
              <div className="ck-stat"><b>{score.checked}</b><span>objects you checked</span></div>
              <div className="ck-stat"><b>{score.knownSeen ? `${score.knownRight} of ${score.knownSeen}` : '—'}</b><span>times you agreed with astronomers, on objects they have already typed</span></div>
              <div className="ck-stat"><b>{score.unknown}</b><span>of your checks were on objects nobody has typed</span></div>
              <label className="ck-name">
                <span>Your first name, to credit your checks (optional)</span>
                <input value={name} maxLength={24} onChange={e => { setName(e.target.value); store.set('parallax.name', e.target.value); }} placeholder="Anonymous" autoComplete="given-name" />
              </label>
              <p className="ck-fine">A check is one person's opinion on a real object. Several checks that agree tell us which candidates deserve a proper telescope spectrum first. It does not confirm a discovery.</p>
            </aside>
          </div>
        )}

        {done && q && (
          <section className="ck-card ck-done">
            <h2 className="h-sec">Thank you.</h2>
            <p className="lede-x" style={{ marginLeft: 0 }}>You checked {score.checked} real objects{score.knownSeen ? ` and agreed with astronomers on ${score.knownRight} of ${score.knownSeen} that already have a type` : ''}. {score.unknown} of them had never been typed. Your answers are saved with everyone else's.</p>
            <div className="ck-btns">
              <Link className="pill pill--solid" href="/hunt">See what the search found</Link>
              <button type="button" className="pill pill--line" onClick={() => { setI(0); setReply(null); }}>Go again</button>
            </div>
          </section>
        )}
        {q && <p className="ck-fine ck-fine--foot">{q.note} {q.total_votes > 0 ? `${q.total_votes.toLocaleString('en-US')} checks recorded so far.` : ''}</p>}
      </div>
    </Page>
  );
}
