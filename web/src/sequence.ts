export interface Coordinates {
  ra: number;
  dec: number;
}

export interface Frame {
  id: string;
  visit_id: string;
  time_utc: string;
  detector: string | number;
  release: string;
  archive_url: string;
  display_url: string;
  wavelength_um?: number | null;
  bandwidth_um?: number | null;
  wavelength_verified?: boolean;
}

export type Comparison = 'matched' | 'unmatched' | 'unverified';

export interface Sequence {
  status: 'ready' | 'one_visit' | 'no_coverage' | 'no_usable_frames' | 'archive_unavailable';
  source?: 'archive' | 'cache';
  comparison_status: Comparison;
  frames: Frame[];
  message?: string;
  ra?: number;
  dec?: number;
}

const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;

export function parseCoordinates(raText: string, decText: string): Coordinates {
  const values = [raText.trim(), decText.trim()];
  if (!values.every(value => decimal.test(value))) {
    throw new Error('Enter both coordinates in decimal degrees.');
  }
  const [ra, dec] = values.map(Number);
  if (!Number.isFinite(ra) || ra < 0 || ra > 360) {
    throw new Error('Right ascension must be between 0° and 360°.');
  }
  if (!Number.isFinite(dec) || dec < -90 || dec > 90) {
    throw new Error('Declination must be between −90° and +90°.');
  }
  return { ra: ra === 360 ? 0 : ra, dec };
}

export function sortFrames(frames: Frame[]): Frame[] {
  return frames.slice().sort((a, b) => Date.parse(a.time_utc) - Date.parse(b.time_utc));
}

function detectorNumber(detector: Frame['detector']): string {
  return String(detector).replace(/^D(?:etector\s+)?/i, '');
}

export function compareFrames(sequence: Sequence, index: number): Comparison {
  if (index === 0 || !sequence.frames[index]) return 'unverified';
  const first = sequence.frames[0];
  const current = sequence.frames[index];
  if (detectorNumber(first.detector) !== detectorNumber(current.detector)) return 'unmatched';
  return index === 1 ? sequence.comparison_status : 'unverified';
}
