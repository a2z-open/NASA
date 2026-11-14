import type { ReactNode } from 'react';
import { Link, useLocation } from '../router.tsx';
import { Starfield } from './Starfield.tsx';

const NAV = [
  { href: '/explore', label: 'Explore' },
  { href: '/hunt', label: 'Planet X hunt' },
  { href: '/proof', label: 'Proof' },
  { href: '/about', label: 'About' },
];

/** The mark: one dot seen twice. A ring where it was, a disc where it is now. */
export function Wordmark() {
  return (
    <Link href="/" className="wordmark" aria-label="PARALLAX home">
      <svg width="30" height="20" viewBox="0 0 30 20" aria-hidden="true">
        <circle cx="10" cy="10" r="8.6" fill="none" stroke="currentColor" strokeWidth="1.8" opacity="0.55" />
        <circle cx="20" cy="10" r="9.5" fill="var(--accent)" />
      </svg>
      <span>PARALLAX</span>
    </Link>
  );
}

export function Header({ children }: { children?: ReactNode }) {
  const { path } = useLocation();
  return (
    <header className="header">
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
    <footer className="foot">
      <div className="foot__inner">
        <p className="foot__mark" aria-hidden="true">PARALLAX</p>
        <div className="foot__cols">
          <nav className="foot__nav" aria-label="Footer">
            {NAV.map(n => <Link key={n.href} href={n.href}>{n.label}</Link>)}
            <Link href="/deck">Seven slides</Link>
          </nav>
          <p>Sky images: NASA SPHEREx, from the NASA/IPAC Infrared Science Archive (<a href="https://doi.org/10.26131/IRSA678">DR1</a> and QR3). Star positions: ESA Gaia DR3.</p>
          <p>Photographs: Pluto, NASA/JHUAPL/SwRI. Neptune, NASA/JPL. The WISE sky, NASA/JPL-Caltech/UCLA. SPHEREx views, NASA/JPL-Caltech; in assembly, NASA/JPL-Caltech/BAE Systems. WISE 0855 (artist's impression), NASA/JPL-Caltech/Penn State.</p>
          <p>A NASA Space Apps Challenge 2026 project. Not affiliated with or endorsed by NASA. <Link href="/about">Sources and AI use</Link></p>
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

export function Page({ children, wide = false, stars = true }: { children: ReactNode; wide?: boolean; stars?: boolean }) {
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
