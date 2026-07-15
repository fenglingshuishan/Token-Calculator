#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v python3)"
fi

exec "$PYTHON" "$ROOT/stop.py" "$@"
