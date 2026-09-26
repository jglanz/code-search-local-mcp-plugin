# Code Search Local MCP Plugin

Local semantic code search for Claude Code, Codex and OpenCode, with one shared embedding model and a separate durable index for every project. Index several workspaces concurrently without starting a model process for each client. Embeddings run on CPU, NVIDIA CUDA or AMD ROCm; FAISS vector search runs on the CPU.

This is an independently maintained hard fork. The Python package and CLI are named `code-search-local`; the repository is [`jglanz/code-search-local-mcp-plugin`](https://github.com/jglanz/code-search-local-mcp-plugin).

- [Quick start](#quick-start)
- [Run from source with Hatch](#run-from-source-with-hatch)
- [Installation options](#installation-options)
- [Setup guide](#setup-guide)
- [OpenCode setup and usage](#opencode-setup-and-usage)
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
- Python **3.12–3.14**, Git, and Hatch **1.18.1** for the repository workflows below. Install Hatch with `uv tool install hatch==1.18.1` or `pipx install hatch==1.18.1`. The checkout uses Python 3.12 environments at `.venvs/cpu`, `.venvs/cuda` and `.venvs/rocm`; Hatch and uv are declared in `pyproject.toml`. Installing an existing wheel does not require Hatch.
- Optionally, Claude Code, Codex or OpenCode. Repeat `--agent-harness` to select clients; `--agent-harness all` selects all three. The default `none` installs only the service.
- For GPU use, a compatible installed NVIDIA or AMD driver. Setup installs GPU Python libraries into its own virtual environment and does not replace system drivers or the system ROCm toolkit.
- Internet access for the initial dependencies, model and parser-grammar downloads. The default model is [`google/embeddinggemma-300m`](https://huggingface.co/google/embeddinggemma-300m). Complete any model access approval and authenticate with Hugging Face, or supply `HF_TOKEN` in the setup shell, before downloading a gated model.

### 2. Clone and prepare the source environment

```sh
git clone https://github.com/jglanz/code-search-local-mcp-plugin.git
cd code-search-local-mcp-plugin
hatch run rocm:sync
```

Use `cuda:sync` for NVIDIA or `cpu:sync` for CPU. Each installs the editable checkout into its own environment under `.venvs/`. All three environments can exist together; creating one leaves the others intact.

### 3. Install a source service for your agent harnesses

```sh
hatch run rocm:setup --agent-harness all --gpu-index 0 --no-cpu-fallback
```

The `rocm:setup` script supplies `--source <checkout>` and `--backend rocm`. For NVIDIA use `cuda:setup`; for CPU use `cpu:setup`. `--agent-harness all` registers Claude, Codex and OpenCode. Select `--agent-harness claude`, `--agent-harness codex` or `--agent-harness opencode` for one client, or repeat the flag to select a subset. Omit `--agent-harness` to leave client configurations untouched.

This downloads the model when needed, validates real inference, installs and starts `code-search-local.service`, and registers the authenticated HTTP MCP connection. The unit's `ExecStart` uses `<checkout>/.venvs/rocm/bin/python -m code_search_local serve`, and its `WorkingDirectory` is the checkout. No release wheel, tarball, `hatch build`, or PyPI publication is needed.

Successful setup ends with JSON containing `mode: "source"`, `source`, `runtime`, `backend`, `service`, `url`, `agent_harness`, `harness_configs` and `installation_origin`. `harness_configs` lists the configuration file updated for each selected agent. The default endpoint is `http://127.0.0.1:8000/mcp`. The service uses the checkout until you explicitly change its installation; keep that directory and its selected environment in place.

### 4. Index and search a project

From the checkout, replace the example directory with an existing project root:

```sh
hatch run rocm:cli service status
hatch run rocm:cli index "$HOME/code/my-project"
hatch run rocm:cli search 'where are authentication tokens validated?' \
  --project "$HOME/code/my-project" --max-results 5
hatch run rocm:cli stats --project "$HOME/code/my-project"
```

`index` waits by default and prints the job as JSON; check that its `status` is `succeeded`. Reconnect or restart Claude, Codex or OpenCode so it discovers the MCP connection. You can then ask it:

> Use Code Search Local to index this workspace, wait for the indexing job to succeed, then find the code that validates authentication tokens.

Indexing registers that project for automatic change detection. A second workspace uses the same service, with its own index and the shared model. The CLI examples later in this guide use `code-search-local`; from a source checkout, substitute `hatch run rocm:cli` (or your selected backend), or the absolute path to `.venvs/rocm/bin/code-search-local`.

## Run from source with Hatch

Hatch explicitly configures separate backend environments in `pyproject.toml`:

| Hatch environment | Directory | Purpose |
|---|---|---|
| `cpu` / `default` | `.venvs/cpu` | CPU source service, ordinary tests, linting and builds |
| `cuda` | `.venvs/cuda` | NVIDIA CUDA source service and GPU tests |
| `rocm` | `.venvs/rocm` | AMD ROCm source service and GPU tests |

PyTorch's CPU, CUDA and ROCm distributions install the same Python package name, so each environment contains one build. The three environments coexist. Selecting a different service backend does not uninstall packages from another environment. `hatch build` shares the CPU tooling environment and leaves GPU environments intact.

### Create or synchronize environments

```sh
hatch run cpu:sync
hatch run cuda:sync
hatch run rocm:sync
hatch env find cpu
hatch env find cuda
hatch env find rocm
```

Create only the environments you need. Each script uses `uv.lock` and the vendor indexes declared in `pyproject.toml`. A bare `hatch run cli`, `hatch run test` or `hatch run sync` uses the CPU environment. Use the environment prefix to select a backend; do not pass a backend name as an argument to `sync`.

### Install the user service directly from source

```sh
# AMD, registering Claude, Codex and OpenCode:
hatch run rocm:setup --agent-harness all --no-cpu-fallback

# Later, select NVIDIA while retaining the ROCm environment:
hatch run cuda:setup --agent-harness all --no-cpu-fallback
```

These configure the same user service, storage, model cache and per-project indexes. Only the selected environment runs the daemon, so multiple environments do not create multiple model owners. Re-running source setup synchronizes the selected environment, validates inference, and restarts the service to load current source. All selected harnesses continue to use its HTTP endpoint.

The underlying CLI also accepts an explicit checkout, including a relative path:

```sh
.venvs/rocm/bin/python -m code_search_local setup \
  --source . --backend rocm --agent-harness claude --agent-harness codex --no-cpu-fallback

# An installed CLI can provision a source service from another directory:
code-search-local setup --source /absolute/path/to/code-search-local-mcp-plugin \
  --backend rocm --agent-harness claude --agent-harness codex
```

`--source` and `--package-source` cannot be combined. Source setup uses the live `src/code_search_local` tree through an editable installation; it does not copy the application into a versioned release runtime. The backend Python path comes from the checkout's Hatch configuration. The existing `setup` command without `--source` remains available for [release installations](#installation-options).

### Iterate against Claude, Codex and OpenCode

After editing Python source, restart the service and continue using the same clients and indexed projects:

```sh
hatch run rocm:cli service restart
hatch run rocm:cli service status
hatch run rocm:cli stats --live
```

No build, installation or model download is required for ordinary Python edits. An already running Python process loads the edits on restart; file watching detects changes in indexed projects, not changes to the server implementation.

For dependency changes, stop the service, update the shared lockfile, and rerun source setup:

```sh
hatch run rocm:cli service stop
hatch run uv lock
hatch run rocm:setup --agent-harness all --no-cpu-fallback
```

Source setup refreshes bundled metadata/plugin resources too. To refresh those without installing a service, use `hatch run rocm:sync --reinstall-package code-search-local`. Keep all environments on the current lockfile by running their `sync` scripts after dependency changes. If the checkout moves, rerun source setup at its new path to refresh `WorkingDirectory` and `ExecStart`.

### Optional foreground development

For an isolated foreground instance, use a separate storage directory and port. In the first terminal:

```sh
hatch run cpu:sync
export CODE_SEARCH_STORAGE="$PWD/.code-search-local"
export CODE_SEARCH_PORT=8123
hatch run cpu:serve --no-watch
```

In a second terminal from the checkout:

```sh
export CODE_SEARCH_STORAGE="$PWD/.code-search-local"
export CODE_SEARCH_PORT=8123
hatch run cpu:cli index /absolute/path/to/project
hatch run cpu:cli stats --live
```

`hatch run rocm:serve` and `hatch run cuda:serve` select the matching backend automatically. The first model operation downloads the configured model if it is not cached. Omit `--no-watch` for automatic change detection in indexed projects. Stop a foreground server with Ctrl+C.

Direct invocation uses the same editable source, without activation or `PYTHONPATH` changes:

```sh
.venvs/rocm/bin/python -m code_search_local --help
.venvs/rocm/bin/code-search-local stats --json
.venvs/rocm/bin/python -m code_search_local serve --backend rocm --no-watch
```

### Test, lint and build releases

```sh
hatch run test
hatch run test tests/unit/test_config_cli.py -q
hatch run coverage
hatch run lint
hatch run fmt --check
hatch build
```

`hatch run fmt` applies formatting. `coverage` enforces separate line and branch floors. `hatch build` is only needed to produce release wheel/sdist artifacts in `dist/`; source setup and iteration do not depend on it. Use the configured `hatch run test`/`lint` scripts instead of Hatch's automatic `hatch test`/`hatch check` environments. See [tests/README.md](tests/README.md) for GPU, source-systemd, packaging and real-client acceptance commands.

## Installation options

### Install a locally built wheel

Build once with `hatch build`, then choose **one** CLI installation method. These examples run from the checkout:

| Installer | Command |
|---|---|
| uv tool | `uv tool install ./dist/code_search_local-1.0.0-py3-none-any.whl` |
| pipx | `pipx install ./dist/code_search_local-1.0.0-py3-none-any.whl` |
| pip in a venv | Use the commands below |
| uvx, without a permanent CLI environment | Use the command below |

```sh
# pip: always use a virtual environment.
python3 -m venv "$HOME/.venvs/code-search-local"
"$HOME/.venvs/code-search-local/bin/python" -m pip install \
  ./dist/code_search_local-1.0.0-py3-none-any.whl
"$HOME/.venvs/code-search-local/bin/code-search-local" setup \
  --agent-harness claude --agent-harness codex --backend rocm \
  --package-source ./dist/code_search_local-1.0.0-py3-none-any.whl
```

```sh
# uvx: both the temporary CLI and persistent service receive the local wheel.
uvx --from ./dist/code_search_local-1.0.0-py3-none-any.whl \
  code-search-local setup --agent-harness claude --agent-harness codex --backend rocm \
  --package-source ./dist/code_search_local-1.0.0-py3-none-any.whl
```

The CLI includes uv as a dependency. Regardless of how you install the CLI, setup uses uv and the bundled lock file to provision the service. pip and pipx do not need to understand uv's vendor-index configuration. Use `setup --backend ...` to select the runtime; do not install GPU extras directly with pip.

### Install a published release

The following examples require version `1.0.0` to have been published to your package index. Building or pushing this repository does not publish it to PyPI.

```sh
uv tool install code-search-local==1.0.0
code-search-local setup --agent-harness claude --agent-harness codex --backend rocm

# Alternative: pipx.
pipx install code-search-local==1.0.0
code-search-local setup --agent-harness claude --agent-harness codex --backend cuda

# Alternative: uvx, with no permanent CLI installation.
uvx --from code-search-local==1.0.0 \
  code-search-local setup --agent-harness claude --agent-harness codex --backend auto
```

For pip, use the venv commands above and replace the wheel path in `pip install` with `code-search-local==1.0.0`; omit `--package-source` from setup.

## Setup guide

### Select a backend and clients

These examples use an installed CLI. Add `--source /absolute/path/to/checkout` for a source service, or use `hatch run rocm:setup` / `cuda:setup` / `cpu:setup` from the checkout. For a release installed from a local wheel, append `--package-source /absolute/path/to/code_search_local-1.0.0-py3-none-any.whl`.

```sh
# AMD: require ROCm on GPU 0; report a failure instead of falling back.
code-search-local setup --agent-harness claude --agent-harness codex --backend rocm --gpu-index 0 --no-cpu-fallback

# NVIDIA: require CUDA on GPU 0.
code-search-local setup --agent-harness claude --agent-harness codex --backend cuda --gpu-index 0 --no-cpu-fallback

# Explicitly permit CPU fallback after a GPU initialization or inference failure.
code-search-local setup --agent-harness claude --backend rocm --cpu-fallback

# CPU only, configuring OpenCode.
code-search-local setup --agent-harness opencode --backend cpu

# Configure Codex and OpenCode only.
code-search-local setup --agent-harness codex --agent-harness opencode --backend rocm

# Probe available hardware and permit CPU fallback.
code-search-local setup --agent-harness claude --agent-harness codex --backend auto --cpu-fallback
```

GPU indexes are zero-based within the selected backend. ROCm uses PyTorch's `cuda:N` device API internally, but the HIP build identifies it as ROCm in statistics. Managed setup provisions separate CUDA and ROCm service runtimes; source development keeps them side by side under `.venvs/`. One running daemon uses one selected backend and model for all projects.

Automatic setup tests CUDA first when detected, then available ROCm, then CPU if fallback is enabled. A successful choice is reused on unchanged setup. With no saved override, `auto` allows CPU fallback and explicit backends do not. Pass `--cpu-fallback` or `--no-cpu-fallback` when changing that policy intentionally.

The tested runtime uses PyTorch 2.14.0 with CUDA 13.0 or ROCm 7.14 and ROCm 7.14.1 venv libraries. A separately installed ROCm toolkit is not required by this packaged runtime. See [hardware validation](docs/validation.md) for the tested GPUs and [dependency selection](docs/dependencies.md) for exact versions and sources.

### Choose storage, port and model

```sh
code-search-local setup \
  --agent-harness claude --agent-harness codex \
  --backend rocm \
  --gpu-index 0 \
  --no-cpu-fallback \
  --storage "$HOME/.local/share/code-search-local" \
  --port 8123 \
  --model google/embeddinggemma-300m \
  --revision 57c266a740f537b4dc058e1b0cda161fd15afa75
```

Setup persists these settings and registers the selected harnesses at the selected port. Storage contains the project registry, indexes, model cache, embedding cache, authentication token and versioned service environments. Changing `--storage` selects a different data set; it does not move existing files. Retain the original directory to keep using its indexes.

The default revision `main` is resolved to a pinned snapshot on acquisition. An explicit commit revision makes the choice reproducible. Changing the model/revision requires indexing registered projects with the new model; use `index --rebuild` when you need to request it explicitly. Index metadata records which model produced its vectors.

### What setup changes

1. With `--source`, synchronizes the editable checkout in its `.venvs/<backend>` environment using the checkout's lockfile. Otherwise, creates or reuses a versioned release environment under `<storage>/runtimes/` from the bundled lockfile.
2. Prefetches supported parser grammars and validates actual model inference before replacing a running service.
3. Stops the existing service before replacing its settings and unit, once validation succeeds.
4. Saves effective settings to `$XDG_CONFIG_HOME/code-search-local/config.json`, normally `~/.config/code-search-local/config.json`, ensures a private token at `<storage>/auth.json`, and installs the user unit at `$XDG_CONFIG_HOME/systemd/user/code-search-local.service`.
5. Reloads systemd, enables and starts the service, then waits for its authenticated health endpoint. Restoring existing indexes can take longer than a fresh startup. Setup reports progress and allows 300 seconds by default; `--startup-timeout SECONDS` changes this limit. Each health request has a bounded timeout, and an exited/crashing service fails immediately with recent journal output.
6. Adds or updates `code-search-local` in every selected harness, then reports the configuration paths in the final JSON. Model-validation output alone does not mean setup has completed.

Registration is optional and user-scoped. `--agent-harness none` is the default; it leaves agent configurations untouched. Repeat the flag to select particular clients, or use `all` for Codex, Claude and OpenCode:

```bash
code-search-local setup --backend rocm                         # service only
code-search-local setup --backend rocm --agent-harness opencode
code-search-local setup --backend rocm --agent-harness codex --agent-harness claude
code-search-local setup --backend rocm --agent-harness all
```

Do not combine `none` with another selection. Each selected harness has this plugin's pre-existing native plugin registration and MCP entry removed before setup writes a single authenticated HTTP MCP entry. A direct/source installation therefore replaces an earlier marketplace installation in the selected harness. Native plugin removal uses the installed Claude/Codex CLI when available. Unrelated plugins and settings are preserved. `--marketplace` keeps the installed marketplace plugin and binds service cleanup to its removal; see [marketplace installation](#claude-and-codex-marketplace-installation).

Configuration paths:

| Harness | User configuration |
| --- | --- |
| Codex | `$CODEX_HOME/config.toml`, default `~/.codex/config.toml` |
| Claude | `~/.claude.json`; with `CLAUDE_CONFIG_DIR`, `$CLAUDE_CONFIG_DIR/.claude.json` |
| OpenCode | `$XDG_CONFIG_HOME/opencode/opencode.json` or `.jsonc`, default `~/.config/opencode/`; honors `OPENCODE_CONFIG_DIR` and `OPENCODE_CONFIG` |

Existing files receive private `.code-search-local.bak` backups. Codex TOML comments are preserved; OpenCode JSONC is accepted and normalized to formatted JSON when changed, with the original comments retained in the backup. Stale Code Search Local entries in the applicable OpenCode config files are removed before adding the replacement to the selected effective config. A failed registration write restores that harness's MCP configuration. Setup records selected config paths in `$XDG_CONFIG_HOME/code-search-local/installation.json` so uninstall can also clean up custom profiles used earlier. Project-local and administrator-managed harness configurations are outside this user-scoped setup.

Repeat setup with the desired harness flags to add another client or apply new settings. An unchanged successful release setup reuses the running service; source setup restarts it to load current code. Neither opening another project nor registering another harness creates another daemon.

For example, after a Claude-only source setup, this enables CPU fallback and refreshes Claude, Codex and OpenCode:

```sh
hatch run rocm:setup --agent-harness all --cpu-fallback
# Allow ten minutes if restoring a large existing index needs longer:
hatch run rocm:setup --agent-harness all --cpu-fallback --startup-timeout 600
```

If startup fails or exceeds the limit, setup exits with an error before changing harness registrations. The new service configuration remains installed and the service may still be starting. Inspect the reported journal output and rerun setup after resolving the failure (or with a longer startup timeout) to complete registration.

## OpenCode setup and usage

OpenCode connects directly to the shared HTTP MCP service. Its registration, JSON/JSONC configuration and uninstall cleanup are implemented alongside Claude and Codex. The repository's marketplace catalog is for Claude/Codex; OpenCode uses `--agent-harness opencode` without `--marketplace`.

### Run from this checkout

```sh
hatch run rocm:setup --agent-harness opencode --gpu-index 0 --no-cpu-fallback
```

Use `cuda:setup` or `cpu:setup` for the corresponding backend. This installs the user service from the live checkout and `.venvs/<backend>/bin/python`, with no release artifact. To share it with Codex, for example:

```sh
hatch run rocm:setup --agent-harness opencode --agent-harness codex
```

Use `--agent-harness all` to register OpenCode, Codex and Claude together. Each connects to the same model owner and keeps its workspace indexes separate.

### Use an installed CLI

After installing with [uv, uvx, pip or pipx](#installation-options), run:

```sh
code-search-local setup --backend rocm --agent-harness opencode
```

A locally built, unpublished release additionally needs `--package-source /absolute/path/to/code_search_local-1.0.0-py3-none-any.whl`. For a published release, a one-shot installation is:

```sh
uvx --from code-search-local==1.0.0 code-search-local setup \
  --backend rocm --agent-harness opencode
```

### Verify and use the connection

From the workspace you want to search:

```sh
cd /absolute/path/to/your-project
opencode mcp list
opencode
```

`opencode mcp list` should show `code-search-local` as connected. Ask “Index codebase”, “Update index”, or “Find where authentication tokens are validated using Code Search Local”. Reopen an existing OpenCode session after setup so it reloads its MCP configuration. The same nine MCP tools and workspace-routing rules apply to every harness.

Setup writes the `mcp.code-search-local` entry with `type: "remote"`, the loopback `/mcp` URL, `enabled: true`, `oauth: false`, and its bearer authorization header. The generated token is private; setup supplies it automatically. This uses OpenCode's [documented remote MCP configuration](https://opencode.ai/docs/mcp-servers/).

### Configuration paths and removal

Setup honors the [OpenCode config locations](https://opencode.ai/docs/config/): `$XDG_CONFIG_HOME/opencode/opencode.json` or `.jsonc` (default `~/.config/opencode/`), plus `OPENCODE_CONFIG` and `OPENCODE_CONFIG_DIR` when set. Use the same overrides in your setup shell and OpenCode shell. Existing Code Search Local entries in those selected user config files are replaced; unrelated entries remain. JSONC comments are retained in `.code-search-local.bak` while the edited config is normalized to JSON. Project-local, inline and administrator configurations can override user settings; check those if the connection is unexpectedly disabled or uses a different URL.

To stop/remove the shared service and unregister its user-scoped connections, including OpenCode:

```sh
code-search-local uninstall
# Or, from this checkout using your selected backend:
hatch run rocm:cli uninstall
```

Removing or disabling an MCP entry manually in OpenCode only changes its client connection. Use `code-search-local uninstall` to remove the service; indexes, models and environments are retained. The shared service stops for all harnesses when uninstalled.

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

Generated/build directories, symlinks, binary files and files above `max_file_bytes` are skipped. Parsers cover Python, JavaScript/TypeScript, JSX/TSX, C/C++, C#, Java, Go, Rust, Solidity, Svelte and Markdown.

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
code-search-local search 'database transaction rollback' --project "$HOME/code/api" --max-results 5
```

`--max-results` (short form `-k`) accepts 1–100 results and defaults to 10. Use `code-search-local search --help` for all search options; every command exposes its flag descriptions through `--help`.

Search prints JSON results containing scores and chunk metadata, including source locations. It reads the last committed generation, which remains available while indexing runs. Finish the initial index before searching a new project.

In Claude, Codex or OpenCode, ask for semantic intent rather than only exact symbol names. For example:

> Search this workspace with Code Search Local for retry/backoff logic. Show the matching files and line numbers, then inspect the relevant implementation.

All three harnesses route tools through the same service. Tools always carry the project root, so parallel sessions cannot change another session's current project. MCP additionally provides metadata filters, similar-chunk search and explicit index clearing; see the [tool reference](#mcp-tools-and-resources).

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

`--agent-harness none|codex|claude|opencode|all` is optional and repeatable, defaults to `none`, and selects registration targets rather than a backend setting. Use `all` for all three harnesses or repeat the flag for a subset; `both` is not an `--agent-harness` value. `--package-source FILE` is setup-only and selects a locally built wheel for the persistent runtime.

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
code-search-local setup --agent-harness claude --agent-harness codex --backend rocm --no-cpu-fallback
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

### Update a source service

```sh
git pull --ff-only
hatch run rocm:setup --agent-harness all --no-cpu-fallback
```

Use your selected backend prefix. Python-only edits need just `hatch run rocm:cli service restart`; dependency changes require source setup or synchronization first. Indexes and models remain in the existing storage root.

### Upgrade a release installed from a local wheel

```sh
git pull --ff-only
hatch build
uv tool install --force ./dist/code_search_local-1.0.0-py3-none-any.whl
code-search-local setup --agent-harness claude --agent-harness codex \
  --package-source ./dist/code_search_local-1.0.0-py3-none-any.whl
```

Run this from the checkout and use the wheel filename matching the new version when it changes. Omitting `--backend` reuses the saved setting. For pipx, install the new wheel with `pipx install --force`; for pip, use the existing venv's Python with `-m pip install --upgrade --force-reinstall`. With uvx, invoke the new wheel directly as shown in [installation options](#installation-options).

For a published installation, upgrade the CLI with its original installer and rerun setup. Setup installs and validates a new versioned runtime before switching the service. Indexes and caches stay under the same storage root. The service's executable lives in that persistent runtime, so removing a temporary uvx environment or uv download cache does not remove the installed service.

### Uninstall the service

```sh
code-search-local uninstall

# From a checkout, use the environment you already installed:
hatch run rocm:cli uninstall
```

This stops and disables the shared user service, removes its unit and marketplace cleanup units, and unregisters Code Search Local's user-scoped MCP entries and native plugin installations from Claude, Codex and OpenCode. It checks both the recorded setup profiles and current configuration paths. Unrelated registrations remain. The older `code-search-local service uninstall` command performs the same cleanup.

Uninstall is repeatable. If a harness config is malformed or its native plugin removal fails, the service is still removed and the command reports which harness needs attention; the installation record is retained so a retry can finish cleanup. Indexes, model caches, runtime environments, source checkouts and the CLI package are preserved. Remove the CLI with its original installer after running uninstall. Remove stored data separately only if you intend to discard it.

### Review and clean current and legacy installations

[`scripts/clean_existing_installations_and_configs.py`](scripts/clean_existing_installations_and_configs.py) inventories Linux installations under both `code-search-local` and the former `claude-context-local` name, including case and underscore variants and the legacy `claude-code-search` storage directories. Run it from this checkout using an existing project environment:

```sh
.venvs/cpu/bin/python scripts/clean_existing_installations_and_configs.py --dry-run

# Machine-readable inventory; includes planned actions and references needing review:
.venvs/cpu/bin/python scripts/clean_existing_installations_and_configs.py --dry-run --json

# Additional project-local configs/custom harness profiles; both options are repeatable:
.venvs/cpu/bin/python scripts/clean_existing_installations_and_configs.py --dry-run \
  --project-root /path/to/workspace --scan-root /path/to/custom/profile

# Preview index removal while retaining runtime environments and packages:
.venvs/cpu/bin/python scripts/clean_existing_installations_and_configs.py --dry-run --remove-indexes

# Preview uninstalling runtime/CLI packages while retaining indexes:
.venvs/cpu/bin/python scripts/clean_existing_installations_and_configs.py --dry-run --remove-runtime-packages

# Preview both optional removals (models and source environments are always retained):
.venvs/cpu/bin/python scripts/clean_existing_installations_and_configs.py --dry-run --remove-all
```

Use `.venvs/cuda/bin/python` or `.venvs/rocm/bin/python` if that is your installed environment. Dependencies come from `pyproject.toml`; this script reuses Click, json5, tomlkit and uv without installing anything during discovery. No bundle or running service is required.

The inventory covers Claude CLI/Desktop, Codex, OpenCode and common editor/agent MCP configuration locations; recorded and environment-selected custom profiles; discovered project roots; plugin registries/caches; user and system systemd services and activation units; matching server processes and their descendants; uv/pipx environments, Python distribution metadata, npm/bun/npx wrappers, package caches, desktop launchers, shell settings and cron entries. `--scope user` limits systemd, cron and shared launcher/package discovery to user locations; the default `--scope all` also examines system locations. Harness/process discovery targets the selected `--home`, which defaults to your home directory. Use explicit scan/project roots for other locations; this is not an unrestricted filesystem text replacement.

**Personally review the script and its dry-run output before executing cleanup. Only dry-run execution was used to validate this script; its destructive branch has not been executed, including in tests.** Real execution requires `--apply --reviewed` and an interactive `REMOVE BOTH INSTALLATIONS` confirmation. Close the affected agent sessions before your reviewed run to avoid their restarting a removed server. Files/process identities are checked again before modification; configurations are backed up privately under `~/.local/state/mcp-cleanup-backups/<timestamp>/`. Backups intentionally retain original configuration contents for recovery. `--backup-dir` selects a different new backup directory.

**Default cleanup uninstalls matching systemd services and removes this plugin's MCP and/or plugin registrations from every discovered harness.** It stops and disables the services and their activation units, removes their unit files/drop-ins/enablement links, removes installed plugin artifacts subject to the protections below, terminates server processes and reloads systemd. Neither optional removal flag is needed for these actions. Only indexes and runtime packages/environments are gated by the flags below. The `--grace-seconds` option controls the SIGTERM interval before SIGKILL. Unrelated registrations, agent applications and conversation/editor history are preserved.

**Existing backups are excluded in every mode, including `--remove-all`.** This covers recognized backup files and directories (such as `.bak`, `.backup`, `.old`, `.orig`, editor recovery files, dated config copies, `backups/` and `legacy-backups/`) and symlinks to them. Discovery does not read their contents. When an installed plugin directory contains backups, only eligible siblings are scheduled for removal; the parent and backups stay. A runtime environment or package cache containing backups is retained entirely so its original installer cannot remove those backups indirectly.

Reports list service and active registration actions before edits that only remove cached discovery or marketplace entries. Config edits include the matching namespace and field, while internal inode/hash checks stay out of the report. A cached MCP discovery entry is identified as cached metadata, not an active MCP registration.

| Option | Additional removal |
| --- | --- |
| No removal flags | Uninstall systemd services and remove matching MCP/plugin registrations across all discovered harnesses; retain indexes and runtime packages/environments. |
| `--remove-indexes` | Project indexes, Merkle state, index statistics, embedding caches and SQLite sidecars (backups are retained). |
| `--remove-runtime-packages` | Runtime/CLI packages and their package caches, using the detected original installer. |
| `--remove-all` | Both index removal and runtime/package removal. |

**Downloaded models are always retained, including with `--remove-all`.** Storage aliases remain available so preserved models/data can still be found. A runtime environment in any cloned checkout or linked Git worktree is never uninstalled or deleted, even when discovered through a symlink or located in another project's checkout. The script's own interpreter environment is also protected. A parent artifact containing protected models, a worktree or an unmanaged runtime is retained rather than recursively deleting its contents.

Runtime removal uses installer ownership evidence:

| Installation | Reviewed removal command |
| --- | --- |
| `uv tool install` | `uv tool uninstall <recorded-package>`, with its original `UV_TOOL_DIR`. |
| `pipx install` | `pipx uninstall <recorded-environment-name>`, with its original `PIPX_HOME`; injected packages use `pipx uninject`. |
| `pip install` inside a venv | That venv's `python -m pip uninstall -y <package>`. |
| `uv pip install` inside a venv | `uv pip uninstall --python <venv-python> <package>`. |
| `uvx` / uv package cache | Package-specific `uv cache clean <package>` with its original `UV_CACHE_DIR`. |

uv/pipx receipts and distribution `INSTALLER` files select the manager; the script never substitutes uv for pip or pipx. Shared venvs retain unrelated packages and the environment itself. For this project's verified, generated service runtimes outside a source checkout, it uninstalls the contained distributions with their recorded managers before removing the dedicated environment and provisioning directory. Installer commands are included in the dry-run report. Missing ownership metadata or an unavailable original installer leaves the runtime/package in place for review. No uninstall command or installer hook runs during dry-run. See the [uv tool/cache reference](https://docs.astral.sh/uv/reference/cli/#uv-tool-uninstall) and [pip uninstall reference](https://pip.pypa.io/en/stable/cli/pip_uninstall/) for the underlying commands.

JSONC files are rewritten as formatted JSON; original comments remain in the private backup. TOML comments on retained settings are preserved.

Ambiguous references, malformed or unsupported configurations (including YAML), inaccessible locations and distributions requiring OS-package ownership checks are listed for manual review. Shared system files and system units can require root; the script does not elevate itself. When using sudo, explicitly pass the original user's `--home` and preserve any custom profile/XDG overrides you intend to scan. A reviewed run reports an error if unresolved review items remain, rather than claiming every reference was removed.

### Foreground operation

Use `hatch run cpu:serve`, `hatch run cuda:serve` or `hatch run rocm:serve` from the checkout. Hatch selects the corresponding `.venvs/<backend>` environment. See the [source workflow](#run-from-source-with-hatch) for isolated port/storage examples.

The daemon creates its private token in storage, but `serve` does not register clients or save CLI overrides. Other terminals and MCP clients must use the same storage/endpoint settings; clients also need the bearer token from `<storage>/auth.json`. A storage lock prevents duplicate daemon owners. MPS is available for foreground use on supported Macs; managed systemd setup is Linux-only.

## Claude and Codex marketplace installation

For OpenCode, use the [direct setup walkthrough](#opencode-setup-and-usage).

Claude and Codex use one repository catalog, `.claude-plugin/marketplace.json`, and one portable manifest, `plugins/code-search-local/plugin.json`.

```sh
# Claude Code.
claude plugin marketplace add jglanz/code-search-local-mcp-plugin
claude plugin install code-search-local@code-search-local

# Codex.
codex plugin marketplace add jglanz/code-search-local-mcp-plugin
codex plugin add code-search-local@code-search-local
```

For a local checkout, replace `jglanz/code-search-local-mcp-plugin` with its absolute path in the marketplace-add command.

The plugin supplies a setup skill, not a second model server. Once the pinned Python version is published, invoke that skill and select your backend/harness. For a source checkout, use the direct source-service setup in the [quick start](#quick-start); the packaged skill's PyPI command requires publication. After setup, reconnect the client to discover the tools. Direct CLI setup works without installing the plugin.

When setting up from an installed marketplace plugin, the setup skill passes `--marketplace` and the calling harness:

```bash
uvx --from code-search-local==1.0.0 code-search-local setup \
  --backend rocm --agent-harness claude --marketplace

# For a marketplace plugin backed by the live checkout:
hatch run rocm:setup --agent-harness codex --marketplace
```

`--marketplace` requires this plugin to be installed in a selected Claude/Codex profile. If both plugins are installed, select both harnesses to track both. Source and release installations use the same cleanup mechanism. Direct CLI setup defaults to an independent installation; it does not infer marketplace ownership merely because a plugin is present.

Native marketplace uninstall **also stops and removes the user service**:

```bash
claude plugin uninstall code-search-local@code-search-local --scope user
codex plugin remove code-search-local@code-search-local
```

Claude and Codex do not expose a plugin-uninstall lifecycle hook. Setup therefore installs `code-search-local-marketplace.path`, `.timer` and `.service` alongside the shared service. The path unit watches the native plugin registration, and a 30-second timer retries missed events. Cleanup confirms removal after a two-second grace period, removes the shared service and recorded MCP connections, then removes its own watcher units. It runs from the persistent service environment, so removal of a plugin cache does not break cleanup. Disabling a plugin leaves the service running.

The service is shared: removing **either tracked marketplace plugin** stops service for every project/client. The other harness's installed plugin package remains; run its setup skill again to restore service. Cached models and indexes are preserved. An existing installation created before this cleanup support must rerun marketplace setup once to install the watcher. Repository marketplace installation is separate from inclusion in any curated marketplace.

## MCP tools and resources

The Streamable HTTP endpoint defaults to `http://127.0.0.1:8000/mcp`. It uses bearer authentication and Host/Origin checks. Setup creates the token and client configuration; marketplace manifests contain no credentials.

Every project-specific tool takes an **absolute canonical project root**. There is no mutable current-project setting.

Tool descriptions, [parameter schemas](https://gofastmcp.com/servers/tools#parameter-metadata) and server instructions tell the agent when to use each tool, how to select the workspace, and what to do with the result. Read-only tools are annotated accordingly; `clear_index` is explicitly marked destructive.

| User request / intent | Tool | Arguments / next step |
|---|---|---|
| “Index code”, “Index codebase”, “Update index”, “Refresh the index”, “Reindex” | `index_directory` | Pass the absolute workspace root as `directory_path`; keep `incremental=True` for ordinary updates. Default `wait=False` returns a job to follow. Set `incremental=False` for an explicit full rebuild. |
| “Is indexing done?”, “How far along is indexing?”, “Why did indexing fail?” | `get_index_job` | Pass the same `project_path` and returned `job_id`; inspect status, progress and error. |
| “Stop indexing”, “Cancel the index update” | `cancel_index_job` | Identify the project's active `job_id`, request cancellation, then follow `get_index_job` until terminal. The committed index remains usable. |
| “Search the code”, “Find where authentication is implemented” | `search_code` | Pass `project_path`, a focused `query`, optional `k=10` and metadata `filters`. Inspect returned source locations before explaining or editing code. |
| “Find similar code”, “Where else is this pattern used?” | `find_similar_code` | Use a current result's exact `chunk_id` with the same project; optional `k=5`. Results exclude the reference chunk. |
| “Show indexing stats”, “How many files are indexed?”, “Which model/GPU is used?” | `get_index_stats` | Supply `project_path` for one workspace or omit it for all; shared model stats are included. |
| “Is this codebase indexed?”, “Is the index up to date?”, “What's indexing?” | `get_index_status` | Pass `project_path`; inspect its committed generation, recorded timestamps/change counts and jobs. This reads recorded state without rescanning disk. |
| “List indexed projects”, “What repositories can I search?” | `list_projects` | No arguments; discover registered absolute roots, then check readiness if needed. |
| “Clear this project's index”, “Delete the code index” | `clear_index` | Use only for an explicit discard request. The project must be idle; its index is emptied and its watcher paused until indexed again. Source, models and other projects remain. |

For “Update index”, the expected tool sequence is:

1. Call `index_directory` with `{"directory_path": "/home/example/code/api", "incremental": true, "wait": false}`.
2. Retain its `job_id` and call `get_index_job` with that ID and `project_path: "/home/example/code/api"`. Pause briefly between polls while queued/running; do not submit duplicate indexing jobs just to check progress.
3. Report completion only on `succeeded`. Report `failed`, `cancelled` or `interrupted` accurately, including any returned error.

`file_patterns` on `index_directory` restricts the **entire indexed scope** using project-relative shell globs, such as `["src/*.py", "tests/*.py"]`. Omit it for all supported, non-ignored files. Files excluded by a new restriction leave the searchable index. Searching during an update reads the previous committed generation. To refresh an index, call `index_directory`; clearing is unnecessary. An unknown project or model mismatch requires indexing before search can succeed.

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
| Address already in use | Select another `--port` through setup and include each harness you use so their endpoints are refreshed. |
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

Source lives under `src/code_search_local/`, fixtures under `tests/conftest.py`, with Hatchling build configuration in `pyproject.toml`. All dependencies/tool settings are declared in `pyproject.toml`; `uv.lock` records reproducible resolution. Hatchling reads the version from `src/code_search_local/__init__.py` and maps the canonical lock, metadata and plugin resources directly into distributions; no custom build script or generated source copies are needed. Environments, indexes, logs, coverage output and distribution artifacts are ignored by Git.

```sh
hatch run cpu:sync
hatch run coverage
hatch run lint
hatch build
```

`hatch run lint` also runs the [code-rule audit](scripts/check_code_rules.py); use `hatch run rules` to run it alone. Operational values (schema keys, paths, protocol identifiers, defaults and timing budgets) live in named constants. Docstrings and explanatory prose stay inline. Shared behavior belongs in helpers when a 5+ line block occurs three times, or an 8+ line block occurs twice. The audit checks common operational-literal syntax and exact duplication, including repeated blocks within one file; review also checks parameterizable variants. Parser fixture source files are input data, not executed application code.

The project rule lives in [.agents/rules/constants-and-duplication.md](.agents/rules/constants-and-duplication.md), with `.claude/rules` symlinked to that directory. Application contracts are in `src/code_search_local/constants.py`; test-only inputs and budgets are in `tests/constants.py`. The standalone cleanup script keeps its own constants so it can inspect a broken or absent installation.

See [tests/README.md](tests/README.md) for the real two-Claude, GPU, systemd, marketplace and installer acceptance lanes, and [docs/validation.md](docs/validation.md) for recorded results. CI runs deterministic coverage and artifact installation checks. The manually dispatched release workflow requires acceptance checks before optional PyPI publication.

Licensed under GPL-3.0-only; see [LICENSE](LICENSE). The original project was created by Farhan Ali Raza and inspired by [zilliztech/claude-context](https://github.com/zilliztech/claude-context). Historical authorship and license attribution are retained.
