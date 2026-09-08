# Nikodemus — capability census

> **A SNAPSHOT, not a standing description of runtime truth.** Collected
> at one commit and true of that tree. Capability moves; this file does
> not move with it. Check `docs/CHANGELOG.md` for what has shipped since,
> and the suite for what is actually enforced.

**Read-only.** Nothing was repaired, renamed, exposed, deleted or consolidated
while this was collected. Every entry below is a report, not a proposal; the
classification section at the end names what *could* be done and rules on
nothing.

**Method and evidence order.** Runtime code is primary evidence. Tests are
proof *claims* — a passing test proves what it actually exercises, which is
sometimes less than its name. Documentation is declared *intent*. Where the
three disagree, the disagreement is listed rather than resolved.

**Provenance of this document.** Route, surface and record inventories were
collected by three read-only passes over the repository at commit `452e98c`.
The candidate counts in §1 and the paste-to-model path in §4.1 were verified
directly against the owner's own store and source. Anything not directly
verified is marked *(reported, unverified)*.

---

## 1. The verified count

The earlier figure of "nine to one" was wrong. It took the **keep rate** (102
kept of 932 shelf rows ≈ 1 in 9) and reused it as a **generate-to-rule ratio**,
which has a different denominator. Corrected, counted from
`local_state/judgments.jsonl` and `accepted_concepts.json`:

| Quantity | Value | Definition |
|---|---|---|
| Judgment rows | 160 | lines in `judgments.jsonl` |
| — sourced `owner` | 154 | `decision_source == "owner"` |
| — sourced `validator` | **6** | **not the owner** — see §4.2 |
| Unique candidates touched by any judgment | 144 | by `concept_id`, else lowercased title |
| Unique candidates the **owner** ruled on | **138** | non-validator rows only |
| Candidates ruled more than once | 9 | revisions and changes of mind |
| Decisions by kind | accepted 110 · revised 31 · rejected 19 | row counts, not candidates |
| `accepted_concepts.json` entries | 107 | shelf entries, 0 with `alias_of` |
| Shelf denominator shown in the app | 932 | the Library's own "every word" count |

**Ratio, with the denominator stated: about one candidate ruled on for every
6.8 on the shelf.** Not nine.

Two caveats on the denominator itself. A broader count over all 480 result
files finds **1,303 unique titles**, but that includes sprout thread anchor
names, which are not candidates awaiting a ruling. The app's 932 uses a
narrower rule. Neither number is wrong; they answer different questions, and
no surface currently says which one it is showing.

`review_status` is `"unreviewed"` on all 160 rows. The field appears to be
dead.

---

## 2. Capabilities, by wing

Status vocabulary: **built and reachable** · **built but hidden** (works, no
door) · **partially built** · **fixture-only** (proved only against
hand-authored data) · **unbuilt** (declared, no code) · **orphaned** (code with
no caller).

### 2.1 The writing room
- **Purpose** — where the owner writes; the sole semantic text, with an
  optional paint layer that may never own layout, selection, input, pointer
  behaviour, clipboard or accessibility meaning.
- **Status** — built and reachable.
- **Entry** — `#compose` on Home; `⫞ write beside the page`; `⤢ full page`.
- **Chords** — `⌘⇧P` whole draft · `⌘⇧⏎` this paragraph (workspace open only) ·
  `Tab`/`⇧Tab` indent · `Esc`-then-`Tab` exits the indent trap · `Esc` closes.
- **Records** — `inputs.jsonl` on run; no draft is persisted server-side.
- **Model** — none until a chord or Run it.
- **Proof** — `room.js` in WebKit (caret on the drawn letter, no wrap movement
  mid-animation, Tab as one undo), `shell.js` (object identity across
  split/swap/full-page/close). Fully real, no mocks.
- **Defects / gates** — the owner's manual Mac pass is still owed. Workspace
  **mode** is never persisted while `side` and divider width are, so the room
  always reopens in `write`.

### 2.2 The forge / Go Deep / decompose
- **Purpose** — take a passage apart into components, forge candidates against
  each, run Friction, record the two grounding tiers.
- **Status** — built and reachable.
- **Entry** — Run it on Home; `⌘⇧P` / `⌘⇧⏎` from the room.
- **Model** — yes. `/api/jobs` (POST). **No cost or lane is disclosed before
  the call for any mode except `deep`** (see §4.1).
