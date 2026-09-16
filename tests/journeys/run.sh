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
# workspace-v2 slice A: every process of this run — the seeder, the scratch
# server, the drill children — is a test process on the scratch root, and
# says so before its first import (scripts/testmode.py, scripts/state_root.py).
export WORDICON_TEST_MODE=1
export WORDICON_STATE="$JOURNEY_STATE"
export WORDICON_TEST_EGRESS_LOG="$JOURNEY_DIR/egress_denied.jsonl"
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
for j in quiet home anatomy chooser speak speakkeep encounter federation shell room deep resume inquiry epistemic partial constitution anchorfit carry wayfinder map moira notebook related narrowing gloss; do
  echo "== journey: $j"
  if [ "$j" = quiet ] || [ "$j" = speak ] || [ "$j" = map ]; then before=$(digest); fi
  (cd "$HERE" && node "$j.js") > "$JOURNEY_OUT/$j.log" 2>&1
  rc=$?
  cat "$JOURNEY_OUT/$j.log"
  if [ $rc -ne 0 ]; then echo "== $j: FAILED (exit $rc)"; status=1; fi
  if ! grep -q "^JOURNEY $j OK" "$JOURNEY_OUT/$j.log"; then echo "== $j: did not reach its final line — not a pass"; status=1; fi
  if [ "$j" = quiet ] || [ "$j" = speak ] || [ "$j" = map ]; then
    after=$(digest)
    if [ -z "$before" ] || [ "$before" != "$after" ]; then echo "== $j: the store changed during a journey that must write nothing ($before -> $after)"; status=1; else echo "ok   $j: the store is byte-identical ($before)"; fi
  fi
done
# the writing-room identity checks must have run (a journey that skipped them is not a pass)
# The desktop layout (2026-09-14) adds two: the rail IS the navigation now,
# and it has to survive the fold to a row on a narrow window — where the
# six header destinations used to be counted, a dropped check would hide a
# rail that had quietly stopped rendering.
for need in "split: same room element" "swap: same room element" "full page: same room element" "undo history survived" "home: no request left the scratch origin" "phone 390px: the rail is the navigation" "split 700px: the rail is the navigation"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/home.log" || { echo "== home: missing check: $need"; status=1; }
done
for need in "a quote checked and not found in the text is a FAILED warrant" "the acquisition labels are real text and survive with every stylesheet removed" "a model-written example sentence carries the invented-example label in real text" "no fact this client cannot observe is printed as a number" "a component whose anchor WAS found keeps the machinery out of the reader" "opening the disclosure brings the anchor and the constraint back" "the reopened run still knows whether a component was shown in the text" "the counted panel does not recommend anything" "the live door explains itself only when asked" "a candidate with a broken warrant is told plainly that no door here repairs it" "a card with BOTH a failed warrant and a craft objection names the door that moves the objection"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/epistemic.log" || { echo "== epistemic: missing check: $need"; status=1; }
done
# block 119: a partial workup may not impersonate a whole reading. These are
# named individually because the defect was an ORDERING and a WORDING, both of
# which a dropped check would hide while the journey still printed OK.
for need in "partial banner states the ruling's sentence verbatim" "a complete run renders no partial banner at all" "coverage line no longer claims \"full coverage\"" "coverage line names components PROPOSED and components ANALYSED separately" "the trial verdict is on the page at all (the ordering check has something to order against)" "partiality is rendered BEFORE the trial verdict, not after it" "the trial verdict is scoped to the input, not to the workup" "the partial line is readable with every disclosure closed" "every failed component keeps its own retry door" "the component that DID complete is still on the page" "a partial run's component count says how many were ANALYSED"; do
  grep -qF "ok   $need" "$JOURNEY_OUT/partial.log" || { echo "== partial: missing check: $need"; status=1; }
