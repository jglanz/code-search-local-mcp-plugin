/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { screen, within } from "@testing-library/react"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  PathColumns,
  TopPathsTable,
  ViewState,
  ViewStateKind
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

describe("TopPathsTable", () => {
  it("lists the top paths with every column and a bar scaled to the most frequent", () => {
    RenderWithStore.render(
      <TopPathsTable paths={ApiFixtures.Project.top_paths} />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    const table = screen.getByTestId(TopPathsTable.TestId),
      [main, util] = within(table).getAllByTestId(TopPathsTable.BarTestId)
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map(header => header.textContent)
    ).toEqual(PathColumns.TopPaths.map(({ label }) => label))
    expect(table).toHaveTextContent(ApiFixtures.MainPath.path)
    expect(main).toHaveStyle({ width: "100%" })
    expect(window.getComputedStyle(util).width).toMatch(/^33\.3/)
  })

  it("shows the empty state before any search returned a file", () => {
    RenderWithStore.render(
      <TopPathsTable paths={[]} />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    expect(
      screen.getByTestId(
        ViewState.testIdOf(TopPathsTable.TestId, ViewStateKind.empty)
      )
    ).toHaveTextContent(TopPathsTable.EmptyMessage)
    expect(
      screen.queryByTestId(TopPathsTable.BarTestId)
    ).not.toBeInTheDocument()
  })
})
