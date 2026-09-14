import { z } from 'zod';
import type { AuthResult, AuthUser, LoginRequest, RegisterRequest } from '@krutrim_agent/shared-types';

import { clearTokens, getRefreshToken } from '../utils/auth-store';
import { apiGet, apiPost } from '../utils/http-client';
import { authResultSchema, authUserSchema } from './schemas';

const authConfigSchema = z.object({ enabled: z.boolean() }).strict();

/** `GET /api/auth/me` — the signed-in user. 401s when there's no session (or
 * auth is disabled on the backend). */
export function fetchMe(backendUrl: string): Promise<AuthUser> {
  return apiGet(`${backendUrl}/api/auth/me`, authUserSchema);
}

/** `GET /api/auth/config` — public. When `enabled` is false the backend needs
 * no token and the UI skips the login gate entirely. */
export function fetchAuthConfig(backendUrl: string): Promise<{ enabled: boolean }> {
  return apiGet(`${backendUrl}/api/auth/config`, authConfigSchema);
}

/** `POST /api/auth/register` — creates the account (the first one becomes the
 * admin) and returns it with a fresh token pair. */
export function register(backendUrl: string, body: RegisterRequest): Promise<AuthResult> {
  return apiPost(`${backendUrl}/api/auth/register`, authResultSchema, body);
}

/** `POST /api/auth/login`. */
export function login(backendUrl: string, body: LoginRequest): Promise<AuthResult> {
  return apiPost(`${backendUrl}/api/auth/login`, authResultSchema, body);
}

/** `POST /api/auth/logout` — best-effort refresh-token revocation. Never
 * throws: the caller clears local state regardless. */
export async function logout(backendUrl: string, refreshToken: string): Promise<void> {
  try {
    await fetch(`${backendUrl}/api/auth/logout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } catch {
    /* offline / already gone — nothing to do */
  }
}

/** Revoke the refresh token server-side and drop the local session — which
 * makes `<AuthGate>` fall back to the login screen. */
export async function signOut(backendUrl: string): Promise<void> {
  const refresh = getRefreshToken();
  if (refresh) await logout(backendUrl, refresh);
  clearTokens();
}
