import { NestedError } from "./NestedError.js"

/** Raised by {@link assert}/{@link assertDefined} when a precondition does not hold. */
export class AssertionFailedError extends NestedError {
  /**
   * @param message the failed condition, including the actual value.
   * @param context structured values about the failed condition.
   */
  constructor(message: string, context: Record<string, unknown> = {}) {
    super(message, { context })
    this.name = AssertionFailedError.Name
  }
}

/** Companion constants for {@link AssertionFailedError}. */
export namespace AssertionFailedError {
  /**
   * Written to `error.name`; changing it changes stack headers and the `name` field of every
   * JSON log line carrying this error.
   */
  export const Name: string = "AssertionFailedError"
}
