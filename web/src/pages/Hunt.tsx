import { useEffect, useMemo, useRef, useState } from 'react';
import { huntApi, loadFrame, type HuntField, type HuntFieldRow, type HuntIndex, type HuntInjection, type HuntMover } from '../api.ts';
import { Page, PageHero } from '../components/Shell.tsx';
import { DistantWorlds, PlanetNineDeep, PlanetNineReach, VanishedPanel } from './Distant.tsx';
import { ColdSpec } from './ColdSpec.tsx';
import { AsteroidHunt } from './Asteroids.tsx';
import { paint } from '../components/FieldImage.tsx';
import { Link } from '../router.tsx';

const MOVER_CLASSES = ['candidate', 'stack_candidate', 'two_visit_candidate', 'known_mover', 'suspect'];
const CURATED = new Set(['epsilon-indi-b', 'wise-0855', 'barnards-star', 'rw-aurigae', 'r-draconis']);

const FLAG_TEXT: Record<string, string> = {
  colour_dependent_motion: 'its motion differs between short and long wavelengths, which is what a blend of two sources does',
  poor_model_fit: 'its positions do not follow a clean path',
  near_bright_star: 'it sits in the glare of a bright star',
  near_saturated_star: 'it sits next to a star so bright it saturates the detector',
  beside_bright_source: 'it sits in the glare of a much brighter source',
  too_few_exposures_in_stack: 'too few images went into the stack it was seen in',
  near_edge: 'it is too close to the edge of the images',
  motion_explained_by_colour: 'the shift is explained by colour, not motion',
  depends_on_one_visit: 'the motion depends on a single visit',
  negative_parallax: 'the fit needs an impossible (negative) parallax',
  unphysical_parallax: 'the fit needs an impossible parallax, closer than the nearest star',
  disagrees_with_gaia: 'Gaia measured a different motion for this star',
  gaia_2016_shows_it_here: 'Gaia saw a star at this exact spot in 2016, so it has not moved',
  wise_2015_shows_it_here: 'WISE saw a source at this exact spot around 2015, so it has not moved',
  two_visits_only: 'it was seen in only two visits',
};

const INJ_LABEL: Record<string, string> = {
  recovered: 'Found', seen_not_moving: 'Seen, motion not proven', not_detected: 'Too faint', correctly_still: 'Still (correct)',
  false_alarm: 'False alarm', wrong_speed: 'Found, wrong speed',
};

function speed(m: HuntMover): number | null {
  return m.pm_arcsec_yr ?? m.stack_motion?.pm_arcsec_yr ?? null;
}

function moverLabel(m: HuntMover): { text: string; tone: string } {
  if (m.truth_match) return { text: 'Found blind', tone: 'hot' };
  if (m.catalogued_as) return { text: `Known mover (${m.catalogued_as.startsWith('Gaia') ? 'Gaia' : 'WISE'})`, tone: 'known' };
  if (m.class === 'candidate') return { text: 'Unexplained mover', tone: 'hot' };
  if (m.class === 'stack_candidate') return { text: 'Faint mover, stacked images only', tone: 'hot' };
  if (m.class === 'two_visit_candidate') return { text: 'Possible mover, two visits', tone: 'hot' };
  if (m.class === 'known_mover') return { text: 'Known star', tone: 'known' };
  return { text: 'Rejected', tone: 'muted' };
}

function fieldResult(f: HuntFieldRow): { text: string; tone: string } {
  const t = f.truth;
  const extra = f.movers.filter(m => !m.truth_match && !m.catalogued_as && ['candidate', 'stack_candidate', 'two_visit_candidate'].includes(m.class)).length;
  const tail = extra ? ` Plus ${extra} unexplained mover${extra > 1 ? 's' : ''}.` : '';
  if (f.kind === 'control') {
    return extra ? { text: `${extra} unexplained mover${extra > 1 ? 's' : ''} in blank sky.`, tone: 'hot' } : { text: 'Nothing unexplained moved. That is the right answer.', tone: 'ok' };
  }
  if (!t) return { text: `${f.n_motion_tested} sources tested.${tail}`, tone: 'muted' };
  if (t.recovered && t.measured_pm_arcsec_yr != null) {
    return { text: `Found it, moving ${t.measured_pm_arcsec_yr.toFixed(2)}″ a year. The catalogue says ${t.catalogue_pm_arcsec_yr.toFixed(2)}″.${tail}`, tone: 'ok' };
  }
  if (t.catalogue_pm_arcsec_yr < 0.2) return { text: `Not a fast mover (${t.catalogue_pm_arcsec_yr.toFixed(2)}″ a year), and nothing false was flagged.${tail}`, tone: 'muted' };
  if (t.detected) return { text: `Seen, but its motion did not pass the tests.${tail}`, tone: 'muted' };
  return { text: `Not found: too faint, or saturated.${tail}`, tone: 'muted' };
}

