import { describe, expect, it } from "@jest/globals"

import {
  zHealthResponse,
  zPathsResponse,
  zStatsSnapshot
} from "@code-search-local/code-search-local-api"
import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"

/** A timestamp without an offset (a naive Python `datetime.isoformat()`). */
const NaiveTimestamp = "2026-10-19T14:05:12.345678"

/** A UTC timestamp written with `Z` instead of `+00:00`. */
const ZuluTimestamp = "2026-10-19T14:05:12Z"

/** A ratio outside 0..1. */
const InvalidRatio = 1.5

/** One more row than `top_paths` may hold. */
const TooManyTopPaths = 11

/** A job status the document does not define. */
const UnknownJobStatus = "paused"

/**
 * The snapshot with its one indexed project replaced.
 *
 * @param project the project's replacement fields.
 * @returns the snapshot.
 */
function withProject(project: Record<string, unknown>): unknown {
  return {
    ...ApiFixtures.Snapshot,
    projects: {
      ...ApiFixtures.Snapshot.projects,
      [ApiFixtures.ProjectPath]: { ...ApiFixtures.Project, ...project }
    }
  }
}

describe("zStatsSnapshot", () => {
  it("parses a full snapshot with every analytics field, +00:00 offsets included", () => {
    const snapshot = zStatsSnapshot.parse(ApiFixtures.Snapshot),
      project = snapshot.projects[ApiFixtures.ProjectPath]
    expect(snapshot).toEqual(ApiFixtures.Snapshot)
    expect(snapshot.totals.search_relevance_hit_ratio).toBe(
      ApiFixtures.Totals.search_relevance_hit_ratio
    )
    expect(snapshot.shared.search_hit_min_score).toBe(
      ApiFixtures.SearchHitMinScore
    )
    expect(project.top_paths.map(({ path }) => path)).toEqual([
      ApiFixtures.MainPath.path,
      ApiFixtures.UtilPath.path
    ])
    expect(project.last_search_at).toBe(ApiFixtures.LastSearchAt)
    expect(
      zStatsSnapshot.safeParse(withProject({ last_search_at: ZuluTimestamp }))
        .success
    ).toBe(true)
  })

  it("parses a project without the optional analytics counters", () => {
    const snapshot = zStatsSnapshot.parse(ApiFixtures.Snapshot)
    expect(
      snapshot.projects[ApiFixtures.IdleProjectPath].search_relevance_hits
    ).toBeUndefined()
  })

  it.each([
    ["missing totals", { ...ApiFixtures.Snapshot, totals: undefined }],
    [
      "a naive timestamp",
      { ...ApiFixtures.Snapshot, started_at: NaiveTimestamp }
    ],
    ["a ratio above 1", withProject({ search_result_hit_ratio: InvalidRatio })],
    ["a negative counter", withProject({ searches: -1 })],
    [
      "too many top paths",
      withProject({
        top_paths: Array(TooManyTopPaths).fill(ApiFixtures.MainPath)
      })
    ],
    [
      "an unknown job status",
      {
        ...ApiFixtures.Snapshot,
        jobs: {
          [ApiFixtures.RunningJobId]: {
            ...ApiFixtures.RunningJob,
            status: UnknownJobStatus
          }
        }
      }
    ]
  ])("rejects %s", (_label, value) => {
    expect(zStatsSnapshot.safeParse(value).success).toBe(false)
  })
})

describe("zPathsResponse", () => {
  it("parses every row, including a never-returned path's nulls", () => {
    expect(zPathsResponse.parse(ApiFixtures.Paths)).toEqual(ApiFixtures.Paths)
    expect(zPathsResponse.parse(ApiFixtures.NoGenerationPaths).generation).toBe(
      null
    )
  })

  it.each([
    [
      "a row without hit_ratio",
      {
        ...ApiFixtures.Paths,
        paths: [{ ...ApiFixtures.MainPath, hit_ratio: undefined }]
      }
    ],
    [
      "a textual best score",
      {
        ...ApiFixtures.Paths,
        paths: [{ ...ApiFixtures.MainPath, best_score: "0.7" }]
      }
    ],
    ["a numeric generation", { ...ApiFixtures.Paths, generation: 7 }],
    [
      "a naive last_seen_at",
      {
        ...ApiFixtures.Paths,
        paths: [{ ...ApiFixtures.MainPath, last_seen_at: NaiveTimestamp }]
      }
    ]
  ])("rejects %s", (_label, value) => {
    expect(zPathsResponse.safeParse(value).success).toBe(false)
  })
})

describe("zHealthResponse", () => {
  it("parses the liveness body", () => {
    expect(zHealthResponse.parse(ApiFixtures.Health)).toEqual(
      ApiFixtures.Health
    )
  })

  it("rejects any status but ok", () => {
    expect(
      zHealthResponse.safeParse({ ...ApiFixtures.Health, status: "down" })
        .success
    ).toBe(false)
  })
})
