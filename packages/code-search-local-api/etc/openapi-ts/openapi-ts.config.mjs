/**
 * `@hey-api/openapi-ts` configuration (`pnpm run generate`): the package's `openapi.yaml` → zod 4
 * schemas and TypeScript types in the git-ignored `src/generated/`, exported through
 * `src/index.ts`. The document is the single source of the service's API models; never edit the
 * generated files.
 *
 * - `dates.offset`: the service writes timestamps with Python's `isoformat()`, which carries a
 *   `+00:00` offset; without it every `date-time` field of a real response fails validation.
 * - `module.extension ".js"`: relative imports between generated files carry `.js`, as Node's
 *   ESM loader (`NodeNext`) and the workspace's `.js` specifier rule require.
 * - `exportFromIndex`: the generated `index.ts` exports the zod schemas next to the types.
 */
import path from "node:path"

/** This package's root. */
const PackagePath = path.resolve(import.meta.dirname, "..", "..")

/** The OpenAPI document every model is generated from. */
export const InputPath = path.join(PackagePath, "openapi.yaml")

/** Where generated code lands (git-ignored; skipped by ESLint, Prettier and check-conventions). */
export const OutputPath = path.join(PackagePath, "src", "generated")

export default {
  input: InputPath,
  output: {
    path: OutputPath,
    module: { extension: ".js" }
  },
  plugins: [
    "@hey-api/typescript",
    { name: "zod", dates: { offset: true }, exportFromIndex: true }
  ]
}
