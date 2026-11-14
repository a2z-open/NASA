import { useEffect, useState } from 'react';
import { Footer, Header } from '../components/Shell.tsx';
import { Starfield } from '../components/Starfield.tsx';
import { HeroBlink } from '../components/HeroBlink.tsx';
import { FieldStill } from '../components/FieldImage.tsx';
import { SearchBox } from '../components/SearchBox.tsx';
import { Link } from '../router.tsx';
import { useTargets } from '../hooks.ts';
import { api, huntApi, type HuntIndex, type Target, type ValidationReport } from '../api.ts';

const TONE: Record<string, string> = {
  known_source_recovered: 'ok', motion_supported: 'ok', variability_supported: 'ok', ultracool_candidate: 'cold',
  saturated: 'warn', insufficient_evidence: 'warn', possible_blend: 'warn', artifact_suspected: 'warn', unmatched_follow_up: 'hot',
};

/** Kept for the Explore landing state: one clickable line per NASA test target. */
export function TargetRow({ t }: { t: Target }) {
  return (
    <Link href={`/explore?target=${t.slug}`} className="row">
      <span className="row__name"><span className={`dot dot--${TONE[t.headline?.verdict ?? ''] ?? 'warn'}`} aria-hidden="true" />{t.title}</span>
      <span className="row__what">{t.headline?.label ?? t.kind}</span>
      <span className="row__go" aria-hidden="true">→</span>
    </Link>
  );
}

export function Home() {
  const targets = useTargets();
  const [val, setVal] = useState<ValidationReport | null>(null);
  const [hunt, setHunt] = useState<HuntIndex | null>(null);
  useEffect(() => {
    api.validation().then(setVal).catch(() => undefined);
    huntApi.index().then(setHunt).catch(() => undefined);
  }, []);
  const exp = val?.experiments.find(e => /indi/i.test(e.target)) ?? val?.experiments[0];
  const miss = exp?.result?.[exp.primary_model]?.residual_arcsec;
  const nc = val?.negative_controls;

  return (
    <>
      <Starfield />
      <Header />
      <main id="main">
        <section className="hero2">
          <div>
            <p className="kicker">Real NASA SPHEREx images</p>
            <h1 className="hero2__title">Find what <span>moves.</span></h1>
            <p className="hero2__lede">Pick any patch of the infrared sky. Watch it change over time, and measure what moved.</p>
            <SearchBox large label="Search" placeholder="A name or coordinates, e.g. 331.09 −56.80" />
            <div className="hero2__quick">
              <span>Try</span>
              <Link href="/explore?target=epsilon-indi-b">a moving star</Link>
              <Link href="/explore?target=wise-0855">the coldest brown dwarf</Link>
              <Link href="/hunt">the Planet X hunt</Link>
            </div>
          </div>
          <HeroBlink />
        </section>

        <section className="band" aria-label="Results so far">
          <div className="facts">
            <Link className="fact" href="/proof">
              <span className="fact__n">{miss != null ? `${miss.toFixed(3)}″` : '—'}</span>
              <span className="fact__t">How close our locked-in prediction landed to where the star really went.</span>
            </Link>
            <Link className="fact" href="/proof">
              <span className="fact__n">{nc ? `${nc.false_positives} of ${nc.n_measured}` : '—'}</span>
              <span className="fact__t">Still stars wrongly flagged as moving.</span>
            </Link>
            <Link className="fact" href="/hunt">
              <span className="fact__n">{hunt ? hunt.totals.motion_tested.toLocaleString('en-US') : '—'}</span>
              <span className="fact__t">Sources tested for motion in the Planet X hunt{hunt ? `, across ${hunt.totals.fields} fields` : ''}.</span>
            </Link>
          </div>
        </section>

        <section className="band" aria-labelledby="start-h">
          <div className="band__head"><h2 id="start-h">Start here</h2></div>
          <div className="cards">
            <Link className="card" href="/explore?target=epsilon-indi-b">
              <div className="card__img"><FieldStill fieldId="epsilon-indi-b" frames={10} detectors={[2, 3]} colormap="ember" alt="Stacked SPHEREx images around Epsilon Indi B" /></div>
              <div className="card__body">
                <h3>Watch a star cross the sky</h3>
                <p>Epsilon Indi B, a pair of brown dwarfs 12 light-years away.</p>
                <span className="card__go">Play the images →</span>
              </div>
            </Link>
            <Link className="card" href="/explore?target=wise-0855">
              <div className="card__img"><FieldStill fieldId="wise-0855" frames={10} detectors={[6]} colormap="ember" alt="Stacked SPHEREx images around WISE 0855" /></div>
              <div className="card__body">
                <h3>Meet the coldest brown dwarf</h3>
                <p>WISE 0855 is invisible until 4 µm. Then it appears.</p>
                <span className="card__go">See it appear →</span>
              </div>
            </Link>
            <Link className="card card--hunt" href="/hunt">
              <div className="card__img"><span aria-hidden="true">X</span></div>
              <div className="card__body">
                <h3>Hunt for Planet X</h3>
                <p>A blind search that tests every source it sees for motion.</p>
                <span className="card__go">See what it found →</span>
              </div>
            </Link>
          </div>
        </section>

        <section className="band" aria-labelledby="five-h">
          <div className="band__head">
            <h2 id="five-h">NASA's five test targets</h2>
            <Link href="/proof">How we tested it →</Link>
          </div>
          {targets.error && <p className="notice notice--bad">The targets could not be loaded: {targets.error}</p>}
          <div className="rows">{targets.data?.map(t => <TargetRow key={t.slug} t={t} />)}</div>
        </section>
      </main>
      <Footer />
    </>
  );
}
