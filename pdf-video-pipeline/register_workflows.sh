#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export CONDUCTOR_SERVER_URL="${CONDUCTOR_SERVER_URL:-http://localhost:8080/api}"

WORKFLOWS=(
  "conductor/workflows/document_understanding.json"
  "conductor/workflows/hitl_style_review.json"
  "conductor/workflows/video_rendering.json"
  "conductor/workflows/pdf_to_video_pipeline.json"
)

echo "Registering workflows against: $CONDUCTOR_SERVER_URL"

for workflow in "${WORKFLOWS[@]}"; do
  echo "-> $workflow"
  temp_payload="$(mktemp)"
  printf '[' >"$temp_payload"
  cat "$workflow" >>"$temp_payload"
  printf ']' >>"$temp_payload"

  curl --silent --show-error --fail \
    -X PUT "${CONDUCTOR_SERVER_URL}/metadata/workflow?overwrite=true" \
    -H "Content-Type: application/json" \
    --data-binary "@${temp_payload}" >/dev/null

  rm -f "$temp_payload"
done

echo "Workflow registration complete."
