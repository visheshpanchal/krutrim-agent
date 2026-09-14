import type { Agent, AgentMeta, Chat, ChatApiMessage, Project, SessionInfo } from '@krutrim_agent/shared-types';

/**
 * Store shape, declared independently of the slice modules so nothing in
 * `./chat-slice` / `./workspace-slice` has to import back from `./store` just to
 * type a thunk's `getState`. `store.ts` composes the real reducers and asserts
 * (at compile time) that its runtime shape still matches `RootState`.
 */

/**
 * What the sidebar tree currently has open in the center pane. `'chat'`
 * selections don't carry a `sessionId` here — the `chat` slice
 * (`./chat-slice.ts`) owns which session of a chat is active, since it's
 * also responsible for loading that session's messages. `'agent'`
 * selections carry their own `sessionId` because nothing else tracks it yet
 * (the AG-UI streaming client that will actually use it is a later pass).
 */
export type WorkspaceSelection =
  | { kind: 'chat'; chatId: string }
  | { kind: 'agent'; agentId: string; sessionId: string | null };

export interface ChatState {
  backendUrl: string;
  sessions: SessionInfo[];
  activeChatId: string | null;
  /** The session the switcher currently points at — updated immediately on select. */
  activeSessionId: string | null;
  /** The session `messages` actually belong to — advances only once that
   * session's history has loaded. `useChatStream` / `useSessionFiles` key off
   * this so the thread and the file list never show two different sessions. */
  historySessionId: string | null;
  /** History for `historySessionId`, loaded on open — the live turn streams on top of this. */
  messages: ChatApiMessage[];
  isLoading: boolean;
  error: string | null;
  /** Bumped by `startNewChat` / `createNewChatSession` so `useChatStream` can
   * tell two successive "new…" actions apart and rebuild its `HttpAgent`. */
  newChatNonce: number;
  /** The composer's model pick for a chat that doesn't exist yet (`activeChatId`
   * is `null`) — `"{provider}:{model}"`, sent as `model_id` on the first message.
   * Once the chat is created the picker switches to `PUT /api/chats/{id}/model`
   * instead, so this is cleared on `openChat` / `syncResolvedChat`. */
  pendingModelId: string | null;
}

export interface WorkspaceState {
  backendUrl: string;
  projects: Project[];
  agentsByProject: Record<string, Agent[]>;
  chatsByProject: Record<string, Chat[]>;
  standaloneChats: Chat[];
  /** Registered agent *profiles* (research/experiment/...) — populates the New Agent picker. */
  agentProfiles: AgentMeta[];
  expandedProjectIds: string[];
  selection: WorkspaceSelection | null;
  isLoading: boolean;
  /** `false` until the first `fetchWorkspace` settles (either way). Lets URL sync
   * tell "still loading" apart from "loaded, and this agent/chat really is gone"
   * so a deep link isn't bounced to `/` before the workspace data arrives. */
  hasLoaded: boolean;
  error: string | null;
}

export interface RootState {
  chat: ChatState;
  workspace: WorkspaceState;
}
