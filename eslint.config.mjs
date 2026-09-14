import tseslint from '@typescript-eslint/eslint-plugin';
import tsParser from '@typescript-eslint/parser';
import importX, { createNodeResolver } from 'eslint-plugin-import-x';
import { createTypeScriptImportResolver } from 'eslint-import-resolver-typescript';
import prettier from 'eslint-config-prettier';

export default [
  {
    ignores: ['**/dist/**', '**/node_modules/**', '**/vite.config.*.timestamp*', 'backend/**'],
  },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      '@typescript-eslint': tseslint,
      'import-x': importX,
    },
    settings: {
      // Let import-x read `.ts`/`.tsx` dependency files (its default only covers
      // `.js`), so `no-cycle` can actually walk the TypeScript module graph.
      ...importX.flatConfigs.typescript.settings,
      'import-x/resolver-next': [
        createTypeScriptImportResolver({
          project: [
            'tsconfig.base.json',
            'libs/*/tsconfig.lib.json',
            'apps/web/tsconfig.app.json',
            'apps/desktop/tsconfig.renderer.json',
          ],
          noWarnOnMultipleProjects: true,
        }),
        createNodeResolver(),
      ],
    },
    rules: {
      ...tseslint.configs.recommended.rules,
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/no-explicit-any': 'off',
      // Fail on a runtime import cycle anywhere in the graph. Type-only edges
      // (`import type` / `export type`) are erased at build and don't count —
      // run `pnpm dlx madge --circular ...` if you also want those flagged.
      'import-x/no-cycle': ['error', { maxDepth: Infinity, ignoreExternal: true }],
    },
  },
  prettier,
];
