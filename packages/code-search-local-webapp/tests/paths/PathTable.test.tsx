/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { fireEvent, screen, within } from "@testing-library/react"

import type { PathStat } from "@code-search-local/code-search-local-api"
import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  PathColumns,
  PathSortKey,
  PathTable,
  SortDirection,
  ViewState,
  ViewStateKind
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** A filter text matching only the util path. */
const UtilFilter = "strings"

/** A filter text matching nothing. */
const MissingFilter = "no-such-file"

/** Paths in the order they are shown first: most appearances first. */
const ByAppearances = [
  ApiFixtures.MainPath.path,
  ApiFixtures.UtilPath.path,
  ApiFixtures.ReadmePath.path
]

/**
 * Render the table.
 *
 * @param paths the rows.
 */
function renderTable(paths: PathStat[] = ApiFixtures.Paths.paths): void {
  RenderWithStore.render(
    <PathTable paths={paths} />,
    RenderWithStore.newServices(FakeFetch.create({}).fetch)
  )
}

/**
 * The first cell of every body row.
 *
 * @returns the paths, in display order.
 */
function shownPaths(): string[] {
  return screen
    .getAllByTestId(PathTable.RowTestId)
    .map(row => within(row).getAllByRole("cell")[0].textContent)
}

/**
 * Click a column heading.
 *
 * @param key the column.
 */
function clickHeading(key: PathSortKey): void {
  fireEvent.click(
    screen.getByRole("button", {
      name: new RegExp(
        `^${PathColumns.All.find(column => column.key === key).label}`
      )
    })
  )
}

describe("PathTable", () => {
  it("starts most-returned first and re-sorts on a heading click, reversing on the second", () => {
    renderTable()
    expect(shownPaths()).toEqual(ByAppearances)
    clickHeading(PathSortKey.path)
    expect(shownPaths()).toEqual([...ByAppearances].sort())
    clickHeading(PathSortKey.path)
    expect(shownPaths()).toEqual([...ByAppearances].sort().reverse())
    expect(screen.getByTestId(PathTable.CountTestId)).toHaveTextContent(
      `3 of 3 ${PathTable.FilesUnit}`
    )
  })

  it("filters by path text and shows the empty state when nothing matches", () => {
    renderTable()
    const filter = screen.getByLabelText(PathTable.FilterLabel)
    fireEvent.change(filter, { target: { value: UtilFilter } })
    expect(shownPaths()).toEqual([ApiFixtures.UtilPath.path])
    fireEvent.change(filter, { target: { value: MissingFilter } })
    expect(
      screen.getByTestId(
        ViewState.testIdOf(PathTable.TestId, ViewStateKind.empty)
      )
    ).toHaveTextContent(MissingFilter)
    expect(screen.queryAllByTestId(PathTable.RowTestId)).toEqual([])
  })

  it("pages through more rows than one page holds", () => {
    const many = Array.from(
      { length: PathTable.DefaultRowsPerPage + 1 },
      (_, index) => ({
        ...ApiFixtures.ReadmePath,
        path: `docs/page-${String(index).padStart(3, "0")}.md`
      })
    )
    renderTable(many)
    expect(screen.getAllByTestId(PathTable.RowTestId)).toHaveLength(
      PathTable.DefaultRowsPerPage
    )
    fireEvent.click(screen.getByRole("button", { name: /next page/i }))
    expect(screen.getAllByTestId(PathTable.RowTestId)).toHaveLength(1)
  })
})

describe("PathTable.nextSort", () => {
  it("starts a new column in its default direction", () => {
    const [path, chunks] = PathColumns.All
    expect(PathTable.nextSort(PathTable.DefaultSort, path)).toEqual({
      key: PathSortKey.path,
      direction: SortDirection.asc
    })
    expect(PathTable.nextSort(PathTable.DefaultSort, chunks).direction).toBe(
      SortDirection.desc
    )
  })

  it("reverses the sorted column", () => {
    const appearances = PathColumns.All.find(
      ({ key }) => key === PathTable.DefaultSort.key
    )
    expect(
      PathTable.nextSort(PathTable.DefaultSort, appearances).direction
    ).toBe(SortDirection.asc)
  })
})
