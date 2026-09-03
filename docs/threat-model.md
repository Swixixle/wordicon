# Threat Model — the system as it actually exists

Rewritten 2026-08-29 in the hardening pass, replacing the Phase 0 document.
The Phase 0 model was honest about a system that no longer exists: it
assumed no real private sources, no external model, and no interface. All
three assumptions are false today, and a threat model describing yesterday's
risks is worse than none — it reassures. This document describes the running
system. (The original Phase 0 text survives in git history.)

## 1. What the system is now

A Flask server on the owner's Mac serving a browser/PWA interface, holding a
REAL private corpus in `local_state/` — concepts, judgments, journals and
writing, imported documents and recordings byte-intact, transcripts, span and
time crossings, trails, works, and the append-only decision logs. A live
Anthropic lane (`ANTHROPIC_API_KEY` in `.env`) carries explicitly invoked
runs; review lanes may carry search queries. Email notifications, when
configured, send job completions through the owner's mail account. The code
is backed up to a private GitHub repository; `local_state/` and `.env` are
deliberately not.

## 2. What is being protected

Three things, in order: the corpus (private writing and judgment history —
the product itself), the API key (a wallet), and the integrity of the record
(append-only logs whose value is that nothing edits them silently).

## 3. Adversaries and failure modes, current

**A stranger on the same network.** The server binds LAN only when the owner
opts in (`WORDICON_LAN=1`); either way every corpus, media, export, mutation,
and model-spending route sits behind the access gate — default-deny, pairing
code via POST only, HttpOnly SameSite=Strict session cookie, per-device
revocation, master-secret rotation, a lockout brake on code guessing, no
CORS, cross-site state changes refused. **Residual risk, stated plainly:
transport is plain HTTP.** On the owner's home Wi-Fi this is acceptable; on
shared or hostile networks (hospital Wi-Fi included) an on-path observer can
read traffic even though the gate refuses them the routes. No clinical-grade
confidentiality is claimed. HTTPS or a private overlay (e.g. Tailscale)
is the named next step before any sensitive-network use.

**Disk failure, device loss, or the owner's own mistake.** The most probable
catastrophic loss. GitHub protects the CODE only. The corpus exists on one
disk. Export-with-manifest exists but is manual, unencrypted, and typically
lands on the same disk. **Encrypted backup AND RESTORE is authorized as the
next planning order and is not yet implemented** — until it lands, this is
the largest open risk in the system, named here so it cannot be mistaken for
handled.

**The model vendor lane.** Bounded payloads leave only through lanes the
owner explicitly invokes, on the owner's key; raw corpus browsing never
transits. What the vendor retains is governed by the vendor's terms, not by
Wordicon — the panel says so in those words. ADR-002's default-deny posture
survives in spirit: nothing is sent except what a summoned run carries.

**A malicious document or transcript inside the corpus.** Prompt-injection
via retrieved content: imported text is data, never instructions; the
library and media wings are constitutionally zero-model (enforced by tests
that poison the gateway and the network); model lanes receive bounded,
delimited material. Transcripts are additionally untrusted as REPRESENTATION:
they are labeled derivatives that can be wrong, and every quotation is
re-retrieved with drift shown.

**A compromised or curious paired device.** Any paired browser can read the
corpus and spend the key — pairing IS trust. Mitigations: the device list
with one-press revocation, rotation to sign out everything, and the pairing
code's short life (per server boot, POST-only, never in URLs or logs).

**The owner's key leaking.** `.env` is git-ignored, never printed by the
server, and the owned secret scanner runs in CI over every tracked file, so
the key cannot ride a commit unnoticed. Residual: any paired device and any
process on the Mac can read the environment; that is accepted for a
single-owner machine.

**Email notification leakage.** Job-completion mail carries titles through
the owner's mail provider. Accepted; content-bearing mail should stay
summary-thin.

**A connected instrument, or someone pretending to be one (block 107).**
The federation adds one outbound reader — the connector fetcher — and one
inbound door — the deposition import — and both are chokepoints. Outbound:
a request goes only to a registered connector's configured origin plus the
producer's contract path with an explicit object id; a pasted URL is
recognized, never fetched; deployed origins must be HTTPS and plain HTTP is
allowed only on loopback for a connector declared as a development endpoint;
redirects are refused (a producer that answers 3xx is a failure by name, so
the reader can never be steered to another host); the body is bounded at 8 MB
and must be JSON; a 15-second deadline applies; nothing from the corpus rides
along (the suite pins the request shape at the fetcher). Inbound: a package
verifies only under a public key the owner pinned on the connector out of
band — a key inside a package is ignored, so a forged package cannot carry
its own trust; the payload must hash to its declared sha256, the signature
must verify by the producer's declared method, and the envelope must name the
object the signed payload carries. A failed verification is not discarded:
the bytes stay in custody marked unverified and seat nothing. Credentials
never enter the record: the registry stores a reference (`env:NAME`), the
value is read from the environment at request time, stored errors are
scrubbed of anything credential-shaped, and the suite greps `local_state`,
pages, fixtures and logs for key material. Residual, stated plainly: a
compromised producer with a valid key can sign a lie — verification proves
who signed, never that it is so, which is why a deposition is testimony by a
named witness and not a finding; and a paired device can register a
connector, which is the same trust the pairing gate already extends.

## 4. What is explicitly not addressed yet

Encrypted transport (HTTPS/overlay) for Nikodemus's own pages (a connector to a deployed producer is HTTPS already). Multi-user anything — this is one owner's tool;
the moment a second user exists, most assumptions here expire. OS-level
compromise of the Mac itself — a keylogger or root malware defeats every
boundary above, and no application design changes that.

## 5. Standing invariants that double as mitigations

Append-only logs (tampering is visible as absence-of-history, not silence);
byte-intact originals with content addresses (substitution is detectable);
export manifests with checksums (a copy can prove it was not edited);
default-deny route gating proven by tests that attack it (12 gate mutations
caught at last run); encrypted, drill-proven corpus vaults in the standard
age format — sealed crash-consistently under a writers lock, verified by
real decrypt before completion, excluded of all auth material so a stolen
vault plus its secret still cannot impersonate a paired device, refusing
hostile archive members out loud rather than neutralizing them, with
generational retention that can never prune the newest drill-proven vault
(17 vault mutations caught at last run); and the wiring rule — every rendered surface must prove
its data arrived — so a starved surface reads as failure, never as an empty
corpus.
