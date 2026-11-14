// Formatting helpers. Missing values render as "unavailable" — never as zero.
export const NA = 'unavailable';

export function num(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return NA;
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function pm(v: number | null | undefined, err: number | null | undefined, digits = 0, unit = ''): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return NA;
  const e = err !== null && err !== undefined && Number.isFinite(err) ? ` ± ${num(err, digits)}` : '';
  return `${num(v, digits)}${e}${unit ? ' ' + unit : ''}`;
}

export function sig(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return NA;
  if (v >= 99) return '> 99σ';
  return `${num(v, digits)}σ`;
}

const dateFmt = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', year: 'numeric', month: 'short', day: 'numeric' });
const dateTimeFmt = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
const monthFmt = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', year: 'numeric', month: 'short' });

export function date(iso: string | null | undefined): string {
  if (!iso) return NA;
  const d = new Date(iso);
  return Number.isFinite(d.getTime()) ? dateFmt.format(d) : NA;
}
export function dateTime(iso: string | null | undefined): string {
  if (!iso) return NA;
  const d = new Date(iso);
  return Number.isFinite(d.getTime()) ? dateTimeFmt.format(d) + ' UTC' : NA;
}
export function month(iso: string | null | undefined): string {
  if (!iso) return NA;
  const d = new Date(iso);
  return Number.isFinite(d.getTime()) ? monthFmt.format(d) : NA;
}
export function mjdIso(mjd: number): string {
  return new Date((mjd - 40587) * 86400000).toISOString();
}
export function um(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return NA;
  return `${v.toFixed(digits)} µm`;
}
export function ujy(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return NA;
  const a = Math.abs(v);
  if (a >= 1e6) return `${(v / 1e6).toFixed(2)} Jy`;
  if (a >= 1e3) return `${(v / 1e3).toFixed(2)} mJy`;
  return `${v.toFixed(1)} µJy`;
}
export function humanize(s: string): string {
  return s.replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase());
}
export function shortHash(h: string | null | undefined, n = 12): string {
  return h ? h.slice(0, n) : NA;
}
