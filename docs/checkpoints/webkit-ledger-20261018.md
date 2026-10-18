# P1: WebKit Ledger and editing boundaries

This repair starts from Nikodemus `76ec0cfeecbe1bd652d55223e795c8e7b7bc21ee`
(`codex/webkit-ledger-20261018`). The shared canonical CURRENT-STATE was read
from the integration checkout and matched that code checkpoint. All reproduction
used a disposable fixture store and a loopback server on port8487. No live
records, provider calls, credentials, server authentication or CORS rules changed.

## Observed failures and repair

The earlier handoff's printed `/127.0.0.1:8498/api/ledger` was reproduced on
port8487. It is WebKit's error formatting, not the requested URL. Instrumented
fetch input was `/api/ledger`, resolving to `http://127.0.0.1:8487/api/ledger`,
from page origin `http://127.0.0.1:8487`. Its initiator was
`pagehide → activityCheck → activitySegment → note → flush`. The note filled the
20-event batch and started a normal fetch before the pagehide handler reached
its explicit beacon flush. The rejected dispatch had no network request,
preflight, response headers or HTTP status. The source's requested method was
POST, credentials `same-origin`, content type `application/json`.

Every flush now checks the page's lifecycle before dispatch. Hidden/departing
pages use the beacon path; a missing scope or rejected beacon retains the durable
outbox for reopen instead of beginning another fetch during teardown. Beacon
acceptance is still not acknowledgement. Only server-acknowledged IDs are removed.

The same reproduction also found WebKit undo in the focused note textarea
emitting a second native `historyUndo` at the unfocused ProseMirror draft. That
second event erased the draft. The structured editor now refuses native
undo/redo when its view lacks focus. Explicit toolbar commands still work.

Two older test defects were corrected without dropping their behavioral checks:

- `End` on macOS WebKit scrolls without placing the caret at the document end.
  The find recount check now places that caret explicitly and still types real
  keystrokes, checking the exact resulting text and match count.
- Notes tests previously trusted a stale Saved label while an asynchronous
  recovery write had not yet painted. The two-tab conflict check now awaits each
  actual note PUT response, verifying B's committed body before A tries to save.
  Undo of a replacement may restore a longer value, so the retained-stack check
  tests a changed value rather than assuming shorter text.

## Evidence

All results below are Playwright browser automation. Manual Safari has **not**
been run. The proof files record the installed engine and Playwright versions.
The full repository gate is a separate integration-owner check.

| Check | Chromium | WebKit |
| --- | ---: | ---: |
| Notes (save, undo/redo, conflicts, reopen) | 43/43 | 43/43 |
| Structured editor | 108/108 | 108/108 |
| Ledger persistence, retry, lifecycle and authorization | 13/13 | 13/13 |

The Node outbox fixtures pass29/29. Scrubbed before/after request traces and
fixture logs are in `docs/checkpoints/webkit-ledger-20261018/`. Traces include
origin, resolved path, initiator stack, method, relevant safe headers and actual
HTTP status when a request exists. Cookies, authentication headers and request
bodies are excluded. The fixtures contain synthetic writing only.

The new Ledger journey proves a successful append whose reply is lost remains
queued, reload preserves its event/session identity, retry acknowledges it, and
exactly one row exists in the authoritative JSONL. The pagehide threshold is
exercised through real reload, with all selected event IDs persisted once.
A paired request with a foreign Origin remains403; an unpaired POST and
unauthorized preflight remain401 without an origin allowance. A browser fetch
from an unauthorized opaque origin is also rejected, and none of those event
IDs enter the Ledger. The journey is required in both engines by `run.sh`.

## Reproduce

Use the existing `tests/journeys/run.sh` for the complete browser gate. For a
focused run, seed `tests/journeys/fixtures.py` and start
`tests/journeys/serve.py` with `WORDICON_TEST_MODE=1`, a disposable `WORDICON_STATE`
matching `JOURNEY_STATE`, `JOURNEY_MOCK_LANE=1`, and a free `JOURNEY_PORT`.
The standard runner configures outbound sockets/providers as unavailable.

