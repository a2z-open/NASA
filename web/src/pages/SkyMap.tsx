import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Mark } from '../components/Shell.tsx';
import { Link, navigate } from '../router.tsx';
import { huntApi } from '../api.ts';
import { resolveQuery } from '../components/SearchBox.tsx';
import { CHUNK_STATUS_LABEL, ChunkReview, useChunkAssignments } from '../components/ChunkReview.tsx';
import { CHUNKS, chunkAt, chunkFromId, chunkGridLines } from '../lib/skyChunks.ts';
import { distantApi } from './Distant.tsx';
import '../map.css';

/* eslint-disable @typescript-eslint/no-explicit-any */
type AladinNS = any;

// All-sky image layers (HiPS), served by NASA/IPAC's IRSA.  The SPHEREx layer is IRSA's DR1 all-sky cube: one
// all-sky image for each of SPHEREx's 102 colours, in ascending wavelength (frames 50 and 51 are blank dichroic channels).
const IRSA = 'https://irsa.ipac.caltech.edu/data/hips';
const SPHEREX = { id: `${IRSA}/SPHEREx/spherex_allsky_cube`, fmt: 'png', label: 'SPHEREx', year: '2025', thumb: '/img/spherex-vela.webp' };
const LAYERS = [
  SPHEREX,
  { id: `${IRSA}/CDS/AllWISE/RGB-W4-W2-W1`, fmt: 'jpeg', label: 'WISE', year: '2010', thumb: `${IRSA}/CDS/AllWISE/RGB-W4-W2-W1/preview.jpg` },
  { id: `${IRSA}/CDS/2MASS/Color`, fmt: 'jpeg', label: '2MASS', year: '1998', thumb: `${IRSA}/CDS/2MASS/Color/preview.jpg` },
  { id: `${IRSA}/CDS/DSS2/color`, fmt: 'jpeg', label: 'Visible', year: '1950s–90s', thumb: `${IRSA}/CDS/DSS2/color/preview.jpg` },
  { id: `${IRSA}/CDS/IRIS/color`, fmt: 'jpeg', label: 'IRAS', year: '1983', thumb: `${IRSA}/CDS/IRIS/color/preview.jpg` },
];
const WAVES = [0.753, 0.771, 0.790, 0.809, 0.828, 0.848, 0.868, 0.889, 0.910, 0.932, 0.955, 0.978, 1.001, 1.025, 1.050, 1.075, 1.102, 1.113, 1.139, 1.167, 1.195, 1.224, 1.254, 1.284, 1.315, 1.346, 1.378, 1.412, 1.446, 1.481, 1.517, 1.554, 1.592, 1.631, 1.656, 1.695, 1.735, 1.775, 1.818, 1.861, 1.905, 1.949, 1.995, 2.041, 2.089, 2.139, 2.189, 2.240, 2.292, 2.345, 2.399, 2.445, 2.506, 2.575, 2.646, 2.719, 2.794, 2.871, 2.951, 3.033, 3.118, 3.204, 3.293, 3.383, 3.476, 3.570, 3.667, 3.768, 3.833, 3.867, 3.901, 3.935, 3.970, 4.005, 4.040, 4.076, 4.112, 4.148, 4.184, 4.220, 4.257, 4.294, 4.331, 4.368, 4.405, 4.435, 4.467, 4.500, 4.533, 4.566, 4.600, 4.635, 4.669, 4.704, 4.739, 4.773, 4.808, 4.843, 4.879, 4.915, 4.951, 4.988];
const BLANK = new Set([50, 51]);

// Brown & Batygin (2021): about 95 % of Planet Nine's predicted positions lie within 12 degrees of declination of this track.
// The track itself is derived from their orbit (inclination 16, node 97) in docs/PLANET_NINE_RESEARCH.md. Approximate.
const P9_TRACK: [number, number][] = [[33, -2], [46, 4], [60, 11], [74, 16], [90, 21], [107, 25]];

