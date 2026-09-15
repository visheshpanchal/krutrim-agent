/// <reference types='vitest' />
import { defineConfig } from 'vite';

// No build target here: this lib is consumed directly from `src/` via the
// `@krutrim_agent/tauri-utils` tsconfig path alias (see tsconfig.base.json),
// never through a built `dist/`. This config exists solely to give it a
// Vitest target.
export default defineConfig(() => ({
  root: import.meta.dirname,
  cacheDir: '../../node_modules/.vite/libs/tauri-utils',
  test: {
    name: 'tauri-utils',
    watch: false,
    globals: true,
    environment: 'node',
    include: ['{src,tests}/**/*.{test,spec}.{ts,tsx}'],
    reporters: ['default'],
    coverage: {
      reportsDirectory: '../../coverage/libs/tauri-utils',
      provider: 'v8' as const,
    },
  },
}));
