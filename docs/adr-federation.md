# ADR: Connected instruments — Open Case and EthicalAlt as a federation, not a merger

## Status

Built in block 107, 2026-09-03, on the reviewer's build brief relayed by
the owner (backlog item 60), and held for inspection. Read-only scope:
manual pull, verification, custody, one Investigation Room, owner-ruled
identity, one mechanical convergence. Every command capability
(investigate, refresh, snapshot, deep research, receipt) is deferred and
shown as unbuilt.

## The decision, and why

Nikodemus becomes the owner-governed place where material from his
specialist instruments can be preserved, connected, questioned and ruled
on — without absorbing the instruments. Open Case keeps its
public-record adapters and pattern engine; EthicalAlt keeps its profiles
and research method; each keeps its database, its repository, its
interface, its vocabulary and its signing key. Nikodemus verifies and
preserves what they produce, connects their records without erasing
their distinctions, and lets the owner decide what a convergence means.

Federation was chosen over merger because the standing decision on the
owner's systems — "borrow one, never unify six" — still holds: a shared
database or a shared engine would make Nikodemus the owner of rules and
methods it did not write and cannot answer for, and it would flatten
vocabularies that mean different things (an Open Case VERIFIED is a
domain rule about a government record; an EthicalAlt `high` is a research
confidence about a source). The integration boundary is therefore a
versioned evidence-export contract — a package the producer signs and
Nikodemus verifies under a key pinned out of band — plus, later and
separately, explicit command capabilities.

## What a deposition is, and is not

