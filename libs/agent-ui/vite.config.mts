/// <reference types='vitest' />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import dts from 'vite-plugin-dts';

// Library build — see libs/shared-types/vite.config.mts's comment for why
// `external` treats every bare specifier (including sibling `@krutrim_agent/*`
// packages) as external rather than bundled.
export default defineConfig(() => ({
  root: import.meta.dirname,
  cacheDir: '../../node_modules/.vite/libs/agent-ui',
  plugins: [react(), dts({ entryRoot: 'src', tsconfigPath: 'tsconfig.lib.json' })],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    lib: {
      entry: 'src/index.ts',
      formats: ['es'],
      fileName: 'index',
    },
    rollupOptions: {
      external: (id: string) => !/^[./]/.test(id),
    },
  },
  test: {
    name: 'agent-ui',
    watch: false,
    globals: true,
    environment: 'jsdom',
    setupFiles: ['tests/setup.ts'],
    include: ['{src,tests}/**/*.{test,spec}.{ts,tsx}'],
    reporters: ['default'],
    coverage: {
      reportsDirectory: '../../coverage/libs/agent-ui',
      provider: 'v8' as const,
    },
  },
}));
