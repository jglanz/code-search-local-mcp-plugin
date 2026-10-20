# Code Search Local API

`openapi.yaml` (OpenAPI 3.1, JSON Schema 2020-12) is the only place where the
service API models are defined: every HTTP route of the shared service, its
request and response bodies, the statistics snapshot, per-path search analytics
and the pub-sub notification shape. The running service also serves this
document at `GET /api/v1/openapi.json`.

## Generated code

Both languages generate their models from this file at build time:

- **Python**: pydantic v2 models (`code_search_local/api/models.py`) and a JSON
  copy of this document (`code_search_local/api/openapi.json`) inside the
  `code_search_local` package, produced with `datamodel-code-generator` by the
  Hatch build hook `packages/code-search-local/scripts/api_models.py` during
  wheel builds and editable installs. Run `hatch run generate` from the
  repository root to regenerate them in the checkout; `hatch run test`,
  `coverage` and `lint` do so first. The service validates request bodies and
  every `/api/v1` response through these models.
- **TypeScript**: zod 4 schemas and TypeScript types, produced in this
  workspace package under `src/generated/` and consumed by the web dashboard.

Generated outputs are build artifacts and are never committed. Change the API by
editing `openapi.yaml`, then regenerate both languages and rebuild; never edit
generated files. The [web dashboard guide](../../docs/webapp.md#api-contract)
shows the whole flow.

## TypeScript package

`@code-search-local/code-search-local-api` is an ESM workspace package.
`pnpm run generate` runs `@hey-api/openapi-ts` with
`etc/openapi-ts/openapi-ts.config.mjs` and writes `src/generated/` (git-ignored):
the `@hey-api/typescript` types and the zod schemas (`zStatsSnapshot`,
`zPathsResponse`, …). The zod plugin is configured with `dates.offset`, because
the service writes timestamps with a `+00:00` offset. The workspace scripts
`compile`, `build`, `dev`, `test` and `check` generate before anything reads the
output, and `pnpm install` generates through this package's `prepare` script.

The main entry exports the generated schemas and types plus two hand-written
namespaces:

- `ApiPaths`: the route constants clients call. Each one is typed with the
  generated operation's `url`, so a route renamed in the document fails
  type-checking until the constant follows.
- `ApiQueryKeys`: query parameter names, typed the same way.

The `testing` subpath (`@code-search-local/code-search-local-api/testing`)
exports `ApiFixtures`, realistic response bodies for tests of this package and
its clients. Production code never imports it.

## Authoring rules

- Property names are the exact snake_case JSON keys the service emits.
- Every reusable shape is a PascalCase entry under `components/schemas`,
  referenced with `$ref` instead of being repeated inline.
- Closed string sets are `enum`s whose values equal the service constants.
- Nullable values use `type: [<type>, "null"]`; timestamps use
  `format: date-time` (UTC with an offset).
- Every object lists `required` keys explicitly and sets `additionalProperties`
  deliberately: `true` for shapes persisted in service state or extended by
  model backends, `false` for request bodies and freshly computed responses.
- Every schema and property has a concise `description`; numeric limits that the
  service validates are expressed with `minimum` and `maximum`.
