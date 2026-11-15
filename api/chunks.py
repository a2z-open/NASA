"""Named sky chunk assignments shared by everyone on this PARALLAX server."""

from collections import defaultdict
from contextlib import closing
import os
from pathlib import Path
import re
import sqlite3
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from pipeline.spherex import CACHE

router = APIRouter(prefix='/api/chunks')
COOKIE = 'parallax_chunk_session'
CHUNK_ID = re.compile(r'[A-L]-(?:0[1-9]|1[0-9]|2[0-4])')
TRANSITIONS = {
    'start': {'claimed': 'in_progress'},
    'review': {'in_progress': 'reviewed'},
    'reopen': {'reviewed': 'in_progress'},
    'release': {'claimed': None, 'in_progress': None},
}


class ChunkUpdate(BaseModel):
    action: Literal['claim', 'join', 'leave', 'start', 'review', 'reopen', 'release']
    name: str = Field(default='', max_length=32)


def connect():
    path = Path(os.environ.get('PARALLAX_CHUNKS_DB', CACHE / 'chunks.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    try:
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('''CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS chunk_teammates (
            chunk_id TEXT NOT NULL REFERENCES chunks(id), owner TEXT NOT NULL, name TEXT NOT NULL,
            PRIMARY KEY (chunk_id, owner)
        )''')
    except sqlite3.Error:
        db.close()
        raise
    return db


def session(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    owner = request.cookies.get(COOKIE, '')
    if not re.fullmatch(r'[0-9a-f]{32}', owner):
        owner = uuid4().hex
        response.set_cookie(COOKIE, owner, max_age=365 * 24 * 60 * 60, httponly=True,
                            samesite='strict', secure=request.url.scheme == 'https', path='/api/chunks')
    return owner


def view(row, teammates, viewer):
    owner, name, status = row
    return {'name': name, 'status': status, 'mine': owner == viewer,
            'teammates': [{'name': person, 'mine': member == viewer} for member, person in teammates]}


@router.get('')
def list_chunks(request: Request, response: Response):
    owner = session(request, response)
    with closing(connect()) as db, db:
        db.execute('BEGIN')
        teammates = defaultdict(list)
        for chunk_id, member, name in db.execute('SELECT chunk_id, owner, name FROM chunk_teammates ORDER BY rowid'):
            teammates[chunk_id].append((member, name))
        return {chunk_id: view((lead, name, status), teammates[chunk_id], owner)
                for chunk_id, lead, name, status in db.execute('SELECT id, owner, name, status FROM chunks')}


@router.post('/{chunk_id}')
def update_chunk(chunk_id: str, update: ChunkUpdate, request: Request, response: Response):
    if not CHUNK_ID.fullmatch(chunk_id):
        raise HTTPException(404, 'Unknown sky chunk.')
    owner = session(request, response)
    action = update.action
    if action in ('claim', 'join'):
        name = ' '.join(update.name.split())
        if not name or not name.isprintable():
            raise HTTPException(422, 'Enter a display name to work on this chunk.')

    with closing(connect()) as db, db:
        # Take the write lock before reading so concurrent changes cannot overwrite each other.
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT owner, name, status FROM chunks WHERE id = ?', (chunk_id,)).fetchone()
        if action == 'claim':
            if row:
                raise HTTPException(409, 'This chunk is already claimed. You can join the team.')
            db.execute('INSERT INTO chunks (id, owner, name, status) VALUES (?, ?, ?, ?)',
                       (chunk_id, owner, name, 'claimed'))
            return view((owner, name, 'claimed'), [], owner)
        if not row:
            raise HTTPException(409 if action == 'join' else 403, 'Claim this chunk before working on it.')

        lead, lead_name, status = row
        teammates = dict(db.execute('SELECT owner, name FROM chunk_teammates WHERE chunk_id = ? ORDER BY rowid', (chunk_id,)))
        if action == 'join':
            if owner == lead or owner in teammates:
                return view(row, teammates.items(), owner)
            if status == 'reviewed':
                raise HTTPException(409, 'A teammate needs to reopen this chunk before others can join.')
            db.execute('INSERT INTO chunk_teammates (chunk_id, owner, name) VALUES (?, ?, ?)', (chunk_id, owner, name))
            teammates[owner] = name
        elif action == 'leave':
            if owner not in teammates:
                raise HTTPException(403, 'Join this chunk before leaving it.')
            db.execute('DELETE FROM chunk_teammates WHERE chunk_id = ? AND owner = ?', (chunk_id, owner))
            del teammates[owner]
        else:
            if owner != lead and (action == 'release' or owner not in teammates):
                raise HTTPException(403, 'Only the chunk team can change its status. Only the lead can release it.')
            if status not in TRANSITIONS[action]:
                raise HTTPException(409, 'That action is unavailable for the current status.')
            if action == 'release':
                if teammates:
                    raise HTTPException(409, 'This chunk still has teammates.')
                db.execute('DELETE FROM chunks WHERE id = ?', (chunk_id,))
                return None
            status = TRANSITIONS[action][status]
            db.execute('UPDATE chunks SET status = ? WHERE id = ?', (status, chunk_id))
        return view((lead, lead_name, status), teammates.items(), owner)
