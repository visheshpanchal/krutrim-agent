import type { Message } from '@ag-ui/client';

import { messageText, type ReasoningEntry } from '../../hooks/use-agent-stream';
import { Markdown } from '../../components/conversation/markdown';
import { ThinkingDisclosure } from './thinking-disclosure';

export interface MessageBubbleProps {
  message: Message;
  reasoning?: ReasoningEntry;
  streaming?: boolean;
}

export function MessageBubble({ message, reasoning, streaming }: MessageBubbleProps) {
  const text = messageText(message);
  if (message.role === 'user') {
    return (
      <div className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
        {text}
      </div>
    );
  }

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
