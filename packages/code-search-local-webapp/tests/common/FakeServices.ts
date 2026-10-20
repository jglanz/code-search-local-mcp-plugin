import {
  TokenStore,
  type CodeSearchServices
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "./FakeFetch.js"
import { FakeStorage } from "./FakeStorage.js"

/** How {@link FakeServices.create} builds the services. */
export interface FakeServicesOptions {
  /** The origin (the fake's test origin by default). */
  apiBaseUrl?: string

  /** The token the session holds ({@link FakeServices.TestToken} by default; `""` for none). */
  token?: string
}

/** Services over a fake fetch and an in-memory session storage (usable in node and jsdom tests). */
export namespace FakeServices {
  /** The token a session holds unless a test says otherwise. */
  export const TestToken = "test-token-0123456789"

  /** Passed as `token` for a session without one. */
  export const NoToken = ""

  /**
   * Create services.
   *
   * @param fetchFn the fake's fetch.
   * @param options the origin and the session's token.
   * @returns the services.
   */
  export function create(
    fetchFn: typeof fetch,
    {
      apiBaseUrl = FakeFetch.TestOrigin,
      token = TestToken
    }: FakeServicesOptions = {}
  ): CodeSearchServices {
    const tokenStore = new TokenStore(FakeStorage.create())
    tokenStore.write(token)
    return { fetchFn, apiBaseUrl, tokenStore }
  }
}
