import { describe, expect, it } from "@jest/globals"

import { ApiPaths } from "@code-search-local/code-search-local-api"

import { OpenApiDocument } from "./common/OpenApiDocument.js"

/** Every route constant (the namespace's string members, the placeholder excluded). */
const RouteConstants = Object.entries(ApiPaths)
  .filter(
    ([name, value]) => typeof value === "string" && name !== "JobIdParameter"
  )
  .map(([, value]) => value as string)

/** A job id as the service writes it. */
const JobId = "9a8b7c6d5e4f30211203f4e5d6c7b8a9"

/** A hostile job id that tries to leave the job route. */
const TraversingJobId = "../stats?project=/"

describe("ApiPaths", () => {
  it("names only routes the OpenAPI document describes", () => {
    expect(OpenApiDocument.listPaths()).toEqual(
      expect.arrayContaining(RouteConstants)
    )
  })

  it("has a constant for every documented /api/v1 route", () => {
    const apiRoutes = OpenApiDocument.listPaths().filter(route =>
      route.startsWith(OpenApiDocument.ApiPrefix)
    )
    expect(RouteConstants).toEqual(expect.arrayContaining(apiRoutes))
    expect(RouteConstants).not.toContain(`${ApiPaths.Stats}/unknown`)
  })
})

describe("ApiPaths.jobPath", () => {
  it("fills the job id into the documented template", () => {
    expect(ApiPaths.jobPath(JobId)).toBe(`/api/v1/jobs/${JobId}`)
    expect(ApiPaths.Job).toContain(ApiPaths.JobIdParameter)
  })

  it("encodes an id so it can never leave the job route", () => {
    const route = ApiPaths.jobPath(TraversingJobId)
    expect(route).not.toContain(TraversingJobId)
    expect(route.split("/")).toHaveLength(ApiPaths.Job.split("/").length)
  })
})
