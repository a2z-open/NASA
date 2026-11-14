import { Fragment, useEffect, useState } from 'react';
import { api, huntApi, type Forecast, type HaloResults, type HaloVariability, type HuntIndex, type ValidationReport } from '../api.ts';
import { Page, PageHero } from '../components/Shell.tsx';
import { Link } from '../router.tsx';
import { humanize, num } from '../lib/format.ts';
import { Experiments } from './Lab.tsx';
import { ControlsScatter, InjectionGrid, TargetsTable, THRESHOLD_LABELS } from './Method.tsx';

/** One page that answers "why should I believe this?" in three tests. */
export function Proof() {
  const [d, setD] = useState<ValidationReport | null>(null);
  const [hunt, setHunt] = useState<HuntIndex | null>(null);
  const [halo, setHalo] = useState<HaloResults | null>(null);
  const [fc, setFc] = useState<Forecast[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.validation().then(setD).catch(e => setError((e as Error).message));
    huntApi.index().then(setHunt).catch(() => undefined);
    huntApi.halo().then(setHalo).catch(() => undefined);
    huntApi.forecasts().then(r => setFc(r.forecasts)).catch(() => undefined);
  }, []);
  const nc = d?.negative_controls;
  return (
    <Page>
      <PageHero
        title="Don't take our word for it."
        lede="Neptune was found in 1846 right where the maths said it would be. We hold PARALLAX to the same kind of test: say first, look after."
        img="/img/neptune.webp"
        alt="Neptune, photographed by NASA's Voyager 2 in 1989"
        caption="Neptune, from Voyager 2."
      />

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

      {halo && (
        <section className="band2" aria-labelledby="t4h">
          <h2 className="test-h" id="t4h"><span>Test 4</span>Measure a star that is too bright to measure</h2>
          <p className="test-p">Two of NASA's five targets are variable stars, and both saturate SPHEREx. We measure the ring of light around each star instead, and check the trick on stars that do not vary.</p>
          <div className="tiles tiles--3">
            <HaloTile name="R Draconis" slug="r-draconis" h={halo.targets['r-draconis']} />
            <HaloTile name="RW Aurigae" slug="rw-aurigae" h={halo.targets['rw-aurigae']} />
            <div className="tile">
              <span className="tile__n">{halo.control_summary.n_flagged_variable}<small> of {halo.control_summary.n_with_comparison + 1}</small></span>
              <span className="tile__t">steady bright stars wrongly called variable (Barnard's Star and {halo.control_summary.n_with_comparison} others)</span>
            </div>
          </div>
        </section>
      )}

      {fc.length > 0 && (
        <section className="band2" aria-labelledby="t5">
          <h2 className="test-h" id="t5"><span>Test 5 · still open</span>Predictions for images that do not exist yet</h2>
          <p className="test-p">Locked today, for dates SPHEREx has not observed. When NASA releases the next images, anyone can check them.</p>
          <div className="hlist">{fc.map(f => <ForecastCard key={f.target} f={f} />)}</div>
        </section>
      )}

      {d && (
        <section className="band2" aria-labelledby="t4">
          <h2 className="test-h" id="t4"><span>Scorecard</span>NASA's five test targets</h2>
          <p className="test-p">Three of the five are too bright for SPHEREx and saturate. We say so, and measure the two variable stars from their halo instead.</p>
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


function HaloTile({ name, slug, h }: { name: string; slug: string; h?: HaloVariability }) {
  const later = (h?.visits ?? []).slice(1).filter(v => v.sigma != null && v.n >= 5);
  const big = later.slice().sort((a, b) => Math.abs(b.ratio - 1) - Math.abs(a.ratio - 1))[0];
  if (!h || !big) return <div className="tile"><span className="tile__n">—</span><span className="tile__t">{name}: not measured</span></div>;
  const pct = Math.round((big.ratio - 1) * 100);
  return (
    <Link className="tile tile--hot" href={`/explore?target=${slug}`} style={{ textDecoration: 'none' }}>
      <span className="tile__n">{pct > 0 ? '+' : '−'}{Math.abs(pct)}%</span>
      <span className="tile__t">{name} {pct < 0 ? 'faded' : 'brightened'} between visits ({(big.sigma ?? 0).toFixed(1)}σ)</span>
    </Link>
  );
}


const longDate = (iso: string) => new Date(iso).toLocaleDateString('en-US', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });

function ForecastCard({ f }: { f: Forecast }) {
  const p = f.predictions.find(x => x.date_utc.startsWith('2027-04')) ?? f.predictions[0];
  return (
    <details className="hrow">
      <summary>
        <span className="hrow__name">{f.title}<small>locked {longDate(f.locked_utc)}</small></span>
        <span className="hrow__result">
          On {longDate(p.date_utc)} it should be <strong>{p.offset_from_stays_here_arcsec.toFixed(1)}″</strong> from where it is now, at{' '}
          <span className="mono">{p.ra_deg.toFixed(5)}, {p.dec_deg.toFixed(5)}</span> (± {Math.max(p.sigma_ra_arcsec, p.sigma_dec_arcsec).toFixed(2)}″).
        </span>
        <span className="hrow__chev" aria-hidden="true">›</span>
      </summary>
      <div className="hrow__body" style={{ gridTemplateColumns: 'minmax(0, 1fr)' }}>
        <p className="small muted">{f.model_note} Fitted to {f.data_used.n_usable_positions} positions. When this was locked, the newest SPHEREx image of this field in NASA's archive was taken on {longDate(f.archive_at_lock.latest_exposure_utc)}.</p>
        <dl className="kv small">
          <dt>Fingerprint (SHA-256)</dt><dd className="mono hash">{f.sha256}</dd>
          <dt>Git commit</dt><dd className="mono">{f.commit ? `${f.commit.hash.slice(0, 10)} · ${f.commit.time}` : 'not committed yet'}</dd>
          <dt>Pass rule</dt><dd>{f.criterion}</dd>
        </dl>
        <div className="table-wrap">
          <table className="table table--dense">
            <thead><tr><th>Date</th><th>RA (deg)</th><th>Dec (deg)</th><th>± RA (″)</th><th>± Dec (″)</th><th>From today's position (″)</th></tr></thead>
            <tbody>
              {f.predictions.map(x => (
                <tr key={x.date_utc}><td>{x.date_utc.slice(0, 10)}</td><td className="mono">{x.ra_deg.toFixed(6)}</td><td className="mono">{x.dec_deg.toFixed(6)}</td>
                  <td className="mono">{x.sigma_ra_arcsec.toFixed(3)}</td><td className="mono">{x.sigma_dec_arcsec.toFixed(3)}</td><td className="mono">{x.offset_from_stays_here_arcsec.toFixed(2)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </details>
  );
}
