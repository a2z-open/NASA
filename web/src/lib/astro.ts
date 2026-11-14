// Pure astronomy and image helpers. Erasable TypeScript only, so Node's test runner
// can import this file directly (node --test strips the types).

export interface SkyPoint { ra: number; dec: number }

const DEG = Math.PI / 180;

function cleanNumber(text: string): string {
  return text.trim().replace(/−/g, '-');
}

const DECIMAL = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;

function sexagesimalParts(text: string): number[] | null {
  const s = cleanNumber(text)
    .replace(/[hdms:°'"′″]/gi, ' ')
    .trim();
  if (!s) return null;
  const parts = s.split(/\s+/);
  if (parts.length < 2 || parts.length > 3) return null;
  if (!parts.every((p, i) => (i === 0 ? /^[+-]?\d+(?:\.\d+)?$/ : /^\d+(?:\.\d+)?$/).test(p))) return null;
  return parts.map(Number);
}

/** Right Ascension: decimal degrees, or sexagesimal hours ("08h55m10.8s", "08 55 10.8", "08:55:10.8"). */
export function parseRA(text: string): number {
  const s = cleanNumber(text);
  if (!s) throw new Error('Enter a right ascension.');
  let deg: number;
  if (DECIMAL.test(s)) {
    deg = Number(s);
  } else {
    const p = sexagesimalParts(s);
    if (!p || p[0] < 0) throw new Error(`Could not read right ascension “${text.trim()}”.`);
    const [h, m, sec = 0] = p;
    if (h >= 24 || m >= 60 || sec >= 60) throw new Error('Right ascension must be below 24h with minutes and seconds below 60.');
    deg = (h + m / 60 + sec / 3600) * 15;
  }
  if (!Number.isFinite(deg) || deg < 0 || deg > 360) throw new Error('Right ascension must be between 0° and 360° (0h–24h).');
  return deg === 360 ? 0 : deg;
}

/** Declination: decimal degrees, or sexagesimal degrees ("-07d14m42.5s", "-07 14 42.5"). */
export function parseDec(text: string): number {
  const s = cleanNumber(text);
  if (!s) throw new Error('Enter a declination.');
  let deg: number;
  if (DECIMAL.test(s)) {
    deg = Number(s);
  } else {
    const p = sexagesimalParts(s);
    if (!p) throw new Error(`Could not read declination “${text.trim()}”.`);
    const negative = s.startsWith('-');
    const [d, m, sec = 0] = p;
    if (m >= 60 || sec >= 60) throw new Error('Declination minutes and seconds must be below 60.');
    deg = Math.abs(d) + m / 60 + sec / 3600;
    if (negative) deg = -deg;
  }
  if (!Number.isFinite(deg) || deg < -90 || deg > 90) throw new Error('Declination must be between −90° and +90°.');
  return deg;
}

/** Parse "RA Dec" in one string. Returns null if it does not look like coordinates (e.g. an object name). */
export function parseCoordinateString(text: string): SkyPoint | null {
  const s = cleanNumber(text).replace(/,/g, ' ').replace(/\s+/g, ' ').trim();
  if (!s || /[a-z]/i.test(s.replace(/[hdms]/gi, ''))) return null;
  const tokens = s.split(' ');
  const tries: [string, string][] = [];
  if (tokens.length === 2) tries.push([tokens[0], tokens[1]]);
  if (tokens.length === 6) tries.push([tokens.slice(0, 3).join(' '), tokens.slice(3).join(' ')]);
  if (tokens.length === 4) tries.push([tokens.slice(0, 2).join(' '), tokens.slice(2).join(' ')]);
  for (const [a, b] of tries) {
    try { return { ra: parseRA(a), dec: parseDec(b) }; } catch { /* try next */ }
  }
  return null;
}

function pad(n: number, width: number, digits = 0): string {
  const fixed = n.toFixed(digits);
  const [int, frac] = fixed.split('.');
  return int.padStart(width, '0') + (frac !== undefined ? '.' + frac : '');
}

export function formatRA(deg: number, digits = 2): string {
  let total = ((deg % 360) + 360) % 360 / 15 * 3600;
  total = Math.round(total * 10 ** digits) / 10 ** digits;
  if (total >= 86400) total -= 86400;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total - h * 3600) / 60);
  const s = total - h * 3600 - m * 60;
  return `${pad(h, 2)}h${pad(m, 2)}m${pad(s, 2, digits)}s`;
}

