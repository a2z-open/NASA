import { useEffect, useState } from 'react';
import { Link } from '../router.tsx';

interface Stat { rms_subtypes: number; median_abs_subtypes: number; rms_M: number; rms_L: number; rms_T: number; auc_T: number; T_found: number; T_total: number; false_T: number; not_T_total: number }
interface Point { name: string; sp_type: string; true: number; pred: number; p_T: number; snr_J: number }
interface Cv { n_used: number; by_class: { M: number; L: number; T: number }; threshold_p_T: number; held_out: Stat; held_out_faint: Stat; baseline_methane_index_auc: number; points: Point[] }
interface Cand {
  name: string; ra: number; dec: number; J: number; pred_type: string; p_T: number; snr_J: number; verdict: string; pm_arcsec_yr: number;
  simbad_types: { sptype: string; bibcode: string }[]; wise: { W1_W2: number | null; W2: number | null } | null; spectrum: { um: number; ujy: number; err: number }[];
}
interface Res { n_unclassified: number; n_pass_quality: number; n_outliers: number; n_typed: number; typed_by_class: Record<string, number>; n_candidates: number; candidates: Cand[]; n_new_wise_agrees: number; caveat: string }
interface Vet {
  n_with_published_type: number; published_T: number; published_T_flagged: number; published_not_T: number; published_not_T_flagged: number; n_new_candidates: number;
  candidates: { name: string; model_type: string; p_T: number; published_type: string | null; published_name: string | null; verdict: string }[];
  matches: { name: string; published_type: string; model_type: string; flagged: boolean }[];
}
interface Quality { scatter_passing_cuts_dex: number; n_passing: number; wise_check: { scatter_dex: number; n: number } | null }
interface WideFlag {
  oid: string; name: string; group: string; cite: string; ra: number; dec: number; J: number; phot_type: string | null; snr_J: number; pred_type: string; p_T: number;
  wise: { W1_W2: number | null } | null; spectrum: Cand['spectrum']; published_type: string | null; published_in: string | null; published_name: string | null; verdict: string;
}
interface Graded extends WideFlag { methane_1p7: number; methane_3p3: number; grade: 'strong' | 'likely'; in_simbad: boolean }
interface Wide {
  n_objects: number; n_spectra: number; n_pass_quality: number; n_flagged: number;
  candidates: { n: number; n_strong: number; candidates: Graded[]; what_it_is: string; limits: { methane_1p7_warm_1st_percentile: number; methane_3p3_warm_1st_percentile: number } } | null;
  other_telescopes?: { n: number; n_agree: number; n_moves: number; rules: Record<string, string>;
    candidates: { name: string; agrees: boolean; n_pass: number; n_tests: number; tests: Record<string, { pass: boolean; value: number; error: number | null; data: string }>;
      hubble_or_jwst?: { name: string; n: number }[] }[] } | null;
  vetting: {
    flagged: WideFlag[]; n_already_typed: number; n_doubtful: number; n_no_published_spectrum: number; caveat: string; references: string[];
    blind_test: { n_with_published_type: number; type_median_abs_subtypes: number | null; published_T: number; published_T_flagged: number; published_not_T: number; published_not_T_flagged: number };
  };
}
interface Doc { cv: Cv; results: Res | null; protocol: { locked_utc: string } | null; vetting: Vet | null; quality: Quality | null; wide: Wide | null }

const TICKS: [number, string][] = [[0, 'M0'], [5, 'M5'], [10, 'L0'], [15, 'L5'], [20, 'T0'], [25, 'T5'], [30, 'Y0']];

/** Predicted type against the type astronomers assigned, for known objects the model had never seen. */
function Scatter({ points }: { points: Point[] }) {
  const w = 560, h = 380, m = { l: 52, r: 14, t: 14, b: 44 };
  const lo = 2, hi = 30;
  const sx = (v: number) => m.l + ((v - lo) / (hi - lo)) * (w - m.l - m.r);
  const sy = (v: number) => h - m.b - ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * (h - m.t - m.b);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Scatter plot: the type the model predicted against the type astronomers assigned. The points follow the diagonal.">
      {TICKS.filter(([v]) => v >= lo && v <= hi).map(([v, t]) => (
        <g key={t}>
          <line x1={sx(v)} x2={sx(v)} y1={m.t} y2={h - m.b} stroke="rgba(245,245,247,0.08)" />
          <line x1={m.l} x2={w - m.r} y1={sy(v)} y2={sy(v)} stroke="rgba(245,245,247,0.08)" />
          <text x={sx(v)} y={h - m.b + 18} textAnchor="middle" className="cs-axis">{t}</text>
          <text x={m.l - 10} y={sy(v) + 4} textAnchor="end" className="cs-axis">{t}</text>
        </g>
      ))}
      <line x1={sx(lo)} y1={sy(lo)} x2={sx(hi)} y2={sy(hi)} stroke="rgba(245,245,247,0.45)" strokeDasharray="5 5" />
      {points.map((p, i) => <circle key={i} cx={sx(p.true)} cy={sy(p.pred)} r={2.6} fill="#f5f5f7" opacity={0.55} />)}
      <text x={(m.l + w - m.r) / 2} y={h - 6} textAnchor="middle" className="cs-axis cs-axis--t">Type astronomers assigned</text>
      <text x={14} y={(m.t + h - m.b) / 2} textAnchor="middle" transform={`rotate(-90 14 ${(m.t + h - m.b) / 2})`} className="cs-axis cs-axis--t">Type the model read</text>
    </svg>
  );
}

