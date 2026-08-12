import "@testing-library/jest-dom/vitest"

// jsdom in this config does not expose Web Storage, so provide an in-memory localStorage
// for code that persists state locally (e.g. the onboarding wizard progress).
if (typeof globalThis.localStorage === "undefined") {
  const store = new Map<string, string>()
  const localStorageMock = {
    get length() {
      return store.size
    },
    clear: () => {
      store.clear()
    },
    getItem: (key: string) => store.get(key) ?? null,
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    removeItem: (key: string) => {
      store.delete(key)
    },
    setItem: (key: string, value: string) => {
      store.set(key, String(value))
    },
  }
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: localStorageMock,
  })
}
