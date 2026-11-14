import assert from 'node:assert/strict';
import test from 'node:test';
import { compareFrames, parseCoordinates, sortFrames } from '../src/sequence.ts';

test('wraps 360° right ascension and accepts the polar limits', () => {
  assert.deepEqual(parseCoordinates('360', '-90'), { ra: 0, dec: -90 });
  assert.deepEqual(parseCoordinates('0', '90'), { ra: 0, dec: 90 });
});

test('rejects empty, nonfinite and out-of-range coordinates', () => {
  for (const [ra, dec] of [['', '0'], ['0', ''], ['NaN', '0'], ['361', '0'], ['0', '91'], ['-1', '0'], ['0x12', '0']]) {
    assert.throws(() => parseCoordinates(ra, dec));
  }
});

test('orders by exposure timestamp across visits', () => {
  const early = { time_utc: '2025-08-14T10:00:00Z' };
  const late = { time_utc: '2026-04-10T10:00:00Z' };
  assert.deepEqual(sortFrames([late, early]), [early, late]);
});

test('keeps approximate bandpasses unverified outside the verified pair', () => {
  const frames = [
    { detector: 2, wavelength_um: 1.10, bandwidth_um: 0.02 },
    { detector: 2, wavelength_um: 1.12, bandwidth_um: 0.02 },
    { detector: 2, wavelength_um: 1.40, bandwidth_um: 0.02 },
    { detector: 1 },
  ];
  const sequence = { frames, comparison_status: 'matched' };
  assert.equal(compareFrames(sequence, 1), 'matched');
  assert.equal(compareFrames(sequence, 2), 'unverified');
  assert.equal(compareFrames(sequence, 3), 'unmatched');
});
