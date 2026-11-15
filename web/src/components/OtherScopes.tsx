import { useEffect, useState } from 'react';

interface Row { key: string; name: string; agency: string; light: string; archive: string; n: number; first_year: number | null; last_year: number | null }
interface Preview { telescope: string; instrument: string; target: string; year: number | null; url: string }
interface Doc {
  telescopes: Row[]; n_telescopes: number; n_observations: number; previews: Preview[]; unanswered: string[];
  not_counted: { collection: string; n: number; why: string }[]; links: { mast: string; heasarc: string; cadc: string }; radius_arcmin: number; note: string;
}

const yr = (a: number | null, b: number | null) => (a == null ? '' : Math.floor(a) === Math.floor(b ?? a) ? String(Math.floor(a)) : `${Math.floor(a)}–${Math.floor(b ?? a)}`);

/** Which other telescopes have looked at one spot: NASA MAST, NASA HEASARC and Canada's CADC, asked live (pipeline/archives.py). */
export function OtherScopes({ ra, dec, auto = false }: { ra: number; dec: number; auto?: boolean }) {
  const [doc, setDoc] = useState<Doc | null>(null);
  const [state, setState] = useState<'idle' | 'asking' | 'done' | 'error'>(auto ? 'asking' : 'idle');
  const ask = () => {
    setState('asking');
    fetch(`/api/telescopes?ra=${ra.toFixed(5)}&dec=${dec.toFixed(5)}&radius_arcmin=3`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Doc) => { setDoc(d); setState('done'); })
      .catch(() => setState('error'));
  };
  useEffect(() => { setDoc(null); setState(auto ? 'asking' : 'idle'); if (auto) ask(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [ra, dec]);

  if (state === 'idle') {
    return <button type="button" className="os-ask" onClick={ask}>What other telescopes saw here</button>;
  }
  if (state === 'asking') {
    return <p className="os-wait" role="status">Asking NASA's MAST and HEASARC archives and Canada's CADC. This can take up to a minute.</p>;
  }
  if (state === 'error' || !doc) {
    return <p className="os-wait" role="status">The archives did not answer. <button type="button" className="os-link" onClick={ask}>Try again</button></p>;
  }
  return (
    <div className="os">
      <p className="os-hd"><b>{doc.n_telescopes ? `${doc.n_telescopes} other telescopes` : 'No other telescope'}</b> pointed within {doc.radius_arcmin}′ of here{doc.n_telescopes ? `, ${doc.n_observations.toLocaleString('en-US')} times` : ''}.</p>
      {doc.telescopes.length > 0 && (
        <ul className="os-list">
          {doc.telescopes.map(r => (
            <li key={r.key}>
              <span><b>{r.name}</b><small>{r.light} · {r.agency}</small></span>
              <span className="os-n">{r.n.toLocaleString('en-US')}<small>{yr(r.first_year, r.last_year)}</small></span>
            </li>
          ))}
        </ul>
      )}
      {doc.previews.length > 0 && (
        <div className="os-pics">
          {doc.previews.slice(0, 6).map(p => (
            <figure key={p.url}>
              <img src={p.url} alt={`${p.telescope} ${p.instrument} image, ${p.year ? Math.floor(p.year) : ''}`} loading="lazy" />
              <figcaption>{p.telescope} · {p.instrument.split('/')[0]} · {p.year ? Math.floor(p.year) : ''}</figcaption>
            </figure>
          ))}
        </div>
      )}
      {doc.unanswered.length > 0 && <p className="os-small">Did not answer in time: {doc.unanswered.join('; ')}. That is not the same as "never observed".</p>}
      <p className="os-small">
        Counts as each archive lists them. Not counted: {doc.not_counted.length ? doc.not_counted.map(c => `${c.n} ${c.collection} (${c.why})`).join(', ') : 'nothing'}.
        {' '}<a href={doc.links.mast} target="_blank" rel="noreferrer">Open in MAST</a>
      </p>
    </div>
  );
}
