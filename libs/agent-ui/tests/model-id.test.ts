import { describe, expect, it } from 'vitest';

import { composeModelId } from '../src/utils/model-id';

describe('composeModelId', () => {
  it('combines provider and model into "{provider}:{model}"', () => {
    expect(composeModelId('openrouter', 'anthropic/claude-sonnet-5')).toBe('openrouter:anthropic/claude-sonnet-5');
  });

  it('does not collapse an already-colon-bearing model id', () => {
    // The model half can itself contain slashes/colons; composeModelId only
    // ever adds the one separating colon, never inspects `model`'s content.
    expect(composeModelId('p', 'a:b')).toBe('p:a:b');
  });
});
