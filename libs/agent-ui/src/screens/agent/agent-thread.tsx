import { useEffect, useRef, useState } from 'react';
import type { Message } from '@ag-ui/client';
import type { Agent, SessionInfo } from '@krutrim_agent/shared-types';
import { Badge, Button } from '@krutrim_agent/ui';
import { Settings } from 'lucide-react';

import { fetchSession } from '../../api';
import type { PendingApproval, TraceStep } from '../../hooks/use-agent-stream';
import { useBlurStatusTitle } from '../../hooks/use-blur-status-title';
import { useSessionFiles } from '../../hooks/use-session-files';
import { Composer } from '../../components/conversation/composer';
import { FilesButton, FilesDrawer } from '../../components/conversation/files-drawer';
import { AgentMessageList } from './agent-message-list';
import { ApprovalPrompt } from './approval-prompt';
import { ComposerModelPicker } from './composer-model-picker';

/** How long the "✓ Embedding complete" tab-title status stays up after the
 * last upload finishes, before reverting to the plain session title. */
const UPLOAD_COMPLETE_TITLE_MS = 10_000;

export interface AgentThreadProps {
  backendUrl: string;
  agent: Agent;
  sessionId: string | null;
  onOpenSandboxSettings: () => void;
  /** Lifted to `WorkspaceLayout` (via `useAgentChat`) so `OutputPanel`, a sibling,
   * can derive its canvas payload from the same live message list. */
  messages: Message[];
  /** The current (last) turn's step / tool-call / reasoning trace. */
  trace: TraceStep[];
  /** One finished turn's trace per prior user message, in order — rendered as a
   * collapsed activity row above each earlier question. */
  pastTraces: TraceStep[][];
  /** Splits one assistant turn's raw text into just its middle-column working
   * narration (per the agent's turn splitter); the finished report goes to the
   * output panel. */
  narrationForTurn: (assistantText: string, isLastTurn: boolean) => string;
  isRunning: boolean;
  error: string | null;
  /** Run was stopped by the user / dropped connection — a neutral notice, not an error. */
  interrupted?: boolean;
  /** Set while the run is paused on a sandbox-policy approval gate. */
  pendingApproval?: PendingApproval | null;
  /** Resolve the `pendingApproval` gate. */
  onApprovalDecision?: (decision: 'approve' | 'reject', note?: string) => void;
  sendMessage: (text: string) => void;
  /** Cancels the in-flight turn (aborts the SSE stream and asks the server to
   * interrupt an in-sandbox run). */
  onStop: () => void;
}

/** Live counterpart to `../agent/chat-thread.tsx`, for the `Agent` (AG-UI/streaming) flow. */
export function AgentThread({
  backendUrl,
  agent,
  sessionId,
  onOpenSandboxSettings,
  messages,
  trace,
  pastTraces,
  narrationForTurn,
  isRunning,
  error,
  interrupted,
  pendingApproval,
  onApprovalDecision,
  sendMessage,
  onStop,
}: AgentThreadProps) {
  const files = useSessionFiles({ backendUrl, sessionId });
  const [filesOpen, setFilesOpen] = useState(false);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [justCompletedUpload, setJustCompletedUpload] = useState(false);
  const wasProcessingRef = useRef(false);

  useEffect(() => {
    if (!sessionId) {
      setSession(null);
      return;
    }
    let live = true;
    fetchSession(backendUrl, sessionId)
      .then((s) => {
        if (live) setSession(s);
      })
      .catch(() => {
        /* non-critical — the drawer just omits the start time */
      });
    return () => {
      live = false;
    };
  }, [backendUrl, sessionId]);

  useEffect(() => {
    const wasProcessing = wasProcessingRef.current;
    wasProcessingRef.current = files.isProcessing;
    if (wasProcessing && !files.isProcessing) {
      setJustCompletedUpload(true);
      const t = window.setTimeout(() => setJustCompletedUpload(false), UPLOAD_COMPLETE_TITLE_MS);
      return () => window.clearTimeout(t);
    }
    return undefined;
  }, [files.isProcessing]);

  useBlurStatusTitle(
    files.isProcessing || justCompletedUpload,
    files.isProcessing ? '● Embedding…' : justCompletedUpload ? '✓ Embedding complete' : null,
  );

  return (
    <main className="flex min-w-0 flex-1 flex-col bg-background">
      <header className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <Badge variant="accent">Agent</Badge>
          <span className="truncate font-mono text-xs text-muted-foreground">{agent.display_name}</span>
        </div>
        <div className="flex items-center gap-1">
          <FilesButton count={files.count} disabled={!sessionId} onClick={() => setFilesOpen(true)} />
          <Button variant="ghost" size="icon" aria-label="Sandbox settings" onClick={onOpenSandboxSettings}>
            <Settings className="size-4" />
          </Button>
        </div>
      </header>

      <AgentMessageList
        messages={messages}
        trace={trace}
        pastTraces={pastTraces}
        narrationForTurn={narrationForTurn}
        isRunning={isRunning}
        error={error}
        interrupted={interrupted}
      />

      {pendingApproval && onApprovalDecision && (
        <ApprovalPrompt
          approval={pendingApproval}
          disabled={isRunning}
          onDecide={onApprovalDecision}
        />
      )}

      <Composer
        disabled={isRunning || !sessionId || files.isProcessing || !!pendingApproval}
        isRunning={isRunning}
        onStop={onStop}
        onSend={sendMessage}
        backendUrl={backendUrl}
        sessionId={sessionId}
        leftSlot={sessionId ? <ComposerModelPicker backendUrl={backendUrl} sessionId={sessionId} /> : undefined}
        onAddFiles={files.addFiles}
        onFilesAdded={() => setFilesOpen(true)}
      />

      <FilesDrawer
        backendUrl={backendUrl}
        files={files}
        session={session}
        open={filesOpen}
        onOpenChange={setFilesOpen}
      />
    </main>
  );
}
