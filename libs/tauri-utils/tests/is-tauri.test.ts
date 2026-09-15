import { describe, expect, it, vi } from 'vitest';

const { isTauri } = vi.hoisted(() => ({ isTauri: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({ isTauri }));

const { isTauriRuntime } = await import('../src/lib/is-tauri');

describe('isTauriRuntime', () => {
  it('returns true when @tauri-apps/api/core reports the Tauri shell', () => {
    isTauri.mockReturnValue(true);
    expect(isTauriRuntime()).toBe(true);
  });

  it('returns false in a plain browser', () => {
    isTauri.mockReturnValue(false);
    expect(isTauriRuntime()).toBe(false);
  });
});
