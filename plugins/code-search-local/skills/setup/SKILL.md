---
name: setup
description: Install or update the shared Code Search Local user service and register its HTTP MCP connection for Claude or Codex.
---

Run this skill when the user requests Code Search Local setup. Determine whether this client is Claude or Codex, and run the matching command:

```sh
uvx --from code-search-local==0.2.0 code-search-local setup --backend auto --client claude
uvx --from code-search-local==0.2.0 code-search-local setup --backend auto --client codex
```

If the user specifies CPU, CUDA or ROCm, pass that backend instead of auto. If both clients are requested, pass `--client both`. A configured backend and GPU index remain user choices; do not replace them during ordinary searches.

If uvx is unavailable, install `code-search-local==0.2.0` with pipx, or pip in a virtual environment, and run the same `code-search-local setup` command. The package includes uv for its managed runtime installer.

Setup downloads the selected runtime and model into persistent user storage, validates actual inference, installs a user systemd service, and registers an authenticated loopback HTTP MCP connection. It preserves other MCP connections. After setup, reconnect this client to discover the server's tools.

For indexing and searching, always pass the current workspace's absolute root path. Use `index_directory` and follow `get_index_job` until its status is succeeded. Models belong to the shared service; never launch a model process per workspace. Use `code-search-local stats --live` for live activity.

Uninstalling this plugin leaves the shared service and indexes intact. To explicitly remove the user service run `code-search-local service uninstall`; stored indexes and models are preserved.
