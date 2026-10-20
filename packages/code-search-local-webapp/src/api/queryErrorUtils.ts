import { asOption } from "@3fv/prelude-ts"
import type { SerializedError } from "@reduxjs/toolkit"
import type { FetchBaseQueryError } from "@reduxjs/toolkit/query"
import { isString } from "lodash-es"

/** Any error an RTK Query hook reports. */
export type QueryError = FetchBaseQueryError | SerializedError

/** The JSON error body every failed service request carries (`ErrorResponse`). */
export interface ServiceErrorBody {
  /** The service's reason. */
  error: string
}

/** Shown when an error carries no description at all. */
export const UnknownQueryErrorMessage = "unknown error"

/**
 * One line describing a failed query, for an error state: the service's `error` text with its
 * HTTP status, a transport failure (`FETCH_ERROR`), a body that failed its schema
 * (`CUSTOM_ERROR`), or a thrown error.
 *
 * @param error the hook's error.
 * @returns e.g. `HTTP 400: Unknown project: /x` or `FETCH_ERROR: Failed to fetch`.
 */
export function describeQueryError(error: QueryError): string {
  if (error == null) return UnknownQueryErrorMessage
  if (!("status" in error))
    return asOption(error.message).getOrElse(UnknownQueryErrorMessage)
  if ("error" in error) return `${error.status}: ${error.error}`
  const { error: reason } = asOption(error.data as ServiceErrorBody).getOrElse(
    {} as ServiceErrorBody
  )
  return `HTTP ${error.status}: ${isString(reason) ? reason : UnknownQueryErrorMessage}`
}
