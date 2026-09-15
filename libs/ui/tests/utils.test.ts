import { describe, expect, it } from 'vitest';

import { cn } from '../src/lib/utils';

describe('cn', () => {
  it('joins plain class names', () => {
    expect(cn('a', 'b')).toBe('a b');
  });

  it('drops falsy/conditional values', () => {
    expect(cn('a', false && 'b', undefined, null, 'c')).toBe('a c');
  });

  it('resolves conflicting Tailwind utilities in favor of the later one', () => {
    // twMerge's whole job: same "group" (padding), last one wins.
    expect(cn('p-2', 'p-4')).toBe('p-4');
  });

  it('lets an explicit later class override an earlier variant class', () => {
    expect(cn('text-sm', 'custom-class')).toBe('text-sm custom-class');
  });
});
