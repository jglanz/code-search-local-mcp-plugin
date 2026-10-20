import { generatePath } from "react-router"

/** Route parameters of {@link AppRoutePaths.Project}. */
export interface ProjectRouteParams extends Record<string, string> {
  /** The project's id: the SHA-256 digest of its root (`project_id` in the snapshot). */
  projectId: string
}

/**
 * Every client-side route of the app, relative to {@link AppRoutePaths.Basename}. The service's
 * SPA fallback serves `index.html` for any non-file path under the basename, so changing a route
 * here needs no service change.
 */
export namespace AppRoutePaths {
  /**
   * Where the service serves the webapp (the Python service's `WEBAPP_ENDPOINT`, the API
   * package's `ApiPaths.WebUi`). The webpack `PublicPath` (`etc/webpack/webpack.common.mjs`) is
   * this value plus a trailing slash, and `AppRoutePaths.test` fails when any of them differ;
   * changing it moves every page and asset URL.
   */
  export const Basename = "/ui"

  /** The service overview (status, totals, projects). */
  export const Overview = "/"

  /** One project's analytics, jobs and indexed paths. */
  export const Project = "/projects/:projectId"

  /** Any other path (rendered as "not found"). */
  export const Fallback = "*"

  /**
   * The page of one project.
   *
   * @param projectId the project's id (`project_id` in the snapshot).
   * @returns e.g. `/projects/8c5b…`.
   */
  export function projectPath(projectId: string): string {
    return generatePath(Project, { projectId })
  }
}
