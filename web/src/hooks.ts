import { useEffect, useRef, useState } from 'react';
import { api, ApiError, type Field, type Investigation, type Target } from './api.ts';

export interface Loadable<T> { data: T | null; error: string | null; loading: boolean }

let targetsPromise: Promise<Target[]> | null = null;

export function fetchTargets(): Promise<Target[]> {
  if (!targetsPromise) {
    targetsPromise = api.targets().catch(err => { targetsPromise = null; throw err; });
  }
  return targetsPromise;
}

export function useTargets(): Loadable<Target[]> {
  const [state, setState] = useState<Loadable<Target[]>>({ data: null, error: null, loading: true });
  useEffect(() => {
    let alive = true;
    fetchTargets()
      .then(data => alive && setState({ data, error: null, loading: false }))
      .catch(err => alive && setState({ data: null, error: err.message, loading: false }));
    return () => { alive = false; };
  }, []);
  return state;
}

const fieldCache = new Map<string, Field>();

/** Load a field; poll every 1.5 s while the backend is still processing it. */
export function useField(fieldId: string | null): Loadable<Field> & { refresh: () => void } {
  const [state, setState] = useState<Loadable<Field>>({ data: fieldId ? fieldCache.get(fieldId) ?? null : null, error: null, loading: !!fieldId });
  const [tick, setTick] = useState(0);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!fieldId) { setState({ data: null, error: null, loading: false }); return; }
    let alive = true;
    const cached = fieldCache.get(fieldId);
    if (cached && cached.data_state !== 'processing') {
      setState({ data: cached, error: null, loading: false });
      return;
    }
    async function poll() {
      try {
        const f = await api.field(fieldId!);
        if (!alive) return;
        setState({ data: f, error: null, loading: false });
        if (f.data_state === 'processing') timer.current = window.setTimeout(poll, 1500);
        else fieldCache.set(fieldId!, f);
      } catch (err) {
        if (!alive) return;
        const e = err as ApiError;
        setState({ data: null, error: e.message, loading: false });
      }
    }
    poll();
    return () => { alive = false; window.clearTimeout(timer.current); };
  }, [fieldId, tick]);
  return { ...state, refresh: () => { if (fieldId) fieldCache.delete(fieldId); setTick(t => t + 1); } };
}

const invCache = new Map<string, Investigation>();

export function useInvestigation(id: string | null): Loadable<Investigation> {
  const [state, setState] = useState<Loadable<Investigation>>({ data: id ? invCache.get(id) ?? null : null, error: null, loading: !!id });
  useEffect(() => {
    if (!id) { setState({ data: null, error: null, loading: false }); return; }
    let alive = true;
    let timer: number | undefined;
    const cached = invCache.get(id);
    if (cached && cached.status !== 'processing') { setState({ data: cached, error: null, loading: false }); return; }
    setState(s => ({ ...s, loading: true, error: null }));
    async function poll() {
      try {
        const inv = await api.investigation(id!);
        if (!alive) return;
        setState({ data: inv, error: null, loading: false });
        if (inv.status === 'processing') timer = window.setTimeout(poll, 1500);
        else invCache.set(id!, inv);
      } catch (err) {
        if (!alive) return;
        const e = err as ApiError;
        // A freshly queued investigation may 404 for a moment
        if (e.status === 404) { timer = window.setTimeout(poll, 1500); return; }
        setState({ data: null, error: e.message, loading: false });
      }
    }
    poll();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [id]);
  return state;
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): Loadable<T> {
  const [state, setState] = useState<Loadable<T>>({ data: null, error: null, loading: true });
  useEffect(() => {
    let alive = true;
    setState(s => ({ ...s, loading: true }));
    fn().then(data => alive && setState({ data, error: null, loading: false }))
      .catch(err => alive && setState({ data: null, error: err?.message ?? String(err), loading: false }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const mq = matchMedia('(prefers-reduced-motion: reduce)');
    const on = () => setReduced(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return reduced;
}
