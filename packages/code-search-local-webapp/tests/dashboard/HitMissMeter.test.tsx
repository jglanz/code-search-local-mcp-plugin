/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { screen, within } from "@testing-library/react"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  HitMiss,
  HitMissKind,
  HitMissMeter,
  NoValue
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** The meter's test id scope. */
const Scope = "totals"

/** The fixture totals' relevance rate in percent, rounded as the meter reports it. */
const RelevancePercent = 66.67

/**
 * Render the meter of one measure.
 *
 * @param hitMiss the measure.
 * @returns the meter's root element.
 */
function renderMeter(hitMiss: HitMiss): HTMLElement {
  RenderWithStore.render(
    <HitMissMeter
      hitMiss={hitMiss}
      threshold={ApiFixtures.SearchHitMinScore}
      scope={Scope}
    />,
    RenderWithStore.newServices(FakeFetch.create({}).fetch)
  )
  return screen.getByTestId(HitMissMeter.testIdOf(Scope, hitMiss.kind))
}

describe("HitMissMeter", () => {
  it("shows the rate, a meter at the hit share and both counts in text", () => {
    const meter = renderMeter(
        HitMiss.of(ApiFixtures.Totals, HitMissKind.relevance)
      ),
      bar = within(meter).getByRole("meter", {
        name: `${HitMiss.RelevanceLabel} ${HitMissMeter.MeterLabelSuffix}`
      })
    expect(
      within(meter).getByTestId(HitMissMeter.RateTestId)
    ).toHaveTextContent("66.7%")
    expect(Number(bar.getAttribute("aria-valuenow"))).toBeCloseTo(
      RelevancePercent,
      1
    )
    expect(
      within(meter).getByTestId(HitMissMeter.CountsTestId)
    ).toHaveTextContent(
      `${HitMissMeter.HitsLabel} 2 · ${HitMissMeter.MissesLabel} 1`
    )
    expect(meter).toHaveTextContent(String(ApiFixtures.SearchHitMinScore))
  })

  it("shows no rate and an empty meter before the first event", () => {
    const meter = renderMeter(
        HitMiss.of(ApiFixtures.IdleProject, HitMissKind.queryCache)
      ),
      bar = within(meter).getByRole("meter")
    expect(
      within(meter).getByTestId(HitMissMeter.RateTestId)
    ).toHaveTextContent(NoValue)
    expect(bar).toHaveAttribute("aria-valuenow", "0")
    expect(bar).toHaveAttribute("aria-valuetext", HitMissMeter.NoEventsText)
  })
})
