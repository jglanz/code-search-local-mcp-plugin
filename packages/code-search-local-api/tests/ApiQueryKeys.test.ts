import { describe, expect, it } from "@jest/globals"

import { ApiQueryKeys } from "@code-search-local/code-search-local-api"

import { OpenApiDocument } from "./common/OpenApiDocument.js"

/** Where a query parameter travels. */
const QueryLocation = "query"

/**
 * The query parameter names of one operation.
 *
 * @param operationId the operation id.
 * @returns its query parameter names.
 */
function queryNames(operationId: string): string[] {
  return OpenApiDocument.findOperation(operationId)
    .parameters.filter(parameter => parameter.in === QueryLocation)
    .map(({ name }) => name)
}

describe("ApiQueryKeys", () => {
  it("names the project query parameter of getStats and getPaths", () => {
    expect(queryNames("getStats")).toEqual([ApiQueryKeys.Project])
    expect(queryNames("getPaths")).toEqual([ApiQueryKeys.Project])
  })

  it("is not a parameter of routes that take none", () => {
    expect(queryNames("getHealth")).not.toContain(ApiQueryKeys.Project)
    expect(OpenApiDocument.findOperation("noSuchOperation")).toBeUndefined()
  })
})
