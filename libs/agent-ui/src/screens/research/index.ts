import { AgentScreen } from '../agent';
import type { ScreenModule } from '../types';
import { ResearchRenderer } from './research-renderer';
import { researchSplitTurn } from './research-split';

/** The research agent: the shared agent thread in the middle, a sectioned
 *  report in the output panel, and a `===FINAL_REPORT===` split between the
 *  work-log narration and that report. */
export const researchScreen: ScreenModule = {
  key: 'research',
  displayName: 'Research',
  Center: AgentScreen,
  OutputRenderer: ResearchRenderer,
  turnSplitter: researchSplitTurn,
};
