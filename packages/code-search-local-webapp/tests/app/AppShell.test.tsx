/**
 * @jest-environment jest-fixed-jsdom
 */
import { afterEach, describe, expect, it, jest } from "@jest/globals"
import { render, screen } from "@testing-library/react"

import {
  AppRoutePaths,
  AppShell,
  AppTitle,
  ConnectScreen,
  OverviewPage
} from "@code-search-local/code-search-local-webapp"

import { DashboardRoutes } from "../common/DashboardRoutes.js"
import { FakeFetch } from "../common/FakeFetch.js"
import { FakeServices } from "../common/FakeServices.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

describe("AppShell", () => {
  afterEach(() => jest.restoreAllMocks())

  it("titles the app with a link to the overview above the routed page", () => {
    RenderWithStore.renderRoutes(
      RenderWithStore.newServices(
        FakeFetch.create(DashboardRoutes.healthy()).fetch
      )
    )
    expect(screen.getByTestId(OverviewPage.TestId)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: AppTitle.Name })).toHaveAttribute(
      "href",
      AppRoutePaths.Overview
    )
  })

  it("shows the connect screen instead of the page without a token", () => {
    const fake = FakeFetch.create(DashboardRoutes.healthy())
    RenderWithStore.renderRoutes(
      RenderWithStore.newServices(fake.fetch, { token: FakeServices.NoToken })
    )
    expect(screen.getByTestId(ConnectScreen.TestId)).toBeInTheDocument()
    expect(screen.queryByTestId(OverviewPage.TestId)).not.toBeInTheDocument()
    expect(fake.requestedUrls).toEqual([])
  })

  it("fails outside a router", () => {
    // React reports the render error on the console before rethrowing it. The message differs
    // between react-router's development and production builds, so only the throw is asserted.
    jest.spyOn(console, "error").mockImplementation(() => {})
    expect(() => render(<AppShell />)).toThrow()
  })
})
