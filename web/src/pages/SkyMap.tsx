import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Mark } from '../components/Shell.tsx';
import { Link, navigate } from '../router.tsx';
import { huntApi } from '../api.ts';
import { resolveQuery } from '../components/SearchBox.tsx';
import { CHUNK_STATUS_LABEL, ChunkReview, useChunkAssignments } from '../components/ChunkReview.tsx';
import { CHUNKS, chunkAt, chunkFromId, chunkGridLines } from '../lib/skyChunks.ts';
import { SOLAR_IMAGES } from '../lib/solarImages.ts';
import { SPHEREX_MAP_BANDS } from '../lib/skySurvey.ts';
import { parseDec, parseRA } from '../lib/astro.ts';
import { distantApi } from './Distant.tsx';
import '../map.css';
import { OtherScopes } from '../components/OtherScopes.tsx';

/* eslint-disable @typescript-eslint/no-explicit-any */
type AladinNS = any;

// Survey layers (HiPS) from the archives listed on each layer.
const IRSA = 'https://irsa.ipac.caltech.edu/data/hips';
const ESA = 'https://skies.esac.esa.int';
const MASTS3 = 'https://stpubdata.s3.us-east-1.amazonaws.com/mast/skybackgrounds';
type Light = 'Infrared' | 'Visible' | 'Ultraviolet' | 'X-ray' | 'Gamma ray' | 'Microwave';
type Cover = 'all' | 'most' | 'part' | 'patches';
interface Layer { id: string; fmt: string; label: string; year: string; light: Light; who: string; host: string; cover: Cover; thumb?: string;
  eg?: { name: string; ra: number; dec: number; fov: number } }
