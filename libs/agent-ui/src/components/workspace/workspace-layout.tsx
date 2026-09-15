import { useEffect, useMemo, useRef, useState } from 'react';
import type { Agent } from '@krutrim_agent/shared-types';

import { useAgentChat, useAgentHistory, useChat, useChatStream, useUrlSync, useWorkspace } from '../../hooks';
import { getScreen, getTurnSplitter } from '../../screens/registry';
import type { ScreenContext } from '../../screens/types';
import { clamp, deriveAssistantTurn } from '../../utils';
import { SandboxSettingsPanel, type SandboxSettingsTarget } from '../settings/sandbox-settings-panel';
import { OutputPanel } from './output-panel';
import { ResizeHandle } from './resize-handle';
import { WorkspaceRail } from './workspace-rail';

const OUTPUT_MIN_WIDTH = 520;
const OUTPUT_MAX_WIDTH = 920;
const OUTPUT_DEFAULT_WIDTH = 420;

/**
 * The 3-column workspace shell (workspace rail / centre / output) — shared by
 * every screen, not just agents. The rail is a `Project -> (Agent | Chat) ->
 * Session` tree; the centre and the output panel are supplied by the **screen**
 * resolved from what's selected — `getScreen('home' | 'chat' | <agent_key>)`
 * (see `../../screens/`). This component owns every hook and hands each screen
 * the slice of state it needs via `ScreenContext`.
 */
interface WorkspaceLayoutProps {
  /** URL of the Python backend. */
  backendUrl: string;
}

