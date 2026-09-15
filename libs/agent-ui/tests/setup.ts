/**
 * Node 22+'s built-in global `localStorage`/`sessionStorage` (Web Storage
 * without `--localstorage-file`) shadows jsdom's real implementation under
 * this Vitest/jsdom combination: `window.localStorage` resolves to
 * `undefined` instead of a working `Storage`, after printing an
 * "ExperimentalWarning: --localstorage-file was not provided" once. Swap in
 * a plain in-memory stand-in so every test in this project gets a normal,
 * working browser Storage. A plain property assignment (not `vi.stubGlobal`)
 * so it survives a test file's own `vi.unstubAllGlobals()` cleanup.
 */
function createMemoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    removeItem: (key: string) => {
      store.delete(key);
    },
    setItem: (key: string, value: string) => {
      store.set(key, String(value));
    },
  } as Storage;
}

if (typeof window !== 'undefined') {
  if (!window.localStorage) {
    Object.defineProperty(window, 'localStorage', { value: createMemoryStorage(), configurable: true });
  }
  if (!window.sessionStorage) {
    Object.defineProperty(window, 'sessionStorage', { value: createMemoryStorage(), configurable: true });
  }
}
