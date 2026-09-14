import { z } from 'zod';

import { clearTokens, getAccessToken, getBackendUrl, getRefreshToken, setTokens } from './auth-store';

/**
 * Thrown when the backend returns a non-2xx response. `detail` is the
 * FastAPI-style `{"detail": "..."}` error body when the backend sent one,
 * otherwise the raw HTTP status line.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`Request failed with ${status}: ${detail}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Thrown when a 2xx response's JSON body doesn't match the schema we
 * expect for that endpoint — including when it contains a field we don't
 * know about, since every schema in `../api/schemas.ts` is `.strict()`.
 *
 * This is the point: if the backend's response shape changes (a field
 * renamed, removed, or newly added) without the frontend being updated to
 * match, this throws immediately with the exact path/reason instead of the
 * UI silently reading `undefined` somewhere or quietly ignoring new data.
 */
export class ApiSchemaError extends Error {
  readonly url: string;
  readonly issues: z.ZodIssue[];

  constructor(url: string, issues: z.ZodIssue[]) {
    const summary = issues
      .map((issue) => `${issue.path.length > 0 ? issue.path.join('.') : '<root>'}: ${issue.message}`)
      .join('; ');
    super(
      `Response from ${url} does not match the expected shape — the backend contract may have ` +
        `changed and the frontend schema in api/schemas.ts needs updating. ${issues.length} issue(s): ${summary}`,
    );
    this.name = 'ApiSchemaError';
    this.url = url;
    this.issues = issues;
  }
}

const errorBodySchema = z.object({ detail: z.string() });

// ── auth: bearer injection + one-shot refresh on 401 ──────────────────

function withBearer(init: RequestInit | undefined): RequestInit {
  const token = getAccessToken();
  if (!token) return init ?? {};
  return { ...init, headers: { ...(init?.headers ?? {}), Authorization: `Bearer ${token}` } };
}

const refreshTokenSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string(),
  token_type: z.literal('bearer'),
  expires_in: z.number(),
});

let refreshInFlight: Promise<boolean> | null = null;

/** Exchange the stored refresh token for a fresh pair. De-duped: concurrent
 * 401s share one round-trip. Resolves `false` (and clears the session) on
 * failure, which makes `<AuthGate>` fall back to the login screen. */
function refreshSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  const refresh_token = getRefreshToken();
  if (!refresh_token) return Promise.resolve(false);

  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${getBackendUrl()}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token }),
      });
      if (!res.ok) {
        clearTokens();
        return false;
      }
      const parsed = refreshTokenSchema.safeParse(await res.json());
      if (!parsed.success) {
        clearTokens();
        return false;
      }
      setTokens(parsed.data);
      return true;
    } catch {
      clearTokens();
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

/** `fetch` with the access token attached. On a 401 for a non-auth route it
 * refreshes once and retries; a still-failing request clears the session.
 *
 * Exported so the AG-UI streaming client (`use-agent-stream.ts`) and the
 * run-interrupt call go through the exact same bearer-injection and
 * refresh-on-401 path as every REST call — its signature matches
 * `@ag-ui/client`'s `HttpAgentFetchFn`. */
export async function authedFetch(url: string, init?: RequestInit): Promise<Response> {
  const isAuthRoute = url.includes('/api/auth/');
  let res = await fetch(url, withBearer(init));
  if (res.status === 401 && !isAuthRoute && getRefreshToken()) {
    const ok = await refreshSession();
    if (ok) res = await fetch(url, withBearer(init));
    else clearTokens();
  }
  return res;
}

async function readErrorDetail(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    const parsed = errorBodySchema.safeParse(body);
    return parsed.success ? parsed.data.detail : `${res.status} ${res.statusText}`;
  } catch {
    return `${res.status} ${res.statusText}`;
  }
}

/**
 * Fetches `url` and validates the JSON body against `schema`.
 *
 * - Non-2xx response → `ApiError` (carrying the backend's `detail` message
 *   when present).
 * - 2xx response whose body doesn't match `schema` → `ApiSchemaError`.
 * - Otherwise → the parsed value, typed as `T`.
 *
 * Every function in `../api/*.ts` goes through this one function — it's the
 * single place "did the backend actually send us what we expect" gets
 * decided, so there's exactly one place to look when a response shape
 * changes on the backend and something downstream needs updating.
 */
export async function apiRequest<T>(url: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  const res = await authedFetch(url, init);
  if (!res.ok) {
    throw new ApiError(res.status, await readErrorDetail(res));
  }

  const body: unknown = await res.json();
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiSchemaError(url, parsed.error.issues);
  }
  return parsed.data;
}

const JSON_HEADERS = { 'Content-Type': 'application/json' } as const;

export function apiGet<T>(url: string, schema: z.ZodType<T>): Promise<T> {
  return apiRequest(url, schema);
}

/**
 * `GET` for a binary (non-JSON) response — e.g. a workspace file download.
 * Same auth + non-2xx → `ApiError` handling as `apiRequest`, but returns the
 * raw `Blob` instead of validating a schema.
 */
export async function apiGetBlob(url: string): Promise<Blob> {
  const res = await authedFetch(url);
  if (!res.ok) {
    throw new ApiError(res.status, await readErrorDetail(res));
  }
  return res.blob();
}

export function apiPost<T>(url: string, schema: z.ZodType<T>, body: unknown): Promise<T> {
  return apiRequest(url, schema, { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(body) });
}

export function apiPut<T>(url: string, schema: z.ZodType<T>, body: unknown): Promise<T> {
  return apiRequest(url, schema, { method: 'PUT', headers: JSON_HEADERS, body: JSON.stringify(body) });
}

/**
 * Like `apiPost`, but sends a `multipart/form-data` body (for real file
 * uploads — e.g. `POST /api/sessions/{id}/rag/file`) instead of JSON. No
 * `Content-Type` header is set explicitly: the browser derives one with the
 * correct multipart boundary from the `FormData` instance itself: setting
 * it manually would omit that boundary and break parsing.
 */
export function apiPostForm<T>(url: string, schema: z.ZodType<T>, formData: FormData): Promise<T> {
  return apiRequest(url, schema, { method: 'POST', body: formData });
}

/**
 * `DELETE` doesn't validate a response schema — unlike every other verb here,
 * a delete route's response body (`{"status": "deleted", ...}`) varies per
 * resource and callers only ever care whether it succeeded, not its exact
 * shape. Still goes through the same non-2xx → `ApiError` handling as
 * `apiRequest`, just without the schema-validation half.
 */
export async function apiDelete(url: string): Promise<void> {
  const res = await authedFetch(url, { method: 'DELETE' });
  if (!res.ok) {
    throw new ApiError(res.status, await readErrorDetail(res));
  }
}
