import { useEffect, useState } from 'react';
import { Link } from '../router.tsx';

interface Track {
  id: string; field: string; n_nights: number; rate_arcsec_h: number; rms_arcsec: number; detectors: number[]; snr_max: number; first_mjd: number;
  known: { name: string; class: string; V: number; delta_au: number } | null;
}
interface Doc {
  n_fields: number; n_tracks: number; n_tracks_known: number; n_tracks_unmatched: number; n_known_in_view: number; n_known_found: number;
  recovery_by_V: { V: string; n: number; found: number }[]; tracks: Track[]; note: string;
  fields?: { id: string; ra: number; dec: number; ecl_lon: number; n_nights: number; n_images: number }[];
  history?: string; chance_tracks_expected?: number;
}

/** The asteroid hunt: tracks from SPHEREx alone, locked, then matched to the known-asteroid catalogue. */
export function AsteroidHunt() {
  const [d, setD] = useState<Doc | null>(null);
  useEffect(() => { fetch('/api/asteroids').then(r => (r.ok ? r.json() : null)).then(setD).catch(() => undefined); }, []);
  if (!d) return null;
  const unmatched = d.tracks.filter(t => !t.known);
  const known = d.tracks.filter(t => t.known).sort((a, b) => (a.known!.V ?? 99) - (b.known!.V ?? 99));
  const fieldOf = (id: string) => d.fields?.find(f => f.id === id);
  return (
    <section className="band2 cs" aria-labelledby="ah-h">
      <h2 className="test-h" id="ah-h"><span>New search</span>{d.n_tracks_known > 0 ? 'Asteroids, found blind.' : 'Asteroids: a measured limit.'}</h2>
      <p className="test-p">
        We took {d.n_fields} patches of sky along the path of the planets, each imaged by SPHEREx on several nights in one week. Software joined dots that move along a smooth path from night to night, after removing everything that stays put.
        The tracks were hash-locked before we asked the international asteroid catalogue (IMCCE SkyBoT) what was there.
      </p>
      <div className="tiles tiles--3">
        <div className="tile"><span className="tile__n">{d.n_tracks}</span><span className="tile__t">moving objects tracked over four or more nights, from SPHEREx images alone</span></div>
        {(() => {
          const bright = d.recovery_by_V.filter(r => /^(0-17|17-18|18-19)$/.test(r.V));
          const n = bright.reduce((a, r) => a + r.n, 0), f = bright.reduce((a, r) => a + r.found, 0);
          return <div className="tile"><span className="tile__n">{f} of {n}</span><span className="tile__t">known asteroids brighter than magnitude 19 that were in view were found blind. Fainter ones are beyond single SPHEREx images.</span></div>;
        })()}
        <div className="tile"><span className="tile__n">{d.n_tracks_unmatched}</span><span className="tile__t">{d.n_tracks_unmatched === 1 ? 'track matches' : 'tracks match'} no known asteroid{d.chance_tracks_expected != null ? ` (chance alone: ${d.chance_tracks_expected})` : ''}. {d.n_tracks_unmatched > 0 ? 'Candidates, not discoveries: they need follow-up images.' : 'No new asteroid. Single SPHEREx images reach about magnitude 17 here, and every asteroid that bright was found long ago.'}</span></div>
      </div>
      <div className="cs-table" role="table" aria-label="Known asteroids recovered, by brightness" style={{ marginTop: 16 }}>
        <div role="row" className="cs-tr cs-tr--h"><span role="columnheader">Brightness (V)</span><span role="columnheader">Known asteroids in view on 3+ nights</span><span role="columnheader">Found blind</span></div>
        {d.recovery_by_V.filter(r => r.n > 0).map(r => <div role="row" className="cs-tr" key={r.V}><span role="cell">{r.V}</span><span role="cell">{r.n}</span><span role="cell">{r.found} ({Math.round((r.found / r.n) * 100)}%)</span></div>)}
      </div>
      {known.length > 0 && (
        <p className="small dim" style={{ marginTop: 12 }}>Recovered, brightest first: {known.slice(0, 12).map(t => `${t.known!.name} (V ${t.known!.V})`).join(', ')}{known.length > 12 ? `, and ${known.length - 12} more` : ''}.</p>
      )}
      {unmatched.length > 0 && (
        <>
          <h3 className="cs-h3">Tracks that match nothing known</h3>
          <p className="test-p">Each moved along a smooth path across several nights and is not in the asteroid catalogue at that place and time. Some may be artefacts that happen to line up; each needs new images before anyone can call it an asteroid. We have not reported them to the Minor Planet Center.</p>
          <div className="cs-table" role="table" aria-label="Unmatched tracks">
            <div role="row" className="cs-tr cs-tr--h"><span role="columnheader">Track</span><span role="columnheader">Nights · speed</span><span role="columnheader">Signal · fit</span></div>
            {unmatched.map(t => {
              const f = fieldOf(t.field);
              return (
                <div role="row" className="cs-tr" key={t.id}>
                  <span role="cell">{f ? <Link href={`/map?ra=${f.ra.toFixed(4)}&dec=${f.dec.toFixed(4)}&fov=0.6`}>{t.id}</Link> : t.id}</span>
                  <span role="cell">{t.n_nights} nights · {t.rate_arcsec_h}″/h</span>
                  <span role="cell">S/N {t.snr_max} · {t.rms_arcsec}″</span>
                </div>
              );
            })}
          </div>
        </>
      )}
      {d.history && <p className="small dim" style={{ marginTop: 12 }}><strong>How we got here.</strong> {d.history}</p>}
      <p className="small dim">{d.note} Images: SPHEREx DR1 and QR3 (IRSA). Known asteroids: IMCCE SkyBoT (Berthier et al. 2006).</p>
    </section>
  );
}