function HuntViewer({ id, focusId }: { id: string; focusId: string | null }) {
  const [doc, setDoc] = useState<HuntField | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [band, setBand] = useState('cold');
  const [vi, setVi] = useState(0);
  const [blink, setBlink] = useState(true);
  const [zoomed, setZoomed] = useState(true);
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => { huntApi.field(id).then(setDoc).catch(e => setError((e as Error).message)); }, [id]);

  const bands = useMemo(() => [...new Set(doc?.stacks.map(s => s.band) ?? [])], [doc]);
  const stacks = useMemo(() => (doc?.stacks ?? []).filter(s => s.band === (bands.includes(band) ? band : bands[0])), [doc, band, bands]);
  const current = stacks[Math.min(vi, stacks.length - 1)];

  useEffect(() => {
    if (!blink || stacks.length < 2) return;
    const t = window.setInterval(() => setVi(v => (v + 1) % stacks.length), 950);
    return () => window.clearInterval(t);
  }, [blink, stacks.length]);

  useEffect(() => {
    if (!doc || !current || !ref.current) return;
    let alive = true;
    loadFrame(current.data_url, doc.grid.dtype).then(data => {
      if (alive && ref.current) paint(ref.current, data, doc.grid.nx, doc.grid.ny, { colormap: 'ember', hiPct: 99.8, loSigma: 1.5 });
    }).catch(() => undefined);
    return () => { alive = false; };
  }, [doc, current]);

  if (error) return <p className="notice notice--bad">This field could not be loaded: {error}</p>;
  if (!doc) return <div className="hview"><div className="hview__stage" /></div>;

  const g = doc.grid;
  const cosd = Math.cos((g.dec0 * Math.PI) / 180);
  const gc = g as typeof g & { cx?: number; cy?: number };
  const frac = (ra: number, dec: number): [number, number] => [
    ((gc.cx ?? (g.nx - 1) / 2) - ((ra - g.ra0) * cosd * 3600) / g.pixel_arcsec + 0.5) / g.nx,
    ((gc.cy ?? (g.ny - 1) / 2) - ((dec - g.dec0) * 3600) / g.pixel_arcsec + 0.5) / g.ny,
  ];
  const movers = doc.sources.filter(s => MOVER_CLASSES.includes(s.class));
  const focus = movers.find(m => m.id === focusId) ?? movers.find(m => m.truth_match) ?? movers.find(m => m.class !== 'suspect') ?? null;
  const z = zoomed && focus ? Math.max(1, doc.fov_arcmin / 2.5) : 1;
  const [fx, fy] = focus && z > 1 ? frac(focus.ra, focus.dec) : [0.5, 0.5];
  const here = (m: typeof movers[number]): [number, number] => {
    const k = m.track?.find(t => t.visit === current?.visit);
    const [mx, my] = k ? frac(k.ra, k.dec) : frac(m.ra, m.dec);
    return [0.5 + (mx - fx) * z, 0.5 + (my - fy) * z];
  };
  const when = current ? new Date(current.time_utc).toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' }) : '';

  return (
    <div className="hview">
      <div className="hview__stage">
        <canvas ref={ref} style={{ transformOrigin: '0 0', transform: `translate(${(0.5 - fx * z) * 100}%, ${(0.5 - fy * z) * 100}%) scale(${z})` }}
          role="img" aria-label={`Stacked SPHEREx images of this field, ${when}`} />
        {movers.map(m => {
          const [x, y] = here(m);
          if (x < 0 || x > 1 || y < 0 || y > 1) return null;
          const tone = m.class === 'suspect' ? 'suspect' : m.class === 'known_mover' ? 'known' : 'hot';
          return <span key={m.id} className={`hview__mark hview__mark--${tone}`} style={{ left: `${x * 100}%`, top: `${y * 100}%` }} aria-hidden="true" />;
        })}
      </div>
      <div className="hview__bar">
        <div className="seg" role="group" aria-label="Visit">
          {stacks.map((s, i) => (
            <button key={s.id} className={`seg__btn${i === vi ? ' is-on' : ''}`} onClick={() => { setBlink(false); setVi(i); }}>{i + 1}</button>
          ))}
        </div>
        <button className={`button button--tiny ${blink ? 'button--primary' : 'button--ghost'}`} onClick={() => setBlink(b => !b)}>{blink ? 'Pause' : 'Blink'}</button>
        {focus && <button className="button button--tiny button--ghost" onClick={() => setZoomed(v => !v)}>{zoomed ? 'Whole field' : 'Zoom in'}</button>}
        {bands.length > 1 && (
          <button className="button button--tiny button--ghost" onClick={() => setBand(b => (b === 'cold' ? 'short' : 'cold'))}>
            {band === 'cold' ? 'Show 1–2 µm' : 'Show 4–5 µm'}
          </button>
        )}
        <span className="hview__label mono">{when} · {current?.wavelength_range_um.join('–')} µm · {current?.n_exposures} images</span>
      </div>
    </div>
  );
}

