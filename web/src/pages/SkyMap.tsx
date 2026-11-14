import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Header } from '../components/Shell.tsx';
import { Link, navigate } from '../router.tsx';
import { api, huntApi } from '../api.ts';
import { resolveQuery } from '../components/SearchBox.tsx';
import { distantApi } from './Distant.tsx';

/* eslint-disable @typescript-eslint/no-explicit-any */
type AladinNS = any;

// All-sky image layers (HiPS), served by NASA/IPAC's IRSA.  The SPHEREx layer is IRSA's DR1 all-sky cube: one
// all-sky image for each of SPHEREx's 102 colours, in ascending wavelength (frames 50 and 51 are blank dichroic channels).
const IRSA = 'https://irsa.ipac.caltech.edu/data/hips';
const SPHEREX = { id: `${IRSA}/SPHEREx/spherex_allsky_cube`, fmt: 'png', label: 'SPHEREx, 102 colours', note: 'NASA SPHEREx DR1, 2025–2026. Slide through all 102 colours below' };
const LAYERS = [
  SPHEREX,
  { id: `${IRSA}/CDS/AllWISE/RGB-W4-W2-W1`, fmt: 'jpeg', label: 'WISE, 2010', note: 'NASA WISE, 3.4 to 22 µm, fifteen years earlier' },
  { id: `${IRSA}/CDS/2MASS/Color`, fmt: 'jpeg', label: '2MASS, 1998', note: 'Near-infrared, almost thirty years earlier' },
  { id: `${IRSA}/CDS/DSS2/color`, fmt: 'jpeg', label: 'Photographic plates', note: 'Digitized Sky Survey, 1950s to 1990s' },
  { id: `${IRSA}/CDS/IRIS/color`, fmt: 'jpeg', label: 'IRAS, 1983', note: 'Far-infrared, where a published Planet Nine candidate was seen' },
];
const WAVES = [0.753, 0.771, 0.790, 0.809, 0.828, 0.848, 0.868, 0.889, 0.910, 0.932, 0.955, 0.978, 1.001, 1.025, 1.050, 1.075, 1.102, 1.113, 1.139, 1.167, 1.195, 1.224, 1.254, 1.284, 1.315, 1.346, 1.378, 1.412, 1.446, 1.481, 1.517, 1.554, 1.592, 1.631, 1.656, 1.695, 1.735, 1.775, 1.818, 1.861, 1.905, 1.949, 1.995, 2.041, 2.089, 2.139, 2.189, 2.240, 2.292, 2.345, 2.399, 2.445, 2.506, 2.575, 2.646, 2.719, 2.794, 2.871, 2.951, 3.033, 3.118, 3.204, 3.293, 3.383, 3.476, 3.570, 3.667, 3.768, 3.833, 3.867, 3.901, 3.935, 3.970, 4.005, 4.040, 4.076, 4.112, 4.148, 4.184, 4.220, 4.257, 4.294, 4.331, 4.368, 4.405, 4.435, 4.467, 4.500, 4.533, 4.566, 4.600, 4.635, 4.669, 4.704, 4.739, 4.773, 4.808, 4.843, 4.879, 4.915, 4.951, 4.988];
const BLANK = new Set([50, 51]);

function hips(Ali: AladinNS, a: any, l: typeof LAYERS[number]) {
  const opts = { name: l.label, imgFormat: l.fmt };
  if (typeof Ali.imageHiPS === 'function') return Ali.imageHiPS(l.id, opts);
  return a.newImageSurvey(l.id, opts);
}

// Brown & Batygin (2021): about 95 % of Planet Nine's predicted positions lie within 12 degrees of declination of this track.
// The track itself is derived from their orbit (inclination 16, node 97) in docs/PLANET_NINE_RESEARCH.md. Approximate.
const P9_TRACK: [number, number][] = [[33, -2], [46, 4], [60, 11], [74, 16], [90, 21], [107, 25]];
// Phan et al. 2025 (PASA 42, e064): a published Planet Nine candidate from IRAS (1983) and AKARI (2006). Unconfirmed.
const PHAN = [{ ra: 35.74075, dec: -48.5125, label: 'IRAS, 1983' }, { ra: 35.18379, dec: -49.2135, label: 'AKARI, 2006' }];

