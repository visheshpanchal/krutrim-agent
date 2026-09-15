import type { ScreenModule } from '../types';
import { chatSplitTurn } from './chat-split';
import { ChatRenderer } from './chat-renderer';
import { ChatScreen } from './chat-screen';

/** The plain (non-agentic) chat flow. `OutputRenderer`/`turnSplitter` only
 * kick in for a turn carrying the `===OUTPUT===` marker (see `chat-split.ts`)
 * — an ordinary short answer never touches the output panel. */
export const chatScreen: ScreenModule = {
  key: 'chat',
  displayName: 'Chat',
  Center: ChatScreen,
  OutputRenderer: ChatRenderer,
  turnSplitter: chatSplitTurn,
};
