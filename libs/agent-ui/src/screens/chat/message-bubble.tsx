import type { Message } from '@ag-ui/client';

import { messageText, type ReasoningEntry } from '../../hooks/use-agent-stream';
import { Markdown } from '../../components/conversation/markdown';
import { chatSplitTurn } from './chat-split';
import { ThinkingDisclosure } from './thinking-disclosure';

export interface MessageBubbleProps {
  message: Message;
  reasoning?: ReasoningEntry;
  streaming?: boolean;
}

/** Shown in place of an empty narration when a deliverable's marker was
 * emitted with nothing (or only whitespace) before it. */
const DELIVERABLE_ONLY_FALLBACK = 'See the output panel for the full result.';

export function MessageBubble({ message, reasoning, streaming }: MessageBubbleProps) {
  const rawText = messageText(message);
  if (message.role === 'user') {
    return (
      <div className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
        {rawText}
      </div>
    );
  }

  // A deliverable's full content is routed to the output panel (see
  // `chat-split.ts`) — the bubble only ever shows the narration before the
  // `===OUTPUT===` marker, never the duplicated report body.
  const split = chatSplitTurn(rawText, { finished: true, title: '' });
  const text = split.output ? split.narration || DELIVERABLE_ONLY_FALLBACK : rawText;

  if (!text && !reasoning) return null;

  return (
    <div className="flex max-w-[85%] flex-col items-start">
      {reasoning && <ThinkingDisclosure reasoning={reasoning} />}
      {text && (
        <div className="rounded-lg bg-secondary px-3 py-2 text-sm text-foreground">
          {/* Rendered as markdown both while tokens stream in (re-parsed each
              token) and when a finished answer is loaded whole from history. */}
          <Markdown>{text}</Markdown>
          {streaming && (
            <span className="mt-1 inline-block h-4 w-0.5 animate-pulse bg-current align-text-bottom" />
          )}
        </div>
      )}
    </div>
  );
}
