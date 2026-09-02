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

## Amendment 2026-09-02: the gate is two gates (owner's ruling)

The first population attempt exposed that one screen was serving two
lanes, and confused ordinary clinical language with patient identity:
it refused "once the patient is on pressure support of 5 cm H2O" and
"verify patient name and date of birth" while admitting a hyphenated
case vignette. The owner rejected the builder's first re-cut as well
— "it still confuses clinical specificity with patient identity" — and
ruled the split below. The law above is unchanged; this is how it is
enforced.

**The question gate refuses patient-specific intent.** Ask This Room
is a policy-and-evidence lane, not clinical decision support, so it
refuses questions about a particular patient even when no
traditional identifier appears ("my patient failed an SBT — what
should I do", "the patient in bed 4 is hypotensive; can I extubate",
"a 65-year-old man on these settings — what treatment", "can I change
this patient's ventilator order"). Generic questions pass ("what does
the policy require before an SBT", "how does the current guideline
define readiness", "which admitted sources mention hemodynamic
instability"). This gate protects the lane's scope, not merely
identifiers.

**The document gate detects identifiers, not clinical prose.**
Guidelines, studies, policies and manuals necessarily contain
clinical language, so these MUST pass: "once the patient is on
pressure support", "when a patient presents with hemodynamic
instability", "verify patient name and date of birth", "the patient
will remain in bed 4 during the trial", and published or instructional
vignettes without explicit identifying information. Hard refusal
requires higher-signal material: an MRN, patient ID or account number
followed by a value; an SSN; a date of birth followed by an actual
date; a patient name paired with another record field; other
unmistakable chart-style identifiers. Bare words such as "patient
name", "date of birth", "bed" and "room" are not identifiers by
themselves. An institution's name is never PHI.

**Three outcomes, not pass/refuse.** *Admit*: no high-signal
identifier found, an allowed source role declared, and the owner
confirms it is a guideline, policy, study, label or manual — not a
patient record. *Held for inspection*: the material resembles a case
narrative or clinical note but carries no decisive identifier; it
stays in temporary memory only — nothing persisted, nothing sent to a
model, nothing in a Keeper packet, nothing in the Vault; the page
names the triggered rule and its location; the owner may cancel or
attest that it is a lawful reference document without patient
records, and the attestation is recorded on the declaration. Refusal
and review are different outcomes. *Refuse*: explicit identifier–
value combinations are present; no override in v1 — obtain a clean,
public, or properly de-identified copy; only the content-free refusal
event is retained.

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
