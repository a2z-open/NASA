import { Fragment, useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent } from 'react';
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
const HERO = '/img/spherex-glow.webp';
const FOOT = '/img/pluto.webp';   // NASA PIA19952, Pluto in enhanced colour; the disk fills 85 % of the frame
const DISK = { cx: 0.496, cy: 0.489, d: 0.85 };

const Arrow = () => <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M2 7h10M8 3l4 4-4 4" /></svg>;
const Search = () => <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="8" cy="8" r="5.5" /><path d="M12.2 12.2 16 16" /></svg>;

const RING = '\u25CB';   // stands in for the "o" in "close", which is drawn as a ring

/** A sentence whose words go from grey to ink, one after another, as it scrolls up the screen. The fill runs
 *  on the browser's scroll timeline (CSS), so it needs no script and stays smooth. */
function Words({ text, as: Tag = 'span', className }: { text: string; as?: 'span' | 'p'; className: string }) {
  return (
    <Tag className={className} aria-hidden={Tag === 'span' ? true : undefined} aria-label={Tag === 'p' ? text : undefined}>
      {text.split(' ').map((w, i) => {
        const [a, b] = w.split(RING);
        return <Fragment key={i}><span className="e-w" aria-hidden="true" style={{ '--i': i } as CSSProperties}>{b === undefined ? w : <>{a}<span className="e-ring" />{b}</>}</span>{' '}</Fragment>;
      })}
    </Tag>
  );
}

/**
 * The footer: Pluto in its real colours, framed by a ring of light drawn in dots, like the Sun's corona in an
 * eclipse. Move the pointer and the planet drifts a little against its ring.
 */
function Lens() {
  const box = useRef<HTMLDivElement>(null);
  const cv = useRef<HTMLCanvasElement>(null);
  const eye = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current, c = cv.current, e = eye.current;
    if (!el || !c || !e) return;
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const g = { cx: 0, cy: 0, R: 0, fw: 1, fh: 1 };
    let x = 0, y = 0, tx = 0, ty = 0, raf = 0;

    const paint = () => { e.style.transform = `translate3d(${x}px, ${y}px, 0)`; };
    const layout = () => {
      const fw = el.clientWidth, fh = el.clientHeight;
      if (!fw || !fh) return;
      const phone = fw < 760;
      const R = phone ? Math.min(fw * 0.26, 116) : Math.min(fw * 0.13, fh * 0.21, 210);
      const cx = fw * 0.5, cy = phone ? Math.min(fh * 0.28, R * 2.5) : fh * 0.4;
      Object.assign(g, { cx, cy, R, fw, fh });

      // dots: full near the rim, shrinking outward; the reach changes with angle so it looks like a corona
      const S = Math.ceil(2 * (R * 2.15)), dpr = Math.min(window.devicePixelRatio || 1, 2);
      Object.assign(c.style, { width: `${S}px`, height: `${S}px`, left: `${cx - S / 2}px`, top: `${cy - S / 2}px` });
      c.width = Math.round(S * dpr); c.height = Math.round(S * dpr);
      const ctx = c.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, S, S);
      // a soft glow first, so the rim looks lit rather than printed
      const glow = ctx.createRadialGradient(S / 2, S / 2, R * 0.98, S / 2, S / 2, R * 1.55);
      glow.addColorStop(0, 'rgba(255,255,255,0.42)');
      glow.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, S, S);
      ctx.fillStyle = '#fff';
      // dots on a 45-degree screen, as in printed halftones
      const step = phone ? 5.5 : 7, N = Math.ceil(S / step), c45 = Math.SQRT1_2;
      for (let i = -N; i <= N; i++) {
        for (let j = -N; j <= N; j++) {
          const u = i * step, v = j * step, r = Math.hypot(u, v);
          if (r < R - step || r > S / 2) continue;
          const xx = S / 2 + (u - v) * c45, yy = S / 2 + (u + v) * c45;
          const th = Math.atan2(yy - S / 2, xx - S / 2);
          const n = 1 + 0.42 * Math.sin(3 * th + 0.6) + 0.26 * Math.sin(5 * th + 2.1) + 0.16 * Math.sin(9 * th + 4) + 0.1 * Math.sin(15 * th + 1.3);
          const t = (r - R) / (R * 0.62 * Math.max(0.3, n));
          if (t >= 1) continue;
          const I = Math.pow(1 - Math.max(0, t), 1.8);
          const rad = I > 0.8 ? step * 0.72 : (step / 2) * 1.1 * I;
          if (rad < 0.35) continue;
          ctx.beginPath(); ctx.arc(xx, yy, rad, 0, Math.PI * 2); ctx.fill();
        }
      }
      // the disk is drawn 3 % larger than the ring, so the ring's edge is clean planet, never black sky
      const size = (2 * R * 1.03) / DISK.d;
      Object.assign(e.style, { width: `${2 * R}px`, height: `${2 * R}px`, left: `${cx - R}px`, top: `${cy - R}px`, backgroundSize: `${size}px ${size}px`, backgroundPosition: `${R - DISK.cx * size}px ${R - DISK.cy * size}px` });
      paint();
    };
    const tick = () => {
      x += (tx - x) * 0.08; y += (ty - y) * 0.08;
      paint();
      raf = Math.abs(tx - x) + Math.abs(ty - y) > 0.1 ? requestAnimationFrame(tick) : 0;
    };
    const move = (ev: PointerEvent) => {
      if (still) return;
      const r = el.getBoundingClientRect();
      tx = ((ev.clientX - r.left) / g.fw - 0.5) * 18;
      ty = ((ev.clientY - r.top) / g.fh - 0.5) * 10;
      if (!raf) raf = requestAnimationFrame(tick);
    };
    const host = el.parentElement ?? el;
    const ro = new ResizeObserver(layout);
    ro.observe(el);
    host.addEventListener('pointermove', move);
    layout();
    return () => { ro.disconnect(); host.removeEventListener('pointermove', move); cancelAnimationFrame(raf); };
  }, []);

  return (
    <div className="e-lens" ref={box} aria-hidden="true">
      <canvas ref={cv} />
      <div className="e-lens__eye" ref={eye} style={{ backgroundImage: `url(${FOOT})` }} />
    </div>
  );
}

