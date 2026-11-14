import { Page } from '../components/Shell.tsx';
import { TargetCard } from './Home.tsx';
import { useTargets } from '../hooks.ts';

export function Targets() {
  const targets = useTargets();
  return (
    <Page>
      <header className="page-head">
        <p className="eyebrow">Target gallery</p>
        <h1>The five NASA test targets</h1>
        <p className="muted lede">The challenge names five objects that test different things: large proper motion, a substellar binary, an extremely cold moving world and two variable stars. Each card opens a real investigation. Saturated or undetected cases are reported as such.</p>
      </header>
      {targets.error && <p className="notice notice--bad">{targets.error}</p>}
      <div className="tgrid tgrid--wide">{targets.data?.map((t, i) => <TargetCard key={t.slug} t={t} priority={i === 0} />)}</div>
      <section className="notes">
        {targets.data?.map(t => (
          <div key={t.slug} className="notes__item">
            <h3>{t.title}</h3>
            <p className="small mono dim">{t.astrometry.source}</p>
            <ul className="bullets small">{t.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
          </div>
        ))}
      </section>
    </Page>
  );
}
