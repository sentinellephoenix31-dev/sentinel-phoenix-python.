#!/usr/bin/env bash
set -eu
PROJECT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$PROJECT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    printf 'Missing Python environment: %s
Create .venv and install requirements first.
' "$PYTHON" >&2
    exit 1
fi
LOG_DIR="$PROJECT/data/logs"
mkdir -p "$LOG_DIR"
cd "$PROJECT"
export PYTHONUNBUFFERED=1
exec "$PYTHON" -u -m core.sentinel_launcher >> "$LOG_DIR/sentinel_autostart.log" 2>&1
