import { useEffect, useMemo, useRef, useState } from 'react';
import {
  HttpAgent,
  randomUUID,
  type Message,
  type ResumeEntry,
  type RunAgentParameters,
} from '@ag-ui/client';

import type { PendingApproval, ReasoningEntry, TraceStep } from '../screens/types';
import { authedFetch } from '../utils/http-client';

/**
 * The shared AG-UI streaming client. Both the Agent flow
 * (`POST /agents/{agentId}`, see `use-agent-chat.ts`) and the plain Chat flow
 * (`POST /api/chat`, see `use-chat-stream.ts`) are the same protocol over the
 * same `@ag-ui/client` `HttpAgent` — this hook is that shared core.
 *
 * Extra views on top of `@ag-ui/client`'s message accumulation:
 *
 * - `trace` — low-level step / tool-call / reasoning event stream.
 * - `reasoningByMessageId` — streamed "thinking" text keyed by AG-UI message id.
 * - `interrupted` — the run was stopped by the user / the connection dropped.
 *   That is NOT an error. Aborting the SSE cancels the server run, which folds
 *   the partial assistant turn into the session checkpoint backend-side (see
 *   `krutrim_agent_agui.translator._persist_partial_turn`), so it comes back on
 *   the next history load — there is no client-side persistence here.
 * - `pendingApproval` — the run paused on a sandbox-policy approval gate
 *   (`RUN_FINISHED` with `outcome.type === "interrupt"`). Call
 *   `respondToApproval('approve' | 'reject')` to resume: it re-runs the agent
 *   with `RunAgentInput.resume` set (same URL, same `HttpAgent`), which the
 *   backend feeds in as `Command(resume=...)` — see
 *   `krutrim_agent_agui.translator`.
 */

export type { PendingApproval, ReasoningEntry, TraceStep };

export interface RunStats {
  elapsedMs?: number;
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
}

export interface UseAgentStreamOptions {
  url: string | null;
  interruptUrl?: string | null;
  threadId: string | null;
  initialMessages?: Message[];
  /** The last already-finished turn's activity trace, when seeding from
   * persisted history — becomes the live `trace` until the next `sendMessage`
   * folds it into `pastTraces`. */
  initialTrace?: TraceStep[];
  /** Activity traces for every finished turn *before* the last one, in order —
   * one entry per prior user message. Feeds the per-turn activity blocks on a
   * reloaded conversation. */
  initialPastTraces?: TraceStep[][];
  forwardedProps?: Record<string, unknown>;
  onCustomEvent?: (name: string, value: unknown) => void;
  onRunFinished?: () => void;
}

export interface UseAgentStreamResult {
  messages: Message[];
  trace: TraceStep[];
  reasoningByMessageId: Record<string, ReasoningEntry>;
  runStats: RunStats | null;
  isRunning: boolean;
  error: string | null;
  /** Stopped by the user / dropped connection — show a neutral notice, not an error. */
  interrupted: boolean;
  /** Activity trace for every finished turn before the current one, in order
   * (one entry per prior user message). `trace` is the current turn's. */
  pastTraces: TraceStep[][];
  /** Set while a run is paused on a sandbox-policy approval gate. */
  pendingApproval: PendingApproval | null;
  sendMessage: (text: string) => void;
  /** Resume a run paused on `pendingApproval`. */
  respondToApproval: (decision: 'approve' | 'reject', note?: string) => void;
  stop: () => void;
}

export function messageText(message: Message): string {
  if (typeof message.content === 'string') return message.content;
  if (Array.isArray(message.content)) {
    return message.content
      .map((part) => ('type' in part && part.type === 'text' ? part.text : ''))
      .join('');
  }
  return '';
}

const isAbortError = (msg: string) => /abort|BodyStreamBuffer|cancell?ed|network error/i.test(msg);

function upsertTrace(
  prev: TraceStep[],
  id: string,
  update: Partial<TraceStep> & Pick<TraceStep, 'kind' | 'label' | 'status'>,
): TraceStep[] {
  const existingIndex = prev.findIndex((step) => step.id === id);
  if (existingIndex === -1) {
    return [...prev, { id, timestamp: Date.now(), ...update }];
  }
  const next = [...prev];
  next[existingIndex] = { ...next[existingIndex], ...update };
  return next;
}

function findLastStarted(steps: TraceStep[], kind: TraceStep['kind'], label?: string): TraceStep | undefined {
  for (let i = steps.length - 1; i >= 0; i--) {
    const step = steps[i];
    if (step.kind === kind && step.status === 'started' && (label === undefined || step.label === label)) {
      return step;
    }
  }
  return undefined;
}