- **Records** — `results/`, `receipts/`, `edges.jsonl`, `inputs.jsonl`,
  `judgments.jsonl` on ruling.
- **Proof** — the suite (blocks 108–116); `deep.js` and `resume.js` are
  **heavily mocked** — `/api/config`, `POST /api/jobs` and `GET /api/jobs/<id>`
  are all `page.route` fulfilments, and the split-pane price is computed from
  an invented `deepResult()`.
- **Defects** — three candidates per component are never compared against each
  other, only against the existing corpus, which is the mechanism behind 39
  definitions carried by more than one word.

### 2.3 The Library / the shelf
- **Purpose** — every word ever put in front of the owner, with its ruling and
  what the record says beside it; plus the counted panel (block 115).
- **Status** — built and reachable.
- **Entry** — nav **Library** opens the *Documents* band; the concept shelf is
  `#concepts` / nav **Concepts**. Two different things, both called Library in
  places (§5.1).
- **Records** — reads `judgments.jsonl`, `receipts/`, `results/`,
  `accepted_concepts.json`, `bench/`, `inputs.jsonl`.
- **Proof** — `epistemic.js` covers the shelf opening and the counted panel.
  No journey covers re-ruling from the shelf or the word filters.

### 2.4 The Clinic
- **Purpose** — institutional sources by declared seat — policy, current
  guidance, superseded guidance, label/device, independent study, manufacturer
  — never blended.
- **Status** — built and reachable; **thin proof**.
- **Privacy boundary** — two gates. The question gate refuses patient-specific
  *intent* with or without identifiers; the document gate detects identifiers.
  **The Clinic is not a lane for personal medical records** and a personal
  medical-record inquiry must not be routed through it.
- **Records** — `clinic/sources.jsonl`, `proposals.jsonl`, `relations.jsonl`,
  `rooms.json`, `phi_refusals.jsonl`, `disagreements.jsonl`.
- **Model** — `/api/clinic/disagree`, undisclosed.
- **Defects** — `phi_refusals.jsonl` is **write-only** (§4.3);
  `disagreements.jsonl` is read in-app only for its `proposal_id`, so the
  owner's ruling is a tombstone in the running system; `rooms.json` is
  rewritten in place with no event log and no rebuild path.
- **Proof** — journey covers the deep link and that it opens as a place. No
  ingest, hold, or ask is exercised in a browser.

### 2.5 The Investigation Room and federation
- **Purpose** — what Open Case and EthicalAlt deposed, seats kept apart by
  instrument, identity proposed mechanically and declared only by the owner.
- **Status** — built and reachable, **labelled "In trial use — not yet relied
  on."**
- **Model** — none. **Network** — yes: `/api/connectors/<cid>/check`,
  `locate`, `import`, all to a pinned origin with credentials held as `env:`
  references, never values.
- **Proof** — `federation.js` is one of the strongest journeys: real server,
  real HTTP to a mock producer, signature verification under a pinned key,
  named failure classes, seats kept apart, Declare converges. The **producer
  contract itself is fixture-only** — a real Open Case or EthicalAlt export
  drifting from the golden fixtures would not be caught.
- **Gates** — no real deployment, no real case imported, no Vault sealed after
  a real import.

### 2.6 The Inquiry
- **Purpose** — a question kept verbatim, with its branches, their standing and
  what became of them; the Question Reader proposes bounded readings without
  answering.
- **Status** — partially built. Phase 1 (the graph) and phase 2 (the Reader)
  are built and reachable. **Five rail entries are declared unbuilt**: *ask my
  record*, *research outside*, *trial*, *comparison*, *synthesis*.
- **Entry** — only the "Open an inquiry" destination chip, which requires a
  question-shaped input.
- **Model** — `/api/inquiry/<iid>/read`, and it is **one of only two paths in
  the app that discloses its cost before firing**.
- **Proof** — `inquiry.js`, real server path against `MockReader`, no
  `page.route`. Proves the mechanical check, the recorded identity and the
  structural guarantees; proves nothing about whether a real model returns good
  readings.

### 2.7 The Bench
- **Purpose** — take a kept word apart: contract, materials, name exploration.
- **Status** — built and reachable, badged **prototype**.
- **Entry** — `⚒ Take it to the Bench` on a result card — since block 116,
  usually inside the collapsed *other doors*. Also `/bench?concept_id=`.
