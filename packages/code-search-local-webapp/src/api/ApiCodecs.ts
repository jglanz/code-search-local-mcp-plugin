import type { z } from "zod"

import {
  zHealthResponse,
  zPathsResponse,
  zStatsSnapshot,
  type HealthResponse,
  type PathsResponse,
  type StatsSnapshot
} from "@code-search-local/code-search-local-api"

import { SchemaCodec } from "../schema/SchemaCodec.js"

/**
 * Codecs of the service responses the dashboard reads, over the zod schemas generated from the
 * API package's `openapi.yaml` (the webapp never hand-writes a wire shape).
 */
export namespace ApiCodecs {
  /** `GET /api/v1/stats`. */
  export const StatsSnapshotCodec = newApiCodec<StatsSnapshot>(
    "StatsSnapshot",
    zStatsSnapshot
  )

  /** `GET /api/v1/paths`. */
  export const PathsResponseCodec = newApiCodec<PathsResponse>(
    "PathsResponse",
    zPathsResponse
  )

  /** `GET /api/v1/health`. */
  export const HealthResponseCodec = newApiCodec<HealthResponse>(
    "HealthResponse",
    zHealthResponse
  )

  /**
   * A codec typed with the generated TypeScript type of its schema. Both come from the same
   * `openapi.yaml`; they differ only because zod infers every nullable key as optional under
   * this workspace's `strictNullChecks: false`, while the generated types keep such keys
   * required. The schema still validates every body.
   *
   * @param name the shape's name, used in failure messages.
   * @param schema the generated zod schema.
   * @returns the codec.
   */
  export function newApiCodec<T>(
    name: string,
    schema: z.ZodType
  ): SchemaCodec<T> {
    return SchemaCodec.create(name, schema as z.ZodType<T>)
  }
}