done
# block 121: the constitution left the controls. Named individually because
# the failures here are a KEYBOARD that stops working and a promise that
# points at nothing — both invisible to source review and both silent.
for need in "all five movements are on the page" "every disclosure has a real <summary>, so every one has a keyboard" "no contents entry points at nothing" "Enter on the focused control opens the explanation" "expand-everything opens every section" "the whole law is readable in one pass when expanded" "no runtime state was moved onto the inert page" "the panel carries no movement heading — one constitution, not two" "the machine-state readouts stayed in the panel where they mean something" "every panel promise reaches the clause that binds it" "the anatomy was not folded into the constitution"; do
  grep -qF "ok   $need" "$JOURNEY_OUT/constitution.log" || { echo "== constitution: missing check: $need"; status=1; }
done
# block 122: five anchor-fit states, drawn as five things. Named individually
# because the failure mode is a state table that is five-valued underneath and
# four-valued on the screen — which is what shipped in the first cut of this
# very block and was caught only by checking the drawn mark.
for need in "all five anchor-fit states say something different" "all five states are DRAWN differently — five marks, not five names over four marks" "contradicted no longer shares a mark with topical" "the row no longer claims grounding, which it never measured" "the deciding difference is readable with every disclosure closed" "the non-gating status is stated once for the run, not on every card" "even a contradicted candidate keeps all three rulings — the row advises, it does not gate"; do
  grep -qF "ok   $need" "$JOURNEY_OUT/anchorfit.log" || { echo "== anchorfit: missing check: $need"; status=1; }
done
# block 123: the bridge. Named individually because each is a way the bridge
# could quietly become something else — a judgment, an insertion, a second
# copy of the draft, a label that exists only in a stylesheet.
for need in "carrying created no judgment and moved no verdict" "each carry is bound to the hash of the text the workup examined, not to a card position" "the carries reopen after a page reload, counted from the record" "the draft text is exactly what the owner typed — nothing inserted" "native undo still reaches the keystroke made before the tray opened" "the invented example is labelled INVENTED on the rendered tray" "the contradicted proposal is labelled CONTRADICTED on the rendered tray" "every standing label is actually displayed, not merely present in the DOM" "the invented label travels INSIDE copied text, not only in a stylesheet" "the tray offers no ruling — carry is not keep" "a draft that differs from the analysed text is said so, plainly" "opening the analysed version shows it read-only and leaves the draft alone" "carrying to a different draft is recorded as the owner's choice" "the original draft was never changed by anything carried" "no revision-notes control exists while nothing has been carried"; do
  grep -qF "ok   $need" "$JOURNEY_OUT/carry.log" || { echo "== carry: missing check: $need"; status=1; }
done
# Map Focus, repair: the three paid Wayfinder actions disclose before they
# spend. Named individually because the failure is a request that leaves
# before the answer — invisible to source review, silent in the log.
for need in "no request left the page before the owner answered" "the panel says exactly one call" "the panel names the lane and model" "cancelling sent nothing" "after confirmation exactly one proposal request left" "no analysis request left before the answer" "exactly one analysis request left after confirmation"; do
  grep -qF "ok   $need" "$JOURNEY_OUT/wayfinder.log" || { echo "== wayfinder: missing check: $need"; status=1; }
