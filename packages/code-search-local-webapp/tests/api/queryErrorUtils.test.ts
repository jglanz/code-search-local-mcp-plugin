import { describe, expect, it } from "@jest/globals"

import {
  CustomErrorStatus,
  UnknownQueryErrorMessage,
  describeQueryError
} from "@code-search-local/code-search-local-webapp"

/** RTK Query's status for a transport failure. */
const FetchErrorStatus = "FETCH_ERROR"

/** The service's reason in a sample error body. */
const Reason = "Unknown project: /x"

describe("describeQueryError", () => {
  it("quotes the service's reason with the HTTP status", () => {
    expect(describeQueryError({ status: 400, data: { error: Reason } })).toBe(
      `HTTP 400: ${Reason}`
    )
  })

  it("names transport, validation and thrown failures", () => {
    expect(
      describeQueryError({ status: FetchErrorStatus, error: "Failed to fetch" })
    ).toBe(`${FetchErrorStatus}: Failed to fetch`)
    expect(
      describeQueryError({ status: CustomErrorStatus, error: "decode failed" })
    ).toBe(`${CustomErrorStatus}: decode failed`)
    expect(describeQueryError({ message: "boom" })).toBe("boom")
  })

  it("falls back to a generic text when nothing describes the failure", () => {
    expect(describeQueryError(undefined)).toBe(UnknownQueryErrorMessage)
    expect(describeQueryError({ status: 502, data: "Bad gateway" })).toBe(
      `HTTP 502: ${UnknownQueryErrorMessage}`
    )
    expect(describeQueryError({})).toBe(UnknownQueryErrorMessage)
  })
})
