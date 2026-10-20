#!/usr/bin/env bash
set -euo pipefail
# Source-checkout wrapper. Python setup owns runtime and client configuration.
script_path="$(realpath -- "${BASH_SOURCE[0]}")"
# This script lives at <checkout>/packages/code-search-local/scripts/install.sh.
project_root="$(realpath -- "$(dirname -- "$script_path")/../../..")"
cd "$project_root"
exec hatch run cli setup --source "$project_root" "$@"
