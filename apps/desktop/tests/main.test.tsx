import { screen } from '@testing-library/dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Same reasoning as apps/web/tests/app.test.tsx: `<Agent>` is the whole
// product shell, so stub it to keep this a focused smoke test of the
// renderer entry point's own wiring (mounting into #root, backend URL).
vi.mock('@krutrim_agent/agent-ui', () => ({
  Agent: ({ backendUrl }: { backendUrl: string }) => <div data-testid="agent-stub">{backendUrl}</div>,
}));

// `backendUrl` is computed once at module load from `import.meta.env`, so
// each test needs its own fresh module instance (`resetModules`) to pick up
// a re-stubbed env var.
beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('desktop renderer entry (src/renderer/main.tsx)', () => {
  it('mounts the Agent shell into #root with the default backend URL', async () => {
    document.body.innerHTML = '<div id="root"></div>';

    // The module renders as a side effect of being imported (no exported
    // mount function), so importing it *is* the test action. React 18's
    // `createRoot().render()` commits asynchronously, so wait for the stub
    // to actually appear rather than asserting immediately after import.
    await import('../src/renderer/main');

    const stub = await screen.findByTestId('agent-stub');
    expect(stub.textContent).toBe('http://localhost:8000');
  });

  it('mounts the Agent shell with VITE_BACKEND_URL when set', async () => {
    document.body.innerHTML = '<div id="root"></div>';
    vi.stubEnv('VITE_BACKEND_URL', 'https://example.test');

    await import('../src/renderer/main');

    const stub = await screen.findByTestId('agent-stub');
    expect(stub.textContent).toBe('https://example.test');
  });
});
