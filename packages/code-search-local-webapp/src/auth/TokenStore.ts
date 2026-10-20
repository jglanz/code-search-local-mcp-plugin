/**
 * Where the service's bearer token lives between page loads: the tab's `sessionStorage`, so a
 * token never outlives the browser session and never reaches another tab or origin. The token
 * arrives once in the URL fragment (`code-search-local web` opens `/ui/#token=…`) or is pasted on
 * the connect screen.
 */
export class TokenStore {
  /**
   * @param storage the storage holding the token (`window.sessionStorage` in the browser).
   */
  constructor(private readonly storage: Storage) {}

  /**
   * The stored token.
   *
   * @returns the token, or undefined when none is stored.
   */
  read(): string {
    const token = this.storage.getItem(TokenStore.StorageKey)
    return token == null || token.length === 0 ? undefined : token
  }

  /**
   * Store a token, replacing any previous one.
   *
   * @param token the service token.
   */
  write(token: string): void {
    this.storage.setItem(TokenStore.StorageKey, token)
  }

  /** Forget the token (the service rejected it). */
  clear(): void {
    this.storage.removeItem(TokenStore.StorageKey)
  }

  /**
   * Take the token out of the URL fragment once: store it, then remove the fragment with
   * `history.replaceState` so the token never stays in the address bar, the history entry or a
   * bookmark. A fragment without a token is left untouched.
   *
   * @param location the page location.
   * @param history the page history.
   * @returns the captured token, or undefined when the fragment carried none.
   */
  captureFragment(location: Location, history: History): string {
    const token = new URLSearchParams(
      location.hash.slice(TokenStore.FragmentPrefix.length)
    ).get(TokenStore.FragmentKey)
    if (token == null || token.length === 0) return undefined
    this.write(token)
    history.replaceState(
      history.state,
      "",
      `${location.pathname}${location.search}`
    )
    return token
  }
}

/** Companion constants for {@link TokenStore}. */
export namespace TokenStore {
  /**
   * Storage key of the token. Renaming it forgets every stored token once (users reconnect with
   * `code-search-local web`).
   */
  export const StorageKey = "code-search-local.token"

  /**
   * Fragment parameter carrying the token; `code-search-local web` writes `#token=<token>`, so
   * both must change together.
   */
  export const FragmentKey = "token"

  /** What precedes the fragment's parameters in `location.hash`. */
  export const FragmentPrefix = "#"
}
