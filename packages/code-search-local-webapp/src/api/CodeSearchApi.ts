import { createApi } from "@reduxjs/toolkit/query/react"

import {
  ApiPaths,
  ApiQueryKeys,
  type HealthResponse,
  type PathsResponse,
  type StatsSnapshot
} from "@code-search-local/code-search-local-api"

import { SliceName } from "../store/SliceName.js"
import { ApiCodecs } from "./ApiCodecs.js"
import { newCodecQueryFn } from "./codecQueryUtils.js"
import { CodeSearchApiTag } from "./CodeSearchApiTag.js"
import { servicesBaseQuery } from "./servicesBaseQuery.js"

/** Argument of {@link CodeSearchApi} `getStats`. */
export interface GetStatsArgs {
  /** Absolute project root to filter the snapshot to; every project when absent. */
  project?: string
}

/**
 * RTK Query API for the service's JSON routes the dashboard reads. Every body is validated by a
 * codec over the generated schemas; every request resolves against the store's
 * {@link CodeSearchServices} and carries the session's bearer token.
 */
export const CodeSearchApi = createApi({
  reducerPath: SliceName.codeSearchApi,
  baseQuery: servicesBaseQuery,
  tagTypes: Object.values(CodeSearchApiTag),
  endpoints: builder => ({
    getStats: builder.query<StatsSnapshot, GetStatsArgs>({
      queryFn: newCodecQueryFn(ApiCodecs.StatsSnapshotCodec, ({ project }) =>
        project == null
          ? ApiPaths.Stats
          : { url: ApiPaths.Stats, params: { [ApiQueryKeys.Project]: project } }
      ),
      providesTags: [CodeSearchApiTag.stats]
    }),
    getPaths: builder.query<PathsResponse, string>({
      queryFn: newCodecQueryFn(ApiCodecs.PathsResponseCodec, project => ({
        url: ApiPaths.Paths,
        params: { [ApiQueryKeys.Project]: project }
      })),
      providesTags: [CodeSearchApiTag.paths]
    }),
    getHealth: builder.query<HealthResponse, void>({
      queryFn: newCodecQueryFn(
        ApiCodecs.HealthResponseCodec,
        () => ApiPaths.Health
      ),
      providesTags: [CodeSearchApiTag.health]
    })
  })
})
