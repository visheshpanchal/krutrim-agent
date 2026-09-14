import type { ScreenContext } from '../types';
import { AgentThread } from './agent-thread';

/**
 * The shared centre pane for every agent-type screen — the live AG-UI thread
 * (`AgentThread`). A screen module that needs a different middle column supplies
 * its own `Center` instead of this; `research` and `default` both use this one
 * and differentiate only via `OutputRenderer` / `turnSplitter`.
 */
export function AgentScreen(ctx: ScreenContext) {
  const a = ctx.agent;
  if (!a) return null;
  // The approve/reject gate is only surfaced for the research agent for now.
  const pendingApproval = a.agent.agent_key === 'research' ? a.pendingApproval : null;
  return (
    <AgentThread
      backendUrl={ctx.backendUrl}
      agent={a.agent}
      sessionId={a.sessionId}
      onOpenSandboxSettings={ctx.onOpenSandboxSettings}
      messages={a.messages}
      trace={a.trace}
      pastTraces={a.pastTraces}
      narrationForTurn={a.narrationForTurn}
      isRunning={a.isRunning}
      error={a.error}
      interrupted={a.interrupted}
      pendingApproval={pendingApproval}
      onApprovalDecision={a.respondToApproval}
      sendMessage={a.sendMessage}
      onStop={a.onStop}
    />
  );
}
