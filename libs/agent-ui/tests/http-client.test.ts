import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';

import { configureAuth, getAccessToken, getRefreshToken, setTokens } from '../src/utils/auth-store';
import { apiDelete, apiGet, apiGetBlob, apiPost, ApiError, ApiSchemaError, authedFetch } from '../src/utils/http-client';

const schema = z.object({ id: z.string() }).strict();

function jsonResponse(body: unknown, init: { ok?: boolean; status?: number; statusText?: string } = {}) {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    statusText: init.statusText ?? 'OK',
    json: async () => body,
  } as Response;
}

beforeEach(() => {
  window.localStorage.clear();
  configureAuth('http://backend.example');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('apiGet', () => {
  it('resolves with the parsed body on a 2xx response matching the schema', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ id: 'abc' })));
    await expect(apiGet('http://backend.example/thing', schema)).resolves.toEqual({ id: 'abc' });
  });

  it('throws ApiError with the backend detail on a non-2xx response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'not found' }, { ok: false, status: 404 })),
    );
    await expect(apiGet('http://backend.example/thing', schema)).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      detail: 'not found',
    });
  });

  it('falls back to the raw status line when the error body has no detail field', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => {
          throw new Error('not json');
        },
      } as unknown as Response),
    );
    await expect(apiGet('http://backend.example/thing', schema)).rejects.toMatchObject({
      detail: '500 Internal Server Error',
    });
  });

  it('throws ApiSchemaError when a 2xx body does not match the expected shape', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ id: 'abc', extra: 'field' })));
    const error = await apiGet('http://backend.example/thing', schema).catch((e) => e);
    expect(error).toBeInstanceOf(ApiSchemaError);
    expect((error as ApiSchemaError).issues.length).toBeGreaterThan(0);
  });
});

describe('authedFetch', () => {
  it('attaches the stored access token as a Bearer header', async () => {
    setTokens({ access_token: 'tok-1', refresh_token: 'ref-1', token_type: 'bearer', expires_in: 3600 });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal('fetch', fetchMock);

    await authedFetch('http://backend.example/thing');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend.example/thing',
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer tok-1' }) }),
    );
  });

  it('sends no Authorization header when there is no access token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal('fetch', fetchMock);

    await authedFetch('http://backend.example/thing');

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit | undefined];
    expect(init?.headers).toBeUndefined();
  });

  it('refreshes once on a 401 and retries the original request', async () => {
    setTokens({ access_token: 'expired', refresh_token: 'ref-1', token_type: 'bearer', expires_in: 3600 });

    const fetchMock = vi
      .fn()
      // 1) the original request -> 401
      .mockResolvedValueOnce(jsonResponse({}, { ok: false, status: 401 }))
      // 2) the refresh call -> new token pair
      .mockResolvedValueOnce(
        jsonResponse({ access_token: 'fresh', refresh_token: 'ref-2', token_type: 'bearer', expires_in: 3600 }),
      )
      // 3) the retried original request -> success
      .mockResolvedValueOnce(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    const res = await authedFetch('http://backend.example/thing');

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toBe('http://backend.example/api/auth/refresh');
    expect(res.ok).toBe(true);
    // The retried call must use the freshly-refreshed token, not the expired one.
    expect(fetchMock.mock.calls[2][1]).toMatchObject({ headers: { Authorization: 'Bearer fresh' } });
    expect(getAccessToken()).toBe('fresh');
  });

  it('clears the session when the refresh call itself fails', async () => {
    setTokens({ access_token: 'expired', refresh_token: 'ref-1', token_type: 'bearer', expires_in: 3600 });

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({}, { ok: false, status: 401 }))
      .mockResolvedValueOnce(jsonResponse({}, { ok: false, status: 401 }));
    vi.stubGlobal('fetch', fetchMock);

    await authedFetch('http://backend.example/thing');

    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it('does not attempt a refresh for a request to the auth routes themselves', async () => {
    setTokens({ access_token: 'expired', refresh_token: 'ref-1', token_type: 'bearer', expires_in: 3600 });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}, { ok: false, status: 401 }));
    vi.stubGlobal('fetch', fetchMock);

    await authedFetch('http://backend.example/api/auth/login');

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('apiPost', () => {
  it('sends a JSON body with the JSON content-type header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'abc' }));
    vi.stubGlobal('fetch', fetchMock);

    await apiPost('http://backend.example/thing', schema, { name: 'x' });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend.example/thing',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ name: 'x' }),
      }),
    );
  });
});

describe('apiDelete', () => {
  it('resolves without validating a response body on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ anything: 'goes' })));
    await expect(apiDelete('http://backend.example/thing')).resolves.toBeUndefined();
  });

  it('throws ApiError on a non-2xx response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'nope' }, { ok: false, status: 403 })),
    );
    await expect(apiDelete('http://backend.example/thing')).rejects.toBeInstanceOf(ApiError);
  });
});

describe('apiGetBlob', () => {
  it('returns the raw blob on success', async () => {
    const blob = new Blob(['data']);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200, statusText: 'OK', blob: async () => blob } as unknown as Response),
    );
    await expect(apiGetBlob('http://backend.example/file')).resolves.toBe(blob);
  });

  it('throws ApiError on a non-2xx response instead of returning a blob', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'missing' }, { ok: false, status: 404 })),
    );
    await expect(apiGetBlob('http://backend.example/file')).rejects.toBeInstanceOf(ApiError);
  });
});
