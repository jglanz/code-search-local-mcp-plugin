/** Construction options for {@link NestedError}. */
export interface NestedErrorOptions {
  /** The error (or value) being wrapped; preserved as the native `cause`. */
  cause?: unknown

  /** Structured values describing what was being done when the error occurred. */
  context?: Record<string, unknown>
}

/**
 * An error that WRAPS its cause instead of restringing it: the original error, its stack and
 * its message survive as the native `cause`, and `context` records what was being attempted.
 */
export class NestedError extends Error {
  /** Structured values describing the failed operation. */
  readonly context: Record<string, unknown>

  /**
   * @param message what failed, in the caller's terms.
   * @param options the wrapped cause and context.
   */
  constructor(
    message: string,
    { cause, context = {} }: NestedErrorOptions = {}
  ) {
    super(message, cause == null ? undefined : { cause })
    this.name = NestedError.Name
    this.context = context
  }

  /**
   * The cause chain, outermost first (this error excluded).
   *
   * @returns every nested cause.
   */
  causes(): unknown[] {
    return NestedError.collectCauses(this.cause, [])
  }
}

/** Companion constants and helpers for {@link NestedError}. */
export namespace NestedError {
  /**
   * Written to `error.name`; changing it changes stack headers and the `name` field of every
   * JSON log line carrying this error.
   */
  export const Name: string = "NestedError"

  /** Deepest cause chain followed by {@link collectCauses}; guards against cyclic causes. */
  export const MaxCauseDepth = 32

  /**
   * Normalise any thrown value to an Error (a non-Error value is wrapped, not restrung).
   *
   * @param value the thrown value.
   * @returns the value itself when it is an Error, else a NestedError carrying it as cause.
   */
  export function toError(value: unknown): Error {
    return value instanceof Error
      ? value
      : new NestedError(String(value), { cause: value })
  }

  /** Between the messages of an error and its causes in {@link describeChain}. */
  export const CauseSeparator = ": "

  /**
   * An error and its cause chain in one line, outermost first: the failure in the caller's
   * terms, then what caused it (a chunk that did not download, the schema problems of a file).
   *
   * @param error the error.
   * @returns e.g. `project status failed to load: fetch failed: connect ECONNREFUSED`.
   */
  export function describeChain(error: Error): string {
    return [error, ...collectCauses(error.cause, [])]
      .map(cause => toError(cause).message)
      .join(CauseSeparator)
  }

  /**
   * Follow `cause` links.
   *
   * @param cause the first cause.
   * @param collected causes found so far.
   * @returns the chain, outermost first.
   */
  export function collectCauses(
    cause: unknown,
    collected: unknown[]
  ): unknown[] {
    if (
      cause == null ||
      collected.length >= MaxCauseDepth ||
      collected.includes(cause)
    )
      return collected
    const next = cause instanceof Error ? cause.cause : null
    return collectCauses(next, [...collected, cause])
  }
}