/** A candidate's SPHEREx spectrum: the dips at 1.7 and 3.3 microns are methane. */
function Spark({ s: raw }: { s: Cand['spectrum'] }) {
  const s = raw.filter(p => p.ujy > -4 * p.err);          // a flux far below zero is a corrupted band, not light: not drawn
  const w = 300, h = 96, m = { l: 6, r: 6, t: 8, b: 18 };
  if (s.length < 3) return null;
  const top = Math.max(...s.map(p => p.ujy + p.err)) * 1.05, bot = Math.min(0, ...s.map(p => p.ujy - p.err));
  const sx = (um: number) => m.l + ((um - 0.75) / (5 - 0.75)) * (w - m.l - m.r);
  const sy = (v: number) => h - m.b - ((v - bot) / (top - bot || 1)) * (h - m.t - m.b);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="The object's brightness at each infrared colour, 0.75 to 5 microns">
      {[[1.66, 1.78], [3.1, 3.45]].map(([a, b]) => <rect key={a} x={sx(a)} y={m.t} width={sx(b) - sx(a)} height={h - m.t - m.b} fill="rgba(245,245,247,0.1)" />)}
      <line x1={m.l} x2={w - m.r} y1={sy(0)} y2={sy(0)} stroke="rgba(245,245,247,0.25)" />
      {s.map((p, i) => <line key={'e' + i} x1={sx(p.um)} x2={sx(p.um)} y1={sy(p.ujy - p.err)} y2={sy(p.ujy + p.err)} stroke="rgba(245,245,247,0.4)" />)}
      <polyline points={s.map(p => `${sx(p.um).toFixed(1)},${sy(p.ujy).toFixed(1)}`).join(' ')} fill="none" stroke="#f5f5f7" strokeWidth={1.4} />
      {s.map((p, i) => <circle key={i} cx={sx(p.um)} cy={sy(p.ujy)} r={2} fill="#f5f5f7" />)}
      {[1, 2, 3, 4, 5].map(v => <text key={v} x={sx(v)} y={h - 4} textAnchor="middle" className="cs-axis">{v} µm</text>)}
    </svg>
  );
}

const POOL: Record<string, string> = { des_y6: 'Dark Energy Survey', des_y3: 'Dark Energy Survey', ukidss_T: 'UKIDSS', ukidss_L: 'UKIDSS', simbad_faint: 'SIMBAD' };

