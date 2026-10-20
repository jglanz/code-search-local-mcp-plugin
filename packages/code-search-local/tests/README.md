# Validation

Hatch keeps CPU, CUDA and ROCm environments side by side at `.venvs/cpu`, `.venvs/cuda` and `.venvs/rocm`, explicitly configured in `pyproject.toml`. Default tests and builds use CPU. Backend-prefixed commands execute the corresponding editable source installation.

All ordinary tests isolate storage, project roots, sockets, and client configuration. Fake models are explicit fixtures and enforce model-thread ownership. Application code has separate 90% line and branch floors, configured in pyproject.toml.

```sh
hatch run cpu:sync
hatch run test
hatch run coverage
hatch run lint
```

`test`, `coverage` and `lint` first run `hatch run generate`, which regenerates the git-ignored API models and JSON document in `code_search_local/api` from `packages/code-search-local-api/openapi.yaml`. Contract tests validate realistic statistics and per-path responses through those models, check that malformed responses become HTTP 500 and invalid request bodies HTTP 400, serve the document at `/api/v1/openapi.json` only with the bearer token, and verify that generation is byte-for-byte reproducible. Build-hook tests check that wheels include the generated models and, only when `packages/code-search-local-webapp/dist` exists, the built dashboard; that editable builds generate the models in place without bundling; and that sdists carry the dashboard build but no generated models. Web dashboard tests cover the redirects, static assets with security headers, client-route fallback, traversal rejection, the missing-build response, bearer exemption limited to dashboard routes, asset directory resolution and the `web` command with a mocked browser, including its failure without a configured service.

Search analytics tests run a real engine with a fake model. They check that a relevance hit counts each returned path once per search, that counters accumulate and query-embedding cache counters stay separate from document embeddings, that below-threshold results still count as non-empty, zero-result searches, that `clear_index` keeps the counters and per-path history, that failed searches count as misses in both pairs, that a failed per-path write rolls the search counters back in memory and on disk, that `totals` cover every project before a project filter, and that state written before these counters existed reads as zeros. Unit tests cover zero-denominator ratios, offline snapshots with and without the per-path table and the ten-row top-paths limit, threshold bounds and float environment parsing, and `--search-hit-min-score` on `setup`, `serve` and `doctor`. TUI tests render every section of the inline report, placeholders for empty and older snapshots, rate/number/time formatting, job progress, error truncation and the 20-job limit; drive the live view's `r`, `d`, `q` and Escape bindings and subtitle headlessly; check error notifications and the CLI's project filter and fetch wiring.

```sh
hatch run test packages/code-search-local/tests/integration/test_search_analytics.py \
  packages/code-search-local/tests/unit/test_search_analytics_stats.py \
  packages/code-search-local/tests/unit/test_tui.py
hatch run test packages/code-search-local/tests/integration/test_web_api.py \
  packages/code-search-local/tests/unit/test_api_models.py packages/code-search-local/tests/unit/test_web_cli.py
```

