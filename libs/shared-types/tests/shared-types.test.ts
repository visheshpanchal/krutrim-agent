import { describe, expect, it } from 'vitest';

import {
  AGENT_ENDPOINT_PREFIX,
  AGENT_QUERY_PARAM,
  CONTENT_KINDS,
  DEFAULT_AGENT_KEY,
  DEFAULT_BACKEND_URL,
  PROVIDER_KEYS,
  SHARING_SCOPES,
} from '../src/lib/shared-types';

// These constants are hand-mirrored from the backend (see the file's header
// comment) — nothing here catches drift automatically, but a change to any
// of them is a cross-package contract change, not a casual edit, so a test
// that has to be touched deliberately is the point.
describe('shared-types constants', () => {
  it('AGENT_ENDPOINT_PREFIX matches the backend AG-UI route prefix', () => {
    expect(AGENT_ENDPOINT_PREFIX).toBe('/agents');
  });

  it('DEFAULT_BACKEND_URL points at the local dev backend', () => {
    expect(DEFAULT_BACKEND_URL).toBe('http://localhost:8000');
  });

  it('AGENT_QUERY_PARAM/DEFAULT_AGENT_KEY select the default agent via ?agent=research', () => {
    expect(AGENT_QUERY_PARAM).toBe('agent');
    expect(DEFAULT_AGENT_KEY).toBe('research');
  });

  it('PROVIDER_KEYS, CONTENT_KINDS and SHARING_SCOPES are non-empty literal tuples', () => {
    expect(PROVIDER_KEYS.length).toBeGreaterThan(0);
    expect(CONTENT_KINDS.length).toBeGreaterThan(0);
    expect(SHARING_SCOPES.length).toBeGreaterThan(0);
  });
});
