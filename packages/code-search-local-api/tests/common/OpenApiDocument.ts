import { readFileSync } from "node:fs"
import path from "node:path"

import { parse } from "yaml"

/** One documented parameter of an operation. */
export interface DocumentedParameter {
  /** The parameter name. */
  name: string

  /** Where it travels: `query`, `path`, … */
  in: string
}

/** One documented operation (the fields the tests read). */
export interface DocumentedOperation {
  /** The operation id the generator names types after. */
  operationId: string

  /** Its parameters, `$ref`s resolved. */
  parameters: DocumentedParameter[]
}

/** An operation as written in the document (parameters may be `$ref`s). */
export interface RawOperation {
  /** The operation id. */
  operationId: string

  /** Parameters or `$ref`s to `components.parameters`; absent when it takes none. */
  parameters?: unknown[]
}

/** The package's `openapi.yaml`, parsed, with the lookups the tests need. */
export namespace OpenApiDocument {
  /** The document every model is generated from. */
  export const DocumentPath = path.resolve(
    import.meta.dirname,
    "..",
    "..",
    "openapi.yaml"
  )

  /** Prefix of every JSON API route (the web UI routes are outside it). */
  export const ApiPrefix = "/api/v1/"

  /** Prefix of a parameter `$ref` into `components.parameters`. */
  export const ParameterRefPrefix = "#/components/parameters/"

  /** The parsed document. */
  export const Document = parse(readFileSync(DocumentPath, "utf8"))

  /**
   * Every documented route.
   *
   * @returns the keys of `paths`.
   */
  export function listPaths(): string[] {
    return Object.keys(Document.paths)
  }

  /**
   * Resolve a parameter or its `$ref`.
   *
   * @param parameter the parameter object.
   * @returns the referenced parameter, or `parameter` itself.
   */
  export function resolveParameter(parameter: unknown): DocumentedParameter {
    const { $ref: ref } = parameter as Record<string, string>
    return ref == null
      ? (parameter as DocumentedParameter)
      : Document.components.parameters[ref.slice(ParameterRefPrefix.length)]
  }

  /**
   * Every operation of every route, with path-level and operation-level parameters merged.
   *
   * @returns the operations.
   */
  export function listOperations(): DocumentedOperation[] {
    return Object.values<Record<string, unknown>>(Document.paths).flatMap(
      pathItem => {
        const { parameters: shared = [], ...methods } = pathItem as Record<
          string,
          unknown[]
        >
        return Object.values(methods).map(operation => {
          const { operationId, parameters = [] } =
            operation as unknown as RawOperation
          return {
            operationId,
            parameters: [...shared, ...parameters].map(resolveParameter)
          }
        })
      }
    )
  }

  /**
   * The operation with an id.
   *
   * @param operationId the operation id.
   * @returns the operation, or undefined when none has the id.
   */
  export function findOperation(operationId: string): DocumentedOperation {
    return listOperations().find(
      operation => operation.operationId === operationId
    )
  }
}
