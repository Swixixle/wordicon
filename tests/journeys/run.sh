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
# The room journey runs in WebKit — Safari's own engine — because the caret bug
# that pass 1 repaired was invisible to source review and the owner writes in
# Safari. A missing WebKit is a failure, not a skip.
if ! (cd "$HERE" && node -e "const {webkit}=require('playwright'); webkit.launch().then(b=>b.close())" 2>"$JOURNEY_OUT/webkit-probe.err"); then
  echo "FAIL WebKit could not launch (npx playwright install webkit):"; cat "$JOURNEY_OUT/webkit-probe.err"; exit 2
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
# block 104: the store's bytes before and after the quiet journey — browsing
# with encounter recording off must leave the store byte-identical
digest() { (cd "$ROOT" && "$PY" -c "import sys,pathlib; sys.path.insert(0,'scripts'); sys.path.insert(0,'src'); from record_smoke import store_digest; print(store_digest(pathlib.Path(sys.argv[1])))" "$JOURNEY_STATE"); }
for j in quiet home anatomy chooser speak speakkeep encounter federation shell room deep; do
  echo "== journey: $j"
  if [ "$j" = quiet ] || [ "$j" = speak ]; then before=$(digest); fi
  (cd "$HERE" && node "$j.js") > "$JOURNEY_OUT/$j.log" 2>&1
  rc=$?
  cat "$JOURNEY_OUT/$j.log"
  if [ $rc -ne 0 ]; then echo "== $j: FAILED (exit $rc)"; status=1; fi
  if ! grep -q "^JOURNEY $j OK" "$JOURNEY_OUT/$j.log"; then echo "== $j: did not reach its final line — not a pass"; status=1; fi
  if [ "$j" = quiet ] || [ "$j" = speak ]; then
    after=$(digest)
    if [ -z "$before" ] || [ "$before" != "$after" ]; then echo "== $j: the store changed during a journey that must write nothing ($before -> $after)"; status=1; else echo "ok   $j: the store is byte-identical ($before)"; fi
  fi