export function Home() {
  const [hunt, setHunt] = useState<HuntIndex | null>(null);
  const [worlds, setWorlds] = useState<DistantResults | null>(null);
  const [cold, setCold] = useState<ColdDoc | null>(null);
  const [p9x, setP9x] = useState<number | null>(null);   // how many times fainter than our deepest stack the predicted Planet Nine is
  const [q, setQ] = useState('');
  const [tab, setTab] = useState<'spot' | 'measure'>('spot');
  const [ink, setInk] = useState(false);
  const [menu, setMenu] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const root = useRef<HTMLDivElement>(null);
  const hero = useRef<HTMLElement>(null);

  useEffect(() => {
    huntApi.index().then(setHunt).catch(() => undefined);
    distantApi.results().then(setWorlds).catch(() => undefined);
    fetch('/api/coldspec').then(r => (r.ok ? r.json() : null)).then(setCold).catch(() => undefined);
    fetch('/api/how').then(r => (r.ok ? r.json() : null)).then((h: { deep: { injection: { distance_au: number; flux_ujy: number; n_measured: number; n_recovered: number }[] | null }[]; planet_nine?: { flux_ujy: number } } | null) => {
      if (!h?.planet_nine) return;
      const reach = h.deep.map(d => (d.injection ?? []).filter(r => r.distance_au === 550 && r.n_measured).sort((a, b) => a.flux_ujy - b.flux_ujy)
        .find(r => r.n_recovered / r.n_measured >= 0.5)?.flux_ujy).filter((v): v is number => typeof v === 'number');
      if (reach.length) setP9x(Math.min(...reach) / h.planet_nine.flux_ujy);
    }).catch(() => undefined);
    const t = window.setInterval(() => setNow(Date.now()), 20000);
    return () => window.clearInterval(t);
  }, []);

  // The opening picture shrinks on the browser's own scroll timeline (CSS), so it moves in step with the
  // scroll. Script only flips the top bar from white to ink, and drives the picture in browsers that lack
  // scroll timelines.
  useEffect(() => {
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const native = typeof CSS !== 'undefined' && CSS.supports('animation-timeline: view()');
    if (still) root.current?.classList.add('e--still');
    else if (!native) root.current?.classList.add('e--js');
    let raf = 0, wasInk = false;
    const run = () => {
      raf = 0;
      const H = window.innerHeight;
      const isInk = window.scrollY > H * 0.24;
      if (isInk !== wasInk) { wasInk = isInk; setInk(isInk); }
      const hs = hero.current;
      if (hs && !native && !still) {
        const r = hs.getBoundingClientRect(), dist = r.height - H;
        const p = dist > 0 ? Math.max(0, Math.min(1, -r.top / dist)) : 0;
        const t = Math.min(1, p / 0.65), e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        hs.style.setProperty('--e', e.toFixed(4));
        hs.style.setProperty('--fade', Math.min(1, p / 0.18).toFixed(3));
        hs.style.setProperty('--show', Math.max(0, Math.min(1, (p - 0.5) / 0.22)).toFixed(3));
      }
    };
    const kick = () => { if (!raf) raf = requestAnimationFrame(run); };
    run();
    window.addEventListener('scroll', kick, { passive: true });
    window.addEventListener('resize', kick);
    return () => { window.removeEventListener('scroll', kick); window.removeEventListener('resize', kick); cancelAnimationFrame(raf); };
  }, []);

  useEffect(() => {
    if (!menu) return;
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenu(false); };
    window.addEventListener('keydown', esc);
    document.body.style.overflow = 'hidden';
    return () => { window.removeEventListener('keydown', esc); document.body.style.overflow = ''; };
  }, [menu]);

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

  const nav = [['/map', 'Sky map'], ['/how', 'How'], ['/check', 'Check'], ['/hunt', 'Finds'], ['/proof', 'Proof']];
  const delay = (ms: number) => ({ '--d': `${ms}ms` } as CSSProperties);

  return (
    <div className="e" ref={root}>
      <header className={`e-top${ink ? ' is-ink' : ''}${menu ? ' is-menu' : ''}`}>
        <div className="e-ruler" aria-hidden="true" />
        <div className="e-top__in">
          <Wordmark />
          <nav aria-label="Main">
            {nav.map(([h, l]) => <Link key={h} href={h}>{l}</Link>)}
            <a className="e-top__cta" href="#try">Play</a>
          </nav>
          <button type="button" className="e-top__menu" aria-expanded={menu} aria-controls="e-menu" onClick={() => setMenu(v => !v)}>
            <span className="visually-hidden">{menu ? 'Close menu' : 'Open menu'}</span><i /><i />
          </button>
        </div>
      </header>
      <div id="e-menu" className={`e-menu${menu ? ' is-open' : ''}`} hidden={!menu}>
        {nav.map(([h, l]) => <Link key={h} href={h}>{l}</Link>)}
        <a href="#try" onClick={() => setMenu(false)}>Play the game</a>
      </div>

      <main id="main">
        {/* 1. The opening picture. It fills the screen, then settles into a card as you scroll. */}
        <section className="e-hero" ref={hero} aria-labelledby="hero-h">
          <div className="e-hero__stick">
            <div className="e-hero__frame">
              <div className="e-hero__pan">
                <img className="e-hero__img" src={HERO} alt="Illustration: the SPHEREx space telescope, seen as a silhouette above the glowing edge of Earth" {...({ fetchpriority: 'high' } as Record<string, string>)} />
              </div>
              <div className="e-hero__shade" />
            </div>
            <div className="e-hero__text">
              <h1 id="hero-h" className="e-hero__h">Help find<br /><em>Planet X.</em></h1>
              <p className="e-hero__sub">A game and a search engine, built on real photos from NASA's SPHEREx telescope.</p>
              <div className="e-hero__go">
                <Link className="e-btn e-btn--white" href="/map">Start hunting <Arrow /></Link>
              </div>
              <div className="e-hero__meta">
                <p className="e-label e-label--dot">SPHEREx · Day {days.toLocaleString('en-US')} in orbit · {utc} UTC</p>
              </div>
            </div>
            <p className="e-hero__beside">NASA's SPHEREx photographs the whole sky, twice a year.</p>
          </div>
        </section>

        {/* 2. The idea, in three plain sentences. */}
        <section className="e-sec e-said" aria-labelledby="said-h">
          <div className="e-wrap">
            <h2 id="said-h" className="e-said__h" aria-label="Two photos of the same sky. Whatever moved is close. That's parallax.">
              <Words className="e-said__l" text="Two photos of the same sky." />
              <Words className="e-said__l" text={`Whatever moved is cl${RING}se.`} />
              <Words className="e-said__l" text="That's parallax." />
            </h2>
            <p className="e-said__cap">Your two eyes do this all day. It's how you judge distance.</p>
          </div>
        </section>

        {/* 3. The sky as a line-drawn sphere. */}
        <section className="e-sec e-globe" aria-labelledby="gl-h">
          <div className="e-wrap e-globe__in">
            <div className="e-globe__text">
              <h2 id="gl-h" className="e-label e-label--dot">The sky map</h2>
              <Words as="p" className="e-fill" text="Every dot is a patch of sky we searched. The thick line is where Planet Nine might hide." />
              <div className="e-row">
                <Link className="e-btn e-btn--ink" href="/map">Open the sky map <Arrow /></Link>
              </div>
            </div>
            <div className="e-globe__ball">
              <SkyGlobe points={points} />
              <p className="e-label e-globe__hint">Drag to turn</p>
            </div>
          </div>
        </section>

        {/* 4. Try it: the game and the distance machine, in one split card with tabs. */}
        <section className="e-sec e-sec--tight" id="try" aria-labelledby="try-h">
          <div className="e-wrap">
            <div className="e-try rv">
              <div className="e-try__stage" role="tabpanel" id="how-far" aria-labelledby={`tab-${tab}`}>
                {tab === 'spot' ? <SpotGame onMeasure={() => setTab('measure')} /> : <HowFar />}
              </div>
              <div className="e-try__panel">
                <div className="e-tabs" role="tablist" aria-label="Choose what to try">
                  <button type="button" role="tab" id="tab-spot" aria-selected={tab === 'spot'} aria-controls="how-far" onClick={() => setTab('spot')}>Spot it</button>
                  <button type="button" role="tab" id="tab-measure" aria-selected={tab === 'measure'} aria-controls="how-far" onClick={() => setTab('measure')}>Measure it</button>
                </div>
                <h2 id="try-h" className="e-try__h">{tab === 'spot' ? 'Spot what moves.' : 'Close things jump more.'}</h2>
                <p className="e-try__p">{tab === 'spot'
                  ? 'Two real NASA photos of the same sky, days apart. Every star stays put. One dot hops. Tap it.'
                  : 'Hold up a thumb and wink each eye. It jumps; the far wall does not. Earth does the same from opposite sides of the Sun.'}</p>
                <div className="e-try__foot">
                  {tab === 'spot'
                    ? <button type="button" className="e-btn e-btn--line" onClick={() => setTab('measure')}>Next: how far? <Arrow /></button>
                    : <button type="button" className="e-btn e-btn--line" onClick={() => setTab('spot')}>Back to the game</button>}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 5. What the software found. */}
        <section className="e-sec" aria-labelledby="fd-h">
          <div className="e-wrap e-found">
            <div className="e-found__head">
              <p className="e-label e-label--dot">What it found</p>
              <h2 id="fd-h" className="e-found__h">No hints. Every answer checked against what astronomers already know.</h2>
              <p className="e-found__p">We gave the software real images and never told it where to look. Then we checked it against NASA's JPL and published catalogues.</p>
              <div className="e-row">
                <Link className="e-btn e-btn--ink" href="/how">How we find them <Arrow /></Link>
                <Link className="e-btn e-btn--line" href="/proof">See the proof <Arrow /></Link>
              </div>
            </div>
            <div className="e-cards">
              <Link className="e-card rv" href="/hunt">
                <span className="e-card__n">01</span>
                <span className="e-card__k">Makemake</span>
                <span className="e-card__v">{mk?.match ? mk.match.r_fit_au.toFixed(1) : '52.7'} AU</span>
                <span className="e-card__t">A dwarf planet, found by its motion. NASA JPL says {mk?.match ? mk.match.r_true_au.toFixed(1) : '52.7'} AU.</span>
              </Link>
              <Link className="e-card rv" href="/hunt" style={delay(80)}>
                <span className="e-card__n">02</span>
                <span className="e-card__k">Eris</span>
                <span className="e-card__v">{er?.match ? er.match.r_fit_au.toFixed(1) : '95.5'} AU</span>
                <span className="e-card__t">Too faint for one photo, so we stacked photos along its path. JPL says {er?.match ? er.match.r_true_au.toFixed(1) : '95.5'} AU.</span>
              </Link>
              <Link className="e-card rv" href="/hunt">
                <span className="e-card__n">03</span>
                <span className="e-card__k">Cold neighbours</span>
                <span className="e-card__v">{hunt ? `${hunt.recovery.n_recovered} of ${hunt.recovery.n_known}` : '13 of 19'}</span>
                <span className="e-card__t">Nearby brown dwarfs and stars, found by motion alone across {hunt ? hunt.totals.fields : 25} patches of sky.</span>
              </Link>
              {cold?.results && (
                <>
                  <Link className="e-card rv" href="/hunt#cs-h" style={delay(80)}>
                    <span className="e-card__n">04</span>
                    <span className="e-card__k">Machine learning</span>
                    <span className="e-card__v">{cold.cv.held_out.T_found} of {cold.cv.held_out.T_total}</span>
                    <span className="e-card__t">Known methane dwarfs our model recognised from SPHEREx's 102 colours alone, with {cold.cv.held_out.false_T} false alarms in {cold.cv.held_out.not_T_total}.</span>
                  </Link>
                  <Link className="e-card rv" href="/hunt#cs-h">
                    <span className="e-card__n">05</span>
                    <span className="e-card__k">{cold.wide?.candidates ? 'First spectra' : newCold > 0 ? 'New candidates' : 'Blind test'}</span>
                    <span className="e-card__v">{cold.wide?.candidates ? cold.wide.candidates.n_strong : newCold > 0 ? newCold : `${knownCold} of ${cold.results.n_candidates}`}</span>
                    <span className="e-card__t">{cold.wide?.candidates
                      ? 'Brown dwarfs a survey had only guessed from colours. SPHEREx shows their methane. We found no published spectrum of any of them.'
                      : newCold > 0
                        ? `Possible new cold worlds among ${cold.results.n_pass_quality.toLocaleString('en-US')} objects nobody had classified. Candidates, not confirmed discoveries.`
                        : `It flagged ${cold.results.n_candidates} of ${cold.results.n_pass_quality.toLocaleString('en-US')} unclassified objects. All were methane dwarfs astronomers had already typed.`}</span>
                  </Link>
                </>
              )}
              <Link className="e-card rv" href="/hunt" style={delay(cold?.results ? 80 : 0)}>
                <span className="e-card__n">{cold?.results ? '06' : '04'}</span>
                <span className="e-card__k">Planet Nine</span>
                <span className="e-card__v">Not yet.</span>
                <span className="e-card__t">{p9x
                  ? `If it exists, it is about ${Math.round(p9x)} times too faint, even after adding photos together. We show how faint we can see, instead of guessing.`
                  : 'If it exists, it is about 40 times too faint for these images. We show how faint we can see, instead of guessing.'}</span>
              </Link>
            </div>
          </div>
        </section>

        {/* 6. Two closing cards: one dark with a photo, one bright. */}
        <section className="e-sec e-sec--tight" aria-label="Get involved">
          <div className="e-wrap e-close">
            <div className="e-dark rv">
              <img src="/img/spherex-dust.webp" alt="" loading="lazy" decoding="async" />
              <div className="e-dark__in">
                <h2 className="e-dark__h">Help check the candidates.</h2>
                <p className="e-dark__p">Our search flags real objects that have no published spectrum. Look at one and tell us what you see. Ten seconds, no account.</p>
                <Link className="e-btn e-btn--white" href="/check">Check a candidate <Arrow /></Link>
              </div>
            </div>
            <div className="e-soft rv" style={{ backgroundImage: 'url(/img/spherex-glow-soft.webp)' }}>
              <div className="e-soft__text">
                <h2 className="e-soft__h">Go anywhere in the sky.</h2>
                <p className="e-soft__p">Type a star, planet or galaxy. We'll fly you there.</p>
              </div>
              <div className="e-soft__go">
                <form className="e-search" onSubmit={submit} role="search">
                  <Search />
                  <label className="visually-hidden" htmlFor="go-q">Star, planet or galaxy</label>
                  <input id="go-q" value={q} onChange={e => setQ(e.target.value)} placeholder="Try Pluto" autoComplete="off" spellCheck={false} />
                  <button className="e-btn e-btn--ink" type="submit">Fly there</button>
                </form>
                <div className="e-chips">{TRY.map(t => <button key={t} type="button" onClick={() => go(t)}>{t}</button>)}</div>
              </div>
            </div>
          </div>
        </section>

        {/* 7. A line that slides past as you scroll. */}
        <div className="e-marquee" aria-hidden="true">
          <div className="e-marquee__in">Look twice. Find what moves. Look twice. Find what moves.</div>
        </div>
      </main>

      <footer className="e-foot">
        <Lens />
        <div className="e-foot__in">
          <div className="e-foot__row">
            <div className="e-foot__say">
              <p>Look twice.</p>
              <Wordmark />
            </div>
            <div className="e-foot__cols">
              <div>
                <h3>Explore</h3>
                <Link href="/map">Sky map</Link>
                <Link href="/hunt">Finds</Link>
                <Link href="/how">How we find them</Link>
                <Link href="/explore">Image explorer</Link>
              </div>
              <div>
                <h3>Check us</h3>
                <Link href="/proof">Proof</Link>
                <Link href="/about">Sources and AI use</Link>
                <Link href="/deck">Seven slides</Link>
              </div>
            </div>
          </div>
          <div className="e-foot__base">
            <p>Images: NASA SPHEREx, from the NASA/IPAC Infrared Science Archive. Planet positions: NASA JPL Horizons. Photographs: NASA/JPL-Caltech; Pluto, NASA/JHUAPL/SwRI. Opening illustration of SPHEREx: supplied by the team.</p>
            <p>NASA Space Apps Challenge 2026, Seattle. Not affiliated with or endorsed by NASA.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
