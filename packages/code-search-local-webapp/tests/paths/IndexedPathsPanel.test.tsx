/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { screen } from "@testing-library/react"

import { ApiPaths } from "@code-search-local/code-search-local-api"
import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  IndexedPathsPanel,
  PathTable,
  PathTreeView,
  ViewState,
  ViewStateKind
} from "@code-search-local/code-search-local-webapp"

import { DashboardRoutes, type FakeRoutes } from "../common/DashboardRoutes.js"
import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/**
 * Render the panel over a fake service.
 *
 * @param routes the fake's routes.
 */
function renderPanel(routes: FakeRoutes): void {
  RenderWithStore.render(
    <IndexedPathsPanel projectPath={ApiFixtures.ProjectPath} />,
    RenderWithStore.newServices(FakeFetch.create(routes).fetch)
  )
}

/**
 * The test id of one of the panel's states.
 *
 * @param kind the state.
 * @returns the test id.
 */
function stateTestIdOf(kind: ViewStateKind): string {
  return ViewState.testIdOf(IndexedPathsPanel.TestId, kind)
}

describe("IndexedPathsPanel", () => {
  it("shows loading, then the tree and the table of the committed generation", async () => {
    renderPanel(DashboardRoutes.healthy())
    expect(
      screen.getByTestId(stateTestIdOf(ViewStateKind.loading))
    ).toBeInTheDocument()
    expect(await screen.findByTestId(PathTreeView.TestId)).toBeInTheDocument()
    expect(screen.getByTestId(PathTable.TestId)).toBeInTheDocument()
    expect(screen.getByTestId(IndexedPathsPanel.TestId)).toHaveTextContent(
      ApiFixtures.Generation
    )
  })

  it("explains a project without a committed index", async () => {
    renderPanel(
      DashboardRoutes.healthy({
        [ApiPaths.Paths]: DashboardRoutes.ok(ApiFixtures.NoGenerationPaths)
      })
    )
    expect(
      await screen.findByTestId(stateTestIdOf(ViewStateKind.empty))
    ).toHaveTextContent(IndexedPathsPanel.NotIndexedMessage)
  })

  it("shows the service's reason when the paths fail to load", async () => {
    renderPanel(
      DashboardRoutes.healthy({
        [ApiPaths.Paths]: {
          status: DashboardRoutes.BadRequestStatus,
          body: { error: "Unknown project" }
        }
      })
    )
    expect(
      await screen.findByTestId(stateTestIdOf(ViewStateKind.error))
    ).toHaveTextContent("HTTP 400: Unknown project")
  })
})
