import { describe, expect, it } from "@jest/globals"

import {
  AuthActions,
  AuthSlice,
  SliceName,
  createAuthInitialState,
  selectToken,
  selectTokenRejected
} from "@code-search-local/code-search-local-webapp"

import { FakeServices } from "../../common/FakeServices.js"

/** A token entered after a rejection. */
const NewToken = "new-token-9876543210"

/**
 * The root-state view of an auth state.
 *
 * @param state the auth state.
 * @returns the root-state fragment the selectors read.
 */
function rootOf(state: ReturnType<typeof AuthSlice.reducer>) {
  return { [SliceName.auth]: state }
}

describe("createAuthInitialState", () => {
  it("starts from the session's token, not rejected", () => {
    expect(createAuthInitialState(FakeServices.TestToken)).toEqual({
      token: FakeServices.TestToken,
      rejected: false
    })
  })

  it("starts without a token when the session holds none", () => {
    expect(selectToken(rootOf(createAuthInitialState()))).toBeUndefined()
  })
})

describe("AuthSlice", () => {
  it("records a rejection: the token is gone and the rejection is selectable", () => {
    const state = AuthSlice.reducer(
      createAuthInitialState(FakeServices.TestToken),
      AuthActions.tokenRejected()
    )
    expect(selectToken(rootOf(state))).toBeUndefined()
    expect(selectTokenRejected(rootOf(state))).toBe(true)
  })

  it("a new token clears the rejection", () => {
    const rejected = AuthSlice.reducer(
        createAuthInitialState(FakeServices.TestToken),
        AuthActions.tokenRejected()
      ),
      state = AuthSlice.reducer(
        rejected,
        AuthActions.tokenEntered({ token: NewToken })
      )
    expect(selectToken(rootOf(state))).toBe(NewToken)
    expect(selectTokenRejected(rootOf(state))).toBe(false)
  })
})
