import {
  CodeSearchApi,
  createCodeSearchStore,
  type CodeSearchServices,
  type CodeSearchStore
} from "@code-search-local/code-search-local-webapp"

/**
 * Stores for node-environment tests, tracked so `resetAll` (in `afterEach`) clears the API
 * state, and with it RTK Query's cache-expiry timers, which would otherwise keep the worker
 * alive after the suite.
 */
export namespace TestStores {
  const created: CodeSearchStore[] = []

  /**
   * Create a tracked store.
   *
   * @param services the services it runs against.
   * @returns the store.
   */
  export function create(services: CodeSearchServices): CodeSearchStore {
    const store = createCodeSearchStore(services)
    created.push(store)
    return store
  }

  /** Reset the API state of every store created since the last call. */
  export function resetAll(): void {
    created
      .splice(0)
      .forEach(store => store.dispatch(CodeSearchApi.util.resetApiState()))
  }
}