interface Toggles { targets: boolean; fields: boolean; makemake: boolean; nine: boolean; phan: boolean; forecasts: boolean }

const openHere = (ra: number, dec: number, fov = 10) => `/explore?ra=${ra.toFixed(5)}&dec=${dec.toFixed(5)}&fov=${fov}`;
const popup = (title: string, body: string, ra: number, dec: number) =>
  `<div class="mapop"><p>${body}</p><a class="mapop__go" href="${openHere(ra, dec)}">Open the SPHEREx images here</a></div>`;

/** "Google Maps for the infrared sky": the whole sky in SPHEREx and five other telescopes, with our results drawn on it. */
export function SkyMap() {
  const box = useRef<HTMLDivElement>(null);
  const al = useRef<any>(null);
  const cube = useRef<any>(null);
  const [slice, setSlice] = useState(42);
  const [sweep, setSweep] = useState(false);
  const A = useRef<AladinNS>(null);
  const groups = useRef<Record<keyof Toggles, any[]>>({ targets: [], fields: [], makemake: [], nine: [], phan: [], forecasts: [] });
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [layer, setLayer] = useState(LAYERS[0].id);
  const [show, setShow] = useState<Toggles>({ targets: true, fields: true, makemake: true, nine: true, phan: true, forecasts: false });
  const [centre, setCentre] = useState<{ ra: number; dec: number; fov: number } | null>(null);
  const [q, setQ] = useState('');
  const [err, setErr] = useState<string | null>(null);

  // ---- start the map ----
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const mod = await import('aladin-lite');
        const Ali: AladinNS = (mod as any).default ?? mod;
        await Ali.init;
        if (!alive || !box.current) return;
        A.current = Ali;
        const params = new URLSearchParams(window.location.search);
        const ra = Number(params.get('ra')), dec = Number(params.get('dec')), fov = Number(params.get('fov'));
        const target = Number.isFinite(ra) && params.get('ra') ? `${ra} ${dec}` : '201.3 +20.6';
        const a = Ali.aladin(box.current, {
          survey: SPHEREX.id, fov: Number.isFinite(fov) && fov > 0 ? fov : 60, target, projection: 'SIN', cooFrame: 'ICRS', log: false,
          showReticle: true, showZoomControl: true, showFullscreenControl: false, showLayersControl: false, showGotoControl: false,
          showFrame: false, showCooGridControl: false, showSimbadPointerControl: false, showContextMenu: false, showProjectionControl: false,
          reticleColor: '#ffa63d',
        });
        al.current = a;
        const report = () => { try { const [r, d] = a.getRaDec(); setCentre({ ra: r, dec: d, fov: a.getFov()[0] }); } catch { /* not ready */ } };
        a.on('positionChanged', report);
        a.on('zoomChanged', report);
        report();
        await drawOverlays(Ali, a);
        if (alive) setState('ready');
      } catch (e) {
        if (alive) { setState('error'); setErr(String((e as Error)?.message ?? e)); }
      }
    })();
    return () => { alive = false; };
  }, []);

  async function drawOverlays(Ali: AladinNS, a: any) {
    const g = groups.current;
    // NASA's five test targets
    try {
      const ts = await api.targets();
      const cat = Ali.catalog({ name: "NASA's five targets", color: '#ffa63d', sourceSize: 16, shape: 'circle' });
      a.addCatalog(cat);
      cat.addSources(ts.filter(t => t.field).map(t => Ali.marker(t.field!.ra, t.field!.dec, {
        popupTitle: t.title, popupDesc: popup(t.title, t.headline?.label ?? t.kind, t.field!.ra, t.field!.dec),
      })));
      g.targets.push(cat);
    } catch { /* targets unavailable */ }
    // The 25 hunt fields
    try {
      const idx = await huntApi.index();
      const ov = Ali.graphicOverlay({ name: 'Hunt fields', color: '#eadcc2', lineWidth: 1.5 });
      a.addOverlay(ov);
      for (const f of idx.fields) {
        const h = f.fov_arcmin / 120, cosd = Math.cos(f.dec * Math.PI / 180) || 1e-3;
        const c = [[f.ra - h / cosd, f.dec - h], [f.ra + h / cosd, f.dec - h], [f.ra + h / cosd, f.dec + h], [f.ra - h / cosd, f.dec + h], [f.ra - h / cosd, f.dec - h]];
        ov.add(Ali.polyline(c));
      }
      const cat = Ali.catalog({ name: 'Hunt fields', color: '#eadcc2', sourceSize: 10, shape: 'square' });
      a.addCatalog(cat);
      cat.addSources(idx.fields.map(f => Ali.marker(f.ra, f.dec, {
        popupTitle: f.title, popupDesc: popup(f.title, `Searched blind for movers: ${f.n_motion_tested.toLocaleString('en-US')} sources tested in ${f.n_visits} visits.`, f.ra, f.dec),
      })));
      g.fields.push(ov, cat);
    } catch { /* hunt unavailable */ }
    // Makemake, found blind: its real detections and the fitted path through three visits
    try {
      const d = await distantApi.results();
      for (const b of d.bodies) {
        const o = b.object as any;
        if (!o) continue;
        const cosd = Math.cos(o.dec0_deg * Math.PI / 180);
        const toSky = (p: { dx_deg: number; dy_deg: number }) => [o.ra0_deg + p.dx_deg / cosd, o.dec0_deg + p.dy_deg];
        const ov = Ali.graphicOverlay({ name: `${b.title} path`, color: '#ffa63d', lineWidth: 2 });
        a.addOverlay(ov);
        ov.add(Ali.polyline(o.curve.map(toSky)));
        const cat = Ali.catalog({ name: `${b.title} detections`, color: '#ffffff', sourceSize: 8, shape: 'circle' });
        a.addCatalog(cat);
        const [r0, d0] = toSky(o.detections[0]);
        cat.addSources(o.detections.map((p: any) => { const [r, dd] = toSky(p); return Ali.source(r, dd, { name: b.title }); }));
        const pin = Ali.catalog({ name: b.title, color: '#ffa63d', sourceSize: 18, shape: 'plus' });
        a.addCatalog(pin);
        pin.addSources([Ali.marker(r0, d0, {
          popupTitle: `${b.title}, found blind`,
          popupDesc: popup(b.title, `Found without being told where to look: ${b.match?.r_fit_au.toFixed(2)} AU from the Sun. JPL says ${b.match?.r_true_au.toFixed(2)}. The line is the path PARALLAX fitted; it loops because the Earth moves.`, r0, d0),
        })]);
        g.makemake.push(ov, cat, pin);
      }
    } catch { /* distant results unavailable */ }
    // Planet Nine: the predicted band (approximate) and a published candidate
    const band = Ali.graphicOverlay({ name: 'Planet Nine band', color: '#7d9bff', lineWidth: 2, lineDash: [8, 8] });
    a.addOverlay(band);
    band.add(Ali.polyline(P9_TRACK.map(([r, d]) => [r, d])));
    band.add(Ali.polyline(P9_TRACK.map(([r, d]) => [r, d + 12])));
    band.add(Ali.polyline(P9_TRACK.map(([r, d]) => [r, d - 12])));
    const nine = Ali.catalog({ name: 'Planet Nine', color: '#7d9bff', sourceSize: 14, shape: 'diamond' });
    a.addCatalog(nine);
    nine.addSources([Ali.marker(60, 11, {
      popupTitle: 'Where Planet Nine is predicted',
      popupDesc: popup('Planet Nine', 'About 95 % of predicted positions lie within the dashed lines (Brown & Batygin 2021; track derived by us, approximate). The planet would be about 7 µJy: far too faint for single SPHEREx images.', 60, 11),
    })]);
    g.nine.push(band, nine);
    const phan = Ali.catalog({ name: 'Published Planet Nine candidate', color: '#f6f2ea', sourceSize: 14, shape: 'triangle' });
    a.addCatalog(phan);
    phan.addSources(PHAN.map(p => Ali.marker(p.ra, p.dec, {
      popupTitle: `Candidate seen by ${p.label}`,
      popupDesc: popup('Phan et al. 2025', `A published Planet Nine candidate (Phan et al. 2025): one far-infrared source in ${p.label}. Not confirmed.`, p.ra, p.dec),
    })));
    g.phan.push(phan);
    // Forecasts locked for 2027
    try {
      const fc = await huntApi.forecasts();
      const cat = Ali.catalog({ name: 'Forecasts', color: '#9af0cc', sourceSize: 6, shape: 'circle' });
      a.addCatalog(cat);
      for (const f of fc.forecasts) cat.addSources(f.predictions.map(p => Ali.source(p.ra_deg, p.dec_deg, { name: `${f.title} ${p.date_utc.slice(0, 7)}` })));
      g.forecasts.push(cat);
      cat.hide();
    } catch { /* forecasts unavailable */ }
  }

  // ---- layer and overlay switches ----
  useEffect(() => {
    const a = al.current;
    if (!a || state !== 'ready') return;
    const l = LAYERS.find(x => x.id === layer);
    if (!l) return;
    try {
      const sv = hips(A.current, a, l);
      a.setBaseImageLayer(sv);
      cube.current = l.id === SPHEREX.id ? sv : null;
      if (cube.current) window.setTimeout(() => { try { cube.current?.setSliceNumber(slice); } catch { /* not ready */ } }, 400);
    } catch { /* ignore */ }
  }, [layer, state]);
  // wavelength: one of the 102 SPHEREx colours
  useEffect(() => { try { cube.current?.setSliceNumber(slice); } catch { /* not ready */ } }, [slice]);
  // sweep through every colour, about 8 per second
  useEffect(() => {
    if (!sweep || layer !== SPHEREX.id) return;
    const id = window.setInterval(() => setSlice(k => { let n = (k + 1) % WAVES.length; while (BLANK.has(n)) n = (n + 1) % WAVES.length; return n; }), 125);
    return () => window.clearInterval(id);
  }, [sweep, layer]);
  useEffect(() => {
    if (state !== 'ready') return;
    (Object.keys(show) as (keyof Toggles)[]).forEach(k => groups.current[k].forEach(o => { try { show[k] ? o.show() : o.hide(); } catch { /* ignore */ } }));
  }, [show, state]);

  function go(ra: number, dec: number, fov?: number) {
    const a = al.current;
    if (!a) return;
    a.gotoRaDec(ra, dec);
    if (fov) a.setFoV(fov);
  }
  async function search(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    try { const r = await resolveQuery(q.trim()); go(r.ra, r.dec, 1.5); } catch (x) { setErr((x as Error).message || 'Not found. Try coordinates.'); }
  }

  const PLACES: { label: string; ra: number; dec: number; fov: number }[] = [
    { label: 'Makemake, found blind', ra: 201.3, dec: 20.6, fov: 6 },
    { label: 'Epsilon Indi B', ra: 331.0976, dec: -56.8012, fov: 0.6 },
    { label: 'WISE 0855, the coldest brown dwarf', ra: 133.787, dec: -7.2445, fov: 0.6 },
    { label: 'Where Planet Nine may be', ra: 60, dec: 11, fov: 60 },
    { label: 'The centre of the Milky Way', ra: 266.4168, dec: -29.0078, fov: 8 },
    { label: 'The whole sky', ra: 90, dec: 0, fov: 180 },
  ];
  const layerInfo = LAYERS.find(l => l.id === layer)!;

  return (
    <>
      <Header />
      <main id="main" className="smap">
        <div ref={box} className="smap__map" aria-label="Interactive map of the whole sky. Drag to pan, scroll to zoom." role="application" />
        {state === 'loading' && <p className="smap__status">Opening the sky…</p>}
        {state === 'error' && <p className="smap__status">The sky map needs WebGL 2 and a network connection. {err}</p>}
        <section className="smap__panel" aria-label="Map controls">
          <h1 className="smap__title">The sky map</h1>
          <p className="smap__lede">The whole sky as SPHEREx sees it. Zoom anywhere, switch telescopes, then open the real images of that spot and watch it change.</p>
          <form className="smap__search" onSubmit={search} role="search">
            <label className="visually-hidden" htmlFor="map-q">Go to a name or coordinates</label>
            <input id="map-q" value={q} onChange={e => setQ(e.target.value)} placeholder="A star name, or RA and Dec" autoComplete="off" spellCheck={false} />
            <button className="button button--primary button--small" type="submit">Go</button>
          </form>
          {err && state === 'ready' && <p className="small smap__err" role="alert">{err}</p>}
          <div className="smap__places">{PLACES.map(p => <button key={p.label} type="button" onClick={() => go(p.ra, p.dec, p.fov)}>{p.label}</button>)}</div>
          <h2 className="smap__h">Telescope</h2>
          <div className="smap__layers" role="radiogroup" aria-label="Which telescope's sky to show">
            {LAYERS.map(l => <button key={l.id} type="button" role="radio" aria-checked={layer === l.id} className={layer === l.id ? 'is-on' : ''} onClick={() => setLayer(l.id)}>{l.label}</button>)}
          </div>
          <p className="small dim">{layerInfo.note}.</p>
          {layer === SPHEREX.id && (
            <div className="smap__wave">
              <label htmlFor="map-wave">Colour: <strong>{WAVES[slice].toFixed(2)} µm</strong>{WAVES[slice] < 1.1 ? ' (reflected sunlight)' : WAVES[slice] > 3.8 ? ' (where cold worlds glow)' : ''}</label>
              <input id="map-wave" type="range" min={0} max={WAVES.length - 1} value={slice} onChange={e => { setSweep(false); setSlice(Number(e.target.value)); }} />
              <button type="button" className="button button--small" onClick={() => setSweep(v => !v)}>{sweep ? 'Stop' : 'Play all 102 colours'}</button>
            </div>
          )}
          <h2 className="smap__h">On the map</h2>
          <div className="smap__toggles">
            {([['targets', "NASA's five targets"], ['makemake', 'Makemake, found blind'], ['fields', 'Fields we searched'], ['nine', 'Where Planet Nine may be'], ['phan', 'A published Planet Nine candidate'], ['forecasts', 'Our 2027 forecasts']] as [keyof Toggles, string][]).map(([k, label]) => (
              <label key={k}><input type="checkbox" checked={show[k]} onChange={e => setShow(s => ({ ...s, [k]: e.target.checked }))} /> {label}</label>
            ))}
          </div>
        </section>
        <section className="smap__here" aria-live="polite">
          <span className="small">{centre ? `Centre: RA ${centre.ra.toFixed(4)}°, Dec ${centre.dec >= 0 ? '+' : ''}${centre.dec.toFixed(4)}°, ${centre.fov >= 1 ? `${centre.fov.toFixed(1)}°` : `${(centre.fov * 60).toFixed(1)}′`} across` : 'Centre: —'}</span>
          <button className="button button--primary" type="button" disabled={!centre} onClick={() => centre && navigate(openHere(centre.ra, centre.dec, Math.min(20, Math.max(4, Math.round((centre.fov * 60) / 3)))))}>Open the SPHEREx images here</button>
        </section>
        <p className="smap__credit">Sky maps served by NASA/IPAC IRSA: SPHEREx DR1 all-sky cube (SPHEREx Science Data Center); AllWISE, 2MASS, DSS2 and IRAS (IRIS) layers made by CDS. Map: Aladin Lite (CDS, Strasbourg). <Link href="/about">Sources</Link></p>
      </main>
    </>
  );
}
