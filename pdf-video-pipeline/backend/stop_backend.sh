#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-8000}"

EXISTING_PIDS="$(
  ss -ltnp 2>/dev/null | awk -v port=":$PORT" '
    $4 ~ port {
      if (match($0, /pid=[0-9]+/)) {
        print substr($0, RSTART + 4, RLENGTH - 4)
      }
    }
  ' | sort -u || true
)"

if [[ -z "$EXISTING_PIDS" ]]; then
  echo "No backend process is listening on port $PORT."
  exit 0
fi

echo "Stopping backend processes on port $PORT: $EXISTING_PIDS"
for pid in $EXISTING_PIDS; do
  kill "$pid" 2>/dev/null || true
done

sleep 1
echo "Backend stopped."
