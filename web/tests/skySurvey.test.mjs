import assert from 'node:assert/strict';
import test from 'node:test';
import { SPHEREX_MAP_BANDS } from '../src/lib/skySurvey.ts';

test('the wavelength slider addresses the published PNG planes in ascending wavelength', () => {
  const first = SPHEREX_MAP_BANDS[0], last = SPHEREX_MAP_BANDS.at(-1);
  assert.equal(first.plane, 1);
  assert.equal(first.wavelength, 0.771);
  assert.equal(last.plane, 101);
  assert.equal(last.wavelength, 4.988);
  assert.ok(first.tileFrequencyHz > 64e12 && first.tileFrequencyHz < 66e12);
  assert.ok(last.tileFrequencyHz > 401e12 && last.tileFrequencyHz < 403e12);
  assert.equal(SPHEREX_MAP_BANDS.length, 99);
  assert.ok(SPHEREX_MAP_BANDS.every(band => ![0, 50, 51, 102].includes(band.plane)));
  assert.ok(SPHEREX_MAP_BANDS.every((band, i, all) => !i || band.wavelength > all[i - 1].wavelength));
});
