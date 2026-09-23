# Repository guidance

Code Search Local is a shared local MCP indexing service. Application source is in `src/code_search_local`; dependencies, console entry points and test settings live in `pyproject.toml`.

Use the project virtual environment. Set up development with `uv sync --extra server --extra cpu` (choose `cuda` or `rocm` instead for the GPU lanes). Run `uv run pytest --cov --cov-report=json:coverage.json` and `uv run python scripts/check_coverage.py`; line and branch coverage each require 90%. Additional acceptance commands are in `tests/README.md`.

Preserve explicit project routing, immutable generation publication, one model owner thread, bounded project/model queues, and a single user-scoped daemon. Operational clients must not construct per-workspace models. Tests use explicit fake model factories only where declared; GPU and real-client acceptance uses actual models and devices.

Keep application source importable from installed wheels outside the repository. Packaging copies runtime metadata and plugin resources at build time; edit the canonical pyproject, lock file and `plugins/` tree rather than generated copies. Preserve `.omc/` unchanged and ignored.

Read README.md for the CLI, MCP tools, service lifecycle, configuration and architecture. Do not commit credentials, runtime state, generated fixtures, environments, build artifacts or coverage reports.