export function WorkspaceLayout({ backendUrl }: WorkspaceLayoutProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [outputCollapsed, setOutputCollapsed] = useState(true);
  const [outputWidth, setOutputWidth] = useState(OUTPUT_DEFAULT_WIDTH);
  const [sandboxSettingsOpen, setSandboxSettingsOpen] = useState(false);

  const workspace = useWorkspace({ backendUrl });
  const chat = useChat({ backendUrl });
  const chatStream = useChatStream({ backendUrl });

  // Keeps the address bar in step with the open chat/agent + session.
  useUrlSync({ workspace, chat });

  const allChats = [...workspace.standaloneChats, ...Object.values(workspace.chatsByProject).flat()];
  const activeChat = chat.activeChatId ? (allChats.find((c) => c.chat_id === chat.activeChatId) ?? null) : null;

  const selection = workspace.selection;
  let activeAgent: Agent | null = null;
  let activeAgentProjectId: string | null = null;
  if (selection?.kind === 'agent') {
    for (const project of workspace.projects) {
      const found = workspace.agentsByProject[project.project_id]?.find((a) => a.agent_id === selection.agentId);
      if (found) {
        activeAgent = found;
        activeAgentProjectId = project.project_id;
        break;
      }
    }
  }

  const activeSession = chat.sessions.find((s) => s.session_id === chat.activeSessionId) ?? null;

  const activeAgentSessionId = selection?.kind === 'agent' ? selection.sessionId : null;
  // The Agent flow is a pure live stream with no store-backed history, so on a
  // page refresh the message list starts empty — load the persisted turns and
  // seed the stream with them (see `useAgentHistory`).
  const agentHistory = useAgentHistory({
    backendUrl,
    sessionId: activeAgent ? activeAgentSessionId : null,
  });
  // Only bind the streaming client once history for THIS session has loaded: the
  // internal `HttpAgent` is memoised on `sessionId` and seeded once, so binding
  // early would build it empty and ignore the late history.
  const historyReady =
    !!activeAgent && !!activeAgentSessionId && agentHistory.loadedSessionId === activeAgentSessionId;
  const agentChat = useAgentChat({
    backendUrl,
    agentId: activeAgent?.agent_id ?? '',
    sessionId: historyReady ? activeAgentSessionId : null,
    initialMessages: agentHistory.messages,
    // Seed the per-turn activity blocks from history: the last finished turn's
    // trace becomes the live `trace`, everything before it `pastTraces`.
    initialTrace: agentHistory.tracesByTurn.at(-1) ?? [],
    initialPastTraces: agentHistory.tracesByTurn.slice(0, -1),
  });

  // Which screen fills the centre + output columns.
  const screenKey =
    selection?.kind === 'agent'
      ? (activeAgent?.agent_key ?? 'default')
      : selection?.kind === 'chat'
        ? 'chat'
        : 'home';
  const screen = getScreen(screenKey);
  const isAgentScreen = selection?.kind === 'agent';
  const isChatScreen = screenKey === 'chat';
  // Both agent-type screens and chat can produce canvas output now — chat
  // only actually populates it for a turn carrying the `===OUTPUT===` marker
  // (see `chat-split.ts`); an ordinary short answer leaves `outputPayload`
  // `null` and the panel shows its empty state.
  const canvasCapable = isAgentScreen || isChatScreen;

  // The latest assistant turn is divided by the screen's own splitter (see
  // `screens/<key>/` — `research` splits on `===FINAL_REPORT===`) into
  // `narration` (middle work-log column) and `output` (the output panel).
  // `turnFinished` gates the fallback where a marker-less turn that *ended
  // normally* is taken as the finished output — while streaming, or after a Stop
  // / a reload of a stopped turn, its text stays entirely in the work log
  // instead of masquerading as a finished answer. (`lastAssistantInterrupted`
  // can read stale after a later successful turn, but that turn carries the
  // marker, so the split is correct regardless.)
  const turnFinished =
    !agentChat.isRunning &&
    !agentChat.interrupted &&
    !agentChat.pendingApproval &&
    !agentHistory.lastAssistantInterrupted;
  const assistantTurn = deriveAssistantTurn(agentChat.messages, screenKey, activeAgent?.display_name ?? '', {
    finished: turnFinished,
  });
  // Chat's own assistant-turn split — `chatSplitTurn`'s fallback (no marker
  // found) always returns `output: null` regardless of `finished`, so this
  // never needs the agent path's `turnFinished` gating.
  const chatAssistantTurn = isChatScreen
    ? deriveAssistantTurn(chatStream.messages, 'chat', activeChat?.display_name ?? 'Chat', {
        finished: !chatStream.isRunning,
      })
    : { narration: '', output: null };
  const outputPayload = isAgentScreen ? assistantTurn.output : isChatScreen ? chatAssistantTurn.output : null;
  // The screen currently driving the output panel's busy/auto-reveal state.
  const currentIsRunning = isAgentScreen ? agentChat.isRunning : isChatScreen ? chatStream.isRunning : false;
  // The current (last) turn's activity trace. Live while a run is in flight or
  // once it has produced steps; otherwise the last turn's steps rebuilt from
  // the checkpoint (`useAgentHistory` — tool calls only; steps aren't
  // persisted). `pastTraces` (one entry per earlier user turn) comes straight
  // from the stream, already seeded from history.
  const trace =
    agentChat.isRunning || agentChat.trace.length > 0
      ? agentChat.trace
      : (agentHistory.tracesByTurn.at(-1) ?? []);

  // Splits one assistant turn's raw text into just its middle-column working
  // narration, via the screen's own turn splitter (research → `===FINAL_REPORT===`).
  const narrationForTurn = useMemo(() => {
    const split = getTurnSplitter(screenKey);
    const title = activeAgent?.display_name ?? '';
    return (assistantText: string, isLastTurn: boolean) =>
      split(assistantText, { finished: !isLastTurn || turnFinished, title }).narration;
  }, [screenKey, activeAgent?.display_name, turnFinished]);

  const screenCtx: ScreenContext = {
    backendUrl,
    onOpenSandboxSettings: () => setSandboxSettingsOpen(true),
    agent: activeAgent
      ? {
          agent: activeAgent,
          sessionId: activeAgentSessionId,
          messages: agentChat.messages,
          trace,
          pastTraces: agentChat.pastTraces,
          narrationForTurn,
          isRunning: agentChat.isRunning,
          error: agentChat.error,
          interrupted: agentChat.interrupted,
          pendingApproval: agentChat.pendingApproval,
          sendMessage: agentChat.sendMessage,
          respondToApproval: agentChat.respondToApproval,
          onStop: agentChat.stop,
        }
      : undefined,
    chat:
      screenKey === 'chat'
        ? {
            activeChat,
            sessions: chat.sessions,
            activeSessionId: chat.activeSessionId,
            historySessionId: chat.historySessionId,
            messages: chatStream.messages,
            reasoningByMessageId: chatStream.reasoningByMessageId,
            isLoading: chat.isLoading,
            isSending: chatStream.isRunning,
            error: chat.error ?? chatStream.error,
            onSelectSession: chat.selectSession,
            onNewSession: chat.startNewSession,
            onSend: chatStream.sendMessage,
            onEnsureSession: chat.ensureSession,
            pendingModelId: chat.pendingModelId,
            onChangeModel: (modelId) => {
              if (activeChat) {
                workspace.changeChatModel(activeChat.chat_id, modelId);
              } else {
                chat.setPendingModelId(modelId);
              }
            },
          }
        : undefined,
  };
  const ScreenCenter = screen.Center;

  // Reveal the output explorer automatically once there's assistant output or a
  // run finishes. Never auto-closes; a manual toggle is respected.
  const wasRunningRef = useRef(false);
  useEffect(() => {
    const justFinished = wasRunningRef.current && !currentIsRunning;
    wasRunningRef.current = currentIsRunning;
    if (outputPayload && (justFinished || currentIsRunning)) setOutputCollapsed(false);
  }, [currentIsRunning, outputPayload]);

  // A fresh session starts with the explorer tucked away again.
  useEffect(() => {
    setOutputCollapsed(true);
  }, [activeAgentSessionId, chat.historySessionId]);

  // Agent-owned session details aren't tracked here yet (the AG-UI client that will actually
  // need them is a later pass) — so an Agent's sandbox settings only cover its own
  // owner-level policy for now, not a specific session's, even though `selection.sessionId`
  // exists. `SessionPolicySection` is skipped in that case (see `SandboxSettingsPanel`).
  let sandboxTarget: SandboxSettingsTarget | null = null;
  if (activeAgent && activeAgentProjectId) {
    sandboxTarget = { kind: 'agent', agent: activeAgent, projectId: activeAgentProjectId };
  } else if (activeChat) {
    sandboxTarget = { kind: 'chat', chat: activeChat };
  }
  const sessionForPanel = sandboxTarget?.kind === 'chat' ? activeSession : null;
  const siblingSessionsForPanel = sandboxTarget?.kind === 'chat' ? chat.sessions : [];

  return (
    <div className="flex h-screen bg-background text-foreground">
      <WorkspaceRail
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
        backendUrl={backendUrl}
        workspace={workspace}
        onOpenChatSession={chat.selectChat}
      />

      <ScreenCenter {...screenCtx} />

      {!outputCollapsed && (
        <ResizeHandle
          onResize={(deltaX) => setOutputWidth((w) => clamp(w - deltaX, OUTPUT_MIN_WIDTH, OUTPUT_MAX_WIDTH))}
          onReset={() => setOutputWidth(OUTPUT_DEFAULT_WIDTH)}
        />
      )}
      <OutputPanel
        collapsed={outputCollapsed}
        onToggle={() => setOutputCollapsed((v) => !v)}
        width={outputWidth}
        screen={screen}
        canvasCapable={canvasCapable}
        payload={outputPayload}
        busy={currentIsRunning}
        session={
          isAgentScreen && activeAgentSessionId
            ? { backendUrl, sessionId: activeAgentSessionId, sendMessage: agentChat.sendMessage }
            : isChatScreen && chat.historySessionId
              ? { backendUrl, sessionId: chat.historySessionId, sendMessage: chatStream.sendMessage }
              : undefined
        }
      />

      {sandboxSettingsOpen && sandboxTarget && (
        <SandboxSettingsPanel
          backendUrl={backendUrl}
          target={sandboxTarget}
          session={sessionForPanel}
          siblingSessions={siblingSessionsForPanel}
          onClose={() => setSandboxSettingsOpen(false)}
        />
      )}
    </div>
  );
}
