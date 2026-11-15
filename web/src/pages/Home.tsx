import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Wordmark } from '../components/Shell.tsx';
import { SpotGame } from '../components/SpotGame.tsx';
import { HowFar } from '../components/HowFar.tsx';
import { SkyGlobe, type GlobePoint } from '../components/SkyGlobe.tsx';
import { Link, navigate } from '../router.tsx';
import { huntApi, type HuntIndex, type Target } from '../api.ts';
import { distantApi, type DistantResults } from './Distant.tsx';
import '../home.css';

/** One clickable line per NASA test target (used by lists elsewhere). */
export function TargetRow({ t }: { t: Target }) {
  return (
    <Link href={`/explore?target=${t.slug}`} className="row">
      <span className="row__name">{t.title}</span>
      <span className="row__what">{t.headline?.label ?? t.kind}</span>
      <span className="row__go" aria-hidden="true">→</span>
    </Link>
  );
}

interface ColdDoc {
  cv: { held_out: { rms_subtypes: number; T_found: number; T_total: number; false_T: number; not_T_total: number } };
  results: { n_pass_quality: number; n_candidates: number; candidates: { name: string; verdict: string }[] } | null;
  vetting: { candidates: { name: string; verdict: string }[] } | null;
  wide: { n_pass_quality: number; candidates: { n: number; n_strong: number } | null } | null;
}

const LAUNCH = Date.UTC(2025, 2, 12, 3, 10);   // SPHEREx lifted off 11 March 2025, 8:10 p.m. Pacific
const TRY = ['Pluto', 'Mars', 'Orion Nebula', 'Vega', 'Andromeda Galaxy'];
const SAY = 'Two photos of the same sky. Whatever moved is close. How far it jumped tells us how far away it is.';
const Arrow = () => <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M2 7h10M8 3l4 4-4 4" /></svg>;
const Search = () => <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="8" cy="8" r="5.5" /><path d="M12.2 12.2 16 16" /></svg>;

/** A sentence that fills in, word by word, as it scrolls through the screen. */
function ScrollWords({ text }: { text: string }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const words = useMemo(() => text.split(' '), [text]);
  const [lit, setLit] = useState(0);
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setLit(words.length); return; }
    const on = () => {
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect(), vh = window.innerHeight;
      const p = (vh * 0.86 - r.top) / (r.height + vh * 0.3);
      setLit(Math.round(Math.max(0, Math.min(1, p)) * words.length));
    };
    on();
    window.addEventListener('scroll', on, { passive: true });
    window.addEventListener('resize', on);
    return () => { window.removeEventListener('scroll', on); window.removeEventListener('resize', on); };
  }, [words.length]);
  return <p ref={ref} className="e-say__big" aria-label={text}>{words.map((w, i) => <span key={i} aria-hidden="true" className={i < lit ? 'is-on' : ''}>{w} </span>)}</p>;
}