- **Model** — four routes, **none disclosed**: `/api/bench/open`, `/build`,
  `/concept`, `/concept/names`.
- **Proof** — title, back link and the `?concept_id=` deep link only.

### 2.8 The Keeper
- **Purpose** — custody of the narration, not authority over the record.
- **Status** — built, **zero journey coverage**, one orphaned model route.
- **Records** — eight logs plus `sheet.json`, `manifests/`, `capsules/`.
- **Model** — `/api/keeper/close`, `/retry` (undisclosed) and
  **`/api/keeper/renarrate`, which no surface in the app calls** (§4.4).
- **Defects** — constitutional wing with no browser proof at all.

### 2.9 The Vault
- **Purpose** — restores a verified past; regrows nothing.
- **Status** — built; drill-proven off-device 2026-09-01; **no browser proof**.
- **Defect** — every journey mocks `/api/vault/status` with a healthy literal.
  **No test asserts anything about the real endpoint**, so renaming
  `stale_red`, `failure` or `dirty_seconds` leaves the strip permanently green
  and the red path unreachable in test (§4.5).
- **Runs without a request** — a 30-second debounced backup loop, backups at
  boot and `atexit`, and a flock corpus lease that refuses to start if held.

### 2.10 Map / Trails / the overworld
- **Purpose** — concepts as nodes, names as satellites, roads the owner
  declares.
- **Status** — built; **the naming is the worst in the system** (§5.1).
- **Model** — `/api/map/roads/suggest`, `/api/map/route/analyze`, undisclosed.
- **Proof** — the frame opens and one link is followed. No road, route or log
  behaviour is exercised.

### 2.11 Speak
- **Purpose** — push-to-talk, editable transcript, audio ephemeral unless kept.
- **Status** — built and reachable.
- **Model** — local Whisper; `/api/speak/model/fetch` reaches Hugging Face on a
  visible button press.
- **Proof** — `speak.js` and `speakkeep.js`, real routes against a server-side
  `MockEngine`; `run.sh` hashes the store around the quiet half.
- **Gates** — real owner-voice testing, phone HTTPS, conversation mode (the
  last is declared "not built").

### 2.12 Recovery
- **Purpose** — the identity-migration cases, ruled by the owner.
- **Status** — built and reachable; `recovery_events.jsonl` is **write-only**.

### 2.13 Warps and the Wayfinder
- **Status** — built, **zero journey coverage** (Warps) and one
  element-exists check (Wayfinder). `/api/warps` is orphaned.

### 2.14 Debrief / code analysis
- **Status** — **not present in this repository.** There is no code-intake
  path in Nikodemus. Debrief is a separate instrument. The shape this most
  plausibly takes is federation — Debrief examines outside code under its own
  rules and deposits a signed, inspectable report into an Investigation or an
  Inquiry — and nothing here should fuse its parser into Nikodemus.

---

## 3. The route ledger

152 path+method entries, all in `server.py`; no blueprints.

| Class | Count |
|---|---|
| Invokes a model | 15 |
| Outbound network, no model | 4 |
| Local only | 133 |

Every model route is also outbound-network when `ANTHROPIC_API_KEY` is set and
falls to the mock lane otherwise. `/api/jobs` additionally reaches
`smtp.gmail.com:587` through `notify.py` on completion, and the search-enabled
stages (sprout, etymon, refract, verify) trigger provider-side web search that
is disclosed nowhere in the app.

**Seams**: `READER_GATEWAY = None`, `speech.ENGINE = None`, `cli.LOCAL_STATE`
and five path constants rebound by `vault.py` and `blind.py`, `vault._NoNet`
socket poisoning for the drill, `gate._STATE` for pairing.

**Environment**: `ANTHROPIC_API_KEY` (the lane switch), `WORDICON_MODEL`
(required with it, never guessed), `WORDICON_LAN`, `PORT`, `WORDICON_STATE`
(**CLI tools only — not read by `server.py`**), the four notify variables,
`WORDICON_VAULT_IDENTITY`, `HF_HOME`, and `env:`-referenced connector
credentials resolved at call time and never stored.

---

## 4. Structural cross-checks

