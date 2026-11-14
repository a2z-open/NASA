import { Page } from '../components/Shell.tsx';
import { InvestigationView } from '../components/InvestigationView.tsx';
import { useInvestigation } from '../hooks.ts';
import { Link } from '../router.tsx';

export function InvestigationPage({ id }: { id: string }) {
  const inv = useInvestigation(id);
  return (
    <Page>
      <p className="crumbs"><Link href="/targets">Targets</Link> / Investigation</p>
      {inv.error && <p className="notice notice--bad">{inv.error}</p>}
      {inv.loading && !inv.data && <p className="muted">Loading investigation…</p>}
      {inv.data && (
        <>
          <div className="row-btns" style={{ marginBottom: 16 }}>
            <Link className="button button--primary button--small" href={`/explore?field=${encodeURIComponent(inv.data.field_id)}&inv=${encodeURIComponent(inv.data.id)}`}>Open in viewer</Link>
          </div>
          <InvestigationView inv={inv.data} />
        </>
      )}
    </Page>
  );
}
