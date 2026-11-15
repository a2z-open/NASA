import { useEffect, useState } from 'react';
import { Link } from '../router.tsx';

// ---- shapes of /api/distant and /api/planet-nine (validation/distant_report.py, validation/planet_nine.py) ----
interface TrackPoint { mjd: number; dx_deg: number; dy_deg: number }
interface DistantDetection extends TrackPoint { snr: number; visit: number; wavelength_um: number | null; flux_ujy: number; detector: number }
interface DistantBody {
  body: string; title: string; kind: string; vmag: number | null; passed: boolean; recovered: boolean; other_objects: number;
  method?: 'tracklets' | 'shift-and-stack' | null;
  shiftstack?: { version: number; n_exposures_stacked: number; snr: number[]; rate_arcsec_day: number[]; versions_on_record: number };
  n_fields: number; n_exposures: number; n_peaks: number; n_explained: number; n_orphans: number; n_tracklets: number;
  locked: { entry: number; hash: string; time_utc: string };
  match: null | { r_fit_au: number; r_err_au: number | null; r_true_au: number; distance_error_fraction: number; median_sep_arcsec: number; n_visits: number; n_detections: number };
  object?: {
    r_au: number; r_err_au: number | null; a_au: number | null; inclination_deg: number | null; n: number; n_visits: number;
    parallax_arcsec: number; jump_deg: number; detections: DistantDetection[]; curve: TrackPoint[]; from_sun: TrackPoint[];
    spectrum?: { wavelength_um: number; value: number; err: number; n: number }[]; spectrum_exposures?: number;
    surface?: { ice: string; bands_um: number[]; reference: string } | null;
  };
  diagnostic: {
    visits: { n_exposures: number; n_detections_of_body: number; nights: number }[]; why_missed?: string;
    one_visit_fit?: { n: number; nights: number; span_days: number; r_au: number; r_err_au: number | null; r_true_au: number };
  };
}
export interface DistantResults {
  bodies: DistantBody[]; n_tested: number; n_passed: number; n_recovered: number; false_objects: number;
  max_distance_error_percent: number | null; ledger_ok: boolean;
}
interface P9Triple { field_id: string; r_au: number; flux_ujy: number; jupiter_twin_ujy: number; too_bright_for_a_planet: boolean; passes_mirror_test: boolean }
interface PlanetNine {
  search: { n_fields_three_visits: number; area_deg2_three_visits: number; candidates: P9Triple[]; accepted: P9Triple[]; median_depth_short_ujy: number | null };
  injection: null | { r_au: number[]; fluxes_ujy: number[]; false_triples: number; results: { r_au: number; flux_ujy: number; outcome: string; r_fit_au: number | null }[] };
  faintest_synthetic_recovered_ujy: number | null;
  reach: null | { world: string; reference: string; max_distance_au: number }[];
  nominal: { v: number; r_au: number; flux_ujy: number };
}

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json() as Promise<T>;
}
export const distantApi = {
  results: () => getJson<DistantResults>('/api/distant'),
  planetNine: () => getJson<PlanetNine>('/api/planet-nine'),
};

const monthYear = (mjd: number) => new Date((mjd - 40587) * 86400000).toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });

