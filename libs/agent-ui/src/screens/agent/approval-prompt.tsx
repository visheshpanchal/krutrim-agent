import { useState } from 'react';
import { Button, cn } from '@krutrim_agent/ui';
import { ShieldAlert } from 'lucide-react';

import type { PendingApproval } from '../types';

export interface ApprovalPromptProps {
  approval: PendingApproval;
  /** Busy while the resume request is in flight. */
  disabled?: boolean;
  onDecide: (decision: 'approve' | 'reject', note?: string) => void;
}

/**
 * The approve / reject card shown while a run is paused on a sandbox-policy
 * gate (`useAgentStream`'s `pendingApproval`). Approving resumes the tool call;
 * rejecting hands the model a refusal it can adapt to. Only the research screen
 * mounts this today.
 */
export function ApprovalPrompt({ approval, disabled, onDecide }: ApprovalPromptProps) {
  const [note, setNote] = useState('');
  const command =
    typeof approval.args?.command === 'string' ? (approval.args.command as string) : null;
  const filePath =
    typeof approval.args?.file_path === 'string' ? (approval.args.file_path as string) : null;
  const target = command ?? filePath;

  return (
    <div className="mx-4 mb-3 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
      <div className="flex items-start gap-2">
        <ShieldAlert className="mt-0.5 size-4 shrink-0 text-amber-500" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-foreground">
            Approval needed{approval.toolName ? ` — ${approval.toolName}` : ''}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">{approval.reason}</p>
          {target && (
            <pre className="mt-2 max-h-32 overflow-auto rounded bg-background/70 p-2 font-mono text-xs text-foreground">
              {target}
            </pre>
          )}
          <input
            type="text"
            value={note}
            disabled={disabled}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional note to the agent…"
            className={cn(
              'mt-2 w-full rounded border border-border bg-background px-2 py-1 text-xs',
              'outline-none focus:border-ring disabled:opacity-50',
            )}
          />
          <div className="mt-2 flex gap-2">
            <Button
              size="sm"
              variant="default"
              disabled={disabled}
              onClick={() => onDecide('approve', note.trim() || undefined)}
            >
              Approve &amp; run
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={disabled}
              onClick={() => onDecide('reject', note.trim() || undefined)}
            >
              Reject
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
