/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { act, fireEvent, screen } from "@testing-library/react"

import {
  AuthActions,
  ConnectScreen,
  selectToken,
  selectTokenRejected
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { FakeServices } from "../common/FakeServices.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** Only whitespace. */
const BlankToken = "   "

/** A token with surrounding whitespace, as a paste may carry. */
const PastedToken = `  ${FakeServices.TestToken}\n`

/**
 * Render the screen for a session without a token.
 *
 * @returns the render result and the services.
 */
function renderScreen() {
  const services = RenderWithStore.newServices(FakeFetch.create({}).fetch, {
    token: FakeServices.NoToken
  })
  return { ...RenderWithStore.render(<ConnectScreen />, services), services }
}

describe("ConnectScreen", () => {
  it("explains the web command and connects with a pasted token", () => {
    const { store, services } = renderScreen()
    expect(screen.getByTestId(ConnectScreen.TestId)).toHaveTextContent(
      ConnectScreen.WebCommand
    )
    fireEvent.change(screen.getByLabelText(ConnectScreen.TokenLabel), {
      target: { value: PastedToken }
    })
    fireEvent.click(
      screen.getByRole("button", { name: ConnectScreen.ConnectLabel })
    )
    expect(selectToken(store.getState())).toBe(FakeServices.TestToken)
    expect(services.tokenStore.read()).toBe(FakeServices.TestToken)
  })

  it("keeps Connect disabled for a blank token and says when a token was rejected", () => {
    const { store } = renderScreen()
    fireEvent.change(screen.getByLabelText(ConnectScreen.TokenLabel), {
      target: { value: BlankToken }
    })
    expect(
      screen.getByRole("button", { name: ConnectScreen.ConnectLabel })
    ).toBeDisabled()
    expect(
      screen.queryByTestId(ConnectScreen.RejectedTestId)
    ).not.toBeInTheDocument()
    act(() => {
      store.dispatch(AuthActions.tokenRejected())
    })
    expect(screen.getByTestId(ConnectScreen.RejectedTestId)).toHaveTextContent(
      ConnectScreen.RejectedMessage
    )
    expect(selectTokenRejected(store.getState())).toBe(true)
  })
})
