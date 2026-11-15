import assert from 'node:assert/strict';
import test from 'node:test';
import { chunkAt, chunkFromId, CHUNKS, DEC_EDGES } from '../src/lib/skyChunks.ts';

test('every sky chunk has a unique searchable ID and its centre maps back to it', () => {
  assert.equal(CHUNKS.length, 288);
  assert.equal(new Set(CHUNKS.map(c => c.id)).size, 288);
  for (const c of CHUNKS) {
    assert.equal(chunkAt(c.ra, c.dec).id, c.id);
    assert.equal(chunkFromId(` chunk ${c.id.toLowerCase()} `)?.id, c.id);
  }
});

test('seam, equator and poles map to valid stable IDs', () => {
  assert.equal(chunkAt(0, 0).id, 'G-01');
  assert.equal(chunkAt(360, 0).id, 'G-01');
  assert.equal(chunkAt(-0.001, 0).id, 'G-24');
  assert.equal(chunkAt(0, -90).id, 'A-01');
  assert.equal(chunkAt(359.999, 90).id, 'L-24');
  for (const id of ['A-00', 'A-25', 'M-01', 'M31', 'C14']) assert.equal(chunkFromId(id), undefined);
});

test('declination bands contain equal spherical area per longitude column', () => {
  const sin = (degrees) => Math.sin(degrees * Math.PI / 180);
  assert.equal(DEC_EDGES[0], -90);
  assert.equal(DEC_EDGES.at(-1), 90);
  for (let i = 1; i < DEC_EDGES.length; i++) {
    assert.ok(Math.abs(sin(DEC_EDGES[i]) - sin(DEC_EDGES[i - 1]) - 1 / 6) < 1e-12);
    assert.equal(chunkAt(7.5, DEC_EDGES[i - 1]).id.charAt(0), 'ABCDEFGHIJKL'[i - 1]);
  }
});