Run `notes.js`, `editor.js`, and `ledger-delivery.js` with `JOURNEY_ENGINE`
`chromium`, then `webkit`, using that scratch `JOURNEY_DIR` and `JOURNEY_OUT`.
Set `JOURNEY_LEDGER_TRACE` to a short diagnostic filename prefix to capture
scrubbed request evidence. Run `node tests/test_ledger_outbox.mjs` separately.

## Runner registration follow-up

The shipped Receipts Chromium fixture is now executed by `run.sh`, with named
checks for local-only review, source-family limits, exact continuation references
and reopening without dispatch. Its focused rerun passed14/14. The totals now
include Receipts and both Ledger engines, and report the actual number of completed
journeys from their CHECKS records instead of assuming an old journey count.
No full browser-suite pass is claimed by this registration-only follow-up.

## Results reads during navigation — follow-up on31d9073

Both remote journey runs39109320333 (2f0e918) and39109788137 (31d9073)
failed the unchanged WebKit page-error assertion on operation-detail GETs.
The Ledger persistence and origin checks passed. A fresh local trace reproduced
why: `beforeunload` fired at08:14:39.404Z, an in-flight GET was cancelled at.405,
and Results issued two further `/api/operations/job_seed_*` GETs at.405/.406.
WebKit emitted access-control page errors before `pagehide` at.407. These were
same-origin reads from `Results.poll`, not Ledger POSTs or a changed CORS policy.
The selected original trace rows and its full-file SHA256 are retained in
`lifecycle-webkit-before.excerpt.json` in the checkpoint directory.

Results now owns an AbortController for its list/detail GETs. `beforeunload`
and `pagehide` stop those reads and subsequent iterations; old-generation
responses cannot update a restored page. `pageshow` starts a new generation
and resumes interrupted list reads, newly opened records and explicit refreshes
of terminal records. A temporary503 does not erase a pending detail refresh.
Start, recover, attempt and other POST requests retain their existing semantics.

A cancelled navigation has a deliberate limit: dismissing an unsaved-work
confirmation leaves Results reads paused with a visible “Updates paused” status
and “Resume updates” button. Clicking the button, or the next trusted pointer or
key input in that still-visible document, resumes the pending reads. The status
travels with the Results body into the narrow stacked layout; it does not replace
any displayed result or proposal.
It does not resume merely because a dialog was dismissed, from synthetic input,
or from a timer that might run during an accepted but slow navigation.
A genuine `pageshow` restoration resumes automatically. The visible status clears
when reads resume. Manual Safari was not run.

The focused Chromium and Playwright WebKit journeys each pass37/37. The existing
real reload/lost-reply persistence and cross-origin assertions remain. The added
controlled operation responses test early teardown, page restoration, list/Open/
terminal refresh recovery,503 retry, an actual dismissed navigation confirmation,
wide and stacked recovery controls, and one explicitly sent POST retaining its
original receipt without replay.
All operation/action requests are observed to assert no extra mutation. Open Case
passes32/32 with the shared fetch helper. The final Work journey passes117/117
with the independently reviewed keyboard fixture3c974a3. Independent WebKit UI
review passes11/11, including retained content, no render/layout requests, stacked
visibility, exactly one Resume GET and no mutation. A repeated Work run against
the same mock producer initially hit its intentional first-receipt cache and
failed the fresh-investigation-id assertion; restarting only the scratch server
reset that cache for the final117-check pass. The full37-journey release gate remains
a separate integration-owner run after these changes are merged.

The `lifecycle-*` logs, browser proofs and scrubbed traces in the checkpoint
folder contain only disposable fixture records. Their URL, phase, initiator,
method, safe headers, response status and cancellation evidence are retained;
cookies, authentication headers and request bodies are excluded.
