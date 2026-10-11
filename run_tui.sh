#!/usr/bin/env bash
# ==============================================================================
# run_tui.sh — Launch Climate Intelligence Right-Sizing & Observability TUI
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure venv Python is used if available
if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
else
    PYTHON_BIN="python"
fi

exec "$PYTHON_BIN" climate_rightsize_tui.py "$@"
