import { chatScreen } from './chat';
import { DefaultRenderer, defaultScreen, defaultSplitTurn } from './default';
import { homeScreen } from './home';
import { researchScreen } from './research';
import type { ScreenOutputRenderer, ScreenModule, TurnSplitter } from './types';

/** Built-ins are registered eagerly (no side-effect-import ordering / tree-shaking
 *  to worry about). Adding an agent = a `screens/<key>/` folder + one line here. */
const REGISTRY = new Map<string, ScreenModule>(
  [defaultScreen, homeScreen, chatScreen, researchScreen].map((m) => [m.key, m]),
);

/** Register a screen at runtime — an external consumer can add its own agent
 *  type this way before the first render. */
export function registerScreen(module: ScreenModule): void {
  REGISTRY.set(module.key, module);
}

/** The screen for `key` — an `agent_key` (`research`, ...) or a built-in
 *  (`home` / `chat`) — falling back to the `default` screen. */
export function getScreen(key: string | null | undefined): ScreenModule {
  return (key ? REGISTRY.get(key) : undefined) ?? defaultScreen;
}

export function listScreens(): ScreenModule[] {
  return [...REGISTRY.values()];
}

/** The output-panel content renderer for `key` — the screen's own, or the default. */
export function getOutputRenderer(key: string | null | undefined): ScreenOutputRenderer {
  return getScreen(key).OutputRenderer ?? DefaultRenderer;
}

/** The work-log vs. finished-output splitter for `key` — the screen's own, or the default. */
export function getTurnSplitter(key: string | null | undefined): TurnSplitter {
  return getScreen(key).turnSplitter ?? defaultSplitTurn;
}