/** Where the body was on the sky against time. The straight line is its own motion; the wave on top is parallax. */
function ParallaxChart({ o, title }: { o: NonNullable<DistantBody['object']>; title: string }) {
  const W = 640, H = 300, L = 54, R = 16, T = 18, B = 40;
  // project every track on to the direction in which the fitted path spreads most
  const mx = o.curve.reduce((s, p) => s + p.dx_deg, 0) / o.curve.length;
  const my = o.curve.reduce((s, p) => s + p.dy_deg, 0) / o.curve.length;
  let sxx = 0, syy = 0, sxy = 0;
  for (const p of o.curve) { sxx += (p.dx_deg - mx) ** 2; syy += (p.dy_deg - my) ** 2; sxy += (p.dx_deg - mx) * (p.dy_deg - my); }
  const ang = 0.5 * Math.atan2(2 * sxy, sxx - syy);
  const ux = Math.cos(ang), uy = Math.sin(ang);
  const along = (p: TrackPoint) => (p.dx_deg - mx) * ux + (p.dy_deg - my) * uy;
  const all = [...o.curve, ...o.from_sun, ...o.detections];
  const t0 = Math.min(...o.curve.map(p => p.mjd)), t1 = Math.max(...o.curve.map(p => p.mjd));
  const v0 = Math.min(...all.map(along)), v1 = Math.max(...all.map(along));
  const pad = (v1 - v0) * 0.08 || 0.1;
  const x = (t: number) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - (v0 - pad)) / (v1 - v0 + 2 * pad)) * (H - T - B);
  const path = (pts: TrackPoint[]) => pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.mjd).toFixed(1)},${y(along(p)).toFixed(1)}`).join(' ');
  const visits = [...new Set(o.detections.map(d => d.visit))].sort((a, b) => a - b);
  const ticks = [v0, (v0 + v1) / 2, v1];
  return (
    <figure className="pchart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}: position on the sky against date. ${o.n} detections in ${o.n_visits} visits lie on a wavy path; the wave is parallax.`}>
        {ticks.map(v => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="pchart__grid" />
            <text x={L - 8} y={y(v) + 4} textAnchor="end" className="pchart__tick">{(v - v0).toFixed(1)}°</text>
          </g>
        ))}
        <path d={path(o.from_sun)} className="pchart__sun" />
        <path d={path(o.curve)} className="pchart__fit" />
        {o.detections.map((d, i) => <circle key={i} cx={x(d.mjd)} cy={y(along(d))} r={4.5} className="pchart__pt" />)}
        {visits.map(v => {
          const ds = o.detections.filter(d => d.visit === v);
          const tm = ds.reduce((s, d) => s + d.mjd, 0) / ds.length;
          return <text key={v} x={Math.min(Math.max(x(tm), L + 30), W - R - 30)} y={H - 14} textAnchor="middle" className="pchart__tick">{monthYear(tm)}</text>;
        })}
      </svg>
      <figcaption>
        <span><i className="pchart__key pchart__key--pt" /> where SPHEREx saw it</span>
        <span><i className="pchart__key pchart__key--fit" /> the orbit Aiges fitted</span>
        <span><i className="pchart__key pchart__key--sun" /> the same orbit seen from the Sun</span>
      </figcaption>
    </figure>
  );
}

/** Reflected sunlight against wavelength, measured along the fitted orbit. Dips are what the surface ice absorbs. */
function SurfaceChart({ o, title }: { o: NonNullable<DistantBody['object']>; title: string }) {
  const pts = (o.spectrum ?? []).filter(p => Number.isFinite(p.value) && Number.isFinite(p.err));
  if (pts.length < 8) return null;
  const W = 640, H = 240, L = 54, R = 16, T = 16, B = 38;
  const x0 = 0.7, x1 = 2.45, y1 = Math.max(1.8, ...pts.map(p => p.value + p.err));
  const x = (l: number) => L + ((l - x0) / (x1 - x0)) * (W - L - R);
  const y = (v: number) => T + (1 - Math.max(v, 0) / y1) * (H - T - B);
  const bands = o.surface?.bands_um ?? [];
  return (
    <figure className="pchart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}: how much sunlight it reflects at ${pts.length} wavelengths from 0.75 to 2.4 micrometres.`}>
        {[0, 1].map(v => <g key={v}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="pchart__grid" /><text x={L - 8} y={y(v) + 4} textAnchor="end" className="pchart__tick">{v}</text></g>)}
        {bands.map(l => <line key={l} x1={x(l)} x2={x(l)} y1={T} y2={H - B} className="pchart__band" />)}
        {[1.0, 1.5, 2.0].map(l => <text key={l} x={x(l)} y={H - 14} textAnchor="middle" className="pchart__tick">{l.toFixed(1)} µm</text>)}
        {pts.map((p, i) => <line key={`e${i}`} x1={x(p.wavelength_um)} x2={x(p.wavelength_um)} y1={y(p.value + p.err)} y2={y(p.value - p.err)} className="pchart__err" />)}
        <path d={pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.wavelength_um).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ')} className="pchart__fit" />
        {pts.map((p, i) => <circle key={i} cx={x(p.wavelength_um)} cy={y(p.value)} r={4} className="pchart__pt" />)}
      </svg>
      <figcaption>
        <span><i className="pchart__key pchart__key--pt" /> sunlight reflected, {o.spectrum_exposures ?? pts.length} exposures along the fitted orbit</span>
        {o.surface && <span><i className="pchart__key pchart__key--band" /> where {o.surface.ice} absorbs</span>}
      </figcaption>
    </figure>
  );
}