type Cat = 'planets' | 'dwarfs' | 'finds' | 'cold' | 'deep' | 'stars';
interface Place {
  name: string; kind: string; cat: Cat; blurb: string;
  q?: string;                       // looked up live (it moves): NASA JPL Horizons
  ra?: number; dec?: number;        // fixed position
  fov?: number; img?: string; ours?: boolean;
}
const PLACES: Place[] = [
  { name: 'Mercury', kind: 'Planet', cat: 'planets', q: 'Mercury', blurb: 'The closest planet to the Sun. SPHEREx never looks this close to the Sun.' },
  { name: 'Venus', kind: 'Planet', cat: 'planets', q: 'Venus', blurb: 'The brightest planet in our sky.' },
  { name: 'Mars', kind: 'Planet', cat: 'planets', q: 'Mars', blurb: 'The red planet.' },
  { name: 'Jupiter', kind: 'Planet', cat: 'planets', q: 'Jupiter', blurb: 'The largest planet. Far too bright for SPHEREx to image cleanly.' },
  { name: 'Saturn', kind: 'Planet', cat: 'planets', q: 'Saturn', blurb: 'The ringed planet.' },
  { name: 'Uranus', kind: 'Planet', cat: 'planets', q: 'Uranus', blurb: 'An ice giant, 19 times farther from the Sun than Earth.' },
  { name: 'Neptune', kind: 'Planet', cat: 'planets', q: 'Neptune', blurb: 'Found in 1846, right where the maths said it would be.', img: '/img/neptune.webp' },
  { name: 'Pluto', kind: 'Dwarf planet', cat: 'dwarfs', q: 'Pluto', blurb: 'Found in 1930 by comparing two photos of the same sky.', img: '/img/pluto.webp' },
  { name: 'Makemake', kind: 'Dwarf planet', cat: 'dwarfs', q: 'Makemake', blurb: 'PARALLAX found it with no hints and measured its distance: 52.7 AU.', ours: true },
  { name: 'Eris', kind: 'Dwarf planet', cat: 'dwarfs', q: 'Eris', blurb: 'Too faint for one photo. PARALLAX found it by stacking photos along its path: 95.5 AU.', ours: true },
  { name: 'Haumea', kind: 'Dwarf planet', cat: 'dwarfs', q: 'Haumea', blurb: 'An egg-shaped dwarf planet with a ring.' },
  { name: 'Ceres', kind: 'Dwarf planet', cat: 'dwarfs', q: 'Ceres', blurb: 'The largest body in the asteroid belt.' },
  { name: 'Sedna', kind: 'Distant world', cat: 'dwarfs', q: 'Sedna', blurb: 'One of the most distant known worlds. Its odd orbit is a clue in the Planet Nine debate.' },
  { name: 'Makemake, where we found it', kind: 'Our find', cat: 'finds', ra: 201.3, dec: 20.6, fov: 6, blurb: 'The path PARALLAX fitted through three SPHEREx visits. It loops because Earth moves.', ours: true },
  { name: 'Epsilon Indi B', kind: 'Brown dwarf pair', cat: 'finds', ra: 331.0976, dec: -56.8012, fov: 0.6, blurb: 'We locked a prediction of where it would be, then opened the images. It landed 0.07″ away.', ours: true },
  { name: 'Planet Nine zone', kind: 'Prediction', cat: 'finds', ra: 60, dec: 11, fov: 60, blurb: 'About 95 % of predicted positions lie between the dashed lines. Even with SPHEREx photos added up along its path, it would be about 8 times too faint.' },
  { name: 'WISE 0855', kind: 'Brown dwarf', cat: 'cold', ra: 133.787, dec: -7.2445, fov: 0.6, blurb: 'The coldest known brown dwarf, near the freezing point of water. PARALLAX found it by its motion alone.', ours: true, img: '/img/cold-dwarf.webp' },
  { name: "Barnard's Star", kind: 'Red dwarf', cat: 'cold', ra: 269.4486, dec: 4.7379, fov: 0.6, blurb: 'The fastest-moving star in our sky. Too bright for the camera, so we measured its halo.', ours: true },
  { name: 'Luhman 16', kind: 'Brown dwarf pair', cat: 'cold', ra: 162.3285, dec: -53.3194, fov: 0.6, blurb: 'The closest brown dwarfs to the Sun, 6.5 light-years away.' },
  { name: 'Orion Nebula', kind: 'Nebula', cat: 'deep', ra: 83.8221, dec: -5.3911, fov: 2, blurb: 'A cloud where stars are being born, 1,300 light-years away.' },
  { name: 'Andromeda Galaxy', kind: 'Galaxy', cat: 'deep', ra: 10.6847, dec: 41.2687, fov: 4, blurb: 'Our nearest large galaxy, 2.5 million light-years away.' },
  { name: 'Milky Way centre', kind: 'Galactic centre', cat: 'deep', ra: 266.4168, dec: -29.0078, fov: 8, blurb: 'The crowded heart of our galaxy. Infrared light sees through the dust.' },
  { name: 'Large Magellanic Cloud', kind: 'Galaxy', cat: 'deep', ra: 80.8938, dec: -69.7561, fov: 10, blurb: 'A small galaxy that orbits ours.' },
  { name: 'Pleiades', kind: 'Star cluster', cat: 'deep', ra: 56.75, dec: 24.1167, fov: 3, blurb: 'The Seven Sisters.' },
  { name: 'Vega', kind: 'Star', cat: 'stars', ra: 279.2347, dec: 38.7837, fov: 2, blurb: 'One of the brightest stars, 25 light-years away.' },
  { name: 'Sirius', kind: 'Star', cat: 'stars', ra: 101.2872, dec: -16.7161, fov: 2, blurb: 'The brightest star in the night sky.' },
  { name: 'Betelgeuse', kind: 'Star', cat: 'stars', ra: 88.7929, dec: 7.4071, fov: 2, blurb: "A red supergiant in Orion's shoulder." },
  { name: 'Polaris', kind: 'Star', cat: 'stars', ra: 37.9546, dec: 89.2641, fov: 4, blurb: 'The North Star.' },
];
const CATS: { id: Cat; label: string }[] = [
  { id: 'finds', label: 'Our finds' }, { id: 'planets', label: 'Planets' }, { id: 'dwarfs', label: 'Dwarf planets' },
  { id: 'cold', label: 'Cold neighbours' }, { id: 'deep', label: 'Nebulae and galaxies' }, { id: 'stars', label: 'Stars' },
];
const POPULAR = ['Makemake, where we found it', 'Pluto', 'WISE 0855', 'Orion Nebula', 'Planet Nine zone', 'Andromeda Galaxy'];

