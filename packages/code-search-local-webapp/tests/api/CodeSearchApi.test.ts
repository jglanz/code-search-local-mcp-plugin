import { afterEach, describe, expect, it } from "@jest/globals"

import {
  ApiPaths,
  ApiQueryKeys
} from "@code-search-local/code-search-local-api"
import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  CodeSearchApi,
  CodeSearchApiTag,
  CustomErrorStatus,
  SliceName
} from "@code-search-local/code-search-local-webapp"

import { DashboardRoutes, type FakeRoutes } from "../common/DashboardRoutes.js"
import { FakeFetch } from "../common/FakeFetch.js"
import { FakeServices } from "../common/FakeServices.js"
import { TestStores } from "../common/TestStores.js"

afterEach(() => TestStores.resetAll())

/** The endpoints the dashboard reads, in declaration order. */
const EndpointNames = ["getStats", "getPaths", "getHealth"]

/**
 * A store over a fake service.
 *
 * @param routes the fake's routes.
 * @returns the fake and the store.
 */
function newStore(routes: FakeRoutes) {
  const fake = FakeFetch.create(routes)
  return {
    fake,
    store: TestStores.create(FakeServices.create(fake.fetch))
  }
}

/**
 * The URL a request to an API path with a project query goes to.
 *
 * @param route the API path.
 * @param project the project root.
 * @returns the absolute URL.
 */
function projectUrl(route: string, project: string): string {
  return `${FakeFetch.TestOrigin}${route}?${new URLSearchParams({ [ApiQueryKeys.Project]: project })}`
}

describe("CodeSearchApi", () => {
  it("keys its state by the slice name and declares every tag", () => {
    expect(CodeSearchApi.reducerPath).toBe(SliceName.codeSearchApi)
    expect(Object.keys(CodeSearchApi.endpoints)).toEqual(EndpointNames)
  })

  it("never shares a tag between endpoints, so polling one never refetches another", () => {
    expect(new Set(Object.values(CodeSearchApiTag)).size).toBe(
      Object.values(CodeSearchApiTag).length
    )
  })
})

describe("CodeSearchApi.getStats", () => {
  it("reads the unfiltered snapshot and validates it with the generated schema", async () => {
    const { fake, store } = newStore(DashboardRoutes.healthy()),
      { data, error } = await store.dispatch(
        CodeSearchApi.endpoints.getStats.initiate({}, { subscribe: false })
      )
    expect(error).toBeUndefined()
    expect(data).toEqual(ApiFixtures.Snapshot)
    expect(fake.requestedUrls).toEqual([
      `${FakeFetch.TestOrigin}${ApiPaths.Stats}`
    ])
  })

  it("filters to one project through the project query parameter", async () => {
    const { fake, store } = newStore(DashboardRoutes.healthy())
    await store.dispatch(
      CodeSearchApi.endpoints.getStats.initiate(
        { project: ApiFixtures.ProjectPath },
        { subscribe: false }
      )
    )
    expect(fake.requestedUrls).toEqual([
      projectUrl(ApiPaths.Stats, ApiFixtures.ProjectPath)
    ])
  })

  it("turns a body that fails the schema into a CUSTOM_ERROR naming the codec", async () => {
    const { store } = newStore(
        DashboardRoutes.healthy({
          [ApiPaths.Stats]: DashboardRoutes.ok({ online: "yes" })
        })
      ),
      { data, error } = await store.dispatch(
        CodeSearchApi.endpoints.getStats.initiate({}, { subscribe: false })
      )
    expect(data).toBeUndefined()
    expect(error).toMatchObject({
      status: CustomErrorStatus,
      error: expect.stringContaining("StatsSnapshot: decode failed")
    })
  })

  it("reports an HTTP failure with its status and the service's body", async () => {
    const { store } = newStore(
        DashboardRoutes.healthy({
          [ApiPaths.Stats]: DashboardRoutes.ServerError
        })
      ),
      { error } = await store.dispatch(
        CodeSearchApi.endpoints.getStats.initiate({}, { subscribe: false })
      )
    expect(error).toEqual({
      status: DashboardRoutes.ServerErrorStatus,
      data: DashboardRoutes.ServerError.body
    })
  })
})

describe("CodeSearchApi.getPaths", () => {
  it("reads one project's paths", async () => {
    const { fake, store } = newStore(DashboardRoutes.healthy()),
      { data } = await store.dispatch(
        CodeSearchApi.endpoints.getPaths.initiate(ApiFixtures.ProjectPath, {
          subscribe: false
        })
      )
    expect(data).toEqual(ApiFixtures.Paths)
    expect(fake.requestedUrls).toEqual([
      projectUrl(ApiPaths.Paths, ApiFixtures.ProjectPath)
    ])
  })

  it("reports the service's 400 for an unknown project", async () => {
    const unknown = {
        status: DashboardRoutes.BadRequestStatus,
        body: { error: "Unknown project" }
      },
      { store } = newStore(
        DashboardRoutes.healthy({ [ApiPaths.Paths]: unknown })
      ),
      { error } = await store.dispatch(
        CodeSearchApi.endpoints.getPaths.initiate(ApiFixtures.IdleProjectPath, {
          subscribe: false
        })
      )
    expect(error).toEqual({ status: unknown.status, data: unknown.body })
  })
})

describe("CodeSearchApi.getHealth", () => {
  it("reads the daemon's liveness", async () => {
    const { store } = newStore(DashboardRoutes.healthy()),
      { data } = await store.dispatch(
        CodeSearchApi.endpoints.getHealth.initiate(undefined, {
          subscribe: false
        })
      )
    expect(data).toEqual(ApiFixtures.Health)
  })

  it("rejects a liveness body with any status but ok", async () => {
    const { store } = newStore(
        DashboardRoutes.healthy({
          [ApiPaths.Health]: DashboardRoutes.ok({
            ...ApiFixtures.Health,
            status: "starting"
          })
        })
      ),
      { error } = await store.dispatch(
        CodeSearchApi.endpoints.getHealth.initiate(undefined, {
          subscribe: false
        })
      )
    expect(error).toMatchObject({ status: CustomErrorStatus })
  })
})
