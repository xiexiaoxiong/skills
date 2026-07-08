#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="${IP_PROPOSAL_VENV:-$SKILL_DIR/.venv}"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$SKILL_DIR/requirements.txt"
"$VENV_DIR/bin/python" "$SCRIPT_DIR/make_visual_contact_sheet.py" --self-test

echo "IP-Proposal environment ready: $VENV_DIR"
echo "Use: $VENV_DIR/bin/python scripts/make_visual_contact_sheet.py --help"
