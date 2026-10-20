import { describe, expect, it } from "@jest/globals"

import { NestedError } from "@code-search-local/code-search-local-webapp"

describe("NestedError", () => {
  it("keeps the wrapped cause, its stack and the context", () => {
    const root = new Error("socket reset"),
      wrapped = new NestedError("search failed", {
        cause: root,
        context: { project: "/work/repo" }
      })
    expect(wrapped.name).toBe(NestedError.Name)
    expect(wrapped.cause).toBe(root)
    expect(wrapped.context).toEqual({ project: "/work/repo" })
    expect(wrapped.causes()).toEqual([root])
  })

  it("has no cause and an empty context when none is given", () => {
    const bare = new NestedError("plain")
    expect(bare.cause).toBeUndefined()
    expect(bare.context).toEqual({})
    expect(bare.causes()).toEqual([])
  })
})

describe("NestedError.collectCauses", () => {
  it("follows a multi-level chain outermost first", () => {
    const inner = new Error("inner"),
      middle = new NestedError("middle", { cause: inner })
    expect(new NestedError("outer", { cause: middle }).causes()).toEqual([
      middle,
      inner
    ])
  })

  it("stops at MaxCauseDepth on a long chain", () => {
    const head = Array.from(
      { length: NestedError.MaxCauseDepth + 5 },
      (_, index) => index
    ).reduce<Error>(
      (cause, index) => new Error(`level ${index}`, { cause }),
      new Error("root")
    )
    expect(NestedError.collectCauses(head, [])).toHaveLength(
      NestedError.MaxCauseDepth
    )
  })

  it("stops at a cycle", () => {
    const first = new Error("first"),
      second = new Error("second", { cause: first })
    Object.defineProperty(first, "cause", { value: second })
    expect(NestedError.collectCauses(first, [])).toEqual([first, second])
  })
})

describe("NestedError.toError", () => {
  it("returns an Error unchanged", () => {
    const error = new Error("x")
    expect(NestedError.toError(error)).toBe(error)
  })

  it("wraps a non-Error value as the cause", () => {
    const wrapped = NestedError.toError("boom")
    expect(wrapped).toBeInstanceOf(NestedError)
    expect(wrapped.cause).toBe("boom")
  })
})

describe("NestedError.describeChain", () => {
  it("joins the failure with every cause's message, outermost first", () => {
    const error = new NestedError("project status failed to load", {
      cause: new NestedError("fetch failed", {
        cause: new Error("ECONNRESET")
      })
    })
    expect(NestedError.describeChain(error)).toBe(
      "project status failed to load: fetch failed: ECONNRESET"
    )
  })

  it("is the bare message for an error without a cause", () => {
    expect(NestedError.describeChain(new Error("no token"))).toBe("no token")
  })
})
