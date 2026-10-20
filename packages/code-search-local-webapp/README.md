# Code Search Local web dashboard

`@code-search-local/code-search-local-webapp` is the browser dashboard of the Code Search Local service: service status, totals, the three search hit/miss rates, the projects, and per project its top paths, indexing jobs and indexed-path tree and table. It is a React 19, MUI 9 and Redux Toolkit (RTK Query) application bundled by webpack 5. The Python service serves the built bundle at `/ui/` and the API it reads at `/api/v1`, so this package has no server of its own. It imports every API schema and type from `@code-search-local/code-search-local-api`, which generates them from `openapi.yaml`.

The [web dashboard guide](../../docs/webapp.md) covers its views, security model, architecture, development, packaging, tests and troubleshooting. TypeScript code follows the workspace [STYLE.md](../../STYLE.md).

## Scripts

Run them from the repository root, whose scripts generate the API schemas first: `pnpm build`, `pnpm dev`, `pnpm test`, `pnpm test:e2e` and `pnpm check`. This package's own scripts are:

| Script          | What it does                                                                                                               |
| --------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `compile`       | Generates the API schemas, then type-checks with `tsc -b`                                                                   |
| `build`         | `compile`, then `build:webpack`                                                                                             |
| `build:webpack` | Production bundle into `dist/` (`etc/webpack/webpack.prod.mjs`), served under `/ui/`                                        |
| `dev`           | webpack-dev-server with hot reload on `127.0.0.1:8100` (`CODE_SEARCH_WEBAPP_DEV_PORT`), proxying `/api` to `CODE_SEARCH_SERVICE_URL` (default `http://127.0.0.1:8000`) |
| `test`          | jest suites under `tests/` (the end-to-end specs excluded)                                                                  |
| `test:e2e`      | Playwright specs under `tests/e2e` against the Python test daemon (`etc/playwright/playwright.config.ts`)                  |
| `clean`         | Removes `lib/` and `dist/`                                                                                                  |

`dist/` and `lib/` are build output and are never committed.
