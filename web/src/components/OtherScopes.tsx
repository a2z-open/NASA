import { useEffect, useState } from 'react';

const SOURCES = [
  { key: 'mast', label: 'MAST', scope: 'Hubble, Webb, Pan-STARRS and more', href: 'https://mast.stsci.edu/portal/Mashup/Clients/Mast/Portal.html' },
  { key: 'heasarc', label: 'HEASARC', scope: 'selected X-ray missions', href: 'https://heasarc.gsfc.nasa.gov/xamin/' },
  { key: 'cadc', label: 'CADC', scope: 'NEOSSat', href: 'https://www.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/en/search/' },
] as const;
type Source = typeof SOURCES[number]['key'];
type Coverage = 'complete' | 'partial' | 'unavailable';
interface Row { key: string; name: string; agency: string; light: string; archive: string; n: number; first_year: number | null; last_year: number | null }
interface Preview { telescope: string; instrument: string; target: string; year: number | null; url: string }
interface Doc {
  telescopes: Row[]; n_telescopes: number; n_observations: number; previews: Preview[]; unanswered: string[];
  not_counted: { collection: string; n: number; why: string }[]; links: Record<Source, string>; radius_arcmin: number;
  coverage?: Record<Source, Coverage>; from_cache?: boolean; note: string;
}

const yr = (a: number | null, b: number | null) => (a == null ? '' : Math.floor(a) === Math.floor(b ?? a) ? String(Math.floor(a)) : `${Math.floor(a)}–${Math.floor(b ?? a)}`);
const count = (n: number) => n.toLocaleString('en-US');

function ArchiveLinks({ coords, doc }: { coords: string; doc?: Doc }) {
  return (
    <div className="os-small os-links" aria-label="Archive sources">
      {SOURCES.map(({ key, label, href, scope }) => {
        const state = doc?.coverage?.[key];
        return <span key={key}><a href={doc?.links[key] ?? href + (key === 'mast' ? `?searchQuery=${encodeURIComponent(coords)}` : '')}
          target="_blank" rel="noreferrer" title={scope}>{label}</a>{state === 'unavailable' ? ' (unavailable)' : state === 'partial' ? ' (partial)' : ''}</span>;
      })}
    </div>
  );
}

function ScopePreview({ preview: p }: { preview: Preview }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  return (
    <figure>
      <a href={p.url} target="_blank" rel="noreferrer">
        <img src={p.url} alt={`${p.telescope} archive preview${p.target ? ` of ${p.target}` : ''}`} loading="lazy" onError={() => setFailed(true)} />
      </a>
      <figcaption>{p.telescope} · {p.instrument.split('/')[0]}{p.year ? ` · ${Math.floor(p.year)}` : ''}</figcaption>
    </figure>
  );
}

/** Live archive matches for a fixed area on the sky. */
export function OtherScopes({ ra, dec, auto = false }: { ra: number; dec: number; auto?: boolean }) {
  const coords = `${ra.toFixed(5)} ${dec.toFixed(5)}`;
  const query = `ra=${ra.toFixed(5)}&dec=${dec.toFixed(5)}&radius_arcmin=3`;
  const [request, setRequest] = useState<{ query: string } | null>(null);
  const [result, setResult] = useState<{ query: string; doc: Doc | null } | null>(null);
  const active = auto || request?.query === query;
  const ask = () => { setResult(null); setRequest({ query }); };

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    fetch(`/api/telescopes?${query}`, { signal: controller.signal })
      .then(r => r.ok ? r.json() : Promise.reject(new Error(String(r.status))))
      .then((doc: Doc) => { if (!controller.signal.aborted) setResult({ query, doc }); })
      .catch(() => { if (!controller.signal.aborted) setResult({ query, doc: null }); });
    return () => controller.abort();
  }, [active, query, request]);

  if (!active) return <button type="button" className="os-ask" onClick={ask}>Check other telescopes</button>;
  if (result?.query !== query) return <p className="os-wait" role="status">Checking MAST, HEASARC and CADC archives…</p>;

  const doc = result.doc;
  if (!doc) return (
    <div className="os">
      <p className="os-wait" role="status">Archive lookup is unavailable. <button type="button" className="os-link" onClick={ask}>Try again</button></p>
      <ArchiveLinks coords={coords} />
    </div>
  );

  const incomplete = doc.unanswered.length > 0;
  const noneAvailable = doc.coverage && SOURCES.every(({ key }) => doc.coverage?.[key] === 'unavailable');
  let summary = 'No matches in the selected catalogs.';
  if (doc.n_observations) summary = `${count(doc.n_observations)} archive entries from ${doc.n_telescopes} ${doc.n_telescopes === 1 ? 'facility' : 'facilities'}.`;
  else if (noneAvailable) summary = 'The archives did not return results.';
  else if (incomplete) summary = 'No matches in the catalogs that answered.';
  return (
    <div className="os">
      <p className="os-hd" role="status"><b>{summary}</b> <span>Search radius: {doc.radius_arcmin}′.{doc.from_cache && ' Saved results.'}</span></p>
      {doc.telescopes.length > 0 && (
        <ul className="os-list">
          {doc.telescopes.map(r => (
            <li key={r.key}>
              <span><b>{r.name}</b><small>{r.light} · {r.archive}</small></span>
              <span className="os-n">{count(r.n)}<small>{yr(r.first_year, r.last_year)}</small></span>
            </li>
          ))}
        </ul>
      )}
      {doc.previews.length > 0 && (
        <div className="os-pics" aria-label="Archive previews">
          {doc.previews.slice(0, 6).map(p => <ScopePreview key={p.url} preview={p} />)}
        </div>
      )}
      {incomplete && <p className="os-small">Some catalogs could not be searched. <button type="button" className="os-link" onClick={ask}>Try again</button></p>}
      <ArchiveLinks coords={coords} doc={doc} />
      <p className="os-small">{doc.note}</p>
      {doc.not_counted.length > 0 && <details className="os-small"><summary>Entries excluded from the count</summary>
        <p>{doc.not_counted.map(c => `${count(c.n)} ${c.collection} (${c.why})`).join('; ')}</p>
      </details>}
    </div>
  );
}
