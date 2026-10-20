/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { act, screen } from "@testing-library/react"

import {
  AuthActions,
  AuthGate,
  ConnectScreen
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { FakeServices } from "../common/FakeServices.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** Test id of the gated content. */
const ContentTestId = "gated-content"

/** The gated content. */
const Content = <p data-testid={ContentTestId}>dashboard</p>

describe("AuthGate", () => {
  it("renders its children while a token is known", () => {
    RenderWithStore.render(
      <AuthGate>{Content}</AuthGate>,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    expect(screen.getByTestId(ContentTestId)).toBeInTheDocument()
    expect(screen.queryByTestId(ConnectScreen.TestId)).not.toBeInTheDocument()
  })

  it("swaps the children for the connect screen once the token is rejected", () => {
    const { store } = RenderWithStore.render(
      <AuthGate>{Content}</AuthGate>,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    act(() => {
      store.dispatch(AuthActions.tokenRejected())
    })
    expect(screen.queryByTestId(ContentTestId)).not.toBeInTheDocument()
    expect(screen.getByTestId(ConnectScreen.RejectedTestId)).toBeInTheDocument()
  })

  it("shows the connect screen without a token", () => {
    RenderWithStore.render(
      <AuthGate>{Content}</AuthGate>,
      RenderWithStore.newServices(FakeFetch.create({}).fetch, {
        token: FakeServices.NoToken
      })
    )
    expect(screen.getByTestId(ConnectScreen.TestId)).toBeInTheDocument()
  })
})
