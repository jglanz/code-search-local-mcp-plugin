# Validation

Hatch keeps CPU, CUDA and ROCm environments side by side at `.venvs/cpu`, `.venvs/cuda` and `.venvs/rocm`, explicitly configured in `pyproject.toml`. Default tests and builds use CPU. Backend-prefixed commands execute the corresponding editable source installation.

All ordinary tests isolate storage, project roots, sockets, and client configuration. Fake models are explicit fixtures and enforce model-thread ownership. Application code has separate 90% line and branch floors, configured in pyproject.toml.

```sh
hatch run cpu:sync
hatch run test
hatch run coverage
hatch run lint
```

The default suite covers languages, routing, fair scheduling, cache identity, queue bounds, cancellation, concurrent searches/updates, deletion-only updates, watch reconciliation, JSON/Click/Textual behavior, IPC loss/restarts, authentication, migration and transactional rollback. HTTP MCP discovery checks all nine tools' intent examples, follow-up guidance, parameter descriptions, defaults and read-only/destructive annotations; initialization checks the server-level indexing instructions. Crash tests kill real subprocesses at four commit boundaries and verify complete old/new generations.

## Required acceptance lanes

The standalone migration cleanup script is tested separately with discovery-only fixtures. Its flag matrix verifies that every mode, including the default with no removal flags, plans systemd service/activation-unit uninstall (stop/disable and removal of unit files/enablement links), MCP and plugin unregistration in Claude/Codex/OpenCode, and installed plugin cache removal. Only indexes and runtime packages are optional:

```sh
hatch run test tests/unit/test_cleanup_script.py
```

Every script invocation in these tests includes `--dry-run`. Tests verify no configuration writes, backups, process signals or mutating subprocess calls; mixed Claude/Codex/OpenCode registrations; TOML arrays/comments and JSONC; process/descendant ownership; systemd identity; installer/cache discovery and uv/pip/pipx command selection; the default and all three removal-flag combinations; unconditional model retention; cron/shell references; cloned/linked worktree and backup protection; and changed-file/symlink detection. The destructive `apply_plan` branch is deliberately unexecuted pending personal review of the script. These tests do not constitute validation of real cleanup execution.

Backup fixtures cover suffixes, directories, editor recovery files, custom profiles, symlinks, parent removal and original-installer removal across all flags. Report checks verify match evidence, redaction of internal identity fields and ordering that puts active registrations before cached metadata.

Opted-in lanes fail on missing tools, authentication or devices; their default skips are not release approval.

```sh
# Hatchling wheel/sdist through uv, uvx, pip in venvs, and pipx, plus editable installation:
CODE_SEARCH_PACKAGING=1 hatch run test tests/integration/test_packaging.py

# Native marketplace install/discovery/removal in isolated client configurations:
CODE_SEARCH_MARKETPLACES=1 hatch run test tests/integration/test_marketplaces.py

# Native Claude/Codex uninstall stops/removes a running service and its watchers:
CODE_SEARCH_MARKETPLACES=1 CODE_SEARCH_SYSTEMD_TESTS=1 hatch run test tests/integration/test_marketplace_lifecycle.py

# Real OpenCode HTTP MCP connection, replacement and unregister in isolated profiles:
CODE_SEARCH_OPENCODE_TESTS=1 hatch run test tests/integration/test_opencode.py

# Two authenticated Claude CLI processes with distinct generated workspaces:
hatch run cuda:sync
CODE_SEARCH_REAL_CLIENTS=1 hatch run cuda:test tests/integration/test_real_clients.py

# Actual normalized embeddings on the selected physical device, no CPU fallback:
hatch run cuda:sync
CODE_SEARCH_GPU_BACKEND=cuda hatch run cuda:test tests/integration/test_gpu.py
hatch run rocm:sync
CODE_SEARCH_GPU_BACKEND=rocm hatch run rocm:test tests/integration/test_gpu.py

# Raw-checkout source service: all three backend venvs, real indexing, edit/restart:
CODE_SEARCH_SYSTEMD_TESTS=1 hatch run test tests/integration/test_source_systemd.py

# Release user-systemd setup/backend changes/upgrade/cache deletion/uninstall:
hatch build
CODE_SEARCH_SYSTEMD_TESTS=1 hatch run test tests/integration/test_systemd_install.py
```

The source workflow test copies raw checkout files without a tarball, starts the CLI before any build, checks the three declared backend paths, observes source edits through Hatch and direct Python/console entry points, and serves real CLI stats requests. It also verifies that release builds reuse the CPU environment. The separate source-systemd test provisions all three backend environments in a raw checkout, checks the actual service process interpreter and working directory, indexes with each backend, then edits server source and observes the change after restart while the prior index remains searchable. It never builds a wheel or tarball.

The packaging lane checks version `1.0.0`, bundled runtime metadata and the single plugin manifest in all eight installer/artifact combinations. It rebuilds the wheel from the sdist, verifies that no custom backend or generated source resources are needed, and tests an editable installation followed by locked runtime dependency resolution after removing its checkout. Hatchling reads the release version from `src/code_search_local/__init__.py`.

The marketplace lifecycle lane uses isolated Claude/Codex profiles and a real uniquely named user service. It verifies native registry detection, disabled-plugin retention, direct CLI removal, MCP cleanup across all three harness schemas, removal of watcher units, and preserved data. It reuses the CPU test interpreter and skips model provisioning/inference, which are covered in the backend lanes.

The OpenCode lane requires `opencode` on `PATH`, or an absolute executable path in `CODE_SEARCH_OPENCODE_BIN`. It uses the real `opencode mcp list` client against an authenticated test daemon and checks connected status, replacement of an old local/disabled registration, repeatable registration/removal, and unrelated-config preservation. All three cases run with private home/config/cache/data directories: global JSONC, `OPENCODE_CONFIG`, and `OPENCODE_CONFIG_DIR`. A fake embedding model isolates this transport/configuration check; it does not send an LLM prompt or need provider credentials.

The systemd lane requires both GPU types, Claude/Codex CLIs and an active user systemd manager. It uses a uniquely named temporary unit, disposable package environments and private client configuration, then removes its unit in `finally`. Its upgrade fixture changes the Hatchling version source from `1.0.0` to a temporary `1.0.1`. `CODE_SEARCH_TEST_UV_CACHE` can seed its disposable cache using hardlinks. `CODE_SEARCH_MODEL_STORAGE` can supply an already downloaded `models/` directory for the GPU lane. The systemd lane reuses `.test-artifacts/real-model/models` when available; it otherwise downloads independently.

The two-Claude lane deliberately starts with a cold model cache. A test-only scheduling barrier requires both real tool requests to overlap. Actual Hub file transfers are audited; the test checks one model acquisition/load, no duplicated blob transfer, project isolation and cache reuse. It restarts the service offline and verifies retained indexes, unchanged model blobs, and independent code updates. Authentication is copied into a private temporary client directory and removed in `finally`.

Use an authenticated self-hosted runner for GPU/systemd/real-client release acceptance. Ordinary CI covers the deterministic suite, coverage floors, build/install matrix and portable plugin manifests. Publication is a manually dispatched workflow gated by all acceptance jobs and a protected PyPI environment.
