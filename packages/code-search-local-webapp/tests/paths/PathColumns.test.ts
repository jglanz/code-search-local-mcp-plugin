import { describe, expect, it } from "@jest/globals"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  NoValue,
  PathColumns,
  PathSortKey
} from "@code-search-local/code-search-local-webapp"

/**
 * The cell text of one column for a row.
 *
 * @param key the column.
 * @param row the row.
 * @returns the formatted value.
 */
function cellOf(key: PathSortKey, row = ApiFixtures.MainPath): string {
  return PathColumns.All.find(column => column.key === key).format(row)
}

describe("PathColumns.All", () => {
  it("has one column per sort key, in sort-key order", () => {
    expect(PathColumns.All.map(({ key }) => key)).toEqual(
      Object.values(PathSortKey)
    )
    expect(cellOf(PathSortKey.path)).toBe(ApiFixtures.MainPath.path)
    expect(cellOf(PathSortKey.hitRatio)).toBe("66.7%")
  })

  it("shows no ratio, score or time for a path never returned", () => {
    expect(cellOf(PathSortKey.hitRatio, ApiFixtures.ReadmePath)).toBe(NoValue)
    expect(cellOf(PathSortKey.bestScore, ApiFixtures.ReadmePath)).toBe(NoValue)
    expect(cellOf(PathSortKey.lastSeenAt, ApiFixtures.ReadmePath)).toBe(NoValue)
  })
})

describe("PathColumns.TopPaths", () => {
  it("drops only the chunk count, which top-path rows do not carry", () => {
    expect(PathColumns.TopPaths.map(({ key }) => key)).toEqual(
      Object.values(PathSortKey).filter(key => key !== PathSortKey.chunks)
    )
  })

  it("never shows a column the indexed-path table lacks", () => {
    expect(
      PathColumns.TopPaths.every(column => PathColumns.All.includes(column))
    ).toBe(true)
  })
})

describe("PathColumns.cellSxOf", () => {
  it("keeps figures and times on one line", () => {
    PathColumns.All.filter(({ key }) => key !== PathSortKey.path).forEach(
      column =>
        expect(PathColumns.cellSxOf(column)).toEqual({ whiteSpace: "nowrap" })
    )
  })

  it("lets only a path wrap", () => {
    expect(PathColumns.cellSxOf(PathColumns.All[0])).toEqual({
      overflowWrap: "anywhere"
    })
  })
})
