# Code Search Local workspace — TypeScript style guide

Conventions for every TypeScript package under `packages/` and every script
under `scripts/`. The Python service package (`packages/code-search-local`)
follows the Python tooling (`hatch run lint`, ruff) instead; the
[constants and duplication rule](.agents/rules/constants-and-duplication.md)
binds both languages.

The rules follow `wire-tools-ts` (`STYLE.md`, `.prettierrc.js`,
`eslint.config.mjs`, `etc/tsconfig/`, `jest.config.ts`) and its baseline
`wire-libraries-ts/STYLE.md`, re-written here: no `@wireio/*` package is a
dependency. Where this file and the reference disagree, the difference is
labelled:

- **[DEVIATION]**: this workspace deliberately differs from the reference.
- **[RELAXATION]**: an override that is looser than the reference, with the
  reason stated.
- **[EXTENSION]**: a documented reference rule that the reference lint does not
  encode, now enforced mechanically.

### Toolchain and config

- **Workspace.**
  - pnpm with `packages/*`, Node ≥24.9.
  - Packages:
    - `code-search-local`: the Python service. Its `package.json` scripts
      delegate to hatch at the workspace root; it has no TypeScript, no
      `tsconfig.json` and no jest project.
    - `code-search-local-webapp`: the React dashboard. The Python service serves
      its bundle under `/ui/` and the API under `/api`, so the webapp has **no
      Node server** of its own.
    - `code-search-local-api`: the service API's models. Its `openapi.yaml` is
      the single source of every wire shape; `pnpm run generate`
      (`@hey-api/openapi-ts`) writes zod schemas and types into the git-ignored
      `src/generated/`, exported with the hand-written `ApiPaths` and
      `ApiQueryKeys` (typed against the generated operations). Its `testing`
      subpath exports response fixtures for tests. The webapp imports wire
      shapes only from this package and compiles its source (webpack alias, jest
      mapper, tsconfig `paths` plus a project reference).
    - A package may hold an `openapi.yaml` from which its build generates
      schemas and types into `src/generated/`. Generated code follows its
      generator's conventions: ESLint, Prettier and `check-conventions` skip
      `src/generated/`, and the document is what gets reviewed. The root
      `generate` script (`pnpm -r --if-present run generate`) runs first in
      `compile`, `compile:watch`, `build`, `dev`, `test` and `check`, and a
      package's `prepare` script regenerates on `pnpm install`.
  - The root solution `tsconfig.json` has `files: []` and references only.
  - Tool configs live under `etc/<tool>/`.
  - There is no husky: `pnpm check` is the gate.
- **[DEVIATION] ESM everywhere.**
  - The **root** `package.json` stays CJS (no `type`), so `.prettierrc.js` and
    root configs are reference-identical.
  - Every TypeScript package has `"type": "module"`.
  - The webapp exports nothing: webpack builds its bundle, and `tsc -b` only
    type-checks it.
