# Sweeps_Relief

## 1. What this is

Sweeps_Relief is a **local-first** toolkit for blocking sweepstakes-casino sites on your own devices and keeping a **tamper-evident** record of enforcement-related events. It does **not** phone home, track your browsing for analytics, or store policy or logs in a vendor cloud you do not control. Policy artifacts are **cryptographically signed** (Ed25519) so you—or someone reviewing an export—can check that the blocklist and signatures have not been quietly altered.

This repository holds the **enforcement-side** code: keys, signing, verification, exports (hosts/DNS/browser JSON), and logging primitives. It is one part of a three-repo pipeline (see [Architecture](#7-architecture)).

---

## 2. Status — what works today

| Component | Status |
| --- | --- |
| Python CLI (keys, policy build/sign/verify, exports, reports) | ✅ Working |
| Signed policy artifacts (`policy.json` + hash + signature) | ✅ Working |
| Tamper-evident event / log-bundle primitives (`sweeps_relief.logger`) | ✅ Library API; **no dedicated CLI yet** for sign/verify-bundle |
| macOS helper (`apps/mac-helper`) | ⚠️ Builds; install / privileged apply flow still WIP for general users |
| Chromium browser guard (`apps/browser-guard-chromium`) | ⚠️ Scaffold + tests in-repo; **not** a shipped store extension |
| Safari extension | ⚠️ Scaffold only |
| iOS companion | ⏸ Planned |
| Router-level DNS enforcement | ⏸ Planned |

Do not expect a one-click installer for non-developers yet.

---

## 3. Install (developers)

```bash
git clone <this-repo-url>
cd Sweeps_Relief
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

If `pytest` passes, the Python package and tests are wired correctly.

**Non-developers:** Sweeps_Relief is not yet packaged for easy install by people who only need blocking tonight. If you need help immediately, skip to [Quick protection](#4-quick-protection) below — the tools listed there work today and don't require any coding.

---

## 4. Quick protection

If you or someone you care about needs **friction right now**, do not wait on this repository’s packaging.

**Crisis support (US):** **1-800-GAMBLER** — free, confidential helpline; you are not reported for calling.

- **Hosts file (macOS/Linux):** Edit `/etc/hosts` (with admin rights) and add lines like `0.0.0.0 example-casino.com` for domains you want to block. Back up the file first. The hosts file is the most bypassable of these options — anyone with admin access on the device can undo it in thirty seconds. SelfControl (below) is harder to bypass because its timer cannot be stopped once started. Use both, with SelfControl as the primary lock.
- **SelfControl** (macOS): Block sites for a set time. [selfcontrolapp.com](https://selfcontrolapp.com)
- **NextDNS** (network/DNS filtering): Configure blocking on your network or device. [nextdns.io](https://nextdns.io)
- **Screen Time** (Apple): Use a passcode someone else holds, if that fits your safety plan.

---

## 5. Usage (developers) — CLI

Invoke as `sweeps-relief` after install, or `python -m sweeps_relief.cli`.

| Command | Purpose |
| --- | --- |
| `sweeps-relief gen-keys --out ./keys` | Create `private.pem`, `public.pem`, and `pubkey.json` (Ed25519). Prints: `Wrote keys to ./keys` |
| `sweeps-relief build-policy [--domains-file seeds.txt] [--out data/published/policy.content.json]` | Write canonical policy **content** JSON (domains + heuristics defaults). |
| `sweeps-relief sign-policy data/published/policy.content.json --private-key keys/private.pem --out data/published/policy.json` | Sign content; writes `policy.json` and a detached `policy.sig` (raw signature line). |
| `sweeps-relief verify-policy data/published/policy.json --public-key keys/public.pem` | Verifies hash + signature. **Success:** `OK: policy signature and hash match.` (exit 0). **Failure:** `FAILED: verification failed.` (exit 1). |
| `sweeps-relief import-seed seeds.txt -o normalized.txt` | Normalize seed lines to unique domains (stdout or `-o` file). |
| `sweeps-relief export-hosts data/published/policy.json -o hosts.txt` | Render a hosts-style blocklist from signed policy. |
| `sweeps-relief export-dns-blocklist …` | DNS denylist text. |
| `sweeps-relief export-browser-rules …` | JSON rules blob for browser integrations. |
| `sweeps-relief build-report …` | Markdown summary for human review. |

**Log bundles:** `sign_log_bundle` / `verify_log_bundle` live in `sweeps_relief.logger` for Python integrations. There is **no** `sweeps-relief verify-log` command yet.

---

## 6. Trust model

**Policy:** Policy content is canonicalized to deterministic JSON, hashed (SHA-256), and signed with **Ed25519**. The device (or auditor) loads `policy.json`, recomputes the hash from embedded content, decodes the base64 signature, and verifies with the public key. A changed file or wrong key fails verification—by design.

**Tamper-evident logs:** Event records and log bundles are built so that integrity checks (hashes, signatures) fail if data is edited without valid keys. An exported bundle can be checked the same way policy can: verify structure, hashes, and signatures against a known public key.

**What auditing proves:** That a given artifact matches what the signer key would have produced—not that the *policy choices* were morally or clinically “correct,” only that they were **not silently replaced** after signing.

---

## 7. Architecture

- **[Sweeps_Scout](https://github.com/Swixixle/Sweeps_Scout)** — discovers and buckets candidate sweepstakes-related domains and sources (ingest, dedupe, research helpers).
- **[Sweeps_Intel](https://github.com/Swixixle/Sweeps_Intel)** — reviews, normalizes, and stages candidates into curated data for publication.
- **Sweeps_Relief (this repo)** — applies **signed** policy on a user’s machine: exports for hosts/DNS/browser, optional mac helper, browser guard work in progress, and signed logging primitives.

Scout and Intel are **internal / operator** workflows. Relief is what runs **on the user side** once policy artifacts exist.

---

## 8. Limitations (honest)

- **No universal guarantee:** Anything not installed on a device cannot block that device. Factory reset or a new unmanaged device bypasses local installs.
- **Discovery lag:** New operators appear continuously; pipeline coverage is best-effort, not same-day for every site.
- **Browser extension:** Chromium MV3 extensions have platform limits; treat any extension as **defense in depth**, not a perfect kernel block.
- **Recovery:** This is a **technical** tool. It is not therapy and not a substitute for professional or peer support.

---

## 9. Contributing

- Run **`pytest`** before pushing; keep changes **reviewable in small commits** (one logical change per commit when possible).
- Prefer **clear messages** so history reads as an audit trail (`fix(scope): …`, `feat(scope): …`, `chore: …`).
- Report issues with **steps to reproduce** and, if relevant, **redacted** policy or log snippets—never share private keys.

The related repository [testimony-corpus](https://github.com/Swixixle/testimony-corpus) has an `ETHICS.md` governing consent-based evidence collection. Relief itself does not touch user stories and has no equivalent document.

---

## 10. License

Licensed under the **MIT License** — see [`LICENSE`](LICENSE).

---

## Further reading

Longer design notes and threat-model drafts may live under `docs/`; the **operational** path is: install → run tests → use CLI commands above → integrate exports with your enforcement layer.
