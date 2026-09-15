import { describe, expect, it } from 'vitest';

import { clamp } from '../src/utils/clamp';

describe('clamp', () => {
  it('returns the value unchanged when inside the range', () => {
    expect(clamp(5, 0, 10)).toBe(5);
  });

  it('clamps to min when below the range', () => {
    expect(clamp(-5, 0, 10)).toBe(0);
  });

  it('clamps to max when above the range', () => {
    expect(clamp(15, 0, 10)).toBe(10);
  });

  it('is inclusive of both bounds', () => {
    expect(clamp(0, 0, 10)).toBe(0);
    expect(clamp(10, 0, 10)).toBe(10);
  });
});