### 4.1 A billable model call fires from a keystroke, with no disclosure
**Verified directly.** `document.addEventListener('paste')` is bound to the
whole document; any pasted file goes to `uploadFile` → `POST /api/upload` →
`cli.represent_artifact(..., server_gateway())`. The same listener exists for
`drop` anywhere on the page. There is no panel, no lane, no model name and no
price. The "photo · text read off it by a model" label renders **after** the
call has already been made.

This is out of step with the app's own pattern: `askDeep` shows lane, model and
an estimate before spending, and the Inquiry's `readCost` names the model
before the button. **Thirteen of the fifteen model routes disclose nothing
before firing** — every `/api/jobs` mode except `deep`, all four Bench routes,
`/api/upload`, `/api/library/support`, both Map routes, `/api/clinic/disagree`,
and two Keeper routes.

### 4.2 Six judgments in the record were not made by the owner
`decision_source` is `"validator"` on 6 of 160 rows. The constitution says the
owner's ruling is the only final authority. This may be a legitimate mechanical
rejection of a malformed candidate; either way, six rows in the record are
decisions the owner did not make, and no surface distinguishes them.

### 4.3 Records written and never read
Five stores are written by the running application and read by nothing in it.
Reads from tests or offline scripts do not count.

1. **`definition_events.jsonl`** — the most serious. It exists to support the
   claim that *"the shelf is a projection that can be rebuilt and checked, not
   the only copy."* `server.py` contains no reference to it. Worse,
   `persist_definition_edit` (`POST /api/definition`) rewrites the shelf and
   appends **no event at all**, so the two can drift with nothing in the app
   able to notice.
2. **`clinic/phi_refusals.jsonl`** — the record that the privacy gate fired.
   Nothing reads it, so zero refusals and a thousand refusals look identical.
3. **`clinic/disagreements.jsonl`** — read in-app only for its `proposal_id`.
   The owner's actual ruling is consulted solely by an offline script.
4. **`recovery_events.jsonl`** — the audit trail of the identity migration.
5. **`speech_vocabulary.json`** — dead projection, harmless: the app now folds
   the event log instead. This is the *contrasting* case to #1 — a projection
   correctly superseded.

### 4.4 Routes with no door
Twelve routes are referenced by no `webapp/*.html`: `/api/auth/devices`,
`/api/keeper/deactivate`, **`/api/keeper/renarrate` (model, mutating)**,
`/overworld/map`, `/api/warps`, `/api/speak/hints/<sha>`,
`/api/federation/recognize`, `/api/identity/proposals`, `/api/clinic/relation`,
`/api/export/corpus/manifest`, `/api/artifact/<artifact_id>`,
`/api/bench/corrections`. Four are mutating with no affordance at all.

**Doors with no route: none.** Every `fetch`, `href`, `src` and `action` target
in the webapp resolves.

### 4.5 Tests that prove only fixtures
- **The Vault strip.** Eight `page.route('**/api/vault/status')` fulfilments
  across seven journeys, all with the same healthy literal. The red path is
  proved only against an invented failure object; `vault.py`'s real failure
  path never reaches a browser.
- **`deep.js` / `resume.js`.** `/api/config`, `POST /api/jobs`,
  `GET /api/jobs/<id>` and `/api/inflight` are all fulfilled. Block 108 now
  cross-reads the real serializer's keys, but `progress`, `input_text` and the
  whole result envelope remain hand-authored — the same class as the job-shape
  bug that once let thirty-one checks pass against a shape the server never
  emitted.
- **`home.js:51`** hand-injects `HOME.pending.saved`; the server emits no such
  row in the journey, so renaming the key ships a blank band undetected.
- **The provider SDK.** The citation collector and the streaming path are
  proved against hand-built block objects. A real SDK shape change passes
  green.
- **The federation producer contract** is golden-fixture only.

### 4.6 Checks that cannot fail
Representative, with line numbers in `tests/test_global_constraints.py`:
`1615` and `2191` have `pass` as their entire body. `16702`, `288`, `11982`
pin strings that exist only inside comments. `12060` and `12964` are gated on
`local_state/` files that are gitignored, so they **never run in CI**.
`15374` matches an 8-character needle over a fixed 3,000-byte window — the
exact byte-slice weakness the suite names elsewhere in its own comments.
`shell.js:154` destructures a `needle` it never uses, so six places are checked
for HTTP 200 and nothing else.

