import type {
  CancelJobData,
  GetHealthData,
  GetOpenApiDocumentData,
  GetPathsData,
  GetStatsData,
  IndexDirectoryData,
  RedirectWebUiPrefixData,
  SearchCodeData,
  WarmupModelData
} from "./generated/index.js"

/**
 * Every route of the service's HTTP API that a TypeScript client calls. Each constant is typed
 * with the `url` of the operation generated from `openapi.yaml`, so renaming a route in the
 * document fails type-checking here until the constant follows; `ApiPaths.test` also checks the
 * reverse (every documented `/api/v1` route has a constant).
 */
export namespace ApiPaths {
  /** Daemon liveness (`getHealth`). */
  export const Health: GetHealthData["url"] = "/api/v1/health"

  /** Shared model warm-up (`warmupModel`). */
  export const Model: WarmupModelData["url"] = "/api/v1/model"

  /** Statistics snapshot, optionally filtered to one project (`getStats`). */
  export const Stats: GetStatsData["url"] = "/api/v1/stats"

  /** Queue an indexing job (`indexDirectory`). */
  export const Index: IndexDirectoryData["url"] = "/api/v1/index"

  /** Search one project's committed index (`searchCode`). */
  export const Search: SearchCodeData["url"] = "/api/v1/search"

  /** One indexing job, as a template with the {@link JobIdParameter} placeholder (`getJob`). */
  export const Job: CancelJobData["url"] = "/api/v1/jobs/{job_id}"

  /** Per-path search analytics of one project (`getPaths`). */
  export const Paths: GetPathsData["url"] = "/api/v1/paths"

  /** This API description as JSON (`getOpenApiDocument`). */
  export const OpenApiDocument: GetOpenApiDocumentData["url"] =
    "/api/v1/openapi.json"

  /**
   * Where the service serves the web dashboard (`redirectWebUiPrefix`); the webapp's router
   * basename and webpack public path derive from it.
   */
  export const WebUi: RedirectWebUiPrefixData["url"] = "/ui"

  /** The placeholder of {@link Job} replaced by a job id. */
  export const JobIdParameter = "{job_id}"

  /**
   * The route of one job.
   *
   * @param jobId the job id returned when the job was queued.
   * @returns e.g. `/api/v1/jobs/0123…`.
   */
  export function jobPath(jobId: string): string {
    return Job.replace(JobIdParameter, encodeURIComponent(jobId))
  }
}
