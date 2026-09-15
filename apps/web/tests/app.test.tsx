import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// `<Agent>` is the whole product shell (redux store, AG-UI streaming, its
// own URL sync) — heavier than what this test is about, which is just: does
// `App` wire up the router and pass the right backend URL through. Stub it
// out so this stays a fast, focused routing smoke test.
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

describe('App', () => {
  it('renders the Agent shell on the catch-all route with the default backend URL', async () => {
    const { App } = await import('../src/app/app');
    render(<App />);
    expect(screen.getByTestId('agent-stub').textContent).toBe('http://localhost:8000');
  });

  it('uses VITE_BACKEND_URL when set', async () => {
    vi.stubEnv('VITE_BACKEND_URL', 'https://example.test');
    const { App } = await import('../src/app/app');
    render(<App />);
    expect(screen.getByTestId('agent-stub').textContent).toBe('https://example.test');
  });
});
