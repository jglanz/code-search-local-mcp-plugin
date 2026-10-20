/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { renderHook } from "@testing-library/react"
import { identity } from "lodash-es"
import { Provider } from "react-redux"

import {
  SliceName,
  createCodeSearchStore,
  useCodeSearchDispatch,
  useCodeSearchSelector,
  type CodeSearchStore
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { FakeServices } from "../common/FakeServices.js"

/** What react-redux throws when a hook runs outside a `Provider`. */
const MissingContextPattern = /react-redux context/

/**
 * A wrapper providing `store`.
 *
 * @param store the store.
 * @returns the wrapper component.
 */
function newWrapper(
  store: CodeSearchStore
): (props: React.PropsWithChildren) => React.ReactElement {
  return function StoreWrapper({
    children
  }: React.PropsWithChildren): React.ReactElement {
    return <Provider store={store}>{children}</Provider>
  }
}

const store = createCodeSearchStore(
  FakeServices.create(FakeFetch.create({}).fetch)
)

describe("useCodeSearchSelector", () => {
  it("reads the root state", () => {
    const { result } = renderHook(
      () => useCodeSearchSelector(state => Object.keys(state)),
      { wrapper: newWrapper(store) }
    )
    expect(result.current).toEqual(Object.values(SliceName))
  })

  it("fails outside a Provider", () => {
    expect(() => renderHook(() => useCodeSearchSelector(identity))).toThrow(
      MissingContextPattern
    )
  })
})

describe("useCodeSearchDispatch", () => {
  it("dispatches thunks with the store's services", () => {
    const { result } = renderHook(() => useCodeSearchDispatch(), {
      wrapper: newWrapper(store)
    })
    expect(
      result.current((_dispatch, _getState, extra) => extra)
    ).toMatchObject({ apiBaseUrl: FakeFetch.TestOrigin })
  })

  it("fails outside a Provider", () => {
    expect(() => renderHook(() => useCodeSearchDispatch())).toThrow(
      MissingContextPattern
    )
  })
})
