# Golden depositions (block 107)

Signed packages produced by the REAL producer code — Open Case's
`routes/export.py` (`GET /api/v1/cases/{id}/export`, Open Case at
`4dc1709`) and EthicalAlt's `server/services/profileExportV2.js`
(`GET /api/profiles/:slug/export/v2`, EthicalAlt at `1a71460`) — against
sanitized, invented material ("Exemplar Holdings", `example.gov` /
`example.org` URLs): no real company, no real record, no production
database. The PUBLIC keys they were signed with are beside them; the
private keys were generated for these fixtures and are not in any
repository. The Nikodemus suite verifies these packages under the
pinned public keys — the interoperability proof: Node-signed and
Python-signed packages, one verifier.

- `open_case.exemplar.deposition.json` — a self-contained `open-case-full-4`
  seal (3 evidence rows incl. a documented absence, 1 signal, 4 source
  checks with all three statuses, 2 gaps), signed by `open_case.seal.v1`
  under `open_case.fixture.pub.b64`. The producer's epistemic labels are
  as its classifier assigned them to the fixture rows — including the
  `gap_documented` row labeled ALLEGED, which is Open Case's own
  behavior and is preserved unchanged here on purpose.
- `open_case.exportable.json` — the listing route's answer.
- `ethicalalt.exemplar.deposition.json` — a deep-research profile export
  v2 (4 incidents across 2 categories, one capped; one incident without
  a source URL; one without a date; an allegation with response Type 3;
  researcher gaps), signed by `ethicalalt.export.v2` under
  `ethicalalt.fixture.pub.b64`.
- `ethicalalt.legacy.deposition.json` — a thin legacy profile: signed,
  `research_depth: legacy`, no incidents, the `no_deep_research` gap.

These prove interoperability of the contract. They do not prove
production connectivity: the real deep-research profiles live only in
EthicalAlt's production database, and the real cases in Open Case's.

W1 (adr-extraction, 2026-10-16) adds the third producer's golden package:
`deflate.exemplar.deposition.json`, signed by the deposition module added
to the owner's deflate-lens 0.15.2 tree (`../producers/make_deflate_fixtures.mjs`
carries its canonicalization and signing verbatim — the generator and
its test-only key live there because THIS directory is scanned against
holding private key material); the fixture is the contract, and a drift
in either side's canonicalization fails the W1 suite block by name. The key beside it is test-only. The payload's
`claims.run.jcs_exercise` carries the numbers and strings RFC 8785 is
touchiest about, so the fixture is also the cross-language
canonicalization proof.