const SPHEREX: Layer = { id: `${IRSA}/SPHEREx/spherex_allsky_cube`, fmt: 'png', label: 'SPHEREx', year: 'DR1', light: 'Infrared', who: 'NASA', host: 'NASA/IPAC IRSA', cover: 'all', thumb: '/img/spherex-vela.webp' };
const LAYERS: Layer[] = [
  SPHEREX,
  { id: `${ESA}/JWST/NIRCam_Imaging`, fmt: 'png', label: 'JWST', year: '2022–', light: 'Infrared', who: 'NASA, ESA, CSA', host: 'ESA ESASky (eJWST)', cover: 'patches', eg: { name: 'the Pillars of Creation', ra: 274.7000, dec: -13.8070, fov: 0.08 } },
  { id: `${IRSA}/CDS/AllWISE/RGB-W4-W2-W1`, fmt: 'jpeg', label: 'WISE', year: '2010', light: 'Infrared', who: 'NASA', host: 'NASA/IPAC IRSA', cover: 'all', thumb: `${IRSA}/CDS/AllWISE/RGB-W4-W2-W1/preview.jpg` },
  { id: `${IRSA}/CDS/2MASS/Color`, fmt: 'jpeg', label: '2MASS', year: '1998', light: 'Infrared', who: 'NASA, NSF', host: 'NASA/IPAC IRSA', cover: 'all', thumb: `${IRSA}/CDS/2MASS/Color/preview.jpg` },
  { id: `${ESA}/Spitzer/IRAC134_RGB_bright`, fmt: 'png', label: 'Spitzer', year: '2003–20', light: 'Infrared', who: 'NASA', host: 'ESA ESASky', cover: 'patches', eg: { name: 'the Orion Nebula', ra: 83.8221, dec: -5.3911, fov: 1.2 } },
  { id: 'https://padc-web.obspm.fr/planeto/hips/VOXASTRO_P_VHS_COLOR', fmt: 'png', label: 'VISTA', year: '2009–', light: 'Infrared', who: 'ESO', host: 'ESO VHS, via PADC', cover: 'part', eg: { name: 'the Sculptor Galaxy', ra: 11.8880, dec: -25.2880, fov: 0.6 } },
  { id: 'https://padc-web.obspm.fr/planeto/hips/VOXASTRO_P_UKIDSS_COLOR', fmt: 'png', label: 'UKIRT', year: '2005–12', light: 'Infrared', who: 'UKIRT', host: 'UKIDSS, via PADC', cover: 'part', eg: { name: 'the Orion Nebula', ra: 83.8221, dec: -5.3911, fov: 1 } },
  { id: `${ESA}/AKARI/color`, fmt: 'jpeg', label: 'AKARI', year: '2006–07', light: 'Infrared', who: 'JAXA', host: 'ESA ESASky', cover: 'all' },
  { id: `${ESA}/Herschel/color`, fmt: 'png', label: 'Herschel', year: '2009–13', light: 'Infrared', who: 'ESA', host: 'ESA ESASky', cover: 'part', eg: { name: 'the Orion Nebula', ra: 83.8221, dec: -5.3911, fov: 1.5 } },
  { id: `${IRSA}/CDS/IRIS/color`, fmt: 'jpeg', label: 'IRAS', year: '1983', light: 'Infrared', who: 'NASA, UK, NL', host: 'NASA/IPAC IRSA', cover: 'all', thumb: `${IRSA}/CDS/IRIS/color/preview.jpg` },
  { id: `${IRSA}/CDS/DSS2/color`, fmt: 'jpeg', label: 'Photo plates', year: '1950s–90s', light: 'Visible', who: 'STScI', host: 'NASA/IPAC IRSA', cover: 'all', thumb: `${IRSA}/CDS/DSS2/color/preview.jpg` },
  { id: `${MASTS3}/PanSTARRS`, fmt: 'jpeg', label: 'Pan-STARRS', year: '2010–14', light: 'Visible', who: 'University of Hawaii', host: 'NASA MAST', cover: 'most', thumb: `${MASTS3}/PanSTARRS/preview.jpg` },
  { id: `${IRSA}/CDS/SDSS/DR9/color`, fmt: 'jpeg', label: 'SDSS', year: '2000–08', light: 'Visible', who: 'SDSS', host: 'NASA/IPAC IRSA', cover: 'part', thumb: `${IRSA}/CDS/SDSS/DR9/color/preview.jpg`, eg: { name: 'the Whirlpool Galaxy', ra: 202.4696, dec: 47.1952, fov: 0.3 } },
  { id: `${ESA}/HST/ACS`, fmt: 'jpeg', label: 'Hubble', year: '2002–', light: 'Visible', who: 'NASA, ESA', host: 'ESA ESASky (eHST)', cover: 'patches', eg: { name: 'the Whirlpool Galaxy', ra: 202.4696, dec: 47.1952, fov: 0.15 } },
  { id: `${ESA}/Gaia/dr3/RGB`, fmt: 'png', label: 'Gaia', year: '2014–17', light: 'Visible', who: 'ESA', host: 'ESA ESASky', cover: 'all' },
  { id: `${MASTS3}/GALEXColor`, fmt: 'png', label: 'GALEX', year: '2003–12', light: 'Ultraviolet', who: 'NASA', host: 'NASA MAST', cover: 'most', thumb: `${MASTS3}/GALEXColor/preview.jpg` },
  { id: 'https://skyview.gsfc.nasa.gov/surveys/uvot/int/color2', fmt: 'jpg', label: 'Swift', year: '2004–', light: 'Ultraviolet', who: 'NASA', host: 'NASA HEASARC SkyView', cover: 'patches', eg: { name: 'the Andromeda Galaxy', ra: 10.6847, dec: 41.2687, fov: 1.5 } },
  { id: 'https://cdaftp.cfa.harvard.edu/cxc-hips', fmt: 'png', label: 'Chandra', year: '1999–', light: 'X-ray', who: 'NASA', host: 'Chandra X-ray Center', cover: 'patches', eg: { name: 'the Crab Nebula', ra: 83.6331, dec: 22.0145, fov: 0.15 } },
  { id: 'https://esdchips.esac.esa.int/XMM-Newton/EPIC-RGB', fmt: 'jpeg', label: 'XMM-Newton', year: '1999–', light: 'X-ray', who: 'ESA', host: 'ESA', cover: 'patches', eg: { name: 'Cassiopeia A', ra: 350.8500, dec: 58.8150, fov: 0.3 } },
  { id: 'https://erosita.mpe.mpg.de/erodat/static/hips/eRASS1_RGB_Rate_c010', fmt: 'png', label: 'eROSITA', year: '2019–20', light: 'X-ray', who: 'MPE (Germany)', host: 'MPE', cover: 'part', eg: { name: 'the Vela supernova remnant', ra: 128.8, dec: -45.2, fov: 12 } },
  { id: `${ESA}/FermiColor`, fmt: 'jpeg', label: 'Fermi', year: '2008–', light: 'Gamma ray', who: 'NASA', host: 'ESA ESASky', cover: 'all', thumb: `${ESA}/FermiColor/preview.jpg` },
  { id: `${ESA}/Integral/color`, fmt: 'jpeg', label: 'INTEGRAL', year: '2002–25', light: 'Gamma ray', who: 'ESA', host: 'ESA ESASky', cover: 'all' },
  { id: `${IRSA}/CDS/PLANCK/R2/HFI/color`, fmt: 'jpeg', label: 'Planck', year: '2009–13', light: 'Microwave', who: 'ESA', host: 'NASA/IPAC IRSA', cover: 'all', thumb: `${IRSA}/CDS/PLANCK/R2/HFI/color/preview.jpg` },
];
const LIGHTS: { light: Light; glyph: string; say: string }[] = [
  { light: 'Infrared', glyph: 'IR', say: 'Heat light, and the colours just past red' },
  { light: 'Visible', glyph: 'V', say: 'The light our eyes see' },
  { light: 'Ultraviolet', glyph: 'UV', say: 'Past violet: hot young stars' },
  { light: 'X-ray', glyph: 'X', say: 'Very hot gas, black holes, dead stars' },
  { light: 'Gamma ray', glyph: 'γ', say: 'The most energetic light there is' },
  { light: 'Microwave', glyph: 'µ', say: 'Cold dust and the glow left over from the Big Bang' },
];
const COVER: Record<Cover, string> = { all: 'the whole sky', most: 'most of the sky', part: 'part of the sky', patches: 'only small patches' };
// An approximate segment of the Brown & Batygin (2021) model corridor. See docs/PLANET_NINE_RESEARCH.md.
const P9_TRACK: [number, number][] = [[33, -2], [46, 4], [60, 11], [74, 16], [90, 21], [107, 25]];

