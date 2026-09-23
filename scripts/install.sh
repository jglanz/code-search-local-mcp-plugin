#!/usr/bin/env bash
set -euo pipefail
# Compatibility wrapper. Python setup owns all runtime and client configuration.
exec uvx --from code-search-local==0.2.0 code-search-local setup "$@"