export function formatDec(deg: number, digits = 1): string {
  const sign = deg < 0 ? '−' : '+';
  let total = Math.abs(deg) * 3600;
  total = Math.round(total * 10 ** digits) / 10 ** digits;
  const d = Math.floor(total / 3600);
  const m = Math.floor((total - d * 3600) / 60);
  const s = total - d * 3600 - m * 60;
  return `${sign}${pad(d, 2)}°${pad(m, 2)}′${pad(s, 2, digits)}″`;
}

// --------------------------------------------------------------------------
// Gnomonic (TAN) projection, arcsec tangent-plane offsets.
// --------------------------------------------------------------------------

export function toTangent(ra: number, dec: number, ra0: number, dec0: number): { xi: number; eta: number } {
  const a = ra * DEG, d = dec * DEG, a0 = ra0 * DEG, d0 = dec0 * DEG;
  const cosc = Math.sin(d0) * Math.sin(d) + Math.cos(d0) * Math.cos(d) * Math.cos(a - a0);
  const xi = Math.cos(d) * Math.sin(a - a0) / cosc;
  const eta = (Math.cos(d0) * Math.sin(d) - Math.sin(d0) * Math.cos(d) * Math.cos(a - a0)) / cosc;
  return { xi: xi / DEG * 3600, eta: eta / DEG * 3600 };
}

export function fromTangent(xi: number, eta: number, ra0: number, dec0: number): SkyPoint {
  const x = xi / 3600 * DEG, y = eta / 3600 * DEG, a0 = ra0 * DEG, d0 = dec0 * DEG;
  const rho = Math.hypot(x, y);
  if (rho === 0) return { ra: ra0, dec: dec0 };
  const c = Math.atan(rho);
  const dec = Math.asin(Math.cos(c) * Math.sin(d0) + y * Math.sin(c) * Math.cos(d0) / rho);
  const ra = a0 + Math.atan2(x * Math.sin(c), rho * Math.cos(d0) * Math.cos(c) - y * Math.sin(d0) * Math.sin(c));
  return { ra: ((ra / DEG) % 360 + 360) % 360, dec: dec / DEG };
}

export interface GridSpec { nx: number; ny: number; pixel_arcsec: number; ra0: number; dec0: number }

/** Sky -> display-grid pixel (col, row). North up, east left, row 0 = north. Pixel centres are integers. */
export function skyToGrid(grid: GridSpec, ra: number, dec: number): { col: number; row: number } {
  const { xi, eta } = toTangent(ra, dec, grid.ra0, grid.dec0);
  const cx = (grid.nx - 1) / 2, cy = (grid.ny - 1) / 2;
  return { col: cx - xi / grid.pixel_arcsec, row: cy - eta / grid.pixel_arcsec };
}

export function gridToSky(grid: GridSpec, col: number, row: number): SkyPoint {
  const cx = (grid.nx - 1) / 2, cy = (grid.ny - 1) / 2;
  return fromTangent((cx - col) * grid.pixel_arcsec, (cy - row) * grid.pixel_arcsec, grid.ra0, grid.dec0);
}

/** Linear proper motion (mas/yr, pmra = mu_alpha*cos(dec)) from epoch0 to epoch (MJD). Parallax ignored (display only). */
export function propagateLinear(ra: number, dec: number, pmra: number | null, pmdec: number | null, mjd0: number, mjd: number): SkyPoint {
  if (pmra == null || pmdec == null) return { ra, dec };
  const years = (mjd - mjd0) / 365.25;
  return fromTangent(pmra * years / 1000, pmdec * years / 1000, ra, dec);
}

export function angularSeparationArcsec(a: SkyPoint, b: SkyPoint): number {
  const d1 = a.dec * DEG, d2 = b.dec * DEG, dra = (b.ra - a.ra) * DEG;
  const s = Math.sin((d2 - d1) / 2) ** 2 + Math.cos(d1) * Math.cos(d2) * Math.sin(dra / 2) ** 2;
  return 2 * Math.asin(Math.min(1, Math.sqrt(s))) / DEG * 3600;
}

// --------------------------------------------------------------------------
// Binary frame decoding
// --------------------------------------------------------------------------

