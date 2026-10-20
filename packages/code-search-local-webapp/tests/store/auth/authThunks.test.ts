import { afterEach, describe, expect, it } from "@jest/globals"

import { ApiPaths } from "@code-search-local/code-search-local-api"
import {
  AuthActions,
  CodeSearchApi,
  SliceName,
  enterToken,
  selectToken,
  selectTokenRejected
} from "@code-search-local/code-search-local-webapp"

import { DashboardRoutes } from "../../common/DashboardRoutes.js"
import { FakeFetch } from "../../common/FakeFetch.js"
import { FakeServices } from "../../common/FakeServices.js"
import { TestStores } from "../../common/TestStores.js"

/** A token entered after a rejection. */
const NewToken = "new-token-9876543210"

afterEach(() => TestStores.resetAll())

describe("enterToken", () => {
  it("stores the token for the session and sends it from then on", () => {
    const services = FakeServices.create(FakeFetch.create({}).fetch, {
        token: FakeServices.NoToken
      }),
      store = TestStores.create(services)
    store.dispatch(AuthActions.tokenRejected())
    store.dispatch(enterToken(NewToken))
    expect(services.tokenStore.read()).toBe(NewToken)
    expect(selectToken(store.getState())).toBe(NewToken)
    expect(selectTokenRejected(store.getState())).toBe(false)
  })

  it("drops every response cached under the previous token", async () => {
    const fake = FakeFetch.create(
        DashboardRoutes.healthy({
          [ApiPaths.Stats]: DashboardRoutes.Unauthorized
        })
      ),
      store = TestStores.create(FakeServices.create(fake.fetch))
    await store.dispatch(
      CodeSearchApi.endpoints.getStats.initiate({}, { subscribe: false })
    )
    expect(
      Object.keys(store.getState()[SliceName.codeSearchApi].queries)
    ).not.toEqual([])
    store.dispatch(enterToken(NewToken))
    expect(store.getState()[SliceName.codeSearchApi].queries).toEqual({})
  })
})
