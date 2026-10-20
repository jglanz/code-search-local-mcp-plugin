import type { ThunkAction, UnknownAction } from "@reduxjs/toolkit"

import { CodeSearchApi } from "../../api/CodeSearchApi.js"
import type { CodeSearchServices } from "../../services/CodeSearchServices.js"
import { AuthActions, type AuthRootState } from "./AuthSlice.js"

/** A thunk of the auth slice: runs against the store's services. */
export type AuthThunk = ThunkAction<
  void,
  AuthRootState,
  CodeSearchServices,
  UnknownAction
>

/**
 * Connect with a token (pasted on the connect screen): store it for the session, drop every
 * cached response fetched with the previous token, and send the new one from the next request.
 *
 * @param token the service token.
 * @returns the thunk.
 */
export function enterToken(token: string): AuthThunk {
  return (dispatch, _getState, { tokenStore }) => {
    tokenStore.write(token)
    dispatch(CodeSearchApi.util.resetApiState())
    dispatch(AuthActions.tokenEntered({ token }))
  }
}
