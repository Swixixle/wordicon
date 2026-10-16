#!/usr/bin/env bash
# Isolated, offline Go deeper journey. PYTHON must have requirements.txt.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
export JOURNEY_DIR="${JOURNEY_DIR:-$(mktemp -d -t nikodemus-deeper-XXXXXX)}"
export JOURNEY_STATE="$JOURNEY_DIR/state"
export JOURNEY_OUT="$JOURNEY_DIR/out"
export JOURNEY_PORT="${JOURNEY_PORT:-8501}"
export WORDICON_TEST_MODE=1 WORDICON_STATE="$JOURNEY_STATE" JOURNEY_MOCK_LANE=1
export WORDICON_TEST_EGRESS_LOG="$JOURNEY_DIR/egress_denied.jsonl"
mkdir -p "$JOURNEY_OUT"
if curl --noproxy '*' -sf "http://127.0.0.1:$JOURNEY_PORT/pair" >/dev/null; then
  echo "Port $JOURNEY_PORT is in use; refusing to test another server."; exit 2
fi
cd "$ROOT"
"${PYTHON:-python3}" tests/journeys/serve.py >"$JOURNEY_OUT/server.log" 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true' EXIT
for i in $(seq 1 60); do
  if curl --noproxy '*' -sf "http://127.0.0.1:$JOURNEY_PORT/pair" >/dev/null; then break; fi
  if ! kill -0 "$pid" 2>/dev/null; then cat "$JOURNEY_OUT/server.log"; exit 2; fi
  sleep 0.2
done
cd "$HERE"
node deeper.js
