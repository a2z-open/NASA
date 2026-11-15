import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import './theme.css';
import { startReveal } from './reveal.ts';
import { useLocation, Link } from './router.tsx';
import { Home } from './pages/Home.tsx';
import { Explore } from './pages/Explore.tsx';
import { InvestigationPage } from './pages/InvestigationPage.tsx';
import { Evidence } from './pages/Evidence.tsx';
import { Proof } from './pages/Proof.tsx';
import { Hunt } from './pages/Hunt.tsx';
import { Deck } from './pages/Deck.tsx';
import { Targets } from './pages/Targets.tsx';
import { DataAbout } from './pages/DataAbout.tsx';
import { SkyMap } from './pages/SkyMap.tsx';
import { Check } from './pages/Check.tsx';
import { How } from './pages/How.tsx';
import { Page } from './components/Shell.tsx';
import { Component, useEffect, type ReactNode } from 'react';

class Boundary extends Component<{ children: ReactNode; resetKey: string }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidUpdate(prev: { resetKey: string }) { if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null }); }
  render() {
    if (this.state.error) {
      return <Page><h1>Something went wrong</h1><p className="notice notice--bad">{this.state.error.message}</p><p className="muted"><Link href="/">Go home</Link> or reload the page.</p></Page>;
    }
    return this.props.children;
  }
}

const TITLES: Record<string, string> = {
  '/': 'PARALLAX · Spot what moves in space',
  '/map': 'Sky map · PARALLAX',
  '/check': 'Check a candidate · PARALLAX',
  '/how': 'How we find them · PARALLAX',
  '/explore': 'Explore · PARALLAX',
  '/hunt': 'Planet X hunt · PARALLAX',
  '/deck': 'PARALLAX in seven slides',
  '/proof': 'Proof · PARALLAX',
  '/about': 'About · PARALLAX',
  '/targets': 'Targets · PARALLAX',
  '/investigation': 'Investigation · PARALLAX',
  '/evidence': 'Evidence · PARALLAX',
};

function App() {
  const { path: pathname, hash } = useLocation();
  const path = pathname.replace(/\/+$/, '') || '/';
  const detail = /^\/(investigation|evidence)\/([^/]+)$/.exec(path);
  useEffect(() => {
    const key = detail ? `/${detail[1]}` : path;
    document.title = TITLES[key] ?? 'PARALLAX';
    if (!hash) return;
    const frame = requestAnimationFrame(() => document.getElementById(hash.slice(1))?.scrollIntoView());
    return () => cancelAnimationFrame(frame);
  }, [path, hash]);
  if (path === '/') return <Home />;
  if (path === '/explore') return <Explore />;
  if (path === '/map') return <SkyMap />;
  if (path === '/check') return <Check />;
  if (path === '/how') return <How />;
  if (detail) {
    try {
      const id = decodeURIComponent(detail[2]);
      return detail[1] === 'investigation' ? <InvestigationPage id={id} /> : <Evidence id={id} />;
    } catch (error) {
      if (!(error instanceof URIError)) throw error;
    }
  }
  if (path === '/hunt') return <Hunt />;
  if (path === '/deck') return <Deck />;
  if (path === '/proof' || path === '/lab' || path === '/method') return <Proof />;
  if (path === '/targets') return <Targets />;
  if (path === '/about' || path === '/data') return <DataAbout />;
  return <Page><h1>Not found</h1><p className="muted">That page does not exist. <Link href="/">Go home</Link>.</p></Page>;
}

function Root() {
  const { path, search } = useLocation();
  return <Boundary resetKey={path + search}><App /></Boundary>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><Root /></StrictMode>);

startReveal();
