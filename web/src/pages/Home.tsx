import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Footer, Header } from '../components/Shell.tsx';
import { Starfield } from '../components/Starfield.tsx';
import { HeroBlink } from '../components/HeroBlink.tsx';
import { SearchBox } from '../components/SearchBox.tsx';
import { Link } from '../router.tsx';
import { useTargets } from '../hooks.ts';
import { api, huntApi, type HuntIndex, type Target, type ValidationReport } from '../api.ts';

const TONE: Record<string, string> = {
  known_source_recovered: 'ok', motion_supported: 'ok', variability_supported: 'ok', ultracool_candidate: 'cold',
  saturated: 'warn', insufficient_evidence: 'warn', possible_blend: 'warn', artifact_suspected: 'warn', unmatched_follow_up: 'hot',
};

/** One clickable line per NASA test target (used by lists elsewhere). */
export function TargetRow({ t }: { t: Target }) {
  return (
    <Link href={`/explore?target=${t.slug}`} className="row">
      <span className="row__name"><span className={`dot dot--${TONE[t.headline?.verdict ?? ''] ?? 'warn'}`} aria-hidden="true" />{t.title}</span>
      <span className="row__what">{t.headline?.label ?? t.kind}</span>
      <span className="row__go" aria-hidden="true">→</span>
    </Link>
  );
}

const POINTS: [string, string][] = [
  ['Play', 'Every image of one patch of sky, in time order, like a short film.'],
  ['Blink', 'Flip between two dates. Whatever moved, jumps.'],
  ['Subtract', 'One date minus another. Only the change is left.'],
  ['Add', 'Stack the images to see fainter things.'],
  ['102 colours', 'Each image shows its true infrared wavelength.'],
  ['Any width', 'Zoom from 2 to 30 arcminutes across.'],
  ['Overlays', 'Gaia stars, and what WISE saw there in 2015.'],
  ['Measure', 'Click a dot for its motion, distance and spectrum.'],
  ['Share', 'The coordinates live in the link. Embed it anywhere.'],
];

const delay = (ms: number) => ({ '--d': `${ms}ms` }) as CSSProperties;

