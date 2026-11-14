import type { ReactNode } from 'react';
import { Link, useLocation } from '../router.tsx';

const NAV = [
  { href: '/explore', label: 'Explore' },
  { href: '/targets', label: 'Targets' },
  { href: '/lab', label: 'Discovery Lab' },
  { href: '/method', label: 'Method' },
  { href: '/data', label: 'Data' },
];

export function Wordmark() {
  return (
    <Link href="/" className="wordmark" aria-label="PARALLAX home">
      <svg width="22" height="22" viewBox="0 0 26 26" fill="none" aria-hidden="true">
        <circle cx="7" cy="16" r="2.2" fill="currentColor" opacity="0.45" />
        <circle cx="19" cy="9" r="2.6" fill="currentColor" />
        <path d="M7 16 19 9" stroke="currentColor" strokeWidth="1.2" strokeDasharray="2 2" />
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
    <footer className="footer">
      <div className="page__inner footer__inner">
        <p>Observations: NASA SPHEREx via the NASA/IPAC Infrared Science Archive (IRSA). DR1 spectral images <a href="https://doi.org/10.26131/IRSA678">doi:10.26131/IRSA678</a>; QR3 spectral images.</p>
        <p>PARALLAX is an independent NASA Space Apps Challenge 2026 project. It is not affiliated with or endorsed by NASA. <Link href="/data">Data, citations &amp; AI disclosure</Link>.</p>
      </div>
    </footer>
  );
}

export function Page({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return (
    <>
      <Header />
      <main id="main" className={`page${wide ? ' page--wide' : ''}`}>
        <div className="page__inner">{children}</div>
      </main>
      <Footer />
    </>
  );
}