function BodyCard({ b }: { b: DistantBody }) {
  const m = b.match, o = b.object, d = b.diagnostic;
  return (
    <article className="world rv">
      <div className="world__text">
        <p className="world__tag"><span className={`badge2 ${b.passed ? 'badge2--hot' : 'badge2--muted'}`}>{b.passed ? (b.method === 'shift-and-stack' ? 'Found blind by stacking' : 'Found blind') : b.recovered ? 'Found, outside the pass rule' : 'Not found'}</span> {b.kind}{b.vmag != null ? `, magnitude ${b.vmag.toFixed(1)}` : ''}</p>
        <h3>{b.title}</h3>
        {m && o ? (
          <>
            <p className="world__n">{m.r_fit_au.toFixed(2)}<small> AU{m.r_err_au != null ? ` ± ${m.r_err_au.toFixed(2)}` : ''}</small></p>
            <p className="world__vs">from the Sun, measured from SPHEREx images alone. NASA's JPL says <strong>{m.r_true_au.toFixed(2)} AU</strong>.</p>
            {b.method === 'shift-and-stack' && b.shiftstack ? (
              <p className="small"><strong>Too faint for any single image.</strong> Aiges added {b.shiftstack.n_exposures_stacked} exposures together along thousands of trial paths, and it appeared in all three visits at {b.shiftstack.snr.map(x => x.toFixed(0)).join(', ')}σ. One orbit through the three gives the distance. Between visits it jumped {o.jump_deg.toFixed(1)}° on the sky. The way visits are joined was changed twice before this worked, without looking at JPL's positions; all three versions are on record.</p>
            ) : (
              <p className="small">{o.n} detections in {o.n_visits} visits, a median {m.median_sep_arcsec.toFixed(1)}″ from JPL's track. Between visits it jumped {o.jump_deg.toFixed(1)}° on the sky.{o.a_au != null && o.inclination_deg != null ? ` The fit also gives an orbit about ${o.a_au.toFixed(0)} AU across its long half, tilted ${o.inclination_deg.toFixed(0)}°.` : ''}</p>
            )}
          </>
        ) : (
          <>
            <p className="world__vs">{d.why_missed ?? 'The search did not link it.'}</p>
            {d.one_visit_fit && (
              <p className="small">After the fact: its track in that one visit ({d.one_visit_fit.n} detections on {d.one_visit_fit.nights} nights) was found, and fitted alone it gives {d.one_visit_fit.r_au.toFixed(1)}{d.one_visit_fit.r_err_au != null ? ` ± ${d.one_visit_fit.r_err_au.toFixed(1)}` : ''} AU. JPL says {d.one_visit_fit.r_true_au.toFixed(1)} AU. This does not count as a pass.</p>
            )}
          </>
        )}
        <p className="small dim">{b.n_exposures} exposures in {b.n_fields} fields: {b.n_peaks.toLocaleString('en-US')} sources seen, {b.n_orphans} of them in no catalogue. Result locked as record {b.locked.entry} before JPL's positions were opened.</p>
      </div>
      {o && (
        <div className="world__charts">
          <ParallaxChart o={o} title={b.title} />
          <SurfaceChart o={o} title={b.title} />
          {o.spectrum && o.spectrum.length >= 8 && o.surface && (
            <p className="small">The dips fall where {o.surface.ice} absorbs. Earlier work found {b.title} covered in {o.surface.ice} ({o.surface.reference}), so the object the search linked has the right surface as well as the right orbit.</p>
          )}
        </div>
      )}
    </article>
  );
}

