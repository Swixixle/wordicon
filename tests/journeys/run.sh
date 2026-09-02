#!/usr/bin/env bash
# The browser journeys, end to end: a scratch store, seeded; the scratch
# server with the gateway poisoned, no key, and outbound HTTP pointed at a
# dead proxy; then every journey in a real (headless) Chromium. Fails if a
# journey fails, if a journey did not run to its final line, if Playwright
# or the browser is missing, or if the writing-room identity checks did
# not appear. Screenshots of failing checks and the server log land in
# JOURNEY_OUT for CI to hand back. Never touches local_state.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PY="${PYTHON:-python3}"
export JOURNEY_DIR="${JOURNEY_DIR:-$(mktemp -d -t nikodemus-journeys-XXXXXX)}"
export JOURNEY_STATE="$JOURNEY_DIR/state"
export JOURNEY_OUT="${JOURNEY_OUT:-$JOURNEY_DIR/out}"
export JOURNEY_PORT="${JOURNEY_PORT:-8499}"
mkdir -p "$JOURNEY_OUT"
unset ANTHROPIC_API_KEY
echo "journeys: dir=$JOURNEY_DIR port=$JOURNEY_PORT out=$JOURNEY_OUT"

# the browser must be there — a missing browser is a failure, not a skip
if ! (cd "$HERE" && node -e "require('playwright')" 2>/dev/null); then
  echo "FAIL playwright is not installed under tests/journeys (npm ci there first)"; exit 2
fi
if ! (cd "$HERE" && node -e "const {chromium}=require('playwright'); chromium.launch(process.env.JOURNEY_CHROME?{executablePath:process.env.JOURNEY_CHROME}:{}).then(b=>b.close())" 2>"$JOURNEY_OUT/browser-probe.err"); then
  echo "FAIL the browser could not launch:"; cat "$JOURNEY_OUT/browser-probe.err"; exit 2
fi

# the port must be free — a stale server would answer for a build that is not this one
if curl -s -o /dev/null "http://127.0.0.1:$JOURNEY_PORT/pair"; then
  echo "FAIL something already answers on port $JOURNEY_PORT — refusing to run against it"; exit 2
fi
# seed, then serve with the network gone for the server process
(cd "$ROOT" && "$PY" tests/journeys/fixtures.py) || { echo "FAIL fixtures did not seed"; exit 2; }
(cd "$ROOT" && exec env HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9 NO_PROXY=127.0.0.1,localhost \
  "$PY" tests/journeys/serve.py > "$JOURNEY_OUT/server.log" 2>&1) &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null' EXIT
for i in $(seq 1 60); do
  if curl -s -o /dev/null "http://127.0.0.1:$JOURNEY_PORT/pair"; then break; fi
  sleep 0.5
  if ! kill -0 $SERVER_PID 2>/dev/null; then echo "FAIL the scratch server died:"; cat "$JOURNEY_OUT/server.log"; exit 2; fi
done
[ -f "$JOURNEY_DIR/token" ] || { echo "FAIL no session was minted"; cat "$JOURNEY_OUT/server.log"; exit 2; }

status=0
for j in home anatomy; do
  echo "== journey: $j"
  (cd "$HERE" && node "$j.js") > "$JOURNEY_OUT/$j.log" 2>&1
  rc=$?
  cat "$JOURNEY_OUT/$j.log"
  if [ $rc -ne 0 ]; then echo "== $j: FAILED (exit $rc)"; status=1; fi
  if ! grep -q "^JOURNEY $j OK" "$JOURNEY_OUT/$j.log"; then echo "== $j: did not reach its final line — not a pass"; status=1; fi
done
# the writing-room identity checks must have run (a journey that skipped them is not a pass)
for need in "split: same room element" "swap: same room element" "full page: same room element" "undo history survived" "home: no request left the scratch origin"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/home.log" || { echo "== home: missing check: $need"; status=1; }
done
grep -q "^ok   anatomy: no request left the scratch origin" "$JOURNEY_OUT/anatomy.log" || { echo "== anatomy: the off-origin guard did not run"; status=1; }
grep -q "^ok   dormant after" "$JOURNEY_OUT/anatomy.log" || { echo "== anatomy: the stillness check did not run"; status=1; }
total=$(grep -h "^CHECKS " "$JOURNEY_OUT"/home.log "$JOURNEY_OUT"/anatomy.log | awk '{s+=$2} END {print s+0}')
echo "== journeys: $total checks, exit $status"
exit $status
