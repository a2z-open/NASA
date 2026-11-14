import assert from 'node:assert/strict';
import test from 'node:test';
import {
  parseRA, parseDec, parseCoordinateString, formatRA, formatDec, toTangent, fromTangent,
  skyToGrid, gridToSky, halfToFloat, decodeFloat16, stretchValue, propagateLinear, wavelengthMatched,
} from '../src/lib/astro.ts';
import { difference, stack, sharedLimits } from '../src/lib/compose.ts';

const close = (a, b, tol = 1e-6) => assert.ok(Math.abs(a - b) <= tol, `${a} != ${b} (tol ${tol})`);

test('parses decimal and sexagesimal right ascension', () => {
  close(parseRA('331.0966'), 331.0966);
  close(parseRA('08h55m10.831s'), (8 + 55 / 60 + 10.831 / 3600) * 15, 1e-9);
  close(parseRA('08:55:10.831'), (8 + 55 / 60 + 10.831 / 3600) * 15, 1e-9);
  close(parseRA('08 55 10.831'), (8 + 55 / 60 + 10.831 / 3600) * 15, 1e-9);
  assert.equal(parseRA('360'), 0);
});

test('parses signed sexagesimal declination including the Unicode minus', () => {
  close(parseDec('-07d14m42.53s'), -(7 + 14 / 60 + 42.53 / 3600), 1e-9);
  close(parseDec('−07:14:42.53'), -(7 + 14 / 60 + 42.53 / 3600), 1e-9);
  close(parseDec('-00 30 00'), -0.5, 1e-12);
  close(parseDec('+66.755'), 66.755);
});

test('rejects invalid and out-of-range coordinates', () => {
  for (const bad of ['', 'abc', '361', '-1', '25h00m00s', '12h61m00s']) assert.throws(() => parseRA(bad), bad);
  for (const bad of ['', '91', '-90.5', '10d61m']) assert.throws(() => parseDec(bad), bad);
});

test('parses one-string coordinates and leaves names alone', () => {
  const a = parseCoordinateString('331.0966 -56.8006');
  close(a.ra, 331.0966); close(a.dec, -56.8006);
  const b = parseCoordinateString('22h04m23.2s -56d48m02s');
  close(b.ra, (22 + 4 / 60 + 23.2 / 3600) * 15, 1e-9);
  const c = parseCoordinateString('08 55 10.8 -07 14 42.5');
  assert.ok(c && c.dec < 0);
  assert.equal(parseCoordinateString("Barnard's Star"), null);
  assert.equal(parseCoordinateString('eps Ind B'), null);
});

test('formats sexagesimal with carries', () => {
  assert.equal(formatRA(0), '00h00m00.00s');
  assert.equal(formatRA(359.99999999), '00h00m00.00s');
  assert.equal(formatDec(-7.245147, 1), '−07°14′42.5″');
});

test('tangent projection round-trips, including across RA = 0', () => {
  for (const [ra0, dec0, ra, dec] of [[331.1, -56.8, 331.12, -56.79], [0.001, 10, 359.995, 10.01], [248.17, 66.75, 248.2, 66.76]]) {
    const { xi, eta } = toTangent(ra, dec, ra0, dec0);
    const back = fromTangent(xi, eta, ra0, dec0);
    close(((back.ra - ra + 540) % 360) - 180, 0, 1e-9);
    close(back.dec, dec, 1e-9);
  }
  const { xi } = toTangent(0.001, 0, 359.999, 0);
  close(xi, 7.2, 1e-3); // east of the reference across the wrap
});

test('display grid is north-up, east-left, row 0 = north', () => {
  const grid = { nx: 99, ny: 99, pixel_arcsec: 6.15, ra0: 100, dec0: 20 };
  const c = skyToGrid(grid, 100, 20);
  close(c.col, 49); close(c.row, 49);
  const north = skyToGrid(grid, 100, 20 + 6.15 / 3600);
  close(north.row, 48, 1e-6);
  const east = skyToGrid(grid, 100 + 6.15 / 3600 / Math.cos(20 * Math.PI / 180), 20);
  assert.ok(east.col < 49);
  const p = gridToSky(grid, 10.3, 70.7);
  const g = skyToGrid(grid, p.ra, p.dec);
  close(g.col, 10.3, 1e-6); close(g.row, 70.7, 1e-6);
});

test('decodes IEEE half-precision floats', () => {
  assert.equal(halfToFloat(0x3c00), 1);
  assert.equal(halfToFloat(0xc000), -2);
  assert.equal(halfToFloat(0x7bff), 65504);
  close(halfToFloat(0x0001), 2 ** -24, 1e-12);
  assert.ok(Number.isNaN(halfToFloat(0x7e00)));
  const buf = new Uint16Array([0x3c00, 0x3800, 0x7e00]).buffer;
  const out = decodeFloat16(buf);
  assert.deepEqual([out[0], out[1]], [1, 0.5]);
  assert.ok(Number.isNaN(out[2]));
});

test('stretches clip and keep NaN', () => {
  assert.equal(stretchValue(-5, 0, 10, 'linear'), 0);
  assert.equal(stretchValue(15, 0, 10, 'linear'), 1);
  close(stretchValue(5, 0, 10, 'linear'), 0.5);
  assert.ok(stretchValue(5, 0, 10, 'asinh') > 0.5);
  assert.ok(Number.isNaN(stretchValue(NaN, 0, 1, 'asinh')));
});

test('linear proper motion over one year', () => {
  const p = propagateLinear(331.0, -56.8, 3600, 0, 57388.5, 57388.5 + 365.25);
  const { xi, eta } = toTangent(p.ra, p.dec, 331.0, -56.8);
  close(xi, 3.6, 1e-6); close(eta, 0, 1e-6);
});

test('wavelength matching uses the bandwidth', () => {
  assert.equal(wavelengthMatched({ wavelength_um: 1.50, bandwidth_um: 0.04 }, { wavelength_um: 1.52, bandwidth_um: 0.04 }), true);
  assert.equal(wavelengthMatched({ wavelength_um: 1.50, bandwidth_um: 0.04 }, { wavelength_um: 1.60, bandwidth_um: 0.04 }), false);
  assert.equal(wavelengthMatched({ wavelength_um: null, bandwidth_um: 0.04 }, { wavelength_um: 1.60, bandwidth_um: 0.04 }), null);
});

test('difference and stack subtract backgrounds and ignore NaN', () => {
  const a = new Float32Array([1, 2, NaN]);
  const b = new Float32Array([3, 2, 5]);
  const d = difference(b, 1, a, 0);
  assert.deepEqual([d[0], d[1]], [1, -1]);
  assert.ok(Number.isNaN(d[2]));
  const s = stack([{ data: a, median: 1 }, { data: b, median: 2 }]);
  assert.deepEqual([s.data[0], s.data[1], s.data[2]], [0.5, 0.5, 3]);
  assert.deepEqual(Array.from(s.count), [2, 2, 1]);
  const lim = sharedLimits([{ median: 1, sigma: 0.1, p995: 3 }, { median: 2, sigma: 0.2, p995: 4 }], 2, 1);
  close(lim.lo, -0.3, 1e-9); close(lim.hi, 2, 1e-9);
});