export function useAgentStream({
  url,
  interruptUrl,
  threadId,
  initialMessages,
  initialTrace,
  initialPastTraces,
  forwardedProps,
  onCustomEvent,
  onRunFinished,
}: UseAgentStreamOptions): UseAgentStreamResult {
  const [messages, setMessages] = useState<Message[]>([]);
  const [trace, setTrace] = useState<TraceStep[]>(initialTrace ?? []);
  const [pastTraces, setPastTraces] = useState<TraceStep[][]>(initialPastTraces ?? []);
  const [reasoningByMessageId, setReasoningByMessageId] = useState<Record<string, ReasoningEntry>>({});
  const [runStats, setRunStats] = useState<RunStats | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [interrupted, setInterrupted] = useState(false);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);

  const callbacksRef = useRef({ onCustomEvent, onRunFinished });
  callbacksRef.current = { onCustomEvent, onRunFinished };
  const forwardedPropsRef = useRef(forwardedProps);
  forwardedPropsRef.current = forwardedProps;
  const initialMessagesRef = useRef(initialMessages);
  initialMessagesRef.current = initialMessages;
  // Read at (re)seed time only — mirrors `initialMessagesRef`.
  const initialTraceRef = useRef(initialTrace);
  initialTraceRef.current = initialTrace;
  const initialPastTracesRef = useRef(initialPastTraces);
  initialPastTracesRef.current = initialPastTraces;

  const activeReasoningIdRef = useRef<string | null>(null);
  const abortedByUserRef = useRef(false);

  const agent = useMemo(() => {
    if (!url) return null;
    return new HttpAgent({
      url,
      threadId: threadId ?? undefined,
      initialMessages: initialMessagesRef.current?.length ? [...initialMessagesRef.current] : undefined,
      // Send the run stream through the same wrapper as REST — attaches the
      // bearer token and does a one-shot refresh + retry on a 401. Without it
      // the run is unauthenticated and 401s whenever the backend enforces auth.
      fetch: authedFetch,
    });
  }, [url, threadId]);

  useEffect(() => {
    setMessages(agent?.messages ?? []);
    setTrace(initialTraceRef.current ?? []);
    setPastTraces(initialPastTracesRef.current ?? []);
    setReasoningByMessageId({});
    setRunStats(null);
    setError(null);
    setInterrupted(false);
    setPendingApproval(null);
    activeReasoningIdRef.current = null;
    abortedByUserRef.current = false;
    if (!agent) return;

    const bumpReasoning = (id: string | null, patch: (entry: ReasoningEntry) => ReasoningEntry) => {
      const key = id ?? activeReasoningIdRef.current;
      if (!key) return;
      setReasoningByMessageId((prev) => {
        const current = prev[key] ?? { text: '', running: true, startedAt: Date.now() };
        return { ...prev, [key]: patch(current) };
      });
    };

    const { unsubscribe } = agent.subscribe({
      onMessagesChanged: ({ messages: updated }) => setMessages([...updated]),
      onRunErrorEvent: ({ event }) => {
        if (abortedByUserRef.current || isAbortError(event.message)) setInterrupted(true);
        else setError(event.message);
      },
      onRunFinishedEvent: ({ event }) => {
        setInterrupted(false);
        const outcome = (event as { outcome?: { type?: string; interrupts?: unknown[] } }).outcome;
        const raw =
          outcome?.type === 'interrupt' ? outcome.interrupts?.[0] : agent.pendingInterrupts?.[0];
        if (raw) {
          const it = raw as {
            id: string;
            reason?: string;
            toolCallId?: string;
            metadata?: Record<string, unknown>;
          };
          setPendingApproval({
            interruptId: it.id,
            reason: it.reason ?? 'Approval required.',
            toolCallId: it.toolCallId,
            toolName: it.metadata?.tool_name as string | undefined,
            args: it.metadata?.args as Record<string, unknown> | undefined,
          });
          return;
        }
        setPendingApproval(null);
        callbacksRef.current.onRunFinished?.();
      },
      onCustomEvent: ({ event }) => {
        callbacksRef.current.onCustomEvent?.(event.name, event.value);
        if (event.name === 'run_stats' && event.value && typeof event.value === 'object') {
          const v = event.value as { elapsed_ms?: number };
          setRunStats((prev) => ({ ...prev, elapsedMs: v.elapsed_ms }));
        }
        if (event.name === 'token_usage' && event.value && typeof event.value === 'object') {
          const v = event.value as { input_tokens?: number; output_tokens?: number; total_tokens?: number };
          setRunStats((prev) => ({
            ...prev,
            inputTokens: v.input_tokens,
            outputTokens: v.output_tokens,
            totalTokens: v.total_tokens,
          }));
        }
      },

      onReasoningMessageStartEvent: ({ event }) => {
        activeReasoningIdRef.current = event.messageId;
        bumpReasoning(event.messageId, () => ({ text: '', running: true, startedAt: Date.now() }));
        setTrace((prev) => [
          ...prev,
          { id: `reasoning:${event.messageId}`, kind: 'reasoning', label: 'Thinking', status: 'started', timestamp: Date.now() },
        ]);
      },
      onReasoningMessageContentEvent: ({ event, reasoningMessageBuffer }) => {
        bumpReasoning(event.messageId, (entry) => ({ ...entry, text: reasoningMessageBuffer, running: true }));
        setTrace((prev) => {
          const started = findLastStarted(prev, 'reasoning');
          return started
            ? upsertTrace(prev, started.id, { kind: 'reasoning', label: 'Thinking', status: 'started', detail: reasoningMessageBuffer })
            : prev;
        });
      },
      onReasoningMessageEndEvent: ({ event, reasoningMessageBuffer }) => {
        bumpReasoning(event.messageId, (entry) => ({
          ...entry,
          text: reasoningMessageBuffer || entry.text,
          running: false,
          endedAt: Date.now(),
        }));
        activeReasoningIdRef.current = null;
        setTrace((prev) => {
          const started = findLastStarted(prev, 'reasoning');
          return started
            ? upsertTrace(prev, started.id, { kind: 'reasoning', label: 'Thinking', status: 'finished', detail: reasoningMessageBuffer })
            : prev;
        });
      },

      onStepStartedEvent: ({ event }) => {
        setTrace((prev) => [
          ...prev,
          { id: `step:${event.stepName}:${Date.now()}`, kind: 'step', label: event.stepName, status: 'started', timestamp: Date.now() },
        ]);
      },
      onStepFinishedEvent: ({ event }) => {
        setTrace((prev) => {
          const started = findLastStarted(prev, 'step', event.stepName);
          return started ? upsertTrace(prev, started.id, { kind: 'step', label: event.stepName, status: 'finished' }) : prev;
        });
      },
      onToolCallStartEvent: ({ event }) => {
        setTrace((prev) => upsertTrace(prev, event.toolCallId, { kind: 'tool_call', label: event.toolCallName, status: 'started' }));
      },
      onToolCallArgsEvent: ({ event, toolCallBuffer, toolCallName }) => {
        setTrace((prev) =>
          upsertTrace(prev, event.toolCallId, { kind: 'tool_call', label: toolCallName, status: 'started', detail: toolCallBuffer }),
        );
      },
      onToolCallEndEvent: ({ event, toolCallName, toolCallArgs }) => {
        setTrace((prev) =>
          upsertTrace(prev, event.toolCallId, {
            kind: 'tool_call',
            label: toolCallName,
            status: 'finished',
            detail: JSON.stringify(toolCallArgs),
          }),
        );
      },
    });
    return unsubscribe;
  }, [agent]);

  function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || !agent || isRunning) return;

    // The trace on screen belongs to the turn just finished — unless this is
    // the very first message, fold it into `pastTraces` so the new turn starts
    // with a clean activity block and the old one stays as a collapsed row.
    const hadPriorTurn = agent.messages.some((m) => m.role === 'user');
    agent.addMessage({ id: randomUUID(), role: 'user', content: trimmed });
    setMessages([...agent.messages]);
    if (hadPriorTurn) setPastTraces((prev) => [...prev, trace]);
    setTrace([]);
    setReasoningByMessageId({});
    setRunStats(null);
    setIsRunning(true);
    setError(null);
    setInterrupted(false);
    setPendingApproval(null);
    abortedByUserRef.current = false;

    const params: RunAgentParameters = {};
    if (forwardedPropsRef.current) params.forwardedProps = forwardedPropsRef.current;

    agent
      .runAgent(params)
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to run agent.';
        if (abortedByUserRef.current || isAbortError(msg)) setInterrupted(true);
        else setError(msg);
      })
      .finally(() => setIsRunning(false));
  }

  function respondToApproval(decision: 'approve' | 'reject', note?: string) {
    if (!agent || !pendingApproval) return;
    const resume: ResumeEntry[] = [
      {
        interruptId: pendingApproval.interruptId,
        status: decision === 'approve' ? 'resolved' : 'cancelled',
        payload: note ? { note } : undefined,
      },
    ];
    setPendingApproval(null);
    setIsRunning(true);
    setError(null);
    setInterrupted(false);
    abortedByUserRef.current = false;

    agent
      .runAgent({ resume })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to resume agent.';
        if (abortedByUserRef.current || isAbortError(msg)) setInterrupted(true);
        else setError(msg);
      })
      .finally(() => setIsRunning(false));
  }

  function stop() {
    if (!isRunning) return;
    abortedByUserRef.current = true;
    // Aborting the SSE disconnects the server run — the backend folds the
    // partial assistant turn into the checkpoint on cancel.
    agent?.abortRun();
    setIsRunning(false);
    setInterrupted(true);
    if (interruptUrl) {
      void authedFetch(interruptUrl, { method: 'POST' }).catch(() => undefined);
    }
  }

  return {
    messages,
    trace,
    pastTraces,
    reasoningByMessageId,
    runStats,
    isRunning,
    error,
    interrupted,
    pendingApproval,
    sendMessage,
    respondToApproval,
    stop,
  };
}
