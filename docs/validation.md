# Implementation validation

Validated locally on 2026-09-23 on branch `feature/code-search-local-v2`, based on `b240a2d9d3867a0ff935b5004d8ec4457fc37f58`. Source is packaged from `src/code_search_local`; tests also exercise artifacts outside the checkout.

## Acceptance evidence

| Lane | Result / assertions |
|---|---|
| Deterministic suite (2026-09-24) | 202 passed; 97.81% lines, 91.94% branches; each floor is 90% |
| Crash recovery | Real process termination at vector write, generation metadata, before manifest and after manifest; complete committed index recovered |
| Hatchling wheel + sdist + editable | All eight combinations of uv, uvx, pip in a venv and pipx installed and executed outside the checkout; the ninth check verifies editable resources and locked runtime provisioning without the source checkout |
| Hatch source workflow | A raw checkout runs before any release build, imports from `src/`, observes edits through Hatch and direct backend Python/console commands, executes lint/tests, and serves CLI stats requests; CPU also provides build tooling |
| Source user systemd | Raw checkout with spaces, no wheel/tarball; CPU, CUDA and ROCm setup each launch the correct `.venvs/<backend>/bin/python` with the checkout as working directory; all three builds remain installed; a server source edit appears over HTTP after restart and the prior index stays searchable |
| Native marketplaces | Claude and Codex catalog installation, discovery and removal passed with private client configurations |
| OpenCode HTTP MCP (2026-09-24) | Real OpenCode 1.18.32 connected using generated global JSONC, custom-file and custom-directory configurations; replacement/repeated registration and unregister passed while preserving unrelated entries |
| Two real Claude processes | Overlapping indexing requests, two project indexes, one cold-cache model acquisition/load, transfer audit with no duplicate model blobs, shared embedding cache hits, independent file updates and offline daemon restart |
| Physical CUDA | PyTorch 2.14.0 + CUDA 13.0, NVIDIA RTX 4090, normalized real embeddings, no CPU fallback |
| Physical ROCm | PyTorch 2.14.0 + ROCm 7.14, AMD Radeon RX 7900 XT, normalized real embeddings, no CPU fallback |
| User systemd | Pipx-origin CPU, pip-origin CUDA, uvx-origin ROCm provisioning; both client registrations preserve unrelated settings; repeated setup preserves ExecStart/process; version 1.0.0 → test-built 1.0.1 upgrade retains searchable indexes; deleting disposable uv cache does not break restart; uninstall retains stored data |
| Textual terminal | An actual 24-row PTY retained all 60 test metrics in the one-shot report; headless tests cover live updates, project filtering, offline startup and reconnect |
| Static/package checks | Ruff F/I checks, Git whitespace check, plugin manifest validation, locked dependency consistency and clean generated-file exclusions |

GPU tests use `google/embeddinggemma-300m` revision `57c266a740f537b4dc058e1b0cda161fd15afa75`, with 768-dimensional embeddings. The system ROCm installation remained at `/opt/rocm-7.0.3`; no drivers or system ROCm packages were changed and no reboot was performed. ROCm 7.14.1 libraries are isolated in the service virtual environment.

The ordinary suite skips external acceptance lanes by default. The results above come from explicitly enabling those lanes, not from counting those skips as successes. Real-client credentials are removed from temporary test directories; uniquely named test systemd units are removed in `finally`.

`uv.lock` and the canonical portable plugin manifest are reproducibility inputs. Hatchling maps runtime metadata and plugin assets into wheels without generating source copies. Legacy generated `runtime/` and `assets/` directories, wheels, sdists, model caches, runtime databases, logs, coverage output and test workspaces are ignored. The case-insensitive naming sweep preserves upper/title/lower case and leaves Git metadata untouched.

The Hatchling 1.32.4 migration uses `src/code_search_local/__init__.py` as the version source for release 1.0.0. The custom build backend and setuptools manifest were removed. The regular suite passes 172 tests with 15 external checks skipped by default; the packaging and marketplace lanes were explicitly rerun against the new build backend. Artifact checks verify that CLI, distribution metadata and plugin versions agree and that bundled dependency files match the canonical sources byte for byte.