function FieldRow({ f }: { f: HuntFieldRow }) {
  const [open, setOpen] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const r = fieldResult(f);
  const shown = f.movers.slice().sort((a, b) => Number(!!b.truth_match) - Number(!!a.truth_match));
  return (
    <details className="hrow" onToggle={e => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>
        <span className="hrow__name">{f.title}<small>{f.notes ?? ''}</small></span>
        <span className="hrow__result"><span className={`dot dot--${r.tone === 'hot' ? 'hot' : r.tone === 'ok' ? 'ok' : 'warn'}`} aria-hidden="true" />{r.text}</span>
        <span className="hrow__chev" aria-hidden="true">›</span>
      </summary>
      {open && (
        <div className="hrow__body">
          <HuntViewer id={f.field_id} focusId={focus} />
          <div className="mtable">
            <p className="small muted">{f.n_exposures} images over {f.n_visits} visits ({Math.round(f.baseline_days)} days). {f.n_sources} sources found, {f.n_motion_tested} bright enough to test.</p>
            {shown.length === 0 && <p className="mrow">Nothing in this field passed the motion test.</p>}
            {shown.map(m => {
              const l = moverLabel(m);
              const v = speed(m);
              const why = m.flags.map(k => FLAG_TEXT[k]).filter(Boolean);
              return (
                <div className="mrow" key={m.id}>
                  <div className="mrow__top">
                    <span className={`badge2 badge2--${l.tone}`}>{l.text}</span>
                    <strong>{v != null ? `${v.toFixed(2)}″ a year` : 'motion not measured'}</strong>
                    <button className="button button--tiny button--ghost" onClick={() => setFocus(m.id)}>Show</button>
                    <Link className="button button--tiny button--ghost" href={CURATED.has(f.field_id) && m.truth_match ? `/explore?target=${f.field_id}` : `/explore?ra=${m.ra.toFixed(6)}&dec=${m.dec.toFixed(6)}&fov=6`}>Measure it</Link>
                  </div>
                  <p>
                    {m.truth_match && <>This is {m.truth_match}. The search was not told it was here. </>}
                    {m.decade_confirmed && m.catalogued_as && <>{m.catalogued_as.startsWith('Gaia') ? 'Gaia' : 'WISE'} recorded a source moving the same way years ago, and that source is now at this position ({m.catalogued_as}). </>}
                    {m.cold_only && <>Visible only at 4–5 µm: a cold object. </>}
                    {m.parallax_mas != null && m.parallax_err_mas != null && m.parallax_mas > 0 && m.parallax_mas / m.parallax_err_mas >= 5 && m.class !== 'suspect'
                      && <>Its distance, measured from these images alone: {(3261.6 / m.parallax_mas).toFixed(1)} light-years (between {(3261.6 / (m.parallax_mas + m.parallax_err_mas)).toFixed(1)} and {(3261.6 / (m.parallax_mas - m.parallax_err_mas)).toFixed(1)}). </>}
                    {m.class === 'known_mover' && m.gaia && <>Gaia DR3 {m.gaia.source_id} moves the same way. </>}
                    {m.class === 'suspect' && why.length > 0 && <>Rejected because {why.join('; ')}. </>}
                    {!m.truth_match && !m.catalogued_as && ['candidate', 'stack_candidate', 'two_visit_candidate'].includes(m.class) && <>No catalogue we checked explains it. A candidate, not a discovery. </>}
                    <span className="mono small dim">{m.ra.toFixed(5)}, {m.dec.toFixed(5)}{m.sigma != null ? ` · ${m.sigma >= 99 ? '>30' : m.sigma.toFixed(1)}σ` : ''}{m.n_native_positions ? ` · ${m.n_native_positions} positions` : ''}</span>
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </details>
  );
}

export function Hunt() {
  const [idx, setIdx] = useState<HuntIndex | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inj, setInj] = useState<HuntInjection | null>(null);
  useEffect(() => { huntApi.index().then(setIdx).catch(e => setError((e as Error).message)); huntApi.injection().then(setInj).catch(() => undefined); }, []);

  const groups = useMemo(() => {
    const f = idx?.fields ?? [];
    return {
      known: f.filter(x => x.kind !== 'control' && x.truth && x.truth.catalogue_pm_arcsec_yr >= 0.2),
      control: f.filter(x => x.kind === 'control' || !x.truth || x.truth.catalogue_pm_arcsec_yr < 0.2),
    };
  }, [idx]);
  const reach = idx?.reach;
  const rejected = idx?.classes.suspect ?? 0;

  return (
    <Page>
      <PageHero
        title="The Planet X hunt"
        lede="Seven searches, none told where in the image its object is: distant worlds by their parallax, cold worlds by their colours, asteroids by their motion, Planet Nine two ways, what has vanished since WISE, and cold neighbours of the Sun."
        img="/img/spherex-vela-wide.webp"
        alt="Stars and dark dust clouds in the Vela Molecular Ridge, imaged in infrared by SPHEREx"
        caption="The Vela Molecular Ridge, as NASA's SPHEREx sees it."
      />

      <DistantWorlds />
      <ColdSpec />
      <AsteroidHunt />
      <PlanetNineReach />
      <PlanetNineDeep />
      <VanishedPanel />

      <section className="band2" aria-labelledby="nb-h">
        <h2 className="test-h" id="nb-h"><span>Search 7</span>Cold neighbours of the Sun</h2>
        <p className="test-p">Nearby brown dwarfs and free-floating planets drift a few arcseconds a year. This search gets a patch of sky, finds every source, tests each one for motion, and only then looks it up.</p>
      </section>


      {error && <p className="notice">The hunt has not been run on this machine yet.</p>}
      {idx && (
        <>
          <div className="tiles">
            <div className="tile"><span className="tile__n">{idx.totals.fields}</span><span className="tile__t">patches of sky searched ({idx.totals.area_deg2.toFixed(1)} square degrees)</span></div>
            <div className="tile"><span className="tile__n">{idx.totals.motion_tested.toLocaleString('en-US')}</span><span className="tile__t">sources tested for motion</span></div>
            <div className="tile tile--hot"><span className="tile__n">{idx.recovery.n_recovered}<small> of {idx.recovery.n_known}</small></span><span className="tile__t">known movers found without being told</span></div>
            <div className="tile"><span className="tile__n">{idx.unexplained.length}</span><span className="tile__t">movers no catalogue explains</span></div>
          </div>

          <p className="verdict">
            {idx.unexplained.length === 0
              ? <><strong>No new world yet.</strong> Everything the search flagged as moving turned out to be a known star or brown dwarf, and {rejected} false alarm{rejected === 1 ? ' was' : 's were'} caught and rejected by the checks. For this much sky that is the expected result, and it shows the search does not invent discoveries.</>
              : <><strong>{idx.unexplained.length} mover{idx.unexplained.length > 1 ? 's are' : ' is'} not explained by any catalogue we checked.</strong> These are candidates, not discoveries. Each needs a second look before anyone should believe it.</>}
            {reach && <> In a single visit the search sees down to about {Math.round(reach.median_depth_ujy)} µJy at 4–5 µm, enough to glimpse a twin of WISE 0855 (the coldest known brown dwarf) out to about {Math.round(reach.reach_ly)} light-years. Proving that it moves takes more: see the limits below.</>}
          </p>

          {idx.unexplained.length > 0 && (
            <section className="band2">
              <h2 className="test-h"><span>Candidates</span>Movers nothing explains</h2>
              <div className="mtable" style={{ marginTop: 18 }}>
                {idx.unexplained.map(m => (
                  <div className="mrow" key={`${m.field_id}-${m.id}`}>
                    <div className="mrow__top">
                      <span className="badge2 badge2--hot">{moverLabel(m).text}</span>
                      <strong>{speed(m)?.toFixed(2)}″ a year</strong>
                      <span className="mono small dim">{m.ra.toFixed(5)}, {m.dec.toFixed(5)} · field {m.field_id}</span>
                      <Link className="button button--tiny button--ghost" href={`/explore?ra=${m.ra.toFixed(6)}&dec=${m.dec.toFixed(6)}&fov=6`}>Measure it</Link>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="band2">
            <h2 className="test-h"><span>Known movers</span>Could it find them blind?</h2>
            <p className="test-p">Each patch hides a nearby brown dwarf or free-floating planet. Open one to blink the images and see what the search circled.</p>
            <div className="hlist">{groups.known.map(f => <FieldRow key={f.field_id} f={f} />)}</div>
          </section>

          <section className="band2">
            <h2 className="test-h"><span>Controls</span>Sky where nothing should move</h2>
            <p className="test-p">Blank, well-studied fields, plus fields around stars too bright to measure. A mover here would be a false alarm.</p>
            <div className="hlist">{groups.control.map(f => <FieldRow key={f.field_id} f={f} />)}</div>
          </section>

          {inj && (
            <section className="band2">
              <h2 className="test-h"><span>Limits · synthetic test</span>How faint and how slow can it go?</h2>
              <p className="test-p">We hid sixteen fake cold sources in the real images of a blank field, then ran the search without telling it. These are not real objects.</p>
              <div className="igrid" role="table" aria-label="Which hidden test sources the blind search found">
                <div className="igrid__corner small dim" role="columnheader">speed ↓ · brightness →</div>
                {inj.fluxes_ujy.map(f => <div key={f} className="igrid__h mono small" role="columnheader">{f} µJy</div>)}
                {inj.speeds_arcsec_yr.map(v => (
                  <div key={v} className="igrid__row" role="row">
                    <div className="igrid__h mono small" role="rowheader">{v === 0 ? 'not moving' : `${v}″ a year`}</div>
                    {inj.fluxes_ujy.map(f => {
                      const r = inj.results.find(x => Math.abs(x.speed_arcsec_yr - v) < 1e-6 && Math.abs(x.flux_ujy - f) < 1e-6);
                      const o = r?.outcome ?? 'not_run';
                      return (
                        <div key={f} className={`igrid__cell igrid__cell--${o}`} role="cell">
                          <strong>{INJ_LABEL[o] ?? o}</strong>
                          {r?.measured_pm_arcsec_yr != null && o === 'recovered' && <span className="mono small">{r.measured_pm_arcsec_yr.toFixed(1)}″ a year</span>}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
              <p className="small dim" style={{ marginTop: 12 }}>{inj.n_exposures} real images over {inj.n_visits} visits. Fake sources shine only above 3.8 µm, like WISE 0855 (about 350 µJy, 8″ a year). Besides the fakes, the search reported {inj.other_movers_reported} movers in this field.</p>
            </section>
          )}

          <section className="band2 plain">
            <details className="more">
              <summary>How the search works</summary>
              <p><strong>1. Stack.</strong> All images from one visit are added together in three colour bands, so faint sources show up.</p>
              <p><strong>2. Detect and link.</strong> Every source in every visit is found. Sources that sit still are matched up. Sources that appear in one visit and vanish in the next are joined along straight lines.</p>
              <p><strong>3. Measure.</strong> Every source is measured in every single image on the original pixels, then tested: is it moving, at more than 5σ?</p>
              <p><strong>4. Check.</strong> A mover must look the same at short and long wavelengths, survive dropping any one visit, and must not have been at the same spot in Gaia (2016) or WISE (2015).</p>
            </details>
            <details className="more">
              <summary>Is this really a search for Planet Nine?</summary>
              <p>Not yet. A planet hundreds of times farther than Pluto would shift by many arcminutes between SPHEREx visits because of Earth's own motion, which is more sky than these small cut-outs cover, and it is expected to be far too faint for a single visit. This search is tuned for what SPHEREx can see today: cold brown dwarfs and free-floating planets within a few tens of light-years.</p>
            </details>
          </section>
        </>
      )}
    </Page>
  );
}