Structurally: the large majority of the suite's ~2,600 failure sites assert
that a branch **exists in source** rather than that it is **reached**. This
session found that class three times.

### 4.7 Documentation describing behaviour that does not exist
- `wordicon_active_job` is written and deleted in eight places and read by
  nothing; its own comment claims "reopening the tab picks the poll back up
  automatically."
- About refers to work waiting under **"Where you left off"**. No such element
  exists; the band is called Continue.
- `resumeJobIfAny()` restores collapsed sections and resumes no job.

### 4.8 Projections that cannot be rebuilt inside the app
`accepted_concepts.json` from `definition_events.jsonl` — the rebuild and check
functions exist but are reachable only from offline scripts and tests.
`library/documents.json` from `library/ingests.jsonl` — no rebuild code exists
at all. `clinic/rooms.json` — rewritten in place, no event log.
Correctly rebuildable: the speech vocabulary, the overworld, the trails, the
bench library, the connector list, the inquiry graph.

### 4.9 Settings saved and never restored
`sect_docs-body`, `sect_questions-body`, `sect_media-body`, `sect_sources-body`
are written by `toggleSection` but only `history-area` and `library-body` are
restored — and the restore honours only the value `closed`, never `open`.

---

## 5. Names

### 5.1 Two names for one thing, or one name for two
- **Map.** The nav item "Map" opens a page titled **Trails**. The overworld has
  four names — *Map*, *Map · the world*, *the spatial map*, `/overworld/map` —
  and `PLACES['/overworld']` is labelled "Map" while serving `trails.html`.
- **Library.** The nav item opens the *Documents* band. The concept shelf owns
  every `library-*` element id, and About's "The Library" describes the shelf,
  which is also called *the shelf* and *the Lexicon*.
- **Room.** Work Room, Clinic room, Investigation Room(s), the writing room and
  the Rooms band are five different things. Investigation is singular in one
  place and plural in another, and its link reads "Open the instruments."
- **About.** "About & proof" / "The Keeper · About" / "What is Nikodemus? — and
  proof" / `#system` / `about-panel`.
- **Wordicon.** `manifest.json` still declares `"name": "Wordicon"`; the
  overworld ships a literal "Wordicon" fallback string; the Bench stores
  `'let Wordicon choose'` as a wire value; storage keys mix `wordicon.*` with
  `nikodemus.run.route.v1`. The naming law permits the technical names; the
  **manifest name and the visible fallback string are user-facing**.

### 5.2 Reachable only by typing a URL
`/overworld/map`, `/overworld`, `/trails`, `/pair`, `/?job=<id>` (email only),
`/bench?word=`, `/investigation?room=`, `/#system`.

---

## 6. Findings, classified

This section names options. It rules on nothing.

| Capability | Classification | Why |
|---|---|---|
| Paste/drop → model call | **repair** | Spends money from a keystroke with no disclosure; out of step with the app's own two disclosed paths |
| The other twelve undisclosed model routes | **needs ruling** | Whether every model call must price itself, or only some |
| `definition_events.jsonl` | **repair** | Written, never read; and the edit path writes no event at all, so the shelf claim is unsupported in-app |
| `clinic/phi_refusals.jsonl` | **repair** | A privacy guard whose firing nothing can see |
| Six validator judgments | **needs ruling** | The constitution says the owner is the only final authority |
| Vault status endpoint | **repair** | The one guarantee with no real-endpoint proof anywhere |
| Keeper | **repair** | Constitutional wing, zero browser proof, one orphaned model route |
| `/api/keeper/renarrate` | **needs ruling** | Live model call, no caller: expose it or remove it |
| Warps | **needs ruling** | Built, no coverage, orphaned route, no prominent door |
| Map / Trails / overworld naming | **repair** | Three surfaces, six names, two of them unreachable except by URL |
| `manifest.json` name, overworld fallback | **repair** | User-facing "Wordicon" after the naming law |
| Inquiry's five unbuilt rails | **keep prominent** | Declared honestly; they are the roadmap |
| The Bench | **keep but recede** | Prototype-badged, thin proof, now behind a disclosure |
| Sibling-candidate collision | **repair** | The mechanism behind 39 shared definitions |
| `deep.js` / `resume.js` mocks | **repair** | The same fixture class that once hid a real contract break |
| Debrief / code intake | **federate** | Not in this repo; a signed deposit, never a fused parser |
| `sect_*` restore, workspace mode | **repair** | Small, and each one is a promise the app makes and does not keep |
| `review_status` field | **deprecate** | `"unreviewed"` on all 160 rows |
| Unbuilt chooser destinations | **keep prominent** | Each already states its own reason |

