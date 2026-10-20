/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { screen } from "@testing-library/react"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  HitMiss,
  HitMissMeter,
  HitMissPanel
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** The panel's heading. */
const Title = "Search quality"

/** The meters' test id scope. */
const Scope = "project"

/**
 * Render the panel for a source.
 *
 * @param source the project.
 */
function renderPanel(source = ApiFixtures.Project): void {
  RenderWithStore.render(
    <HitMissPanel
      source={source}
      threshold={ApiFixtures.SearchHitMinScore}
      title={Title}
      scope={Scope}
    />,
    RenderWithStore.newServices(FakeFetch.create({}).fetch)
  )
}

describe("HitMissPanel", () => {
  it("shows one meter per measure under its heading", () => {
    renderPanel()
    expect(screen.getByRole("heading", { name: Title })).toBeInTheDocument()
    expect(screen.getAllByRole("meter")).toHaveLength(HitMiss.Kinds.length)
    HitMiss.Kinds.forEach(kind =>
      expect(
        screen.getByTestId(HitMissMeter.testIdOf(Scope, kind))
      ).toBeInTheDocument()
    )
  })

  it("still shows every measure for a project without searches", () => {
    renderPanel(ApiFixtures.IdleProject)
    expect(screen.getAllByTestId(HitMissMeter.RateTestId)).toHaveLength(
      HitMiss.Kinds.length
    )
  })
})
