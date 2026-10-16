// The golden Deflate deposition, made by the producer's own canonicalization
// and signing code — `canonicalize` and the signing core of `signedEnvelope`
// copied verbatim from the deposition module added to the owner's Deflate
// tree (deflate-lens 0.15.2 + server/deposition.js, W1 of
// docs/adr-extraction.md, 2026-10-16; stock 0.15.2 and origin/main e25f7c2
// serve no deposition routes). The private key beside this file is a
// test-only key; nothing here is a real key, a real transcript or a real
// reading.
//
//   node tests/fixtures/producers/make_deflate_fixtures.mjs
//
// It lives HERE, beside the other producers' generators and test keys,
// because the federation fixtures directory is scanned by the suite and
// may hold no private key material and no key-handling code; the signed
// outputs are written there, the key stays here.
//
// Writes into ../federation/ (the signed outputs) and beside this file (the key):
//   deflate.exemplar.deposition.json   one signed nikodemus.deposition.v1
//                                      package in exactly the shape the
//                                      route serves — the Python verifier
//                                      (scripts/federation.py, RFC 8785 via
//                                      the jcs package) must accept it under
//                                      the pinned key, accept it again with
//                                      every object's keys reordered, and
//                                      refuse it once a payload byte changes
//   deflate.fixture.pub.b64            the raw 32-byte public key, base64 —
//                                      what the owner would pin
//   deflate.fixture.key.pkcs8.b64      the test-only private key (reused on
//                                      re-runs so the fixture is stable)
import { createPrivateKey, createPublicKey, generateKeyPairSync, sign, createHash } from 'node:crypto';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));

// ---- copied verbatim from server/deposition.js (deflate-lens 0.15.2 + W1) ----
function canonicalize(v) {
  if (v === null || typeof v === "boolean" || typeof v === "string") return JSON.stringify(v);
  if (typeof v === "number") {
    if (!isFinite(v)) throw new Error("a non-finite number cannot be canonicalized (RFC 8785)");
    return JSON.stringify(v);
  }
  if (Array.isArray(v)) return "[" + v.map(x => (x === undefined ? "null" : canonicalize(x))).join(",") + "]";
  if (typeof v === "object") {
    const keys = Object.keys(v).filter(k => v[k] !== undefined).sort();
    return "{" + keys.map(k => JSON.stringify(k) + ":" + canonicalize(v[k])).join(",") + "}";
  }
  throw new Error("cannot canonicalize a " + typeof v);
}
const sha256hex = buf => createHash('sha256').update(buf).digest('hex');
// ---- end of the verbatim copy ----

// the test key: made once, then reused so the fixture bytes stay stable
const FED = join(HERE, '..', 'federation');
const keyFile = join(HERE, 'deflate.fixture.key.pkcs8.b64');
let privateKey;
if (existsSync(keyFile)) {
  privateKey = createPrivateKey({ key: Buffer.from(readFileSync(keyFile, 'utf8').trim(), 'base64'), format: 'der', type: 'pkcs8' });
} else {
  const pair = generateKeyPairSync('ed25519');
  privateKey = pair.privateKey;
  writeFileSync(keyFile, privateKey.export({ type: 'pkcs8', format: 'der' }).toString('base64') + '\n');
}
const pub = createPublicKey(privateKey);
const raw = pub.export({ type: 'spki', format: 'der' }).subarray(-32);
writeFileSync(join(FED, 'deflate.fixture.pub.b64'), raw.toString('base64') + '\n');
const keyId = 'ed25519:sha256:' + sha256hex(raw);