export function Home() {
  const [hunt, setHunt] = useState<HuntIndex | null>(null);
  const [worlds, setWorlds] = useState<DistantResults | null>(null);
  const [cold, setCold] = useState<ColdDoc | null>(null);
  const [q, setQ] = useState('');
  const [tab, setTab] = useState<'spot' | 'measure'>('spot');
  const [light, setLight] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const hero = useRef<HTMLElement>(null);

  useEffect(() => {
    huntApi.index().then(setHunt).catch(() => undefined);
    distantApi.results().then(setWorlds).catch(() => undefined);
    fetch('/api/coldspec').then(r => (r.ok ? r.json() : null)).then(setCold).catch(() => undefined);
    const tick = window.setInterval(() => setNow(Date.now()), 20000);
    return () => window.clearInterval(tick);
  }, []);

  // the opening photo shrinks into a card over the first 72 % of a screen of scrolling
  useEffect(() => {
    const on = () => {
      const vh = window.innerHeight;
      const p = Math.max(0, Math.min(1, window.scrollY / (vh * 0.72)));
      hero.current?.style.setProperty('--p', p.toFixed(4));
      setLight(p > 0.9);
    };
    on();
    window.addEventListener('scroll', on, { passive: true });
    window.addEventListener('resize', on);
    return () => { window.removeEventListener('scroll', on); window.removeEventListener('resize', on); };
  }, []);

  const body = (name: string) => worlds?.bodies.find(b => b.title === name && b.passed && b.match) ?? null;
  const mk = body('Makemake'), er = body('Eris');
  const go = (text: string) => { if (text.trim()) navigate(`/map?q=${encodeURIComponent(text.trim())}`); };
  const submit = (e: FormEvent) => { e.preventDefault(); go(q); };
  const coldVerdicts = (cold?.results?.candidates ?? []).map(c => cold?.vetting?.candidates.find(x => x.name === c.name)?.verdict ?? c.verdict);
  const newCold = coldVerdicts.filter(x => x.startsWith('new candidate')).length;
  const knownCold = coldVerdicts.filter(x => x.startsWith('already')).length;
  const days = Math.floor((now - LAUNCH) / 86400000);
  const utc = new Date(now).toISOString().slice(11, 16);

  const points = useMemo<GlobePoint[]>(() => [
    ...(hunt?.fields ?? []).map(f => ({ ra: f.ra, dec: f.dec })),
    { ra: 201.3, dec: 20.6, label: 'Makemake', big: true },
    { ra: 26.8, dec: -0.2, label: 'Eris', big: true },
    { ra: 133.79, dec: -7.24, label: 'Coldest brown dwarf', big: true },
    { ra: 331.1, dec: -56.8, label: 'Epsilon Indi B', big: true },
  ], [hunt]);

  return (
    <div className="e">
      <header className={`e-top${light ? ' is-light' : ''}`}>
        <Wordmark />
        <nav aria-label="Main">
          <Link href="/map">Sky map</Link>
          <Link href="/check">Check</Link>
          <Link href="/hunt">Finds</Link>
          <Link href="/proof">Proof</Link>
          <a className="e-top__cta" href="#try">Play</a>
        </nav>
      </header>

      <main id="main">
        <section className="e-hero" ref={hero} aria-labelledby="hero-h">
          <div className="e-hero__stick">
            <div className="e-hero__frame">
              <div className="e-hero__pic"><img src="/img/spherex-orbit.webp" alt="NASA's SPHEREx space telescope in orbit above Earth (illustration: NASA/JPL-Caltech)" fetchPriority="high" /></div>
              <div className="e-hero__shade" />
            </div>
            <div className="e-hero__text">
              <h1 id="hero-h" className="e-hero__h">Find what moves in the sky.</h1>
              <p className="e-hero__sub">NASA's SPHEREx telescope photographs the whole sky. PARALLAX compares the photos, spots what moved, and measures how far away it is.</p>
              <div className="e-hero__go">
                <a className="e-btn e-btn--white" href="#try">Play the game <Arrow /></a>
                <Link className="e-btn e-btn--glass" href="/map">Open the sky map</Link>
              </div>
            </div>
            <div className="e-hero__meta">
              <p className="e-label e-label--dot">SPHEREx · Day {days.toLocaleString('en-US')} in orbit · {utc} UTC</p>
              <p className="e-label e-hero__stamp">NASA Space Apps<br />Seattle, USA 2026</p>
            </div>
          </div>
        </section>

        <section className="e-sec" aria-label="How it works, in one sentence">
          <div className="e-wrap e-say">
            <p className="e-say__lead">This is parallax. It's how your two eyes judge distance.</p>
            <ScrollWords text={SAY} />
          </div>
        </section>

        <section className="e-sec" id="try" aria-labelledby="try-h" style={{ paddingTop: 0 }}>
          <div className="e-wrap">
            <div className="e-try__head">
              <div>
                <p className="e-label e-label--dot">Try it</p>
                <h2 id="try-h" className="e-try__h">{tab === 'spot' ? 'Spot what moves.' : 'Close things jump more.'}</h2>
                <p className="e-try__p">{tab === 'spot'
                  ? 'Two real NASA photos of the same sky, 3½ days apart. Every star stays put. One dot hops. Tap it.'
                  : 'Hold up a thumb and wink each eye: it jumps, the far wall does not. Earth does the same from opposite sides of the Sun. Pick a world.'}</p>
              </div>
              <div className="e-tabs" role="tablist" aria-label="Choose what to try">
                <button type="button" role="tab" aria-selected={tab === 'spot'} onClick={() => setTab('spot')}>Spot it</button>
                <button type="button" role="tab" aria-selected={tab === 'measure'} onClick={() => setTab('measure')}>Measure it</button>
              </div>
            </div>
            <div className="e-stage" role="tabpanel" id="how-far">
              {tab === 'spot' ? <SpotGame onMeasure={() => setTab('measure')} /> : <HowFar />}
            </div>
          </div>
        </section>

        <section className="e-sec" aria-labelledby="gl-h" style={{ paddingTop: 0 }}>
          <div className="e-wrap e-globe">
            <div>
              <p className="e-label e-label--dot">The sky map</p>
              <h2 id="gl-h" className="e-globe__h">The whole sky, in 102 colours of infrared.</h2>
              <p className="e-globe__p">Every dot is a patch PARALLAX searched. The thick line is where Planet Nine is predicted. Drag the sphere, then open the real map.</p>
              <div className="e-globe__go">
                <Link className="e-btn e-btn--ink" href="/map">Open the sky map <Arrow /></Link>
              </div>
            </div>
            <div>
              <SkyGlobe points={points} />
              <p className="e-label e-globe__hint" style={{ fontSize: 11 }}>Drag to turn</p>
            </div>
          </div>
        </section>

        <section className="e-sec" aria-labelledby="fd-h" style={{ paddingTop: 0 }}>
          <div className="e-wrap e-found">
            <div>
              <p className="e-label e-label--dot">What it found</p>
              <h2 id="fd-h" className="e-found__h">No hints. Every answer checked against NASA's JPL.</h2>
              <p className="e-found__p">We gave the software real images and never told it where to look.</p>
            </div>
            <div className={`e-cards${cold?.results ? ' e-cards--3' : ''}`}>
              <Link className="e-card" href="/hunt">
                <span className="e-card__n">01</span>
                <span className="e-card__k">Makemake</span>
                <span className="e-card__v">{mk?.match ? mk.match.r_fit_au.toFixed(1) : '52.7'} AU</span>
                <span className="e-card__t">A dwarf planet, found by its motion. NASA JPL says {mk?.match ? mk.match.r_true_au.toFixed(1) : '52.7'} AU.</span>
              </Link>
              <Link className="e-card" href="/hunt">
                <span className="e-card__n">02</span>
                <span className="e-card__k">Eris</span>
                <span className="e-card__v">{er?.match ? er.match.r_fit_au.toFixed(1) : '95.5'} AU</span>
                <span className="e-card__t">Too faint for one photo, so we stacked photos along its path. JPL says {er?.match ? er.match.r_true_au.toFixed(1) : '95.5'} AU.</span>
              </Link>
              <Link className="e-card" href="/hunt">
                <span className="e-card__n">03</span>
                <span className="e-card__k">Cold neighbours</span>
                <span className="e-card__v">{hunt ? `${hunt.recovery.n_recovered} of ${hunt.recovery.n_known}` : '13 of 19'}</span>
                <span className="e-card__t">Nearby brown dwarfs and stars, found by motion alone across {hunt ? hunt.totals.fields : 25} patches of sky.</span>
              </Link>
              {cold?.results && (
                <>
                  <Link className="e-card" href="/hunt#cs-h">
                    <span className="e-card__n">04</span>
                    <span className="e-card__k">Machine learning</span>
                    <span className="e-card__v">{cold.cv.held_out.T_found} of {cold.cv.held_out.T_total}</span>
                    <span className="e-card__t">Known methane dwarfs our model recognised from SPHEREx's 102 colours alone, with {cold.cv.held_out.false_T} false alarms in {cold.cv.held_out.not_T_total}.</span>
                  </Link>
                  <Link className="e-card" href="/hunt#cs-h">
                    <span className="e-card__n">05</span>
                    <span className="e-card__k">{cold.wide?.candidates ? 'First spectra' : newCold > 0 ? 'New candidates' : 'Blind test'}</span>
                    <span className="e-card__v">{cold.wide?.candidates ? cold.wide.candidates.n_strong : newCold > 0 ? newCold : `${knownCold} of ${cold.results.n_candidates}`}</span>
                    <span className="e-card__t">{cold.wide?.candidates
                      ? 'Brown dwarfs that a survey had only guessed from colours. SPHEREx shows their methane, and no spectrum of them was ever published. To confirm with a big telescope.'
                      : newCold > 0
                        ? `Possible new cold worlds among ${cold.results.n_pass_quality.toLocaleString('en-US')} objects nobody had classified. Candidates, not confirmed discoveries.`
                        : `It flagged ${cold.results.n_candidates} of ${cold.results.n_pass_quality.toLocaleString('en-US')} unclassified objects. All were methane dwarfs astronomers had already typed. No new world yet.`}</span>
                  </Link>
                </>
              )}
              <Link className="e-card" href="/hunt">
                <span className="e-card__n">{cold?.results ? '06' : '04'}</span>
                <span className="e-card__k">Planet Nine</span>
                <span className="e-card__v">Not yet.</span>
                <span className="e-card__t">If it exists, it is about 40 times too faint for these images. We show how faint we can see, instead of guessing.</span>
              </Link>
            </div>
          </div>
        </section>

        <section className="e-sec" aria-labelledby="hp-h" style={{ paddingTop: 0 }}>
          <div className="e-wrap e-help">
            <div>
              <p className="e-label e-label--dot">Your turn</p>
              <h2 id="hp-h" className="e-try__h">Help check the candidates.</h2>
            </div>
            <div>
              <p className="e-try__p" style={{ marginTop: 0 }}>Our search flags real objects that nobody has classified. Look at one and tell us what you see. It takes ten seconds, needs no account, and your answer is saved with everyone else's.</p>
              <div className="e-globe__go"><Link className="e-btn e-btn--ink" href="/check">Check a candidate <Arrow /></Link></div>
            </div>
          </div>
        </section>

        <section className="e-sec e-go" aria-labelledby="go-h" style={{ paddingTop: 0 }}>
          <div className="e-wrap">
            <p className="e-label">Sky map</p>
            <h2 id="go-h" className="e-go__h">Go anywhere.</h2>
            <p className="e-go__p">Type a star, planet or galaxy. We'll fly you there.</p>
            <form className="e-search" onSubmit={submit} role="search">
              <Search />
              <label className="visually-hidden" htmlFor="go-q">Star, planet or galaxy</label>
              <input id="go-q" value={q} onChange={e => setQ(e.target.value)} placeholder="Try Pluto" autoComplete="off" spellCheck={false} />
              <button className="e-btn e-btn--ink" type="submit">Fly there</button>
            </form>
            <div className="e-chips">{TRY.map(t => <button key={t} type="button" onClick={() => go(t)}>{t}</button>)}</div>
          </div>
        </section>
      </main>

      <footer className="e-foot">
        <div className="e-foot__pic"><img src="/img/pluto-horizon.webp" alt="Pluto's mountains and hazy sky, photographed by NASA's New Horizons" loading="lazy" /></div>
        <div className="e-foot__in">
          <p className="e-foot__big">Look twice.</p>
          <div className="e-foot__row">
            <div><Wordmark /></div>
            <div>
              <h3>Explore</h3>
              <Link href="/map">Sky map</Link>
              <Link href="/hunt">Finds</Link>
              <Link href="/explore">Image explorer</Link>
            </div>
            <div>
              <h3>Check us</h3>
              <Link href="/proof">Proof</Link>
              <Link href="/about">Sources and AI use</Link>
              <Link href="/deck">Seven slides</Link>
            </div>
            <div>
              <p>Images: NASA SPHEREx, from the NASA/IPAC Infrared Science Archive. Planet positions: NASA JPL Horizons. Photographs: NASA/JPL-Caltech; Pluto, NASA/JHUAPL/SwRI.</p>
              <p>A NASA Space Apps Challenge 2026 project, Seattle. Not affiliated with or endorsed by NASA.</p>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
