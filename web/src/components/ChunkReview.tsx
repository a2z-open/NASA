import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { chunkApi, type ChunkAction, type ChunkAssignment } from '../api.ts';

export const CHUNK_STATUS_LABEL = {
  unclaimed: 'Unclaimed',
  claimed: 'Claimed',
  in_progress: 'In progress',
  reviewed: 'Reviewed',
};

export function useChunkAssignments() {
  const [assignments, setAssignments] = useState<Record<string, ChunkAssignment> | null>(null);
  const [loadError, setLoadError] = useState('');
  const revision = useRef(0);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const current = ++revision.current;
    try {
      const data = await chunkApi.list(signal);
      if (current === revision.current && !signal?.aborted) {
        setAssignments(data);
        setLoadError('');
      }
    } catch {
      if (current === revision.current && !signal?.aborted) setLoadError('Couldn’t refresh chunk assignments.');
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    const timer = window.setInterval(() => {
      if (!document.hidden) void refresh(controller.signal);
    }, 5000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [refresh]);

  async function update(id: string, action: ChunkAction, name?: string) {
    try {
      const assignment = await chunkApi.update(id, action, name);
      revision.current++;
      setAssignments(current => {
        const next = { ...current };
        if (assignment) next[id] = assignment;
        else delete next[id];
        return next;
      });
    } finally {
      void refresh();
    }
  }

  return { assignments, loadError, refresh, update };
}

const OWNER_ACTION = {
  claimed: { action: 'start', label: 'Start work' },
  in_progress: { action: 'review', label: 'Mark reviewed' },
  reviewed: { action: 'reopen', label: 'Reopen' },
} as const;

interface Props {
  id: string;
  team: ReturnType<typeof useChunkAssignments>;
  onClose: () => void;
  onCopy: () => void;
}

export function ChunkReview({ id, team, onClose, onCopy }: Props) {
  const { assignments, loadError, refresh, update } = team;
  const assignment = assignments?.[id];
  const status = assignment?.status ?? 'unclaimed';
  const joined = assignment?.teammates.some(person => person.mine);
  const next = assignment && (assignment.mine || joined) ? OWNER_ACTION[assignment.status] : null;
  const canJoin = assignment && !assignment.mine && !joined && status !== 'reviewed';
  const canRelease = assignment?.mine && status !== 'reviewed' && assignment.teammates.length === 0;
  const [name, setName] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, []);

  async function save(action: ChunkAction, displayName?: string) {
    setPending(true);
    setError('');
    try {
      await update(id, action, displayName);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Couldn’t save the chunk. Try again.');
    } finally {
      setPending(false);
    }
  }

  function claim(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (name.trim()) void save(canJoin ? 'join' : 'claim', name.trim());
  }

  return (
    <section className="gm-chunk-panel" id="gm-chunk-review" aria-labelledby="gm-chunk-title"
      onKeyDown={event => { if (event.key === 'Escape') onClose(); }}>
      <header className="gm-chunk-panel__head">
        <h2 ref={heading} tabIndex={-1} id="gm-chunk-title">Chunk {id}</h2>
        <button type="button" className="gm-ic" aria-label="Close chunk panel" onClick={onClose}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
        </button>
      </header>
      {assignments && (
        <p className="gm-chunk-panel__status" role="status">
          <i className="gm-chunk-dot" data-status={status} />
          <strong>{CHUNK_STATUS_LABEL[status]}</strong>
        </p>
      )}
      {!assignments && !loadError && <p role="status">Loading assignments…</p>}
      {loadError && <p className="gm-chunk-panel__error" role="alert">
        {loadError} <button type="button" className="gm-chunk-text" onClick={() => void refresh()}>Retry</button>
      </p>}
      {assignment && (
        <ul className="gm-chunk-team" aria-label="Chunk team">
          {[assignment, ...assignment.teammates].map((person, index) => (
            <li key={index}><span>{person.name}{person.mine ? ' (you)' : ''}</span><small>{index === 0 ? 'Lead' : 'Teammate'}</small></li>
          ))}
        </ul>
      )}
      {assignments && (!assignment || canJoin) && (
        <form className="gm-chunk-panel__form" onSubmit={claim}>
          <label htmlFor="gm-chunk-name">Display name</label>
          <input id="gm-chunk-name" value={name} onChange={event => setName(event.target.value)} required maxLength={32}
            autoComplete="nickname" aria-describedby="gm-chunk-name-help" disabled={pending} />
          <small id="gm-chunk-name-help">Shown to everyone using this map.</small>
          <button type="submit" className="gm-btn" disabled={pending || !name.trim()}>{canJoin ? 'Join chunk' : 'Claim chunk'}</button>
        </form>
      )}
      {next && <div className="gm-chunk-panel__buttons">
        <button type="button" className="gm-btn" disabled={pending} onClick={() => void save(next.action)}>{next.label}</button>
        {canRelease && <button type="button" className="gm-chunk-text" disabled={pending}
          onClick={() => void save('release')}>Release chunk</button>}
        {joined && <button type="button" className="gm-chunk-text" disabled={pending}
          onClick={() => void save('leave')}>Leave chunk</button>}
      </div>}
      {error && <p className="gm-chunk-panel__error" role="alert">{error}</p>}
      <button type="button" className="gm-chunk-text" onClick={onCopy}>Copy chunk link</button>
    </section>
  );
}
