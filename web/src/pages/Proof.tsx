import { Fragment, useEffect, useState } from 'react';
import { api, huntApi, type HuntIndex, type ValidationReport } from '../api.ts';
import { Page } from '../components/Shell.tsx';
import { Link } from '../router.tsx';
import { humanize, num } from '../lib/format.ts';
import { Experiments } from './Lab.tsx';
import { ControlsScatter, InjectionGrid, TargetsTable, THRESHOLD_LABELS } from './Method.tsx';

/** One page that answers "why should I believe this?" in three tests. */
export function Proof() {
  const [d, setD] = useState<ValidationReport | null>(null);
  const [hunt, setHunt] = useState<HuntIndex | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.validation().then(setD).catch(e => setError((e as Error).message));
    huntApi.index().then(setHunt).catch(() => undefined);
  }, []);
  const nc = d?.negative_controls;
  return (
    <Page>
      <header className="page-head">
        <p className="eyebrow">Proof</p>
        <h1>Don't take our word for it.</h1>
        <p className="lede">Three tests. Each one could have failed, and each uses only real SPHEREx images.</p>
      </header>

      <section className="band2" aria-labelledby="t1">
        <h2 className="test-h" id="t1"><span>Test 1</span>Predict where a star will be, before the images exist</h2>
        <p className="test-p">We measured a star's motion from earlier images, locked a prediction with a time-stamp, and only then downloaded the new images.</p>
        <Experiments />
      </section>

      <section className="band2" aria-labelledby="t2">
        <h2 className="test-h" id="t2"><span>Test 2</span>Don't cry wolf</h2>
        <p className="test-p">Stars that Gaia says are not moving should not be flagged as moving.</p>
        {error && <p className="notice">The validation report has not been generated yet.</p>}
        {nc && (
          <>
            <div className="tiles tiles--3">
              <div className="tile"><span className="tile__n">{nc.n_measured}</span><span className="tile__t">still stars measured</span></div>
              <div className="tile tile--hot"><span className="tile__n">{nc.false_positives}</span><span className="tile__t">wrongly flagged as moving</span></div>
              <div className="tile"><span className="tile__n">{num(nc.pull_std, 2)}</span><span className="tile__t">error-bar check (1.00 is perfect)</span></div>
            </div>
            <details className="more">
              <summary>See every control star</summary>
              <p className="small muted">{nc.description}</p>
              <ControlsScatter results={nc.results} sigma={nc.thresholds?.pm_over_error ?? 5} />
            </details>
          </>
        )}
      </section>

      <section className="band2" aria-labelledby="t3">
        <h2 className="test-h" id="t3"><span>Test 3</span>Find a mover without being told where it is</h2>
        <p className="test-p">The blind search is given a patch of sky and nothing else. Afterwards we check whether it found the known mover hiding there.</p>
        {hunt ? (
          <div className="tiles tiles--3">
            <div className="tile tile--hot"><span className="tile__n">{hunt.recovery.n_recovered}<small> of {hunt.recovery.n_known}</small></span><span className="tile__t">known movers found blind</span></div>
            <div className="tile"><span className="tile__n">{hunt.totals.motion_tested.toLocaleString('en-US')}</span><span className="tile__t">sources tested for motion</span></div>
            <div className="tile"><span className="tile__n">{hunt.unexplained.length}</span><span className="tile__t">movers no catalogue explains</span></div>
          </div>
        ) : <p className="muted">The hunt results are loading.</p>}
        <p style={{ marginTop: 18 }}><Link className="button button--primary" href="/hunt">Open the Planet X hunt</Link></p>
      </section>

      {d && (
        <section className="band2" aria-labelledby="t4">
          <h2 className="test-h" id="t4"><span>Scorecard</span>NASA's five test targets</h2>
          <p className="test-p">Three of the five are too bright for SPHEREx and saturate. We report that instead of forcing a number.</p>
          <TargetsTable targets={d.targets} />
          {d.extra_targets && d.extra_targets.length > 0 && (
            <details className="more">
              <summary>One extra target we added</summary>
              <TargetsTable targets={d.extra_targets} />
            </details>
          )}
          {d.injections && (
            <details className="more">
              <summary>How faint can it go? (synthetic test sources)</summary>
              <InjectionGrid inj={d.injections} />
            </details>
          )}
          <details className="more">
            <summary>The rules, fixed before any result was looked at</summary>
            <dl className="kv small">
              {Object.entries(d.thresholds).filter(([k]) => k !== 'note').map(([k, val]) => (
                <Fragment key={k}><dt>{THRESHOLD_LABELS[k] ?? humanize(k)}</dt><dd className="mono">{String(val)}</dd></Fragment>
              ))}
            </dl>
          </details>
          <details className="more">
            <summary>What this does not prove</summary>
            <ul className="bullets small">{d.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
          </details>
        </section>
      )}
    </Page>
  );
}
