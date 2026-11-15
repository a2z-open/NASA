const ROWS = 'ABCDEFGHIJKL';
const COLUMNS = 24;
const RA_STEP = 360 / COLUMNS;
const toDegrees = (radians: number) => radians * 180 / Math.PI;

// Solid angle between two declinations is proportional to the difference of their sines.
export const DEC_EDGES = Array.from({ length: ROWS.length + 1 },
  (_, row) => toDegrees(Math.asin((row * 2 - ROWS.length) / ROWS.length)));

export const CHUNKS = Array.from({ length: ROWS.length * COLUMNS }, (_, index) => {
  const row = Math.floor(index / COLUMNS), column = index % COLUMNS;
  return {
    id: `${ROWS[row]}-${String(column + 1).padStart(2, '0')}`,
    ra: (column + 0.5) * RA_STEP,
    dec: (DEC_EDGES[row] + DEC_EDGES[row + 1]) / 2,
  };
});

const byId = new Map(CHUNKS.map(chunk => [chunk.id, chunk]));

export function chunkFromId(text: string) {
  return byId.get(text.trim().toUpperCase().replace(/^CHUNK\s+/, ''));
}

export function chunkAt(ra: number, dec: number) {
  const longitude = ra % 360;
  const column = Math.min(COLUMNS - 1, Math.floor((longitude < 0 ? longitude + 360 : longitude) / RA_STEP));
  const upperEdge = DEC_EDGES.findIndex(edge => edge > dec);
  const row = upperEdge === -1 ? ROWS.length - 1 : Math.max(0, upperEdge - 1);
  return CHUNKS[row * COLUMNS + column];
}

export function chunkGridLines() {
  const meridians = Array.from({ length: COLUMNS }, (_, column) =>
    Array.from({ length: 181 }, (_, step) => [column * RA_STEP, step - 90]));
  const parallels = DEC_EDGES.slice(1, -1).map(dec =>
    Array.from({ length: 361 }, (_, ra) => [ra, dec]));
  return [...meridians, ...parallels];
}
