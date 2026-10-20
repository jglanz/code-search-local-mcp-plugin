/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { render, screen } from "@testing-library/react"

import {
  App,
  AppTitle,
  NotFoundPage,
  OverviewPage
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** A client-side path no route but the fallback serves. */
const UnknownPath = "/no-such-page"

describe("App", () => {
  it("renders the shell and the overview at the root", () => {
    render(
      <App
        services={RenderWithStore.newServices(FakeFetch.create({}).fetch)}
        router={RenderWithStore.newMemoryRouter()}
      />
    )
    expect(
      screen.getByRole("heading", { name: AppTitle.Name })
    ).toBeInTheDocument()
    expect(screen.getByTestId(OverviewPage.TestId)).toBeInTheDocument()
  })

  it("renders the not-found page inside the shell for an unknown path", () => {
    render(
      <App
        services={RenderWithStore.newServices(FakeFetch.create({}).fetch)}
        router={RenderWithStore.newMemoryRouter(UnknownPath)}
      />
    )
    expect(
      screen.getByRole("heading", { name: AppTitle.Name })
    ).toBeInTheDocument()
    expect(screen.getByTestId(NotFoundPage.TestId)).toBeInTheDocument()
  })
})
