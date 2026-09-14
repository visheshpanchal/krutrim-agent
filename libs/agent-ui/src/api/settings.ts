import type { AppSettingsPayload, AppSettingValue } from '@krutrim_agent/shared-types';

import { apiGet, apiPost, apiPut } from '../utils/http-client';
import { appSettingsPayloadSchema } from './schemas';

/** `GET /api/settings/app` — the hot-reloadable app-settings tier
 * (`<home_root>/config.json`). */
export function fetchAppSettings(backendUrl: string): Promise<AppSettingsPayload> {
  return apiGet(`${backendUrl}/api/settings/app`, appSettingsPayloadSchema);
}

/** `PUT /api/settings/app/user` — write one or more keys; takes effect on the
 * next agent turn (no restart). */
export function updateAppSettings(
  backendUrl: string,
  updates: Record<string, AppSettingValue>,
): Promise<AppSettingsPayload> {
  return apiPut(`${backendUrl}/api/settings/app/user`, appSettingsPayloadSchema, { updates });
}

/** `POST /api/settings/app/user/reset` — reset the given keys (or all when
 * omitted) to their built-in default. */
export function resetAppSettings(
  backendUrl: string,
  keys?: string[],
): Promise<AppSettingsPayload> {
  return apiPost(`${backendUrl}/api/settings/app/user/reset`, appSettingsPayloadSchema, {
    keys: keys ?? null,
  });
}
