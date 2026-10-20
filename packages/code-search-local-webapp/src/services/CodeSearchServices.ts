import { TokenStore } from "../auth/TokenStore.js"

/**
 * Environment the store's thunks and the RTK Query base query run against, injected as the
 * thunk `extraArgument` (and RTK Query's `api.extra`) so tests substitute a fake fetch, an
 * absolute test origin and an in-memory token storage.
 */
export interface CodeSearchServices {
  /** The fetch implementation every API request goes through. */
  fetchFn: typeof fetch

  /**
   * Absolute origin every API path is resolved against (Node's `Request` rejects relative URLs).
   * In the browser it is the page's origin: the service serves the webapp and the API together.
   */
  apiBaseUrl: string

  /** Where the bearer token is kept for the session. */
  tokenStore: TokenStore
}

/** Companion helpers for {@link CodeSearchServices}. */
export namespace CodeSearchServices {
  /**
   * Services for the browser: the window's fetch and origin, and the tab's `sessionStorage`.
   *
   * @returns the browser services.
   */
  export function createBrowserServices(): CodeSearchServices {
    return {
      fetchFn: window.fetch.bind(window),
      apiBaseUrl: window.location.origin,
      tokenStore: new TokenStore(window.sessionStorage)
    }
  }
}
