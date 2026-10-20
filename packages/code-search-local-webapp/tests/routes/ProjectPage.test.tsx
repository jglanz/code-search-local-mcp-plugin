/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { screen, within } from "@testing-library/react"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  AppRoutePaths,
  AppTitle,
  HitMissKind,
  HitMissMeter,
  JobsPanel,
  NotFoundPage,
  PathTreeView,
  ProjectPage,
  TopPathsTable
} from "@code-search-local/code-search-local-webapp"

import { DashboardRoutes } from "../common/DashboardRoutes.js"
import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** The fixture project's non-empty-results rate. */
const ResultsRate = "100.0%"

/**
 * Render the route table at a project's page.
 *
 * @param projectId the route's project id.
 */
function renderProject(projectId: string): void {
  RenderWithStore.renderRoutes(
    RenderWithStore.newServices(
      FakeFetch.create(DashboardRoutes.healthy()).fetch
    ),
    AppRoutePaths.projectPath(projectId)
  )
}

describe("ProjectPage", () => {
  it("shows the project's rates, top paths, jobs and indexed-path tree", async () => {
    renderProject(ApiFixtures.ProjectId)
    expect(
      await screen.findByRole("heading", { name: ApiFixtures.ProjectPath })
    ).toBeInTheDocument()
    expect(
      within(
        screen.getByTestId(
          HitMissMeter.testIdOf(ProjectPage.HitMissScope, HitMissKind.results)
        )
      ).getByTestId(HitMissMeter.RateTestId)
    ).toHaveTextContent(ResultsRate)
    expect(screen.getByTestId(TopPathsTable.TestId)).toHaveTextContent(
      ApiFixtures.MainPath.path
    )
    expect(
      screen.getByTestId(JobsPanel.rowTestIdOf(ApiFixtures.RunningJobId))
    ).toBeInTheDocument()
    expect(await screen.findByTestId(PathTreeView.TestId)).toBeInTheDocument()
    expect(document.title).toBe(AppTitle.of(ApiFixtures.ProjectPath))
  })

  it("shows the not-found message for an id no project has", async () => {
    renderProject(ApiFixtures.DaemonId)
    expect(await screen.findByTestId(NotFoundPage.TestId)).toHaveTextContent(
      ApiFixtures.DaemonId
    )
    expect(screen.queryByTestId(JobsPanel.TestId)).not.toBeInTheDocument()
  })
})