done
# Map · focus: named individually because each is a rendering that could
# quietly become a claim — a derived issuer reading as recorded, a missing
# receipt rendered blank, a snapshot claimed where none is, a verdict on the
# node, a dispute collapsed, a title welded, a group open by itself, a total
# hidden, a second ring, a synthesized time, a write from a read.
for need in "the Map opens on a picker: nothing is in focus until chosen" "no focus was requested before a place was chosen" "the node carries no review verdict — a verdict belongs to a road in a run" "the title-keyed twin is disclosed beside the concept-keyed box, never welded" "the grouped list keeps the total visible" "no group is open until opened" "a road citing a receipt that is not there says so by name" "a road whose receipt AND snapshot are gone claims no snapshot — the eighteen render as this" "no provenance cell is blank" "a target judged differently across runs shows both verdicts on the road and chooses neither" "a legacy row derives from its snapshot with rule, basis and version on the road" "a derived issuer never reads as recorded" "a row from before the tracked history with no snapshot says issuer not recorded — nothing is inferred from its relation" "a declared road carries owner standing with its verb and declaration id" "a road the map resolved onto this box discloses the key it was recorded against" "a reconstruction with no recorded time says so — no time is synthesized" "expanding one road opens exactly one further ring" "no other road expanded" "reload restores the open groups and the one expansion from the URL" "reload restores focus, expansion and filter from the URL" "tabbing reaches a road and its accessible name carries relation, issuer and provenance" "no paid or writing map route was touched" "no request but GET left the page" "and what opens is the picker — Focus is the Map's door" "and lands on that run in Home — a door that goes somewhere"; do
  grep -qF "ok   $need" "$JOURNEY_OUT/map.log" || { echo "== map: missing check: $need"; status=1; }
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
for need in "the document was never replaced" "the writing room is the SAME element" "the caret AND the selection survived the walk" "undo walked back through an edit made BEFORE the walk" "a closed place stops running" "Home came back to where it was scrolled" "the anatomy takes the whole window, as ruled" "the rail marks where you are" "and writing beside it lights Write too"; do
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
# defect 4: every origin, not one guessed path. Each of these is a scenario
# that used to end with the owner leaving the room and coming back before the
# page would notice its own answer.
for need in "the run records which surface asked" "and the stored route carries no word of the draft" "a full reload picks the running job back up" "a workup that lands while he is away waits and offers itself" "opening it puts the workup beside the writing" "a run submitted from the page belongs to the page" "it does not hijack the writing room into a split" "a failure names its real class" "a job the server has lost is stated, not left as a frozen line" "every character typed while the answer was arriving is in the draft"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/resume.log" || { echo "== resume: missing check: $need"; status=1; }
done
# the Tab repair, in the room journey where the room is
for need in "Tab indents at the caret and does not leave the writing" "a selection spanning lines indents every line it touches" "Shift and Tab take one level back off" "a three-line indent is one undo step" "one undo takes back the whole indent and nothing else" "Escape arms the exit and says so" "Escape then Tab leaves the writing untouched"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/room.log" || { echo "== room: missing check: $need"; status=1; }
done
# defect 2: the room's line has to have MOVED through honest states
for need in "the room says submitted while the job is queued" "the estimate becomes an exact count the moment the split comes back, and is still called an estimate"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/deep.log" || { echo "== deep: missing check: $need"; status=1; }
done
# block 111 phase 1: the question survives everything the room does to it
# block 111 phase 2: the Reader proposes; it never asserts, and it never
# spends without saying so first
for need in "the page says what a reading costs before it spends it" "a span the Reader invented is dropped and shown as dropped" "taking every reading makes separate sibling branches" "an edit descends from the proposal" "a meta-question is marked as being about the question" "the whole of that spent exactly one model call"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/inquiry.log" || { echo "== inquiry: missing check: $need"; status=1; }
done
for need in "the question is kept exactly as it was asked" "the same words opened twice are two inquiries" "every phase this room has not built renders as an unbuilt door" "an abandoned branch keeps what the failure revealed" "after a full reload it reopens on the question as asked" "exploring created no ruling due" "walking to the Inquiry and back leaves the same room element"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/inquiry.log" || { echo "== inquiry: missing check: $need"; status=1; }
done
# block 125: the readers. The press must have been proved not to spend, the
# room proved untouched, the three answers proved separate, the invented span
# proved marked, the failed reader proved failed-not-agreeing, the carry proved
# to land by CLICK (the button was found dead by this journey), the blind
# reader's discussion proved a consultation, and the earlier reading proved
# reopenable after the draft moved on.
for need in "the readers' control opens a question rather than starting a reading" "and it has spent nothing" "cancelling spent nothing at all" "one press starts exactly one reading" "the room splits when the first reader answers" "the reading leaves the element, the draft and the caret exactly as they were" "three readers answer into three separate cards" "a quoted span that is not in the text is marked, not dropped" "the blind reader's card says what she received" "carrying an observation back lands in the revision notes" "a follow-up goes to one reader only" "the blind reader's discussion is labelled a consultation and her first reading stands" "a reader that failed is shown failed, says it is not agreement, and can be retried alone" "an earlier reading reopens whole" "a whole-draft reading reopened after an edit says the draft has moved on" "the undo stack survived the whole invocation"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/moira.log" || { echo "== moira: missing check: $need"; status=1; }
done
# notebook stage A: the room keeps what you write. Each named check is a
# defect measured before the repair; a journey that did not reach them is
# not a pass.
for need in "what was typed in the room is in the browser" "reopening the room brings back the selection he left" "the undo stack survived the close and reopen" "after a reload the words typed in the room are back on the page" "and the room reopens on the same words at the place he was" "one Escape inside the writing leaves the room open" "a second Escape within the window closes it" "from the bar one Escape closes the room" "with the type panel open, Escape closes the panel and leaves the room" "a paste that carries words beside a file, into the writing, is left to the browser as words" "a text drag inside the writing is the browser" "while a selection exists the real text shows itself and the picture steps aside" "what was typed is saved on this installation without any run" "and Saved is said only when the newest words are in the store" "with the server unreachable the room says the words are on this device" "a save whose reply was lost is retried with the same request id and lands once" "Keep mine as a new copy makes my text a durable document" "the old session draft became one document, once"; do
  grep -q "^ok   $need" "$JOURNEY_OUT/notebook.log" || { echo "== notebook: missing check: $need"; status=1; }