/** The wider search: objects other surveys picked from colours alone, given a SPHEREx spectrum and the same locked model. */
function WideBlock({ w }: { w: Wide }) {
  const v = w.vetting, b = v.blind_test;
  const fresh: (WideFlag & Partial<Graded>)[] = w.candidates?.candidates ?? v.flagged.filter(f => f.verdict.startsWith('no published spectrum'));
  const typed = v.flagged.filter(f => f.verdict.startsWith('already'));
  const doubt = v.flagged.filter(f => f.verdict.startsWith('doubtful'));
  return (
    <>
      <h3 className="cs-h3">The wider search.</h3>
      <p className="test-p">
        Then we gave the same locked model {w.n_objects.toLocaleString('en-US')} more objects: ones that other surveys picked out from their colours alone, mostly without ever taking a spectrum, and fainter catalogue candidates.
        {' '}{w.n_pass_quality.toLocaleString('en-US')} had a clean enough SPHEREx spectrum. The model flagged {w.n_flagged}.
      </p>
      <div className="tiles tiles--3">
        <div className="tile"><span className="tile__n">{typed.length} of {w.n_flagged}</span><span className="tile__t">flagged objects already have a published type. {b.published_T > 0 ? `Blind test: it flagged ${b.published_T_flagged} of ${b.published_T} published T dwarfs in this list, and ${b.published_not_T_flagged} of ${b.published_not_T} published warmer dwarfs.` : ''}</span></div>
        <div className="tile"><span className="tile__n">{fresh.length}</span><span className="tile__t">flagged objects with no published spectrum that we could find{w.candidates ? `, ${w.candidates.n_strong} with strong methane` : ''}. Another survey suspected them from colours; SPHEREx now shows the methane.</span></div>
        <div className="tile"><span className="tile__n">{doubt.length}</span><span className="tile__t">flagged but doubtful, because their WISE colour is not that of a T dwarf</span></div>
      </div>
      {fresh.length > 0 && (
        <>
          <h3 className="cs-h3">{w.candidates ? `${w.candidates.n_strong} brown dwarfs, seen in methane for the first time.` : 'Candidates for a first spectrum.'}</h3>
          <p className="test-p">The Dark Energy Survey listed these as possible T dwarfs from their colours alone. We found no published spectrum of any of them, and SIMBAD has no entry for them at all. Their SPHEREx spectra show the methane that only cold worlds have.{w.candidates ? ` In ${w.candidates.n_strong} of them, both methane bands are deeper than in 99% of known warmer dwarfs.` : ''} These are not new objects, and a large telescope should confirm them before anyone publishes them.</p>
          {w.other_telescopes && (
            <p className="test-p"><strong>Checked with other telescopes.</strong> A cold brown dwarf nearby should drift across the sky (WISE and NEOWISE, 2010–2016), look blue in the near infrared (VISTA or UKIRT: J − Ks below 0.5) and red in the mid infrared (WISE: W1 − W2 of 0.8 or more). {w.other_telescopes.n_moves} of {w.other_telescopes.n} measurably move, which a distant galaxy or quasar would not, and {w.other_telescopes.n_agree} pass all three tests. Most of the others miss only the near-infrared test by a little, which is common for the warmest T dwarfs. The rules were set before the check was run.</p>
          )}
          <div className="cs-cands">
            {fresh.map(c => (
              <article key={c.oid} className="cs-cand">
                <header><h4>{c.name}</h4><span className="cs-chip">{c.grade === 'strong' ? 'Strong methane' : c.grade === 'likely' ? 'Likely' : c.verdict.includes('agrees') ? 'WISE agrees' : 'No WISE colour'}</span></header>
                <Spark s={c.spectrum} />
                <dl>
                  <div><dt>Model reads</dt><dd>{c.pred_type}</dd></div>
                  <div><dt>{POOL[c.group] ?? 'Survey'} guessed</dt><dd>{c.phot_type ?? '—'}</dd></div>
                  <div><dt>Signal</dt><dd>{c.snr_J.toFixed(0)}×</dd></div>
                  <div><dt>WISE colour</dt><dd>{c.wise?.W1_W2 != null ? c.wise.W1_W2.toFixed(2) : '—'}</dd></div>
                </dl>
                {(() => {
                  const o = w.other_telescopes?.candidates.find(x => x.name === c.name);
                  if (!o) return null;
                  const t = o.tests;
                  const mark = (k: string) => (t[k] ? (t[k].pass ? 'yes' : 'no') : 'no data');
                  return (
                    <p className="cs-others">
                      <b>Other telescopes {o.agrees ? 'agree' : `agree on ${o.n_pass} of ${o.n_tests}`}.</b>
                      {' '}Moves: {t.moves ? `${t.moves.value} ± ${t.moves.error} mas a year (WISE)` : 'no data'}, {mark('moves')}.
                      {' '}Near-infrared colour: {t.j_ks ? `${t.j_ks.value.toFixed(2)} (${t.j_ks.data.startsWith('VISTA') ? 'VISTA' : 'UKIRT'})` : 'no data'}, {mark('j_ks')}.
                      {' '}Mid-infrared colour: {t.w1_w2 ? `${t.w1_w2.value.toFixed(2)} (WISE)` : 'no data'}, {mark('w1_w2')}.
                    </p>
                  );
                })()}
                <Link className="cs-go" href={`/map?ra=${c.ra.toFixed(5)}&dec=${c.dec.toFixed(5)}&fov=0.5`}>See it on the sky map</Link>
              </article>
            ))}
          </div>
        </>
      )}
      {fresh.length === 0 && <p className="test-p"><strong>Again, nothing unpublished.</strong> Every object the model flagged in the wider list already has a published type or fails the WISE check.</p>}
      {typed.length > 0 && (
        <div className="cs-table" role="table" aria-label="Wider search: flagged objects that already have a published type">
          <div role="row" className="cs-tr cs-tr--h"><span role="columnheader">Already typed</span><span role="columnheader">Model read</span><span role="columnheader">Published type</span></div>
          {typed.slice(0, 12).map(c => <div role="row" className="cs-tr" key={c.oid}><span role="cell">{c.published_name || c.name}</span><span role="cell">{c.pred_type}</span><span role="cell">{c.published_type}</span></div>)}
          {typed.length > 12 && <div role="row" className="cs-tr cs-tr--miss"><span role="cell">and {typed.length - 12} more, in validation/coldspec/wide/vetting.json</span><span role="cell" /><span role="cell" /></div>}
        </div>
      )}
      <p className="small dim">{v.caveat} Checked against: {v.references.join('; ')}.</p>
    </>
  );
}

