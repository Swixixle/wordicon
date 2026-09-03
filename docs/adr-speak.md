# ADR: Speak to Nikodemus — the first doorway that is not a keyboard

## Status

Built in block 106, 2026-09-03, on the reviewer's ruled direction
(backlog items 53, 55) after the read-only spike (report 54), and held
for inspection. Mac-local: the phone's microphone waits for the
trusted-LAN-HTTPS block and says so on its face. No Conversation, no
spoken replies, no camera, no screen — each is its own ruling.

## The governing law

Nikodemus may hear and see what the owner deliberately presents, but
capture is not interpretation, and interpretation is not memory until
the owner keeps it.

## What it is

A recording instrument beside the attachment doorway in "Bring
something in": **Speak to Nikodemus**. Its states are plain — Ready,
Listening, Transcribing, Review what Nikodemus heard, Sent, Discarded,
Failed — and its flow is the reviewer's: the owner presses; recording
begins only after that gesture (the microphone is opened inside the
press handler and nowhere else); the owner stops it visibly; a local
engine transcribes; the transcript appears in the existing text box and
remains editable; the owner may replay, correct, retry, discard, keep
the recording, or continue; continuing hands the box — the edited
transcript, never an invisible alternate — to the destination chooser
with provenance **spoken**; the chosen lane receives it with that
provenance and the transcription's identity beside it.

## The four layers, on this doorway

Captured: the recording, as bytes in the page's memory — nowhere else,
until Keep recording, which stores it byte-intact through the Media
wing's own ingest as the owner's recording. Extracted: the transcript,
with the engine's name and version, the model's name and file hash,
the compute type, and the vocabulary hint's count and hash — as a
transcript version of origin `locally generated` when kept, and as the
`speech` block on the input row or the open question when sent.
Interpreted: nothing on this doorway — the language model is never
called by it. Remembered: what the owner sends, where he sends it,
and, if he edited the words, the fact and the machine's own text beside
his (`edited: true`, `machine_text`), so a correction is never mistaken
for what the engine heard; a kept correction is a second transcript
version of origin `owner-corrected`, one cue, citing the machine's.

## The engine, and why it is primed with the shelf

faster-whisper (MIT) on the owner's machine, base.en int8 on the CPU,
decoding from memory. The spike (report 54) established the two facts
that decide this: plain transcription mutilates exactly the owner's
vocabulary — Nikodemus, his coinages, the clinical acronyms — and a
vocabulary hint drawn from the shelf's own accepted titles makes every
one of them exact, in his spelling, at half a second per sentence,
without leaking into sentences that contain none of them. So the
adapter reads the accepted titles from the record at call time and
passes them as the engine's `initial_prompt`, and records that it did —
count and hash — on every transcript, because the hint biases: the
spike also showed a correction ("not parrot books") normalized toward
the known title. That cost is why the transcript is reviewed and edited
before anything receives it.

## Raw bytes, never a form

A multipart upload above 500 KB is spooled by Werkzeug to real,
unlinked files on disk during the parse (two were observed in the
spike); a raw request body is not. The transcribe and keep routes take
the recording as the raw body with its audio type, capped at 25 MB,
refuse multipart with 415 rather than parse it, and never touch
`request.files`. The suite pins the routes' source for this.

## What nothing does

Idle and disabled states write nothing. Listening writes nothing.
Transcribing writes nothing — not an input row, not a receipt, not an
encounter, not a file: the route's response says `recorded: false`.
Discard leaves nothing: the blob is released, the box cleared. A failed
transcription holds the audio in the page's memory and offers Retry,
Download, Discard — it is not quietly persisted. A reload forgets the
audio; the draft in the box survives as every draft does, in the
browser's own storage, and its spoken provenance with it, so the
provenance on a later send is honest; nothing restarts listening. The
model is fetched once, by a visible button in About & proof, into the
Hugging Face cache outside `local_state`; `transcribe()` never fetches
(`local_files_only`). An engine that is not installed is reported as
not installed — the server never substitutes the mock.

## The phone

On a page that is not a secure context — the phone over plain HTTP —
the browser exposes no microphone API at all. The control is disabled
and says: "Speaking needs a secure page. On this Mac open
http://127.0.0.1:8420; on the phone it waits for the trusted-LAN-HTTPS
block." That block is separate and comes before any phone capture.

## Names

Item 49's narration lane keeps "Talk it" as its historical and internal
name; its visible control will be "Read aloud". The microphone is
"Speak to Nikodemus". The later two-way session is "Conversation".

## Proofs (block 106)

An unpaired client cannot reach the transcribe or keep routes; nothing
records before the press (the microphone is opened only inside the
press handler — pinned in source and watched in the browser); idle,
disabled, listening, transcribing and discard leave the store
byte-identical (hashed in the suite and by the journey runner); raw
audio is absent from disk and the Vault unless Keep recording was
chosen (no temp-ish file, no blob); the editable box is exactly what
reaches the chooser (typed and spoken versions of one sentence receive
the same destinations); a transcription failure neither loses nor
persists the recording; no external provider exists on the path
(`external: false` on every record, no network in the engine); no
judgment, receipt or encounter is created by transcribing; a reload
cannot restart listening; multipart is refused; the engine's identity
and the vocabulary hint ride on the input row, the open question, and
the kept transcript; the anatomy's Sensory Tissue says what is built
and what is not.