// An invented run — "The Exemplar Hour", example.org — shaped exactly as the
// route builds it: the claims export whole, plus the retained transcript.
// claims.run.jcs_exercise carries the number and string forms RFC 8785 is
// touchiest about, so the committed fixture proves the Python side matches
// the producer's bytes on exactly those.
const transcript = "HOST: Welcome back to The Exemplar Hour — it’s 15% better today.\nGUEST: “Half a million,” she said. 1.5 degrees. Done.\n";
const payload = {
  schema: 'deflate-lens/deposition@1',
  claims: {
    schema: 'deflate-lens/claims@0.7',
    exportedAt: '2026-10-16T00:00:00.000Z',
    generator: 'deflate-lens local app',
    run: {
      id: 'r_fixture0001', title: 'The Exemplar Hour', kind: 'transcript', parseMode: 'transcript', example: true,
      source: { url: 'https://example.org/exemplar-hour', label: 'Exemplar Hour', date: '2026-10-01' },
      sourceIdentity: { state: 'needs_confirmation', match: { method: 'title-lookup' } },
      transcript: { updatedAt: '2026-10-02T00:00:00.000Z', characters: transcript.length, sha256: sha256hex(Buffer.from(transcript, 'utf8')), parseMode: 'transcript', earlierVersions: [{ sha256: 'a'.repeat(64), chars: 100, replacedAt: '2026-10-01T12:00:00Z' }] },
      speakers: [
        { key: 'HOST', name: 'Avery Exemplar', namedBy: 'identification', how: 'named in the episode listing', inText: true },
        { key: 'GUEST', name: 'GUEST', namedBy: 'unnamed', how: 'no one says a name', inText: true },
      ],
      jcs_exercise: { big: 1e21, tiny: 1e-7, whole: 10, neg: -1.5, text: 'quotes “curly” and straight "x", emoji 😀, accents café' },
    },
    passagesHeld: [{ id: 'p002', title: 'The held half', turnStart: 3, turnEnd: 4, reasons: ['quote not found in the text'] }],
    passages: [{
      id: 'p001', title: 'The fifteen percent claim', turnStart: 1, turnEnd: 2, speakerNames: ['Avery Exemplar', 'GUEST'],
      analyzedAt: '2026-10-02T01:00:00Z', analyzedBy: 'fixture', model: 'fixture-model', readingRev: 1, earlierReadings: 0,
      basedOn: { inputHash: sha256hex(Buffer.from(transcript, 'utf8')) }, fidelity: 'faithful',
      quoteCheck: { matched: 1, quotes: 2 }, stale: [],
    }],
    claims: [{
      id: 'p001-c1', passageId: 'p001', speaker: 'Avery Exemplar', speakerKey: 'HOST', text: 'It is 15% better today.',
      type: 'claim', displayType: 'Checkable claim', status: 'receipt', turns: [1, 1], provisional: ['speaker preparation is unresolved'],
      relations: { supports: 0, contradicts: 1, mentions: 0, unstated: 0 },
      receipts: [{ rid: 'rc1', kind: 'link', url: 'https://example.org/report', relation: 'contradicts', relationBy: 'a person', at: '2026-10-03T00:00:00Z' }],
      searches: [], candidatesPending: 0, rejections: [],
    }],
    patterns: [],
  },
  transcript: {
    included: true, text: transcript, characters: transcript.length,
    sha256: sha256hex(Buffer.from(transcript, 'utf8')),
    note: "the run's transcript as saved now; claims.run.transcript names the original input's hash and earlier versions by hash",
  },
};

const canonical = Buffer.from(canonicalize(payload), 'utf8');
const envelope = {
  schema: 'nikodemus.deposition.v1',
  producer: { id: 'deflate', display: 'Deflate Lens', version: '0.15.2+deposition' },
  object: { type: 'reading_run', id: 'r_fixture0001' },
  recorded_at: '2026-10-16T00:00:00Z',
  payload_media_type: 'application/json',
  payload_sha256: sha256hex(canonical),
  signature: { algorithm: 'Ed25519', method: 'deflate.deposition.v1', trusted_key_id: keyId, value: sign(null, canonical, privateKey).toString('base64') },
  gaps: [
    { kind: 'earlier_transcript_versions', detail: '1 earlier text version(s) are named by SHA-256 in claims.run.transcript.earlierVersions; versions edited before 0.12.1 kept only the hash, not the text' },
    { kind: 'source_audio_not_retained', detail: 'the uploaded recording was deleted after transcription, by design; its name, size and SHA-256 are in claims.run.import.file' },
  ],
  source_times: [],
  payload,
};
writeFileSync(join(FED, 'deflate.exemplar.deposition.json'), JSON.stringify(envelope, null, 1) + '\n');
console.log('wrote deflate.exemplar.deposition.json (payload_sha256 ' + envelope.payload_sha256.slice(0, 12) + '…), pub, key');