A deposition is the exact bytes a producer handed over, held in custody
with their content hash, the connector they came through, the time they
were received (Nikodemus's clock, `received_at`) and the times the
producer stated (`source_times`, each marked `source_stated`), the
verification result and the id of the key it was verified under, and a
rebuildable representation beside it. It is testimony by a named
witness, kept whole. It is not a Nikodemus finding, not a merged
record, and not a claim about anything but what the producer said.

The outer envelope, `nikodemus.deposition.v1`, is a transport and
custody shape only: producer id and revision, the producer's declared
constitution version, the object type and its source-native id, the
producer's own times, subject references, the payload's media type and
canonicalization, the payload's sha256, the payload itself, the
producer's stated gaps, and a signature block that names the algorithm,
the producer's method, the canonicalization, the trusted key's
fingerprint, and the value. The producer's native schema lives inside
`payload` unchanged; Nikodemus dispatches on the producer and parses by
that schema. No universal ontology was built.

## The signature trust model

Verification uses a key the owner pinned on the connector, out of band.
A key inside a package — anywhere — is ignored; a package whose
`trusted_key_id` is not among the pinned keys fails, and so does a
package whose payload does not hash to its `payload_sha256`, whose
signature does not verify, or whose envelope names an object other than
the one the signed payload carries. The two producers sign differently
and the difference is recorded, not papered over: Open Case's
`open_case.seal.v1` is Ed25519 over the UTF-8 hex of the sha256 of the
RFC 8785 canonical payload (the stored seal, returned as stored, never
re-signed on read); EthicalAlt's `ethicalalt.export.v2` is Ed25519 over
the canonical bytes themselves. The key fingerprint all three systems
compute the same way is `ed25519:sha256:` + sha256 of the raw 32-byte
public key. Golden fixtures signed by both producers' real code verify
in the Nikodemus suite. A failed verification does not discard the
package: the bytes stay in custody, marked unverified, with nothing from
them seated as evidence. A legacy Open Case seal without an embedded
payload is returned by Open Case as exactly that and held here as
legacy, unverifiable from the export; no modern-looking package is
manufactured from it.

## The identity law

Names are not identities. Every record keeps a namespaced id
(`open_case:case:<uuid>`, `open_case:evidence:<uuid>` with the
run-stable `evidence_hash` beside it, `open_case:signal:<uuid>`,
`ethicalalt:profile:<slug>`, `ethicalalt:incident:<id>`), and external
identifiers the producer recorded (a bioguide id, an FEC committee id,
a docket or filing id) ride in the representation. A relationship
between records of different instruments is an explicit row with a
state — `proposed_same_entity`, then, by the owner only,
`declared_same_entity`, `affiliate_of`, `parent_of`,
`political_committee_of`, `recipient_of`, `rejected_match`, or
`unresolved`. This block's one proposer is mechanical: an exact,
case-insensitive name match between an EthicalAlt profile's names and
an Open Case subject or matched name, which proposes and never links.
A model may later propose; nothing but the owner's ruling declares.

## Absence, failure, and unknown

These never collapse: a source searched with evidence, a source searched
and empty (Open Case records a `result_hash` for it), a source that
could not be searched (no hash), a response that could not be parsed, a
source not searched, a gap the producer documented, provenance the
producer marks incomplete, and a legacy claim the current application
cannot verify. A producer that cannot be reached is a failure record
with its class — DNS or connection, timeout, HTTP 401/403/404/409/429,
5xx, an HTML page, not JSON, oversized, the credential unavailable — and
never an empty result; what is already in custody stays readable.

## Privacy and credentials

An outbound request carries the connector's configured origin, the
producer's contract path, the explicit object id, and a credential read
from the environment at request time. Nothing from the corpus — no
writing, no concepts, no Keeper entries, no transcripts, no medical
material, no behavioral records — is in a request, and the suite pins
this at the fetcher. The registry stores a credential reference
(`env:NAME`), never a value; stored errors are scrubbed of anything
credential-shaped; no key or credential appears in `local_state`, a
package, a page, a fixture, or a log.

## The network boundary

Only configured origins are ever fetched: a pasted URL is recognized by
origin and by the producer's own path shape, and an import reaches the
connector's base URL plus the contract path — never the pasted URL.
Deployed origins are HTTPS; plain HTTP is allowed only on loopback for a
connector declared as a development endpoint. Redirects are refused;
responses are bounded (8 MB) and must be JSON; a 15-second deadline
applies; the outcome classes above are recorded without bodies.

## Read-only, manual, and no automation

Every fetch is the owner's press. There is no polling, no scheduled
refresh, no ambient investigation, and no automatic comparison across
systems; a later monitoring switch would be visible, off by default,
and inspectable. Open Case's export route was built to be
side-effect-free — no view counter, no engine run, no proportionality
call, no re-investigation, no snapshot, no re-signing — and its tests
prove it; EthicalAlt's v2 export likewise reads and signs
deterministically, with no request-time clock inside the signed object.

## Custody and versions

The bytes go into the Library's blob store by content hash; the
deposition row records everything above; the representation is a
derived file named by the blob hash and the representation revision.
The same bytes imported again append an import event citing the
existing deposition and nothing else. Different bytes for the same
producer object become a new deposition linked to the prior, with
`supersession: unknown` — a changed hash proves only that the bytes
changed; supersession is declared by the source or ruled by the owner.

## Compatibility promises

Open Case's `/cases/{id}` and `/report` are untouched; the export is a
new authenticated route. EthicalAlt's v1 export and its receipt routes
are untouched; v2 is a new route and the v1 remains served. The envelope
is versioned; an unsupported schema, producer, object type, or method
is refused visibly.

## Known legacy limitations, stated

Open Case signals carry `signal_type`, not a pattern-rule id; rule ids
and versions live on pattern alerts inside sealed payloads of schema
`open-case-full-2` and later. Re-investigation in Open Case replaces
evidence and signal UUIDs; `evidence_hash` and `signal_identity_hash`
are the run-stable identities and are carried. Open Case's classifier
labels a documented absence ALLEGED and a Senate roll-call REPORTED as
recorded — preserved unchanged here, noted as the producer's behavior.
EthicalAlt's deep-research profiles exist only in its production
database; the repository's 313 committed profiles are legacy, so the
golden fixtures are sanitized and schema-faithful and do not prove
production connectivity. EthicalAlt records no source title, publisher
or date — those fields are null, not invented — and its concern-level
vocabulary varies across the corpus and is passed through as recorded.

## Deferred, explicitly

Commands (run an investigation, refresh adapters, take a snapshot,
refresh a profile, run deep research, generate a receipt) with their
envelope — connector, capability, explicit subject, minimal arguments,
the owner's invocation event, an idempotency key, requested-at, status,
the external id, the resulting deposition, an error class, no unrelated
context. Bulk synchronization. Model-assisted comparison as a summoned
doorway. Convergence beyond the one declared-link timeline. Code View
and Debrief as producers.

## Proofs (block 107)

The golden packages from both producers verify under the pinned keys;
a wrong key, a changed byte, a replaced signature, an embedded key, an
unknown schema or producer, a mismatched object id each fail by name;
the same bytes twice are idempotent; changed bytes are a new linked
version with supersession unknown; the fetcher refuses a foreign origin,
a redirect, an oversized body, an HTML page, non-JSON, and reports a
timeout, a 5xx and a missing credential as failures — never as empty;
documented gaps, source-native labels, the allegation/response pairing
and legacy standing survive import unchanged; two same-named entities
stay separate; nothing declares without the owner; a rejection or an
unresolved match produces no convergence; the original bytes are
byte-identical; no model is constructed on any path; nothing from the
corpus reaches a request; no credential reaches the store, a page, a
fixture or a log; reading works with the producer offline; the gate
holds.
