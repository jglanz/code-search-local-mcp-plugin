# Code Search Local plugin

Install this repository marketplace, add the `code-search-local` plugin, then invoke its `setup` skill once. The skill installs the pinned Python distribution and registers a user-scoped HTTP MCP connection. No credentials or machine-specific paths are stored in this plugin.

Both Claude and Codex use the same user service and persistent model cache. Removing a plugin does not stop that shared service.
