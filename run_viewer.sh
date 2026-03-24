#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${ROOT_DIR:-$SCRIPT_DIR}"
VIEWER_DIR="$ROOT_DIR/viewer"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
VIEWER_HOST="${VIEWER_HOST:-127.0.0.1}"
VIEWER_PORT="${VIEWER_PORT:-5173}"

API_URL="http://${API_HOST}:${API_PORT}"
VIEWER_URL="http://${VIEWER_HOST}:${VIEWER_PORT}"

API_PID=""
VIEWER_PID=""

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

port_in_use() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local attempts="${3:-40}"

  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$label ready at $url"
      return 0
    fi
    sleep 0.5
  done

  echo "$label did not become ready: $url" >&2
  return 1
}

cleanup() {
  local exit_code=$?

  if [[ -n "${VIEWER_PID}" ]] && kill -0 "${VIEWER_PID}" >/dev/null 2>&1; then
    kill "${VIEWER_PID}" >/dev/null 2>&1 || true
  fi

  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" >/dev/null 2>&1; then
    kill "${API_PID}" >/dev/null 2>&1 || true
  fi

  wait >/dev/null 2>&1 || true
  exit "$exit_code"
}

trap cleanup EXIT INT TERM

require_cmd python3
require_cmd npm
require_cmd curl
require_cmd lsof

if port_in_use "$API_PORT"; then
  echo "API port $API_PORT is already in use. Stop the existing process or set API_PORT." >&2
  exit 1
fi

if port_in_use "$VIEWER_PORT"; then
  echo "Viewer port $VIEWER_PORT is already in use. Stop the existing process or set VIEWER_PORT." >&2
  exit 1
fi

cd "$ROOT_DIR"
python3 -m uvicorn manufacturing_pipeline.api.app:app --host "$API_HOST" --port "$API_PORT" &
API_PID=$!

wait_for_http "$API_URL/api/v1/health" "API"

cd "$VIEWER_DIR"
npm run dev -- --host "$VIEWER_HOST" --port "$VIEWER_PORT" &
VIEWER_PID=$!

wait_for_http "$VIEWER_URL" "Viewer"

cat <<EOF

ALES STEP Viewer is running.
Viewer: $VIEWER_URL
API:    $API_URL

Press Ctrl+C to stop both processes.
EOF

wait "$API_PID" "$VIEWER_PID"