done
# stage C: colours and Download. Named because each is a way the surface could
# quietly change what it never may: the default pair, the draft under a
# recolour, the undo chain, the body of a download.
# The result cards on a wide desk (2026-09-14): named individually because a
# grid that quietly went back to one column, or quietly reordered, would
# still pass every functional check.
for need in "at 1440 wide each section lays its cards in two columns" "no card runs the whole pane" "reading order is the DOM order" "status notices and asides span the row"; do
  grep -qF "ok   $need" "$JOURNEY_OUT/related.log" || { echo "== related: missing check: $need"; status=1; }
done
# The narrowing history (2026-09-14): named individually because the defect
# was a FLAG dropped in a projection — the text survived, the history did
# not — and a dropped check would hide exactly that. The engine is named
# because the first version of this journey said WebKit and ran Chromium.
for need in "the narrowing is measured in WebKit" "the outgoing request carries meaning_narrowed: true" "and the queued job records meaning_narrowed: true, as received" "the outgoing request carries meaning_narrowed: false" "reopening projects the recorded value, true, into what a follow-up will send"; do
  grep -qF "ok   $need" "$JOURNEY_OUT/narrowing.log" || { echo "== narrowing: missing check: $need"; status=1; }
done
# The plain gloss (2026-09-14): named individually because each is a way the
# gloss could quietly go wrong again — sent unshown, sent cut, dropped without
# a press, or lost with the panel when a server error replaced it. The
# engine is named for the same reason as narrowing's.
for need in "the gloss panel is measured in WebKit" "the gloss has its own box and holds the whole value" "nothing is sent while the gloss is over the limit" "the request carries the shortened text once, as the meaning, and no hidden original gloss" "the request carries the meaning untouched and the gloss as shortened" "and records the gloss as narrowed for this comparison only" "the request carries the meaning and no gloss" "and records the omission as a choice" "the error is written beside the panel, and the panel is still there" "every typed field survived the error, line breaks included" "and so did the selection and the caret" "the retry sends the corrections exactly, without retyping"; do
  grep -qF "ok   $need" "$JOURNEY_OUT/gloss.log" || { echo "== gloss: missing check: $need"; status=1; }
done
for need in "the room opens blue & yellow — background #0f2350, caret #ffd97d" "Aa holds Colours: the four presets, Background, Text and Reset to blue & yellow" "Paper recolours the room through custom properties" "and the draft, the selection and the scroll are exactly as they were" "a pair under 4.5:1 gets a hint that says the number and offers the reset" "Reset to blue & yellow hands the colours back to the stylesheet — no inline copy of the default" "undo after the colour changes still takes back the word typed before them" "the chosen colours are back after a reload" "the download panel says Download, with Text and Markdown, PDF, and everything" "the Text download is the body exactly — leading spaces, a tab, a blank paragraph, the trailing newline"; do
  grep -qF "ok   $need" "$JOURNEY_OUT/notebook.log" || { echo "== notebook: missing check: $need"; status=1; }