---

## 7. What this census did not examine

The two producer repositories (Open Case, EthicalAlt) beyond their contract
fixtures. The Vault's off-device restore path. Anything in
`~/Downloads/wordicon-backlog.md` that has no code. The owner's real corpus
contents beyond the counts in §1.

---

## 8. Notes added after the census — the Map Focus build (2026-09-08)

The census above is a snapshot at `452e98c`; these notes are dated and name
their own evidence.

**A write-order defect, and the eighteen.** Eighteen rows in the owner's
`edges.jsonl` cite receipts that do not exist: three sprouts at
2026-09-03T05:24:10Z, 05:24:16Z and 05:25:35Z (five `parallels` and one
`continued_from` each), whose receipts `receipt_trace_cli_2562964933`,
`_9fea3c6271` and `_6792cc220b` were never written and whose snapshots do not
exist. Cause: `run_sprout` appended its roads before building and validating
the receipt, and the three sprouts failed in between — ten hours after block
104 changed the receipt shape (`3fc5dbe`, 2026-09-02T18:56Z), which is an
inference, not a record. The same order stood in `run_refract`, `run_revise`,
`run_archetype`, `run()` and the composite writers (for a CLI deep run the
parent receipt was never written at all). All repaired (v1.18.0); the eighteen
rows are untouched and render as *producer receipt cited · file not found*
with no snapshot claimed.

**Issuers under the exact rule.** The counts belong here and in the changelog,
never in the constitution. They are produced, with their populations, the
method, the date and the store hash before and after, by
`python3 scripts/map_focus.py --census --state ⟨local_state⟩`; paste its output
below when it is run on the owner's record, and keep the date.

*Population: rows in edges.jsonl without a recorded origin; roads in the
served map (recorded and reconstructed). Method: derive_issuer per road under
issuer-derivation/1 — exact recorded identity against the run's snapshot or a
composite listing it; the writer invariant only for rows created at or after
2026-08-29T23:43:11Z. The reconnaissance figures 1,481 / 32 / 93 were counted
under a label-prefix rule and are superseded.*

**The Map's names, resolved.** The header's **Map** opens *Map · focus*
(`/map`); *Map · trails* (`/map/trails`) and *Map · world* (`/map/world`) are
the other two views, named the same on all three pages; `/overworld/map`,
`/overworld` and `/trails` stay as old URLs. §5.1's Map entry is closed.

**Two of the undisclosed model routes now disclose.** `/api/map/roads/suggest`
and `/api/map/route/analyze` open the disclosure panel before any request
leaves the page (§4.1's count of thirteen undisclosed routes is now eleven).

**`/api/warps`** stays classified `dormant_capability` in `DOORLESS_ROUTES` —
deliberate dormancy, not retirement; nothing in tests, docs or contracts reads
it.

**Two new read-only routes.** `GET /api/map/focus`, `GET /api/map/places`
(local only; §3's local count rises by two). Both have a door (`focus.html`).

**Found, reported, not repaired.** (1) A trace id is `sha256(input_text +
_now())[:10]` with `_now()` at one-second grain: two runs on one input inside a
second share an id, and the second overwrites the first's receipt and
snapshot — the journey fixture waits for the clock; the writers have no
guard. (2) `build_overworld` draws a sprout or refract from a concept-keyed
candidate twice: the recorded road from the concept box, and a reconstructed
road from the snapshot's title-keyed seed (`node_word(seed_title)`), which the
dedupe cannot match because the keys differ. Every such concept has a
title-keyed twin carrying duplicate reconstructed roads and inflated dispute
tallies; Map · focus discloses the twin and counts disputes by run. (3) A
revise's `renamed_as` / `compressed_as` roads are recorded from the original's
*title* key, so a concept-keyed box and its title-keyed twin split a revise's
history; disclosed, not welded. (4) The constitution's Map section carries
a live count from block 82 ("three percent of shelf pairs"); the Map Focus
paragraph carries none, per the ruling, and the older sentence is left as
written.
