import { useState, type FormEvent } from 'react';
import { api } from '../api.ts';
import { parseCoordinateString } from '../lib/astro.ts';
import { navigate } from '../router.tsx';

interface Props {
  label: string;
  placeholder?: string;
  large?: boolean;
  fov?: number;
  initial?: string;
  onResolved?: (r: { ra: number; dec: number; target?: string; name?: string }) => void;
}

export async function resolveQuery(q: string): Promise<{ ra: number; dec: number; target?: string; name?: string }> {
  const coords = parseCoordinateString(q);
  if (coords) return coords;
  const r = await api.resolve(q);
  return { ra: r.ra, dec: r.dec, target: r.target, name: r.name };
}

export function SearchBox({ label, placeholder, large, fov, initial = '', onResolved }: Props) {
  const [q, setQ] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const text = q.trim();
    if (!text) { setError('Type a name or coordinates first.'); return; }
    setBusy(true);
    setError(null);
    try {
      const r = await resolveQuery(text);
      if (onResolved) onResolved(r);
      else if (r.target) navigate(`/explore?target=${r.target}`);
      else navigate(`/explore?ra=${r.ra.toFixed(6)}&dec=${r.dec.toFixed(6)}&fov=${fov ?? 6}`);
    } catch (err) {
      setError((err as Error).message || 'That name was not found. Try coordinates instead.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={`search${large ? ' search--large' : ''}`} onSubmit={submit} role="search" noValidate>
      <label className="visually-hidden" htmlFor={large ? 'search-hero' : 'search-bar'}>Object name or coordinates</label>
      <input
        id={large ? 'search-hero' : 'search-bar'}
        value={q}
        onChange={e => setQ(e.target.value)}
        placeholder={placeholder ?? 'Name or RA Dec'}
        autoComplete="off"
        spellCheck={false}
        aria-invalid={!!error}
        aria-describedby={error ? 'search-error' : undefined}
      />
      <button className="button button--primary" type="submit" disabled={busy}>{busy ? 'Looking…' : label}</button>
      {error && <p id="search-error" className="search__error" role="alert">{error}</p>}
      {large && !error && <p className="search__hint">Any star name works, or RA and Dec in degrees or hours.</p>}
    </form>
  );
}