done
# Find related words (2026-09-13). Named individually because each is a way
# the panel could quietly become something else: a door that spends, an
# English section that is not English, a gap read as absence, an old record
# read as empty, a follow-up that replaces, a bar that grew.
for need in "Find related words is the first door in Explore this idea" "opening the door spent nothing" "the saved comparisons for this idea are shown before anything is spent" "a comparison matched by concept id and one matched only by title are labelled apart" "one press started exactly one run, with no second form" "the meaning that went is the one he edited, not the card's" "the meaning box keeps line breaks and non-BMP characters exactly" "a meaning over the limit stops the pass before it starts" "and it says both counts and that the idea it came from is not changed" "and pressing it anyway sends nothing" "shortening it lets the pass start again" "a close synonym and a related one are told apart" "an exact antonym and a contrast are told apart, and each says what it opposes" "a non-Latin word offered as an English synonym is set aside, visibly, with its reason" "Latin has its own section, with the term and its period" "Ancient Greek has its own required section: the period name, the Greek letters, the romanization, the period" "Modern Greek is shown apart under its own name, with its period" "and the Modern entry is not folded into the Ancient section" "a loanword English carries is kept and marked as one" "a Latin-lettered foreign word offered as English is set aside with the reviewer's reason, marked as recall" "a language that came back empty reads as no close match in this pass, not as absence" "the follow-up rendered under the language it was asked for" "and the results above it were not replaced" "its English sections say they were never part of the tool then — not that nothing was found" "Latin, Ancient Greek, and Koine and Modern Greek say they were not asked for, by name" "the bar is still four buttons and none of them is Find related words" "and spends nothing" "a selected word is the meaning line as it stands" "the run needs no title and no accepted concept" "a selected passage is enough: the meaning line is empty and optional, and Use selected passage is live and focused" "no meaning was demanded — nothing had to be explained again" "the selection went as the passage exactly, the line break before it and all" "a narrowing goes as the meaning and the selection still goes exactly" "a pass made from a selection alone still offers Ask another language, about that passage" "and asking it sends that record's own passage, exactly, with the language named" "the follow-up is added beneath and the earlier results survive" "the draft is untouched by the run" "and never calls it a workup" "every result carries Explore this word, Compare with my idea, Save and Check sources" "and it says the review cannot search, and where the lookup lives instead" "Check sources sends nothing until it is pressed" "it says what it costs before it spends" "and it says exactly what leaves" "and it does not claim the query itself is controlled" "pressing it made exactly one lookup" "and the request carries only the word, its language and its period" "built from what the card shows" "a returned result is drawn as a result to inspect, and the source stays the model" "zero searches is drawn as no acquisition, in warning colour" "the zero is stated, not omitted" "a fictional reference with nothing acquired never wears" "the acquisition line is above the model" "a reply with no acquisition record is drawn as unverified, never as success" "and it says plainly that it cannot speak to fit" "the card’s own verdict is untouched by the lookup" "Compare sets your meaning beside the word's own meaning, fit and differences, with the review" "a field the pass did not produce is named as not analysed, and an English item says what the reviewer judged and that its fit is recall" "and a loanword says so in Compare, with where it came from" "Explore this word opens the word-comparison panel with the word, its sense and the cost, and waits for Find" "Compare and Explore sent no run" "a save pressed twice sends one request and no run" "and a save sent again for the same result hands back the bookmark it already has" "opening a saved word lands on the card it bookmarked, not merely on its run" "and a bookmark whose position the record no longer holds is told plainly, not guessed by spelling" "saving it again after a removal is meant, and makes a new bookmark" "the saved word carries its run, language, intended meaning and review" "the Library has a Saved words shelf with the word, its language and its verdict" "remove takes it off the shelf"; do
  grep -qF "ok   $need" "$JOURNEY_OUT/related.log" || { echo "== related: missing check: $need"; status=1; }
