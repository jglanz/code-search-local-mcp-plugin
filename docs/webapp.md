# Web dashboard

The web dashboard is a browser view of the shared service: its status, totals,
the three search hit/miss rates, every registered project with its top paths,
indexing jobs and indexed files. The Python service serves it at
`<service url>/ui/` (by default `http://127.0.0.1:8000/ui/`); there is no
separate web server to run. The terminal equivalent is
[`code-search-local stats`](tui.md), and both read the same statistics snapshot.

- [Open the dashboard](#open-the-dashboard)
- [Views](#views)
- [Security model](#security-model)
- [Architecture](#architecture)
- [API contract](#api-contract)
- [Development](#development)
- [Build and packaging](#build-and-packaging)
- [Tests and checks](#tests-and-checks)
- [Troubleshooting](#troubleshooting)

## Open the dashboard

```sh
# Print the dashboard URL, which carries the service token, and open it in the default browser.
code-search-local web

# Only print the URL (for example on a remote machine; see "Remote access" below).
code-search-local web --no-open
```

`web` reads the same configuration as every other command and prints
`<service url>/ui/#token=<token>`, where `<token>` is the service token from
`<storage>/auth.json`. From a source checkout, run `hatch run cpu:cli web` (or
your backend prefix). Without a configured service, the command fails with
`Service is not configured; run code-search-local setup`.

To open the dashboard, `web` does not pass the token URL to the browser, whose
command line other local processes can read. It writes a launch page readable
only by you (mode `0600`, in `code-search-local/web/` of the runtime directory
`$XDG_RUNTIME_DIR`, or `/tmp/code-search-local-<uid>` without it) and opens that
file. The page forwards to the printed URL at once, by a meta refresh and a
script, and also shows a link to it. The page stays after the command exits so
the browser can read it; a later `web` run removes launch pages older than five
minutes.

The dashboard needs a build. A source checkout serves
`packages/code-search-local-webapp/dist` once you have run `pnpm install` and
`pnpm build` from the repository root; release wheels built after `pnpm build`
contain a copy. Until a build exists, `/ui/` answers 503 (see
[Build and packaging](#build-and-packaging)).

### Remote access

The service accepts only requests whose `Host` header names a loopback address
with the service's own port: `127.0.0.1:<port>`, `localhost:<port>` or
`[::1]:<port>`. To use the dashboard of a service on another machine, forward
the **same** port number over SSH and open the printed URL locally:

```sh
ssh -L 8000:127.0.0.1:8000 remote-host   # then, on remote-host: code-search-local web --no-open
```

A different local port (for example `-L 9000:127.0.0.1:8000`) sends
`Host: localhost:9000` and is rejected with 403.

## Views

Every page polls the service every 2 seconds (`DashboardPolling.IntervalMs`):
the statistics snapshot (`GET /api/v1/stats`, one request shared by every view),
the health check (`GET /api/v1/health`) and, on a project page, that project's
paths (`GET /api/v1/paths`). The page follows the operating system's light or
dark preference. Numbers, percentages and times use the `en-US` format; times
are shown in the browser's time zone. A value that does not exist yet, such as a
rate before any search, is shown as `—`.

### Service header

Shown above every page:

| Field               | Meaning                                                                                          |
| ------------------- | ------------------------------------------------------------------------------------------------ |
| Online / Offline    | Online while the snapshot is live and both the latest statistics and health requests succeeded   |
| Daemon              | `daemon_id` of the service process; it changes on every restart                                  |
| Model               | `shared.model.model`                                                                             |
| Backend, Device     | `shared.model.backend` and `shared.model.device`                                                 |
| Model resident      | `Loaded` or `Not loaded` (`shared.model_resident`)                                               |
| Relevance threshold | `shared.search_hit_min_score`, the score a search's top result needs to count as a relevance hit |
| Last refresh        | When the displayed snapshot was received                                                         |

Until the first snapshot arrives, the page shows `Loading service statistics…`,
or `Service statistics failed to load: <reason>` when it cannot be fetched. When
a later refresh fails, the page keeps the last snapshot, marks the service
offline, and shows `Showing the last snapshot; the refresh failed: <reason>`;
polling continues and the warning disappears once the service answers again.

### Overview (`/ui/`)

- **Totals:** Projects, Indexed files, Chunks, Searches and Failed searches over
  every registered project (`totals`).
- **Search quality, all projects:** one meter each for Relevance, Non-empty
  results and Query cache. Each shows the hit rate, a bar whose filled share is
  the hit rate, the hit and miss counts, and what a hit means; before the first
  counted event it reads `No searches counted yet`.
- **Projects:** every registered project ordered by root, with Files, Chunks,
  Last indexed, Searches, the three hit rates and Active jobs (queued or
  running). Clicking a row, or the root link, opens the project page.

The three measures are defined in
[search hit and miss statistics](tui.md#search-hit-and-miss-statistics).

### Project page (`/ui/projects/<project_id>`)

`<project_id>` is the SHA-256 of the canonical project root, as in the
snapshot's `project_id`. An id that no registered project has shows
`No registered project has the id <id>`; any other unknown address shows a
not-found message with a link back to the overview. The page is loaded as a
separate script chunk on first visit.

- **Heading and summary:** the project root, then its files, chunks, searches
  and last index time.
- **Search quality:** the project's three meters, as on the overview.
- **Top paths:** the project's `top_paths` (up to ten files, most often returned
  first), with a bar scaling each file's appearances against the most frequent
  one, and Hits, Misses, Hit ratio, Top-ranked, Best score and Last seen. This
  list comes from the per-path history and can include files that are no longer
  indexed.
- **Indexing jobs:** the project's ten most recently queued jobs with status, a
  progress bar and `processed / total` files (an indeterminate bar while an
  active job has not counted its files yet), queue time, duration and error.
- **Indexed paths:** the files of the committed generation from
  `GET /api/v1/paths`, with the generation name:
  - A **directory tree** in which every directory shows the files, appearances,
    hits and misses summed over the files below it. Top-level directories start
    expanded; `Expand all` and `Collapse all` change every directory at once.
  - A **file table** with Path, Chunks, Appearances, Hits, Misses, Hit ratio,
    Top-ranked, Best score and Last seen. It starts sorted by appearances,
    highest first. Clicking a heading sorts by that column, numeric columns
    highest first and Path and Last seen in ascending order, and clicking it
    again reverses the order; ties keep path order. `Filter paths` keeps the
    rows whose path contains the text, ignoring case, and the line beside it
    counts the matches (`3 of 120 files`). Pages hold 25, 50 or 100 rows.
  - A project without a committed index shows that its paths appear after the
    first indexing job succeeds; a cleared index shows that it holds no files.

The per-path values are defined in
[per-path statistics](tui.md#per-path-statistics).

## Security model

The service binds a loopback address only, and every HTTP request, dashboard
files included, must pass its Host/Origin check: `Host` must be one of the
loopback `host:port` pairs above, and an `Origin` header, when present, must be
`http://` plus one of them. Anything else is answered with 403
`Invalid Host or Origin`.

| Route                                         | Token  | Notes                                                                                                                                                                   |
| --------------------------------------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /`, `GET /ui`                            | None   | 307 redirect to `/ui/`                                                                                                                                                  |
| `GET /ui/`, `GET /ui/<path>`                  | None   | Static dashboard files; an extensionless path naming no file returns `index.html`; a missing file with an extension, or a path outside the build directory, returns 404 |
| `/api/v1/*`, including `/api/v1/openapi.json` | Bearer | 401 `Unauthorized` without the service token                                                                                                                            |
| `/mcp`                                        | Bearer | The MCP endpoint                                                                                                                                                        |

The dashboard files contain no data, so they need no token; every figure comes
from the bearer-authenticated `/api/v1` routes. Dashboard responses and
redirects carry:

- `Content-Security-Policy: default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'`
  (scripts and API requests only from the service's own origin, no framing;
  inline styles are allowed for the component library's runtime styles)
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: no-referrer`

Every `index.html` response, including the client-side route fallback, also
carries `Cache-Control: no-cache`, so the browser revalidates the entry page and
always loads the current content-hashed scripts.

**Token handover.** `code-search-local web` puts the token in the URL fragment
(`#token=…`). Browsers never send a fragment to the server, so the token does
not appear in the service's request log. Before the app first renders, it reads
the token once, stores it in the tab's `sessionStorage` under
`code-search-local.token`, and removes the fragment with `history.replaceState`,
which replaces the tab's session history entry, so the token leaves the address
bar and a later bookmark. The browser's global history may still record the
original URL with its fragment; if that matters, open the dashboard in a private
window or clear that history entry. The stored token survives reloads of that
tab and is discarded when the tab is closed. Every API request sends it as
`Authorization: Bearer <token>`. Treat the printed URL like the token itself.

**Connect screen.** Without a stored token, every page shows the connect screen:
run `code-search-local web`, or paste the `token` value of `<storage>/auth.json`
into the `Access token` field. A pasted token is stored the same way and drops
every response cached with the previous one. When the service answers 401, the
dashboard deletes the stored token and returns to the connect screen with
`The service rejected the access token. Connect again with a current token.`

## Architecture

The dashboard is the workspace package
`@code-search-local/code-search-local-webapp`
(`packages/code-search-local-webapp/`), an ESM TypeScript application that
follows the workspace [STYLE.md](../STYLE.md).

| Layer    | Implementation                                                                                                                                                                                                                                                                                                                                                  |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| UI       | React 19 and MUI 9 (`@mui/material`, `@mui/icons-material`, and `@mui/x-tree-view` for the path tree), with light and dark colour schemes selected by the `prefers-color-scheme` media query                                                                                                                                                                    |
| Routing  | A react-router data router with the basename `/ui`: `/` (overview), `/projects/:projectId` (project page, a lazily loaded chunk) and a not-found fallback. The service returns `index.html` for every extensionless path under `/ui/` that names no file, so routes need no service change.                                                                     |
| State    | Redux Toolkit 2: an `auth` slice (token and rejection) and the RTK Query API `CodeSearchApi` with the `getStats`, `getPaths` and `getHealth` queries, polled by the views                                                                                                                                                                                       |
| Requests | A custom base query (`servicesBaseQuery`) takes `fetch`, the absolute API base URL (the page's own origin in the browser) and the token store from injected services, adds the bearer token, and handles 401. Every response body is validated against the generated zod schema before a component sees it; a body that fails validation becomes a query error. |
| Bundle   | webpack 5 with `ts-loader` (`transpileOnly`; `tsc -b` type-checks), html-webpack-plugin with `resources/index.html`, and the public path `/ui/`. The bundle compiles the API package's `src/` directly, so it needs only the generated schemas, not the API package's compiled output.                                                                          |

`etc/webpack/webpack.common.mjs` holds the shared configuration,
`webpack.prod.mjs` the production build (content-hashed
`assets/[name].[contenthash].js` with source maps in `dist/`), and
`webpack.dev.mjs` the development server described below.

In production, the Python service is the only server. It serves the first
dashboard build it finds, checked again on each request, so a new build appears
on the next page load without a restart:

1. `webapp_dir` (`CODE_SEARCH_WEBAPP_DIR`) when configured. It must contain
   `index.html`, and no other location is tried.
2. `packages/code-search-local-webapp/dist` of the source checkout the service
   runs from. Only a service imported from a checkout's
   `packages/code-search-local/src/` uses this location, so an installed package
   never serves files from unrelated parent directories.
3. `code_search_local/assets/webapp` inside the installed package (release
   wheels built after `pnpm build`).

Persist `CODE_SEARCH_WEBAPP_DIR` through `setup`, like other
[configuration](../README.md#configuration-reference); a shell export does not
reach a running user service.

## API contract

`packages/code-search-local-api/openapi.yaml` (OpenAPI 3.1) is the only
definition of the HTTP API: routes, request and response bodies, the statistics
snapshot and the per-path analytics. No model is written by hand in either
language:

```text
packages/code-search-local-api/openapi.yaml
├── TypeScript: @hey-api/openapi-ts (etc/openapi-ts/openapi-ts.config.mjs)
│     → packages/code-search-local-api/src/generated/   types + zod 4 schemas (git-ignored)
│     → exported by @code-search-local/code-search-local-api, imported by the dashboard
└── Python: Hatch build hook packages/code-search-local/scripts/api_models.py (datamodel-code-generator)
      → code_search_local/api/models.py and openapi.json   pydantic v2 models (git-ignored)
      → the service validates request bodies and every /api/v1 response, and serves the document
        at /api/v1/openapi.json
```

- TypeScript generation runs with `pnpm run generate` and before `pnpm compile`,
  `pnpm build`, `pnpm dev`, `pnpm test` and `pnpm check`. The API package also
  exports `ApiPaths` and `ApiQueryKeys`, route and query-parameter constants
  typed against the generated operations, so a route renamed in the document
  fails type-checking until they follow. See
  [its README](../packages/code-search-local-api/README.md).
- Python generation runs with `hatch run generate`, before `hatch run test`,
  `coverage` and `lint`, and in every wheel and editable build.

To change the API, edit `openapi.yaml`, regenerate both sides, update the
service and the dashboard, and rebuild. A dashboard and a service built from
different versions of the document can disagree: the dashboard then reports a
response that fails its schema as an error.

## Development

Prerequisites: Node.js 24.9 or later (development uses 24.18.0), pnpm 12.6.0,
and a service to talk to. From the repository root:

```sh
pnpm install
pnpm dev
```

`pnpm dev` generates the API schemas, then starts webpack-dev-server with hot
module replacement and React Refresh. It serves the dashboard from memory at
`http://127.0.0.1:8100/ui/` and proxies every `/api` request to the service:

| Variable                      | Default                 | Meaning                                             |
| ----------------------------- | ----------------------- | --------------------------------------------------- |
| `CODE_SEARCH_WEBAPP_DEV_PORT` | `8100`                  | Port of the dev server (an integer from 1 to 65535) |
| `CODE_SEARCH_SERVICE_URL`     | `http://127.0.0.1:8000` | Service that receives the proxied `/api` requests   |

The dev server binds `127.0.0.1` only. The proxy rewrites the `Host` header to
the service's address and removes the browser's `Origin` header, because the
service rejects requests from any origin but its own. Client-side routes under
`/ui/` fall back to `index.html`, as on the service.

**Getting a token for development.** `sessionStorage` is per origin, so the dev
server's page needs its own handover. Print the URL with
`code-search-local web --no-open` (for the service selected by your
configuration) and replace its origin with the dev server's, keeping the
fragment: `http://127.0.0.1:8100/ui/#token=<token>`. Alternatively, open
`http://127.0.0.1:8100/ui/` and paste the `token` value of the service's
`<storage>/auth.json`.

**An isolated service.** Instead of the user service, run the repository's test
daemon, which needs no model download, with its own storage and port:

```sh
PYTHONPATH=packages/code-search-local .venvs/cpu/bin/python -m tests.daemon \
  --fake --storage /tmp/csl-dev --port 8123
CODE_SEARCH_SERVICE_URL=http://127.0.0.1:8123 pnpm dev   # in a second terminal
```

Its token is in `/tmp/csl-dev/auth.json`. Index a project through its API, or
with
`CODE_SEARCH_STORAGE=/tmp/csl-dev CODE_SEARCH_PORT=8123 hatch run cpu:cli index /absolute/path/to/project`,
so the dashboard has data to show. Stop the daemon with Ctrl+C.
`hatch run cpu:serve` with a separate `CODE_SEARCH_STORAGE` and
`CODE_SEARCH_PORT` (see the README's
[foreground development](../README.md#optional-foreground-development)) works
the same way with the real model.

## Build and packaging

```sh
pnpm build    # generate, type-check the workspace, bundle into packages/code-search-local-webapp/dist
hatch build   # wheel and sdist; both carry the dashboard build when it exists
```

`pnpm build` writes `dist/index.html` and content-hashed scripts with source
maps under `dist/assets/`, replacing the previous build. A service running from
the checkout serves the new build on the next page load.

`hatch build` copies `dist/` into the wheel as
`code_search_local/assets/webapp`, and into the sdist so that a wheel rebuilt
from it keeps the dashboard, but only when `dist/index.html` exists. Run
`pnpm build` first for a release that serves `/ui/`. Without it the artifacts
still build, and their `/ui/` answers 503. `hatch run cpu:sync`, editable
installs and source setup never need Node.js.

CI follows the same order. The `test` job in `.github/workflows/ci.yml` runs
`pnpm install --frozen-lockfile` and `pnpm build` before `hatch build`, so the
uploaded `distributions` artifact (which the release workflow publishes) carries
the dashboard. The `web` job runs `pnpm check`, installs Chromium and runs
`pnpm test:e2e` against the CPU environment.

## Tests and checks

| Command         | What it runs                                                                                                                                                                                                                           |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pnpm test`     | The workspace scripts' `node --test` suites, `pnpm compile`, then jest over the API package and the dashboard (`jest.config.ts` projects). Dashboard suites use Testing Library; DOM suites select `jest-fixed-jsdom` with a docblock. |
| `pnpm test:e2e` | `pnpm build`, then the Playwright specs in `packages/code-search-local-webapp/tests/e2e` against the real Python service                                                                                                               |
| `pnpm check`    | The workspace gate: `pnpm run generate`, then the stages `layout`, `conventions`, `format`, `lint`, `build` and `tests` in order                                                                                                       |

The end-to-end setup (`etc/playwright/globalSetup.ts`) builds the dashboard if
`dist/index.html` is missing, then starts
`packages/code-search-local/tests/daemon.py --fake` with
`.venvs/cpu/bin/python`. The daemon gets temporary storage, a free loopback port
and `CODE_SEARCH_WEBAPP_DIR` pointing at `dist/`. The setup waits up to 90
seconds for its health check, indexes a four-file fixture project and runs one
search. The specs then check, in Chromium with one worker:

- the token handover from the fragment and its removal from the URL, the online
  status, the project row and the overview's rates;
- the project page with its rates, the directory tree and the file table;
- the connect screen without a token, and connecting with a pasted token;
- the return to the connect screen when the service rejects a token.

The teardown stops the daemon (SIGTERM, then SIGKILL after 10 seconds) and
removes the temporary directory. Traces of failed tests are kept under
`packages/code-search-local-webapp/lib/playwright/test-results`.

The end-to-end tests need the CPU environment (`hatch run cpu:sync`) and
Playwright's Chromium:

```sh
pnpm --filter @code-search-local/code-search-local-webapp exec playwright install chromium
```

On a machine without the browser's system libraries, add `--with-deps` (it
installs operating-system packages and may ask for elevated rights).

`pnpm check` stages:

| Stage         | Command                                                                                                                              |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `layout`      | `scripts/check-package-layout.mjs`: allowed files and directories at the workspace and package roots, no compiler output in `src/`   |
| `conventions` | `scripts/check-conventions.mjs`: STYLE.md rules ESLint cannot express (import order, barrels, naming, JSDoc, one component per file) |
| `format`      | `pnpm run format:check` (Prettier)                                                                                                   |
| `lint`        | `pnpm lint` (ESLint, no warnings allowed)                                                                                            |
| `build`       | `pnpm build`                                                                                                                         |
| `tests`       | `pnpm test`                                                                                                                          |

Quick stages may run for 3 minutes and `build` and `tests` for 15; a stage that
fails or runs out of time fails the gate. The end-to-end tests are not part of
`pnpm check`. The Python package is checked by `hatch run lint` and
`hatch run coverage`.

## Troubleshooting

| Symptom                                                                               | What to check                                                                                                                                                                                                                                              |
| ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 503: `The web dashboard is not built. Run pnpm build in the repository root, …`       | No build was found. Run `pnpm install` and `pnpm build` in the checkout the service runs from, then reload. With `webapp_dir` set, only that directory is used, and it must contain `index.html`. A wheel built before `pnpm build` contains no dashboard. |
| The connect screen appears, or `The service rejected the access token`                | No token was handed over, or the service answered 401. Run `code-search-local web` with the same configuration (storage) as the service. The service uses the `token` value of its `<storage>/auth.json`, read when it starts.                             |
| The browser cannot open the `dashboard-….html` launch page                            | A sandboxed browser, such as a snap or Flatpak package, may not be allowed to read the runtime directory. Run `code-search-local web --no-open` and open the printed URL yourself.                                                                         |
| 403 `Invalid Host or Origin`                                                          | Open the dashboard through `127.0.0.1`, `localhost` or `[::1]` with the service's own port. A port forward or proxy must keep the port number, and must not add a foreign `Origin`.                                                                        |
| `Offline` and `Showing the last snapshot; the refresh failed`                         | The service stopped, restarted or became unreachable. The dashboard keeps polling and recovers when it answers; check `code-search-local service status`.                                                                                                  |
| An error naming `CUSTOM_ERROR` or a schema                                            | A response failed the dashboard's schema: the dashboard and the service were built from different versions of `openapi.yaml`. Rebuild the dashboard (`pnpm build`) and restart or reinstall the service.                                                   |
| `pnpm dev`: `Error occurred while trying to proxy` with 504                           | Nothing answers at `CODE_SEARCH_SERVICE_URL`. Start the service, or point the variable at the running one.                                                                                                                                                 |
| `pnpm dev`: 401 from every request                                                    | The dev server's page has no token, or a token of another service. Hand over the token of the service at `CODE_SEARCH_SERVICE_URL` as described in [Development](#development).                                                                            |
| `pnpm dev` fails with `CODE_SEARCH_WEBAPP_DEV_PORT must be a port number in 1..65535` | Set the variable to an integer port, or unset it for 8100. If the port is in use, choose another.                                                                                                                                                          |
| `pnpm test:e2e` cannot launch the browser                                             | Install Chromium for Playwright as shown in [Tests and checks](#tests-and-checks).                                                                                                                                                                         |
| `pnpm test:e2e`: `the daemon did not come up within 90000 ms`                         | The error includes the daemon's log. Check that `.venvs/cpu` exists and is current (`hatch run cpu:sync`).                                                                                                                                                 |
