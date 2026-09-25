# Code Search Local plugin

Install this repository marketplace, add the `code-search-local` plugin, then invoke its `setup` skill once. The skill installs the pinned Python distribution and registers a user-scoped HTTP MCP connection. No credentials or machine-specific paths are stored in this plugin.

Both Claude and Codex use the same user service and persistent model cache. Setup binds marketplace removal to service cleanup. Uninstalling either tracked plugin stops and removes the shared user service and recorded MCP connections, then removes the systemd cleanup watcher. The other client's plugin package, indexes and model cache remain. Disabling a plugin leaves the service running. For a direct/source CLI installation, run `code-search-local uninstall` (or `hatch run rocm:cli uninstall` with your selected backend); it also removes this plugin's harness registrations.

OpenCode uses the same HTTP MCP server through direct registration:

```sh
# Source checkout (ROCm example):
hatch run rocm:setup --agent-harness opencode
# Installed CLI:
code-search-local setup --backend rocm --agent-harness opencode
# Verify in OpenCode:
opencode mcp list
```

Choose `cpu` or `cuda` as needed. Use `--agent-harness all` for Claude, Codex and OpenCode, or repeat the flag for a subset. OpenCode does not use this Claude/Codex marketplace catalog; omit `--marketplace` for its direct setup. See the [OpenCode walkthrough](../../README.md#opencode-setup-and-usage) for config paths, iteration and uninstall.
