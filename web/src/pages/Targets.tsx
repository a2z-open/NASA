import { Page } from '../components/Shell.tsx';
import { TargetRow } from './Home.tsx';
import { useTargets } from '../hooks.ts';

export function Targets() {
  const targets = useTargets();
  return (
    <Page>
      <header className="page-head">
        <p className="eyebrow">Targets</p>
        <h1>NASA's five test targets</h1>
        <p className="lede">Pick one to play its images.</p>
      </header>
      {targets.error && <p className="notice notice--bad">{targets.error}</p>}
      <div className="rows">{targets.data?.map(t => <TargetRow key={t.slug} t={t} />)}</div>
    </Page>
  );
}
