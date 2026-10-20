import type { FetchArgs, FetchBaseQueryError } from "@reduxjs/toolkit/query"

import type { SchemaCodec } from "../schema/SchemaCodec.js"

/** A successful `queryFn` result. */
export interface CodecQueryData<T> {
  /** The validated body. */
  data: T
}

/** A failed `queryFn` result. */
export interface CodecQueryError {
  /** The transport or validation failure. */
  error: FetchBaseQueryError
}

/** Result shape RTK Query expects from a `queryFn`. */
export type CodecQueryResult<T> = CodecQueryData<T> | CodecQueryError

/** The base query RTK Query hands a `queryFn` (its result is validated by the codec). */
export type CodecBaseQuery = (request: string | FetchArgs) => unknown

/** A `queryFn` whose body is validated by a codec. */
export type CodecQueryFn<Arg, T> = (
  arg: Arg,
  api: unknown,
  extraOptions: unknown,
  baseQuery: CodecBaseQuery
) => Promise<CodecQueryResult<T>>

/**
 * RTK Query's error status for a failure that is not an HTTP status. It must stay the literal
 * `FetchBaseQueryError` declares for custom errors: any other value fails type-checking of every
 * codec query, and code that tells validation failures apart by status stops recognising them.
 */
export const CustomErrorStatus = "CUSTOM_ERROR"

/**
 * Validate a base-query result with a codec: a transport error passes through, a body that
 * fails the generated schema becomes a `CUSTOM_ERROR` carrying the codec's message and context
 * — never a mistyped object handed to components.
 *
 * @param result the base query's result.
 * @param codec the codec of the expected body.
 * @returns the validated data or an error.
 */
export function decodeQueryResult<T>(
  result: CodecQueryResult<unknown>,
  codec: SchemaCodec<T>
): CodecQueryResult<T> {
  if ("error" in result) return result
  return codec.decode(result.data).match<CodecQueryResult<T>>({
    Left: error => ({
      error: {
        status: CustomErrorStatus,
        error: error.message,
        data: error.context
      }
    }),
    Right: data => ({ data })
  })
}

/**
 * A `queryFn` that sends the request `toRequest` builds and validates the body with `codec`.
 *
 * @param codec the codec of the expected body.
 * @param toRequest the request (a path, or fetch args) for an endpoint argument.
 * @returns the query function.
 */
export function newCodecQueryFn<Arg, T>(
  codec: SchemaCodec<T>,
  toRequest: (arg: Arg) => string | FetchArgs
): CodecQueryFn<Arg, T> {
  return async (arg, _api, _extraOptions, baseQuery) =>
    decodeQueryResult(
      (await baseQuery(toRequest(arg))) as CodecQueryResult<unknown>,
      codec
    )
}
