import { describe, expect, it } from "@jest/globals"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  DisplayLocale,
  NoValue,
  formatCount,
  formatDuration,
  formatRatio,
  formatScore,
  formatTime,
  formatTimestamp
} from "@code-search-local/code-search-local-webapp"

/** A count large enough for a thousands separator. */
const LargeCount = 12_345

/** A text that is not a timestamp. */
const NotATimestamp = "yesterday"

describe("formatCount", () => {
  it("separates thousands", () => {
    expect(formatCount(LargeCount)).toBe("12,345")
  })

  it("shows no value for a missing count", () => {
    expect(formatCount(undefined)).toBe(NoValue)
  })
})

describe("formatRatio", () => {
  it("shows a percentage with one decimal", () => {
    expect(formatRatio(ApiFixtures.Totals.search_relevance_hit_ratio)).toBe(
      "66.7%"
    )
  })

  it("shows no value for a missing ratio", () => {
    expect(formatRatio(undefined)).toBe(NoValue)
  })
})

describe("formatScore", () => {
  it("shows two or three decimals", () => {
    expect(formatScore(ApiFixtures.MainPath.best_score)).toBe("0.71")
  })

  it("shows no value for a path never returned", () => {
    expect(formatScore(ApiFixtures.ReadmePath.best_score)).toBe(NoValue)
  })
})

describe("formatDuration", () => {
  it("shows seconds with one decimal", () => {
    expect(formatDuration(ApiFixtures.SucceededJob.duration_seconds)).toBe(
      "7.9 s"
    )
  })

  it("shows no value for a job that has not run", () => {
    expect(formatDuration(undefined)).toBe(NoValue)
  })
})

describe("formatTimestamp", () => {
  it("formats an offset timestamp in the viewer's zone and locale", () => {
    expect(formatTimestamp(ApiFixtures.LastSearchAt)).toBe(
      new Intl.DateTimeFormat(DisplayLocale, {
        dateStyle: "medium",
        timeStyle: "medium"
      }).format(Date.parse(ApiFixtures.LastSearchAt))
    )
  })

  it("shows no value for a missing or unparseable timestamp", () => {
    expect(formatTimestamp(undefined)).toBe(NoValue)
    expect(formatTimestamp(NotATimestamp)).toBe(NoValue)
  })
})

describe("formatTime", () => {
  it("formats a refresh time", () => {
    const now = Date.parse(ApiFixtures.StartedAt)
    expect(formatTime(now)).toBe(
      new Intl.DateTimeFormat(DisplayLocale, { timeStyle: "medium" }).format(
        now
      )
    )
  })

  it("shows no value before the first refresh", () => {
    expect(formatTime(undefined)).toBe(NoValue)
  })
})
