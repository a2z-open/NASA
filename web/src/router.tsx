import { useEffect, useState, type AnchorHTMLAttributes, type MouseEvent } from 'react';

const EVENT = 'parallax:navigate';

export function navigate(to: string, { replace = false } = {}) {
  if (replace) history.replaceState(null, '', to);
  else history.pushState(null, '', to);
  window.dispatchEvent(new Event(EVENT));
  if (!replace) window.scrollTo({ top: 0 });
}

/** Update the query string without creating history entries (keeps share links current). */
export function replaceQuery(params: Record<string, string | number | null | undefined>) {
  const url = new URL(window.location.href);
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '') url.searchParams.delete(k);
    else url.searchParams.set(k, String(v));
  }
  const next = url.pathname + (url.searchParams.toString() ? '?' + url.searchParams.toString() : '') + url.hash;
  if (next !== window.location.pathname + window.location.search + window.location.hash) history.replaceState(null, '', next);
}

export function useLocation() {
  const [loc, setLoc] = useState(() => ({ path: window.location.pathname, search: window.location.search }));
  useEffect(() => {
    const update = () => setLoc({ path: window.location.pathname, search: window.location.search });
    window.addEventListener('popstate', update);
    window.addEventListener(EVENT, update);
    return () => {
      window.removeEventListener('popstate', update);
      window.removeEventListener(EVENT, update);
    };
  }, []);
  return loc;
}

export function Link({ href, onClick, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) {
  function handle(e: MouseEvent<HTMLAnchorElement>) {
    onClick?.(e);
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    if (!href.startsWith('/') || rest.target === '_blank' || rest.download !== undefined) return;
    if (href.startsWith('/api/') || href.startsWith('/files/')) return;
    e.preventDefault();
    navigate(href);
  }
  return <a href={href} onClick={handle} {...rest} />;
}
