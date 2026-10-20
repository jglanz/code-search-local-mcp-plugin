import { describe, expect, it } from "@jest/globals"

import {
  SliceName,
  createCodeSearchStore,
  selectToken
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { FakeServices } from "../common/FakeServices.js"

/** An action no slice handles. */
const UnknownActionType = "unknown/action"

const services = FakeServices.create(FakeFetch.create({}).fetch)

describe("createCodeSearchStore", () => {
  it("keys the API state by its slice name and passes services to thunks", () => {
    const store = createCodeSearchStore(services)
    expect(Object.keys(store.getState())).toEqual(Object.values(SliceName))
    let received: unknown = null
    store.dispatch((_dispatch, _getState, extra) => {
      received = extra
    })
    expect(received).toBe(services)
  })

  it("starts the auth slice from the token the session holds", () => {
    expect(selectToken(createCodeSearchStore(services).getState())).toBe(
      FakeServices.TestToken
    )
    expect(
      selectToken(
        createCodeSearchStore(
          FakeServices.create(FakeFetch.create({}).fetch, {
            token: FakeServices.NoToken
          })
        ).getState()
      )
    ).toBeUndefined()
  })

  it("starts from a preloaded state when given one", () => {
    const seeded = createCodeSearchStore(services),
      preloaded = seeded.getState(),
      store = createCodeSearchStore(services, preloaded)
    expect(store.getState()).toEqual(preloaded)
  })

  it("leaves the state unchanged for an action no slice handles", () => {
    const store = createCodeSearchStore(services)
    // The first action through the store registers the API middleware in the API's state.
    store.dispatch({ type: UnknownActionType })
    const before = store.getState()
    store.dispatch({ type: UnknownActionType })
    expect(store.getState()).toBe(before)
  })
})
