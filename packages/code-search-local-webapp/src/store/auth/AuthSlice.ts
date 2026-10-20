import { createSlice, type PayloadAction } from "@reduxjs/toolkit"

import { SliceName } from "../SliceName.js"

/**
 * Client state of the service connection, shared by every route: the bearer token the API
 * requests carry, and whether the service rejected the last one. The token is also kept in the
 * tab's `sessionStorage` by `TokenStore`; this state is what the UI and the base query read.
 */
export interface AuthState {
  /** The bearer token; undefined until one is captured from the URL or pasted. */
  token: string

  /** The service answered 401 to the last token, which was therefore cleared. */
  rejected: boolean
}

/** Payload of {@link AuthActions.tokenEntered}. */
export interface TokenEnteredPayload {
  /** The token to send from now on. */
  token: string
}

/** The part of the root state the auth selectors read. */
export interface AuthRootState {
  /** The auth slice. */
  [SliceName.auth]: AuthState
}

/**
 * The initial auth state.
 *
 * @param token the token found in `sessionStorage` (or the URL fragment), if any.
 * @returns the state.
 */
export function createAuthInitialState(token?: string): AuthState {
  return { token, rejected: false }
}

/** The auth slice: past-tense events of the connection's token. */
export const AuthSlice = createSlice({
  name: SliceName.auth,
  initialState: createAuthInitialState(),
  reducers: {
    tokenEntered: (state, { payload }: PayloadAction<TokenEnteredPayload>) => {
      state.token = payload.token
      state.rejected = false
    },
    tokenRejected: state => {
      state.token = undefined
      state.rejected = true
    }
  }
})

/** Action creators of {@link AuthSlice}. */
export const AuthActions = AuthSlice.actions

/**
 * The bearer token.
 *
 * @param state the root state.
 * @returns the token, or undefined when none is known.
 */
export function selectToken(state: AuthRootState): string {
  return state[SliceName.auth].token
}

/**
 * Whether the service rejected the last token.
 *
 * @param state the root state.
 * @returns true after a 401, until a new token is entered.
 */
export function selectTokenRejected(state: AuthRootState): boolean {
  return state[SliceName.auth].rejected
}
