import { useEffect, useRef, useState } from 'react';
import { api, huntApi, type HaloResults, type HaloVariability, type HuntIndex, type ValidationReport } from '../api.ts';
import { HeroBlink } from '../components/HeroBlink.tsx';
import { FieldStill } from '../components/FieldImage.tsx';
import { Starfield } from '../components/Starfield.tsx';
import { Link } from '../router.tsx';

const TOTAL = 7;

function fade(h?: HaloVariability): { pct: number; sigma: number } | null {
  const later = (h?.visits ?? []).slice(1).filter(v => v.sigma != null && v.n >= 5);
  const big = later.slice().sort((a, b) => Math.abs(b.ratio - 1) - Math.abs(a.ratio - 1))[0];
  return big ? { pct: Math.round((big.ratio - 1) * 100), sigma: big.sigma ?? 0 } : null;
}

/** Seven slides for the Space Apps demo. Every number is read live from the app's own results. */
export function Deck() {
  const [val, setVal] = useState<ValidationReport | null>(null);
  const [hunt, setHunt] = useState<HuntIndex | null>(null);
  const [halo, setHalo] = useState<HaloResults | null>(null);
  const [n, setN] = useState(1);
  const root = useRef<HTMLDivElement>(null);
  const goRef = useRef<(d: number) => void>(() => undefined);

  useEffect(() => {
    api.validation().then(setVal).catch(() => undefined);
    huntApi.index().then(setHunt).catch(() => undefined);
    huntApi.halo().then(setHalo).catch(() => undefined);
  }, []);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const go = (d: number) => {
      const i = Math.max(0, Math.min(TOTAL - 1, Math.round(el.scrollTop / el.clientHeight) + d));
      const top = i * el.clientHeight;
      el.scrollTo({ top, behavior: 'smooth' });
      // smooth scrolling does not run in a background tab or with reduced motion: make sure we arrive
      window.setTimeout(() => { if (Math.abs(el.scrollTop - top) > 4) el.scrollTo({ top }); }, 700);
    };
    const key = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'IFRAME') return;
      if (['ArrowDown', 'ArrowRight', 'PageDown', ' '].includes(e.key)) { e.preventDefault(); go(1); }
      if (['ArrowUp', 'ArrowLeft', 'PageUp'].includes(e.key)) { e.preventDefault(); go(-1); }
    };
    const scroll = () => setN(Math.round(el.scrollTop / el.clientHeight) + 1);
    goRef.current = go;
    window.addEventListener('keydown', key);
    el.addEventListener('scroll', scroll, { passive: true });
    return () => { window.removeEventListener('keydown', key); el.removeEventListener('scroll', scroll); };
  }, []);

  const exp = val?.experiments.find(e => /indi/i.test(e.target)) ?? val?.experiments[0];
  const miss = exp?.result?.primary?.residual_arcsec;
  const stays = exp?.result?.stationary_null?.residual_arcsec;
  const nc = val?.negative_controls;
  const rdra = fade(halo?.targets['r-draconis']);
  const rwaur = fade(halo?.targets['rw-aurigae']);
  const barn = fade(halo?.targets['barnards-star']);
  const rejected = hunt?.classes.suspect ?? 0;

  return (
    <div className="deck" ref={root}>
      <Starfield />
      <Link href="/" className="deck__home" aria-label="Leave the slides">PARALLAX</Link>
      <span className="deck__count mono" aria-hidden="true">{n} / {TOTAL}</span>
      <div className="deck__nav">
        <button className="icon" onClick={() => goRef.current(-1)} disabled={n <= 1} aria-label="Previous slide">‹</button>
        <button className="icon" onClick={() => goRef.current(1)} disabled={n >= TOTAL} aria-label="Next slide">›</button>
      </div>

      <section className="slide slide--split">
        <div>
          <p className="kicker">NASA Space Apps 2026 · Planet X and SPHEREx · Seattle</p>
          <h1 className="slide__title slide__title--xl">Find what <span>moves.</span></h1>
          <p className="slide__lede">Pick any patch of NASA's infrared sky. Watch it change. Measure what moved. Then prove it.</p>
        </div>
        <HeroBlink />
      </section>

      <section className="slide slide--split">
        <div>
          <p className="kicker">What we built</p>
          <h2 className="slide__title">NASA asked for a tool that plays the sky like a video.</h2>
          <ul className="slide__list">
            <li>Type a name or coordinates. Real SPHEREx images line up and play.</li>
            <li>Blink, subtract or add them. Gaia and WISE overlays.</li>
            <li>Click any dot: its motion, distance and spectrum, measured.</li>
            <li>Every view is a link you can share or embed.</li>
          </ul>
        </div>
        <div className="slide__frame"><iframe title="Live PARALLAX viewer" src="/explore?target=epsilon-indi-b&embed=1" loading="lazy" /></div>
      </section>

      <section className="slide">
        <p className="kicker">Proof 1</p>
        <h2 className="slide__title">We predicted where a star would be, before the images existed.</h2>
        <div className="slide__nums">
          <div><b>{miss != null ? `${miss.toFixed(3)}″` : '—'}</b><span>how close the locked prediction landed</span></div>
          <div><b>{stays != null ? `${stays.toFixed(2)}″` : '—'}</b><span>how far off “it stays put” was</span></div>
          <div><b>2027</b><span>new predictions are locked now, for images NASA has not taken yet</span></div>
        </div>
        <p className="slide__foot">The prediction was fingerprinted and committed before the new images were downloaded. Epsilon Indi B, {exp?.heldout_usable ?? ''} new images.</p>
      </section>

      <section className="slide">
        <p className="kicker">Proof 2 · the Planet X hunt</p>
        <h2 className="slide__title">A blind search that finds what it should, and nothing it should not.</h2>
        <div className="slide__nums">
          <div><b>{hunt ? hunt.totals.motion_tested.toLocaleString('en-US') : '—'}</b><span>sources tested for motion in {hunt?.totals.fields ?? '—'} patches of sky</span></div>
          <div><b>{hunt ? `${hunt.recovery.n_recovered} of ${hunt.recovery.n_known}` : '—'}</b><span>known movers found without being told where they are</span></div>
          <div><b>{hunt ? hunt.unexplained.length : '—'}</b><span>movers no catalogue explains{hunt ? `; ${rejected} false alarm${rejected === 1 ? '' : 's'} caught and rejected` : ''}</span></div>
        </div>
        <p className="slide__foot">Every mover is checked against where Gaia and WISE saw the sky ten years ago. {nc ? `Separately, ${nc.false_positives} of ${nc.n_measured} still stars were flagged as moving.` : ''}</p>
      </section>

      <section className="slide slide--split">
        <div>
          <p className="kicker">NASA's hardest targets</p>
          <h2 className="slide__title">A world too cold to see, and stars too bright to measure.</h2>
          <ul className="slide__list">
            <li><strong>WISE 0855</strong>, the coldest known brown dwarf: invisible below 3.8 µm, clear at 4–5 µm.</li>
            <li><strong>R Draconis</strong> {rdra ? `${rdra.pct < 0 ? 'faded' : 'brightened'} by ${Math.abs(rdra.pct)}% (${rdra.sigma.toFixed(0)}σ)` : 'changed brightness'} and <strong>RW Aurigae</strong> {rwaur ? `by ${Math.abs(rwaur.pct)}% (${rwaur.sigma.toFixed(0)}σ)` : 'too'}. Both saturate the camera, so we measured the ring of light around them.</li>
            <li>The control, Barnard's Star, stayed flat{barn ? ` (${Math.abs(barn.pct)}%)` : ''}.</li>
          </ul>
        </div>
        <div className="slide__still"><FieldStill fieldId="wise-0855" frames={12} detectors={[6]} colormap="ember" alt="Stacked SPHEREx images at 4.4 to 5 micrometres around WISE 0855" /><p className="small dim">Real SPHEREx images at 4.4–5.0 µm around WISE 0855.</p></div>
      </section>

      <section className="slide">
        <p className="kicker">Honest by design</p>
        <h2 className="slide__title">It says what it cannot do.</h2>
        <ul className="slide__list slide__list--cols">
          <li>Three of NASA's five targets saturate. The app says so instead of forcing a number.</li>
          <li>No new world yet. Unexplained movers are called candidates, never discoveries.</li>
          <li>Planet Nine itself would be too faint and would move too far between visits for this search.</li>
          <li>No AI runs inside the app. AI helped write the code, and that is disclosed.</li>
        </ul>
        <p className="slide__foot">Data: NASA SPHEREx DR1 and QR3 (IRSA), ESA Gaia DR3, CatWISE2020. Brown-dwarf templates: SPIFF (Gagné et al. 2026).</p>
      </section>

      <section className="slide">
        <p className="kicker">Why it matters</p>
        <h2 className="slide__title slide__title--xl">Anyone can <span>check a claim.</span></h2>
        <p className="slide__lede">Pluto was found by blinking two photographs. SPHEREx photographs the whole sky, again and again, in 102 colours. PARALLAX lets anyone look, measure, and show their evidence.</p>
        <p className="slide__links"><Link className="button button--primary" href="/explore">Try it</Link> <Link className="button button--ghost" href="/hunt">The hunt</Link> <Link className="button button--ghost" href="/proof">The proof</Link></p>
      </section>
    </div>
  );
}
