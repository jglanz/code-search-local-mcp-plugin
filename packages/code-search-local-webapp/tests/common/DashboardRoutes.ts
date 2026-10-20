import { ApiPaths } from "@code-search-local/code-search-local-api"
import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"

import type { FakeHandler, FakeRoute } from "./FakeFetch.js"

/** A fake-fetch route table. */
export type FakeRoutes = Record<string, FakeRoute | FakeHandler>

/** Fake service routes for dashboard tests, answering with the API package's fixtures. */
export namespace DashboardRoutes {
  /** HTTP 200. */
  export const OkStatus = 200

  /** HTTP 400 (unknown project, invalid input). */
  export const BadRequestStatus = 400

  /** HTTP 401 (missing or wrong token). */
  export const UnauthorizedStatus = 401

  /** HTTP 500. */
  export const ServerErrorStatus = 500

  /** The service's answer to a request without a valid token. */
  export const Unauthorized: FakeRoute = {
    status: UnauthorizedStatus,
    body: { error: "Unauthorized" }
  }

  /** A failure with the service's error body. */
  export const ServerError: FakeRoute = {
    status: ServerErrorStatus,
    body: { error: "snapshot unavailable" }
  }

  /**
   * A successful JSON answer.
   *
   * @param body the body.
   * @returns the route.
   */
  export function ok(body: unknown): FakeRoute {
    return { status: OkStatus, body }
  }

  /**
   * A healthy service: stats, health and paths answer with the fixtures.
   *
   * @param overrides routes replacing the healthy ones.
   * @returns the route table.
   */
  export function healthy(overrides: FakeRoutes = {}): FakeRoutes {
    return {
      [ApiPaths.Stats]: ok(ApiFixtures.Snapshot),
      [ApiPaths.Health]: ok(ApiFixtures.Health),
      [ApiPaths.Paths]: ok(ApiFixtures.Paths),
      ...overrides
    }
  }
}