/** Cold-world spectra: a model that reads spectral types from SPHEREx's 102 colours, and what it flags. */
export function ColdSpec() {
  const [d, setD] = useState<Doc | null>(null);
  useEffect(() => { fetch('/api/coldspec').then(r => (r.ok ? r.json() : null)).then(setD).catch(() => undefined); }, []);
  if (!d) return null;
  const { cv, results: r, vetting: v, quality: ql } = d;
  const verdict = (c: Cand) => v?.candidates.find(x => x.name === c.name)?.verdict ?? c.verdict;
  const fresh = r ? r.candidates.filter(c => verdict(c).startsWith('new candidate')) : [];
  const known = r ? r.candidates.filter(c => verdict(c).startsWith('already')) : [];
  const doubtful = r ? r.candidates.filter(c => verdict(c).startsWith('doubtful')) : [];
  const pct = (dex: number) => Math.round((10 ** dex - 1) * 100);
  return (
    <section className="band2 cs" aria-labelledby="cs-h">
      <h2 className="test-h" id="cs-h"><span>Search 2</span>Reading 102 colours.</h2>
      <p className="test-p">
        SPHEREx sees every object in 102 infrared colours. Cold worlds have a fingerprint there: methane swallows the light at 1.7 and 3.3 microns.
        We trained a model on {cv.n_used.toLocaleString('en-US')} dwarfs whose type astronomers already know
        {r ? `, locked it, and only then let it read ${r.n_pass_quality.toLocaleString('en-US')} objects that have no type at all.` : '. The unclassified objects come next.'}
      </p>
      <div className="tiles tiles--3">
        <div className="tile"><span className="tile__n">±{cv.held_out.rms_subtypes.toFixed(1)}</span><span className="tile__t">subtypes: how close the model gets to the astronomers' type, on objects it had never seen{ql ? `. Our SPHEREx colours agree with 2MASS to ${pct(ql.scatter_passing_cuts_dex)}%${ql.wise_check ? ` and with WISE to ${pct(ql.wise_check.scatter_dex)}%` : ''}.` : ''}</span></div>
        <div className="tile"><span className="tile__n">{cv.held_out.T_found} of {cv.held_out.T_total}</span><span className="tile__t">known T dwarfs it recognised from the spectrum alone. It wrongly called {cv.held_out.false_T} of {cv.held_out.not_T_total} warmer dwarfs a T dwarf.</span></div>
        <div className="tile">
          <span className="tile__n">{r ? (fresh.length > 0 ? fresh.length : `${known.length} of ${r.n_candidates}`) : '—'}</span>
          <span className="tile__t">{!r ? 'candidates: not scored yet'
            : fresh.length > 0 ? `new T-dwarf candidates. ${known.length} more that it flagged were already typed in the literature.`
            : `objects it flagged, out of ${r.n_pass_quality.toLocaleString('en-US')} unclassified ones, turned out to be T dwarfs that astronomers had already typed. A blind test passed. No new world.`}</span>
        </div>
      </div>

      <div className="cs-grid">
        <figure className="cs-fig">
          <Scatter points={cv.points} />
          <figcaption>Each dot is a known dwarf the model had not seen. On the dashed line, the model agrees with the astronomers. Made as faint as the faintest we accept, it still finds {cv.held_out_faint.T_found} of {cv.held_out_faint.T_total} T dwarfs.</figcaption>
        </figure>
        <div className="cs-note">
          <h3>How to read this</h3>
          <p>M dwarfs are small stars. L dwarfs are cooler. T dwarfs are colder still, with methane in their air like Jupiter.</p>
          <p>A plain rule using only the 1.7-micron methane dip scores {(cv.baseline_methane_index_auc * 100).toFixed(1)}% at telling T dwarfs apart. The model scores {(cv.held_out.auc_T * 100).toFixed(1)}%.</p>
          {r && <p>Of the {r.n_unclassified.toLocaleString('en-US')} unclassified objects, {r.n_pass_quality.toLocaleString('en-US')} had a clean enough spectrum. The model reads {r.typed_by_class.M ?? 0} as M, {r.typed_by_class.L ?? 0} as L and {r.typed_by_class.T ?? 0} as T. {r.n_outliers} looked unlike anything it was trained on, so it gives no answer for those.</p>}
        </div>
      </div>

      {r && fresh.length > 0 && (
        <>
          <h3 className="cs-h3">New candidates</h3>
          <p className="test-p">SIMBAD lists no spectral type for these. Their SPHEREx spectra look like T dwarfs. They are candidates, not discoveries: each needs a proper spectrum from a large telescope.</p>
          <div className="cs-cands">
            {fresh.map(c => (
              <article key={c.name} className="cs-cand">
                <header><h4>{c.name}</h4><span className="cs-chip">{c.verdict.includes('agrees') ? 'WISE agrees' : 'Unconfirmed'}</span></header>
                <Spark s={c.spectrum} />
                <dl>
                  <div><dt>Model reads</dt><dd>{c.pred_type}</dd></div>
                  <div><dt>Confidence</dt><dd>{Math.round(c.p_T * 100)}%</dd></div>
                  <div><dt>Signal</dt><dd>{c.snr_J.toFixed(0)}×</dd></div>
                  <div><dt>WISE colour</dt><dd>{c.wise?.W1_W2 != null ? c.wise.W1_W2.toFixed(2) : '—'}</dd></div>
                </dl>
                <Link className="cs-go" href={`/map?ra=${c.ra.toFixed(5)}&dec=${c.dec.toFixed(5)}&fov=0.5`}>See it on the sky map</Link>
              </article>
            ))}
          </div>
        </>
      )}
      {r && fresh.length === 0 && (
        <>
          <h3 className="cs-h3">No new world. A blind test instead.</h3>
          <p className="test-p">
            The catalogue we searched (SIMBAD) lists no type for these objects, so the model had never been told what they are. After we locked its answers, we checked the published literature.
            {v ? ` Every object it flagged has a published T-dwarf type. Of ${v.published_T} published T dwarfs hidden among the unclassified objects, it flagged ${v.published_T_flagged}. It flagged ${v.published_not_T_flagged} of the ${v.published_not_T} published warmer dwarf${v.published_not_T === 1 ? '' : 's'}.` : ''}
            {' '}That is evidence the method works. It is not a discovery.
          </p>
          {v && v.candidates.length > 0 && (
            <div className="cs-table" role="table" aria-label="Flagged objects: the model's reading against the published type">
              <div role="row" className="cs-tr cs-tr--h"><span role="columnheader">Object</span><span role="columnheader">Model read</span><span role="columnheader">Published type</span></div>
              {v.candidates.map(c => <div role="row" className="cs-tr" key={c.name}><span role="cell">{c.published_name ?? c.name}</span><span role="cell">{c.model_type}</span><span role="cell">{c.published_type ?? '—'}</span></div>)}
              {v.matches.filter(m => !m.flagged).map(m => <div role="row" className="cs-tr cs-tr--miss" key={m.name}><span role="cell">{m.name} <em>(not flagged)</em></span><span role="cell">{m.model_type}</span><span role="cell">{m.published_type}</span></div>)}
            </div>
          )}
          <p className="small dim">Published types: Best et al. 2020, AJ 159, 257. The one published T dwarf the model missed has a signal far stronger than its catalogue brightness allows, so its light is probably blended with a neighbour.</p>
          <p className="test-p" style={{ marginTop: 18 }}>The model can miss things, so people can help: <Link href="/check">check a candidate yourself</Link>.</p>
        </>
      )}
      {r && doubtful.length > 0 && <p className="small dim">Flagged but doubtful, because the WISE colour disagrees: {doubtful.map(c => c.name).join(', ')}.</p>}
      {d.wide && <WideBlock w={d.wide} />}
      <p className="small dim">Spectra: SPHEREx DR1 all-sky data cube (IRSA). Types and the unclassified lists: SIMBAD (CDS). Model, cuts and decision rule were hash-locked {d.protocol ? `on ${d.protocol.locked_utc.slice(0, 10)} ` : ''}before any unclassified object was scored. The absolute flux scale is not calibrated; only the shape of each spectrum is used.</p>
    </section>
  );
}