## Amendment (block 106b) — the ear, governed

The reviewer provisionally accepted block 106 and ruled on the two
questions report 55 raised, plus a security check. This amendment is
those rulings, built.

**The order of standing.** "Newest 39" is rejected as a permanent
vocabulary rule: newness has nothing to do with pronunciation
importance. The engine is told, in order: (1) the visible name and the
words the owner declared it must hear right; (2) the names of what he
has open — a concept, a Room, a document, a work, an attached artifact
— sent by the page as ids only and resolved from the record, so a name
never comes from the request; (3) the shelf titles he explicitly pinned
for speech, by exact title, kept by the entry's id; (4) the shelf as
space remains, in a deterministic order that is not newness: rarest
first under the engine's own tokenizer (tokens per letter — a coinage
or an acronym is many pieces, a familiar word is one), ties
alphabetical, and plainly alphabetical when there is no model on the
machine. The manifest names which rule ran.

**The cap, in the engine's tokens.** Building this exposed a defect in
block 106's cap: 700 characters was calibrated to ordinary titles, and
Whisper keeps only the LAST 223 tokens of its prompt. Ordered by rarity,
the real shelf's coinages filled 715 characters with 251 tokens, and the
front of the hint — "Nikodemus" and the owner's declared words, the
highest-standing tier — fell off while the hint looked whole: every
habitat word was misheard again. So the cap is now 190 of the engine's
own tokens when its tokenizer is on the machine to count them (the
manifest records the count), characters only when nothing can count;
and a shelf title costing more than 12 tokens (a gloss, a foreign
script) is left out of the fallback and listed, while the owner's own
tiers are never dropped for cost, only for the cap. With that, the real
shelf's ear holds the name, the owner's words and about thirty of his
rarest titles, and every habitat phrase transcribes exactly again.

**The manifest.** A count and a hash cannot reconstruct why the engine
heard a word one way, so every transcript cites a content-addressed
hint manifest: the exact terms in the order told, each with its tier
and its source id (`brand:config/brand.json`, `declared:owner`,
`context:room:<id>`, `pinned:<id>`, `shelf:<id>`), what did not fit
under the cap, the frame, the rule, and the model whose tokenizer
ordered the fallback; its name is the sha256 of its own canonical
body. Transcribing still writes nothing: the manifest is written once,
under `local_state/speech_hints/`, at the moment the transcript enters
the record — Send or Keep — from the server's own copy of the
transcription, or from the page's copy only when it hashes to the sha
it claims. A row never cites a manifest that is not on disk. It reads
back at `/api/speak/hints/<sha>`.

**Events, not a rewrite.** The declared words and the pinned titles are
appended events — declare, undeclare, pin, unpin — with the owner's
clock on each; the projection (`speech_vocabulary.json`) is a plain
file rebuilt from them and says so. A block-106 file, which was
rewritten in place, is migrated into events by the owner's next save,
each migrated word noted as such.

**The model, recorded.** The 148 MB fetch is acceptable provided its
exact revision, hash, source and license are recorded. `fetch_model`
now records what arrived (`speech_models.jsonl`): the source URL, the
hub revision the snapshot is kept under, every file's size and sha256,
the composite hash the transcripts cite, and the license as the model
card in the snapshot states it (or "unstated in the cache", honestly);
an already-cached model is recorded as observed, without the network.
The cache itself stays outside `local_state` and the Vault, replaceable;
a replaced cache reads as unrecorded, because the record is keyed by
the file hash.

**The body, before a byte.** "Doesn't spool to disk" must not become
"will absorb unlimited RAM." Pairing is answered by the gate before any
body is read; then the type must be audio (multipart and anything else
refused with 415), the length must be declared (411) and within the
hard cap (413), and a deadline is set on the socket — all before a byte
is read into memory; then a bounded read that stops at the cap whatever
the header claimed, drops a body that trickles past thirty seconds
(408), and refuses one shorter than it declared (400).

**The correction law, on a specimen.** The parrot-books result is a
fixture now: where the owner says "not parrot books", the engine hears
the shelf title he was contrasting against. Pinned: what the engine heard stays visible beside the
owner's edit (the review line is painted from the transcription only,
never from the box); the owner-edited transcript is what is sent; the
record never claims the engine heard the correction (the machine's
version carries the machine's words, the owner's version the owner's,
each citing the manifest); and editing alone retrains nothing — the
instrument cannot reach the ear's settings, and no vocabulary event is
appended by a correction. A later, optional **Teach this correction**
could add a pronunciation or phrase preference by a visible act; it is
named here and not built.
