import { AgentScreen } from '../agent';
import type { ScreenModule } from '../types';
import { DefaultRenderer } from './default-renderer';
import { defaultSplitTurn } from './default-split';

export { DefaultRenderer } from './default-renderer';
export { defaultSplitTurn } from './default-split';

/** Fallback screen for any agent type that hasn't registered its own module. */
export const defaultScreen: ScreenModule = {
  key: 'default',
  displayName: 'Agent',
  Center: AgentScreen,
  OutputRenderer: DefaultRenderer,
  turnSplitter: defaultSplitTurn,
};