done
# workspace-v2 slice B: the workspace journey needs a run to COMPLETE through
# the one job path, so it drives a SECOND scratch server on its own port and
# its own scratch root with the mock lane instead of the poison (test mode
# still refuses every provider and every outbound socket). It is seeded the
# same way and torn down when the journey ends.
export JOURNEY_DIR_WORK="$JOURNEY_DIR/work"
export JOURNEY_PORT_WORK="${JOURNEY_PORT_WORK:-8498}"
mkdir -p "$JOURNEY_DIR_WORK/out"
if curl -s -o /dev/null "http://127.0.0.1:$JOURNEY_PORT_WORK/pair"; then
  echo "FAIL something already answers on port $JOURNEY_PORT_WORK — refusing to run the workspace journey against it"; status=1
else
  (cd "$ROOT" && env JOURNEY_DIR="$JOURNEY_DIR_WORK" JOURNEY_STATE="$JOURNEY_DIR_WORK/state" WORDICON_STATE="$JOURNEY_DIR_WORK/state" "$PY" tests/journeys/fixtures.py) || { echo "FAIL fixtures did not seed for the workspace server"; status=1; }
  (cd "$ROOT" && exec env HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9 NO_PROXY=127.0.0.1,localhost \
    JOURNEY_DIR="$JOURNEY_DIR_WORK" JOURNEY_STATE="$JOURNEY_DIR_WORK/state" WORDICON_STATE="$JOURNEY_DIR_WORK/state" JOURNEY_PORT="$JOURNEY_PORT_WORK" \
    WORDICON_TEST_EGRESS_LOG="$JOURNEY_DIR_WORK/egress_denied.jsonl" JOURNEY_MOCK_LANE=1 \
    "$PY" tests/journeys/serve.py > "$JOURNEY_DIR_WORK/out/server.log" 2>&1) &
  WORK_PID=$!
  for i in $(seq 1 60); do
    if curl -s -o /dev/null "http://127.0.0.1:$JOURNEY_PORT_WORK/pair"; then break; fi
    sleep 0.5
    if ! kill -0 $WORK_PID 2>/dev/null; then echo "FAIL the workspace scratch server died:"; cat "$JOURNEY_DIR_WORK/out/server.log"; status=1; break; fi
  done
  for j in work; do
    echo "== journey: $j"
    (cd "$HERE" && env JOURNEY_DIR="$JOURNEY_DIR_WORK" JOURNEY_STATE="$JOURNEY_DIR_WORK/state" JOURNEY_OUT="$JOURNEY_OUT" JOURNEY_PORT="$JOURNEY_PORT_WORK" node "$j.js") > "$JOURNEY_OUT/$j.log" 2>&1
    rc=$?
    cat "$JOURNEY_OUT/$j.log"
    if [ $rc -ne 0 ]; then echo "== $j: FAILED (exit $rc)"; status=1; fi
    if ! grep -q "^JOURNEY $j OK" "$JOURNEY_OUT/$j.log"; then echo "== $j: did not reach its final line — not a pass"; status=1; fi
  done
  # workspace-v2 slice C: the editor journey runs in BOTH engines (standard
  # writing must work in Chromium and WebKit), against the same server
  for eng in chromium webkit; do
    j="editor-$eng"
    echo "== journey: $j"
    (cd "$HERE" && env JOURNEY_DIR="$JOURNEY_DIR_WORK" JOURNEY_STATE="$JOURNEY_DIR_WORK/state" JOURNEY_OUT="$JOURNEY_OUT" JOURNEY_PORT="$JOURNEY_PORT_WORK" JOURNEY_ENGINE="$eng" node editor.js) > "$JOURNEY_OUT/$j.log" 2>&1
    rc=$?
    cat "$JOURNEY_OUT/$j.log"
    if [ $rc -ne 0 ]; then echo "== $j: FAILED (exit $rc)"; status=1; fi
    if ! grep -q "^JOURNEY $j OK" "$JOURNEY_OUT/$j.log"; then echo "== $j: did not reach its final line — not a pass"; status=1; fi
  done
  kill $WORK_PID 2>/dev/null; wait $WORK_PID 2>/dev/null
