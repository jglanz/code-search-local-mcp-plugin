import { join } from "node:path"

import { z } from "zod"

/** A clean, documented class. */
export class Clean {
  /** The schema. */
  readonly schema = z.string()

  /**
   * Join two segments.
   *
   * @param a first.
   * @param b second.
   * @returns the joined path.
   */
  join(a: string, b: string): string {
    return join(a, b)
  }
}
