import { asOption } from "@3fv/prelude-ts"
import { isFunction } from "lodash-es"

/** A canned JSON response. */
export interface FakeRoute {
  /** HTTP status. */
  status: number

  /** JSON body. */
  body: unknown
}

/** One request the fake received. */
export interface FakeRequest {
  /** HTTP method. */
  method: string

  /** Absolute URL. */
  url: string

  /** The parsed JSON body; null for a request without one. */
  body: unknown

  /** Request headers, names lower-cased. */
  headers: Record<string, string>
}

/** A response computed from the request (e.g. a PUT echoing its body). */
export type FakeHandler = (request: FakeRequest) => FakeRoute

/**
 * A `fetch` stand-in answering from a route table and recording every request. A route key is
 * `METHOD /path` or `/path` (any method); the method-specific key wins. Unknown routes answer
 * 404.
 */
export class FakeFetch {
  /** URLs requested, oldest first. */
  readonly requestedUrls: string[] = []

  /** Requests received, oldest first. */
  readonly requests: FakeRequest[] = []

  private constructor(
    private readonly routes: Record<string, FakeRoute | FakeHandler>
  ) {}

  /**
   * Create a fake.
   *
   * @param routes route key → canned response or handler.
   * @returns the fake.
   */
  static create(routes: Record<string, FakeRoute | FakeHandler>): FakeFetch {
    return new FakeFetch(routes)
  }

  /** The fetch function to inject. */
  readonly fetch: typeof fetch = async (
    input: RequestInfo | URL,
    init?: RequestInit
  ) => {
    const request = input instanceof Request ? input : new Request(input, init),
      { pathname } = new URL(request.url),
      text = await request.text(),
      received: FakeRequest = {
        method: request.method,
        url: request.url,
        body: text.length === 0 ? null : JSON.parse(text),
        headers: Object.fromEntries(request.headers)
      },
      route = asOption(this.routes[`${request.method} ${pathname}`])
        .orElse(asOption(this.routes[pathname]))
        .getOrElse(FakeFetch.NotFound),
      { status, body } = isFunction(route) ? route(received) : route
    this.requests.push(received)
    this.requestedUrls.push(request.url)
    return new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" }
    })
  }
}

/** Companion constants for {@link FakeFetch}. */
export namespace FakeFetch {
  /** Response for an unknown path. */
  export const NotFound: FakeRoute = {
    status: 404,
    body: { error: "not found" }
  }

  /** Absolute origin used as `apiBaseUrl` in tests. */
  export const TestOrigin = "http://code-search-local.test"

  /** Answers a request with its own body (as the server's PUT routes do). */
  export const EchoBody: FakeHandler = ({ body }) => ({ status: 200, body })
}