interface Sel { name: string; kind: string; blurb?: string; ra: number; dec: number; fov?: number; img?: string; moves?: boolean; source?: string; ours?: boolean; cat?: Cat; pin?: boolean }
interface Toggles { finds: boolean; fields: boolean; nine: boolean; forecasts: boolean }

// ---- icons (one stroke weight, one family) ----
const I = (d: ReactNode) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>;
const IcSearch = () => I(<><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></>);
const IcX = () => I(<path d="M6 6l12 12M18 6 6 18" />);
const IcPin = () => I(<><path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" /></>);
const IcPlanet = () => I(<><circle cx="12" cy="12" r="5.5" /><path d="M3 15.5c2 2.2 16-4.2 18-7" /></>);
const IcStar = () => I(<path d="M12 3.5l2.5 5.6 6 .6-4.5 4.1 1.3 6-5.300-3.100-5.300 3.100 1.300-6L3.500 9.700l6-.6z" />);
const IcSpiral = () => I(<><circle cx="12" cy="12" r="1.6" /><path d="M12 6.500a5.500 5.500 0 0 1 5.500 5.500M12 17.500A5.500 5.500 0 0 1 6.500 12M3.500 12A8.500 8.500 0 0 1 12 3.500M20.500 12A8.500 8.500 0 0 1 12 20.500" /></>);
const IcFlag = () => I(<><path d="M6 21V4" /><path d="M6 4h11l-2.500 4L17 12H6" /></>);
const IcSnow = () => I(<path d="M12 3v18M4.200 7.500l15.600 9M19.800 7.500l-15.600 9" />);
const IcImages = () => I(<><rect x="3.500" y="5" width="17" height="14" rx="2.500" /><circle cx="9" cy="10" r="1.600" /><path d="m5 17 5-4.500 3.500 3 2.500-2 3.500 3.500" /></>);
const IcPlus = () => I(<path d="M12 5v14M5 12h14" />);
const IcMinus = () => I(<path d="M5 12h14" />);
const IcShare = () => I(<><circle cx="6.500" cy="12" r="2.200" /><circle cx="17.500" cy="6" r="2.200" /><circle cx="17.500" cy="18" r="2.200" /><path d="m8.500 11 7-4M8.500 13l7 4" /></>);
const IcGlobe = () => I(<><circle cx="12" cy="12" r="8.500" /><path d="M3.500 12h17M12 3.500c3 3 3 14 0 17M12 3.500c-3 3-3 14 0 17" /></>);
const IcLayers = () => I(<><path d="m12 4 8.500 4.500L12 13 3.500 8.500z" /><path d="m3.500 12.500 8.500 4.500 8.500-4.500" /></>);
const IcClock = () => I(<><circle cx="12" cy="12" r="8.500" /><path d="M12 7.500V12l3 2" /></>);
const IcInfo = () => I(<><circle cx="12" cy="12" r="8.500" /><path d="M12 11v5.500M12 7.800v.2" /></>);
const catIcon = (c?: Cat) => c === 'planets' || c === 'dwarfs' ? <IcPlanet /> : c === 'deep' ? <IcSpiral /> : c === 'stars' ? <IcStar /> : c === 'cold' ? <IcSnow /> : c === 'finds' ? <IcFlag /> : <IcPin />;

function hips(Ali: AladinNS, a: any, l: typeof LAYERS[number]) {
  const opts = { name: l.label, imgFormat: l.fmt };
  if (typeof Ali.imageHiPS === 'function') return Ali.imageHiPS(l.id, opts);
  return a.newImageSurvey(l.id, opts);
}

/** A white map pin, drawn once. The canvas is twice the pin's height so its tip sits on the position. */
function pinCanvas(size = 30, hollow = false) {
  const c = document.createElement('canvas');
  const w = size, h = Math.round(size * 1.32);
  c.width = w; c.height = h * 2;
  const g = c.getContext('2d')!;
  const r = w / 2 - 2;
  g.beginPath();
  g.arc(w / 2, r + 2, r, Math.PI * 0.86, Math.PI * 0.14, false);
  g.lineTo(w / 2, h);
  g.closePath();
  g.fillStyle = hollow ? '#1e1f20' : '#ffffff';
  g.strokeStyle = hollow ? '#ffffff' : '#131314';
  g.lineWidth = hollow ? 2 : 1.5;
  g.fill(); g.stroke();
  g.beginPath(); g.arc(w / 2, r + 2, r * 0.36, 0, Math.PI * 2);
  g.fillStyle = hollow ? '#ffffff' : '#131314'; g.fill();
  return c;
}

const fmtCoord = (ra: number, dec: number) => `${ra.toFixed(4)}°, ${dec >= 0 ? '+' : '−'}${Math.abs(dec).toFixed(4)}°`;
const fmtFov = (f: number) => f >= 1 ? `${f.toFixed(f >= 10 ? 0 : 1)}° wide` : `${(f * 60).toFixed(0)}′ wide`;
const openHere = (ra: number, dec: number, fov = 10) => `/explore?ra=${ra.toFixed(5)}&dec=${dec.toFixed(5)}&fov=${fov}`;
const CHUNK_GRID_FOV = 45;
const CHUNK_SEARCH_FOV = 28;

interface ChunkLabel { id: string; x: number; y: number }
const NO_LABELS: ChunkLabel[] = [];

function visibleChunkLabels(project: (ra: number, dec: number) => number[] | undefined, width: number, height: number) {
  const labels: ChunkLabel[] = [];
  const top = width <= 760 ? 124 : 80;
  for (const { id, ra, dec } of CHUNKS) {
    const [x, y] = project(ra, dec) ?? [];
    if (!(x >= 44 && x <= width - 44 && y >= top && y <= height - 62)) continue;
    if (!labels.some(label => Math.abs(label.x - x) < 92 && Math.abs(label.y - y) < 42)) labels.push({ id, x, y });
  }
  return labels;
}

/** The sky, used like a map app: search, tap a pin, switch layers, drop a pin anywhere. */
export function SkyMap() {
  const box = useRef<HTMLDivElement>(null);
  const al = useRef<any>(null);
  const A = useRef<AladinNS>(null);
  const cube = useRef<any>(null);
  const groups = useRef<Record<keyof Toggles, any[]>>({ finds: [], fields: [], nine: [], forecasts: [] });
  const selCat = useRef<any>(null);
  const pins = useRef<{ place: Sel; size: number; group: keyof Toggles }[]>([]);
  const showRef = useRef<Toggles | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [layer, setLayer] = useState(LAYERS[0].id);
  const [slice, setSlice] = useState(42);
  const [sweep, setSweep] = useState(false);
  const [show, setShow] = useState<Toggles>({ finds: true, fields: true, nine: true, forecasts: false });
  const [centre, setCentre] = useState<{ ra: number; dec: number; fov: number } | null>(null);
  const [chunkLabels, setChunkLabels] = useState(NO_LABELS);
  const [activeChunk, setActiveChunk] = useState<string | null>(null);
  const chunkOpener = useRef<HTMLButtonElement | null>(null);
  const chunkTeam = useChunkAssignments();
  const [q, setQ] = useState('');
  const [focus, setFocus] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<Sel | null>(null);
  const [list, setList] = useState<Cat | null>(null);
  const [layersOpen, setLayersOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

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
        const chunk = chunkFromId(params.get('chunk') ?? '');
        const target = chunk ? `${chunk.ra} ${chunk.dec}`
          : Number.isFinite(ra) && params.get('ra') ? `${ra} ${dec}` : '201.3 +20.6';
        const a = Ali.aladin(box.current, {
          survey: SPHEREX.id, fov: chunk ? CHUNK_SEARCH_FOV : Number.isFinite(fov) && fov > 0 ? fov : 60, target, projection: 'SIN', cooFrame: 'ICRS', log: false,
          showReticle: false, showZoomControl: false, showFullscreenControl: false, showLayersControl: false, showGotoControl: false,
          showFrame: false, showCooGridControl: false, showSimbadPointerControl: false, showContextMenu: false, showProjectionControl: false,
          showCooGrid: false, showStatusBar: false, showShareControl: false, showSettingsControl: false,
        });
        al.current = a;
        const grid = Ali.graphicOverlay({ name: 'Sky chunks', color: 'rgba(230,240,255,0.5)', lineWidth: 1 });
        a.addOverlay(grid);
        grid.addFootprints(chunkGridLines().map(line => Ali.polyline(line)));
        let gridVisible = true;
        const report = () => {
          if (!alive) return;
          try {
            const [r, d] = a.getRaDec();
            const widthDegrees = a.getFov()[0];
            setCentre({ ra: r, dec: d, fov: widthDegrees });
            const visible = widthDegrees <= CHUNK_GRID_FOV;
            if (visible !== gridVisible) {
              if (visible) grid.show();
              else grid.hide();
              gridVisible = visible;
            }
            if (visible) {
              const [width, height] = a.getSize();
              setChunkLabels(visibleChunkLabels((lon, lat) => a.world2pix(lon, lat), width, height));
            } else setChunkLabels(NO_LABELS);
          } catch { /* projection not ready */ }
        };
        a.on('positionChanged', report);
        a.on('zoomChanged', report);
        a.on('resizeChanged', () => window.requestAnimationFrame(report));
        report();
        // tap a pin (anywhere on its shape): open its card.  tap empty sky: drop a pin.
        a.on('click', (e: any) => {
          if (!e || e.isDragging || typeof e.ra !== 'number') return;
          let hit: Sel | null = null;
          try {
            const [cx, cy] = a.world2pix(e.ra, e.dec);
            for (const p of pins.current) {
              if (showRef.current && !showRef.current[p.group]) continue;
              const xy = a.world2pix(p.place.ra, p.place.dec);
              if (!xy) continue;
              const h = p.size * 1.32;
              if (Math.abs(cx - xy[0]) <= p.size / 2 + 3 && cy >= xy[1] - h - 3 && cy <= xy[1] + 5) { hit = p.place; if (p.size > 20) break; }
            }
          } catch { /* projection not ready */ }
          setList(null);
          setLayersOpen(false);
          setActiveChunk(null);
          if (hit) setSel(hit);
          else setSel(s => (s && !s.pin ? null : { name: 'Dropped pin', kind: 'A spot in the sky', ra: e.ra, dec: e.dec, pin: true }));
        });
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
    const pin = pinCanvas(30), small = pinCanvas(20, true);
    const mk = (cat: any, places: Sel[], group: keyof Toggles = 'finds', size = 30) => {
      cat.addSources(places.map(p => Ali.source(p.ra, p.dec, { place: p, name: p.name })));
      for (const place of places) pins.current.push({ place, size, group });
    };
    // the patches PARALLAX searched
    try {
      const idx = await huntApi.index();
      const ov = Ali.graphicOverlay({ name: 'Searched patches', color: 'rgba(255,255,255,0.55)', lineWidth: 1 });
      a.addOverlay(ov);
      for (const f of idx.fields) {
        const h = f.fov_arcmin / 120, cosd = Math.cos(f.dec * Math.PI / 180) || 1e-3;
        ov.add(Ali.polyline([[f.ra - h / cosd, f.dec - h], [f.ra + h / cosd, f.dec - h], [f.ra + h / cosd, f.dec + h], [f.ra - h / cosd, f.dec + h], [f.ra - h / cosd, f.dec - h]]));
      }
      const cat = Ali.catalog({ name: 'Searched patches', shape: small, sourceSize: 20 });
      a.addCatalog(cat);
      mk(cat, idx.fields.map(f => ({ name: f.title, kind: 'A patch we searched', ra: f.ra, dec: f.dec, fov: 1, ours: true, cat: 'finds' as Cat,
        blurb: `PARALLAX tested ${f.n_motion_tested.toLocaleString('en-US')} sources here for motion, across ${f.n_visits} SPHEREx visits.` })), 'fields', 20);
      g.fields.push(ov, cat);
    } catch { /* hunt unavailable */ }
    // distant worlds found with no hints: the real detections and the fitted path
    const cat = Ali.catalog({ name: 'Our finds', shape: pin, sourceSize: 30 });
    a.addCatalog(cat);
    g.finds.push(cat);
    try {
      const d = await distantApi.results();
      for (const b of d.bodies) {
        const o = b.object as any;
        if (!o) continue;
        const cosd = Math.cos(o.dec0_deg * Math.PI / 180);
        const toSky = (p: { dx_deg: number; dy_deg: number }) => [o.ra0_deg + p.dx_deg / cosd, o.dec0_deg + p.dy_deg];
        const ov = Ali.graphicOverlay({ name: `${b.title} path`, color: '#ffffff', lineWidth: 2 });
        a.addOverlay(ov);
        ov.add(Ali.polyline(o.curve.map(toSky)));
        const dots = Ali.catalog({ name: `${b.title} detections`, color: '#ffffff', sourceSize: 7, shape: 'circle' });
        a.addCatalog(dots);
        dots.addSources(o.detections.map((p: any) => { const [r, dd] = toSky(p); return Ali.source(r, dd, {}); }));
        const [r0, d0] = toSky(o.detections[0]);
        mk(cat, [{ name: `${b.title}, found with no hints`, kind: 'Our find · dwarf planet', ra: r0, dec: d0, fov: 5, ours: true, cat: 'finds',
          blurb: `PARALLAX measured ${b.match?.r_fit_au.toFixed(1)} AU from the Sun. NASA JPL says ${b.match?.r_true_au.toFixed(1)}. The line is the path it fitted; it loops because Earth moves.` }]);
        g.finds.push(ov, dots);
      }
    } catch { /* distant results unavailable */ }
    mk(cat, PLACES.filter(p => p.ra != null && p.ours && p.name !== 'Makemake, where we found it').map(p => ({ ...p, ra: p.ra!, dec: p.dec! })));
    // where Planet Nine is predicted (approximate)
    const band = Ali.graphicOverlay({ name: 'Planet Nine zone', color: '#ffffff', lineWidth: 1.5, lineDash: [8, 8] });
    a.addOverlay(band);
    band.add(Ali.polyline(P9_TRACK.map(([r, d]) => [r, d + 12])));
    band.add(Ali.polyline(P9_TRACK.map(([r, d]) => [r, d - 12])));
    const nine = Ali.catalog({ name: 'Planet Nine zone', shape: pin, sourceSize: 30 });
    a.addCatalog(nine);
    mk(nine, PLACES.filter(p => p.name === 'Planet Nine zone').map(p => ({ ...p, ra: p.ra!, dec: p.dec! })), 'nine');
    g.nine.push(band, nine);
    // forecasts locked for images that do not exist yet
    try {
      const fc = await huntApi.forecasts();
      const fcat = Ali.catalog({ name: 'Forecasts', color: '#ffffff', sourceSize: 6, shape: 'circle' });
      a.addCatalog(fcat);
      for (const f of fc.forecasts) fcat.addSources(f.predictions.map(p => Ali.source(p.ra_deg, p.dec_deg, { place: { name: `${f.title}, forecast`, kind: `Locked forecast for ${p.date_utc.slice(0, 7)}`, ra: p.ra_deg, dec: p.dec_deg, ours: true, blurb: 'A position we predicted and locked before SPHEREx took the image.' } })));
      g.forecasts.push(fcat);
      fcat.hide();
    } catch { /* forecasts unavailable */ }
    // the pin for whatever is selected
    selCat.current = Ali.catalog({ name: 'Selected', shape: pinCanvas(38), sourceSize: 38 });
    a.addCatalog(selCat.current);
  }

  // ---- layers ----
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layer, state]);
  useEffect(() => { try { cube.current?.setSliceNumber(slice); } catch { /* not ready */ } }, [slice]);
  useEffect(() => {
    if (!sweep || layer !== SPHEREX.id) return;
    const id = window.setInterval(() => setSlice(k => { let n = (k + 1) % WAVES.length; while (BLANK.has(n)) n = (n + 1) % WAVES.length; return n; }), 125);
    return () => window.clearInterval(id);
  }, [sweep, layer]);
  useEffect(() => {
    showRef.current = show;
    if (state !== 'ready') return;
    (Object.keys(show) as (keyof Toggles)[]).forEach(k => groups.current[k].forEach(o => { try { show[k] ? o.show() : o.hide(); } catch { /* ignore */ } }));
  }, [show, state]);

  // ---- the selected place: fly there and plant the big pin ----
  useEffect(() => {
    const a = al.current, Ali = A.current, cat = selCat.current;
    if (!a || !Ali || !cat) return;
    try { cat.removeAll?.(); } catch { /* ignore */ }
    if (!sel) return;
    try { cat.addSources([Ali.source(sel.ra, sel.dec, { place: sel })]); } catch { /* ignore */ }
    if (!sel.pin) { a.gotoRaDec(sel.ra, sel.dec); if (sel.fov) a.setFoV(sel.fov); }
  }, [sel, state]);

  const flash = (t: string) => { setToast(t); window.setTimeout(() => setToast(null), 2200); };
  const zoom = (f: number) => { const a = al.current; if (a) a.setFoV(Math.max(0.03, Math.min(180, a.getFov()[0] * f))); };

  async function find(text: string, known?: Place) {
    const t = text.trim();
    if (!t) return;
    setErr(null); setFocus(false); setList(null); setActiveChunk(null);
    const chunk = chunkFromId(t);
    if (chunk && al.current) {
      setSel(null);
      setQ(chunk.id);
      al.current.gotoRaDec(chunk.ra, chunk.dec);
      al.current.setFoV(CHUNK_SEARCH_FOV);
      return;
    }
    setBusy(true);
    try {
      const r = await resolveQuery(t);
      const k = known ?? PLACES.find(p => p.name.toLowerCase() === t.toLowerCase() || p.q?.toLowerCase() === t.toLowerCase());
      setSel({
        name: k?.name ?? r.name ?? t, kind: k?.kind ?? (r.moves ? 'Solar System body' : r.name ? 'Star or deep-sky object' : 'Coordinates'),
        blurb: k?.blurb, img: k?.img, cat: k?.cat, ours: k?.ours, ra: r.ra, dec: r.dec, fov: k?.fov ?? (r.moves ? 3 : 1.5), moves: !!r.moves,
        source: r.moves ? 'NASA JPL Horizons' : r.name ? 'the SIMBAD catalogue' : undefined,
      });
    } catch (x) { setSel(null); setErr((x as Error).message || `Couldn't find "${t}".`); }
    finally { setBusy(false); }
  }
  async function pick(p: Place) {
    setFocus(false); setErr(null); setQ(p.name); setList(null);
    if (p.ra != null && p.dec != null) { setSel({ ...p, ra: p.ra, dec: p.dec }); return; }
    await find(p.q ?? p.name, p);
  }
  const submit = (e: FormEvent) => { e.preventDefault(); void find(q); };

  // a search handed over from the home page: /map?q=Pluto
  useEffect(() => {
    if (state !== 'ready') return;
    const pq = new URLSearchParams(window.location.search).get('q');
    if (pq) { setQ(pq); void find(pq); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  const sugg = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return PLACES.filter(p => POPULAR.includes(p.name));
    const rank = (p: Place) => { const n = p.name.toLowerCase(); return n.startsWith(t) ? 0 : n.includes(t) ? 1 : p.kind.toLowerCase().includes(t) ? 2 : 9; };
    return PLACES.map(p => ({ p, r: rank(p) })).filter(x => x.r < 9).sort((a, b) => a.r - b.r).slice(0, 7).map(x => x.p);
  }, [q]);

  async function copyLink(url: string) {
    try { await navigator.clipboard.writeText(url); flash('Link copied'); } catch { flash(url); }
  }
  function share() {
    if (!sel) return;
    const url = `${window.location.origin}/map?ra=${sel.ra.toFixed(5)}&dec=${sel.dec.toFixed(5)}&fov=${(sel.fov ?? centre?.fov ?? 3).toFixed(2)}`;
    return copyLink(url);
  }
  const imagesFov = (s: Sel) => Math.min(20, Math.max(4, Math.round(((s.fov ?? centre?.fov ?? 0.2) * 60) / 3)));
  const today = new Date().toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' });
  const hasCard = !!(sel && !sel.pin) || !!list;
  const centreChunk = centre && centre.fov <= CHUNK_GRID_FOV ? chunkAt(centre.ra, centre.dec) : null;
  const centreStatus = centreChunk && chunkTeam.assignments?.[centreChunk.id]?.status;
  const suggestedChunk = chunkFromId(q);

  function openChunk(id: string, opener: HTMLButtonElement) {
    chunkOpener.current = opener;
    setSel(null);
    setList(null);
    setLayersOpen(false);
    setActiveChunk(id);
  }

  return (
    <div className={`gm${hasCard ? ' has-card' : ''}${centreChunk ? ' gm--chunks' : ''}`}>
      <div ref={box} className="gm__map" aria-label="Interactive map of the whole sky. Drag to pan, scroll to zoom, click to drop a pin." role="application" />
      {chunkLabels.length > 0 && <div className="gm-chunk-labels" role="group" aria-label="Visible sky chunks">
        {chunkLabels.map(({ id, x, y }) => {
          const assignment = chunkTeam.assignments?.[id];
          const status = assignment?.status ?? 'unclaimed';
          const names = assignment ? [assignment.name, ...assignment.teammates.map(person => person.name)].join(', ') : '';
          const details = chunkTeam.assignments ? `, ${CHUNK_STATUS_LABEL[status]}${names ? `, ${names}` : ''}` : '';
          return <button key={id} type="button" style={{ left: x, top: y }} aria-label={`Chunk ${id}${details}`}
            title={names ? `${CHUNK_STATUS_LABEL[status]} · ${names}` : undefined}
            aria-expanded={activeChunk === id} onClick={event => openChunk(id, event.currentTarget)}>
            <span>{assignment && <i className="gm-chunk-dot" data-status={status} />}{id}</span>
            {assignment && <small className="gm-chunk-names"><span>{assignment.name}</span>
              {assignment.teammates.length > 0 && <b>+{assignment.teammates.length}</b>}
            </small>}
          </button>;
        })}
      </div>}
      {state === 'loading' && <p className="gm-load">Opening the sky…</p>}
      {state === 'error' && <p className="gm-load">The sky map needs WebGL 2 and a network connection. {err}</p>}

      <div className="gm-search">
        <form className="gm-search__box" onSubmit={submit} role="search">
          <Link href="/" className="gm-search__home" aria-label="PARALLAX home"><Mark size={22} /></Link>
          <label className="visually-hidden" htmlFor="gm-q">Search the sky by object, coordinates or chunk ID</label>
          <input id="gm-q" value={q} onChange={e => { setQ(e.target.value); setFocus(true); }} onFocus={() => setFocus(true)} onBlur={() => window.setTimeout(() => setFocus(false), 160)}
            placeholder="Search the sky" autoComplete="off" spellCheck={false} />
          <button type="submit" className="gm-ic" aria-label="Search" disabled={busy}><IcSearch /></button>
          {(q || sel || list) && <><span className="gm-search__sep" /><button type="button" className="gm-ic" aria-label="Clear" onClick={() => { setQ(''); setSel(null); setList(null); setErr(null); }}><IcX /></button></>}
        </form>
        {focus && (suggestedChunk || sugg.length > 0) && (
          <div className="gm-sugg">
            {!q.trim() && <p className="gm-sugg__hd">Popular places</p>}
            {suggestedChunk && <button type="button" className="gm-sugg__row" onMouseDown={e => e.preventDefault()} onClick={() => void find(suggestedChunk.id)}>
              <IcGlobe /><span><b>{suggestedChunk.id}</b><span>Sky chunk</span></span>
            </button>}
            {sugg.map(p => (
              <button key={p.name} type="button" className="gm-sugg__row" onMouseDown={e => e.preventDefault()} onClick={() => void pick(p)}>
                {catIcon(p.cat)}<span style={{ margin: 0 }}><b>{p.name}</b><span>{p.kind}</span></span>
              </button>
            ))}
            {q.trim() && !suggestedChunk && <button type="button" className="gm-sugg__row" onMouseDown={e => e.preventDefault()} onClick={() => void find(q)}><IcSearch /><span style={{ margin: 0 }}><b>Search for “{q.trim()}”</b><span>star, planet, coordinates or chunk ID</span></span></button>}
          </div>
        )}
        {err && !focus && <p className="gm-err" role="alert">{err}</p>}
      </div>

      <div className="gm-chips" role="group" aria-label="Kinds of places">
        {CATS.map(c => (
          <button key={c.id} type="button" className={`gm-chip${list === c.id ? ' is-on' : ''}`} onClick={() => { setSel(null); setErr(null); setActiveChunk(null); setList(list === c.id ? null : c.id); }}>
            {catIcon(c.id)}{c.label}
          </button>
        ))}
      </div>

      {list && (
        <section className="gm-card" aria-label={CATS.find(c => c.id === list)?.label}>
          <div className="gm-list__hd"><h2>{CATS.find(c => c.id === list)?.label}</h2><button type="button" className="gm-ic" aria-label="Close" onClick={() => setList(null)}><IcX /></button></div>
          <div className="gm-card__scroll">
            {PLACES.filter(p => p.cat === list).map(p => (
              <button key={p.name} type="button" className="gm-list__row" onClick={() => void pick(p)}>
                {catIcon(p.cat)}<span><b>{p.name}</b><span>{p.kind}{p.ours ? ' · PARALLAX result' : ''}</span></span>
              </button>
            ))}
          </div>
        </section>
      )}

      {sel && !sel.pin && !list && (
        <section className="gm-card" aria-label={sel.name}>
          <div className="gm-card__scroll">
            <div className="gm-card__pic">
              {sel.img ? <img src={sel.img} alt="" /> : catIcon(sel.cat)}
              <button type="button" className="gm-ic gm-card__close" aria-label="Close" onClick={() => setSel(null)}><IcX /></button>
            </div>
            <div className="gm-card__body">
              <h2 className="gm-card__title">{sel.name}</h2>
              <p className="gm-card__kind">{sel.kind}</p>
              {sel.ours && <p className="gm-card__meta">PARALLAX result</p>}
            </div>
            <div className="gm-acts">
              <button type="button" className="gm-act gm-act--main" onClick={() => navigate(openHere(sel.ra, sel.dec, imagesFov(sel)))}><i><IcImages /></i>Real images</button>
              <button type="button" className="gm-act" onClick={() => zoom(0.4)}><i><IcPlus /></i>Zoom in</button>
              <button type="button" className="gm-act" onClick={() => zoom(2.5)}><i><IcMinus /></i>Zoom out</button>
              <button type="button" className="gm-act" onClick={() => void share()}><i><IcShare /></i>Share</button>
            </div>
            <div className="gm-rows">
              {sel.blurb && <div className="gm-row"><IcInfo /><span>{sel.blurb}</span></div>}
              <div className="gm-row"><IcPin /><span>{fmtCoord(sel.ra, sel.dec)}<small>Right ascension, declination</small></span></div>
              {sel.moves && <div className="gm-row"><IcClock /><span>Here on {today}<small>It moves, so next month it will be somewhere else. Position from {sel.source}.</small></span></div>}
              {!sel.moves && sel.source && <div className="gm-row"><IcInfo /><span>Position from {sel.source}</span></div>}
            </div>
          </div>
        </section>
      )}

      <div className="gm-layers">
        <button type="button" className="gm-tile" aria-expanded={layersOpen} aria-label="Layers: choose which telescope's sky to show" onClick={() => { setActiveChunk(null); setLayersOpen(v => !v); }}>
          <img src={(LAYERS.find(l => l.id !== layer && l.id !== SPHEREX.id) ?? LAYERS[1]).thumb} alt="" />
          <span className="gm-tile__lb"><IcLayers />Layers</span>
        </button>
        {layersOpen && (
          <div className="gm-pop" role="dialog" aria-label="Layers">
            <div className="gm-pop__tiles" role="radiogroup" aria-label="Telescope">
              {LAYERS.map(l => (
                <button key={l.id} type="button" role="radio" aria-checked={layer === l.id} className={`gm-ltile${layer === l.id ? ' is-on' : ''}`} onClick={() => setLayer(l.id)}>
                  <i><img src={l.thumb} alt="" loading="lazy" /></i>{l.label}<br />{l.year}
                </button>
              ))}
            </div>
            {layer === SPHEREX.id && (
              <div className="gm-pop__sec">
                <div className="gm-pop__hd"><span>Infrared colour</span><b>{WAVES[slice].toFixed(2)} µm{WAVES[slice] < 1.1 ? ' · reflected sunlight' : WAVES[slice] > 3.8 ? ' · where cold worlds glow' : ''}</b></div>
                <input type="range" aria-label="Infrared colour" min={0} max={WAVES.length - 1} value={slice} onChange={e => { setSweep(false); setSlice(Number(e.target.value)); }} />
                <button type="button" className="gm-pop__play" onClick={() => setSweep(v => !v)}>{sweep ? 'Stop' : 'Play all 102 colours'}</button>
              </div>
            )}
            <div className="gm-pop__sec">
              <div className="gm-pop__hd"><span>Map details</span></div>
              <div className="gm-checks">
                {([['finds', 'Our finds'], ['fields', 'Patches we searched'], ['nine', 'Planet Nine zone'], ['forecasts', 'Locked forecasts']] as [keyof Toggles, string][]).map(([k, label]) => (
                  <label key={k}><input type="checkbox" checked={show[k]} onChange={e => setShow(s => ({ ...s, [k]: e.target.checked }))} />{label}</label>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {sel?.pin && (
        <div className="gm-drop" role="status">
          <IcPin />
          <span><b>Dropped pin</b><span>{fmtCoord(sel.ra, sel.dec)}</span></span>
          <button type="button" className="gm-btn" onClick={() => navigate(openHere(sel.ra, sel.dec, 10))}>See real images</button>
          <button type="button" className="gm-ic" aria-label="Remove pin" onClick={() => setSel(null)}><IcX /></button>
        </div>
      )}
      {toast && <p className="gm-toast" role="status">{toast}</p>}

      <div className="gm-ctl">
        <button type="button" className="gm-ctl__one" aria-label="Show the whole sky" onClick={() => { setActiveChunk(null); al.current?.setFoV(180); }}><IcGlobe /></button>
        <div className="gm-ctl__grp">
          <button type="button" aria-label="Zoom in" onClick={() => zoom(0.5)}><IcPlus /></button>
          <button type="button" aria-label="Zoom out" onClick={() => zoom(2)}><IcMinus /></button>
        </div>
      </div>
      <div className="gm-status">
        {centreChunk && <button type="button" className="gm-status__chunk" aria-expanded={activeChunk === centreChunk.id}
          onClick={event => openChunk(centreChunk.id, event.currentTarget)}>
          <IcGlobe />Chunk {centreChunk.id}{centreStatus && <i className="gm-chunk-dot" data-status={centreStatus} />}
        </button>}
        <span className="gm-status__coords">{centre ? `${fmtCoord(centre.ra, centre.dec)} · ${fmtFov(centre.fov)}` : ''}</span>
        <span className="gm-status__credits">
          <span>Sky: NASA/IPAC IRSA (SPHEREx DR1, WISE, 2MASS, DSS2, IRAS) · Map: Aladin Lite ·</span>
          <Link href="/about">Sources</Link>
        </span>
      </div>
      {activeChunk && <ChunkReview key={activeChunk} id={activeChunk} team={chunkTeam}
        onClose={() => { setActiveChunk(null); chunkOpener.current?.focus(); }}
        onCopy={() => void copyLink(`${window.location.origin}/map?chunk=${activeChunk}`)} />}
    </div>
  );
}