type Cat = 'planets' | 'dwarfs' | 'finds' | 'nasa' | 'cold' | 'deep' | 'stars' | 'sun-moon';
interface Place {
  name: string; kind: string; cat: Cat; blurb: string;
  q?: string;                       // object name for an updated position
  ra?: number; dec?: number;        // fixed sky field or historical marker
  fov?: number; ours?: boolean;
}
const PLACES: Place[] = [
  { name: 'The Sun', kind: 'Our star', cat: 'sun-moon', q: 'Sun', blurb: 'SPHEREx surveys the sky away from the Sun.' },
  { name: 'The Moon', kind: 'Moon', cat: 'sun-moon', q: 'Moon', blurb: 'Its position and phase change as it orbits Earth.' },
  { name: 'Mercury', kind: 'Planet', cat: 'planets', q: 'Mercury', blurb: 'The closest planet to the Sun.' },
  { name: 'Venus', kind: 'Planet', cat: 'planets', q: 'Venus', blurb: 'The brightest planet in our sky.' },
  { name: 'Mars', kind: 'Planet', cat: 'planets', q: 'Mars', blurb: 'The red planet.' },
  { name: 'Jupiter', kind: 'Planet', cat: 'planets', q: 'Jupiter', blurb: 'The largest planet in our Solar System.' },
  { name: 'Saturn', kind: 'Planet', cat: 'planets', q: 'Saturn', blurb: 'The ringed planet.' },
  { name: 'Uranus', kind: 'Planet', cat: 'planets', q: 'Uranus', blurb: 'An ice giant, 19 times farther from the Sun than Earth.' },
  { name: 'Neptune', kind: 'Planet', cat: 'planets', q: 'Neptune', blurb: 'Found in 1846, right where the maths said it would be.' },
  { name: 'Pluto', kind: 'Dwarf planet', cat: 'dwarfs', q: 'Pluto', blurb: 'Found in 1930 by comparing two photos of the same sky.' },
  { name: 'Makemake', kind: 'Dwarf planet', cat: 'dwarfs', q: 'Makemake', blurb: 'PARALLAX found it with no hints and measured its distance: 52.7 AU.', ours: true },
  { name: 'Eris', kind: 'Dwarf planet', cat: 'dwarfs', q: 'Eris', blurb: 'PARALLAX recovered Eris by stacking images along its path and measured its distance: 95.5 AU.', ours: true },
  { name: 'Haumea', kind: 'Dwarf planet', cat: 'dwarfs', q: 'Haumea', blurb: 'An egg-shaped dwarf planet with a ring.' },
  { name: 'Ceres', kind: 'Dwarf planet', cat: 'dwarfs', q: 'Ceres', blurb: 'The largest body in the asteroid belt.' },
  { name: 'Sedna', kind: 'Distant world', cat: 'dwarfs', q: 'Sedna', blurb: 'One of the most distant known worlds. Its odd orbit is a clue in the Planet Nine debate.' },
  { name: 'Makemake, where we found it', kind: 'Our find', cat: 'finds', ra: 201.3, dec: 20.6, fov: 6, blurb: 'The path PARALLAX fitted through three SPHEREx visits. It loops because Earth moves.', ours: true },
  { name: 'Epsilon Indi B', kind: 'Brown dwarf pair', cat: 'finds', q: 'Epsilon Indi B', ra: 331.0976, dec: -56.8012, fov: 0.6, blurb: 'We locked a prediction of where it would be, then opened the images. It landed 0.07″ away.', ours: true },
  { name: 'Planet Nine zone', kind: 'Model estimate', cat: 'finds', ra: 60, dec: 11, fov: 60, blurb: 'The dashed lines show an approximate search corridor based on Brown and Batygin’s 2021 model. Planet Nine remains unconfirmed.' },
  { name: 'WISE 0855', kind: 'Brown dwarf', cat: 'cold', q: 'WISE 0855', ra: 133.787, dec: -7.2445, fov: 0.6, blurb: 'The coldest known brown dwarf, near the freezing point of water. PARALLAX found it by its motion alone.', ours: true },
  { name: "Barnard's Star", kind: 'Red dwarf', cat: 'cold', q: "Barnard's Star", ra: 269.4486, dec: 4.7379, fov: 0.6, blurb: 'The fastest-moving star in our sky. Too bright for the camera, so we measured its halo.', ours: true },
  { name: 'Luhman 16', kind: 'Brown dwarf pair', cat: 'cold', q: 'Luhman 16', fov: 0.6, blurb: 'The closest brown dwarfs to the Sun, 6.5 light-years away.' },
  { name: 'Orion Nebula', kind: 'Nebula', cat: 'deep', ra: 83.8221, dec: -5.3911, fov: 2, blurb: 'A cloud where stars are being born, 1,300 light-years away.' },
  { name: 'Andromeda Galaxy', kind: 'Galaxy', cat: 'deep', ra: 10.6847, dec: 41.2687, fov: 4, blurb: 'Our nearest large galaxy, 2.5 million light-years away.' },
  { name: 'Milky Way centre', kind: 'Galactic centre', cat: 'deep', ra: 266.4168, dec: -29.0078, fov: 8, blurb: 'The crowded heart of our galaxy. Infrared light sees through the dust.' },
  { name: 'Large Magellanic Cloud', kind: 'Galaxy', cat: 'deep', ra: 80.8938, dec: -69.7561, fov: 10, blurb: 'A small galaxy that orbits ours.' },
  { name: 'Pleiades', kind: 'Star cluster', cat: 'deep', ra: 56.75, dec: 24.1167, fov: 3, blurb: 'The Seven Sisters.' },
  { name: 'Vega', kind: 'Star', cat: 'stars', q: 'Vega', fov: 2, blurb: 'One of the brightest stars, 25 light-years away.' },
  { name: 'Sirius', kind: 'Star', cat: 'stars', q: 'Sirius', fov: 2, blurb: 'The brightest star in the night sky.' },
  { name: 'Betelgeuse', kind: 'Star', cat: 'stars', q: 'Betelgeuse', fov: 2, blurb: "A red supergiant in Orion's shoulder." },
  { name: 'Polaris', kind: 'Star', cat: 'stars', q: 'Polaris', fov: 4, blurb: 'The North Star.' },
  { name: 'RW Aurigae', kind: 'Variable star', cat: 'stars', q: 'RW Aurigae', fov: 0.6, blurb: "A young star that dims when dust drifts in front of it. One of NASA's five test targets. Too bright for the camera, so we measure the ring of light around it." },
  { name: 'R Draconis', kind: 'Variable star', cat: 'stars', q: 'R Draconis', fov: 0.6, blurb: "A red giant that swells and shrinks, brightening and fading about every eight months. One of NASA's five test targets. Too bright for the camera, so we measure the ring of light around it." },
];
const CATS: { id: Cat; label: string }[] = [
  { id: 'finds', label: 'Our finds' }, { id: 'nasa', label: "NASA's 5 targets" }, { id: 'planets', label: 'Planets' }, { id: 'dwarfs', label: 'Dwarf planets and candidates' },
  { id: 'cold', label: 'Cold neighbours' }, { id: 'deep', label: 'Nebulae and galaxies' }, { id: 'stars', label: 'Stars' },
  { id: 'sun-moon', label: 'Sun and Moon' },
];
// The five objects the challenge asks every tool to be tested on, in the order the challenge lists them.
// They keep their own categories too; this chip just gathers them in one place.
const NASA_FIVE = ["Barnard's Star", 'Epsilon Indi B', 'WISE 0855', 'RW Aurigae', 'R Draconis'];
const inList = (c: Cat) => (c === 'nasa' ? NASA_FIVE.flatMap(n => PLACES.filter(p => p.name === n)) : PLACES.filter(p => p.cat === c));
const POPULAR = ['Makemake, where we found it', 'Pluto', 'WISE 0855', 'Orion Nebula', 'Planet Nine zone', 'Andromeda Galaxy'];

