"""A local, append-only lock record that does not need Git.

Each entry stores the SHA-256 of one or more files, the time, and the hash of the previous entry, so entries
cannot be reordered or silently edited without breaking the chain.  A blind result is written here BEFORE
the truth is opened; the scoring step refuses to run if the locked file has changed.

Limits, stated plainly: the clock is this computer's clock and the file lives on this computer, so the record
is self-reported.  It proves order and integrity to anyone who trusts the machine; publishing the last entry's
hash somewhere public (a commit, a message) would give it an outside time-stamp.

    python -m validation.ledger verify
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / 'validation' / 'ledger.jsonl'


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _entry_hash(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != 'hash'}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def entries() -> list[dict]:
    if not LEDGER.is_file():
        return []
    return [json.loads(line) for line in LEDGER.read_text().splitlines() if line.strip()]


def append(label: str, paths: list[Path], note: str = '') -> dict:
    prev = entries()
    entry = {'seq': len(prev) + 1, 'time_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'label': label,
             'files': {str(Path(p).resolve().relative_to(ROOT)): sha256_file(p) for p in paths}, 'note': note,
             'prev': prev[-1]['hash'] if prev else None}
    entry['hash'] = _entry_hash(entry)
    with LEDGER.open('a') as f:
        f.write(json.dumps(entry, sort_keys=True) + '\n')
    return entry


def find(label: str) -> dict | None:
    return next((e for e in reversed(entries()) if e['label'] == label), None)


def locked(label: str, path: Path) -> dict:
    """Return the ledger entry for `label` if `path` still has the locked hash; raise otherwise."""
    e = find(label)
    rel = str(Path(path).resolve().relative_to(ROOT))
    if e is None or rel not in e['files']:
        raise RuntimeError(f'{rel} was never locked under "{label}"')
    if e['files'][rel] != sha256_file(path):
        raise RuntimeError(f'{rel} has changed since it was locked under "{label}"')
    return e


def verify() -> tuple[bool, list[str]]:
    problems, prev = [], None
    for e in entries():
        if e.get('prev') != prev:
            problems.append(f'entry {e["seq"]}: chain broken')
        if _entry_hash(e) != e.get('hash'):
            problems.append(f'entry {e["seq"]}: entry was edited')
        prev = e.get('hash')
    latest = {}
    for e in entries():
        for rel, digest in e['files'].items():
            latest[rel] = (e['seq'], digest)
    for rel, (seq, digest) in latest.items():
        p = ROOT / rel
        if not p.is_file():
            problems.append(f'{rel}: missing (locked in entry {seq})')
        elif sha256_file(p) != digest:
            problems.append(f'{rel}: differs from its lock in entry {seq}')
    return not problems, problems


if __name__ == '__main__':
    ok, problems = verify()
    es = entries()
    print(f'{len(es)} entries; chain and files {"OK" if ok else "NOT OK"}')
    for e in es:
        print(f'  {e["seq"]:3d}  {e["time_utc"]}  {e["label"]}  {e["hash"][:12]}')
    for p in problems:
        print('  PROBLEM:', p)
    sys.exit(0 if ok else 1)
