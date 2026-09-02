# ADR: The medical wing — Room One

## Status

Ruled by the owner 2026-09-02; the reconciled Room One proposal became
the build order with one correction (below). Vertical slice only: one
room, no bulk ingestion, no patient-specific decision support.

## The rulings

Room One is **Adult Ventilator Liberation: Readiness, SBTs, and
Extubation** — chosen because it naturally forces the separation the
wing exists for: hospital policy and department procedure,
professional guidance, current versus retired sources, independent
studies, device documentation, and the owner's own operational
judgment, without ever needing a patient in the question.

The adapters are **two explicit, separately versioned extractors** —
`pdf_text_v1` and `docx_text_v1` — never a shared "universal
extraction" revision. Same bytes plus the same extractor identity
produce the same representation and the same anchors; a future
extractor revision creates a NEW representation and never rewrites an
old one. Scanned PDFs (no extractable text layer) are refused with a
visible finding; OCR is a later, separately versioned adapter.

## The PHI non-retention law (constitutional amendment, owner's wording)

When an input appears to contain patient-identifying or
patient-specific clinical information, Wordicon refuses it before
model transmission and before any persistent write. It may preserve
only a content-free refusal event: time, lane, and rule invoked. It
must not retain the query, excerpts, extracted names, reversible
derivatives, fingerprints, hashes, results snapshots, Keeper packet
material, logs, or Vault copies. Detection is heuristic and cannot
guarantee identification of every case; therefore medical lanes are
designed not to solicit patient-specific information in the first
place.

The boundary applies to questions AND uploaded documents. V1
explicitly accepts policies, guidelines, labels, manuals, and studies
— not charts, handoff sheets, screenshots of EHRs, or patient
records. This amends the normal raw-input custody law, correctly:
auditability does not require preserving material the system was
constitutionally forbidden to accept.

## The correction: what code may and may not conclude

Code may compute: which source roles are present; which expected
roles are absent; which sources are current, retired, superseded, or
unknown; which anchored passages were retrieved for the same
question; whether a citation belongs to the admitted room; whether a
claimed source version resolves. Placing two passages beside each
other does not mechanically prove they disagree — "these sources
disagree" is a semantic judgment, and it exists only as a model
PROPOSAL with exact passages attached or as an owner ruling. Absence
is always phrased as "No admitted source of this role is present" or
"No admitted source answered this question" — never as medicine
having no answer.

## Metadata may be unknown; it may never be invented

Every source keeps: role, issuing institution, title, publication
date (value or unknown), effective date (value, not applicable, or
unknown), review/expiration (value, not applicable, or unknown),
current/retired/superseded/unknown status, jurisdiction or facility,
population and clinical scope, acquisition source and retrieval date,
blob and representation identity, declared guideline family, declared
supersession relations. Extraction may PROPOSE values from the
document; identity, family membership, retirement, and supersession
become permanent only through the owner's visible ruling. The program
never fabricates a date, status, scope, family, or relation to
complete an import form. Guideline-family identity obeys the
concept-first identity law: family membership is ruled, never derived
from a title match.

## Ask This Room v1: questions, never orders

In: what does this policy say; what does the current guideline say;
what does the label say; where were different passages retrieved for
the same question; what is absent from this room; which source is
retired or older; show the exact passages. Out, refused by design:
what should I do for this patient; which treatment should I choose;
is this patient safe; can I override an order or policy. The lane
shape — questions about admitted documents, never about patients —
is the primary PHI control; the heuristic screen is the backstop and
says so.

## The ruled build order

1. PDF and DOCX custody adapters. 2. Medical-source metadata and
declared relationship records. 3. One Adult Ventilator Liberation
room. 4. Ask This Room v1. 5. Medical-specific acceptance and
sabotage battery. 6. Real RT use in shadow mode. 7. Only then
additional topics or bulk ingestion.

## Rights

Personal-corpus ingestion of lawfully accessed material is personal
use. Hospital-restricted material stays local and out of every public
artifact. Any future product that redistributes third-party guideline
text is a licensing conversation that has not happened.