On 2026-09-24, the backend environments were separated into `.venvs/cpu`, `.venvs/cuda` and `.venvs/rocm`. The source workflow was validated with Hatch commands and the new real user-systemd acceptance test. The deterministic coverage run passed 172 tests with 97.65% line and 91.10% branch coverage. Source setup and foreground execution require no release artifact. The README, CI and install wrapper use the backend-specific paths.

All 10 packaging/workflow tests passed against this refactor. The release-systemd regression also passed, including CPU/CUDA/ROCm provisioning, upgrade to a test-built 1.0.1, retained indexes, and restart after deleting its disposable package cache. Source and release acceptance each used a private temporary unit and client configuration.

The source-systemd test starts from directly copied checkout files, installs each backend in editable mode, performs real indexing through the service, and verifies the process's `/proc/<pid>/cmdline` and working directory. After all three backends are installed, each Python still imports its own PyTorch build and the same checkout source. Editing the HTTP health handler and restarting exposes the edit without rebuilding; search still retrieves the previously indexed symbol. The private test unit is removed afterward. No system GPU libraries or drivers were changed.

On 2026-09-24, direct/source setup gained repeatable `--agent-harness` selection (default `none`) and full user-service/harness uninstall. Native Claude and Codex marketplace removal was tested against real private user services: uninstall removes the service, recorded MCP entries and cleanup units; disabling retains service; the other harness's plugin package and stored data remain. The Codex case deliberately stopped the path watcher and verified timer-driven removal. Direct CLI uninstall was also exercised twice to verify repeatability. All four native marketplace/lifecycle checks passed. No production service or user harness configuration was replaced.

OpenCode support was rechecked on 2026-09-24 with its real 1.18.32 CLI, obtained from the official npm package in a temporary directory. All three OpenCode acceptance cases and 17 harness unit tests passed (20 total). Each case connected to the authenticated HTTP MCP server, replaced a stale local registration, re-registered successfully, and removed the entry twice without losing an unrelated server. Tests isolated OpenCode's user directories and used an explicit fake embedding model; no OpenCode LLM session or real embedding inference was involved. Production registration code needed no changes. README quick-start/source/usage/configuration guidance and the setup skill now cover OpenCode explicitly; its integration uses direct MCP registration, while the repository marketplace catalog targets Claude/Codex.

All 10 artifact/source-workflow checks passed with the new JSONC dependency and uninstall modules. The source-systemd regression passed again with real CPU/CUDA/ROCm indexing and source edits, then exercised source CLI uninstall: unit and MCP entries gone, indexes and backend Python environments retained. Unit coverage also exercises configuration-write rollback, duplicate registration replacement, custom profile paths, incomplete registry writes and cleanup retry after configuration errors.

All nine MCP tools now expose task-oriented descriptions, intent examples, argument guidance and next steps. HTTP `tools/list` tests check descriptions and every parameter schema, indexing defaults, and read-only/destructive annotations. MCP connection negotiation checks workspace selection and indexing instructions; the existing call tests exercise all nine tools. The final deterministic run passed 202 tests (18 external checks skipped by default), with 97.81% line and 91.94% branch coverage. Ruff, formatting, Git whitespace, locked dependency and final wheel/sdist checks passed.

See [tests/README.md](../tests/README.md) for reproducible commands. CI runs deterministic tests and artifact installations; the manually dispatched release workflow requires an authenticated dual-GPU runner before its optional protected PyPI publication step. No package or marketplace was published during this implementation.

## Consolidated plugin layout

Both native CLIs were tested against one `.claude-plugin/marketplace.json` catalog and one `plugins/code-search-local/plugin.json` portable manifest. Redundant `.agents/`, `.codex-plugin/` and nested `.claude-plugin/` copies were removed. This uses Codex's [documented portable manifest and compatible marketplace loader](https://developers.openai.com/plugins/build/plugins). Claude discovers the skill through its catalog entry and standard `skills/` directory. All pytest fixtures live under `tests/conftest.py`.
