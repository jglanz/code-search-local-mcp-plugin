/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { fireEvent, screen, within } from "@testing-library/react"

import { ApiPaths } from "@code-search-local/code-search-local-api"
import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  AppRoutePaths,
  AppTitle,
  HitMissKind,
  HitMissMeter,
  OverviewPage,
  ProjectPage,
  ProjectsTable,
  ServiceHeader,
  StatsView,
  TotalsCards,
  ViewState,
  ViewStateKind
} from "@code-search-local/code-search-local-webapp"

import { DashboardRoutes } from "../common/DashboardRoutes.js"
import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** The totals' relevance rate as the fixture's ratio formats. */
const TotalsRelevanceRate = "66.7%"

describe("OverviewPage", () => {
  it("shows the service header, totals, the totals' hit rates and the projects", async () => {
    RenderWithStore.renderRoutes(
      RenderWithStore.newServices(
        FakeFetch.create(DashboardRoutes.healthy()).fetch
      )
    )
    expect(
      screen.getByRole("heading", { name: OverviewPage.Title })
    ).toBeInTheDocument()
    expect(await screen.findByTestId(ServiceHeader.TestId)).toBeInTheDocument()
    expect(screen.getByTestId(TotalsCards.TestId)).toBeInTheDocument()
    expect(
      within(
        screen.getByTestId(
          HitMissMeter.testIdOf(
            OverviewPage.HitMissScope,
            HitMissKind.relevance
          )
        )
      ).getByTestId(HitMissMeter.RateTestId)
    ).toHaveTextContent(TotalsRelevanceRate)
    expect(
      screen.getByTestId(ProjectsTable.rowTestIdOf(ApiFixtures.ProjectId))
    ).toHaveTextContent(ApiFixtures.ProjectPath)
    expect(document.title).toBe(AppTitle.of(OverviewPage.Title))
  })

  it("opens a project's page from its row", async () => {
    RenderWithStore.renderRoutes(
      RenderWithStore.newServices(
        FakeFetch.create(DashboardRoutes.healthy()).fetch
      ),
      AppRoutePaths.Overview
    )
    fireEvent.click(
      await screen.findByTestId(
        ProjectsTable.rowTestIdOf(ApiFixtures.ProjectId)
      )
    )
    expect(await screen.findByTestId(ProjectPage.TestId)).toBeInTheDocument()
  })

  it("shows the error state when the snapshot cannot be loaded", async () => {
    RenderWithStore.renderRoutes(
      RenderWithStore.newServices(
        FakeFetch.create(
          DashboardRoutes.healthy({
            [ApiPaths.Stats]: DashboardRoutes.ServerError
          })
        ).fetch
      )
    )
    expect(
      await screen.findByTestId(
        ViewState.testIdOf(StatsView.TestId, ViewStateKind.error)
      )
    ).toHaveTextContent(StatsView.ErrorMessage)
    expect(screen.queryByTestId(TotalsCards.TestId)).not.toBeInTheDocument()
  })
})
