import { describe, expect, it } from "@jest/globals"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  HitMiss,
  HitMissKind,
  NoValue
} from "@code-search-local/code-search-local-webapp"

/** The fixture project's relevance rate, formatted. */
const ProjectRelevanceRate = "66.7%"

describe("HitMiss.of", () => {
  it("reads each measure's counters and ratio from the totals and a project", () => {
    expect(HitMiss.of(ApiFixtures.Totals, HitMissKind.relevance)).toEqual({
      kind: HitMissKind.relevance,
      hits: ApiFixtures.Totals.search_relevance_hits,
      misses: ApiFixtures.Totals.search_relevance_misses,
      ratio: ApiFixtures.Totals.search_relevance_hit_ratio
    })
    expect(HitMiss.of(ApiFixtures.Project, HitMissKind.queryCache)).toEqual({
      kind: HitMissKind.queryCache,
      hits: ApiFixtures.Project.query_cache_hits,
      misses: ApiFixtures.Project.query_cache_misses,
      ratio: ApiFixtures.Project.query_cache_hit_ratio
    })
  })

  it("counts a counter the project has not recorded yet as 0", () => {
    expect(HitMiss.of(ApiFixtures.IdleProject, HitMissKind.results)).toEqual({
      kind: HitMissKind.results,
      hits: 0,
      misses: 0,
      ratio: 0
    })
  })
})

describe("HitMiss.allOf", () => {
  it("returns every measure in display order", () => {
    expect(HitMiss.allOf(ApiFixtures.Totals).map(({ kind }) => kind)).toEqual(
      HitMiss.Kinds
    )
  })

  it("covers every kind exactly once", () => {
    expect([...HitMiss.Kinds].sort()).toEqual(Object.values(HitMissKind).sort())
  })
})

describe("HitMiss.formatRate", () => {
  it("formats the service's ratio as a percentage", () => {
    expect(
      HitMiss.formatRate(HitMiss.of(ApiFixtures.Project, HitMissKind.relevance))
    ).toBe(ProjectRelevanceRate)
  })

  it("shows no rate before the first event instead of 0%", () => {
    expect(
      HitMiss.formatRate(
        HitMiss.of(ApiFixtures.IdleProject, HitMissKind.relevance)
      )
    ).toBe(NoValue)
  })
})

describe("HitMiss.totalOf", () => {
  it("adds hits and misses", () => {
    expect(
      HitMiss.totalOf(HitMiss.of(ApiFixtures.Totals, HitMissKind.results))
    ).toBe(
      ApiFixtures.Totals.search_result_hits +
        ApiFixtures.Totals.search_result_misses
    )
  })

  it("is 0 without events", () => {
    expect(
      HitMiss.totalOf(
        HitMiss.of(ApiFixtures.IdleProject, HitMissKind.queryCache)
      )
    ).toBe(0)
  })
})

describe("HitMiss.labelOf and HitMiss.describe", () => {
  it("names and explains every measure, quoting the threshold for relevance", () => {
    expect(HitMiss.Kinds.map(HitMiss.labelOf)).toEqual([
      HitMiss.RelevanceLabel,
      HitMiss.ResultsLabel,
      HitMiss.QueryCacheLabel
    ])
    expect(
      HitMiss.describe(HitMissKind.relevance, ApiFixtures.SearchHitMinScore)
    ).toContain(String(ApiFixtures.SearchHitMinScore))
  })

  it("gives each measure its own label", () => {
    expect(new Set(HitMiss.Kinds.map(HitMiss.labelOf)).size).toBe(
      HitMiss.Kinds.length
    )
    expect(HitMiss.describe(HitMissKind.results, 0)).toBe(
      HitMiss.ResultsDescription
    )
  })
})