The TypeScript workspace (API package and dashboard) has its own jest tests (`pnpm test`, also run by the `pnpm check` gate) and Playwright end-to-end tests (`pnpm test:e2e`), which start `tests/daemon.py --fake` from `.venvs/cpu`; see [the web dashboard guide](../../../docs/webapp.md#tests-and-checks).

The default suite covers languages, routing, fair scheduling, cache identity, queue bounds, cancellation, concurrent searches/updates, deletion-only updates, watch reconciliation, JSON/Click/Textual behavior, IPC loss/restarts, authentication, migration and transactional rollback. HTTP MCP discovery checks all nine tools' intent examples, follow-up guidance, parameter descriptions, defaults and read-only/destructive annotations; initialization checks the server-level indexing instructions. Crash tests kill real subprocesses at four commit boundaries and verify complete old/new generations.

## Code rules

`hatch run rules` checks operational literals and uses Pylint's duplicate finder with the project's inclusive thresholds: five code lines at three occurrences, or eight at two. It also checks repeated blocks within a file. `packages/code-search-local/tests/unit/test_code_rules.py` verifies these boundaries and that docstrings/prose remain allowed while inline JSON keys, paths, options and timing budgets are rejected. The checker supplements review of semantic duplicates; it is not a proof that every possible syntax or parameterized variant is covered. Parser fixture files under `test_data` and `fixtures` are intentionally treated as input data.

## Required acceptance lanes

The standalone migration cleanup script is tested separately with discovery-only fixtures. Its flag matrix verifies that every mode, including the default with no removal flags, plans systemd service/activation-unit uninstall (stop/disable and removal of unit files/enablement links), MCP and plugin unregistration in Claude/Codex/OpenCode, and installed plugin cache removal. Only indexes and runtime packages are optional:

```sh
hatch run test packages/code-search-local/tests/unit/test_cleanup_script.py
```

Every script invocation in these tests includes `--dry-run`. Tests verify no configuration writes, backups, process signals or mutating subprocess calls; mixed Claude/Codex/OpenCode registrations; TOML arrays/comments and JSONC; process/descendant ownership; systemd identity; installer/cache discovery and uv/pip/pipx command selection; the default and all three removal-flag combinations; unconditional model retention; cron/shell references; cloned/linked worktree and backup protection; and changed-file/symlink detection. The destructive `apply_plan` branch is deliberately unexecuted pending personal review of the script. These tests do not constitute validation of real cleanup execution.

Backup fixtures cover suffixes, directories, editor recovery files, custom profiles, symlinks, parent removal and original-installer removal across all flags. Report checks verify match evidence, redaction of internal identity fields and ordering that puts active registrations before cached metadata.

Opted-in lanes fail on missing tools, authentication or devices; their default skips are not release approval.

```sh
# Hatchling wheel/sdist through uv, uvx, pip in venvs, and pipx, plus editable installation:
CODE_SEARCH_PACKAGING=1 hatch run test packages/code-search-local/tests/integration/test_packaging.py

# Native marketplace install/discovery/removal in isolated client configurations:
CODE_SEARCH_MARKETPLACES=1 hatch run test packages/code-search-local/tests/integration/test_marketplaces.py

# Native Claude/Codex uninstall stops/removes a running service and its watchers:
CODE_SEARCH_MARKETPLACES=1 CODE_SEARCH_SYSTEMD_TESTS=1 hatch run test packages/code-search-local/tests/integration/test_marketplace_lifecycle.py

# Real OpenCode HTTP MCP connection, replacement and unregister in isolated profiles:
CODE_SEARCH_OPENCODE_TESTS=1 hatch run test packages/code-search-local/tests/integration/test_opencode.py

# Two authenticated Claude CLI processes with distinct generated workspaces:
hatch run cuda:sync
CODE_SEARCH_REAL_CLIENTS=1 hatch run cuda:test packages/code-search-local/tests/integration/test_real_clients.py

# Actual normalized embeddings on the selected physical device, no CPU fallback:
hatch run cuda:sync
CODE_SEARCH_GPU_BACKEND=cuda hatch run cuda:test packages/code-search-local/tests/integration/test_gpu.py
hatch run rocm:sync
CODE_SEARCH_GPU_BACKEND=rocm hatch run rocm:test packages/code-search-local/tests/integration/test_gpu.py

# Raw-checkout source service: all three backend venvs, real indexing, edit/restart:
CODE_SEARCH_SYSTEMD_TESTS=1 hatch run test packages/code-search-local/tests/integration/test_source_systemd.py

# Release user-systemd setup/backend changes/upgrade/cache deletion/uninstall:
hatch build
CODE_SEARCH_SYSTEMD_TESTS=1 hatch run test packages/code-search-local/tests/integration/test_systemd_install.py
```

The source workflow test copies raw checkout files without a tarball, starts the CLI before any build, checks the three declared backend paths, observes source edits through Hatch and direct Python/console entry points, and serves real CLI stats requests. It also verifies that release builds reuse the CPU environment. The separate source-systemd test provisions all three backend environments in a raw checkout, checks the actual service process interpreter and working directory, indexes with each backend, then edits server source and observes the change after restart while the prior index remains searchable. It never builds a wheel or tarball.

The packaging lane checks version `1.0.0`, bundled runtime metadata, the generated API models and document, and the single plugin manifest in all eight installer/artifact combinations. It rebuilds the wheel from the sdist, verifies that the sdist carries the OpenAPI document and build hook but not generated files, that a built web dashboard (`packages/code-search-local-webapp/dist`) is bundled into both artifacts exactly when it exists, and that no custom backend is needed. It then tests an editable installation, in which the hook generates only the documented API module inside the source tree, followed by locked runtime dependency resolution after removing its checkout. Hatchling reads the release version from `packages/code-search-local/src/code_search_local/__init__.py`.

The marketplace lifecycle lane uses isolated Claude/Codex profiles and a real uniquely named user service. It verifies native registry detection, disabled-plugin retention, direct CLI removal, MCP cleanup across all three harness schemas, removal of watcher units, and preserved data. It reuses the CPU test interpreter and skips model provisioning/inference, which are covered in the backend lanes.

The OpenCode lane requires `opencode` on `PATH`, or an absolute executable path in `CODE_SEARCH_OPENCODE_BIN`. It uses the real `opencode mcp list` client against an authenticated test daemon and checks connected status, replacement of an old local/disabled registration, repeatable registration/removal, and unrelated-config preservation. All three cases run with private home/config/cache/data directories: global JSONC, `OPENCODE_CONFIG`, and `OPENCODE_CONFIG_DIR`. A fake embedding model isolates this transport/configuration check; it does not send an LLM prompt or need provider credentials.

The systemd lane requires both GPU types, Claude/Codex CLIs and an active user systemd manager. It uses a uniquely named temporary unit, disposable package environments and private client configuration, then removes its unit in `finally`. Its upgrade fixture changes the Hatchling version source from `1.0.0` to a temporary `1.0.1`. `CODE_SEARCH_TEST_UV_CACHE` can seed its disposable cache using hardlinks. `CODE_SEARCH_MODEL_STORAGE` can supply an already downloaded `models/` directory for the GPU lane. The systemd lane reuses `.test-artifacts/real-model/models` when available; it otherwise downloads independently.

The two-Claude lane deliberately starts with a cold model cache. A test-only scheduling barrier requires both real tool requests to overlap. Actual Hub file transfers are audited; the test checks one model acquisition/load, no duplicated blob transfer, project isolation and cache reuse. It restarts the service offline and verifies retained indexes, unchanged model blobs, and independent code updates. Authentication is copied into a private temporary client directory and removed in `finally`.

Use an authenticated self-hosted runner for GPU/systemd/real-client release acceptance. Ordinary CI covers the deterministic suite, coverage floors, build/install matrix and portable plugin manifests. Publication is a manually dispatched workflow gated by all acceptance jobs and a protected PyPI environment.
