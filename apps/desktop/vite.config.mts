/// <reference types='vitest' />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { nxViteTsPaths } from '@nx/vite/plugins/nx-tsconfig-paths.plugin';

// Test-only config, separate from `vite.renderer.config.mts` (the actual
// Tauri renderer build, wired explicitly in project.json since its
// non-standard filename isn't picked up by Nx's plugin inference). Nx's
// vite/vitest plugins do scan for the standard `vite.config.mts` name, so
// this file's only job is to give the project a Vitest target without
// touching the real build config. Needs the same tsconfig-paths + react
// plugins as the renderer config so `src/renderer/main.tsx`'s
// `@krutrim_agent/*` imports and JSX resolve under test.
export default defineConfig(() => ({
  root: import.meta.dirname,
  cacheDir: '../../node_modules/.vite/apps/desktop-test',
  plugins: [react(), nxViteTsPaths()],
  test: {
    name: 'desktop',
    watch: false,
    globals: true,
    environment: 'jsdom',
    include: ['tests/**/*.{test,spec}.{ts,tsx}'],
    reporters: ['default'],
    coverage: {
      reportsDirectory: '../../coverage/apps/desktop',
      provider: 'v8' as const,
    },
  },
}));
