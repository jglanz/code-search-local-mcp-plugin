/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { screen } from "@testing-library/react"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  NoValue,
  ServiceHeader,
  formatTime
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** When the fixture snapshot was refreshed. */
const RefreshedAt = Date.parse(ApiFixtures.LastSearchAt)

describe("ServiceHeader", () => {
  it("shows online, the daemon, the model, its residency, the threshold and the refresh time", () => {
    RenderWithStore.render(
      <ServiceHeader
        snapshot={ApiFixtures.Snapshot}
        online
        refreshedAt={RefreshedAt}
      />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    expect(screen.getByTestId(ServiceHeader.StatusTestId)).toHaveTextContent(
      ServiceHeader.OnlineLabel
    )
    expect(screen.getByTestId(ServiceHeader.TestId)).toHaveTextContent(
      ApiFixtures.DaemonId
    )
    expect(screen.getByTestId(ServiceHeader.TestId)).toHaveTextContent(
      ApiFixtures.Model.model
    )
    expect(
      ServiceHeader.listFacts(ApiFixtures.Snapshot, RefreshedAt).map(
        ({ value }) => value
      )
    ).toEqual([
      ApiFixtures.DaemonId,
      ApiFixtures.Model.model,
      ApiFixtures.Model.backend,
      ApiFixtures.Model.device,
      ServiceHeader.ResidentLabel,
      "0.50",
      formatTime(RefreshedAt)
    ])
  })

  it("shows offline, and no model facts before a model was loaded", () => {
    const snapshot = {
      ...ApiFixtures.Snapshot,
      online: false,
      shared: { model_resident: false }
    }
    RenderWithStore.render(
      <ServiceHeader
        snapshot={snapshot}
        online={false}
        refreshedAt={RefreshedAt}
      />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    expect(screen.getByTestId(ServiceHeader.StatusTestId)).toHaveTextContent(
      ServiceHeader.OfflineLabel
    )
    expect(
      ServiceHeader.listFacts(snapshot, RefreshedAt).map(({ value }) => value)
    ).toEqual([
      ApiFixtures.DaemonId,
      NoValue,
      NoValue,
      NoValue,
      ServiceHeader.NotResidentLabel,
      NoValue,
      formatTime(RefreshedAt)
    ])
  })
})
