import { Fragment, useEffect, useMemo, useRef } from 'react';
import type { Message } from '@ag-ui/client';
import { ScrollArea } from '@krutrim_agent/ui';

import { messageText, type TraceStep } from '../../hooks/use-agent-stream';
import { Markdown } from '../../components/conversation/markdown';
import { AgentActivity } from './agent-activity';
import { AgentMessageBubble } from './agent-message-bubble';

export interface AgentMessageListProps {
  messages: Message[];
  /** The current (last) turn's step / tool-call / reasoning trace. */
  trace?: TraceStep[];
  /** One finished turn's trace per prior user message, in order — index `i`
   * pairs with the i-th user turn and renders as a collapsed activity row. */
  pastTraces?: TraceStep[][];
  /** Splits one assistant turn's raw text into just its middle-column working
   * narration (per the agent's turn splitter). `''` for agents with no
   * work-log concept. The finished output goes to the output panel instead. */
  narrationForTurn: (assistantText: string, isLastTurn: boolean) => string;
  isRunning: boolean;
  error: string | null;
  /** Run stopped by the user / dropped connection — shown as a neutral notice. */
  interrupted?: boolean;
}

interface Turn {
  user: Message;
  assistantText: string;
}

/** Group the flat AG-UI message list into `user → assistant` turns: every user
 * message starts a turn, and every assistant message's text is appended to the
 * turn in progress (tool-only assistant messages contribute nothing here —
 * their calls live in the trace). */
function groupIntoTurns(messages: Message[]): Turn[] {
  const turns: Turn[] = [];
  for (const message of messages) {
    if (message.role === 'user') {
      turns.push({ user: message, assistantText: '' });
    } else if (message.role === 'assistant' && turns.length > 0) {
      turns[turns.length - 1].assistantText += messageText(message);
    }
  }
  return turns;
}

/**
 * The middle column is the **conversation work log**: each user question
 * followed by that turn's own activity block (thinking / tool calls / steps)
 * and its working narration. Past turns' activity collapses to a single
 * "Worked for Ns · N steps" row the reader can expand; the live turn stays
 * open. The finished report is never rendered here — it goes to the output
 * panel (via the screen's turn splitter). Auto-scrolls on new messages/trace.
 */
export function AgentMessageList({
  messages,
  trace = [],
  pastTraces = [],
  narrationForTurn,
  isRunning,
  error,
  interrupted,
}: AgentMessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, trace, pastTraces]);

  const turns = useMemo(() => groupIntoTurns(messages), [messages]);
  const lastIdx = turns.length - 1;
  // "thinking…" only until the current turn produces its first trace step or
  // its first assistant text.
  const showThinking = isRunning && trace.length === 0 && !turns[lastIdx]?.assistantText.trim();

  return (
    <ScrollArea ref={scrollRef} className="flex-1 px-5 py-4">
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        {turns.length === 0 && !isRunning && (
          <p className="text-sm text-muted-foreground">Ask this agent something to get started.</p>
        )}

        {turns.map((turn, idx) => {
          const isLast = idx === lastIdx;
          // `pastTraces[i]` covers every turn before the current one; the last
          // turn's trace is the live `trace`.
          const turnTrace = idx < pastTraces.length ? pastTraces[idx] : trace;
          const turnRunning = isLast && isRunning;
          const narration = narrationForTurn(turn.assistantText, isLast);

          return (
            <Fragment key={turn.user.id}>
              <AgentMessageBubble message={turn.user} />
              {(turnTrace.length > 0 || turnRunning) && (
                <AgentActivity trace={turnTrace} isRunning={turnRunning} />
              )}
              {narration && (
                <Markdown className="w-full max-w-[85%] text-muted-foreground">{narration}</Markdown>
              )}
            </Fragment>
          );
        })}

        {showThinking && <p className="font-mono text-xs text-muted-foreground">thinking…</p>}
        {interrupted && !error && (
          <p className="rounded-md border border-border bg-muted/40 p-2 text-xs text-muted-foreground">
            You stopped the response. Ask a follow-up or send a new message to continue.
          </p>
        )}
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
            {error}
          </p>
        )}
      </div>
    </ScrollArea>
  );
}
