---
name: setup
description: Install or update the shared Code Search Local user service and register its HTTP MCP connection for Claude, Codex or OpenCode.
---

Run this skill when the user requests Code Search Local setup. Determine the selected harness: Claude, Codex, OpenCode, or an explicitly requested combination. For an installed Claude/Codex marketplace plugin, include `--marketplace` and select that harness. Direct CLI/source installations and OpenCode-only setup omit `--marketplace`. For a source-development installation from a Claude marketplace plugin, run from the user's checkout:

```sh
hatch run rocm:setup --agent-harness claude --marketplace --no-cpu-fallback
```

Select `cpu:setup` or `cuda:setup` when requested. This runs `setup --source <checkout>`: it installs editable source into `.venvs/<backend>`, sets the user service's working directory to the checkout, and launches its backend Python. It requires no wheel, tarball or published package. After code edits, run `hatch run rocm:cli service restart` using the selected backend; after dependency edits, update the lockfile and rerun source setup. Keep the checkout and its environments in place while the service uses them.

For a published release used by an installed Claude/Codex marketplace plugin, run the matching command:

```sh
uvx --from code-search-local==1.0.0 code-search-local setup --backend auto --agent-harness claude --marketplace
uvx --from code-search-local==1.0.0 code-search-local setup --backend auto --agent-harness codex --marketplace
```

For OpenCode, register its direct HTTP MCP connection and verify it with the OpenCode CLI:

```sh
# Live source checkout:
hatch run rocm:setup --agent-harness opencode
# Published release instead:
uvx --from code-search-local==1.0.0 code-search-local setup --backend auto --agent-harness opencode
# Check the registered server:
opencode mcp list
```

Setup supports OpenCode JSON/JSONC and honors `OPENCODE_CONFIG`/`OPENCODE_CONFIG_DIR`; use the same environment when launching OpenCode. Reopen the agent session after registration. For direct setup of all three harnesses, use `--agent-harness all`; for a subset, repeat `--agent-harness` once per selected harness.

If the user specifies CPU, CUDA or ROCm, pass that backend instead of auto. For Codex, use `--agent-harness codex`. If both plugins are installed and both clients are requested, pass `--agent-harness claude --agent-harness codex --marketplace`. Select additional OpenCode registration with `--agent-harness opencode` only when requested. For a direct/source CLI installation independent of any marketplace, omit `--marketplace`; registration defaults to `none`. A configured backend and GPU index remain user choices; do not replace them during ordinary searches.

If uvx is unavailable, install `code-search-local==1.0.0` with pipx, or pip in a virtual environment, and run the same `code-search-local setup` command. The package includes uv for its managed runtime installer.

Setup downloads the selected runtime and model into persistent user storage, validates actual inference, installs a user systemd service, and registers an authenticated loopback HTTP MCP connection. It preserves other MCP connections. After setup, reconnect this client to discover the server's tools.

For indexing and searching, always pass the current workspace's absolute root path. For requests such as "Index code", "Index codebase" or "Update index", use `index_directory` with incremental updates by default and follow `get_index_job` until a terminal status. Only `succeeded` means complete; report failed/cancelled/interrupted outcomes instead of polling forever. Use `search_code` to locate behavior, `find_similar_code` with an existing result's chunk ID, `get_index_status` for readiness/jobs, `get_index_stats` for usage/model/GPU details, and `list_projects` to discover registered roots. Cancel a requested job with `cancel_index_job` and follow it to completion. Use `clear_index` only when the user explicitly asks to discard an index. Models belong to the shared service; never launch a model process per workspace. Use `code-search-local stats --live` for live activity.

Native marketplace uninstall stops and removes the shared user service and its recorded MCP registrations. Setup installs a systemd registry watcher and a 30-second retry timer because Claude/Codex expose no uninstall hook. Disabling the plugin leaves the service installed. Removing either tracked plugin stops the service for all clients/projects, while the other plugin package, stored indexes and models remain. The cleanup executable lives outside the plugin cache. Direct `code-search-local uninstall` also unregisters this plugin from Claude/Codex/OpenCode; `service uninstall` is a compatibility alias. Do not delete runtime environments before service cleanup finishes.
