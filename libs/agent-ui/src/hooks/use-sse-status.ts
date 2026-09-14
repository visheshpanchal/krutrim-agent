import { useEffect, useState } from 'react';

import { getAccessToken } from '../utils/auth-store';

/**
 * Subscribes to a backend SSE endpoint (`GET /api/status/...` — see
 * `krutrim_agent_backend/api/status_routes.py`) and returns the most recently
 * received JSON payload, or `null` before the first event / whenever `url`
 * is `null` (pass `null` to disable the subscription entirely, e.g. when
 * there's no active session to watch yet).
 *
 * `EventSource` auto-reconnects on transient errors on its own — there's
 * nothing for this hook to do beyond letting the browser retry; a
 * persistently-down backend just means the last-known status keeps showing.
 *
 * `EventSource` can't set an `Authorization` header, so the access token is
 * passed as `?access_token=` — `AuthMiddleware` accepts that as a fallback.
 * It's read once when the subscription opens; these status streams are far
 * shorter-lived than the token, so a mid-stream rotation isn't a concern.
 */
export function useSseStatus<T>(url: string | null): T | null {
  const [status, setStatus] = useState<T | null>(null);

  useEffect(() => {
    setStatus(null);
    if (!url) return;

    const token = getAccessToken();
    const src = token ? `${url}${url.includes('?') ? '&' : '?'}access_token=${encodeURIComponent(token)}` : url;
    const source = new EventSource(src);
    source.onmessage = (event) => {
      try {
        setStatus(JSON.parse(event.data) as T);
      } catch {
        // Malformed payload — ignore, keep the last-known-good status. A
        // live stream should degrade gracefully on one bad frame rather
        // than tear down the subscription (see `schemas.ts`'s note on why
        // SSE payloads aren't validated as strictly as REST responses).
      }
    };

    return () => source.close();
  }, [url]);

  return status;
}
