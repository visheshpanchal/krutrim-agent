import type { TokenPair } from '@krutrim_agent/shared-types';

/**
 * Client-side auth state: the JWT pair (persisted to `localStorage` so a
 * reload stays signed in) plus the backend URL the token talks to. This is
 * the one place `http-client.ts` reads the access token from and the one
 * place the login screen writes it to.
 *
 * `localStorage` is readable by any script on the origin — an XSS bug would
 * leak the tokens. Accepted for now (see plan.md); the access token
 * is short-lived and refresh rotation limits the blast radius.
 */

const ACCESS_KEY = 'krutrim.auth.access';
const REFRESH_KEY = 'krutrim.auth.refresh';

let backendUrl = '';
const listeners = new Set<() => void>();

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* private mode / storage disabled — tokens just won't persist */
  }
}

/** Call once at app start with the backend base URL (see `agent.tsx`). */
export function configureAuth(url: string): void {
  backendUrl = url.replace(/\/$/, '');
}

export function getBackendUrl(): string {
  return backendUrl;
}

export function getAccessToken(): string | null {
  return readStorage(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return readStorage(REFRESH_KEY);
}

export function hasSession(): boolean {
  return getAccessToken() !== null && getRefreshToken() !== null;
}

export function setTokens(tokens: TokenPair): void {
  writeStorage(ACCESS_KEY, tokens.access_token);
  writeStorage(REFRESH_KEY, tokens.refresh_token);
  emit();
}

export function clearTokens(): void {
  writeStorage(ACCESS_KEY, null);
  writeStorage(REFRESH_KEY, null);
  emit();
}

/** Subscribe to session changes (login, logout, forced sign-out on a failed
 * refresh). Returns an unsubscribe fn. */
export function onAuthChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit(): void {
  for (const fn of listeners) fn();
}
