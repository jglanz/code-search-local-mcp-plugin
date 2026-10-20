import { afterEach, describe, expect, it } from "@jest/globals"

import { ApiPaths } from "@code-search-local/code-search-local-api"
import {
  AuthorizationHeader,
  BearerScheme,
  CodeSearchApi,
  UnauthorizedStatus,
  newBearerAuthorization,
  selectToken,
  selectTokenRejected
} from "@code-search-local/code-search-local-webapp"

import { DashboardRoutes } from "../common/DashboardRoutes.js"
import { FakeFetch } from "../common/FakeFetch.js"
import { FakeServices } from "../common/FakeServices.js"
import { TestStores } from "../common/TestStores.js"

afterEach(() => TestStores.resetAll())

/** Lower-cased header name, as `Headers` reports it. */
const AuthorizationKey = AuthorizationHeader.toLowerCase()

describe("newBearerAuthorization", () => {
  it("prefixes the token with the bearer scheme", () => {
    expect(newBearerAuthorization(FakeServices.TestToken)).toBe(
      `${BearerScheme} ${FakeServices.TestToken}`
    )
  })

  it("never sends a bare token", () => {
    expect(newBearerAuthorization(FakeServices.TestToken)).not.toBe(
      FakeServices.TestToken
    )
  })
})

describe("servicesBaseQuery", () => {
  it("sends the session's token as a bearer Authorization header", async () => {
    const fake = FakeFetch.create(DashboardRoutes.healthy()),
      store = TestStores.create(FakeServices.create(fake.fetch))
    await store.dispatch(
      CodeSearchApi.endpoints.getHealth.initiate(undefined, {
        subscribe: false
      })
    )
    expect(fake.requests[0].headers[AuthorizationKey]).toBe(
      newBearerAuthorization(FakeServices.TestToken)
    )
  })

  it("sends no Authorization header without a token", async () => {
    const fake = FakeFetch.create(DashboardRoutes.healthy()),
      store = TestStores.create(
        FakeServices.create(fake.fetch, { token: FakeServices.NoToken })
      )
    await store.dispatch(
      CodeSearchApi.endpoints.getHealth.initiate(undefined, {
        subscribe: false
      })
    )
    expect(fake.requests[0].headers).not.toHaveProperty(AuthorizationKey)
  })

  it("clears the stored token and records the rejection on a 401", async () => {
    const fake = FakeFetch.create(
        DashboardRoutes.healthy({
          [ApiPaths.Stats]: DashboardRoutes.Unauthorized
        })
      ),
      services = FakeServices.create(fake.fetch),
      store = TestStores.create(services),
      { error } = await store.dispatch(
        CodeSearchApi.endpoints.getStats.initiate({}, { subscribe: false })
      )
    expect(error).toMatchObject({ status: UnauthorizedStatus })
    expect(services.tokenStore.read()).toBeUndefined()
    expect(selectToken(store.getState())).toBeUndefined()
    expect(selectTokenRejected(store.getState())).toBe(true)
  })

  it("keeps the token on other failures", async () => {
    const fake = FakeFetch.create(
        DashboardRoutes.healthy({
          [ApiPaths.Stats]: DashboardRoutes.ServerError
        })
      ),
      services = FakeServices.create(fake.fetch),
      store = TestStores.create(services)
    await store.dispatch(
      CodeSearchApi.endpoints.getStats.initiate({}, { subscribe: false })
    )
    expect(services.tokenStore.read()).toBe(FakeServices.TestToken)
    expect(selectTokenRejected(store.getState())).toBe(false)
  })
})