- **TypeScript ^6.** The `etc/tsconfig/` hierarchy:
  - **`tsconfig.base.json`** uses the reference values:
    - `strict: false`, `strictNullChecks: false`, `noImplicitAny: false`
    - target `ES2022`, `moduleResolution bundler`
    - `composite`, `incremental`, `declaration`, `declarationMap`,
      `inlineSourceMap`, `isolatedModules`, `experimentalDecorators`,
      `resolveJsonModule`, `skipLibCheck`
    - `paths`: `@code-search-local/<pkg>` and `@code-search-local/<pkg>/*` →
      `src`. These are used by the app/bundler and jest configs only.
  - **`tsconfig.base.esm.json`:** `module NodeNext`,
    `moduleResolution NodeNext`, for code Node runs directly (the Playwright
    config and specs). This makes tsc reject anything Node's strict ESM loader
    would reject at runtime: JSON imports need `with { type: "json" }`, and
    directory subpaths are not allowed.
  - **`tsconfig.base.jest.json`:** ESM, `module NodeNext`,
    `inlineSourceMap: false`, `sourceMap: true`, `types ["node","jest"]`,
    `ignoreDeprecations "6.0"`, mirroring the reference
    `tsconfig.cjs.jest.json`. Each package's `tsconfig.jest.json` sets
    `rootDir tests` and `outDir lib/test` (a base-relative outDir would resolve
    under `etc/tsconfig/`).
  - **Each TypeScript package** has a `tsconfig.json` (solution) that references
    its configs, including `tsconfig.jest.json`.
  - **Sources are `src/*.ts` (suites `tests/`); compiler output goes only to
    `lib/{esm,cjs,test,node}/`** (`*.js`, `*.d.ts`, `*.map`): every package
    tsconfig's `outDir` is one of those four, and nothing is ever emitted under
    `src/`. `check-package-layout` enforces both. Scripts are `.mjs`. Build with
    `pnpm run compile` from the workspace root.
  - Every config that uses `paths` → `src` (`tsconfig.jest.json`) references the
    project it imports (`tsconfig.app.json`), which avoids TS6307. The root
    solution references every package solution.
  - Because each solution config includes `tsconfig.jest.json`, `tsc -b`
    type-checks the tests. ts-jest only transpiles because of `isolatedModules`.
  - **The webapp's `tsconfig.app.json`** (`include ["src"]`) emits to `lib/esm/`
    only because a referenced project may not disable emit; webpack produces the
    real bundle. Its settings:
    - `lib [ESNext, DOM, DOM.Iterable]`, `jsx react-jsx`
    - `types ["webpack/module"]` for the ESM `import.meta.webpackContext` and
      `import.meta.webpackHot`. The CJS forms `require.context` and `module.hot`
      are not used.
    - `src/webpackGlobals.d.ts` declares `module "*.css"`. It is needed because
      TS 6 defaults to `noUncheckedSideEffectImports`.
  - **The webapp's `tsconfig.jest.json`** adds
    `lib [ESNext, DOM, DOM.Iterable]`, `jsx react-jsx`, and
    `types ["node","jest","@testing-library/jest-dom","webpack/module"]`, and
    excludes `tests/e2e`.
  - **The webapp's `tsconfig.playwright.json`** (NodeNext through
    `tsconfig.base.esm.json`, `rootDir "."`, `outDir lib/test`,
    `lib [ESNext, DOM]`, `types ["node"]`,
    `include ["etc/playwright", "tests/e2e"]`) exists because
    `tsconfig.jest.json` excludes `tests/e2e`: without it `tsc -b` would never
    type-check the Playwright config and specs. Its output is never used.
  - **Null handling under `strictNullChecks: false`:** `null` means intentional
    absence. **Never write `?? null` or `| null`**; guard with `!= null`. Use an
    explicit `null` only where it has runtime meaning (JSON persistence).
