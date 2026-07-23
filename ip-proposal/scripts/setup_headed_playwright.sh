#!/usr/bin/env bash
set -euo pipefail

runtime_dir="${IP_PROPOSAL_PW_RUNTIME_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/ip-proposal-playwright}"

command -v node >/dev/null
command -v npm >/dev/null

mkdir -p "$runtime_dir"
npm install --prefix "$runtime_dir" --no-save --no-audit --no-fund playwright-core

echo "Playwright runtime installed: $runtime_dir/node_modules"
echo "Set IP_PROPOSAL_PW_MODULE_DIR=$runtime_dir/node_modules when the agent does not inherit the default cache path."