interface Sel { name: string; kind: string; blurb?: string; ra: number; dec: number; fov?: number; solarQuery?: string; bodyId?: string; positionUtc?: string; source?: string; epochNote?: string; ours?: boolean; cat?: Cat; pin?: boolean }
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
const IcInfo = () => I(<><circle cx="12" cy="12" r="8.500" /><path d="M12 11v5.500M12 7.800v.2" /></>);
const IcTarget = () => I(<><circle cx="12" cy="12" r="7.5" /><circle cx="12" cy="12" r="2.6" /><path d="M12 2v3.5M12 18.5V22M2 12h3.5M18.5 12H22" /></>);
const catIcon = (c?: Cat) => c === 'nasa' ? <IcTarget /> : c === 'planets' || c === 'dwarfs' ? <IcPlanet /> : c === 'deep' ? <IcSpiral /> : c === 'stars' || c === 'sun-moon' ? <IcStar /> : c === 'cold' ? <IcSnow /> : c === 'finds' ? <IcFlag /> : <IcPin />;

function hips(Ali: AladinNS, a: any, l: Layer, errorCallback: () => void) {
  const opts = { name: l.label, imgFormat: l.fmt, errorCallback };
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

/** Aladin supplies the projected pixel of the source. Leave its center open to show the sky underneath. */
function drawEphemerisMarker(source: { x: number; y: number; data: { name: string } }, ctx: CanvasRenderingContext2D) {
  ctx.save();
  ctx.translate(source.x, source.y);
  ctx.beginPath();
  ctx.arc(0, 0, 9, 0, Math.PI * 2);
  ctx.moveTo(-14, 0); ctx.lineTo(-9, 0);
  ctx.moveTo(9, 0); ctx.lineTo(14, 0);
  ctx.moveTo(0, -14); ctx.lineTo(0, -9);
  ctx.moveTo(0, 9); ctx.lineTo(0, 14);
  ctx.lineWidth = 4;
  ctx.strokeStyle = '#161617';
  ctx.stroke();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = '#ffd39a';
  ctx.stroke();

  const label = `${source.data.name} · JPL position`;
  ctx.font = '600 12px system-ui';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const labelWidth = Math.min(ctx.measureText(label).width, 232);
  ctx.beginPath();
  ctx.roundRect(-labelWidth / 2 - 8, 19, labelWidth + 16, 24, 5);
  ctx.fillStyle = '#1e1f20';
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = '#ffd39a';
  ctx.fillText(label, 0, 31, labelWidth);
  ctx.restore();
}

const fmtCoord = (ra: number, dec: number) => `${(Number(ra.toFixed(4)) % 360).toFixed(4)}°, ${dec >= 0 ? '+' : '−'}${Math.abs(dec).toFixed(4)}°`;
const fmtFov = (f: number) => f >= 1 ? `${f.toFixed(f >= 10 ? 0 : 1)}° wide` : `${(f * 60).toFixed(0)}′ wide`;
const openHere = (ra: number, dec: number, fov = 10) => `/explore?ra=${ra.toFixed(5)}&dec=${dec.toFixed(5)}&fov=${fov}`;
const ephemerisTime = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});
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
  const pendingLayer = useRef<any>(null);
  const bandIndex = useRef(41);
  const groups = useRef<Record<keyof Toggles, any[]>>({ finds: [], fields: [], nine: [], forecasts: [] });
  const selCat = useRef<any>(null);
  const ephemerisCat = useRef<any>(null);
  const pins = useRef<{ place: Sel; size: number; group: keyof Toggles }[]>([]);
  const showRef = useRef<Toggles | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [layer, setLayer] = useState(LAYERS[0].id);
  const activeLayer = LAYERS.find(l => l.id === layer) ?? SPHEREX;
  const [slice, setSlice] = useState(41);
  const [layerStatus, setLayerStatus] = useState<'loading' | 'ready' | 'error'>('loading');
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
  const [scopes, setScopes] = useState<{ ra: number; dec: number; name: string } | null>(null);

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
        const fov = Number(params.get('fov'));
        const chunk = chunkFromId(params.get('chunk') ?? '');
        let target = '201.3 +20.6';
        if (chunk) target = `${chunk.ra} ${chunk.dec}`;
        else if (params.has('ra') || params.has('dec')) {
          try {
            target = `${parseRA(params.get('ra') ?? '')} ${parseDec(params.get('dec') ?? '')}`;
          } catch {
            setErr('This link needs a valid right ascension and declination. Enter both in Search the sky.');
          }
        }
        const a = Ali.aladin(box.current, {
          survey: SPHEREX.id, fov: chunk ? CHUNK_SEARCH_FOV : Number.isFinite(fov) && fov > 0 ? Math.min(180, Math.max(0.03, fov)) : 60, target, projection: 'SIN', cooFrame: 'ICRS', log: false,
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
        a.on('stackChanged', ({ change, layer: added }: { change: string; layer?: any }) => {
          if (!alive || change !== 'added' || !added || added !== pendingLayer.current) return;
          if (added === cube.current) added.setFrequency({ value: SPHEREX_MAP_BANDS[bandIndex.current].tileFrequencyHz, unit: 'Hz' });
          setLayerStatus('ready');
        });
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
          else setSel({ name: 'Dropped pin', kind: 'A spot in the sky', ra: e.ra, dec: e.dec, pin: true });
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
        const toSky = (p: { dx_deg: number; dy_deg: number }) => [
          ((o.ra0_deg + p.dx_deg / cosd) % 360 + 360) % 360, o.dec0_deg + p.dy_deg,
        ];
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
    mk(cat, PLACES.filter(p => p.ra != null && p.ours && p.name !== 'Makemake, where we found it')
      .map(p => ({ ...p, ra: p.ra!, dec: p.dec!, kind: `${p.kind} · historical field` })));
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
      for (const f of fc.forecasts) mk(fcat, f.predictions.map(p => ({
        name: `${f.title}, forecast`, kind: `Locked prediction for ${p.date_utc.slice(0, 10)} UTC`,
        ra: p.ra_deg, dec: p.dec_deg, fov: 0.4, cat: 'finds',
        blurb: 'The marker shows the predicted location. The archive field shows observations taken at their own dates.',
      })), 'forecasts', 6);
      g.forecasts.push(fcat);
      fcat.hide();
    } catch { /* forecasts unavailable */ }
    // the pin for whatever is selected
    selCat.current = Ali.catalog({ name: 'Selected', shape: pinCanvas(38), sourceSize: 38 });
    a.addCatalog(selCat.current);
    ephemerisCat.current = Ali.catalog({ name: 'JPL position', shape: drawEphemerisMarker, sourceSize: 28 });
    a.addCatalog(ephemerisCat.current);
  }

  // ---- layers ----
  useEffect(() => {
    const a = al.current;
    if (!a || state !== 'ready') return;
    const l = LAYERS.find(x => x.id === layer);
    if (!l) return;
    setLayerStatus('loading');
    let current = true;
    try {
      const sv = hips(A.current, a, l, () => { if (current) setLayerStatus('error'); });
      pendingLayer.current = sv;
      cube.current = l.id === SPHEREX.id ? sv : null;
      a.setBaseImageLayer(sv);
    } catch { setLayerStatus('error'); }
    return () => { current = false; };
  }, [layer, state]);
  useEffect(() => {
    bandIndex.current = slice;
    cube.current?.setFrequency({ value: SPHEREX_MAP_BANDS[slice].tileFrequencyHz, unit: 'Hz' });
  }, [slice]);
  useEffect(() => {
    if (!sweep || layer !== SPHEREX.id || layerStatus !== 'ready') return;
    const id = window.setInterval(() => setSlice(k => (k + 1) % SPHEREX_MAP_BANDS.length), 500);
    return () => window.clearInterval(id);
  }, [sweep, layer, layerStatus]);
  useEffect(() => {
    showRef.current = show;
    if (state !== 'ready') return;
    (Object.keys(show) as (keyof Toggles)[]).forEach(k => groups.current[k].forEach(o => { try { show[k] ? o.show() : o.hide(); } catch { /* ignore */ } }));
  }, [show, state]);

  // ---- the selected place: fly there and plant the big pin ----
  useEffect(() => {
    const a = al.current, Ali = A.current, cat = selCat.current, movingCat = ephemerisCat.current;
    if (!a || !Ali || !cat || !movingCat) return;
    cat.removeAll();
    movingCat.removeAll();
    if (!sel) return;
    const destination = sel.solarQuery ? movingCat : cat;
    destination.addSources([Ali.source(sel.ra, sel.dec, { name: sel.name })]);
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
    const k = known ?? PLACES.find(p => p.name.toLowerCase() === t.toLowerCase() || p.q?.toLowerCase() === t.toLowerCase());
    if (k && !k.q && k.ra != null && k.dec != null) {
      setSel({ ...k, ra: k.ra, dec: k.dec });
      return;
    }
    setBusy(true);
    try {
      const r = await resolveQuery(k?.q ?? t);
      setSel({
        name: k?.name ?? r.name ?? t, kind: k?.kind ?? r.kind ?? (r.moves ? 'Solar System body' : r.name ? 'Star or deep-sky object' : 'Coordinates'),
        blurb: k?.blurb, cat: k?.cat, ours: k?.ours, ra: r.ra, dec: r.dec, fov: k?.fov ?? (r.moves ? 3 : 1.5),
        solarQuery: r.moves ? (k?.q ?? t) : undefined, bodyId: r.body_id, positionUtc: r.position_utc, source: r.name ? r.source : undefined, epochNote: r.epoch_note,
      });
    } catch (x) { setSel(null); setErr((x as Error).message || `Couldn't find "${t}".`); }
    finally { setBusy(false); }
  }
  async function pick(p: Place) {
    setQ(p.name);
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
    if (sel.solarQuery) return copyLink(`${window.location.origin}/map?q=${encodeURIComponent(sel.solarQuery)}`);
    const url = `${window.location.origin}/map?ra=${sel.ra.toFixed(5)}&dec=${sel.dec.toFixed(5)}&fov=${(sel.fov ?? centre?.fov ?? 3).toFixed(2)}`;
    return copyLink(url);
  }
  const imagesFov = (s: Sel) => Math.min(20, Math.max(4, Math.round(((s.fov ?? centre?.fov ?? 0.2) * 60) / 3)));
  const objectImage = sel?.solarQuery && sel.bodyId ? SOLAR_IMAGES[sel.bodyId] : undefined;
  const hasCard = !!(sel && !sel.pin) || !!list || !!(scopes && sel?.pin);
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
    <div className={`gm${hasCard ? ' has-card' : ''}${centreChunk ? ' gm--chunks' : ''}${sel?.solarQuery ? ' gm--solar' : ''}`}>
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
            {inList(list).map(p => (
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
            <div className={`gm-card__pic${objectImage ? ' gm-card__pic--object' : ''}`}>
              {objectImage ? <img src={`/img/${objectImage.file}-archive.webp`} alt={`${sel.name} in an archival NASA image`} /> : catIcon(sel.cat)}
              <button type="button" className="gm-ic gm-card__close" aria-label="Close" onClick={() => setSel(null)}><IcX /></button>
            </div>
            <div className="gm-card__body">
              <h2 className="gm-card__title">{sel.name}</h2>
              <p className="gm-card__kind">{sel.kind}</p>
              {objectImage && <p className="gm-card__meta gm-card__image-credit">Archive image · {objectImage.caption}</p>}
              {sel.solarQuery && <div className="gm-card__ephemeris">
                <p>{fmtCoord(sel.ra, sel.dec)} <small>RA, Dec · Earth center (ICRF)</small></p>
                <p><small>JPL Horizons{sel.positionUtc && <> · <time dateTime={sel.positionUtc}>{ephemerisTime.format(new Date(sel.positionUtc))} UTC</time></>}</small></p>
                <p><small>The crosshair marks the calculated position over the survey image.</small></p>
              </div>}
              {sel.ours && <p className="gm-card__meta">PARALLAX result</p>}
            </div>
            <div className="gm-acts">
              {objectImage && <a className="gm-act gm-act--main" href={objectImage.source} target="_blank" rel="noreferrer"><i><IcImages /></i>NASA image</a>}
              {!sel.solarQuery && <button type="button" className="gm-act gm-act--main" onClick={() => navigate(openHere(sel.ra, sel.dec, imagesFov(sel)))}><i><IcImages /></i>Archive field</button>}
              <button type="button" className="gm-act" onClick={() => zoom(0.4)}><i><IcPlus /></i>Zoom in</button>
              <button type="button" className="gm-act" onClick={() => zoom(2.5)}><i><IcMinus /></i>Zoom out</button>
              <button type="button" className="gm-act" onClick={() => void share()}><i><IcShare /></i>Share</button>
            </div>
            <div className="gm-rows">
              {sel.blurb && <div className="gm-row"><IcInfo /><span>{sel.blurb}</span></div>}
              {!sel.solarQuery && <div className="gm-row"><IcPin /><span>{fmtCoord(sel.ra, sel.dec)}<small>Right ascension, declination</small></span></div>}
              {sel.solarQuery && !objectImage && <div className="gm-row"><IcImages /><span>No verified object image in PARALLAX.</span></div>}
              {!sel.solarQuery && sel.source && <div className="gm-row"><IcInfo /><span>Position from {sel.source}{sel.epochNote && <small>{sel.epochNote}</small>}</span></div>}
              {!sel.solarQuery && <div className="gm-row gm-row--os"><IcLayers /><OtherScopes ra={sel.ra} dec={sel.dec} /></div>}
            </div>
          </div>
        </section>
      )}

      <div className="gm-layers">
        <button type="button" className="gm-tile" aria-expanded={layersOpen} aria-label="Layers: choose which telescope's sky to show" onClick={() => { setActiveChunk(null); setLayersOpen(v => !v); }}>
          {activeLayer.thumb && <img src={activeLayer.thumb} alt="" />}
          <span className="gm-tile__lb"><IcLayers />Layers</span>
        </button>
        {layersOpen && (
          <div className="gm-pop" role="dialog" aria-label="Layers">
            <div role="radiogroup" aria-label="Telescope">
              {LIGHTS.map(g => (
                <div key={g.light} className="gm-pop__group">
                  <div className="gm-pop__gh"><b>{g.light}</b><span>{g.say}</span></div>
                  <div className="gm-pop__tiles">
                    {LAYERS.filter(l => l.light === g.light).map(l => (
                      <button key={l.id} type="button" role="radio" aria-checked={layer === l.id} className={`gm-ltile${layer === l.id ? ' is-on' : ''}`}
                        onClick={() => { setSweep(false); setLayer(l.id); }} title={`${l.label} (${l.who}), ${l.year}: ${COVER[l.cover]}`}>
                        <i>{l.thumb ? <img src={l.thumb} alt="" loading="lazy" /> : <span className="gm-ltile__glyph" aria-hidden="true">{g.glyph}</span>}</i>{l.label}<br />{l.year}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            {layerStatus === 'error' && <p className="gm-layer-note" role="alert">The survey could not load. Choose another layer or switch back to retry.</p>}
            {layerStatus !== 'error' && activeLayer.cover !== 'all' && (
              <div className="gm-pop__note">
                <span>{activeLayer.label} covers {COVER[activeLayer.cover]}.</span>
                {activeLayer.eg && <button type="button" className="gm-pop__play" onClick={() => {
                  const a = al.current, example = activeLayer.eg;
                  if (a && example) { a.gotoRaDec(example.ra, example.dec); a.setFoV(example.fov); }
                }}>Show me {activeLayer.eg.name}</button>}
              </div>
            )}
            {layer === SPHEREX.id && (
              <div className="gm-pop__sec">
                <div className="gm-pop__hd"><span>SPHEREx wavelength</span><b>{SPHEREX_MAP_BANDS[slice].wavelength.toFixed(3)} µm</b></div>
                <input type="range" aria-label="SPHEREx wavelength" aria-valuetext={`${SPHEREX_MAP_BANDS[slice].wavelength.toFixed(3)} micrometers`} min={0} max={SPHEREX_MAP_BANDS.length - 1} value={slice} onChange={e => { setSweep(false); setSlice(Number(e.target.value)); }} />
                <button type="button" className="gm-pop__play" onClick={() => setSweep(v => !v)}>{sweep ? 'Pause bands' : `Play ${SPHEREX_MAP_BANDS.length} bands`}</button>
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
          <button type="button" className="gm-btn" onClick={() => navigate(openHere(sel.ra, sel.dec, 10))}>Open archive field</button>
          <button type="button" className="gm-btn gm-btn--line" onClick={() => setScopes({ ra: sel.ra, dec: sel.dec, name: 'Dropped pin' })}>Other telescopes</button>
          <button type="button" className="gm-ic" aria-label="Remove pin" onClick={() => setSel(null)}><IcX /></button>
        </div>
      )}
      {scopes && sel?.pin && Math.abs(scopes.ra - sel.ra) < 1e-9 && (
        <section className="gm-card" aria-label="Other telescopes at the dropped pin">
          <div className="gm-list__hd"><h2>Other telescopes here</h2><button type="button" className="gm-ic" aria-label="Close" onClick={() => setScopes(null)}><IcX /></button></div>
          <div className="gm-card__scroll gm-card__pad"><p className="gm-card__kind">{fmtCoord(scopes.ra, scopes.dec)}</p><OtherScopes ra={scopes.ra} dec={scopes.dec} auto /></div>
        </section>
      )}
      {toast && <p className="gm-toast" role="status">{toast}</p>}

      <div className="gm-ctl">
        <button type="button" className="gm-ctl__one" aria-label="Sky overview" onClick={() => { setActiveChunk(null); al.current?.setFoV(180); }}><IcGlobe /></button>
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
        <span className="gm-status__coords">{centre ? `Center RA/Dec · ${fmtCoord(centre.ra, centre.dec)} · ${fmtFov(centre.fov)}` : ''}</span>
        <span className="gm-status__credits">
          <span>Survey: {activeLayer.label}{layer === SPHEREX.id ? ` DR1 · ${SPHEREX_MAP_BANDS[slice].wavelength.toFixed(3)} µm` : ''}{layerStatus === 'loading' ? ' · loading' : layerStatus === 'error' ? ' · unavailable' : ''} · {activeLayer.host} · <a href="https://aladin.cds.unistra.fr/AladinLite/">Aladin Lite</a> ·</span>
          <Link href="/about">Sources</Link>
        </span>
      </div>
      {activeChunk && <ChunkReview key={activeChunk} id={activeChunk} team={chunkTeam}
        onClose={() => { setActiveChunk(null); chunkOpener.current?.focus(); }}
        onCopy={() => void copyLink(`${window.location.origin}/map?chunk=${activeChunk}`)} />}
    </div>
  );
}
