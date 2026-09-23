# Implementation validation

Validated locally on 2026-09-23 on branch `feature/code-search-local-v2`, based on `b240a2d9d3867a0ff935b5004d8ec4457fc37f58`. Source is packaged from `src/code_search_local`; tests also exercise artifacts outside the checkout.

## Acceptance evidence

| Lane | Result / assertions |
|---|---|
| Deterministic suite | 167 passed; 97.53% lines, 90.94% branches; each floor is 90% |
| Crash recovery | Real process termination at vector write, generation metadata, before manifest and after manifest; complete committed index recovered |
| Wheel + sdist | All eight combinations of uv, uvx, pip in a venv and pipx installed and executed outside the checkout |
| Native marketplaces | Claude and Codex catalog installation, discovery and removal passed with private client configurations |
| Two real Claude processes | Overlapping indexing requests, two project indexes, one cold-cache model acquisition/load, transfer audit with no duplicate model blobs, shared embedding cache hits, independent file updates and offline daemon restart |
| Physical CUDA | PyTorch 2.14.0 + CUDA 13.0, NVIDIA RTX 4090, normalized real embeddings, no CPU fallback |
| Physical ROCm | PyTorch 2.14.0 + ROCm 7.14, AMD Radeon RX 7900 XT, normalized real embeddings, no CPU fallback |
| User systemd | Pipx-origin CPU, pip-origin CUDA, uvx-origin ROCm provisioning; both client registrations preserve unrelated settings; repeated setup preserves ExecStart/process; version 0.2.0 → test-built 0.2.1 upgrade retains searchable indexes; deleting disposable uv cache does not break restart; uninstall retains stored data |
| Textual terminal | An actual 24-row PTY retained all 60 test metrics in the one-shot report; headless tests cover live updates, project filtering, offline startup and reconnect |
| Static/package checks | Ruff F/I checks, Git whitespace check, plugin manifest validation, locked dependency consistency and clean generated-file exclusions |

GPU tests use `google/embeddinggemma-300m` revision `57c266a740f537b4dc058e1b0cda161fd15afa75`, with 768-dimensional embeddings. The system ROCm installation remained at `/opt/rocm-7.0.3`; no drivers or system ROCm packages were changed and no reboot was performed. ROCm 7.14.1 libraries are isolated in the service virtual environment.

The ordinary suite skips external acceptance lanes by default. The results above come from explicitly enabling those lanes, not from counting those skips as successes. Real-client credentials are removed from temporary test directories; uniquely named test systemd units are removed in `finally`.

`uv.lock` and the canonical portable plugin manifest are reproducibility inputs. Copies generated under `src/code_search_local/runtime/` and `assets/`, wheels, sdists, model caches, runtime databases, logs, coverage output and test workspaces are ignored. The case-insensitive naming sweep preserves upper/title/lower case and leaves `.omc/` and Git metadata untouched.

See [tests/README.md](../tests/README.md) for reproducible commands. CI runs deterministic tests and artifact installations; the manually dispatched release workflow requires an authenticated dual-GPU runner before its optional protected PyPI publication step. No package or marketplace was published during this implementation.

## Consolidated plugin layout

Both native CLIs were tested against one `.claude-plugin/marketplace.json` catalog and one `plugins/code-search-local/plugin.json` portable manifest. Redundant `.agents/`, `.codex-plugin/` and nested `.claude-plugin/` copies were removed. This uses Codex's [documented portable manifest and compatible marketplace loader](https://developers.openai.com/plugins/build/plugins). Claude discovers the skill through its catalog entry and standard `skills/` directory. All pytest fixtures live under `tests/conftest.py`.
