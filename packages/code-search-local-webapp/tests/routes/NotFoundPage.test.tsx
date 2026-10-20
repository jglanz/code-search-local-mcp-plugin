/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { screen } from "@testing-library/react"

import {
  AppRoutePaths,
  NotFoundPage
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** A caller-supplied message. */
const ProjectMessage = "No such project."

describe("NotFoundPage", () => {
  it("shows the given message and links back to the overview", () => {
    RenderWithStore.render(
      <NotFoundPage message={ProjectMessage} />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    expect(screen.getByTestId(NotFoundPage.TestId)).toHaveTextContent(
      ProjectMessage
    )
    expect(
      screen.getByRole("link", { name: NotFoundPage.BackLabel })
    ).toHaveAttribute("href", AppRoutePaths.Overview)
  })

  it("falls back to the generic message", () => {
    RenderWithStore.render(
      <NotFoundPage />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    expect(screen.getByTestId(NotFoundPage.TestId)).toHaveTextContent(
      NotFoundPage.DefaultMessage
    )
  })
})