fi
# workspace-v2 slice B: named individually because each is a promise of the
# shell that a green journey could quietly stop making — the engine, the
# colours, typing that starts nothing, a proposal that spends nothing, the
# editor element that survives every toggle, Focus that restores, the drawer
# and the section below the draft at 125%, Ask that proposes and never runs.
for need in "the workspace is measured in WebKit" "the writing surface is #0f2350" "the writing is #ffd97d" "typing posted nothing to /api/jobs or /api/operations" "typing did save (a PUT to the notebook)" "and the structure beside it (two paragraphs), under the versioned fingerprint" "the menu opens below the selected words, not over the top of the draft" "the mock lane says no provider request, no charge" "preparing posted a prepare and no Start" "Escape closes the proposal" "the result names its origin" "and says the draft has not changed since" "the operation links to its immutable snapshot" "after typing, the card says the draft changed and to review the earlier version" "the editor element survived four toggles" "the selection survived the toggles" "undo still works after the toggles" "Focus hides Tools, Results and the activity strip" "Exit focus restores exactly the arrangement before" "Tools is a drawer over the left" "Escape closes the drawer" "Results is a section below the draft" "Back to writing puts the caret back in the draft" "all three readers answered" "with nothing selected, Find related words asks for a selection instead of inventing one" "Ask \"map\" opens the Map as a place inside the shell" "the editor element survived the Map round trip" "no fixture constant on the page" "a reload reopens the same document" "after the reload the run made here is listed from the record, Done" "restoring the page started nothing" "an operation a dead process left after its first dispatch intent is unknown, by the record" "one never dispatched and without a proposal is not resumed, and says why" "the card says a dispatch was recorded and its outcome was not" "Check status reads the record and sends nothing" "and the operation stays unknown — it is never replayed" "Start another attempt is refused for an operation with no proposal to rebuild, and nothing was sent" "the store names its dispatcher and its population" "Your work lists the draft, from the index" "and the runs, with the index’s own population line" "a word from the draft finds the draft" "and the run that was made from it" "searching sent the words to nothing but the local index (a GET)" "a malformed query is answered, not crashed" "Archive takes the draft out of the ordinary listing" "and the archive filter shows it, kept whole" "the archived document is still in the notebook, untouched" "opening Investigate contacted no producer and started nothing" "the EthicalAlt card says the deployment is not verified, that starting works here only against the fixture producer, and which contract is pinned" "the proposal names what leaves and to whom" "and nothing was started by proposing" "the investigation card names the producer, the upstream id and the start’s outcome" "the signed export is in custody and its signature verified under the pinned key" "and the card says what a signature does and does not mean" "the record holds the intent before and the outcome after the POST, then the export’s read" "the name itself is not in the events" "Ask shows the rest of the request as the subject it would propose" "and Enter proposes the investigation with that subject, starting nothing" "and its four tabs (Results, Feedback, Notes, Sources) came down with it" "a tab in the section still switches" "the header wraps its formatting bar onto its own row rather than overlapping" "at 1280×800 both sides stay open as sides, narrowed" "a Tab walk reaches every control of the header, Tools, the editor and Results, including both grips" "the Tools grip resizes on the arrow keys" "Tab outside a list leaves the editor (the keyboard is never trapped in the draft) and types nothing" "work: no request left the scratch origin"; do
  grep -qF "ok   $need" "$JOURNEY_OUT/work.log" || { echo "== work: missing check: $need"; status=1; }
