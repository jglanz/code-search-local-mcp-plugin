/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it, jest } from "@jest/globals"

import { CodeSearchServices } from "@code-search-local/code-search-local-webapp"

/** Any absolute URL; the stubbed fetch never sends it. */
const StubUrl = "http://stub.test/"

describe("CodeSearchServices.createBrowserServices", () => {
  it("uses the window origin as the API base URL", () => {
    expect(CodeSearchServices.createBrowserServices().apiBaseUrl).toBe(
      window.location.origin
    )
  })

  it("delegates fetch to window.fetch and passes its failure through", async () => {
    const original = window.fetch,
      failure = new TypeError("fetch failed"),
      stub = jest.fn(async () => {
        throw failure
      })
    window.fetch = stub as unknown as typeof fetch
    try {
      await expect(
        CodeSearchServices.createBrowserServices().fetchFn(StubUrl)
      ).rejects.toBe(failure)
      expect(stub).toHaveBeenCalledTimes(1)
    } finally {
      window.fetch = original
    }
  })
})
