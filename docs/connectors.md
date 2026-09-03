# Connected instruments — how to use Open Case and EthicalAlt with Nikodemus

Block 107 (`docs/adr-federation.md`). Manual pull only. Nothing here polls,
refreshes, investigates, or calls a model.

## The page

`/investigation` (behind the pairing gate, like everything). It has the
registry of instruments, the import controls, the depositions in custody,
and the Investigation Rooms. Home's chooser sends you here when you paste
a recognized Open Case or EthicalAlt URL, or when you choose "Look in
EthicalAlt", "Search Open Case's cases" or "Create an Investigation Room"
for a name — the page pre-fills the form and waits for your press.

## Registering an instrument

Register with a connector id, the producer (Open Case or EthicalAlt), the
base URL, and — for Open Case — a credential reference.

- The base URL is the whole network permission: an import reaches that
  origin plus the producer's contract path and nothing else. A deployed
  origin must be `https://`. Plain `http://127.0.0.1:PORT` is allowed only
  when the connector is marked as a development endpoint.
- The credential reference is a name in the server's environment, such as
  `env:OPEN_CASE_API_KEY`. The value is read when a request is made and is
  never stored, shown, or logged. Set it where the Nikodemus server starts
  (its `.env` is already outside the record and outside git):
  `OPEN_CASE_API_KEY=open_case_…` (an Open Case investigator API key minted
  by its `POST /api/v1/auth/keys` behind the admin secret). EthicalAlt's
  read routes need no credential.

## Pinning the trusted public key

Nothing from an instrument verifies until you pin its public key on the
connector — out of band, from the operator of that instrument, never from
a package.

- Open Case: the value of `OPEN_CASE_PUBLIC_KEY` in the Open Case server's
  environment (a base64 SPKI DER, 44 bytes). Its fingerprint appears in
  every export as `signature.trusted_key_id`; the page shows the same
  fingerprint for a pinned key so you can compare.
- EthicalAlt: the public half of `EXPORT_ED25519_PKCS8_DER_B64` (or, when
  that is unset, `PERIMETER_ED25519_PKCS8_DER_B64`). Its
  `GET /api/profiles/export-key` returns the fingerprint only; the key
  itself comes from the operator. To derive it locally on the EthicalAlt
  host: `node -e "const c=require('crypto');const k=c.createPrivateKey({key:Buffer.from(process.env.EXPORT_ED25519_PKCS8_DER_B64,'base64'),format:'der',type:'pkcs8'});console.log(c.createPublicKey(k).export({type:'spki',format:'der'}).toString('base64'))"`.

Fingerprint: `ed25519:sha256:` + sha256 of the raw 32-byte public key.
Pinned keys live in `local_state/federation/connectors.jsonl` (appended
events, projected at read). Unpin to retire a key; packages that name it
will no longer verify.

## Importing

- By id: an Open Case case UUID, or an EthicalAlt profile slug.
- By URL: a URL of the configured origin whose path is a case or a profile
  (`/cases/<uuid>`, `/api/v1/cases/<uuid>`, `/profile/<slug>`,
  `/api/profiles/<slug>`). The URL is only recognized; the fetch goes to
  the connector's base URL and contract path.
- From a package in hand: paste the JSON the producer gave you; the exact
  bytes go through the same chokepoint and the same pinned keys.
- "Locate" asks the instrument for its own list (Open Case:
  `/api/v1/cases/exportable`; EthicalAlt: `/api/profiles/index`) and
  imports nothing.

What arrives is kept byte for byte under `local_state/library/blobs/<sha256>`
and recorded in `local_state/federation/depositions.jsonl`; a verified
package also gets a derived representation under
`local_state/federation/reps/`. The same bytes twice: an import event and
nothing else. Different bytes for the same object: a new version, linked
to the prior, `supersession: unknown` until the source declares it or you
rule it.

## Verifying

Each row says verified or not, under which key, and why not. "Re-verify"
checks the stored bytes against the connector's current pinned keys and
writes nothing. "Exact bytes" opens the package as received.

## The Investigation Room

Create a room, add depositions to it. Seats are separate and stay
separate: Open Case evidence; Open Case signals; EthicalAlt incidents and
profile; primary-source documents admitted here; organizational statements
and responses; counterevidence and disputes; documented gaps and
unavailable sources; owner rulings. Every item names its instrument, its
source-native id, its source link, its signature status, when it was
imported and when the source recorded it, the instrument's own label
(VERIFIED/REPORTED/ALLEGED/DISPUTED/CONTEXTUAL for Open Case, attributed to
its classifier; high/medium/low and the concern level for EthicalAlt,
attributed to EthicalAlt), and its status (current, legacy, unverified,
superseded?).

"Propose relationships" runs the one mechanical proposer: exact,
case-insensitive name matches between an EthicalAlt profile's names and
an Open Case subject or matched name. A proposal grants nothing. For each,
you declare a relationship kind (the same entity, affiliate of, parent of,
political committee of, recipient of), reject it, or leave it unresolved.
Nothing else can declare.

Convergence appears only after a declaration: one timeline of both
instruments' dated records for the declared pair, each row citing its
source record and carrying the instrument's own label, plus the pairs of
records that fall within 90 days of each other, in a mechanical sentence.
Why they might matter together is a proposal a model could make when
summoned — not built.

## When a producer is offline

An import or a check fails with its class — DNS or connection, timeout
(15 s), HTTP 401/403/404/409/429, 5xx, an HTML error page, not JSON,
oversized (over 8 MB), the credential unavailable — and nothing is
imported. It is never shown as "nothing found". Everything already in
custody stays readable, verifiable, and seated.

## Diagnosing

- "not pinned on this connector": pin the producer's public key.
- "credential_unavailable": set the referenced environment variable where
  the Nikodemus server runs, then restart it.
- "origin_refused": the URL is not on the connector's origin — register a
  connector for that origin if it is yours.
- "html_error_page" / "http_5xx": the producer's host answered with a page
  or an error — the producer is down or misdeployed; nothing was imported.
- "payload_sha256 does not match": the bytes changed in transit or were
  edited — the package is kept unverified; ask the producer for a fresh
  export.
- "the package says producer X but this connector is Y": you imported a
  package into the wrong connector.
- Open Case 409 "no seal": the case was never sealed; seal or snapshot it
  through Open Case's authenticated commands.
- Open Case `legacy`: a pre-2026-04-02 seal without an embedded payload;
  held as legacy, unverifiable from the export.

## What this block does not do

No commands toward either producer (investigate, refresh, snapshot, deep
research, receipt). No bulk synchronization. No model call. No polling.
