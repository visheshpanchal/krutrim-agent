import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// `<Agent>` is the whole product shell (redux store, AG-UI streaming, its
// own URL sync) — heavier than what this test is about, which is just: does
// `App` wire up the router and pass the right backend URL through. Stub it
// out so this stays a fast, focused routing smoke test.
vi.mock('@krutrim_agent/agent-ui', () => ({
  Agent: ({ backendUrl }: { backendUrl: string }) => <div data-testid="agent-stub">{backendUrl}</div>,
}));

const { App } = await import('../src/app/app');

describe('App', () => {
  it('renders the Agent shell on the catch-all route with the default backend URL', () => {
    render(<App />);
    expect(screen.getByTestId('agent-stub').textContent).toBe('http://localhost:8000');
  });
});