done
# workspace-v2 slice C: each editor promise, in each engine, by name
for eng in chromium webkit; do
  for need in "the editor is measured in $eng" "the page reproduces all 18 golden vectors (projection, canonical JSON, fingerprint v2, position map) in $eng" "bold changed no character of the text" "the bold-only save moved the revision" "after a reload the bold is still there, on the same document" "a body-only save against the structured head is refused by name (422 structure_would_be_lost), with an explicit null too" "a document the server never received is reopened from this browser’s recovery, bold and all" "an unsent formatting-only edit (no character changed) is recovered from the envelope" "Shift-Enter is a hard break (one LF), Enter a paragraph (two LF)" "the list continues, nests on Tab, lifts on Shift-Tab and exits on an empty item" "the projection joins every leaf paragraph with two LF and adds no markers" "the header counts the words of this draft" "clicking Italic on the bar italicised exactly the selected word and left the selection where it was" "an unsafe link scheme is refused by the editor" "and the server refuses one too (400 unsafe_link)" "a structure that does not project to the text sent with it is refused (422 projection_mismatch)" "find counts the matches in this draft" "and one undo takes the whole replace-all back" "typing with the bar open recounts" "the proposal says the words go as text only" "the result is fresh: the writer’s own autosave acknowledgment did not make the capture stale" "Replace put the candidate where the FIRST cat stood and nowhere else" "the application was one undo step" "the record holds the application and its undo, linked to the operation" "and the application was marked committed by the save that carried it" "after the draft changed, the old target is refused even though \"cat\" still stands at the old offsets" "with nothing selected, choosing the target again applies nothing" "an explicitly reconfirmed target takes the candidate, and only there" "a CRLF document opens plain, read-only, exact, with the formatting bar off" "a checkpoint of the read-only document rewrites nothing" "the disclosed conversion made revision 2 with LF line endings, structured" "the plain head was kept as a migration checkpoint and the conversion is an event" "a document with a control character stays plain and editable, and the character is kept" "restoring revision 1 made revision" "the head before the restore was kept as a version, and revision 1 is still there" "a plain copy is a NEW plain document; the original keeps its id and its structure" "a save waits for the composition" "and so does a capture: no proposal while composing" "the text export says it is plain and what a .txt file does not carry" "Markdown keeps heading, list, bold, quote and link" "pasted text keeps a single line break as a hard break and a blank line as a paragraph" "a 20400-word draft: an edit with its handlers" "the editor’s own last check refuses a target whose words are not the words the suggestion was made for" "more words were typed while the save was in flight" "every word typed before the switch is on the server" "reopening it recovers nothing and rewrites nothing: the envelope held exactly the head" "the switch waited its bound for the held save and then went on rather than holding the room" "the late reply repaired its envelope" "reopening it recovers the words typed after the send, from the envelope, and saves them" "the second tab has its own tab id, so the two envelopes never overwrite each other" "the first tab’s save is refused and the room says so, with the choice beside the draft" "nothing was overwritten: the head is the second tab’s and the first tab still holds its own words" "Keep mine as a new document: both copies are on the server under their own ids" "the candidate was applied while the older save was still in flight, and the application is not yet committed" "the save that carried the application committed it, at the revision it made" "the undo is recorded and committed as the next revision, and the head holds the words before the application" "with storage refusing, the server save lands and the header says this browser keeps no recovery copy" "with the server gone as well, the room says the words are not on the server and this browser kept no copy" "editor-$eng: no request left the scratch origin"; do
    grep -qF "ok   $need" "$JOURNEY_OUT/editor-$eng.log" || { echo "== editor-$eng: missing check: $need"; status=1; }
  done
done
total=$(grep -h "^CHECKS " "$JOURNEY_OUT"/work.log "$JOURNEY_OUT"/editor-chromium.log "$JOURNEY_OUT"/editor-webkit.log "$JOURNEY_OUT"/quiet.log "$JOURNEY_OUT"/home.log "$JOURNEY_OUT"/anatomy.log "$JOURNEY_OUT"/chooser.log "$JOURNEY_OUT"/speak.log "$JOURNEY_OUT"/speakkeep.log "$JOURNEY_OUT"/encounter.log "$JOURNEY_OUT"/federation.log "$JOURNEY_OUT"/shell.log "$JOURNEY_OUT"/room.log "$JOURNEY_OUT"/deep.log "$JOURNEY_OUT"/resume.log "$JOURNEY_OUT"/inquiry.log "$JOURNEY_OUT"/epistemic.log "$JOURNEY_OUT"/partial.log "$JOURNEY_OUT"/constitution.log "$JOURNEY_OUT"/anchorfit.log "$JOURNEY_OUT"/carry.log "$JOURNEY_OUT"/wayfinder.log "$JOURNEY_OUT"/map.log "$JOURNEY_OUT"/moira.log "$JOURNEY_OUT"/notebook.log "$JOURNEY_OUT"/related.log "$JOURNEY_OUT"/narrowing.log "$JOURNEY_OUT"/gloss.log | awk '{s+=$2} END {print s+0}')
echo "== journeys: $total checks, exit $status"
exit $status