/** Blind recovery of known distant bodies: the test of the distant-world search. */
export function DistantWorlds() {
  const [d, setD] = useState<DistantResults | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { distantApi.results().then(setD).catch(() => setErr(true)); }, []);
  if (err) return null;
  if (!d) return <p className="muted">Loading the distant-world test…</p>;
  const missed = d.n_tested - d.n_passed;
  return (
    <section className="band2" aria-labelledby="dw-h">
      <h2 className="test-h" id="dw-h"><span>Search 1</span>Find a distant world by its parallax</h2>
      <p className="test-p">Six months apart, SPHEREx looks at the same world from opposite sides of the Earth's orbit. The world appears to jump, and the size of the jump gives its distance. We tested this on worlds whose distance is already known.</p>
      <div className="tiles tiles--3">
        <div className="tile tile--hot"><span className="tile__n">{d.n_passed}<small> of {d.n_tested}</small></span><span className="tile__t">known distant worlds found and placed at the right distance{missed > 0 ? `; ${missed} missed` : ''}</span></div>
        <div className="tile"><span className="tile__n">{d.max_distance_error_percent != null ? (d.max_distance_error_percent < 0.1 ? 'under 0.1%' : `${d.max_distance_error_percent.toFixed(1)}%`) : '—'}</span><span className="tile__t">largest error in distance among those found</span></div>
        <div className="tile"><span className="tile__n">{d.false_objects}</span><span className="tile__t">false objects linked in the same fields</span></div>
      </div>
      <div className="worlds">{[...d.bodies].sort((a, b) => Number(b.passed) - Number(a.passed)).map(b => <BodyCard key={b.body} b={b} />)}</div>
      {missed > 0 && (
        <p className="small">What the misses show: Pluto sits in a crowded star field with two thin visits, and Haumea was imaged in only one visit. Eris was too faint for any single image, and stacking along trial paths is what found it; the same stacking is how a fainter, farther world would have to be found.</p>
      )}
      <details className="more">
        <summary>How blind was this?</summary>
        <div className="plain">
          <p>We used JPL's positions for one thing before the search: choosing which patches of sky to download, because these worlds move by degrees between visits. The search itself was given the images and nothing else. It found every point of light, removed the ones already in the Gaia and WISE catalogues, joined what was left along straight tracks, and fitted one orbit through tracks from different visits.</p>
          <p>Each result was then locked with a hash in a local record, and only after that were JPL's positions opened to score it. The pass rule was written first: within 2 pixels of JPL's track, distance within 5%, and no second object. The record is on this computer, so its time-stamp is our own until the team publishes it.</p>
        </div>
      </details>
    </section>
  );
}

const OUTCOME: Record<string, string> = {
  recovered: 'found', too_faint: 'too faint', seen_not_linked: 'seen, not linked', wrong_distance: 'found, wrong distance', outside_field: 'left the field',
};

interface DeepPatch { field: string; ra: number; dec: number; n_photos: number | null; n_visits: number; n_visits_all?: number; single_5sigma_ujy: number; n_candidates: number;
  n_passed_checks?: number | null; chance_expected?: number; injection: { distance_au: number; flux_ujy: number; n_measured: number; n_recovered: number }[] | null }

/** Search 5: one visit's photos added up along every path a distant planet could take (validation/p9_deepstack.py). */
export function PlanetNineDeep() {
  const [d, setD] = useState<{ deep: DeepPatch[]; planet_nine?: { flux_ujy: number } } | null>(null);
  useEffect(() => { fetch('/api/how').then(r => (r.ok ? r.json() : null)).then(setD).catch(() => undefined); }, []);
  if (!d || !d.deep.length) return null;
  const half = (p: DeepPatch) => {
    const at = (p.injection ?? []).filter(r => r.distance_au === 550 && r.n_measured).sort((a, b) => a.flux_ujy - b.flux_ujy);
    return at.find(r => r.n_recovered / r.n_measured >= 0.5)?.flux_ujy ?? null;
  };
  const flagged = d.deep.reduce((s, p) => s + p.n_candidates, 0);
  const checked = d.deep.every(p => p.n_candidates === 0 || typeof p.n_passed_checks === 'number');
  const passed = d.deep.reduce((s, p) => s + (p.n_passed_checks ?? 0), 0);
  const chance = d.deep.reduce((s, p) => s + (p.chance_expected ?? p.n_visits / 3), 0);
  return (
    <section className="band2" aria-labelledby="p9d-h">
      <h2 className="test-h" id="p9d-h"><span>Search 5</span>Planet Nine again: adding photos together, along its path</h2>
      <p className="test-p">One photo is too noisy. So we shifted every photo of a visit to follow each path a distant planet could take, and added them up. Two patches on Planet Nine's predicted path.</p>
      <div className="rows">
        {d.deep.map(p => {
          const h = half(p);
          return (
            <div key={p.field} className="row row--static">
              <span className="row__name">RA {p.ra}°, Dec {p.dec}°</span>
              <span className="row__what">{p.n_photos} photos, {(p.n_visits_all ?? p.n_visits) > p.n_visits ? `${p.n_visits_all} visits (${p.n_visits} big enough to search)` : `${p.n_visits} visits`}. One photo: {Math.round(p.single_5sigma_ujy)} µJy.{h ? ` Added up: ${h} µJy.` : ''}</span>
              <span className="row__num">{p.n_candidates} flagged</span>
            </div>
          );
        })}
      </div>
      <p className="verdict">
        <strong>{checked ? (passed === 0 ? 'No planet.' : `${passed} flag(s) pass our checks so far, unconfirmed.`) : `${flagged} flagged, being checked.`}</strong>
        {' '}Chance alone flags about {Math.round(chance)} in these visits.{d.planet_nine ? ` The predicted Planet Nine is ${d.planet_nine.flux_ujy.toFixed(1)} µJy, still fainter than we reach.` : ''}
        {' '}<Link href="/how#s8">How this works</Link>.
      </p>
    </section>
  );
}

