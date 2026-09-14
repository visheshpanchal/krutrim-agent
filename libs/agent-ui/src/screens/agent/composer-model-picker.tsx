import { useEffect, useState } from 'react';
import type { ModelCard, ProviderCard, RoleModelSettings } from '@krutrim_agent/shared-types';

import {
  fetchModelCatalog,
  fetchProviders,
  fetchSessionModelSettings,
  resetSessionModelSettings,
  updateSessionModelSettings,
} from '../../api';
import { ModelPicker } from '../../components/conversation/model-picker';
import { composeModelId } from '../../utils/model-id';

/** Picks the role the composer switcher targets — the primary chat role. */
function primaryRole(roles: RoleModelSettings[]): RoleModelSettings | null {
  return roles.find((r) => r.role === 'main') ?? roles[0] ?? null;
}

export interface ComposerModelPickerProps {
  backendUrl: string;
  /** The active agent session — the switch is a per-session override. */
  sessionId: string;
}

/**
 * The composer's model switcher for agent mode. Writes a **session-scoped**
 * override of the agent's `main` role via `PUT /api/providers/sessions/{id}/{role}`.
 * Takes effect on the next message.
 */
export function ComposerModelPicker({ backendUrl, sessionId }: ComposerModelPickerProps) {
  const [role, setRole] = useState<RoleModelSettings | null>(null);
  const [models, setModels] = useState<ModelCard[]>([]);
  const [providers, setProviders] = useState<ProviderCard[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setRole(null);
    Promise.all([
      fetchSessionModelSettings(backendUrl, sessionId),
      fetchModelCatalog(backendUrl, { kind: 'chat' }),
      fetchProviders(backendUrl),
    ])
      .then(([settings, catalog, provs]) => {
        if (cancelled) return;
        setRole(primaryRole(settings.roles));
        setModels(catalog);
        setProviders(provs);
      })
      .catch(() => {
        /* non-critical — the picker just stays hidden */
      });
    return () => {
      cancelled = true;
    };
  }, [backendUrl, sessionId]);

  if (!role) return null;

  const value = composeModelId(role.settings.provider, role.settings.model);

  async function apply(modelId: string) {
    if (busy || modelId === value) return;
    setBusy(true);
    try {
      const data = await updateSessionModelSettings(backendUrl, sessionId, role!.role, { model_id: modelId });
      setRole(primaryRole(data.roles));
    } catch {
      /* keep the previous selection on failure */
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    if (busy) return;
    setBusy(true);
    try {
      const data = await resetSessionModelSettings(backendUrl, sessionId, role!.role);
      setRole(primaryRole(data.roles));
    } catch {
      /* keep the previous selection on failure */
    } finally {
      setBusy(false);
    }
  }

  return (
    <ModelPicker
      label="Model for this session"
      models={models}
      providers={providers}
      value={value}
      onChange={apply}
      onReset={role.source !== 'profile' ? reset : undefined}
      busy={busy}
    />
  );
}
