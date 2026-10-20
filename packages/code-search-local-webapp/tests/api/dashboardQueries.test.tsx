/**
 * @jest-environment jest-fixed-jsdom
 */
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  jest
} from "@jest/globals"
import { act, waitFor } from "@testing-library/react"

import {
  ApiPaths,
  ApiQueryKeys
} from "@code-search-local/code-search-local-api"
import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  AllProjectsArgs,
  DashboardPolling,
  DashboardQueryOptions,
  useDashboardHealth,
  useDashboardStats,
  useProjectPaths
} from "@code-search-local/code-search-local-webapp"

import { DashboardRoutes } from "../common/DashboardRoutes.js"
import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** The polling interval the dashboard contract specifies. */
const DocumentedIntervalMs = 2_000

/** One millisecond short of a polling interval. */
const JustBeforeIntervalMs = DashboardPolling.IntervalMs - 1

/**
 * How many requests a fake received for an API path.
 *
 * @param fake the fake fetch.
 * @param route the API path.
 * @returns the count.
 */
function countRequests(fake: FakeFetch, route: string): number {
  return fake.requestedUrls.filter(url => new URL(url).pathname === route)
    .length
}

describe("DashboardPolling", () => {
  beforeEach(() =>
    jest.useFakeTimers({
      doNotFake: ["queueMicrotask", "nextTick", "setImmediate"]
    })
  )
  afterEach(() => jest.useRealTimers())

  it("refreshes the snapshot once per interval, not before", async () => {
    const fake = FakeFetch.create(DashboardRoutes.healthy()),
      { result, unmount } = RenderWithStore.renderHook(
        () => useDashboardStats(),
        RenderWithStore.newServices(fake.fetch)
      )
    await waitFor(() =>
      expect(result.current.data).toEqual(ApiFixtures.Snapshot)
    )
    expect(countRequests(fake, ApiPaths.Stats)).toBe(1)
    // The next poll is scheduled when the first response is fulfilled (on the fake clock).
    const sinceFulfilledMs = Date.now() - result.current.fulfilledTimeStamp
    await act(() =>
      jest.advanceTimersByTimeAsync(JustBeforeIntervalMs - sinceFulfilledMs)
    )
    expect(countRequests(fake, ApiPaths.Stats)).toBe(1)
    await act(() => jest.advanceTimersByTimeAsync(1))
    await waitFor(() => expect(countRequests(fake, ApiPaths.Stats)).toBe(2))
    unmount()
  })

  it("polls every dashboard query at the documented 2-second interval", () => {
    expect(DashboardPolling.IntervalMs).toBe(DocumentedIntervalMs)
    expect(DashboardQueryOptions).toEqual({
      pollingInterval: DashboardPolling.IntervalMs
    })
  })
})

describe("useDashboardStats", () => {
  it("reads the unfiltered snapshot", async () => {
    const fake = FakeFetch.create(DashboardRoutes.healthy()),
      { result, unmount } = RenderWithStore.renderHook(
        () => useDashboardStats(),
        RenderWithStore.newServices(fake.fetch)
      )
    await waitFor(() =>
      expect(result.current.data).toEqual(ApiFixtures.Snapshot)
    )
    expect(AllProjectsArgs).toEqual({})
    unmount()
  })

  it("reports a failed request", async () => {
    const fake = FakeFetch.create(
        DashboardRoutes.healthy({
          [ApiPaths.Stats]: DashboardRoutes.ServerError
        })
      ),
      { result, unmount } = RenderWithStore.renderHook(
        () => useDashboardStats(),
        RenderWithStore.newServices(fake.fetch)
      )
    await waitFor(() => expect(result.current.isError).toBe(true))
    unmount()
  })
})

describe("useDashboardHealth", () => {
  it("reads the daemon's liveness", async () => {
    const fake = FakeFetch.create(DashboardRoutes.healthy()),
      { result, unmount } = RenderWithStore.renderHook(
        () => useDashboardHealth(),
        RenderWithStore.newServices(fake.fetch)
      )
    await waitFor(() => expect(result.current.data).toEqual(ApiFixtures.Health))
    unmount()
  })

  it("reports an unreachable service", async () => {
    const fake = FakeFetch.create(
        DashboardRoutes.healthy({
          [ApiPaths.Health]: DashboardRoutes.ServerError
        })
      ),
      { result, unmount } = RenderWithStore.renderHook(
        () => useDashboardHealth(),
        RenderWithStore.newServices(fake.fetch)
      )
    await waitFor(() => expect(result.current.isError).toBe(true))
    unmount()
  })
})

describe("useProjectPaths", () => {
  it("reads one project's paths", async () => {
    const fake = FakeFetch.create(DashboardRoutes.healthy()),
      { result, unmount } = RenderWithStore.renderHook(
        () => useProjectPaths(ApiFixtures.ProjectPath),
        RenderWithStore.newServices(fake.fetch)
      )
    await waitFor(() => expect(result.current.data).toEqual(ApiFixtures.Paths))
    expect(
      new URL(fake.requestedUrls[0]).searchParams.get(ApiQueryKeys.Project)
    ).toBe(ApiFixtures.ProjectPath)
    unmount()
  })

  it("requests nothing until the project is known", () => {
    const fake = FakeFetch.create(DashboardRoutes.healthy()),
      { result, unmount } = RenderWithStore.renderHook(
        () => useProjectPaths(undefined),
        RenderWithStore.newServices(fake.fetch)
      )
    expect(result.current.isUninitialized).toBe(true)
    expect(fake.requestedUrls).toEqual([])
    unmount()
  })
})
