import { describe, expect, it } from "@jest/globals"

import {
  AssertionFailedError,
  NestedError
} from "@code-search-local/code-search-local-webapp"

describe("AssertionFailedError", () => {
  it("is a NestedError carrying its context", () => {
    const error = new AssertionFailedError("expected 2, got 3", { actual: 3 })
    expect(error).toBeInstanceOf(NestedError)
    expect(error.name).toBe(AssertionFailedError.Name)
    expect(error.context).toEqual({ actual: 3 })
  })

  it("defaults to an empty context", () => {
    expect(new AssertionFailedError("m").context).toEqual({})
  })
})
