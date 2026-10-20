import { describe, expect, it } from "@jest/globals"

import {
  AssertionFailedError,
  assert,
  assertDefined
} from "@code-search-local/code-search-local-webapp"

describe("assert", () => {
  it("passes a truthy condition", () => {
    expect(() => assert(1 + 1 === 2, "math works")).not.toThrow()
  })

  it("throws with the (lazily built) message for a falsy condition", () => {
    const actual: number = 3
    expect(() =>
      assert(actual === 2, () => `expected 2, got ${actual}`)
    ).toThrow(new AssertionFailedError("expected 2, got 3"))
  })
})

describe("assertDefined", () => {
  it("returns a present value", () => {
    expect(assertDefined(0, "zero is present")).toBe(0)
  })

  it("throws for null and undefined", () => {
    expect(() => assertDefined(null, "need a value")).toThrow(
      AssertionFailedError
    )
    expect(() => assertDefined(undefined, "need a value")).toThrow(
      "need a value"
    )
  })
})