/** IEEE 754 half-precision -> number. */
export function halfToFloat(h: number): number {
  const sign = h & 0x8000 ? -1 : 1;
  const exp = (h >> 10) & 0x1f;
  const frac = h & 0x3ff;
  if (exp === 0) return sign * 2 ** -14 * (frac / 1024);
  if (exp === 31) return frac ? NaN : sign * Infinity;
  return sign * 2 ** (exp - 15) * (1 + frac / 1024);
}

let halfTable: Float32Array | null = null;

export function decodeFloat16(buffer: ArrayBuffer): Float32Array {
  if (!halfTable) {
    halfTable = new Float32Array(65536);
    for (let i = 0; i < 65536; i++) halfTable[i] = halfToFloat(i);
  }
  const src = new Uint16Array(buffer);
  const out = new Float32Array(src.length);
  for (let i = 0; i < src.length; i++) out[i] = halfTable[src[i]];
  return out;
}

export function decodeFrame(buffer: ArrayBuffer, dtype: string): Float32Array {
  if (dtype === 'float16') return decodeFloat16(buffer);
  return new Float32Array(buffer.slice(0));
}

// --------------------------------------------------------------------------
// Stretch
// --------------------------------------------------------------------------

export type StretchKind = 'linear' | 'asinh' | 'log';

/** Map a background-subtracted value to [0, 1] given black (lo) and white (hi) points. */
export function stretchValue(v: number, lo: number, hi: number, kind: StretchKind, soft = 10): number {
  if (!Number.isFinite(v)) return NaN;
  const t = Math.min(1, Math.max(0, (v - lo) / Math.max(hi - lo, 1e-12)));
  if (kind === 'linear') return t;
  if (kind === 'asinh') return Math.asinh(soft * t) / Math.asinh(soft);
  return Math.log1p(1000 * t) / Math.log1p(1000);
}

export function percentile(values: ArrayLike<number>, q: number): number {
  const finite: number[] = [];
  const step = Math.max(1, Math.floor(values.length / 20000));
  for (let i = 0; i < values.length; i += step) if (Number.isFinite(values[i])) finite.push(values[i]);
  if (!finite.length) return NaN;
  finite.sort((a, b) => a - b);
  const idx = Math.min(finite.length - 1, Math.max(0, Math.round((q / 100) * (finite.length - 1))));
  return finite[idx];
}

// --------------------------------------------------------------------------
// Wavelength -> display colour (restrained spectral accent, 0.75–5 µm, log scale)
// --------------------------------------------------------------------------

const RAMP: [number, [number, number, number]][] = [
  [0.75, [138, 164, 255]],
  [1.1, [104, 196, 255]],
  [1.6, [86, 214, 196]],
  [2.4, [150, 222, 120]],
  [3.3, [240, 208, 106]],
  [4.1, [255, 150, 92]],
  [5.0, [255, 96, 120]],
];

export function wavelengthColor(um: number | null | undefined, alpha = 1): string {
  if (um == null || !Number.isFinite(um)) return `rgba(140,150,160,${alpha})`;
  const x = Math.min(5, Math.max(0.75, um));
  for (let i = 1; i < RAMP.length; i++) {
    if (x <= RAMP[i][0]) {
      const [x0, c0] = RAMP[i - 1];
      const [x1, c1] = RAMP[i];
      const t = (Math.log(x) - Math.log(x0)) / (Math.log(x1) - Math.log(x0));
      const c = c0.map((v, k) => Math.round(v + (c1[k] - v) * t));
      return `rgba(${c[0]},${c[1]},${c[2]},${alpha})`;
    }
  }
  const c = RAMP[RAMP.length - 1][1];
  return `rgba(${c[0]},${c[1]},${c[2]},${alpha})`;
}

export function mjdToDate(mjd: number): Date {
  return new Date((mjd - 40587) * 86400000);
}

/** Are two frames comparable in wavelength? (|Δλ| below the larger bandwidth.) */
export function wavelengthMatched(a: { wavelength_um: number | null; bandwidth_um: number | null }, b: { wavelength_um: number | null; bandwidth_um: number | null }): boolean | null {
  if (a.wavelength_um == null || b.wavelength_um == null) return null;
  const bw = Math.max(a.bandwidth_um ?? 0, b.bandwidth_um ?? 0);
  if (!(bw > 0)) return null;
  return Math.abs(a.wavelength_um - b.wavelength_um) < bw;
}
