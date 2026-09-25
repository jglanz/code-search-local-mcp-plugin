# Repository guidance

Code Search Local is a shared local MCP indexing service. Application source is in `src/code_search_local`; dependencies, console entry points and test settings live in `pyproject.toml`.

Hatch defines backend environments in `.venvs/cpu`, `.venvs/cuda` and `.venvs/rocm`. Use `hatch run cpu:sync`, `cuda:sync` or `rocm:sync`; they coexist without changing one another. Default test/lint/build commands use CPU. Install a live source user service with `hatch run rocm:setup --agent-harness all` (or `cuda:setup` / `cpu:setup`): it passes `--source <checkout>`, sets the unit working directory to the checkout, and uses its backend venv Python with an editable installation. No wheel/tarball/build is needed. After Python edits use `hatch run rocm:cli service restart`; dependency edits require updating `uv.lock` and rerunning source setup. Direct execution uses `.venvs/rocm/bin/python -m code_search_local`. Run `hatch run coverage` and `hatch run lint`; line and branch coverage each require 90%. `hatch build` creates release artifacts only. Additional acceptance commands are in `tests/README.md`.

Preserve explicit project routing, immutable generation publication, one model owner thread, bounded project/model queues, and a single user-scoped daemon. Operational clients must not construct per-workspace models. Tests use explicit fake model factories only where declared; GPU and real-client acceptance uses actual models and devices.

Keep application source importable from installed wheels outside the repository. Packaging copies runtime metadata and plugin resources at build time; edit the canonical pyproject, lock file and `plugins/` tree rather than generated copies.

Supported harnesses are Claude, Codex and OpenCode. Setup defaults to `--agent-harness none`; repeat the flag to select a subset or use `all`. OpenCode is a direct HTTP MCP client configured through `--agent-harness opencode`. Only Claude/Codex marketplace setup uses `--marketplace`.

Read README.md for the CLI, MCP tools, service lifecycle, configuration and architecture. Do not commit credentials, runtime state, generated fixtures, environments, build artifacts or coverage reports.
