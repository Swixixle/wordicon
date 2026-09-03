# Browser journeys

The behavioral half of the constraint suite: what a static test cannot
hold — the writing room keeping its object identity (draft, caret, undo
history) across Write / split / swap / full page / close, Home's
continuation cards through stable ids, the ruling band's composition,
the Saved-for-later line's placement, phone and split layouts, the
anatomy's stillness until a click. `tests/test_global_constraints.py`
stays the fast unit job; these run in a real headless Chromium against
a scratch store.

    cd tests/journeys && npm ci && npx playwright install --with-deps chromium
    bash tests/journeys/run.sh

`run.sh` makes a scratch directory, seeds sanitized fixtures
(`fixtures.py`), starts `serve.py` — the app with `LOCAL_STATE`
redirected to the scratch, the model gateway poisoned, the API key
removed, outbound HTTP pointed at a dead proxy — then runs `quiet.js`
(block 104: browsing with encounter recording off; `run.sh` hashes the
scratch store before and after it and fails if a byte changed),
`home.js`, `anatomy.js`, `chooser.js` (block 105: the cats sentence and
an invented name read by the destination chooser, nothing run by typing,
a question kept verbatim, Run it reached only through Develop the idea)
`speak.js` (block 106, hashed like `quiet.js`: with a fake microphone
the instrument is pressed, listens, is stopped, transcribes with the
mock engine, is discarded, and survives a reload mid-listen with
nothing recording — none of it writes), `speakkeep.js` (Keep recording
into Media with the engine on the transcript version; an edited spoken
transcript sent as an open question with its identity), and
`encounter.js` (the switch turned on and off
from About & proof with each flip recorded, one `owner_opened` row by
id, and an unresolved Recovery Review case found on Home and reopened).
Every check prints one line. A failing check saves a
screenshot into `$JOURNEY_OUT`; CI uploads that directory on failure.
The run fails if a journey fails, does not reach its final line, or if
Playwright or the browser is missing — nothing is skipped silently. Any
request leaving the scratch origin is a failure.

Never the real store: `local_state/` is not read or written. Playwright
is pinned in `package.json`; the browser revision follows it.

Environment: `JOURNEY_DIR` (scratch; default a temp dir), `JOURNEY_PORT`
(default 8499), `JOURNEY_OUT` (diagnostics), `JOURNEY_CHROME` (a browser
executable, when not using Playwright's own), `PYTHON`.
