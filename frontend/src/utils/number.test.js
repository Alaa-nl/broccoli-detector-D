// Tests for clampNumber: NaN/non-numeric -> fallback, out-of-range -> bound,
// in-range -> the value itself.

import { clampNumber } from './number.js';

describe('clampNumber', () => {
  it('returns the fallback for a non-numeric string', () => {
    expect(clampNumber('abc', 100, 5000, 1000)).toBe(1000);
  });

  it('returns the fallback for null/undefined (missing storage)', () => {
    expect(clampNumber(null, 100, 5000, 1000)).toBe(1000);
    expect(clampNumber(undefined, 100, 5000, 1000)).toBe(1000);
  });

  it('returns the fallback for NaN', () => {
    expect(clampNumber(NaN, 0.1, 0.9, 0.4)).toBe(0.4);
  });

  it('clamps a value below the minimum up to the minimum', () => {
    expect(clampNumber('10', 100, 5000, 1000)).toBe(100);
  });

  it('clamps a value above the maximum down to the maximum', () => {
    expect(clampNumber('999999', 100, 5000, 1000)).toBe(5000);
  });

  it('returns an in-range value unchanged', () => {
    expect(clampNumber('1200', 100, 5000, 1000)).toBe(1200);
    expect(clampNumber(0.55, 0.1, 0.9, 0.4)).toBe(0.55);
  });
});
