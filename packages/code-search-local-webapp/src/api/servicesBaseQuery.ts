import {
  fetchBaseQuery,
  type BaseQueryFn,
  type FetchArgs,
  type FetchBaseQueryError
} from "@reduxjs/toolkit/query/react"

import type { CodeSearchServices } from "../services/CodeSearchServices.js"
import {
  AuthActions,
  selectToken,
  type AuthRootState
} from "../store/auth/AuthSlice.js"

/** HTTP status of a missing or wrong bearer token. */
export const UnauthorizedStatus = 401

/** Request header carrying the bearer token. */
export const AuthorizationHeader = "Authorization"

/** Authentication scheme of the service API (`securitySchemes.bearerAuth`). */
export const BearerScheme = "Bearer"

/**
 * The `Authorization` value for a token.
 *
 * @param token the service token.
 * @returns `Bearer <token>`.
 */
export function newBearerAuthorization(token: string): string {
  return `${BearerScheme} ${token}`
}

/**
 * Base query that reads `fetchFn` and the absolute `apiBaseUrl` from `api.extra` (the store's
 * services) on every call — `fetchBaseQuery` alone fixes its fetch when `createApi` runs — and
 * sends the auth slice's token as `Authorization: Bearer`. A 401 means the token is wrong or
 * gone: it is cleared from the session and the auth slice records the rejection, which brings
 * up the connect screen.
 *
 * @param args the request.
 * @param api the RTK Query API object (its `extra` is the services).
 * @param extraOptions per-endpoint options.
 * @returns the query result.
 */
export const servicesBaseQuery: BaseQueryFn<
  string | FetchArgs,
  unknown,
  FetchBaseQueryError
> = async (args, api, extraOptions) => {
  const { fetchFn, apiBaseUrl, tokenStore } = api.extra as CodeSearchServices,
    token = selectToken(api.getState() as AuthRootState),
    result = await fetchBaseQuery({
      baseUrl: apiBaseUrl,
      fetchFn,
      prepareHeaders: headers => {
        if (token != null)
          headers.set(AuthorizationHeader, newBearerAuthorization(token))
        return headers
      }
    })(args, api, extraOptions)
  if (result.error?.status === UnauthorizedStatus) {
    tokenStore.clear()
    api.dispatch(AuthActions.tokenRejected())
  }
  return result
}
