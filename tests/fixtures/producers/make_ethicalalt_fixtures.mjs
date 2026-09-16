// Fixtures of EthicalAlt's RECEIPT contract, made by the producer's own
// canonicalization and signing code — copied verbatim from
// server/services/investigationReceipt.js at 1a71460a9bbae62124f9cf774f25f4c05c0b1f61
// (main = origin/main, 2026-04-24): `stableStringify` (lines 21–31) and the
// message/signature form of `signReceiptBody` (lines 62–69: Ed25519 over the
// UTF-8 bytes of stableStringify(receiptBody), "ed25519:" + base64url) and
// `getReceiptPublicKeyB64Url` (SPKI DER, base64url). The private key is the
// test-only key beside this file; nothing here is a real key or a real record.
//
//   node tests/fixtures/producers/make_ethicalalt_fixtures.mjs
//
// Writes, beside this file:
//   ethicalalt.stable-stringify.vectors.json  inputs and the producer's exact
//                                             bytes for them — the Python
//                                             re-implementation in
//                                             scripts/producers.py must match
//                                             every one, byte for byte
//   ethicalalt.receipt.node-signed.json       one receipt reply in the route's
//                                             shape ({receipt_id, signed_receipt,
//                                             signature, public_key, verify_url,
//                                             cached}), signed HERE by node:crypto
//                                             — the Python verifier must accept
//                                             it under the pinned key and refuse
//                                             it once a byte of the body changes
import { createPrivateKey, createPublicKey, sign } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));

// ---- verbatim from investigationReceipt.js @1a71460, lines 21–31 ----------
/** @param {unknown} val */
function stableStringify(val) {
  if (val === null || typeof val !== 'object') {
    return JSON.stringify(val);
  }
  if (Array.isArray(val)) {
    return `[${val.map((x) => stableStringify(x)).join(',')}]`;
  }
  const o = /** @type {Record<string, unknown>} */ (val);
  const keys = Object.keys(o).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(o[k])}`).join(',')}}`;
}
// ---------------------------------------------------------------------------

const priv = createPrivateKey({ key: Buffer.from(readFileSync(join(HERE, 'ethicalalt.receipt.key.pkcs8.b64'), 'utf8').trim(), 'base64'), format: 'der', type: 'pkcs8' });
const pubB64Url = createPublicKey(priv).export({ type: 'spki', format: 'der' }).toString('base64url');

// the values a JSON body can carry where JSON.stringify and a naive Python
// json.dumps disagree: whole floats, exponents, tiny numbers, big integers,
// escapes, non-ASCII, U+2028, a lone surrogate (parsed from JSON text), key
// order by UTF-16 code units (an astral key sorts before U+FFFF in code units
// and after it in code points), nesting, empties
const vectors = [
  null, true, false, 0, -0, 1, 1.0, 1.5, 100, 1e21, 1e20, 123456789012345680000, 1e-7, 0.000001, 0.0000001, 1e-10, 3.14159, -2.5e-8, 9007199254740993, 12345678901234567890,
  '', 'plain', 'quote " backslash \\ slash /', 'tab\tnewline\nreturn\rbackspace\bformfeed\f', 'control   del ', 'unicode é ü 日本 😀', 'line sep   para sep  ',
  JSON.parse('"lone surrogate \\ud800 here"'), JSON.parse('"pair \\ud83d\\ude00 ok"'),
  [], {}, [1, 'two', null, [3, { b: 2, a: 1 }]], { b: 1, a: 2, '': 3, 'é': 4, 'z': 5, 'Z': 6, '10': 7, '9': 8, '😀': 9, '￿': 10 },
  { receipt_id: 'e3b0c442-98fc-4c14-9afb-f4c8996fb924', subject: { brand_name: 'Exemplar Holdings', brand_slug: 'exemplar-holdings', ultimate_parent: 'Exemplar Holdings' }, incident_count: 4, category_summary: [{ category: 'labor', count: 2, overflow: 0 }, { category: 'environment', count: 2, overflow: 1 }], source_urls: ['https://example.org/a', 'https://example.org/b'], overall_concern_level: null, investigation_id: 'op_fixture' },
];
const outVectors = vectors.map((v) => ({ input: v, output: stableStringify(v) }));
// -0 stringifies as "0"; keep the input as the JSON text '-0' cannot be told from 0 after a round trip — note it
writeFileSync(join(HERE, 'ethicalalt.stable-stringify.vectors.json'), JSON.stringify({
  source: 'stableStringify, server/services/investigationReceipt.js:21-31 @1a71460a9bbae62124f9cf774f25f4c05c0b1f61, run under ' + process.version,
  note: 'input is the value as JSON; output is the exact string the producer signs for it. A verifier that does not reproduce output for input cannot verify the producer\'s receipts.',
  vectors: outVectors,
}, null, 1) + '\n');

// one receipt in the route's shape (routes/receipt.js:178-297 @1a71460): the
// body fields as buildReceiptPayloadFromProfileRow makes them, invented values
const receiptBody = {
  receipt_id: '7d3c1f2e-5a4b-4c6d-8e9f-0a1b2c3d4e5f',
  subject: { brand_name: 'Exemplar Holdings', brand_slug: 'exemplar-holdings', ultimate_parent: 'Exemplar Holdings' },
  investigated_at: '2026-09-01T10:00:00.000Z',
  generated_at: '2026-09-16T09:00:00.000Z',
  incident_count: 4,
  category_summary: [{ category: 'labor', count: 2, overflow: 0 }, { category: 'environment', count: 2, overflow: 1 }],
  source_urls: ['https://example.org/exemplar/labor-2025', 'https://example.org/exemplar/spill-2024'],
  source_count: 2,
  incidents_hash: '4a5b6c7d8e9f00112233445566778899aabbccddeeff00112233445566778899',
  data_source: 'deep_research+database',
  last_deep_researched: '2026-09-01T10:00:00.000Z',
  disclaimer: 'This receipt documents public records and credible reporting. It is not a legal finding. Sources are linked directly and independently verifiable.',
  methodology_url: 'https://ethicalalt-client.onrender.com/methodology',
  issuer: 'EthicalAlt / Nikodemus Systems',
  schema_version: '1.0',
  overall_concern_level: 'significant',
  investigation_id: 'op_node_signed_fixture',
};
const msg = Buffer.from(stableStringify(receiptBody), 'utf8');
const signature = `ed25519:${Buffer.from(sign(null, msg, priv)).toString('base64url')}`;
writeFileSync(join(HERE, 'ethicalalt.receipt.node-signed.json'), JSON.stringify({
  receipt_id: receiptBody.receipt_id, signed_receipt: receiptBody, signature, public_key: pubB64Url,
  verify_url: 'https://ethicalalt-client.onrender.com/verify/' + encodeURIComponent(receiptBody.receipt_id), cached: false,
}, null, 1) + '\n');
console.log('wrote', outVectors.length, 'vectors and one node-signed receipt; public key (SPKI DER base64url):', pubB64Url);