export function Home() {
  const targets = useTargets();
  const [val, setVal] = useState<ValidationReport | null>(null);
  const [hunt, setHunt] = useState<HuntIndex | null>(null);
  const hero = useRef<HTMLElement>(null);
  useEffect(() => {
    api.validation().then(setVal).catch(() => undefined);
    huntApi.index().then(setHunt).catch(() => undefined);
  }, []);

  // The planet drifts a little against the stars as the pointer and the page move: parallax.
  useEffect(() => {
    const el = hero.current;
    if (!el || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const onScroll = () => { el.style.setProperty('--sy', String(Math.min(window.scrollY, 1400))); };
    const onMove = (e: PointerEvent) => {
      el.style.setProperty('--px', (e.clientX / window.innerWidth - 0.5).toFixed(3));
      el.style.setProperty('--py', (e.clientY / window.innerHeight - 0.5).toFixed(3));
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => { window.removeEventListener('scroll', onScroll); window.removeEventListener('pointermove', onMove); };
  }, []);

  const exp = val?.experiments.find(e => /indi/i.test(e.target)) ?? val?.experiments[0];
  const miss = exp?.result?.primary?.residual_arcsec;
  const found = hunt ? `${hunt.recovery.n_recovered} of ${hunt.recovery.n_known}` : '—';
  const unexplained = hunt ? hunt.unexplained.length : null;

  return (
    <>
      <Starfield />
      <Header />
      <main id="main" className="hm">
        <section className="hm-hero" ref={hero}>
          <div className="hm-hero__text">
            <h1>Find what<br />moves.</h1>
            <p className="hm-hero__lede">PARALLAX plays real NASA SPHEREx images of any patch of sky, so anything that moved stands out. Then it measures it.</p>
            <SearchBox large label="Search the sky" placeholder="A star name, or RA and Dec" />
            <p className="hm-hero__try">
              Or start with <Link href="/explore?target=epsilon-indi-b">a star that moves</Link>, <Link href="/explore?target=wise-0855">the coldest brown dwarf</Link> or <Link href="/hunt">the Planet X hunt</Link>.
            </p>
          </div>
          <figure className="hm-hero__planet">
            <img src="/img/pluto.webp" alt="Pluto, photographed by NASA's New Horizons spacecraft in 2015" fetchPriority="high" />
          </figure>
          <p className="hm-hero__cap">Pluto, the first Planet X. Found in 1930 by blinking two photographs of the same sky.</p>
        </section>

        <section className="hm-blink" aria-labelledby="bl-h">
          <div className="hm-blink__text">
            <h2 id="bl-h" className="rv">This star moved.</h2>
            <p className="rv" style={delay(80)}>Two real SPHEREx images of Epsilon Indi B, taken 17 months apart. Every other star stays put. This one does not.</p>
            <Link className="button button--primary rv" style={delay(160)} href="/explore?target=epsilon-indi-b">Measure it yourself</Link>
          </div>
          <div className="rv" style={delay(120)}><HeroBlink /></div>
        </section>

        <section className="hm-stats" aria-labelledby="st-h">
          <h2 id="st-h" className="hm-stats__h rv">Checked before it is claimed.</h2>
          <Link className="hstat hstat--a rv" href="/proof">
            <span className="hstat__n">{miss != null ? `${miss.toFixed(3)}″` : '—'}</span>
            <span className="hstat__t">How far our locked prediction landed from where the star really went. One SPHEREx pixel is 6″ wide.</span>
          </Link>
          <Link className="hstat hstat--b rv" style={delay(90)} href="/hunt">
            <span className="hstat__n">{found}</span>
            <span className="hstat__t">Known fast movers the blind search found by itself.</span>
          </Link>
          <Link className="hstat hstat--c rv" style={delay(180)} href="/hunt">
            <span className="hstat__n">{unexplained ?? '—'}</span>
            <span className="hstat__t">Movers no catalogue could explain. No new planet yet, and we say so.</span>
          </Link>
        </section>

        <section className="hm-tools" aria-labelledby="tl-h">
          <figure className="hm-tools__fig rv">
            <img src="/img/spherex-vela.webp" alt="Stars and glowing dust in the Vela Molecular Ridge, imaged in infrared by SPHEREx" loading="lazy" decoding="async" />
            <figcaption>The Vela Molecular Ridge, as SPHEREx sees it.</figcaption>
          </figure>
          <div className="hm-tools__body">
            <h2 id="tl-h" className="rv">Everything NASA asked for.</h2>
            <ul className="points">
              {POINTS.map(([t, d], i) => (
                <li key={t} className="rv" style={delay((i % 3) * 70)}><strong>{t}</strong><span>{d}</span></li>
              ))}
            </ul>
            <Link className="button button--primary rv" href="/explore">Open the explorer</Link>
          </div>
        </section>

        <section className="hm-board" aria-labelledby="tg-h">
          <div className="tileb tileb--head rv">
            <h2 id="tg-h">NASA's five test targets</h2>
            <p>The challenge named five hard objects. This is how each one came out.</p>
          </div>
          {targets.error && <p className="notice notice--bad">The targets could not be loaded: {targets.error}</p>}
          {targets.data?.map((t, i) => (
            <Link key={t.slug} className="tileb rv" style={delay((i % 4) * 60)} href={`/explore?target=${t.slug}`}>
              <strong>{t.title}</strong>
              <span>{t.headline?.label ?? t.kind}</span>
            </Link>
          ))}
          <Link className="tileb tileb--any rv" href="/explore">
            <strong>Anywhere else</strong>
            <span>Any name or coordinates, fetched live from NASA's archive.</span>
          </Link>
        </section>

        <section className="hm-doors" aria-label="How we check ourselves">
          <Link className="door rv" href="/hunt">
            <img src="/img/wise-sky-centre.webp" alt="The centre of the Milky Way in infrared, from NASA's WISE map of the whole sky" loading="lazy" decoding="async" />
            <h2>The Planet X hunt</h2>
            <p>{hunt ? `${hunt.totals.fields} patches of sky. ${hunt.totals.motion_tested.toLocaleString('en-US')} sources tested for motion.` : 'A blind search of real SPHEREx fields.'} Nothing told it where to look.</p>
            <span className="door__go">See what it found</span>
          </Link>
          <Link className="door rv" style={delay(120)} href="/proof">
            <img src="/img/neptune.webp" alt="Neptune, photographed by NASA's Voyager 2 in 1989" loading="lazy" decoding="async" />
            <h2>Predict first. Look after.</h2>
            <p>Neptune was found in 1846 right where the maths said it would be. We lock our predictions before the images exist.</p>
            <span className="door__go">See the proof</span>
          </Link>
        </section>

        <section className="hm-close" aria-labelledby="cl-h">
          <figure className="hm-close__fig"><img src="/img/pluto-horizon.webp" alt="Pluto's mountains and haze, backlit by the Sun, seen by New Horizons as it flew past" loading="lazy" decoding="async" /></figure>
          <div className="hm-close__text">
            <h2 id="cl-h" className="rv">Pick your patch of sky.</h2>
            <p className="rv" style={delay(80)}>Any name, any coordinates. Real images from NASA's archive in about a minute.</p>
            <div className="rv" style={delay(160)}><SearchBox label="Search" placeholder="A star name, or RA and Dec" /></div>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
