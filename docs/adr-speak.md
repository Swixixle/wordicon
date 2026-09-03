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
