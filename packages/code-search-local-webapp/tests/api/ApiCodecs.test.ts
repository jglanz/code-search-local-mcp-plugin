import { describe, expect, it } from "@jest/globals"
import { z } from "zod"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  ApiCodecs,
  NestedError
} from "@code-search-local/code-search-local-webapp"

describe("ApiCodecs", () => {
  it("decodes the service's responses with +00:00 timestamps", () => {
    expect(
      ApiCodecs.StatsSnapshotCodec.decode(ApiFixtures.Snapshot).getOrThrow()
    ).toEqual(ApiFixtures.Snapshot)
    expect(
      ApiCodecs.PathsResponseCodec.decode(ApiFixtures.Paths).getOrThrow()
    ).toEqual(ApiFixtures.Paths)
    expect(
      ApiCodecs.HealthResponseCodec.decode(ApiFixtures.Health).getOrThrow()
    ).toEqual(ApiFixtures.Health)
  })

  it("rejects a body that breaks the document with a NestedError naming the shape", () => {
    const error = ApiCodecs.PathsResponseCodec.decode({
      ...ApiFixtures.Paths,
      paths: [{ ...ApiFixtures.MainPath, hit_ratio: 2 }]
    }).getLeftOrThrow()
    expect(error).toBeInstanceOf(NestedError)
    expect(error.message).toContain(
      "PathsResponse: decode failed: paths.0.hit_ratio"
    )
  })
})

describe("ApiCodecs.newApiCodec", () => {
  it("validates with the schema it is given", () => {
    const codec = ApiCodecs.newApiCodec<number>("Count", z.int())
    expect(codec.decode(3).getOrThrow()).toBe(3)
  })

  it("fails on a value outside the schema", () => {
    const codec = ApiCodecs.newApiCodec<number>("Count", z.int())
    expect(codec.decode("three").isLeft()).toBe(true)
  })
})
