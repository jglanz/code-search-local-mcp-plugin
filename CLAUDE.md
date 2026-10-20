# Repository guidance

Read and follow [the constants and duplication rule](.agents/rules/constants-and-duplication.md):
operational literals must be defined as named constants (docstrings and prose may remain inline); extract blocks of 5+ code lines
at 3+ total occurrences, or 8+ code lines at 2+ total occurrences, into a shared
method or function. The rule binds Python and TypeScript alike. All TypeScript code and the workspace `.mjs` scripts also follow [STYLE.md](STYLE.md).

Code Search Local is a shared local MCP indexing service. The repository is a pnpm monorepo; run Hatch and pnpm commands from the repository root:

- `packages/code-search-local/`: the Python service (application source in `src/code_search_local`, tests in `tests`, Python tooling and the API build hook in `scripts`). Its `package.json` only forwards `test`, `lint` and `coverage` to Hatch. `pyproject.toml`, `uv.lock`, `plugins/`, `.claude-plugin/`, `.venvs/` and `docs/` stay at the repository root; dependencies, console entry points and test settings live in the root `pyproject.toml`.
- `packages/code-search-local-api/`: `openapi.yaml`, the only definition of the HTTP API models, plus the TypeScript package that generates zod schemas and types from it.
- `packages/code-search-local-webapp/`: the React dashboard that the service serves at `/ui/`. It imports API schemas and types only from the API package.

API models are never hand-written in either language. Change `packages/code-search-local-api/openapi.yaml`, then regenerate: `hatch run generate` writes the git-ignored `code_search_local/api/models.py` and `openapi.json` (every wheel/editable build and `test`, `coverage` and `lint` also run it), and `pnpm run generate` or `pnpm compile` writes the API package's git-ignored `src/generated/`. The service validates request bodies and every `/api/v1` response through the generated models.

Python uses Hatch. Hatch defines backend environments in `.venvs/cpu`, `.venvs/cuda` and `.venvs/rocm`. Use `hatch run cpu:sync`, `cuda:sync` or `rocm:sync`; they coexist without changing one another. Default test/lint/build commands use CPU. Install a live source user service with `hatch run rocm:setup --agent-harness all` (or `cuda:setup` / `cpu:setup`): it passes `--source <checkout>`, sets the unit working directory to the checkout, and uses its backend venv Python with an editable installation. No wheel/tarball/build is needed. After Python edits use `hatch run rocm:cli service restart`; dependency edits require updating `uv.lock` and rerunning source setup. Direct execution uses `.venvs/rocm/bin/python -m code_search_local`. Run `hatch run coverage` and `hatch run lint`; line and branch coverage each require 90%. `hatch build` creates release artifacts only, and bundles the dashboard only when `packages/code-search-local-webapp/dist` has been built. Additional acceptance commands are in `packages/code-search-local/tests/README.md`.

TypeScript uses pnpm 12.6.0 (`packageManager`) with Node.js 24.18.0 (`engines` requires 24.9 or later). `pnpm install` installs the workspace; `pnpm check` is the gate (layout, conventions, format, lint, build, tests); `pnpm build` builds the dashboard into `packages/code-search-local-webapp/dist`; `pnpm test`, `pnpm lint` and `pnpm run format:check` run single stages; `pnpm test:e2e` (not part of `pnpm check`) runs the Playwright specs against `tests/daemon.py --fake` and needs `.venvs/cpu` and Playwright's Chromium; `pnpm dev` serves the dashboard with hot reload, proxying `/api` to a running service. [docs/webapp.md](docs/webapp.md) describes the dashboard. Prettier skips the Python package and the Python-oriented Markdown listed in `.prettierignore`. Python-only work needs neither Node.js nor pnpm.

Preserve explicit project routing, immutable generation publication, one model owner thread, bounded project/model queues, and a single user-scoped daemon. Operational clients must not construct per-workspace models. Tests use explicit fake model factories only where declared; GPU and real-client acceptance uses actual models and devices.

Keep application source importable from installed wheels outside the repository. Packaging copies runtime metadata, plugin resources, the generated API models and a built dashboard at build time; edit the canonical pyproject, lock file, `plugins/` tree and `openapi.yaml` rather than generated copies.

Supported harnesses are Claude, Codex and OpenCode. Setup defaults to `--agent-harness none`; repeat the flag to select a subset or use `all`. OpenCode is a direct HTTP MCP client configured through `--agent-harness opencode`. Only Claude/Codex marketplace setup uses `--marketplace`.

Read README.md for the CLI, MCP tools, service lifecycle, configuration and architecture, and [docs/tui.md](docs/tui.md) for the statistics UI and search hit/miss definitions. Do not commit credentials, runtime state, generated fixtures or code (API models, `src/generated/`, `lib/`, `dist/`), environments, `node_modules`, build artifacts or coverage reports.
