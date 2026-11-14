import type { DataState } from '../api.ts';

const LABELS: Record<DataState, string> = {
  cached: 'Cached NASA observations',
  live: 'Live NASA archive data',
  ready: 'Live NASA archive data',
  processing: 'Processing',
  no_coverage: 'No SPHEREx coverage found',
  insufficient: 'Insufficient observations',
  archive_unavailable: 'Archive temporarily unavailable',
  failed: 'Processing failed',
};

export function DataStatePill({ state, progress }: { state: DataState | 'idle'; progress?: { stage: string; done: number; total: number } | null }) {
  if (state === 'idle') return <span className="pill pill--idle">No field selected</span>;
  const tone = state === 'cached' || state === 'live' || state === 'ready' ? 'ok' : state === 'processing' ? 'busy' : state === 'insufficient' || state === 'no_coverage' ? 'warn' : 'bad';
  return (
    <span className={`pill pill--${tone}`} role="status">
      <span className="pill__dot" aria-hidden="true" />
      {LABELS[state] ?? state}
      {state === 'processing' && progress && progress.total > 0 && <span className="mono"> · {progress.stage.replace(/_/g, ' ')} {progress.done}/{progress.total}</span>}
    </span>
  );
}
