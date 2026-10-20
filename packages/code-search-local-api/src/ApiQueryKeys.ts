import type { GetPathsData, GetStatsData } from "./generated/index.js"

/**
 * Query parameter names of the service's HTTP API. Each constant is typed with the query of the
 * operations generated from `openapi.yaml` that take it, so a renamed parameter fails
 * type-checking here.
 */
export namespace ApiQueryKeys {
  /**
   * The absolute project root: optional on `getStats` (omit for every project), required on
   * `getPaths` and the job routes.
   */
  export const Project: keyof GetStatsData["query"] &
    keyof GetPathsData["query"] = "project"
}
