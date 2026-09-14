import { useEffect, useMemo, useState } from 'react';
import type { AppSettingField, AppSettingsPayload, AppSettingValue } from '@krutrim_agent/shared-types';
import {
  Button,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
} from '@krutrim_agent/ui';

import { fetchAppSettings, resetAppSettings, updateAppSettings } from '../../../api';
import { ApiError } from '../../../utils/http-client';

interface AppSettingsSectionProps {
  backendUrl: string;
}

function humanize(key: string): string {
  const s = key.replace(/_/g, ' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
}

type Draft = Record<string, AppSettingValue>;

function draftFrom(settings: Record<string, AppSettingField>): Draft {
  return Object.fromEntries(
    Object.entries(settings).map(([key, field]) => [key, field.current_value]),
  );
}

/**
 * Form over `GET/PUT /api/settings/app` — the hot-reloadable app-settings tier
 * (`<home_root>/config.json`). Every widget is chosen from the backend
 * descriptor `type` (`enum` → select, `boolean` → checkbox, `integer` /
 * `number` → number input, `string` → text), never inferred from the value.
 * Edits are batched and saved together; any key that differs from its
 * built-in default gets a per-key **Reset**. Changes land on the next agent turn.
 */
export function AppSettingsSection({ backendUrl }: AppSettingsSectionProps) {
  const [payload, setPayload] = useState<AppSettingsPayload | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchAppSettings(backendUrl)
      .then((p) => {
        if (cancelled) return;
        setPayload(p);
        setDraft(draftFrom(p.settings));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setStatus(err instanceof ApiError ? err.detail : `Could not reach ${backendUrl}.`);
      });
    return () => {
      cancelled = true;
    };
  }, [backendUrl]);

  const entries = useMemo(
    () => (payload ? Object.entries(payload.settings) : []),
    [payload],
  );

  const changed = useMemo(() => {
    const out: Draft = {};
    for (const [key, field] of entries) {
      if (draft[key] !== field.current_value) out[key] = draft[key];
    }
    return out;
  }, [draft, entries]);

  const dirty = Object.keys(changed).length > 0;

  async function save() {
    setBusy(true);
    setStatus(null);
    try {
      const next = await updateAppSettings(backendUrl, changed);
      setPayload(next);
      setDraft(draftFrom(next.settings));
      setStatus('Saved — applies on the next agent turn.');
    } catch (err) {
      setStatus(err instanceof ApiError ? err.detail : 'Save failed — check the values.');
    } finally {
      setBusy(false);
    }
  }

  async function resetKey(key: string) {
    setBusy(true);
    setStatus(null);
    try {
      const next = await resetAppSettings(backendUrl, [key]);
      setPayload(next);
      setDraft(draftFrom(next.settings));
      setStatus(`Reset "${humanize(key)}" to its default.`);
    } catch (err) {
      setStatus(err instanceof ApiError ? err.detail : 'Reset failed.');
    } finally {
      setBusy(false);
    }
  }

  if (!payload) {
    return (
      <section>
        <h3 className="text-sm font-medium text-foreground">Application</h3>
        <p className="mt-2 text-xs text-muted-foreground">{status ?? 'Loading…'}</p>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-col divide-y divide-border rounded-md border border-border">
        {entries.map(([key, field]) => (
          <div key={key} className="flex items-center gap-3 px-3 py-2">
            <Label htmlFor={`app-setting-${key}`} className="min-w-0 flex-1 text-xs">
              {humanize(key)}
              {field.overridden && (
                <span className="ml-2 text-[11px] font-normal text-muted-foreground">
                  default: {String(field.default_value)}
                </span>
              )}
            </Label>

            <AppSettingControl
              id={`app-setting-${key}`}
              field={field}
              value={draft[key]}
              onChange={(next) => setDraft((d) => ({ ...d, [key]: next }))}
            />

            <button
              type="button"
              className="text-[11px] text-muted-foreground hover:text-foreground disabled:invisible"
              disabled={!field.overridden || busy}
              onClick={() => void resetKey(key)}
            >
              Reset
            </button>
          </div>
        ))}
      </div>

      {status && <p className="text-xs text-muted-foreground">{status}</p>}

      <div className="flex justify-end">
        <Button size="sm" disabled={!dirty || busy} onClick={() => void save()}>
          {busy ? 'Saving…' : 'Save changes'}
        </Button>
      </div>

      <Separator />

      <div className="flex flex-col gap-2 opacity-60">
        <div>
          <h3 className="text-sm font-medium text-foreground">MCP Servers</h3>
          <p className="text-xs text-muted-foreground">
            Connect Model Context Protocol servers. Coming soon.
          </p>
        </div>
        <div>
          <h3 className="text-sm font-medium text-foreground">Integrations</h3>
          <p className="text-xs text-muted-foreground">
            OAuth &amp; API-key connections to third-party services. Coming soon.
          </p>
        </div>
      </div>
    </section>
  );
}

interface AppSettingControlProps {
  id: string;
  field: AppSettingField;
  value: AppSettingValue;
  onChange: (next: AppSettingValue) => void;
}

/** One row's editor, chosen from `field.type` — never from `typeof value`. */
function AppSettingControl({ id, field, value, onChange }: AppSettingControlProps) {
  if (field.type === 'boolean') {
    return (
      <input
        id={id}
        type="checkbox"
        className="size-4 accent-primary"
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }

  if (field.type === 'enum' && field.possible_values) {
    return (
      <Select value={String(value)} onValueChange={onChange}>
        <SelectTrigger id={id} className="h-8 w-52 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {field.possible_values.map((opt) => (
            <SelectItem key={String(opt)} value={String(opt)} className="text-xs">
              {humanize(String(opt))}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }

  const numeric = field.type === 'integer' || field.type === 'number';
  return (
    <Input
      id={id}
      className="h-8 w-52 text-xs"
      type={numeric ? 'number' : 'text'}
      step={field.type === 'integer' ? 1 : 'any'}
      min={field.minimum ?? undefined}
      max={field.maximum ?? undefined}
      value={String(value)}
      onChange={(e) => onChange(numeric ? Number(e.target.value) : e.target.value)}
    />
  );
}
