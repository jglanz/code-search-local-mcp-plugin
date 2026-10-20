/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { screen } from "@testing-library/react"

import {
  ViewState,
  ViewStateKind
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** The view whose state is shown. */
const Scope = "sample"

/** The state's message. */
const Message = "Loading samples…"

/**
 * Render one state.
 *
 * @param kind the state.
 */
function renderState(kind: ViewStateKind): void {
  RenderWithStore.render(
    <ViewState kind={kind} scope={Scope} message={Message} />,
    RenderWithStore.newServices(FakeFetch.create({}).fetch)
  )
}

describe("ViewState", () => {
  it("announces loading as a status with its message", () => {
    renderState(ViewStateKind.loading)
    expect(screen.getByRole("status")).toHaveTextContent(Message)
    expect(
      screen.getByTestId(ViewState.testIdOf(Scope, ViewStateKind.loading))
    ).toBeInTheDocument()
  })

  it("shows a failure as an alert and an empty view as plain text", () => {
    renderState(ViewStateKind.error)
    expect(screen.getByRole("alert")).toHaveTextContent(Message)
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("renders an empty state without an alert or a spinner", () => {
    renderState(ViewStateKind.empty)
    expect(
      screen.getByTestId(ViewState.testIdOf(Scope, ViewStateKind.empty))
    ).toHaveTextContent(Message)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })
})
