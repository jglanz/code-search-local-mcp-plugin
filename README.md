# Code Search Local MCP Plugin

Local semantic code search for Claude Code and Codex, with one shared embedding model and a separate durable index for every project. Index several workspaces concurrently without starting a model process for each client. Embeddings run on CPU, NVIDIA CUDA or AMD ROCm; FAISS vector search runs on the CPU.

This is an independently maintained hard fork. The Python package and CLI are named `code-search-local`; the repository is [`jglanz/code-search-local-mcp-plugin`](https://github.com/jglanz/code-search-local-mcp-plugin).

- [Quick start](#quick-start)
- [Installation options](#installation-options)
- [Setup guide](#setup-guide)
- [User guide](#user-guide)
- [Configuration reference](#configuration-reference)
- [Service management and upgrades](#service-management-and-upgrades)
- [Claude and Codex marketplace installation](#claude-and-codex-marketplace-installation)
- [MCP tools and resources](#mcp-tools-and-resources)
- [Troubleshooting](#troubleshooting)
- [Architecture and development](#architecture-and-development)

## Quick start

### 1. Check prerequisites

- Linux with a running **user systemd manager** for managed setup. Run `systemctl --user status` to check it; run setup as your normal user.
- Python **3.12–3.14**, Git, and `uv` for the source-build instructions below. Managed service environments use Python 3.12, which uv can provision.
- Claude Code and/or Codex. `--client both` configures both; Claude's CLI must be available on `PATH` when selecting `claude` or `both`.
- For GPU use, a compatible installed NVIDIA or AMD driver. Setup installs GPU Python libraries into its own virtual environment and does not replace system drivers or the system ROCm toolkit.
- Internet access for the initial dependencies, model and parser-grammar downloads. The default model is [`google/embeddinggemma-300m`](https://huggingface.co/google/embeddinggemma-300m). Complete any model access approval and authenticate with Hugging Face, or supply `HF_TOKEN` in the setup shell, before downloading a gated model.

### 2. Build and install the CLI

The repository can be installed before a PyPI release exists. From a new checkout:

```sh
git clone https://github.com/jglanz/code-search-local-mcp-plugin.git
cd code-search-local-mcp-plugin
uv build
uv tool install ./dist/code_search_local-0.2.0-py3-none-any.whl
```

If `code-search-local` is not on `PATH`, run `uv tool update-shell` and open a new shell. Return to the checkout for the next command.

### 3. Set up AMD ROCm and both clients

```sh
code-search-local setup \
  --client both \
  --backend rocm \
  --gpu-index 0 \
  --no-cpu-fallback \
  --package-source ./dist/code_search_local-0.2.0-py3-none-any.whl
```

Use `--client` with **two hyphens**. For NVIDIA, replace `--backend rocm` with `--backend cuda`; for CPU, use `--backend cpu`. If you use only one client, select `--client claude` or `--client codex`.

The first setup can take time: it installs the backend, downloads the model, executes a real embedding to validate the device, installs and starts `code-search-local.service`, and registers the authenticated HTTP MCP connection. Successful setup ends with JSON containing `backend`, `runtime`, `service` and `url`. The default endpoint is `http://127.0.0.1:8000/mcp`.

Keep `--package-source` on setup commands for this unpublished/local build. It tells the persistent service to install the same wheel as the CLI. Omit it only when that CLI version is available from your package index.

### 4. Index and search a project

Replace the example directory with an existing project root:

```sh
code-search-local service status
code-search-local index "$HOME/code/my-project"
code-search-local search 'where are authentication tokens validated?' \
  --project "$HOME/code/my-project" -k 5
code-search-local stats --project "$HOME/code/my-project"
```

`index` waits by default and prints the job as JSON; check that its `status` is `succeeded`. Reconnect or restart Claude/Codex so it discovers the new MCP connection. You can then ask it:

> Use Code Search Local to index this workspace, wait for the indexing job to succeed, then find the code that validates authentication tokens.

Indexing registers that project for automatic change detection. A second workspace can use the same service immediately; it gets its own index and shares the already loaded model.

## Installation options

### Install a locally built wheel

Build once with `uv build`, then choose **one** CLI installation method. These examples run from the checkout:

| Installer | Command |
|---|---|
| uv tool | `uv tool install ./dist/code_search_local-0.2.0-py3-none-any.whl` |
| pipx | `pipx install ./dist/code_search_local-0.2.0-py3-none-any.whl` |
| pip in a venv | Use the commands below |
| uvx, without a permanent CLI environment | Use the command below |

```sh
# pip: always use a virtual environment.
python3 -m venv "$HOME/.venvs/code-search-local"
"$HOME/.venvs/code-search-local/bin/python" -m pip install \
  ./dist/code_search_local-0.2.0-py3-none-any.whl
"$HOME/.venvs/code-search-local/bin/code-search-local" setup \
  --client both --backend rocm \
  --package-source ./dist/code_search_local-0.2.0-py3-none-any.whl
```

```sh
# uvx: both the temporary CLI and persistent service receive the local wheel.
uvx --from ./dist/code_search_local-0.2.0-py3-none-any.whl \
  code-search-local setup --client both --backend rocm \
  --package-source ./dist/code_search_local-0.2.0-py3-none-any.whl
```

The CLI includes uv as a dependency. Regardless of how you install the CLI, setup uses uv and the bundled lock file to provision the service. pip and pipx do not need to understand uv's vendor-index configuration. Use `setup --backend ...` to select the runtime; do not install GPU extras directly with pip.

### Install a published release

The following examples require version `0.2.0` to have been published to your package index. Building or pushing this repository does not publish it to PyPI.

```sh
uv tool install code-search-local==0.2.0
code-search-local setup --client both --backend rocm

# Alternative: pipx.
pipx install code-search-local==0.2.0
code-search-local setup --client both --backend cuda

# Alternative: uvx, with no permanent CLI installation.
uvx --from code-search-local==0.2.0 \
  code-search-local setup --client both --backend auto
```

For pip, use the venv commands above and replace the wheel path in `pip install` with `code-search-local==0.2.0`; omit `--package-source` from setup.

## Setup guide

### Select a backend and clients

These examples assume a published package. For a source build, append `--package-source /absolute/path/to/code_search_local-0.2.0-py3-none-any.whl` to each setup invocation.

```sh
# AMD: require ROCm on GPU 0; report a failure instead of falling back.
code-search-local setup --client both --backend rocm --gpu-index 0 --no-cpu-fallback

# NVIDIA: require CUDA on GPU 0.
code-search-local setup --client both --backend cuda --gpu-index 0 --no-cpu-fallback

# Explicitly permit CPU fallback after a GPU initialization or inference failure.
code-search-local setup --client claude --backend rocm --cpu-fallback

# CPU only, configuring Codex.
code-search-local setup --client codex --backend cpu

# Probe available hardware and permit CPU fallback.
code-search-local setup --client both --backend auto --cpu-fallback
```

GPU indexes are zero-based within the selected backend. ROCm uses PyTorch's `cuda:N` device API internally, but the HIP build identifies it as ROCm in statistics. CUDA and ROCm environments are separate; one running daemon uses one selected backend and model for all projects.

Automatic setup tests CUDA first when detected, then available ROCm, then CPU if fallback is enabled. A successful choice is reused on unchanged setup. With no saved override, `auto` allows CPU fallback and explicit backends do not. Pass `--cpu-fallback` or `--no-cpu-fallback` when changing that policy intentionally.

The tested runtime uses PyTorch 2.14.0 with CUDA 13.0 or ROCm 7.14 and ROCm 7.14.1 venv libraries. A separately installed ROCm toolkit is not required by this packaged runtime. See [hardware validation](docs/validation.md) for the tested GPUs and [dependency selection](docs/dependencies.md) for exact versions and sources.

### Choose storage, port and model

```sh
code-search-local setup \
  --client both \
  --backend rocm \
  --gpu-index 0 \
  --no-cpu-fallback \
  --storage "$HOME/.local/share/code-search-local" \
  --port 8123 \
  --model google/embeddinggemma-300m \
  --revision 57c266a740f537b4dc058e1b0cda161fd15afa75
```

Setup persists these settings and registers both clients at the selected port. Storage contains the project registry, indexes, model cache, embedding cache, authentication token and versioned service environments. Changing `--storage` selects a different data set; it does not move existing files. Retain the original directory to keep using its indexes.

The default revision `main` is resolved to a pinned snapshot on acquisition. An explicit commit revision makes the choice reproducible. Changing the model/revision requires indexing registered projects with the new model; use `index --rebuild` when you need to request it explicitly. Index metadata records which model produced its vectors.

### What setup changes

1. Creates or reuses a versioned environment under `<storage>/runtimes/` from the bundled dependency lock.
2. Prefetches supported parser grammars and validates actual model inference before replacing a running service.
3. Saves effective settings to `$XDG_CONFIG_HOME/code-search-local/config.json`, normally `~/.config/code-search-local/config.json`.
4. Creates a private token at `<storage>/auth.json` and installs the user unit at `$XDG_CONFIG_HOME/systemd/user/code-search-local.service`.
5. Enables and starts the user service, then registers `code-search-local` with the selected clients.

Claude registration is user-scoped and uses its native `claude mcp` command. Codex registration updates `~/.codex/config.toml`, or `$CODEX_HOME/config.toml`. Existing unrelated connections/settings are preserved and existing client configuration files receive `.code-search-local.bak` backups. `CLAUDE_CONFIG_DIR` is honored for an alternate Claude configuration directory.

Repeat setup to add the other client or apply new settings. An unchanged successful setup reuses the running service. Neither opening another project nor installing the second client plugin creates another daemon.

## User guide

### Index one or several projects

```sh
# From a project root; waits for completion.
code-search-local index .

# Incremental indexing is the default.
code-search-local index /absolute/path/to/project

# Queue two independent projects immediately.
code-search-local index "$HOME/code/api" --no-wait
code-search-local index "$HOME/code/web" --no-wait
code-search-local stats --live

# Rebuild a project's complete index.
code-search-local index "$HOME/code/api" --rebuild

# Limit eligible files with repeatable, quoted patterns.
code-search-local index "$HOME/code/api" --pattern '*.py' --pattern '*.md'
```

The CLI accepts relative or absolute roots and resolves symlinks to the canonical path. Treat the repository root as the project boundary: indexing a subdirectory registers a distinct project. The MCP tools require absolute roots.

Patterns match project-relative file paths using shell-style matching; quote them so your shell does not expand them first. They further restrict supported files, do not override ignore rules, and are remembered for watcher-driven updates. A later explicit `index` without `--pattern` clears that restriction.

Root `.gitignore`, `.code-search-ignore` and legacy `.claude-context-ignore` rules are honored. For example, put this in a project's `.code-search-ignore`:

```gitignore
vendor/
generated/
*.min.js
```

Generated/build directories, `.omc/`, symlinks, binary files and files above `max_file_bytes` are skipped. Parsers cover Python, JavaScript/TypeScript, JSX/TSX, C/C++, C#, Java, Go, Rust, Solidity, Svelte and Markdown.

### Inspect or cancel an indexing job

`index --no-wait` prints JSON with a `job_id`. Copy that value into the following commands:

```sh
code-search-local job JOB_ID --project "$HOME/code/api"
code-search-local job JOB_ID --project "$HOME/code/api" --cancel
```

Jobs transition from `queued` to `running`, then `succeeded`, `failed` or `cancelled`. Jobs interrupted by a service restart are recorded as `interrupted`; startup schedules reconciliation for eligible registered projects. Inspect `error` on failed jobs. A completed HTTP/CLI request alone does not mean the indexing job succeeded.

Requests for one project run in order; different projects can be active together. Cancelling a job leaves the last committed index searchable. A cancellation request can race with completion, so read the final job status.

### Search from the terminal or an agent

```sh
# Current project, up to ten results.
code-search-local search 'retry failed HTTP requests'

# Another project, up to five results.
code-search-local search 'database transaction rollback' --project "$HOME/code/api" -k 5
```

Search prints JSON results containing scores and chunk metadata, including source locations. It reads the last committed generation, which remains available while indexing runs. Finish the initial index before searching a new project.

In Claude or Codex, ask for semantic intent rather than only exact symbol names. For example:

> Search this workspace with Code Search Local for retry/backoff logic. Show the matching files and line numbers, then inspect the relevant implementation.

Both clients route tools through the same service. Tools always carry the project root, so parallel sessions cannot change another session's current project. MCP additionally provides metadata filters, similar-chunk search and explicit index clearing; see the [tool reference](#mcp-tools-and-resources).

### View statistics

```sh
# A complete report, retained in terminal scrollback.
code-search-local stats

# Restrict project and job rows to one workspace.
code-search-local stats --project ./my-project

# Fullscreen live view; q or Escape exits.
code-search-local stats --live
code-search-local stats --project /absolute/path/to/project --live

# Machine-readable output of the same snapshot.
code-search-local stats --json
code-search-local stats --project ./my-project --json > project-stats.json
```

`stats` uses a Textual inline report; `--live` uses a fullscreen Textual app. Live changes arrive through private ZeroMQ pub-sub IPC, with heartbeat/reconnect and sequence-gap recovery. `--json` emits JSON to stdout and cannot be combined with `--live`. Unknown project roots return an error. When the service is unreachable, statistics can be read from the persisted database and are labeled as an offline snapshot.

| Scope | Statistics |
|---|---|
| Project index | Canonical root, files, chunks, generation, index bytes, registration/index timestamps |
| Changes | Detected additions/modifications/deletions, reused chunks, indexing failures |
| Cache and search | Embedding cache hits/misses and ratio, searches, latency |
| Jobs | Project, job ID, status, processed files, timing, progress and errors |
| Model/device | Model ID/revision, backend, GPU/device, fallback information |
| Shared service | Model acquisition/load counts, resident state, inference time, GPU allocation, daemon identity |

Project filtering retains shared service/model context. `model` describes the committed index; `active_model` describes the most recent embedding operation. Counters persist across restarts; `model_resident` reports the current service's loaded state when online. An offline snapshot is historical, not a live GPU reading.

Use `code-search-local warmup` to acquire/load the model through the existing daemon without indexing a project.

## Configuration reference

Configuration precedence is **command-line option → `CODE_SEARCH_*` environment variable → saved JSON → built-in default**. Options belong after the subcommand, for example `code-search-local setup --backend rocm`, not before `setup`.

### Model, device and service settings

The shared CLI options below are accepted by `setup`, `serve` and `doctor`, except where noted.

| JSON key | CLI option | Environment variable | Default |
|---|---|---|---|
| `backend` | `--backend auto/cpu/cuda/rocm/mps` | `CODE_SEARCH_BACKEND` | `auto` |
| `gpu_index` | `--gpu-index N` | `CODE_SEARCH_GPU_INDEX` | `0` |
| `cpu_fallback` | `--cpu-fallback` / `--no-cpu-fallback` | `CODE_SEARCH_CPU_FALLBACK` | `null`: enabled for auto, disabled for explicit backends |
| `storage` | `--storage PATH` | `CODE_SEARCH_STORAGE` | `~/.claude_code_search`, retained for existing data |
| `model` | `--model ID` | `CODE_SEARCH_MODEL` | `google/embeddinggemma-300m` |
| `revision` | `--revision REF` | `CODE_SEARCH_REVISION` | `main`, pinned on acquisition |
| `host` | JSON/environment only | `CODE_SEARCH_HOST` | `127.0.0.1`; only loopback addresses accepted |
| `port` | `--port PORT` | `CODE_SEARCH_PORT` | `8000` |
| `watch` | serve: `--watch` / `--no-watch` | `CODE_SEARCH_WATCH` | `true` |
| `offline` | serve: `--offline` / `--online` | `CODE_SEARCH_OFFLINE` | `false` |

`--client claude/codex/both` is required by setup and is a registration choice, not a saved backend setting. `--package-source FILE` is setup-only and selects a locally built wheel for the persistent runtime.

### Work limits

These settings are configured through JSON or environment variables; there are no corresponding CLI flags.

| JSON key | Environment variable | Default / meaning |
|---|---|---|
| `project_workers` | `CODE_SEARCH_PROJECT_WORKERS` | `4` concurrent project workers |
| `chunk_workers` | `CODE_SEARCH_CHUNK_WORKERS` | `4` shared parsing workers |
| `model_batch_size` | `CODE_SEARCH_MODEL_BATCH_SIZE` | `32` texts per model batch |
| `max_pending_jobs` | `CODE_SEARCH_MAX_PENDING_JOBS` | `64` queued/running index jobs |
| `max_file_bytes` | `CODE_SEARCH_MAX_FILE_BYTES` | `2097152` (2 MiB) per file |

Work limits must be positive integers. Increasing project/parsing workers does not create additional model instances: the daemon still uses one model worker. Lower the model batch size if GPU memory is constrained.

### Save environment settings through setup

A shell export does not reconfigure an already running user service. Pass settings to setup so they are persisted, validated and applied:

```sh
CODE_SEARCH_MODEL_BATCH_SIZE=16 \
CODE_SEARCH_PROJECT_WORKERS=2 \
CODE_SEARCH_WATCH=true \
code-search-local setup --client both --backend rocm --no-cpu-fallback
```

For a local build, append `--package-source` as above. Boolean environment values accept `true/false`, `yes/no` or `1/0`, case-insensitively.

### Edit the JSON configuration

Setup writes all effective settings. The following is a valid partial configuration for `~/.config/code-search-local/config.json`; omitted keys use defaults. Merge the settings you need into an existing file:

```json
{
  "backend": "rocm",
  "gpu_index": 0,
  "cpu_fallback": false,
  "storage": "~/.claude_code_search",
  "model": "google/embeddinggemma-300m",
  "revision": "57c266a740f537b4dc058e1b0cda161fd15afa75",
  "host": "127.0.0.1",
  "port": 8000,
  "watch": true,
  "offline": false,
  "project_workers": 4,
  "chunk_workers": 4,
  "model_batch_size": 16,
  "max_pending_jobs": 64,
  "max_file_bytes": 2097152
}
```

Run `code-search-local doctor` to inspect the resolved settings as JSON. It does not run inference unless `--inference` is specified. After editing configuration, rerun setup to validate it, provision the correct backend and refresh client registration. Use this especially for backend, storage, model or port changes; restarting alone does not install a different backend runtime or update client endpoints.

For offline operation, first complete online setup and warmup with the intended model/revision. Then persist `CODE_SEARCH_OFFLINE=true` through setup using the already available package/runtime. Offline model mode requires a complete local model snapshot; provisioning a new runtime may still require package-index access.

## Service management and upgrades

```sh
code-search-local service status
code-search-local service stop
code-search-local service start
code-search-local service restart

# Follow logs, or inspect recent startup errors.
journalctl --user -u code-search-local.service -f
journalctl --user -u code-search-local.service -n 100 --no-pager
```

The service belongs to your user session and is enabled at the user manager's startup. To keep it running after logout, an administrator may enable user lingering with `loginctl enable-linger USERNAME`; setup does not change that policy.

### Upgrade a source installation

```sh
git pull --ff-only
uv build
uv tool install --force ./dist/code_search_local-0.2.0-py3-none-any.whl
code-search-local setup --client both \
  --package-source ./dist/code_search_local-0.2.0-py3-none-any.whl
```

Run this from the checkout and use the wheel filename matching the new version when it changes. Omitting `--backend` reuses the saved setting. For pipx, install the new wheel with `pipx install --force`; for pip, use the existing venv's Python with `-m pip install --upgrade --force-reinstall`. With uvx, invoke the new wheel directly as shown in [installation options](#installation-options).

For a published installation, upgrade the CLI with its original installer and rerun setup. Setup installs and validates a new versioned runtime before switching the service. Indexes and caches stay under the same storage root. The service's executable lives in that persistent runtime, so removing a temporary uvx environment or uv download cache does not remove the installed service.

### Uninstall the service

```sh
code-search-local service uninstall
```

This disables/stops the user service and removes its unit. It preserves indexes, model caches, runtime environments and client registration. Remove the MCP connection in each client if you no longer want it listed, and uninstall the CLI using the installer you chose. Remove stored data separately only if you intend to discard it.

### Foreground operation

For development or a host without user systemd, install the server dependencies and one backend in a project venv:

```sh
uv sync --locked --extra server --extra cpu
uv run --no-sync code-search-local serve --backend cpu --no-watch
```

Substitute the `cuda` or `rocm` extra and matching backend as needed. The daemon creates its private token in storage, but `serve` does not register clients or save CLI overrides. A second terminal must use matching saved/environment settings, and clients require the same HTTP endpoint and bearer token. Stop an existing service before using its storage in the foreground; a lock prevents duplicate daemon owners.

MPS is available for foreground use on supported Macs; managed systemd setup is Linux-only. CUDA/ROCm acceptance was performed on Linux.

## Claude and Codex marketplace installation

Both clients use one repository catalog, `.claude-plugin/marketplace.json`, and one portable manifest, `plugins/code-search-local/plugin.json`.

```sh
# Claude Code.
claude plugin marketplace add jglanz/code-search-local-mcp-plugin
claude plugin install code-search-local@code-search-local

# Codex.
codex plugin marketplace add jglanz/code-search-local-mcp-plugin
codex plugin add code-search-local@code-search-local
```

For a local checkout, replace `jglanz/code-search-local-mcp-plugin` with its absolute path in the marketplace-add command.

The plugin supplies a setup skill, not a second model server. Once the pinned Python version is published, invoke that skill and select your backend/client. For an unpublished source build, run the wheel-based setup in the [quick start](#quick-start) yourself; the packaged skill's PyPI command requires publication. After setup, reconnect the client to discover the tools. Direct CLI setup works without installing the plugin.

Installing both plugins shares the same user service and model cache. Removing a plugin preserves the service and indexes. Repository marketplace installation is separate from inclusion in any curated marketplace.

## MCP tools and resources

The Streamable HTTP endpoint defaults to `http://127.0.0.1:8000/mcp`. It uses bearer authentication and Host/Origin checks. Setup creates the token and client configuration; marketplace manifests contain no credentials.

Every project-specific tool takes an **absolute canonical project root**. There is no mutable current-project setting.

| Tool | Arguments / behavior |
|---|---|
| `index_directory` | `directory_path`, `incremental=True`, `file_patterns=None`, `wait=False`; submits a durable indexing job |
| `get_index_job` | `project_path`, `job_id`; reads status/progress |
| `cancel_index_job` | `project_path`, `job_id`; cancels without discarding the committed index |
| `search_code` | `project_path`, `query`, `k=10`, `filters=None`; searches the committed generation |
| `find_similar_code` | `project_path`, `chunk_id`, `k=5`; finds similar indexed chunks in that project |
| `get_index_stats` | Optional `project_path`; reports one or all projects with shared model statistics |
| `get_index_status` | `project_path`; reports index and job state |
| `list_projects` | No arguments; lists registered project roots and index information |
| `clear_index` | `project_path`; requires an idle project, clears its index and pauses its watcher until explicitly indexed again |

For example, an MCP `search_code` call can use these arguments:

```json
{
  "project_path": "/home/example/code/api",
  "query": "validate an authentication token",
  "k": 5,
  "filters": {"file_path": "*/auth/*"}
}
```

Filters match chunk metadata fields with shell globs. The CLI's `search` command currently exposes the query, project and result count; filters are available through MCP/the API.

Resources are `code-search-local://stats` and `code-search-local://stats/{project_id}`, where `project_id` is the SHA-256 of the canonical root. These are **MCP resource identifiers**, read with `resources/read` over the established connection. They do not register an operating-system or browser URL handler.

The authenticated administrative API used by the CLI exposes:

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Service health and daemon identity |
| POST | `/api/v1/model` | Shared model warmup |
| GET | `/api/v1/stats` | Snapshot; optional `project` query parameter |
| POST | `/api/v1/index` | Index a `directory_path`; accepts `wait`, `incremental`, `file_patterns` |
| POST | `/api/v1/search` | Search a `project_path` with `query`, optional `k`/`filters` |
| GET / DELETE | `/api/v1/jobs/{job_id}` | Inspect/cancel; requires the `project` query parameter |

These routes use the same bearer token as MCP. Use the CLI for ordinary administration so it reads the saved endpoint/token for you.

## Troubleshooting

| Symptom | What to check |
|---|---|
| `code-search-local: command not found` | For uv, run `uv tool update-shell` and open a new shell; for pipx, check its bin directory is on `PATH`; for pip, use the venv's `bin/code-search-local`. |
| Setup cannot find the package version | A local/unpublished installation needs `--package-source /absolute/path/to/the.whl`, even if the CLI itself is installed. |
| Cannot connect to the user systemd manager | Run setup from a Linux session with a working `systemctl --user`; use foreground operation when user systemd is unavailable. |
| Model download gets an access error | Check access approval for the configured model and Hugging Face authentication/`HF_TOKEN` in the setup shell. |
| GPU unavailable or wrong backend | Check the driver, `--backend`, GPU index and setup validation output. Inspect stats for the actual backend/fallback state. |
| GPU runs out of memory | Lower `CODE_SEARCH_MODEL_BATCH_SIZE` through setup, or explicitly allow CPU fallback. |
| Address already in use | Select another `--port` through setup so both clients are re-registered with the new endpoint. |
| Service owns the storage already | Use the existing daemon, or stop it before starting foreground `serve` against the same directory. |
| Service unavailable | Check `service status` and `journalctl --user -u code-search-local.service -n 100 --no-pager`. Confirm the CLI resolves the expected storage/port with `doctor`. |
| Project is not registered / has no index | Run `index` on that exact project root and check the returned job's `status` and `error`. Parent and child roots are distinct projects. |
| Expected files are missing | Check ignore files, supported extensions, `--pattern` restrictions and `max_file_bytes`. Reindex after correcting them. |
| Model changed since the index was built | Reindex with the current configured model; `index --rebuild` explicitly requests a full rebuild. |
| Tools absent after setup | Reconnect/restart the client. Confirm setup selected that client and the expected config directory. |
| Live statistics show offline state | Start the service and check the saved endpoint/storage; the live view reconnects. `--json` and `--live` are mutually exclusive. |

`doctor --inference` requires server/model dependencies in the executing Python environment and loads a model for diagnostics. A lightweight CLI installation may not contain those dependencies. Setup already runs this check inside the managed backend environment; use `warmup` to exercise the running daemon, or run `doctor --inference` from a development environment with the matching server/backend extras.

## Architecture and development

Each project serializes its indexing requests. A bounded shared parsing pool processes files, and one fair model thread handles query/document batches for all projects. Searches read immutable committed generations while updates run. FAISS vectors, SQLite metadata, Merkle hashes and model identity publish together through an atomic manifest replacement. Cancellation and crashes cannot publish half an index.

watchfiles detects changes, content hashes determine the actual additions/modifications/deletions, and an embedding cache avoids repeated inference for matching content/model/encoding. Startup recovers interrupted jobs and reconciles registered workspaces. Legacy indexes are backed up under `legacy-backups/` before rebuilding; existing Hugging Face model caches are reused.

Source lives under `src/code_search_local/`, fixtures under `tests/conftest.py`, and the build hook under `scripts/build_backend.py`. All dependencies/tool settings are declared in `pyproject.toml`; `uv.lock` records reproducible resolution. Generated resource copies, environments, indexes, logs, coverage output and distribution artifacts are ignored by Git. `.omc/` is left untouched.

```sh
uv sync --locked --extra server --extra cpu
uv run --no-sync pytest --cov --cov-report=json:coverage.json
uv run --no-sync python scripts/check_coverage.py
uv run --no-sync ruff check src scripts tests --select F,I
uv build
```

See [tests/README.md](tests/README.md) for the real two-Claude, GPU, systemd, marketplace and installer acceptance lanes, and [docs/validation.md](docs/validation.md) for recorded results. CI runs deterministic coverage and artifact installation checks. The manually dispatched release workflow requires acceptance checks before optional PyPI publication.

Licensed under GPL-3.0-only; see [LICENSE](LICENSE). The original project was created by Farhan Ali Raza and inspired by [zilliztech/claude-context](https://github.com/zilliztech/claude-context). Historical authorship and license attribution are retained.
