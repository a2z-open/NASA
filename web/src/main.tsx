import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import { useLocation, Link } from './router.tsx';
import { Home } from './pages/Home.tsx';
import { Explore } from './pages/Explore.tsx';
import { InvestigationPage } from './pages/InvestigationPage.tsx';
import { Evidence } from './pages/Evidence.tsx';
import { Proof } from './pages/Proof.tsx';
import { Hunt } from './pages/Hunt.tsx';
import { Targets } from './pages/Targets.tsx';
import { DataAbout } from './pages/DataAbout.tsx';
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
  '/': 'PARALLAX · Find what moves in the infrared sky',
  '/explore': 'Explore · PARALLAX',
  '/hunt': 'Planet X hunt · PARALLAX',
  '/proof': 'Proof · PARALLAX',
  '/about': 'About · PARALLAX',
  '/targets': 'Targets · PARALLAX',
  '/investigation': 'Investigation · PARALLAX',
  '/evidence': 'Evidence · PARALLAX',
};

function App() {
  const { path } = useLocation();
  useEffect(() => {
    const key = Object.keys(TITLES).find(k => k !== '/' && path.startsWith(k)) ?? (path === '/' ? '/' : '');
    document.title = TITLES[key] ?? 'PARALLAX';
  }, [path]);
  if (path === '/' || path === '') return <Home />;
  if (path.startsWith('/explore')) return <Explore />;
  if (path.startsWith('/investigation/')) return <InvestigationPage id={decodeURIComponent(path.slice('/investigation/'.length))} />;
  if (path.startsWith('/evidence/')) return <Evidence id={decodeURIComponent(path.slice('/evidence/'.length))} />;
  if (path.startsWith('/hunt')) return <Hunt />;
  if (path.startsWith('/proof') || path.startsWith('/lab') || path.startsWith('/method')) return <Proof />;
  if (path.startsWith('/targets')) return <Targets />;
  if (path.startsWith('/about') || path.startsWith('/data')) return <DataAbout />;
  return <Page><h1>Not found</h1><p className="muted">That page does not exist. <Link href="/">Go home</Link>.</p></Page>;
}

function Root() {
  const { path, search } = useLocation();
  return <Boundary resetKey={path + search}><App /></Boundary>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><Root /></StrictMode>);