/** Planet Nine mode: what was searched, what could have been found, and what could not. */
export function PlanetNineReach() {
  const [p, setP] = useState<PlanetNine | null>(null);
  useEffect(() => { distantApi.planetNine().then(setP).catch(() => undefined); }, []);
  if (!p) return null;
  const inj = p.injection;
  const rejected = p.search.candidates.filter(c => c.too_bright_for_a_planet || !c.passes_mirror_test);
  const limit = p.faintest_synthetic_recovered_ujy;
  return (
    <section className="band2" aria-labelledby="p9-h">
      <h2 className="test-h" id="p9-h"><span>Search 4</span>The same search, pointed at Planet Nine</h2>
      <p className="test-p">A planet 500 AU away would jump 14 arcminutes between visits and come back. We looked for that pattern in every field we hold.</p>
      <p className="verdict">
        <strong>{p.search.accepted.length === 0 ? 'Not found. And it could not have been.' : `${p.search.accepted.length} unconfirmed candidate${p.search.accepted.length === 1 ? '' : 's'}.`}</strong>
        The {p.search.n_fields_three_visits} fields with three visits cover {p.search.area_deg2_three_visits.toFixed(1)} square degrees; the planet could be anywhere in thousands.
        {limit != null && <> In these images the search finds a distant body down to about {limit.toFixed(0)} µJy. The predicted Planet Nine is about {p.nominal.flux_ujy.toFixed(0)} µJy, some {Math.round(limit / p.nominal.flux_ujy)} times fainter.</>}
        {' '}This is a working method and an honest limit, not a discovery.
      </p>
      {p.reach && limit != null && (
        <>
          <h3 className="sub-h">How far away could a world be, and still be seen here?</h3>
          <div className="rows">
            {p.reach.map(r => (
              <div key={r.world} className="row row--static">
                <span className="row__name">{r.world}</span>
                <span className="row__what">{r.reference}</span>
                <span className="row__num">{Math.round(r.max_distance_au / 10) * 10} AU</span>
              </div>
            ))}
          </div>
          <p className="small dim">Reflected sunlight fades with the fourth power of distance. Our fields are 20 arcminutes wide, so a body closer than about 450 AU leaves the field between visits. Only something the size of Jupiter was within reach, and the WISE telescope has already ruled that out.</p>
        </>
      )}
      {inj && (
        <>
          <h3 className="sub-h">Test with pretend planets</h3>
          <p className="test-p">We added {inj.results.length} pretend planets to real images of a blank field and ran the search without telling it. These are not real objects.</p>
          <div className="igrid" role="table" aria-label="Which pretend planets the search found">
            <div className="igrid__corner small dim" role="columnheader">distance ↓ · brightness →</div>
            {inj.fluxes_ujy.map(f => <div key={f} className="igrid__h small" role="columnheader">{f} µJy</div>)}
            {inj.r_au.map(r => (
              <div key={r} className="igrid__row" role="row">
                <div className="igrid__h small" role="rowheader">{r} AU</div>
                {inj.fluxes_ujy.map(f => {
                  const x = inj.results.find(q => Math.abs(q.r_au - r) < 1e-6 && Math.abs(q.flux_ujy - f) < 1e-6);
                  const o = x?.outcome ?? 'not_run';
                  return (
                    <div key={f} className={`igrid__cell igrid__cell--${o === 'recovered' ? 'recovered' : 'none'}`} role="cell">
                      <strong>{OUTCOME[o] ?? o}</strong>
                      {x?.r_fit_au != null && <span>fitted {Math.round(x.r_fit_au)} AU</span>}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
          <p className="small dim">{inj.false_triples === 0 ? 'No false planet was linked in that field.' : `${inj.false_triples} false link(s) in that field.`} At 2000 AU the planet moves so little that only one case was linked.</p>
        </>
      )}
      {rejected.length > 0 && (
        <>
          <h3 className="sub-h">{rejected.length === 1 ? 'One false alarm, caught' : `${rejected.length} false alarms, both caught`}</h3>
          <div className="plain">
            <p>Geometry alone raised {rejected.length} candidate{rejected.length === 1 ? '' : 's'} in the real fields. {rejected.map(c => `In the ${c.field_id.replace(/-/g, ' ').replace(/\b[a-z]/g, m => m.toUpperCase())} field the three sources are about ${Math.round(c.flux_ujy).toLocaleString('en-US')} µJy at a fitted ${Math.round(c.r_au / 100) * 100} AU, where a twin of Jupiter would be ${c.jupiter_twin_ujy < 1 ? c.jupiter_twin_ujy.toFixed(1) : Math.round(c.jupiter_twin_ujy)} µJy.`).join(' ')} Nothing that bright can be a planet at that distance.</p>
            <p>The R Draconis case is the interesting one. Its sources sit about one arcminute from that saturated star, in the same place in two visits and a different place in the visit between. A reflection inside the telescope does that, because the spacecraft is turned round every six months. So a reflection can imitate parallax, and a search like this needs a brightness check as well as geometry. We added that check after seeing these two cases, and we say so.</p>
          </div>
        </>
      )}
      <p className="small dim">Sources and numbers: <code>docs/PLANET_NINE_RESEARCH.md</code> and <code>validation/distant/PROTOCOL_P9.md</code> in the project. <Link href="/about">About the data</Link></p>
    </section>
  );
}

interface BarnardHaloDoc {
  result: {
    locked_entry: number; locked_time_utc: string; n_measured: number; years_between: number; measured_total_arcsec: number; predicted_total_arcsec: number;
    difference_arcsec: number; motion_arcsec_per_year: number; gaia_motion_arcsec_per_year: number; passed: boolean;
    per_detector: { detector: number; difference_arcsec: number }[];
  };
  pass_rule: { max_difference_arcsec: number };
  n_reference: number;
}

/** Barnard's Star saturates the camera. Its halo does not, and the halo's centre moves with the star. */
export function BarnardHalo() {
  const [d, setD] = useState<BarnardHaloDoc | null>(null);
  useEffect(() => { getJson<BarnardHaloDoc>('/api/barnard-halo').then(setD).catch(() => undefined); }, []);
  if (!d) return null;
  const r = d.result;
  const worst = Math.max(...r.per_detector.map(p => p.difference_arcsec));
  return (
    <section className="band2" aria-labelledby="bh-h">
      <h2 className="test-h" id="bh-h"><span>Test 5 · on sealed images</span>Track a star too bright to pin down</h2>
      <p className="test-p">Barnard's Star, the first target NASA named, overloads the camera in every exposure. We followed the centre of the ring of light around it, locked the rule, and only then opened a visit that had been sealed since the first session.</p>
      <div className="tiles tiles--3">
        <div className={`tile ${r.passed ? 'tile--hot' : ''}`}><span className="tile__n">{r.measured_total_arcsec.toFixed(1)}″</span><span className="tile__t">how far the halo's centre moved in {r.years_between.toFixed(2)} years. {r.passed ? 'Pass.' : 'Outside the limit.'}</span></div>
        <div className="tile"><span className="tile__n">{r.predicted_total_arcsec.toFixed(1)}″</span><span className="tile__t">what Gaia says the star moved in that time</span></div>
        <div className="tile"><span className="tile__n">{r.difference_arcsec.toFixed(2)}″</span><span className="tile__t">gap between the two, direction included. The limit set in advance was {d.pass_rule.max_difference_arcsec}″</span></div>
      </div>
      <p className="small dim">{r.n_measured} sealed exposures against {d.n_reference} from a year earlier, compared detector by detector; the largest single-detector gap is {worst.toFixed(1)}″. Rule locked as record {r.locked_entry} before the download. Gaia supplies the expected motion, so this tests the halo method, not Gaia. A visit in the opposite season sits 1.7″ off in one direction and is not used.</p>
    </section>
  );
}

interface WatchDoc {
  checked_utc: string; n_new_total: number;
  items: { name: string; kind: 'forecast' | 'target'; target: string; status: string; n_new: number; note: string; next_window?: { start_utc: string; end_utc: string } | null }[];
}

/** The SPHEREx watcher's last check of NASA's archive (pipeline/watch.py). */
export function WatchPanel() {
  const [d, setD] = useState<WatchDoc | null>(null);
  useEffect(() => { getJson<WatchDoc>('/api/watch').then(setD).catch(() => undefined); }, []);
  if (!d) return null;
  const when = new Date(d.checked_utc);
  const ago = Math.max(0, Math.round((Date.now() - when.getTime()) / 60000));
  const agoText = ago < 60 ? `${ago} minute${ago === 1 ? '' : 's'} ago` : ago < 1440 ? `${Math.round(ago / 60)} hours ago` : when.toLocaleDateString('en-US', { day: 'numeric', month: 'long' });
  const fc = d.items.filter(i => i.kind === 'forecast');
  return (
    <section className="band2" aria-labelledby="watch-h">
      <h2 className="test-h" id="watch-h"><span>Live</span>Waiting for the next images</h2>
      <p className="test-p">NASA releases new SPHEREx images every week. Aiges checks the archive for every prediction it has locked. When the images arrive, the forecast is scored, pass or fail.</p>
      <div className="rows">
        {fc.map(i => (
          <div key={i.target} className="row row--static">
            <span className="row__name"><span className={`dot dot--${i.status === 'new_data' ? 'hot' : 'cold'}`} aria-hidden="true" />{i.name}</span>
            <span className="row__what">{i.note}</span>
            <span className="row__num small">{i.status === 'new_data' ? `${i.n_new} new` : 'waiting'}</span>
          </div>
        ))}
      </div>
      <p className="small dim">Last check of NASA's archive: {agoText}. {d.n_new_total === 0 ? 'Nothing new yet.' : `${d.n_new_total} new image(s) found.`} Run <code>python -m pipeline.watch</code> after each weekly release.</p>
    </section>
  );
}

interface VanishedDoc {
  n_fields: number; n_tested: number; counts: { moved: number; faded: number; vanished: number };
  fields_without_catalogue: string[];
  flagged: { field_id: string; name: string; kind: string; w2: number; ra: number; dec: number; mover_track: string | null; pm_arcsec_yr: number | null }[];
}

/** What WISE saw around 2015 that SPHEREx cannot see now. */
export function VanishedPanel() {
  const [d, setD] = useState<VanishedDoc | null>(null);
  useEffect(() => { getJson<VanishedDoc>('/api/vanished').then(setD).catch(() => undefined); }, []);
  if (!d) return null;
  const byObject = new Map<string, VanishedDoc['flagged']>();
  for (const f of d.flagged) {
    const key = f.mover_track ?? `${f.field_id}:${f.name}`;
    byObject.set(key, [...(byObject.get(key) ?? []), f]);
  }
  const unexplained = d.counts.faded + d.counts.vanished;
  return (
    <section className="band2" aria-labelledby="gone-h">
      <h2 className="test-h" id="gone-h"><span>Search 6</span>What has disappeared since WISE?</h2>
      <p className="test-p">A world that moves leaves an empty spot behind. We took every bright source NASA's WISE telescope saw around 2015 in our fields, and looked at the same spot in SPHEREx's images today.</p>
      <div className="tiles tiles--3">
        <div className="tile"><span className="tile__n">{d.n_tested.toLocaleString('en-US')}</span><span className="tile__t">bright WISE sources checked in {d.n_fields} fields</span></div>
        <div className="tile tile--hot"><span className="tile__n">{byObject.size}</span><span className="tile__t">gone from where WISE saw them, because they moved: known brown dwarfs</span></div>
        <div className="tile"><span className="tile__n">{unexplained}</span><span className="tile__t">gone or faded with no explanation</span></div>
      </div>
      <div className="rows">
        {[...byObject.entries()].map(([name, fs]) => (
          <a key={name} className="row" href={`/explore?ra=${fs[0].ra.toFixed(5)}&dec=${fs[0].dec.toFixed(5)}&fov=6`}>
            <span className="row__name"><span className="dot dot--hot" aria-hidden="true" />{fs[0].mover_track ?? fs[0].name}</span>
            <span className="row__what">{fs[0].kind === 'moved' ? `Not at the spot${fs.length > 1 ? 's' : ''} where WISE saw it. Its own motion, measured by SPHEREx, runs back through ${fs.length > 1 ? `all ${fs.length} WISE positions` : 'that position'}.` : fs[0].kind}</span>
            <span className="row__go" aria-hidden="true">→</span>
          </a>
        ))}
      </div>
      <p className="small dim">Checked at 3.8–5.0 µm, where SPHEREx should see each source at 15σ or more. Entries that WISE itself marks as artefacts, and anything within 2′ of a star that saturates SPHEREx, are skipped; those two rules were added after the first run found debris around Barnard's Star.{d.fields_without_catalogue.length ? ` No WISE catalogue came back for: ${d.fields_without_catalogue.join(', ')}.` : ''}</p>
    </section>
  );
}

interface MLDoc {
  folds: { held_out: string; auc_synthetic: number | null; auc_real_body_vs_artefacts: number | null; auc_real_body_snr_only: number | null; n_real_body: number; n_artefacts: number }[];
  mean_auc_synthetic: number | null; mean_auc_real_body: number | null; mean_auc_real_body_snr_only: number | null;
}

/** Does machine learning help? Tested properly, and reported whatever the answer. */
export function MLPanel() {
  const [d, setD] = useState<MLDoc | null>(null);
  useEffect(() => { getJson<MLDoc>('/api/ml').then(setD).catch(() => undefined); }, []);
  if (!d || d.mean_auc_real_body == null || d.mean_auc_real_body_snr_only == null) return null;
  const better = d.mean_auc_real_body > d.mean_auc_real_body_snr_only + 0.02;
  const pct = (x: number | null) => (x == null ? '—' : `${Math.round(x * 100)}%`);
  return (
    <section className="band2" aria-labelledby="ml-h">
      <h2 className="test-h" id="ml-h"><span>Test 6</span>Does machine learning help? {better ? 'Yes, a little.' : 'Not yet.'}</h2>
      <p className="test-p">We trained a model to tell a real point of light from an artefact, the way big sky surveys do. It learned from pretend stars hidden in real SPHEREx images, then had to rank the real detections of four dwarf planets it had never seen.</p>
      <div className="tiles tiles--3">
        <div className="tile"><span className="tile__n">{pct(d.mean_auc_synthetic)}</span><span className="tile__t">pretend stars told apart from artefacts, on fields it never saw</span></div>
        <div className={`tile ${better ? 'tile--hot' : ''}`}><span className="tile__n">{pct(d.mean_auc_real_body)}</span><span className="tile__t">real dwarf-planet detections told apart from artefacts by the model</span></div>
        <div className="tile"><span className="tile__n">{pct(d.mean_auc_real_body_snr_only)}</span><span className="tile__t">the same, using signal strength alone, with no machine learning</span></div>
      </div>
      <p className="small dim">The figure is the chance that a random real detection is ranked above a random artefact (50% is guessing). {better ? 'The model beats the simple rule.' : 'On real detections the model does not beat the simple rule, so it is not used in any result.'} By body: {d.folds.map(f => `${f.held_out} ${pct(f.auc_real_body_vs_artefacts)} vs ${pct(f.auc_real_body_snr_only)}`).join(' · ')}. Pretend stars are cleaner than real ones, which is why the first number flatters the model.</p>
    </section>
  );
}
