import { useState } from 'react';
import { Footer, Header } from '../components/Shell.tsx';
import { FieldStill } from '../components/FieldImage.tsx';
import { SearchBox } from '../components/SearchBox.tsx';
import { Link, navigate } from '../router.tsx';
import { useTargets } from '../hooks.ts';
import type { Target } from '../api.ts';
import { date } from '../lib/format.ts';

const VERDICT_TONE: Record<string, string> = {
  known_source_recovered: 'supported', motion_supported: 'supported', variability_supported: 'supported',
  ultracool_candidate: 'supported', saturated: 'untestable', insufficient_evidence: 'untestable',
  possible_blend: 'tentative', artifact_suspected: 'not_supported', unmatched_follow_up: 'tentative',
};

export function TargetCard({ t, priority = false }: { t: Target; priority?: boolean }) {
  const href = `/explore?target=${t.slug}`;
  return (
    <article className="tcard">
      <Link href={href} className="tcard__link" aria-label={`Open ${t.title}`}>
        <div className="tcard__image">
          {t.field ? <FieldStill fieldId={t.field.field_id} frames={priority ? 10 : 6} alt={`Stacked SPHEREx exposures of the ${t.title} field`} /> : <div className="still" data-state="error"><span className="still__error">Not cached</span></div>}
          <span className="tcard__reticle" aria-hidden="true" />
        </div>
        <div className="tcard__body">
          <p className="tcard__kind">{t.kind}</p>
          <h3 className="tcard__title">{t.title}</h3>
          <p className="tcard__purpose">{t.purpose}</p>
          {t.headline && <p className={`tcard__verdict tone--${VERDICT_TONE[t.headline.verdict] ?? 'untestable'}`}>{t.headline.label}</p>}
          <p className="tcard__meta mono">
            {t.n_observations} exposures · {t.n_visits} visits{t.date_range ? ` · ${date(t.date_range[0])} – ${date(t.date_range[1])}` : ''}
          </p>
        </div>
      </Link>
    </article>
  );
}

export function Home() {
  const targets = useTargets();
  const [heroReady, setHeroReady] = useState(false);
  return (
    <>
      <Header />
      <main id="main">
        <section className="hero">
          <div className="hero__image" data-ready={heroReady}>
            <FieldStill fieldId="epsilon-indi-b" frames={24} detectors={[2, 3]} colormap="ember" alt="Stacked real SPHEREx exposures around Epsilon Indi B" onReady={() => setHeroReady(true)} />
          </div>
          <div className="hero__shade" />
          <div className="page__inner hero__inner">
            <p className="eyebrow">NASA SPHEREx · 0.75–5 <span className="nocase">µm</span> · real observations</p>
            <h1 className="hero__title">The universe moves.<br /><em>Find out why.</em></h1>
            <p className="hero__lede">Explore NASA's infrared sky, investigate moving objects and turn astronomical observations into scientific evidence.</p>
            <div className="hero__search">
              <SearchBox large label="Explore the sky" placeholder="Object name or RA Dec, e.g. 331.0966 −56.8006" />
            </div>
            <div className="hero__actions">
              <button className="button button--ghost" onClick={() => navigate('/explore?target=epsilon-indi-b')}>Try a known discovery →</button>
              <Link className="hero__lab" href="/lab">See a locked prediction meet new data</Link>
            </div>
            <p className="hero__caption">Background: mean of 24 SPHEREx exposures (1.1–2.4 µm) around Epsilon Indi B, reprojected for display.</p>
          </div>
        </section>

        <section className="page__inner home-targets" aria-labelledby="targets-h">
          <div className="section-head">
            <h2 id="targets-h">Five NASA test targets</h2>
            <p className="muted">Each opens a real investigation built from SPHEREx exposures. Where the data cannot support a measurement, the result says so.</p>
          </div>
          {targets.error && <p className="notice notice--bad">Targets could not be loaded: {targets.error}</p>}
          {targets.loading && <div className="tgrid">{Array.from({ length: 5 }, (_, i) => <div key={i} className="tcard tcard--skeleton" />)}</div>}
          {targets.data && <div className="tgrid">{targets.data.map((t, i) => <TargetCard key={t.slug} t={t} priority={i === 0} />)}</div>}
        </section>

        <section className="page__inner home-how">
          <ol className="steps">
            <li><span className="steps__n mono">01</span><h3>Watch the sky change</h3><p>Real exposures play in time order on a common north-up grid, with the wavelength of every frame shown.</p></li>
            <li><span className="steps__n mono">02</span><h3>Measure, don't eyeball</h3><p>Click a source: PARALLAX fits its position in every exposure on native pixels, then its proper motion and parallax.</p></li>
            <li><span className="steps__n mono">03</span><h3>Follow its light</h3><p>Flux is extracted where the source actually is in each exposure, then binned into a 0.75–5 µm spectrum and compared with templates.</p></li>
            <li><span className="steps__n mono">04</span><h3>Weigh the explanations</h3><p>Moving, variable, blended, artifact or known object: each hypothesis is marked supported, disfavoured or not yet testable.</p></li>
          </ol>
        </section>
      </main>
      <Footer />
    </>
  );
}