done
# the writing-room identity checks must have run (a journey that skipped them is not a pass)
for need in "split: same room element" "swap: same room element" "full page: same room element" "undo history survived" "home: no request left the scratch origin"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/home.log" || { echo "== home: missing check: $need"; status=1; }
done
grep -q "^ok   anatomy: no request left the scratch origin" "$JOURNEY_OUT/anatomy.log" || { echo "== anatomy: the off-origin guard did not run"; status=1; }
grep -q "^ok   dormant after" "$JOURNEY_OUT/anatomy.log" || { echo "== anatomy: the stillness check did not run"; status=1; }
# block 104: the switch and the unresolved case must have been exercised
for need in "browsing with recording off posted nothing" "About says recording is off by default" "an identity-shaped input is read and shown with the studies unbuilt"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/quiet.log" || { echo "== quiet: missing check: $need"; status=1; }
done
for need in "nothing was posted to /api/jobs by typing" "Research is highlighted and unbuilt" "the question is kept verbatim with its arrival" "choosing Develop reveals Run it" "a lone word highlights Develop without choosing it"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/chooser.log" || { echo "== chooser: missing check: $need"; status=1; }
done
for need in "the press opens the microphone and Listening is visible" "stopping closes the microphone and reaches Review" "Discard clears the box, the review and the audio" "after a reload the instrument is Ready and nothing is recording" "what the engine heard stays visible, unchanged by the correction" "the speech block cites the hint manifest it was told"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/speak.log" || { echo "== speak: missing check: $need"; status=1; }
done
for need in "Keep recording stores it and says so" "the open question arrived spoken, edited" "the question cites a manifest that reads back" "the kept transcript cites the same manifest"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/speakkeep.log" || { echo "== speakkeep: missing check: $need"; status=1; }
done
for need in "the switch is on and the flip is the first row" "opening the bridged entry recorded one owner_opened row" "turning off is a confirmed action and the second recorded flip" "Home paints the quiet Unresolved line" "the reopened ruling is recorded, on the shelf, citing the unresolved ruling"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/encounter.log" || { echo "== encounter: missing check: $need"; status=1; }
done
# block 107: the instruments — nothing on load, named failures, seats apart, the owner alone declares, the chooser carries without fetching
for need in "opening the page posted nothing" "Check reaches Open Case through the credential and imports nothing" "importing by id verifies the EthicalAlt package under the pinned key" "a foreign address is refused and nothing is fetched" "the exact-bytes door returns the bytes received" "a package with one changed byte is kept UNVERIFIED" "server-boom lands as http_5xx, not as nothing found" "gateway-502 lands as html_error_page, not as nothing found" "each instrument keeps its own standing" "the seats are filled apart by instrument and kind" "each seat item carries its instrument's own label" "the documented absence, the failed search and the producer's own gaps stay distinct" "three exact name matches are proposed" "Reject and Leave unresolved converge nothing" "Declare produces the two instruments' dated records" "the form is pre-filled and nothing was fetched" "About & proof states the registry, custody and rulings" "federation: no request left the scratch origin"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/federation.log" || { echo "== federation: missing check: $need"; status=1; }
done
# slice 2: the shell must have proved the three things a source pin cannot —
# same window, same element, and an undo stack that walked back through an
# edit made before the walk. A journey that quietly stops making these is not
# a pass, however green it looks.
for need in "the document was never replaced" "the writing room is the SAME element" "the caret AND the selection survived the walk" "undo walked back through an edit made BEFORE the walk" "a closed place stops running" "Home came back to where it was scrolled" "the anatomy takes the whole window, as ruled"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/shell.log" || { echo "== shell: missing check: $need"; status=1; }
done
# pass 1: the caret must have been measured against the letters actually drawn,
# in WebKit, or this journey proved nothing about the thing it exists for.
for need in "the room is measured in WebKit" "the caret lands on the letter that is drawn" "the textarea and the picture behind it are the same box" "no letter is an atomic box — every one of them wraps" "no wrap point moves while the letters are still animating" "the caret lands on the letter while the letters are still animating" "the picture and its animated copies are hidden from the reader" "the pointer over a drawn letter reaches the writing" "selecting the whole page does not pick up" "selecting in the room returns the draft exactly once" "with motion reduced the real letter is visible at once" "changing the view records nothing" "a view name this build does not know falls back" "the caret is still on the letter after every mode change and a walk"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/room.log" || { echo "== room: missing check: $need"; status=1; }
done
# pass 2: the invocation must have been proved not to spend, the run proved
# not to disturb the room, and the expansion proved not to fire.
for need in "the chord opens the question rather than starting the run" "and it has spent nothing" "cancelling spent nothing at all" "one press starts exactly one run" "the run leaves the element, the draft and the caret exactly as they were" "and it does not take the focus" "the room has NOT split while the run is still going" "the room splits when the answer arrives" "the paragraph is exactly the text between the blank lines" "with a selection the paragraph command offers the selection" "the expansion is counted from the components that actually came back" "clicking it runs nothing" "it renders as this page's unbuilt door" "the undo stack survived the whole invocation"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/deep.log" || { echo "== deep: missing check: $need"; status=1; }
done
total=$(grep -h "^CHECKS " "$JOURNEY_OUT"/quiet.log "$JOURNEY_OUT"/home.log "$JOURNEY_OUT"/anatomy.log "$JOURNEY_OUT"/chooser.log "$JOURNEY_OUT"/speak.log "$JOURNEY_OUT"/speakkeep.log "$JOURNEY_OUT"/encounter.log "$JOURNEY_OUT"/federation.log "$JOURNEY_OUT"/shell.log "$JOURNEY_OUT"/room.log "$JOURNEY_OUT"/deep.log | awk '{s+=$2} END {print s+0}')
echo "== journeys: $total checks, exit $status"
exit $status
