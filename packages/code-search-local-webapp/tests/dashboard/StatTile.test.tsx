/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { screen } from "@testing-library/react"

import { StatTile } from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** The tile's test id. */
const TileTestId = "tile"

describe("StatTile", () => {
  it("shows its label above its value", () => {
    RenderWithStore.render(
      <StatTile label="Searches" value="1,284" testId={TileTestId} />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    expect(screen.getByTestId(TileTestId)).toHaveTextContent("Searches1,284")
  })

  it("shows an absent value as given, never blank", () => {
    RenderWithStore.render(
      <StatTile label="Searches" value="—" testId={TileTestId} />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    expect(screen.getByTestId(TileTestId)).toHaveTextContent("—")
  })
})
