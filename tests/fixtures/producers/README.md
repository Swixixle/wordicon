# Fixtures of the producers' contracts at the pinned revisions

These are NOT the golden depositions (`../federation/`, the package
contract `nikodemus.deposition.v1`, which at the pinned revisions neither
producer's main serves — see `scripts/producers.py` `PACKAGE_CONTRACT`).
These are fixtures of what each producer's MAIN branch actually serves, in
the shapes its source builds, read from the owner's checkouts with
read-only git plumbing on 2026-09-16:

- EthicalAlt `1a71460a9bbae62124f9cf774f25f4c05c0b1f61` (main = origin/main, 2026-04-24)
- Open Case `4dc17090feb9915204070e9fdd65fcc0d2813867` (origin/main, 2026-07-12)

The mock producer (`tests/journeys/mock_producer.py`) serves those
contracts from invented material ("Exemplar Holdings", `example.org`);
nothing here is a real company, a real record, or a real key.

## Keys (test-only)

`ethicalalt.receipt.key.pkcs8.b64` / `ethicalalt.receipt.pub.spki.b64` and
`open_case.snapshot.key.pkcs8.b64` / `open_case.snapshot.pub.spki.b64` —
Ed25519 keypairs generated for these fixtures, in the encodings the
producers use (PKCS8 DER for the private key, SPKI DER for the public;
EthicalAlt's receipt reply carries the SPKI as base64url). They are in the
repository on purpose: the mock signs with them and the suite pins the
public halves. They sign nothing real and must never be pinned on a
connector to a deployment.

## EthicalAlt's canonicalization, proven against the producer's own bytes

`make_ethicalalt_fixtures.mjs` copies `stableStringify` verbatim from
`server/services/investigationReceipt.js:21-31` at the pinned revision
and writes:

- `ethicalalt.stable-stringify.vectors.json` — inputs and the exact string
  the producer signs for each: whole floats, exponents, tiny numbers, big
  integers, escapes, non-ASCII, U+2028, a lone surrogate, key order by
  UTF-16 code units (an astral key sorts before U+FFFF), nesting, empties.
  `scripts/producers.stable_stringify` must match every one byte for byte
  (`_check_producer_contracts`); the sabotage pass swaps it for
  `json.dumps` and the check fails by name.
- `ethicalalt.receipt.node-signed.json` — one receipt reply in the route's
  shape, signed by `node:crypto` the way `signReceiptBody` signs (Ed25519
  over the UTF-8 bytes of `stableStringify(receiptBody)`, `ed25519:` +
  base64url), with `public_key` as `getReceiptPublicKeyB64Url` emits it.
  The Python verifier accepts it under the pinned key, refuses it once a
  field changes, and reports whether the reply's own key is the pinned one
  without ever trusting it.

Re-generate with `node tests/fixtures/producers/make_ethicalalt_fixtures.mjs`
(Node 22 was used); the vectors must not change unless the producer's
function does.

## What these prove, and what they do not

They prove that the adapters implement the producers' contracts as their
source defines them, and that the verifiers reproduce the producers'
signing. They do not prove that any deployment runs these revisions: live
starts stay disabled until the owner records that ruling on the connector.
