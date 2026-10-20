/**
 * @jest-environment jest-fixed-jsdom
 */
import { afterEach, describe, expect, it } from "@jest/globals"
import { screen } from "@testing-library/react"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  AppRoutePaths,
  AppRouter,
  NotFoundPage,
  OverviewPage,
  ProjectPage
} from "@code-search-local/code-search-local-webapp"

import { DashboardRoutes } from "../common/DashboardRoutes.js"
import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** A client-side path no route but the fallback serves. */
const UnknownPath = "/projects/unknown/extra"

/** A browser path outside the basename (the service redirects it; the router matches nothing). */
const OutsideBasenamePath = "/elsewhere"

/** HTTP status react-router reports when no route matches. */
const NotFoundStatus = 404

/**
 * Render the route table at a path over a healthy fake service.
 *
 * @param path the initial path.
 */
function renderAt(path: string): void {
  RenderWithStore.renderRoutes(
    RenderWithStore.newServices(
      FakeFetch.create(DashboardRoutes.healthy()).fetch
    ),
    path
  )
}

describe("AppRouter.createRoutes", () => {
  it("renders the overview at the root", () => {
    renderAt(AppRoutePaths.Overview)
    expect(screen.getByTestId(OverviewPage.TestId)).toBeInTheDocument()
  })

  it("loads the project page for a project path", async () => {
    renderAt(AppRoutePaths.projectPath(ApiFixtures.ProjectId))
    expect(await screen.findByTestId(ProjectPage.TestId)).toBeInTheDocument()
  })

  it("renders the not-found page for an unknown path", () => {
    renderAt(UnknownPath)
    expect(screen.getByTestId(NotFoundPage.TestId)).toBeInTheDocument()
    expect(screen.queryByTestId(OverviewPage.TestId)).not.toBeInTheDocument()
  })
})

describe("AppRouter.createBrowser", () => {
  const initialPath = window.location.pathname

  afterEach(() => window.history.replaceState(null, "", initialPath))

  it("routes the browser path relative to the basename", () => {
    window.history.replaceState(null, "", `${AppRoutePaths.Basename}/`)
    const router = AppRouter.createBrowser()
    try {
      expect(router.basename).toBe(AppRoutePaths.Basename)
      expect(router.state.matches.at(-1).route.path).toBe(
        AppRoutePaths.Overview
      )
      expect(router.state.errors).toBeNull()
    } finally {
      router.dispose()
    }
  })

  it("matches nothing outside the basename and reports a 404", () => {
    window.history.replaceState(null, "", OutsideBasenamePath)
    const router = AppRouter.createBrowser()
    try {
      expect(Object.values(router.state.errors ?? {})).toEqual([
        expect.objectContaining({ status: NotFoundStatus })
      ])
    } finally {
      router.dispose()
    }
  })
})
