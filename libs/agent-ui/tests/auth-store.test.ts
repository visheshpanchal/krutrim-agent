import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  clearTokens,
  configureAuth,
  getAccessToken,
  getBackendUrl,
  getRefreshToken,
  hasSession,
  onAuthChange,
  setTokens,
} from '../src/utils/auth-store';

const TOKENS = {
  access_token: 'access-1',
  refresh_token: 'refresh-1',
  token_type: 'bearer' as const,
  expires_in: 3600,
};

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  clearTokens();
});

describe('configureAuth / getBackendUrl', () => {
  it('strips a trailing slash from the configured URL', () => {
    configureAuth('http://backend.example/');
    expect(getBackendUrl()).toBe('http://backend.example');
  });

  it('leaves a URL with no trailing slash untouched', () => {
    configureAuth('http://backend.example');
    expect(getBackendUrl()).toBe('http://backend.example');
  });
});

describe('setTokens / getAccessToken / getRefreshToken / clearTokens', () => {
  it('has no session before any tokens are set', () => {
    expect(hasSession()).toBe(false);
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it('persists both tokens and reports a session once set', () => {
    setTokens(TOKENS);
    expect(getAccessToken()).toBe('access-1');
    expect(getRefreshToken()).toBe('refresh-1');
    expect(hasSession()).toBe(true);
  });

  it('clears both tokens and the session on clearTokens', () => {
    setTokens(TOKENS);
    clearTokens();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
    expect(hasSession()).toBe(false);
  });
});

describe('onAuthChange', () => {
  it('notifies subscribers on setTokens and clearTokens', () => {
    const listener = vi.fn();
    const unsubscribe = onAuthChange(listener);

    setTokens(TOKENS);
    expect(listener).toHaveBeenCalledTimes(1);

    clearTokens();
    expect(listener).toHaveBeenCalledTimes(2);

    unsubscribe();
  });

  it('stops notifying once unsubscribed', () => {
    const listener = vi.fn();
    const unsubscribe = onAuthChange(listener);
    unsubscribe();

    setTokens(TOKENS);
    expect(listener).not.toHaveBeenCalled();
  });
});
