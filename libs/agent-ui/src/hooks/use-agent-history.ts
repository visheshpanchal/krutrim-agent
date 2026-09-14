import { useEffect, useState } from 'react';
import type { Message } from '@ag-ui/client';
import type { ChatApiMessage } from '@krutrim_agent/shared-types';

import { fetchSessionMessages } from '../api/sessions';
import type { TraceStep } from './use-agent-stream';

/**
 * Loads an **Agent** session's persisted history once, on mount / session
 * switch, so a page refresh doesn't wipe the conversation.
 *
 * The Agent flow (`use-agent-chat.ts`) is a pure live AG-UI stream — unlike the
 * Chat flow it has no store-backed history — so without this the message list
 * starts empty on every reload. `GET /api/sessions/{id}/messages` reads the
 * session's LangGraph checkpoint and returns the visible turns plus the tool
 * calls each made; this hook turns that into the two things the shell needs:
 *
 * - `messages` — user + non-empty assistant turns, to seed the `HttpAgent`;
 * - `trace` — the tool calls, rebuilt as `TraceStep[]` so the work-log panel
 *   (`AgentActivity`) is populated on reload, not just during a live run.
 *
 * `loadedSessionId` is the id the returned data actually belongs to — the
 * caller gates the `HttpAgent` (memoised on `sessionId`) on
 * `loadedSessionId === sessionId` so it is only built once its seed is ready,
 * and never re-seeded with a stale session's turns.
 */

const EMPTY_HISTORY = {
  sessionId: null,
  messages: [] as Message[],
  trace: [] as TraceStep[],
  tracesByTurn: [] as TraceStep[][],
  lastAssistantInterrupted: false,
};

function toAguiMessage(message: ChatApiMessage, index: number): Message {
  return { id: `history-${index}`, role: message.role, content: message.content };
}

/** Rebuild the activity trace from the tool calls the checkpoint recorded,
 * bucketed per conversation turn — one `TraceStep[]` per user message, in
 * order. Steps / reasoning aren't persisted, so only `tool_call` rows come
 * back. The middle column pairs `tracesByTurn[i]` with the i-th user turn so a
 * reloaded conversation shows each turn's own activity, not one flat list. */
function reconstructTracesByTurn(raw: ChatApiMessage[]): TraceStep[][] {
  const turns: TraceStep[][] = [];
  let current: TraceStep[] | null = null;
  let i = 0;
  for (const message of raw) {
    if (message.role === 'user') {
      current = [];
      turns.push(current);
      continue;
    }
    if (!current) {
      current = [];
      turns.push(current);
    }
    for (const call of message.tool_calls ?? []) {
      current.push({
        id: call.id || `history-tc-${i}`,
        kind: 'tool_call',
        label: call.name,
        detail: call.result != null && call.result !== '' ? `${call.args}\n\n→ ${call.result}` : call.args,
        status: 'finished',
        timestamp: i,
      });
      i += 1;
    }
  }
  return turns;
}

export interface UseAgentHistoryResult {
  messages: Message[];
  /** The session id `messages` were loaded for, or `null` before the first load resolves. */
  loadedSessionId: string | null;
  /** Tool calls from the checkpoint, as trace steps — feeds `AgentActivity` on reload. */
  trace: TraceStep[];
  /** The same steps split per conversation turn (one entry per user message),
   * so the reloaded thread shows each turn's own activity block. */
  tracesByTurn: TraceStep[][];
  /** The last persisted turn is an assistant turn that was stopped mid-generation
   * (`ChatApiMessage.interrupted`). Its text is a partial work log, not a report —
   * `WorkspaceLayout` uses this to keep it out of the output panel after a reload. */
  lastAssistantInterrupted: boolean;
  isLoading: boolean;
}

export function useAgentHistory({
  backendUrl,
  sessionId,
}: {
  backendUrl: string;
  sessionId: string | null;
}): UseAgentHistoryResult {
  const [state, setState] = useState<{
    sessionId: string | null;
    messages: Message[];
    trace: TraceStep[];
    tracesByTurn: TraceStep[][];
    lastAssistantInterrupted: boolean;
  }>(EMPTY_HISTORY);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!sessionId) {
      setState(EMPTY_HISTORY);
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    fetchSessionMessages(backendUrl, sessionId)
      .then((raw) => {
        if (cancelled) return;
        const last = raw[raw.length - 1];
        const tracesByTurn = reconstructTracesByTurn(raw);
        setState({
          sessionId,
          // Skip empty (tool-call-only) assistant turns in the seed — the tool
          // calls live in `trace`; only turns with prose belong in the thread.
          messages: raw
            .filter((m) => m.role === 'user' || m.content.trim().length > 0)
            .map(toAguiMessage),
          trace: tracesByTurn.flat(),
          tracesByTurn,
          lastAssistantInterrupted: last?.role === 'assistant' && last.interrupted === true,
        });
      })
      .catch(() => {
        // A failed load must not wedge the thread — adopt the id with an empty
        // history so the caller's `loadedSessionId === sessionId` gate opens and
        // the user can still start a turn.
        if (!cancelled) setState({ ...EMPTY_HISTORY, sessionId });
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [backendUrl, sessionId]);

  return {
    messages: state.messages,
    loadedSessionId: state.sessionId,
    trace: state.trace,
    tracesByTurn: state.tracesByTurn,
    lastAssistantInterrupted: state.lastAssistantInterrupted,
    isLoading,
  };
}
