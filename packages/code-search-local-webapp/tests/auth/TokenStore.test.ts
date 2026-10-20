/**
 * @jest-environment jest-fixed-jsdom
 */
import { afterEach, describe, expect, it } from "@jest/globals"

import { TokenStore } from "@code-search-local/code-search-local-webapp"

import { FakeServices } from "../common/FakeServices.js"
import { FakeStorage } from "../common/FakeStorage.js"

/** The page the token fragment arrives on. */
const UiPath = "/ui/projects/abc"

/** A query string kept when the fragment is stripped. */
const Search = "?view=compact"

/** A fragment without a token. */
const OtherFragment = "#section-2"

describe("TokenStore", () => {
  it("writes, reads and clears the token in its storage", () => {
    const storage = FakeStorage.create(),
      store = new TokenStore(storage)
    store.write(FakeServices.TestToken)
    expect(store.read()).toBe(FakeServices.TestToken)
    expect(storage.getItem(TokenStore.StorageKey)).toBe(FakeServices.TestToken)
    store.clear()
    expect(store.read()).toBeUndefined()
  })

  it("reads nothing from an empty storage or an empty value", () => {
    expect(new TokenStore(FakeStorage.create()).read()).toBeUndefined()
    expect(
      new TokenStore(
        FakeStorage.create({ [TokenStore.StorageKey]: FakeServices.NoToken })
      ).read()
    ).toBeUndefined()
  })
})

describe("TokenStore.captureFragment", () => {
  const initialUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`

  afterEach(() => window.history.replaceState(null, "", initialUrl))

  it("stores the fragment's token and removes the fragment, keeping path and query", () => {
    window.history.replaceState(
      null,
      "",
      `${UiPath}${Search}#${TokenStore.FragmentKey}=${FakeServices.TestToken}`
    )
    const store = new TokenStore(FakeStorage.create()),
      historyLength = window.history.length
    expect(store.captureFragment(window.location, window.history)).toBe(
      FakeServices.TestToken
    )
    expect(store.read()).toBe(FakeServices.TestToken)
    expect(window.location.hash).toBe("")
    expect(`${window.location.pathname}${window.location.search}`).toBe(
      `${UiPath}${Search}`
    )
    expect(window.history.length).toBe(historyLength)
  })

  it("leaves the URL and the stored token alone without a token fragment", () => {
    window.history.replaceState(null, "", `${UiPath}${OtherFragment}`)
    const store = new TokenStore(
      FakeStorage.create({ [TokenStore.StorageKey]: FakeServices.TestToken })
    )
    expect(
      store.captureFragment(window.location, window.history)
    ).toBeUndefined()
    expect(window.location.hash).toBe(OtherFragment)
    expect(store.read()).toBe(FakeServices.TestToken)
  })

  it("ignores an empty token parameter", () => {
    window.history.replaceState(
      null,
      "",
      `${UiPath}#${TokenStore.FragmentKey}=`
    )
    const store = new TokenStore(FakeStorage.create())
    expect(
      store.captureFragment(window.location, window.history)
    ).toBeUndefined()
    expect(store.read()).toBeUndefined()
  })
})
