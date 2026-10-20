import { describe, expect, it } from "@jest/globals"
import { identity } from "lodash-es"

import {
  ApiPaths,
  type HealthResponse
} from "@code-search-local/code-search-local-api"
import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  ApiCodecs,
  CustomErrorStatus,
  decodeQueryResult,
  newCodecQueryFn
} from "@code-search-local/code-search-local-webapp"

/** A liveness body that fails its schema. */
const InvalidHealth = { status: "down" }

describe("decodeQueryResult", () => {
  it("passes valid data through", () => {
    expect(
      decodeQueryResult(
        { data: ApiFixtures.Health },
        ApiCodecs.HealthResponseCodec
      )
    ).toEqual({ data: ApiFixtures.Health })
  })

  it("turns a schema failure into a CUSTOM_ERROR and passes transport errors through", () => {
    const invalid = decodeQueryResult(
        { data: InvalidHealth },
        ApiCodecs.HealthResponseCodec
      ),
      transport = { error: { status: 500, data: {} } }
    expect(invalid).toMatchObject({ error: { status: CustomErrorStatus } })
    expect(decodeQueryResult(transport, ApiCodecs.HealthResponseCodec)).toBe(
      transport
    )
  })
})

describe("newCodecQueryFn", () => {
  it("sends the request built from the argument and decodes the body", async () => {
    const requests: unknown[] = [],
      queryFn = newCodecQueryFn<string, HealthResponse>(
        ApiCodecs.HealthResponseCodec,
        identity
      ),
      result = await queryFn(ApiPaths.Health, null, null, request => {
        requests.push(request)
        return { data: ApiFixtures.Health }
      })
    expect(requests).toStrictEqual([ApiPaths.Health])
    expect(result).toEqual({ data: ApiFixtures.Health })
  })

  it("turns a body that fails the codec into a CUSTOM_ERROR", async () => {
    const queryFn = newCodecQueryFn(
        ApiCodecs.HealthResponseCodec,
        () => ApiPaths.Health
      ),
      result = await queryFn(undefined, null, null, () => ({
        data: InvalidHealth
      }))
    expect(result).toMatchObject({ error: { status: CustomErrorStatus } })
  })
})
