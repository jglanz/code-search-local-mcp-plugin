/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { screen, within } from "@testing-library/react"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  AppRoutePaths,
  NoValue,
  ProjectsTable,
  ViewState,
  ViewStateKind
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** The fixture project's three rates and active jobs, in column order. */
const ProjectRates = ["66.7%", "100.0%", "33.3%"]

describe("ProjectsTable", () => {
  it("lists each project with its figures, rates and active jobs, linking to its page", () => {
    RenderWithStore.render(
      <ProjectsTable snapshot={ApiFixtures.Snapshot} />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    const row = screen.getByTestId(
        ProjectsTable.rowTestIdOf(ApiFixtures.ProjectId)
      ),
      cells = within(row)
        .getAllByRole("cell")
        .map(cell => cell.textContent)
    expect(
      screen.getAllByRole("columnheader").map(cell => cell.textContent)
    ).toEqual(ProjectsTable.Columns.map(({ label }) => label))
    expect(cells.slice(-4)).toEqual([...ProjectRates, "1"])
    expect(
      within(row).getByRole("link", { name: ApiFixtures.ProjectPath })
    ).toHaveAttribute("href", AppRoutePaths.projectPath(ApiFixtures.ProjectId))
  })

  it("shows no rates for a project never searched, and an empty state without projects", () => {
    const { unmount } = RenderWithStore.render(
      <ProjectsTable snapshot={ApiFixtures.Snapshot} />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    const idle = screen.getByTestId(
      ProjectsTable.rowTestIdOf(ApiFixtures.IdleProjectId)
    )
    expect(
      within(idle)
        .getAllByRole("cell")
        .slice(-4)
        .map(cell => cell.textContent)
    ).toEqual([NoValue, NoValue, NoValue, "0"])
    unmount()
    RenderWithStore.render(
      <ProjectsTable snapshot={{ ...ApiFixtures.Snapshot, projects: {} }} />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    expect(
      screen.getByTestId(
        ViewState.testIdOf(ProjectsTable.TestId, ViewStateKind.empty)
      )
    ).toHaveTextContent(ProjectsTable.EmptyMessage)
  })
})
