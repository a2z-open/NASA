import type { ReactNode } from 'react';
import { Link, useLocation } from '../router.tsx';
import { Starfield } from './Starfield.tsx';

const NAV = [
  { href: '/map', label: 'Sky map' },
  { href: '/how', label: 'How' },
  { href: '/check', label: 'Check' },
  { href: '/hunt', label: 'Finds' },
  { href: '/proof', label: 'Proof' },
];

/** The mark: an orbit and one body displaced on it. One colour, so it works on any background. */
export function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <mask id="pm-cut"><rect width="32" height="32" fill="#fff" /><circle cx="23.8" cy="8.2" r="7.2" fill="#000" /></mask>
      </defs>
      <circle cx="16" cy="16" r="11" fill="none" stroke="currentColor" strokeWidth="2.8" mask="url(#pm-cut)" />
      <circle cx="23.8" cy="8.2" r="4.2" fill="currentColor" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <Link href="/" className="wordmark" aria-label="PARALLAX home">
      <Mark />
      <span>PARALLAX</span>
    </Link>
  );
}

export function Header({ children, overlay = false }: { children?: ReactNode; overlay?: boolean }) {
  const { path } = useLocation();
  return (
    <header className={`header${overlay ? ' header--overlay' : ''}`}>
      <div className="header__inner">
        <Wordmark />
        {children}
        <nav className="nav" aria-label="Main">
          {NAV.map(n => (
            <Link key={n.href} href={n.href} className={`nav__link${path.startsWith(n.href) ? ' is-active' : ''}`} aria-current={path.startsWith(n.href) ? 'page' : undefined}>{n.label}</Link>
          ))}
        </nav>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="foot4">
      <div className="foot4__in">
        <div>
          <Wordmark />
          <nav aria-label="Footer">
            <Link href="/">Play</Link>
            {NAV.map(n => <Link key={n.href} href={n.href}>{n.label}</Link>)}
            <Link href="/explore">Images</Link>
            <Link href="/about">Sources</Link>
          </nav>
        </div>
        <div>
          <p>Sky images: NASA SPHEREx, from the NASA/IPAC Infrared Science Archive (<a href="https://doi.org/10.26131/IRSA678">DR1</a> and QR3). Planet positions: NASA JPL Horizons. Star positions: ESA Gaia DR3. Photographs: NASA/JHUAPL/SwRI, NASA/JPL-Caltech.</p>
          <p>Made for the NASA Space Apps Challenge 2026, Seattle. Not affiliated with or endorsed by NASA.</p>
        </div>
      </div>
    </footer>
  );
}

/** The opening of every inner page: a short title, one sentence, and one real photograph in the round. */
export function PageHero({ title, lede, img, alt, caption, children }: { title: string; lede?: ReactNode; img: string; alt: string; caption?: string; children?: ReactNode }) {
  return (
    <header className="phero">
      <div className="phero__text">
        <h1 className="rv">{title}</h1>
        {lede && <p className="phero__lede rv" style={{ ['--d' as string]: '80ms' }}>{lede}</p>}
        {children}
      </div>
      <figure className="phero__fig rv" style={{ ['--d' as string]: '140ms' }}>
        <img src={img} alt={alt} decoding="async" />
        {caption && <figcaption>{caption}</figcaption>}
      </figure>
    </header>
  );
}

export function Page({ children, wide = false, stars = false }: { children: ReactNode; wide?: boolean; stars?: boolean }) {
  return (
    <>
      {stars && <Starfield />}
      <Header />
      <main id="main" className={`page${wide ? ' page--wide' : ''}`}>
        <div className="page__inner">{children}</div>
      </main>
      <Footer />
    </>
  );
}
