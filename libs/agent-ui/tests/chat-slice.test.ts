import { describe, expect, it } from 'vitest';
import type { ChatApiMessage, SessionInfo } from '@krutrim_agent/shared-types';

import chatReducer, {
  createNewChatSession,
  ensureChatSession,
  openChat,
  openSession,
  setBackendUrl,
  setPendingChatModelId,
  startNewChat,
  syncResolvedChat,
  type ChatState,
} from '../src/store/chat-slice';

// RTK's createAsyncThunk exposes `.pending`/`.fulfilled`/`.rejected` action
// creators directly on the thunk, so extraReducers can be exercised with
// real, correctly-typed actions without dispatching anything or mocking the
// `../api` network layer — that layer already has its own coverage in
// http-client.test.ts.

function session(overrides: Partial<SessionInfo> = {}): SessionInfo {
  return {
    session_id: 's1',
    user_id: 'u1',
    owner_type: 'chat',
    owner_id: 'c1',
    project_id: null,
    display_name: null,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    sandbox_sharing: 'isolated',
    attached_to_session_id: null,
    ...overrides,
  } as SessionInfo;
}

function message(overrides: Partial<ChatApiMessage> = {}): ChatApiMessage {
  return { role: 'user', content: 'hi', ...overrides };
}

const initial: ChatState = chatReducer(undefined, { type: '@@init' });

describe('chat-slice plain reducers', () => {
  it('setBackendUrl stores the backend URL', () => {
    const state = chatReducer(initial, setBackendUrl('http://backend.example'));
    expect(state.backendUrl).toBe('http://backend.example');
  });

  it('startNewChat resets the active chat/session/messages and bumps newChatNonce', () => {
    const loaded: ChatState = {
      ...initial,
      activeChatId: 'c1',
      activeSessionId: 's1',
      historySessionId: 's1',
      sessions: [session()],
      messages: [message()],
      error: 'boom',
      newChatNonce: 2,
    };
    const state = chatReducer(loaded, startNewChat());
    expect(state.activeChatId).toBeNull();
    expect(state.activeSessionId).toBeNull();
    expect(state.historySessionId).toBeNull();
    expect(state.sessions).toEqual([]);
    expect(state.messages).toEqual([]);
    expect(state.error).toBeNull();
    expect(state.newChatNonce).toBe(3);
  });

  it('setPendingChatModelId stores or clears the pending model id', () => {
    let state = chatReducer(initial, setPendingChatModelId('openrouter:model-x'));
    expect(state.pendingModelId).toBe('openrouter:model-x');
    state = chatReducer(state, setPendingChatModelId(null));
    expect(state.pendingModelId).toBeNull();
  });
});

describe('chat-slice openChat', () => {
  it('marks isLoading and clears any previous error while pending', () => {
    const state = chatReducer(
      { ...initial, error: 'previous error' },
      openChat.pending('reqId', { chatId: 'c1' }),
    );
    expect(state.isLoading).toBe(true);
    expect(state.error).toBeNull();
  });

  it('adopts the resolved chat/session/messages on fulfilled and clears the pending model id', () => {
    const sessions = [session({ session_id: 's1' })];
    const messages = [message()];
    const state = chatReducer(
      { ...initial, isLoading: true, pendingModelId: 'openrouter:x' },
      openChat.fulfilled({ chatId: 'c1', sessions, sessionId: 's1', messages }, 'reqId', { chatId: 'c1' }),
    );
    expect(state.isLoading).toBe(false);
    expect(state.activeChatId).toBe('c1');
    expect(state.sessions).toBe(sessions);
    expect(state.activeSessionId).toBe('s1');
    expect(state.historySessionId).toBe('s1');
    expect(state.messages).toBe(messages);
    expect(state.pendingModelId).toBeNull();
  });

  it('records the rejection reason and clears isLoading on rejected', () => {
    const state = chatReducer(
      { ...initial, isLoading: true },
      openChat.rejected(new Error('network'), 'reqId', { chatId: 'c1' }, 'Failed to open chat.'),
    );
    expect(state.isLoading).toBe(false);
    expect(state.error).toBe('Failed to open chat.');
  });
});

describe('chat-slice openSession', () => {
  it('moves activeSessionId immediately on pending, but leaves historySessionId until fulfilled', () => {
    const state = chatReducer({ ...initial, activeSessionId: 's1', historySessionId: 's1' }, openSession.pending('reqId', 's2'));
    expect(state.activeSessionId).toBe('s2');
    expect(state.historySessionId).toBe('s1');
    expect(state.isLoading).toBe(true);
  });

  it('advances historySessionId and messages on fulfilled', () => {
    const messages = [message({ content: 'loaded' })];
    const state = chatReducer(
      { ...initial, isLoading: true },
      openSession.fulfilled({ sessionId: 's2', messages }, 'reqId', 's2'),
    );
    expect(state.isLoading).toBe(false);
    expect(state.historySessionId).toBe('s2');
    expect(state.messages).toBe(messages);
  });
});

describe('chat-slice syncResolvedChat', () => {
  it('adopts the resolved ids/sessions/messages and clears the pending model id on fulfilled', () => {
    const sessions = [session()];
    const messages = [message()];
    const state = chatReducer(
      { ...initial, pendingModelId: 'openrouter:x' },
      syncResolvedChat.fulfilled(
        { chatId: 'c1', sessionId: 's1', sessions, messages },
        'reqId',
        { chatId: 'c1', sessionId: 's1' },
      ),
    );
    expect(state.activeChatId).toBe('c1');
    expect(state.activeSessionId).toBe('s1');
    expect(state.historySessionId).toBe('s1');
    expect(state.sessions).toBe(sessions);
    expect(state.messages).toBe(messages);
    expect(state.pendingModelId).toBeNull();
  });
});

describe('chat-slice ensureChatSession', () => {
  it('folds a newly-created session into `sessions` exactly once', () => {
    const newSession = session({ session_id: 's-new' });
    const once = chatReducer(
      initial,
      ensureChatSession.fulfilled({ chatId: 'c1', sessionId: 's-new', session: newSession }, 'reqId', undefined),
    );
    expect(once.sessions).toEqual([newSession]);

    // A second fulfilled action for the same session must not duplicate it.
    const twice = chatReducer(
      once,
      ensureChatSession.fulfilled({ chatId: 'c1', sessionId: 's-new', session: newSession }, 'reqId', undefined),
    );
    expect(twice.sessions).toEqual([newSession]);
  });

  it('is a no-op on `sessions` when no new session was created (already had one)', () => {
    const state = chatReducer(
      initial,
      ensureChatSession.fulfilled({ chatId: 'c1', sessionId: 's1' }, 'reqId', undefined),
    );
    expect(state.activeChatId).toBe('c1');
    expect(state.activeSessionId).toBe('s1');
    expect(state.sessions).toEqual([]);
  });
});

describe('chat-slice createNewChatSession', () => {
  it('appends the new session, selects it, and clears messages', () => {
    const newSession = session({ session_id: 's-new' });
    const state = chatReducer(
      { ...initial, sessions: [session({ session_id: 's-old' })], messages: [message()], newChatNonce: 0 },
      createNewChatSession.fulfilled({ chatId: 'c1', session: newSession }, 'reqId', undefined),
    );
    expect(state.sessions.map((s) => s.session_id)).toEqual(['s-old', 's-new']);
    expect(state.activeSessionId).toBe('s-new');
    expect(state.historySessionId).toBe('s-new');
    expect(state.messages).toEqual([]);
    expect(state.newChatNonce).toBe(1);
  });
});
