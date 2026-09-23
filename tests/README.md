# Validation

All ordinary tests isolate storage, project roots, sockets, and client configuration. Fake models are explicit fixtures and enforce model-thread ownership. Application code has separate 90% line and branch floors, configured in pyproject.toml.

```sh
uv sync --extra server --extra cpu
uv run pytest --cov --cov-report=json:coverage.json
uv run python scripts/check_coverage.py
```

The default suite covers languages, routing, fair scheduling, cache identity, queue bounds, cancellation, concurrent searches/updates, deletion-only updates, watch reconciliation, JSON/Click/Textual behavior, IPC loss/restarts, authentication, migration and transactional rollback. Crash tests kill real subprocesses at four commit boundaries and verify complete old/new generations.

## Required acceptance lanes

Opted-in lanes fail on missing tools, authentication or devices; their default skips are not release approval.

```sh
# Wheel and sdist through uv, uvx, pip in venvs, and pipx, outside the checkout:
CODE_SEARCH_PACKAGING=1 uv run pytest tests/integration/test_packaging.py

# Native marketplace install/discovery/removal in isolated client configurations:
CODE_SEARCH_MARKETPLACES=1 uv run pytest tests/integration/test_marketplaces.py

# Two authenticated Claude CLI processes with distinct generated workspaces:
CODE_SEARCH_REAL_CLIENTS=1 uv run --extra server --extra cuda pytest tests/integration/test_real_clients.py

# Actual normalized embeddings on the selected physical device, no CPU fallback:
CODE_SEARCH_GPU_BACKEND=cuda uv run --extra server --extra cuda pytest tests/integration/test_gpu.py
CODE_SEARCH_GPU_BACKEND=rocm uv run --extra server --extra rocm pytest tests/integration/test_gpu.py

# Linux user-systemd setup/backend changes/upgrade/cache deletion/uninstall:
uv run python -m build
CODE_SEARCH_SYSTEMD_TESTS=1 uv run pytest tests/integration/test_systemd_install.py
```

The systemd lane requires both GPU types, Claude/Codex CLIs and an active user systemd manager. It uses a uniquely named temporary unit, disposable package environments and private client configuration, then removes its unit in `finally`. `CODE_SEARCH_TEST_UV_CACHE` can seed its disposable cache using hardlinks. `CODE_SEARCH_MODEL_STORAGE` can supply an already downloaded `models/` directory for the GPU lane. The systemd lane reuses `.test-artifacts/real-model/models` when available; it otherwise downloads independently.

The two-Claude lane deliberately starts with a cold model cache. A test-only scheduling barrier requires both real tool requests to overlap. Actual Hub file transfers are audited; the test checks one model acquisition/load, no duplicated blob transfer, project isolation and cache reuse. It restarts the service offline and verifies retained indexes, unchanged model blobs, and independent code updates. Authentication is copied into a private temporary client directory and removed in `finally`.

Use an authenticated self-hosted runner for GPU/systemd/real-client release acceptance. Ordinary CI covers the deterministic suite, coverage floors, build/install matrix and portable plugin manifests. Publication is a manually dispatched workflow gated by all acceptance jobs and a protected PyPI environment.
