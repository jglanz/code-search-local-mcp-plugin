import { describe, expect, it } from "@jest/globals"

import {
  zJob,
  zPathStat,
  zProjectStats,
  zSearchTotals
} from "@code-search-local/code-search-local-api"
import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"

describe("ApiFixtures", () => {
  it("holds bodies the generated schemas accept unchanged", () => {
    expect(zProjectStats.parse(ApiFixtures.Project)).toEqual(
      ApiFixtures.Project
    )
    expect(zProjectStats.parse(ApiFixtures.IdleProject)).toEqual(
      ApiFixtures.IdleProject
    )
    expect(zJob.parse(ApiFixtures.RunningJob)).toEqual(ApiFixtures.RunningJob)
    expect(zJob.parse(ApiFixtures.SucceededJob)).toEqual(
      ApiFixtures.SucceededJob
    )
    expect(zSearchTotals.parse(ApiFixtures.Totals)).toEqual(ApiFixtures.Totals)
  })

  it("keeps every path row consistent: misses are appearances minus hits", () => {
    ApiFixtures.Paths.paths.forEach(row => {
      expect(zPathStat.parse(row)).toEqual(row)
      expect(row.misses).toBe(row.appearances - row.hits)
    })
    expect(
      zPathStat.safeParse({ ...ApiFixtures.MainPath, appearances: -1 }).success
    ).toBe(false)
  })
})
