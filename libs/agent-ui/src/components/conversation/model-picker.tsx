import type { ModelCard, ProviderCard } from '@krutrim_agent/shared-types';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
} from '@krutrim_agent/ui';

import { composeModelId } from '../../utils/model-id';

const RESET = '__reset__';

function providerLabel(providers: ProviderCard[], key: string): string {
  return providers.find((p) => p.key === key)?.label ?? key;
}

export interface ModelPickerProps {
  /** aria-label for the trigger — describes the scope being changed. */
  label: string;
  models: ModelCard[];
  providers: ProviderCard[];
  /** The current selection's `"{provider}:{model}"` id. */
  value: string;
  onChange: (modelId: string) => void;
  /** Shows a trailing "Reset to default" item when provided. */
  onReset?: () => void;
  busy?: boolean;
}

/** The one model dropdown used by both the chat and agent composers. Options
 * read `"{provider label}: {model label}"` so the same model offered through
 * more than one provider (e.g. OpenRouter vs. Ollama) stays distinguishable. */
export function ModelPicker({ label, models, providers, value, onChange, onReset, busy }: ModelPickerProps) {
  const known = models.find((m) => composeModelId(m.provider, m.id) === value);

  function handleChange(next: string) {
    if (next === RESET) {
      onReset?.();
      return;
    }
    onChange(next);
  }

  return (
    <Select value={value} onValueChange={handleChange} disabled={busy}>
      <SelectTrigger
        aria-label={label}
        className="h-7 gap-1 border-0 bg-transparent px-2 text-xs text-muted-foreground hover:text-foreground focus:ring-0"
      >
        <SelectValue placeholder="Model">
          {known ? `${providerLabel(providers, known.provider)}: ${known.label}` : value}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {models.map((m) => (
          <SelectItem key={composeModelId(m.provider, m.id)} value={composeModelId(m.provider, m.id)}>
            {providerLabel(providers, m.provider)}: {m.label}
          </SelectItem>
        ))}
        {!known && <SelectItem value={value}>{value} (custom)</SelectItem>}
        {onReset && (
          <>
            <Separator className="my-1" />
            <SelectItem value={RESET}>Reset to default</SelectItem>
          </>
        )}
      </SelectContent>
    </Select>
  );
}
