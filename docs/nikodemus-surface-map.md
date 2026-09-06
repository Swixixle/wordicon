# Nikodemus — surface map

**What a person can reach, from where, and why.** Companion to
`nikodemus-capability-census.md`. Read-only; nothing was changed to produce it.

The organising question is not "what exists" but **"standing on Home, what can
I get to, and how many presses does it take?"** Where the answer is *you
cannot, unless you type the URL*, that is stated.

---

## 1. Home, and everything one press away

Home paints from local records with no model in the path. In order down the
page:

| Band | What it holds | Door |
|---|---|---|
| **Continue** | the objects you were last using, as themselves | each card opens its own thing |
| **Needs your ruling** | bounded; plus *Saved for later*, *Unresolved*, *Open questions* | each row is a door |
| **Bring something in** | the destination chooser, the gesture chooser, speak review, three intake doors | Run it appears only after *Develop the idea* |
| **Recent** | runs by subject | a title reopens the run |
| **Concepts** | the shelf — every word, its ruling, the counted panel | `Open the shelf` |
| **Rooms** | Work Room, Clinic rooms, Investigation | `Enter`, `Open the Clinic`, `Open the instruments` |
| **Library** | Documents · Open questions · Media · Sources | four disclosures |
| **The Keeper · About** | the constitution and the proof | no nav link — `#system` or scroll |

The writing room sits at `#compose` with its own bar: `Aa` (face, size, view,
landing style), `⇄ sides`, `⫞ split`, `⤢ write`, `☰ page`, `⤓ save`,
`done · esc`.

---

## 2. The places

A *place* opens inside the shell beside an untouched writing room, and each is
still its own document answering on its own URL.

| Place | URL | Title it shows | How you actually get there |
|---|---|---|---|
| Trails | `/map` | **Trails** | header nav **Map** |
| The overworld | `/map/world` | **Map** | one link, inside the Trails header |
| — | `/overworld/map` | Map | **nothing links here** |
| — | `/overworld` | serves Trails, labelled Map | **nothing links here** |
| — | `/trails` | serves Trails, labelled Trails | **nothing links here** |
| The Bench | `/bench` | The Bench *(prototype)* | `⚒ Take it to the Bench` on a card — since block 116 usually inside the collapsed *other doors* |
| The Clinic | `/clinic` | The Clinic | intake door `🏛 Admit a source to a Room`; Rooms row; destination `Start a Room` |
| Investigation | `/investigation` | Investigation Rooms | Rooms row `Open the instruments`; two About links; five destination chips |
| Recovery | `/recovery` | Recovery Review | About link; the `Unresolved` line; Home's `Review them` |
| The Inquiry | `/inquiry` | the question, kept | **one door only** — the `Open an inquiry` destination chip, which needs a question-shaped input |
| The anatomy | `/anatomy` | The Functional Anatomy… | header `Anatomy`; About `See the anatomy`. Constitutionally standalone — not in the shell |
| Pairing | `/pair` | — | no link; reached only by a 401 redirect |

**Four of the twelve are unreachable without typing a URL.**

---

## 3. What the app says is not built

Every one of these already states its own reason, in the owner's voice. They
are the roadmap, and they are honest.

**In the destination chooser** (dashed, disabled):
- *Research outside Nikodemus* — "not built yet — save the question and it
  waits, findable, in the Library. Search my record is the local exact-text
  search, not this"
- *Study the name* — "the Name Study is the next block after the chooser"
- *Create a private portrait* — "the Portrait is a separate opt-in object,
  after the Name Study"
- *Save owner-declared facts* — "the Owner Card needs its privacy contract
  before a line of it exists"
- footer: "The highlighted destination is not built yet; the others are real
  doors."

**On a deep workup** — *Run all three on every component*: "not built —
fanning three instruments across every component is its own machinery, and one
of the three is sprout, which has never once in fifty-eight runs come back
empty."

**In the Inquiry rail** — *ask my record*, *research outside*, *trial*,
*comparison*, *synthesis*, each with its own why.

**In the anatomy** — three organs marked UNBUILT TISSUE: Archive Circulation,
Publication / Exchange, Instrument Commands. All read "Nothing yet. It does not
exist," tests "none — unbuilt." Four Story options are disabled with "later."

**Standing badges** — the Bench header reads *prototype*; the Investigation
card reads *In trial use — not yet relied on.*

**One presentational leak**: the dashed-border idiom that means *unbuilt* is
also used on things that work — the Library status chips, the Bench keep-box,
the part editor.

---

## 4. Where a model call can start

Fifteen routes reach a model. **Two of them tell you first.**

| Disclosed before firing | Where |
|---|---|
| `/api/inquiry/<iid>/read` | `readCost()` — one model call, lane, model |
| `/api/jobs` **mode `deep` only** | `askDeep()` — lane, model, "N + about M per idea" |

| Fires with no lane, model or price | Started by |
|---|---|
| `/api/jobs`, every other mode | **Run it** |
| `/api/upload` | **pasting or dropping a file anywhere on the page** |
| `/api/bench/open` · `/build` · `/concept` · `/concept/names` | Bench buttons |
| `/api/library/support` | "Ask: what bearing does the span have on this claim?" |
| `/api/map/roads/suggest` · `/api/map/route/analyze` | Map buttons |
| `/api/clinic/disagree` | Clinic |
| `/api/keeper/close` · `/retry` | Keeper |
| `/api/keeper/renarrate` | **nothing — no door exists** |

Not disclosed anywhere in the app: the SMTP notification on job completion, and
the provider-side web search that sprout, etymon, refract and verify trigger.

---

## 5. Keyboard

| Chord | Where | What |
|---|---|---|
| `⌘⇧P` | writing room | workup on the whole draft |
| `⌘⇧⏎` | writing room | workup on this paragraph |
| `Esc` | writing room | closes the ask panel, then the workspace |
| `Tab` / `⇧Tab` | writing room | indent / outdent, one undo step |
| `Esc` then `Tab` | writing room | leaves the field instead of indenting |
| `Enter` | doc search, warp note | submit |
| `Enter` / `Space` | anatomy | open an organ |
| arrows · `PgUp` · `PgDn` · `Home` · `End` · `0` · `=` · `+` · `-` | overworld | pan and zoom |

`⌘⇧T` is deliberately **not** used: it is Reopen Last Closed Tab in Safari and
Chrome, and the page cannot prevent it.

---

## 6. Where the same word means two things

Full list in the census §5.1. The four that cost a reader the most:

1. **Map** opens a page titled **Trails**; the thing actually called Map is one
   link deeper and has four names.
2. **Library** in the nav is Documents; the Library that About describes is the
   concept shelf, which owns every `library-*` id and is also *the shelf* and
   *the Lexicon*.
3. **Room** is five different objects.
4. **Wordicon** is still user-facing in `manifest.json` and in the overworld's
   fallback string.

---

## 7. What a first-time reader meets, in order

Standing at Home having typed nothing:

1. A sentence: *Continue where your thinking left off.*
2. Cards for real objects, each openable as itself.
3. A ruling band that is empty when there is nothing to rule.
4. A box to bring something in, and three doors beside it.
5. Below that: Recent, the shelf, the Rooms, the Library, the constitution.

Nothing on that page calls a model. The first model call happens when the
person presses **Run it** — or, today, when they paste an image anywhere on the
page.
