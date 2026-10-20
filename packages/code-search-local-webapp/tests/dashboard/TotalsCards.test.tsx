/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { screen } from "@testing-library/react"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  NoValue,
  TotalsCards,
  formatCount
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

describe("TotalsCards", () => {
  it("shows projects, files, chunks, searches and failures", () => {
    RenderWithStore.render(
      <TotalsCards totals={ApiFixtures.Totals} />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    TotalsCards.Tiles.forEach(({ label, field }) =>
      expect(
        screen.getByTestId(TotalsCards.tileTestIdOf(field))
      ).toHaveTextContent(
        `${label}${formatCount(ApiFixtures.Totals[field] as number)}`
      )
    )
    expect(
      screen.getByRole("region", { name: TotalsCards.Label })
    ).toBeInTheDocument()
  })

  it("shows no value for a counter the totals lack", () => {
    RenderWithStore.render(
      <TotalsCards
        totals={{ ...ApiFixtures.Totals, search_failures: undefined }}
      />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    expect(
      screen.getByTestId(TotalsCards.tileTestIdOf("search_failures"))
    ).toHaveTextContent(NoValue)
  })
})
