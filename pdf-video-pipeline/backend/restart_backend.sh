#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

if [[ ! -d ".venv" ]]; then
  echo "Missing .venv in $SCRIPT_DIR"
  echo "Create it first with:"
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -e .[dev]"
  exit 1
fi

source ".venv/bin/activate"

EXISTING_PIDS="$(
  ss -ltnp 2>/dev/null | awk -v port=":$PORT" '
    $4 ~ port {
      if (match($0, /pid=[0-9]+/)) {
        print substr($0, RSTART + 4, RLENGTH - 4)
      }
    }
  ' | sort -u || true
)"

if [[ -n "$EXISTING_PIDS" ]]; then
  echo "Stopping backend processes on port $PORT: $EXISTING_PIDS"
  for pid in $EXISTING_PIDS; do
    kill "$pid" 2>/dev/null || true
  done
  sleep 1
fi

echo "Starting backend on http://$HOST:$PORT"
exec uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
