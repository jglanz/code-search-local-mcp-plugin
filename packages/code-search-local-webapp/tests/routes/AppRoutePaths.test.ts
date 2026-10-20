import { describe, expect, it } from "@jest/globals"
import { matchPath } from "react-router"

import { ApiPaths } from "@code-search-local/code-search-local-api"
import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import { AppRoutePaths } from "@code-search-local/code-search-local-webapp"

import { PublicPath } from "../../etc/webpack/webpack.common.mjs"

/** A client-side path no route but the fallback serves. */
const UnknownPath = "/projects/unknown/extra"

describe("AppRoutePaths", () => {
  it("serves the app at the API's web UI route, under the webpack public path", () => {
    expect(`${AppRoutePaths.Basename}/`).toBe(PublicPath)
    expect(AppRoutePaths.Basename).toBe(ApiPaths.WebUi)
  })

  it("matches the overview only at the root; any other path falls back", () => {
    expect(
      matchPath(AppRoutePaths.Overview, AppRoutePaths.Overview)
    ).not.toBeNull()
    expect(matchPath(AppRoutePaths.Overview, UnknownPath)).toBeNull()
    expect(matchPath(AppRoutePaths.Project, UnknownPath)).toBeNull()
    expect(matchPath(AppRoutePaths.Fallback, UnknownPath)).not.toBeNull()
  })
})

describe("AppRoutePaths.projectPath", () => {
  it("builds the project route the router matches back to the id", () => {
    const path = AppRoutePaths.projectPath(ApiFixtures.ProjectId)
    expect(matchPath(AppRoutePaths.Project, path).params).toEqual({
      projectId: ApiFixtures.ProjectId
    })
  })

  it("encodes an id so it stays one path segment", () => {
    const path = AppRoutePaths.projectPath("a/b")
    expect(matchPath(AppRoutePaths.Project, path).params.projectId).toBe("a/b")
    expect(path.split("/")).toHaveLength(
      AppRoutePaths.Project.split("/").length
    )
  })
})
