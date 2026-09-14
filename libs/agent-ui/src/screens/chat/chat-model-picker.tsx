import { useEffect, useState } from 'react';
import type { ModelCard, ProviderCard } from '@krutrim_agent/shared-types';

import { fetchModelCatalog, fetchProviders } from '../../api';
import { ModelPicker } from '../../components/conversation/model-picker';
import { composeModelId } from '../../utils/model-id';

export interface ChatModelPickerProps {
  backendUrl: string;
  /** The chat's current model (`"{provider}:{model}"`) once it exists, or the
   * pending pick for a not-yet-created chat; `null` before either is known —
   * falls back to the catalog default. */
  value: string | null;
  /** Called with the newly chosen `"{provider}:{model}"` id. The caller decides
   * whether that means `PUT /api/chats/{id}/model` (an existing chat) or just
   * remembering the pick until the first message creates one. */
  onChange: (modelId: string) => void;
}

/** The composer's model switcher for plain chat — mirrors the agent mode's
 * `ComposerModelPicker` but backs onto a chat's flat `provider`/`model`
 * instead of per-role session settings (chat has no roles or profile default,
 * so there's no "Reset to default" here). */
export function ChatModelPicker({ backendUrl, value, onChange }: ChatModelPickerProps) {
  const [models, setModels] = useState<ModelCard[]>([]);
  const [providers, setProviders] = useState<ProviderCard[]>([]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchModelCatalog(backendUrl, { kind: 'chat' }), fetchProviders(backendUrl)])
      .then(([catalog, provs]) => {
        if (cancelled) return;
        setModels(catalog);
        setProviders(provs);
      })
      .catch(() => {
        /* non-critical — the picker just stays hidden */
      });
    return () => {
      cancelled = true;
    };
  }, [backendUrl]);

  if (models.length === 0) return null;

  const defaultModel = models.find((m) => m.default) ?? models[0];
  const effectiveValue = value ?? composeModelId(defaultModel.provider, defaultModel.id);

  return (
    <ModelPicker
      label="Chat model"
      models={models}
      providers={providers}
      value={effectiveValue}
      onChange={onChange}
    />
  );
}
