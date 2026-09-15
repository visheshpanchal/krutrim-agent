import type { Message } from '@ag-ui/client';
import { describe, expect, it } from 'vitest';

import { messageText } from '../src/hooks/use-agent-stream';
import { deriveAssistantTurn } from '../src/utils/render-payload';

function userMsg(content: string): Message {
  return { id: 'u1', role: 'user', content };
}

function assistantMsg(content: Message['content']): Message {
  return { id: 'a1', role: 'assistant', content };
}

describe('messageText', () => {
  it('returns a plain string message unchanged', () => {
    expect(messageText(assistantMsg('hello'))).toBe('hello');
  });

  it('concatenates the text parts of an array-content message', () => {
    const content = [
      { type: 'text', text: 'hello ' },
      { type: 'image', url: 'ignored.png' },
      { type: 'text', text: 'world' },
    ] as unknown as Message['content'];
    expect(messageText(assistantMsg(content))).toBe('hello world');
  });

  it('returns an empty string for a message with no content', () => {
    expect(messageText(assistantMsg(undefined))).toBe('');
  });
});

describe('deriveAssistantTurn', () => {
  it('returns an empty turn when there is no assistant message yet', () => {
    const turn = deriveAssistantTurn([userMsg('hi')], null, 'Agent', { finished: false });
    expect(turn).toEqual({ narration: '', output: null });
  });

  it('uses the default splitter (unregistered screen key) to wrap the latest assistant text as markdown output', () => {
    const messages = [userMsg('hi'), assistantMsg('# Report\n\nDone.')];
    const turn = deriveAssistantTurn(messages, 'not-a-registered-key', 'My Agent', { finished: true });
    expect(turn.narration).toBe('');
    expect(turn.output).toEqual({ kind: 'markdown', title: 'My Agent', content: '# Report\n\nDone.' });
  });

  it('skips a tool-call-only assistant turn (no prose) and uses an earlier one with text', () => {
    const messages = [
      assistantMsg('The real answer.'),
      assistantMsg(''), // tool-call-only turn: empty text
    ];
    const turn = deriveAssistantTurn(messages, null, 'Agent', { finished: true });
    expect(turn.output).toMatchObject({ content: 'The real answer.' });
  });

  it('produces no output when the latest assistant text is only scaffolding', () => {
    const messages = [assistantMsg('<thinking>\n</thinking>')];
    const turn = deriveAssistantTurn(messages, null, 'Agent', { finished: false });
    expect(turn.output).toBeNull();
  });
});
