import { Provider } from 'react-redux';
import { ThemeProvider } from '@krutrim_agent/ui';
import { ExtensionProvider, type ExtensionHooks } from '@krutrim_agent/extensions';

import { AuthGate } from './components/auth';
import { WorkspaceLayout } from './components/workspace/workspace-layout';
import { store } from './store/store';
import { configureAuth } from './utils/auth-store';

export interface AgentProps {
  /** URL of the Python backend. */
  backendUrl: string;
  /**
   * Security-hook overrides (auth provider, agent-visibility filter) — a
   * consuming app supplies its own here. Omit for the community default
   * (no-op hooks, matching the backend's own no-op defaults exactly). This
   * is the only prop a consuming app needs to fork nothing else in this
   * package for — see `@krutrim_agent/extensions`.
   */
  extensions?: ExtensionHooks;
}

/**
 * Sole top-level product — owns its own Redux `Provider`, `ThemeProvider`,
 * and `ExtensionProvider`. `<AuthGate>` sits between the providers and the
 * shell: it shows the login screen until there's a valid session (unless the
 * backend has auth disabled). The actual 3-column shell (workspace rail /
 * conversation / output) lives in `WorkspaceLayout`.
 */
export function Agent({ backendUrl, extensions }: AgentProps) {
  configureAuth(backendUrl);
  return (
    <Provider store={store}>
      <ThemeProvider>
        <ExtensionProvider hooks={extensions}>
          <AuthGate backendUrl={backendUrl}>
            <WorkspaceLayout backendUrl={backendUrl} />
          </AuthGate>
        </ExtensionProvider>
      </ThemeProvider>
    </Provider>
  );
}
