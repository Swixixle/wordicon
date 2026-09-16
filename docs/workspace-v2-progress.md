# workspace-v2 — progress

The build authorized on 2026-09-16 (implementation instructions: "Nikodemus — implementation instructions for Claude", forwarded by the owner with "I authorize the build, testing, corrections, commits and delivery of a working candidate while I'm away"). This file is the resumable state of that build: what is done, on which commit, with which tests, and what remains. It is updated at the end of every slice and whenever a session could be interrupted.

Branch: `workspace-v2`, cut from `17894e3` (main = origin/main on 2026-09-16). Data during the build: fixtures and disposable roots only; the owner's store is never read or written.

## Slices

| Slice | State | Commit | Evidence |
|---|---|---|---|
| A — fail-closed test environment, explicit data root, baseline ledger | done | 3bd9b01 | suite exit 0 with the new canary; 25 journeys, 983 checks, exit 0, under test mode; sabotage of the canary (two ways) fails it by name |
| B — /work shell, action registry, notebook + fixture result path | done | (this commit) | suite exit 0 with `_check_workspace_registry`; 26 journeys, 1048 checks, exit 0 (`work.js`: 65 checks in WebKit on the mock-lane server) |
| C — rich document model/editor and compatibility | not started | | |
| D — durable operations and common dispatch | not started | | |
| E — Your work index and complete retrieval | not started | | |
| F — investigation adapters and Ask | not started | | |
| G — parity, accessibility, failure testing, delivery | not started | | |

## Slice A — what was built

- `scripts/testmode.py`: `WORDICON_TEST_MODE=1` (inherited by children) installs a socket guard — outbound `connect`, `connect_ex`, `sendto` and name resolution are refused unless loopback on a port the guard was told about (`allow_port`, `WORDICON_TEST_ALLOW_PORTS`, `JOURNEY_PORT`); the real application's port (8420 / `PORT` / `WORDICON_TEST_DENY_PORTS`) is refused even when listed; every refusal is recorded in-process and appended to `WORDICON_TEST_EGRESS_LOG` with host, port and calling frames, never a payload. A provider gateway built in a test process gets an httpx transport that refuses every request (the attempt-loop checks need the real class). `harden(server)` swaps readers, Moira and speech for their stand-ins.
- `wordicon_cli.py` imports `testmode` before anything else and reads no `.env` in test mode (the real repository's `.env` only — the loader stays testable against a temp dir). `server.server_gateway()` answers the mock in test mode whatever the environment holds. `notify._configured()` is false in test mode.
- `scripts/state_root.py`: one data root per process — explicit argument, else `WORDICON_STATE`, else a root the process already chose by hand, else the repository's `local_state`; `apply()` rebases every `Path` attribute of every imported scripts module that points under the repository default or any previously applied root (no hand-kept list). `server.py` applies it at import, refuses the real store in test mode (`testmode.assert_isolated`) and prints the resolved root in its banner. The Vault drill's child process declares its own root before importing the server.
- `tests/journeys/run.sh` exports `WORDICON_TEST_MODE=1`, `WORDICON_STATE=$JOURNEY_STATE` and the egress log for every process of a run; `serve.py` sets the same before its first import and allows the mock producer's port.
- `tests/test_global_constraints.py` sets test mode and its scratch root before its first import, applies `state_root` on top of its hand list, and gains `_check_test_mode_fails_closed`: a direct socket to 1.1.1.1:443, a lookup of api.anthropic.com and a connection to the real port are refused and logged; with a sentinel key and model in the environment `server_gateway()` still answers the mock and a directly built provider gateway cannot send; notify stays off with sentinel mail credentials; the suite is not on the repository store and the server resolved the same root. Proven to fail under sabotage: `server_gateway` ignoring test mode → "answered 'anthropic'"; the guard's `connect` restored → "expected three refusals, saw 2".

Finding recorded during A (the instruction's warning was right): the first version of `state_root.apply()` took "the current cli.LOCAL_STATE" as the only old root. The journeys' seeder (`fixtures.py`) sets `cli.LOCAL_STATE` by hand and then imports the server; the server's `apply_from_env()` resolved to the repository default (no env set in that process) and rebased the seeder's scratch paths back onto the repository's own `local_state` — 70 fixture files landed in the container clone's real store before the journeys noticed an empty Home. Fixed by the resolution order above and by `run.sh` exporting the root and test mode for every process; with test mode on, that process would now refuse to run on the real store instead of writing to it. The container clone's `local_state` (gitignored, test exhaust) is the only thing that was written; the owner's Mac was never involved.

## Slice B — what was built

- `webapp/work/` — `work.html`, `work.css` (the app's tokens; two new chrome values recorded in workspace-v2-build.md D11), `main.js` (bootstrap), `layout.js` (independent Tools/Results, Focus, resize grips with keyboard, measured narrow mode: drawer + section below), `session.js` (the document session over an editor adapter, the notebook client's semantics), `editor_plain.js` (the textarea adapter — kept as the plain path in C), `recovery.js` (IndexedDB envelopes per document and tab), `actions.js` (Tools groups, the selection menu, the proposal card, Ask), `results.js` (Results/Feedback/Notes/Sources; tracked operations; freshness against the snapshot), `places.js` (existing pages inside the shell with return), `yourwork.js` and `investigate.js` (slice B forms; E and F replace their sources).
- `scripts/actions.py` (the registry, readiness, Ask matching, prepare/load_prepared/job_payload), `scripts/snapshots.py` (immutable content-addressed input snapshots).
- `server.py`: `/work`, `/work/<file>`, `GET /api/actions`, `POST /api/actions/match`, `POST /api/actions/prepare`, `POST /api/operations`, `GET /api/operations/<id>`; `_create_job_from(data)` split out of the job route so a Start goes through the same body.
- `tests/journeys/work.js` (WebKit) on a second scratch server (`JOURNEY_MOCK_LANE=1`, port 8498) started by `run.sh`; `_check_workspace_registry` in the suite; `work` added to the pinned WebKit list.
- Known gaps carried into later slices: request keys are in process memory (D); an operation the restarted server no longer holds is shown as outcome unknown (D); Your work lists the notebook and the last thirty runs (E); the toolbar is hidden until the structured editor (C); Archive and restore-as-new (C/E); investigation Start is unavailable by the connector contract (F); concept-subject actions (Sprout, Archetype, Revise, Re-check) have no concept picker in the shell yet — reached from a result inside the shell (E lists concepts).

## Test commands

- Suite: `WORDICON_TEST_MODE` is set by the file itself; `timeout 900 python3 tests/test_global_constraints.py` (≈2 min; exit 0 with the two private-store skips).
- Journeys: `JOURNEY_DIR=<scratch> bash tests/journeys/run.sh` (≈12 min; `== journeys: 1048 checks, exit 0` after slice B; ports 8499 and 8498 must be free).

## Remaining, in order

C, D, E, F, G as the instructions' §4 table. Blockers: none for the local workspace. External deployment facts (EthicalAlt, Open Case, PUBLIC EYE, the Rabbit Hole repository) are unavailable and block only live verification of their adapters.
