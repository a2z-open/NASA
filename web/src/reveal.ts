/** Scroll entrances. Any element with class "rv" rises into place once, the first time it
 *  enters the viewport. Without script, or with reduced motion, everything is simply visible. */
export function startReveal() {
  if (typeof window === 'undefined' || !('IntersectionObserver' in window)) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  document.documentElement.classList.add('rv-on');
  const io = new IntersectionObserver(entries => {
    for (const e of entries) if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); }
  }, { rootMargin: '0px 0px -6% 0px', threshold: 0.04 });
  // Blocks on the inner pages get the same entrance without each one having to ask for it.
  const AUTO = '.tile, .verdict, .section-head, .hrow, .test-h, .test-p, .exp, .rows > .row, .plain > *, .igrid, .idle__target';
  const scan = (n: ParentNode) => {
    n.querySelectorAll<HTMLElement>(AUTO).forEach(el => { if (!el.classList.contains('rv')) el.classList.add('rv'); });
    n.querySelectorAll<HTMLElement>('.rv:not(.is-in)').forEach(el => io.observe(el));
  };
  scan(document);
  // Safety net: if the observer stalls (a throttled or just-restored tab), anything already
  // on screen still appears.
  window.setInterval(() => {
    document.querySelectorAll<HTMLElement>('.rv:not(.is-in)').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.top < window.innerHeight * 0.96 && r.bottom > 0) { el.classList.add('is-in'); io.unobserve(el); }
    });
  }, 500);
  new MutationObserver(ms => {
    for (const m of ms) m.addedNodes.forEach(n => {
      if (!(n instanceof HTMLElement)) return;
      if (n.classList.contains('rv')) io.observe(n);
      scan(n);
    });
  }).observe(document.body, { childList: true, subtree: true });
}
