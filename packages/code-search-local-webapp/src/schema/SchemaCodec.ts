import { Either } from "@3fv/prelude-ts"
import { identity } from "lodash-es"
import { match } from "ts-pattern"
import type { z } from "zod"

import { NestedError } from "../errors/NestedError.js"

/**
 * Validates a persisted or wire shape on BOTH ends. Every decode and encode goes through the
 * schema; a failure is a `Left<NestedError>` whose cause is the zod error and whose context
 * names the codec. Create one with {@link SchemaCodec.create}.
 *
 * @typeParam T the validated type (`z.infer` of the schema).
 */
export interface SchemaCodec<T> {
  /** The shape's name, used in failure messages (e.g. `"Progress"`). */
  readonly name: string

  /** The zod schema that defines the shape. */
  readonly schema: z.ZodType<T>

  /**
   * Validate an untrusted value.
   *
   * @param value the value (already JSON-parsed).
   * @returns `Right(value)` when valid, else `Left(NestedError)`.
   */
  decode(value: unknown): Either<NestedError, T>

  /**
   * Parse and validate JSON text.
   *
   * @param text the JSON text.
   * @returns `Right(value)` when the text parses and validates, else `Left(NestedError)`.
   */
  decodeJson(text: string): Either<NestedError, T>

  /**
   * Validate a value before it is persisted or sent.
   *
   * @param value the value.
   * @returns `Right(value)` when valid, else `Left(NestedError)`.
   */
  encode(value: T): Either<NestedError, T>

  /**
   * Validate and serialise to JSON.
   *
   * @param value the value.
   * @param indent JSON indentation (0 for compact).
   * @returns `Right(json)` when valid, else `Left(NestedError)`.
   */
  encodeJson(value: T, indent?: number): Either<NestedError, string>

  /**
   * Decode or throw — for boundaries where an invalid value is a programming error.
   *
   * @param value the value.
   * @returns the validated value.
   * @throws NestedError when invalid.
   */
  assertDecode(value: unknown): T

  /**
   * Encode or throw — for outbound boundaries (an HTTP response) where an invalid value must
   * not reach the wire.
   *
   * @param value the value.
   * @returns the validated value.
   * @throws NestedError when invalid.
   */
  assertEncode(value: T): T
}

/** Companion factory, types and helpers for {@link SchemaCodec}. */
export namespace SchemaCodec {
  /** Which way a value is travelling when validated. */
  export enum Direction {
    decode = "decode",
    encode = "encode"
  }

  /**
   * Create a codec.
   *
   * @param name the shape's name, used in failure messages.
   * @param schema the zod schema that defines the shape.
   * @returns the codec.
   */
  export function create<T>(
    name: string,
    schema: z.ZodType<T>
  ): SchemaCodec<T> {
    const validate = (
        value: unknown,
        direction: Direction
      ): Either<NestedError, T> =>
        match(schema.safeParse(value))
          .with({ success: true }, ({ data }) =>
            Either.right<NestedError, T>(data)
          )
          .otherwise(({ error }) =>
            Either.left<NestedError, T>(
              new NestedError(
                `${name}: ${direction} failed: ${error.issues.map(describeIssue).join("; ")}`,
                {
                  cause: error,
                  context: { codec: name, direction }
                }
              )
            )
          ),
      orThrow = (result: Either<NestedError, T>): T =>
        result.match<T>({
          Left: error => {
            throw error
          },
          Right: identity
        }),
      decode = (value: unknown) => validate(value, Direction.decode),
      encode = (value: T) => validate(value, Direction.encode)
    return {
      name,
      schema,
      decode,
      decodeJson: (text: string) =>
        Either.try<unknown>(() => JSON.parse(text))
          .mapLeft(
            cause =>
              new NestedError(`${name}: invalid JSON`, {
                cause,
                context: { codec: name }
              })
          )
          .flatMap(decode),
      encode,
      encodeJson: (value: T, indent = 0) =>
        encode(value).map(valid => JSON.stringify(valid, null, indent)),
      assertDecode: (value: unknown) => orThrow(decode(value)),
      assertEncode: (value: T) => orThrow(encode(value))
    }
  }

  /**
   * Render one zod issue as `path: message`.
   *
   * @param issue the zod issue.
   * @returns a one-line description.
   */
  export function describeIssue(issue: z.core.$ZodIssue): string {
    const path = issue.path.map(String).join(".")
    return path.length === 0 ? issue.message : `${path}: ${issue.message}`
  }
}
