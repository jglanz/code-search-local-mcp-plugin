import { describe, expect, it } from "@jest/globals"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  PathSortKey,
  SortDirection,
  filterPathRows,
  sortPathRows,
  sortValueOf
} from "@code-search-local/code-search-local-webapp"

/** A filter text matching only the util path, in another case. */
const UtilFilter = "  STRINGS "

/** A filter text matching nothing. */
const MissingFilter = "no-such-file"

/** The rows, as `getPaths` orders them. */
const Rows = ApiFixtures.Paths.paths

describe("sortValueOf", () => {
  it("reads every column's value", () => {
    expect(
      Object.values(PathSortKey).map(key =>
        sortValueOf(ApiFixtures.MainPath, key)
      )
    ).toEqual([
      ApiFixtures.MainPath.path,
      ApiFixtures.MainPath.chunks,
      ApiFixtures.MainPath.appearances,
      ApiFixtures.MainPath.hits,
      ApiFixtures.MainPath.misses,
      ApiFixtures.MainPath.hit_ratio,
      ApiFixtures.MainPath.top_ranked,
      ApiFixtures.MainPath.best_score,
      Date.parse(ApiFixtures.MainPath.last_seen_at)
    ])
  })

  it("sorts a never-returned path's missing score and time below every real value", () => {
    expect(sortValueOf(ApiFixtures.ReadmePath, PathSortKey.bestScore)).toBe(
      Number.NEGATIVE_INFINITY
    )
    expect(sortValueOf(ApiFixtures.ReadmePath, PathSortKey.lastSeenAt)).toBe(
      Number.NEGATIVE_INFINITY
    )
  })
})

describe("sortPathRows", () => {
  it("sorts by a column in either direction", () => {
    expect(
      sortPathRows(Rows, PathSortKey.appearances, SortDirection.desc).map(
        ({ path }) => path
      )
    ).toEqual([
      ApiFixtures.MainPath.path,
      ApiFixtures.UtilPath.path,
      ApiFixtures.ReadmePath.path
    ])
    expect(
      sortPathRows(Rows, PathSortKey.bestScore, SortDirection.asc)[0].path
    ).toBe(ApiFixtures.ReadmePath.path)
  })

  it("breaks ties by path and never reorders its input", () => {
    const tied = [ApiFixtures.UtilPath, { ...ApiFixtures.MainPath, hits: 0 }],
      sorted = sortPathRows(tied, PathSortKey.hits, SortDirection.desc)
    expect(sorted.map(({ path }) => path)).toEqual([
      ApiFixtures.MainPath.path,
      ApiFixtures.UtilPath.path
    ])
    expect(tied[0]).toBe(ApiFixtures.UtilPath)
  })
})

describe("filterPathRows", () => {
  it("keeps the rows containing the text, ignoring case and surrounding blanks", () => {
    expect(filterPathRows(Rows, UtilFilter)).toEqual([ApiFixtures.UtilPath])
    expect(filterPathRows(Rows, "")).toBe(Rows)
  })

  it("keeps nothing when no path contains the text", () => {
    expect(filterPathRows(Rows, MissingFilter)).toEqual([])
  })
})
