import { AssertionFailedError } from "../errors/AssertionFailedError.js"

/** A message, or a function building it (only called when the assertion fails). */
export type AssertMessage = string | (() => string)

/**
 * Resolve an {@link AssertMessage}.
 *
 * @param message the message or its builder.
 * @returns the message text.
 */
function resolveMessage(message: AssertMessage): string {
  return typeof message === "function" ? message() : message
}

/**
 * Fail fast when `condition` is falsy. Put the actual value in the message.
 *
 * @param condition the precondition.
 * @param message what was expected and what was found.
 * @throws AssertionFailedError when `condition` is falsy.
 */
export function assert(
  condition: unknown,
  message: AssertMessage
): asserts condition {
  if (!condition)
    throw new AssertionFailedError(resolveMessage(message), { condition })
}

/**
 * Fail fast when `value` is null or undefined, else return it.
 *
 * @param value the value that must be present.
 * @param message what was expected.
 * @returns `value`.
 * @throws AssertionFailedError when `value` is null or undefined.
 */
export function assertDefined<T>(value: T, message: AssertMessage): T {
  if (value == null)
    throw new AssertionFailedError(resolveMessage(message), { value })
  return value
}
