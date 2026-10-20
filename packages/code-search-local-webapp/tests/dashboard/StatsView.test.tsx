/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { screen } from "@testing-library/react"

import { ApiPaths } from "@code-search-local/code-search-local-api"
import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  ServiceHeader,
  StatsView,
  ViewState,
  ViewStateKind
} from "@code-search-local/code-search-local-webapp"

import { DashboardRoutes, type FakeRoutes } from "../common/DashboardRoutes.js"
import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** Test id of the body the view renders. */
const BodyTestId = "stats-body"

/**
 * Render the view over a fake service.
 *
 * @param routes the fake's routes.
 */
function renderView(routes: FakeRoutes): void {
  RenderWithStore.render(
    <StatsView>
      {snapshot => <p data-testid={BodyTestId}>{snapshot.daemon_id}</p>}
    </StatsView>,
    RenderWithStore.newServices(FakeFetch.create(routes).fetch)
  )
}

describe("StatsView", () => {
  it("shows loading, then the header (online) above the body", async () => {
    renderView(DashboardRoutes.healthy())
    expect(
      screen.getByTestId(
        ViewState.testIdOf(StatsView.TestId, ViewStateKind.loading)
      )
    ).toHaveTextContent(StatsView.LoadingMessage)
    expect(await screen.findByTestId(BodyTestId)).toHaveTextContent(
      ApiFixtures.DaemonId
    )
    expect(
      await screen.findByText(ServiceHeader.OnlineLabel)
    ).toBeInTheDocument()
  })

  it("marks the service offline when its health check fails", async () => {
    renderView(
      DashboardRoutes.healthy({
        [ApiPaths.Health]: DashboardRoutes.ServerError
      })
    )
    expect(
      await screen.findByText(ServiceHeader.OfflineLabel)
    ).toBeInTheDocument()
  })

  it("shows the error state with the reason when no snapshot loads", async () => {
    renderView(
      DashboardRoutes.healthy({ [ApiPaths.Stats]: DashboardRoutes.ServerError })
    )
    expect(
      await screen.findByTestId(
        ViewState.testIdOf(StatsView.TestId, ViewStateKind.error)
      )
    ).toHaveTextContent("snapshot unavailable")
    expect(screen.queryByTestId(BodyTestId)).not.toBeInTheDocument()
  })
})