- **Prettier** (`.prettierrc.js`, using the reference values):
  - `semi: false`, `singleQuote: false`, `trailingComma: "none"`,
    `arrowParens: "avoid"`, `tabWidth: 2`, `quoteProps: "as-needed"`,
    `bracketSpacing: true`, `bracketSameLine: false`, `proseWrap: "always"`,
    `parser: "typescript"`
  - Overrides give `*.md` `parser: "markdown"` and `*.{yaml,yml}`
    `parser: "yaml"` (the API package's `openapi.yaml`).
  - **`.prettierignore`** keeps out the files pnpm writes itself
    (`pnpm-lock.yaml`, `pnpm-workspace.yaml`), the Python package, the agent
    plugin assets (`plugins/`), CI workflows, agent rules, the Python-oriented
    documentation (`README.md`, `CLAUDE.md`, `AGENTS.md`, `docs/*.md`), Python
    environments, agent state, generated code and the deliberately
    non-conforming fixtures.
  - Scripts: `format` (`--write`) and `format:check` (`--check`) over
    `**/*.{ts,tsx,mts,md,yaml,yml}`.
- **ESLint** (`eslint.config.mjs`, flat `tseslint.config`):
  - **Reference-identical:**
    - `@eslint/js` recommended, `typescript-eslint` recommended,
      `eslint-config-prettier` last
    - the local plugin `csl-local/no-identity-arrow`
      (`etc/eslint/codeSearchLocalPlugin.mjs`)
    - every reference `no-restricted-syntax` ban:
      - `BanSwitch`, `BanInlineIife`, `BanNullUnionReturn`,
        `BanInlineTypeLiteral`, `BanPickParameter`
      - `BanStringLiteralUnion`, `BanAsOptionAwait`,
        `BanMemberCoalesceDeclarator`, `BanErrorMessageRestring`,
        `BanBareErrorInHandler`
    - `no-console: error`
    - `id-match` that bans `require[A-Z]`
    - `no-restricted-imports` `**/src/*`
    - the `process.stdout`/`process.stderr` ban
    - `eqeqeq` (null ignored)
    - `no-unused-vars` with `^_`
    - `preserve-caught-error`, `prefer-const`, `no-var`
    - **turned off:** `@typescript-eslint/no-namespace`,
      `@typescript-eslint/no-empty-object-type`,
      `@typescript-eslint/no-explicit-any`. `no-require-imports` stays **on**:
      the reference turned it off for its CJS packages, and that reason does not
      apply to an ESM workspace. Without the first two, companion namespaces and
      `FooConfig extends Required<FooOptions> {}` would fail.
    - `**/*.{js,cjs,mjs,jsx}`, `lib`, `dist`, `*.d.ts`, `src/generated`, the
      Python package, `plugins/`, `.github/`, Python environments, agent state
      and **`scripts/tests/fixtures/**`** are ignored. The fixtures are linted
      only by `lintRules.test.mjs`, with `ignore: false`.
  - **`**/logging/*Appender.ts` and `**/tests/logging/*Appender.test.ts`
    override:**
    - Turns off the stream ban, as in the reference.
    - **[RELAXATION]** Also turns off `no-console`. The reference lifts only the
      stream ban, but the browser `ConsoleAppender` must call `console`.
  - **[EXTENSION] selectors and rules, added so the documented rules are
    machine-checked:**
    - `ExportDefaultDeclaration` and `export { x as default }`. Files override,
      because their consumer loads the default export: `jest.config.ts`,
      `playwright.config.ts`, `etc/playwright/globalSetup.ts` and
      `etc/playwright/globalTeardown.ts` (Playwright loads them by default
      export), and `etc/webpack/webpack.{dev,prod}.mjs` (`webpack --config` and
      `webpack serve --config` load the default export; `.mjs` files are not
      linted, so this exception is documentation only).
    - Relative
      `ImportDeclaration`/`ExportAllDeclaration`/`ExportNamedDeclaration`
      sources not ending in `.js|.mjs|.json|.css|.mdx` (`.mjs` for the webpack
      tooling modules a test imports).
    - `ForStatement`, `ForInStatement` and non-`await` `ForOfStatement`.
      `for await` stays legal for consuming streams.
    - `React.FC`/`FC` type references.
    - `styled()` calls.
    - `export const log`.
    - `IfStatement` testing `.success`, which forces `safeParse` results through
      `Either`.
    - `no-restricted-imports` `paths` banning the root `@mui/material` /
      `@mui/icons-material` imports, so deep imports are required.
    - `linterOptions: { noInlineConfig: true }` plus a lint script of
      `eslint . --max-warnings 0`. With inline config off, an `eslint-disable`
      comment produces a warning, which fails the run, and the rule it targeted
      still fires as an error.
    - `no-restricted-imports` `paths` bans `lodash` and requires
      **`lodash-es`**. Node's ESM loader rejects named imports from CJS `lodash`
      at runtime, even though tsc, jest and webpack accept them.
  - **No grandfather lists.**
- **Bundler: webpack 5.**
  - Configs live in
    `packages/code-search-local-webapp/etc/webpack/webpack.{common,dev,prod}.mjs`.
  - **Loader: `ts-loader` with `transpileOnly`, plus `react-refresh-typescript`
    in development.** No babel or swc: the reference documents that swc
    mis-compiles companion namespaces.
  - Copied from the reference:
    `resolve.extensionAlias {".js": [".ts",".tsx",".js"]}`,
    `fullySpecified: false`.
  - `html-webpack-plugin` renders `resources/index.html`; `output.publicPath` is
    `/ui/`, the service's webapp endpoint, and equals the router basename plus a
    trailing slash (`AppRoutePaths.test` fails when they differ).
  - **Production** (`pnpm build`): `dist/` with content-hashed
    `assets/[name].[contenthash].js` and source maps. The service serves `dist/`
    from a source checkout; wheel builds include it.
  - **[DEVIATION] Development** (`pnpm dev`): `webpack serve` with HMR and React
    Refresh, because there is no Node server to host webpack's middleware. It
    binds loopback on `CODE_SEARCH_WEBAPP_DEV_PORT` (default 8100), serves the
    SPA page for every client-side route (`historyApiFallback` to
    `/ui/index.html`), and proxies `/api` to `CODE_SEARCH_SERVICE_URL` (default
    `http://127.0.0.1:8000`) with `changeOrigin: true` and the outgoing `Origin`
    header removed, because the service rejects foreign origins.
- **Tests: jest 30 + ts-jest 29 in ESM mode.**
  - `useESM: true`, `extensionsToTreatAsEsm [".ts",".tsx"]`,
    `NODE_OPTIONS=--experimental-vm-modules` (already in the reference scripts).
  - ESM dependencies load natively in jest's ESM mode when their package
    declares `"type": "module"` or ships `.mjs` (lodash-es, MUI 9, RTK,
    react-redux all do), so no `transformIgnorePatterns` allow-list is
    configured. Add one, with a `^.+\\.m?js$` ts-jest transform, only for a
    dependency that ships ESM `.js` WITHOUT `"type": "module"`. There is no
    regex shim.
  - `moduleNameMapper` is **ordered**, because jest takes the first match:
    1. `\.css$` → stub
    2. `@code-search-local/*` → `src`
    3. the `.js`-strip pattern, last
  - `moduleFileExtensions` lists `ts` and `tsx` first, so a stray compiler emit
    (`X.js` next to `X.ts`) never shadows the source the `.js`-strip pattern
    resolves; `check-package-layout` rejects such emits under `src/`.
  - Every test does `import { jest } from "@jest/globals"`, because `jest` is
    not a global in ESM mode.
  - Webpack-only modules (anything using `import.meta.webpackContext` or
    `import.meta.webpackHot`) and modules jsdom cannot run are replaced through
    **`moduleNameMapper`** with mocks in `tests/__mocks__/`. Static import
    chains never reach them.
  - `jest.unstable_mockModule` is used only for per-test overrides, followed by
    `await import()`.
  - Component and RTK Query tests use the **`jest-fixed-jsdom`** environment,
    which provides real `fetch`, `Request`, `Response` and streams. RTK Query
    uses a **custom `baseQuery`** that reads `fetchFn` and an absolute
    `apiBaseUrl` from `api.extra`, the services object. Node's `Request` rejects
    relative URLs, and `fetchBaseQuery`'s `fetchFn` is fixed when `createApi`
    runs. In the browser, `apiBaseUrl` is `window.location.origin`.
  - `@jest/globals`, `ts-node` and `jest-fixed-jsdom` are pinned
    devDependencies.
  - `testMatch ["**/*.test.ts","**/*.test.tsx"]`, so jest never picks up
    Playwright `*.spec.ts`.
  - The root multi-project config lists the API package and the webapp (the
    Python package is tested by hatch) and sets `maxWorkers: 2` and
    `workerIdleMemoryLimit "2GB"`.
  - DOM tests opt in per file with the `@jest-environment jest-fixed-jsdom`
    docblock.
  - Versions are pinned for `jest-environment-jsdom`, `@testing-library/react`
    and `@testing-library/jest-dom`.
  - `.mjs` scripts are tested with node:test.
  - Playwright `*.spec.ts` lives in
    `packages/code-search-local-webapp/tests/e2e/`, with config in
    `etc/playwright/`. `outputDir` is an absolute path under `lib/playwright/`:
    a relative path would resolve against `etc/playwright/`, and `dist/` is the
    bundle the service serves. End-to-end runs start the Python service on a
    free port with isolated storage, never on a fixed port.
- **Scripts:**
  - `scripts/<kebab>.mjs` using zx, with `#!/usr/bin/env node`, the executable
    bit, and a JSDoc header covering Usage, Options, Exit codes (0/1/2) and
    Examples.
  - Helpers live in `scripts/common/cli-common.mjs`.
  - **`check-package-layout.mjs` uses a filesystem walk, not git**, so it checks
    the files that exist, tracked or not. Entries that are never authored
    content never count:
    - anywhere (root, package roots, under a package's `src/`): `.cache`,
      `.git`, `.idea`, `.omc`, `.remember`, `.venv`, `.venvs`, `__pycache__`,
      `.pytest_cache`, `.ruff_cache`, `.test-artifacts`;
    - at the root only, the Python tooling's output: `dist`, `logs`,
      `.coverage`, `coverage.json`, `coverage.xml`.
    - Package roots are checked against the reference allow-list (whether or not
      the package has a `package.json` yet):
      - files: `package.json`, `README.md`, `CHANGELOG.md`, `LICENSE`,
        `.gitignore`, `.npmignore`, `tsconfig*.json`, `jest.config.*`,
        `{webpack,esbuild}.config.*`, `openapi.yaml`
      - dirs: `src/`, `tests/`, `bin/`, `scripts/`, `etc/`, `resources/`,
        `lib/`, `dist/`, `node_modules/`
    - A package's `src/` holds no compiler output (`*.js`, `*.d.ts`, `*.map`): a
      stray emit next to its source shadows it for jest and webpack. The
      hand-written `code-search-local-webapp/src/webpackGlobals.d.ts` is
      allow-listed.
    - The **workspace root** is shared with the Python project and is checked
      against its own allow-list: `packages/ etc/ scripts/ docs/ plugins/`
      `.claude-plugin/ .agents/ .claude/ .github/ node_modules/`, `STYLE.md`,
      `README.md`, `CLAUDE.md`, `AGENTS.md`, `LICENSE`, `pyproject.toml`,
      `uv.lock`, the root config files and `.gitignore`.
  - **`check-conventions.mjs`** checks the `src/` and `tests/` of every
    TypeScript package (one whose root holds `tsconfig.json`), so the sample
    TypeScript sources the Python tests index are never checked.
  - **`check.mjs` stage order (single source of truth):** layout → conventions →
    format (`prettier --check`) → lint → **build** → tests (node:test +
    `tsc -b` + jest). The gate covers the TypeScript workspace; the Python
    package is checked by its hatch commands. Each stage runs in its own process
    group with a deadline, as in the reference.
- **`pnpm dev`** runs the webapp's `webpack serve` (see "Bundler"); start the
  Python service separately and point `CODE_SEARCH_SERVICE_URL` at it.

### Code idioms

- **Branching:** `ts-pattern` `match()` instead of `switch`, with
  `.exhaustive()` on enums.
- **`@3fv/prelude-ts`:**
  - `asOption` for nullables.
  - `Either` for error branching; never discard an `Either`.
  - `safeParse` → `Either`.
  - `Either.try` is used only where the result is consumed. Side-effect-only
    swallowing uses a local `guard(fn)`; defaulting uses a local
    `getValue(fn, fallback)`, per baseline STYLE.md:115-141. No code needs them
    yet; the first caller adds them to the webapp's `src/util/guardUtils.ts`.
- **lodash:** named imports from **`lodash-es`** (`defaults`, `identity`,
  `isEqual`, …). This is an ESM consequence; plain `lodash` is banned by lint.
- **Options pattern:** `FooOptions` (all optional),
  `FooConfig extends Required<FooOptions>`, `createFooDefaultOptions()`, merged
  with `defaults({ ...options }, …)`.
- **Classes:** plain `new`-able classes. Use an async static `create()` with a
  private constructor only for async construction or singletons.
- **Companion `namespace`s** hold constants, sub-types and pure helpers,
  including for components (`AppRoutePaths`, `AppTitle`, `NotFoundPage`).
- **String identity enums** (`a = "a"`), never string-literal unions; derive
  unions as `` `${Enum}` ``.
- **Values:** joined `const` declarations, destructuring with defaults instead
  of member `??`, named constants instead of inline literals, numeric separators
  (`16_384`).
- **Files:**
  - Directories are kebab-case.
  - Class, type and component files are PascalCase; utilities are camelCase
    topic files.
  - `index.ts` barrels contain only `export * from "./X.js"`.
  - Relative imports end in `.js`.
  - No `src/` in specifiers, no default exports, no re-exporting third-party
    code.
- **Naming:**
  - Verbs: `assert*`, `create*`, `new*`; never `require*`, `make*` or `apply`.
    Words are spelled out.
  - Suffixes: `Path`, `File`, `Subpath`.
- **Imports:** ordered `node:` built-ins → external → `@code-search-local/*` →
  relative, with blank lines between groups. Use `import type` / inline `type`.
- **JSDoc** on every exported symbol **and every interface field, `XProps`
  fields included**, with `@param` and `@returns`. Constants document what
  changing them affects.
- **Errors:**
  - Fail fast with assertions that include the actual value.
  - Never swallow.
  - A local `NestedError extends Error` uses native `{ cause }` plus `context`.
  - Error handlers wrap rather than rethrow bare (`BanBareErrorInHandler`).
- **Async:**
  - async/await, and `void promise` for fire-and-forget.
  - `Promise.withResolvers()` replaces `Deferred`.
  - Race timers are cleared; module timers are `.unref()`'d.
- **Loops:** `forEach`/`map`/`filter`/`reduce`. `for await` is used only for
  streams.
- **Logging:**
  - Each file does `const log = getLogger(import.meta.url)` **[DEVIATION from
    `__filename`, which follows from ESM]**.
  - `import.meta.url` is replaced at build time by webpack and is native in
    jest-ESM, so one form works in the browser and in tests.
  - No webapp file logs yet, so there is no logging module. The first file that
    needs one adds the local `src/logging/` module (`getLogger`, `Level` enum,
    `Appender` interface, `ConsoleAppender`), following the reference workspace:
    it derives the category from the path after `src/` or `lib/esm/` (e.g.
    `store:createCodeSearchStore`). The `*Appender.ts` lint override below is
    already in place for it.
  - Never `export const log`, never `console`.
- **zod schema-first:** `export const XSchema = z.strictObject(…)`,
  `type X = z.infer<typeof XSchema>`, `z.enum(TsEnum)`. A local `SchemaCodec`
  (zod 4 + prelude-ts) handles every persisted and wire shape. Wire shapes of
  the service's HTTP API come from the schemas generated from its OpenAPI
  document; the webapp never hand-writes them.
- **React:**
  - Function components only; error boundaries are the one class exception.
  - Each component exports an `XProps` interface (JSDoc on every field),
    destructured in the signature.
  - No `React.FC`, one component per `.tsx`, named exports.
  - `React.lazy(() => import("./ProjectPage.js").then(m => ({ default: m.ProjectPage })))`.
  - An async effect is a named inner `async function load()` called as
    `void load()`, never an IIFE (`BanInlineIife`).
- **MUI:** deep default imports, `sx` only, `data-testid`.
  - `createCodeSearchTheme()` →
    `createTheme({ cssVariables: { colorSchemeSelector: "media" }, colorSchemes: { light, dark }, … })`.
  - Root order: `Provider → ThemeProvider → CssBaseline → RouterProvider`.
- **Routing:** a react-router data router. `AppRouter.createRoutes()` is the one
  route table; `AppRouter.createBrowser()` builds the browser router with the
  `/ui` basename, and tests build a memory router from the same table.
- **Redux Toolkit:**
  - Where state lives: server state (service status, totals, projects, paths,
    jobs) is RTK Query cache, refreshed by `pollingInterval`; state of one view
    (sort order, filter text, expanded tree nodes) is component state. The store
    therefore holds only the `CodeSearchApi` reducer. Add a slice only for
    client state that several routes share, and then follow the rules below.
  - Slices at `store/<domain>/<Name>Slice.ts`, with a `SliceName` identity enum.
  - Each slice has `XState`, `createXInitialState()`, `XSlice` and `XActions`.
  - Reducers are past-tense events taking `PayloadAction<NamedPayload>`.
    Payload, route-param and thunk-config types are always **named interfaces**
    (`BanInlineTypeLiteral`).
  - Selectors are plain `selectX(state)` functions.
  - `createCodeSearchStore(services, preloadedState?)` with
    `thunk.extraArgument: services`; typed hooks via `.withTypes<…>()`.
  - **[EXTENSION] RTK Query** (`api/CodeSearchApi.ts`, with tags, plus the
    custom services-backed `baseQuery`) follows baseline STYLE.md:721-748.
- **HTTP:** the API is the Python service's. API paths are named constants in
  one namespace; tests use `get-port` and free ports, never fixed ports.
- **Tests:**
  - `tests/` mirrors `src/`, files are `*.test.ts(x)`.
  - **Every new symbol gets a happy-path test and a failure test.**
  - `tests/common/` holds `FakeX.create()`, `XFixtures` namespaces and
    `RenderWithStore.render()`.
  - `describe("Class.method")`, `screen.getByRole`.

### Conformance matrix (every convention has an enforcer)

| Convention                                                                                                                                                                                              | Enforced by                                                                                                |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| switch, IIFE, null-union return, inline type literal, Pick param, string-literal union, asOption-await, member-coalesce, error restring, bare error in handler                                          | ESLint (reference bans)                                                                                    |
| console, process streams, `src/` imports, `require*` names, eqeqeq, unused vars, prefer-const, no-var, identity arrow                                                                                   | ESLint (reference)                                                                                         |
| default exports, `.js` relative specifiers, for-loops, `React.FC`, `styled()`, MUI root imports, `export const log`, `if (x.success)`, no `eslint-disable`                                              | ESLint **[EXTENSION]**                                                                                     |
| formatting                                                                                                                                                                                              | `prettier --check`                                                                                         |
| type safety                                                                                                                                                                                             | `tsc -b` (includes `tsconfig.jest.json` and `tsconfig.playwright.json`)                                    |
| import group order, barrel shape (`export *` only), PascalCase/camelCase file naming vs primary export, JSDoc on exported symbols **and** interface/Props fields, one component per `.tsx`              | **`scripts/check-conventions.mjs`** (TS compiler API; node:test-tested with per-rule fixtures)             |
| package/root layout                                                                                                                                                                                     | `check-package-layout.mjs`                                                                                 |
| happy- and failure-path test per symbol, Options pattern, companion namespaces, naming verbs/suffixes, NestedError wrapping, Either-not-discarded, **and every other `STYLE.md` rule not listed above** | **Review checklist**: a code review against this file, with every finding resolved before the change lands |

**This file.** `STYLE.md` is on the workspace-root allow-list and is the
document every conventions review is run against.

**Lint fixtures.** `scripts/tests/fixtures/lint/<rule>.ts` holds one violation
per ESLint rule above. `scripts/tests/lintRules.test.mjs` runs the ESLint Node
API with `ignore: false` and asserts that the expected rule fires for each
fixture. `check-conventions` and `check-package-layout` have their own fixture
sets in the same way.

### Wire libs → replacements

| Wire symbol                                         | Replacement                                                |
| --------------------------------------------------- | ---------------------------------------------------------- |
| `getLogger` / `Level` / `Appender` / `FileAppender` | the webapp's `src/logging/` (added with the first logger)  |
| `Deferred`                                          | `Promise.withResolvers()`                                  |
| `guard` / `getValue`                                | the webapp's `src/util/guardUtils.ts` (added when needed)  |
| `assert` / `is*`                                    | the webapp's `src/util/assertUtils.ts` + `lodash-es` `is*` |
| `NestedError`                                       | the webapp's `src/errors/NestedError.ts`                   |
| `SchemaCodec`                                       | the webapp's `src/schema/SchemaCodec.ts`                   |
| `BindConfigProvider`                                | `get-port`                                                 |
