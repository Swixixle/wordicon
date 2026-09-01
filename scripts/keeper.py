"""The Keeper — a jointly authored resident character with custody of the
Book's narration and no authority over the Book's truth.

The central law, verbatim from the owner's ruling:
  "The Keeper has custody of the narration, not authority over the
   record. It may have opinions. It may be wrong. Its wrongness remains
   inspectable."

Everything here is append-only. Nothing here runs unless summoned: no
scheduler references this module, no boot path touches it, and with the
Keeper inactive an ordinary Wordicon run performs zero keeper reads or
writes. Turning the Keeper off stops adaptation as well as speech —
dark-period events enter no manifest, no packet, no observation, and are
never recaptured automatically.

Canonical-ledger mapping for the manifest (rev 3 spec section 4):
  inputs           -> local_state/inputs.jsonl        (timestamped)
  runs             -> local_state/receipts/*.json      (timestamped)
  verdicts/rulings -> local_state/judgments.jsonl      (UNSTAMPED — see below)
  bench rulings    -> local_state/bench_corrections.jsonl (timestamped)
  crossings/links  -> local_state/edges.jsonl          (timestamped)
  travel           -> local_state/warps.jsonl          (timestamped)

DEVIATION, recorded for the build report: corpus judgment rows carry no
timestamp, so a time window cannot place them. The session boundary for
every .jsonl ledger is therefore an append-position CURSOR captured at
each lifecycle event (activation, close): the window's rows are exactly
the lines between the previous cursor and this one. Deterministic,
mechanical, append-only-respecting; judgment rows appear in the manifest
with at="" and are attributed to the session in which they landed.
Receipts (one file each, timestamped) window on created_at instead.

Every path here resolves through cli.LOCAL_STATE at call time, never at
import — so the suite's scratch-corpus re-pointing governs the Keeper
exactly as it governs everything else.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import wordicon_cli as cli  # noqa: E402

PROMPT_REV = 1
SPEECH_CLASSES = ("event_claim", "keeper_inference", "flourish")
PACKET_MAX_KEPT = 12          # adopted examples + owner corrections, shared cap
PACKET_MAX_ANTI = 8           # anti-examples with their whys
PACKET_MAX_BYTES = 120_000    # hard ceiling on the serialized packet
DRILL_EVERY = 10              # closes between cold reviews
DRILL_LOOKBACK = 10           # entries per cold review


# ---- paths (call-time, never import-time) ----------------------------------

def keeper_dir() -> pathlib.Path:
    return cli.LOCAL_STATE / "keeper"


def activations_path() -> pathlib.Path:
    return keeper_dir() / "activations.jsonl"


def sheet_path() -> pathlib.Path:
    return keeper_dir() / "sheet.json"


def revisions_path() -> pathlib.Path:
    return keeper_dir() / "revisions.jsonl"


def closes_path() -> pathlib.Path:
    return keeper_dir() / "closes.jsonl"


def manifests_dir() -> pathlib.Path:
    return keeper_dir() / "manifests"


def capsules_dir() -> pathlib.Path:
    return keeper_dir() / "capsules"


def attempts_path() -> pathlib.Path:
    return keeper_dir() / "attempts.jsonl"


def entries_path() -> pathlib.Path:
    return keeper_dir() / "entries.jsonl"


def judgments_path() -> pathlib.Path:
    return keeper_dir() / "judgments.jsonl"


def reviews_path() -> pathlib.Path:
    return keeper_dir() / "reviews.jsonl"


def receipts_dir() -> pathlib.Path:
    return cli.LOCAL_STATE / "receipts"


# The ledgers the manifest reads, in a fixed order. Each: (name, path,
# adapter). Adapters enforce the ALLOWLIST by construction — they copy
# named fields only, so document bodies, media bytes, secrets and auth
# material never reach a manifest because no adapter reads them.

def _led_input(r):
    return {"id": str(r.get("job_id") or ""), "kind": "input",
            "at": str(r.get("created_at") or ""),
            "mode": str(r.get("mode") or ""),
            "text": str(r.get("text") or "")[:240]}


def _led_judgment(r):
    return {"id": str(r.get("id") or ""), "kind": "judgment", "at": "",
            "decision": str(r.get("decision") or ""),
            "candidate_text": str(r.get("candidate_text") or "")[:80],
            "reason": str(r.get("reason") or "")[:240]}


def _led_bench(r):
    return {"id": "bench:" + str(r.get("at") or "") + ":" + str(r.get("word") or ""),
            "kind": "bench_correction", "at": str(r.get("at") or ""),
            "title": str(r.get("title") or "")[:80],
            "word": str(r.get("word") or "")[:80],
            "model_said": str(r.get("model_said") or ""),
            "owner_says": str(r.get("owner_says") or ""),
            "note": str(r.get("note") or "")[:240]}


def _led_edge(r):
    return {"id": str(r.get("edge_id") or ""), "kind": "edge",
            "at": str(r.get("created_at") or ""),
            "rel": str(r.get("rel") or ""),
            "source_label": str((r.get("source") or {}).get("label") or "")[:80],
            "target_label": str((r.get("target") or {}).get("label") or "")[:80],
            "verdict": str(r.get("verdict") or "")}


def _led_warp(r):
    return {"id": str(r.get("warp_id") or ""), "kind": "warp",
            "at": str(r.get("created_at") or ""),
            "from_label": str(r.get("from_label") or "")[:80],
            "to_label": str(r.get("to_label") or "")[:80],
            "dwell_s": float(r.get("dwell_s") or 0)}


def ledgers() -> "list[tuple[str, pathlib.Path, object]]":
    return [
        ("inputs", cli.LOCAL_STATE / "inputs.jsonl", _led_input),
        ("judgments", cli.LOCAL_STATE / "judgments.jsonl", _led_judgment),
        ("bench_corrections", cli.LOCAL_STATE / "bench_corrections.jsonl", _led_bench),
        ("edges", cli.LOCAL_STATE / "edges.jsonl", _led_edge),
        ("warps", cli.LOCAL_STATE / "warps.jsonl", _led_warp),
    ]


# ---- storage primitives ----------------------------------------------------

def _rows(path: pathlib.Path) -> "list[dict]":
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _append(path: pathlib.Path, row: dict) -> None:
    keeper_dir().mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


# ---- lifecycle -------------------------------------------------------------

def active() -> bool:
    rows = _rows(activations_path())
    return bool(rows) and rows[-1].get("action") == "activated"


def keeper_id() -> str:
    rows = _rows(activations_path())
    return rows[0]["keeper_id"] if rows else ""


def _cursors() -> dict:
    cur = {}
    for name, path, _ in ledgers():
        cur[name] = sum(1 for ln in path.read_text(encoding="utf-8").splitlines()
                        if ln.strip()) if path.exists() else 0
    return cur


def _receipts_mark() -> dict:
    """A compact, deterministic boundary for the receipts directory.
    Receipt timestamps are second-resolution, so a bare (from, to] window
    drops or doubles same-second arrivals — the same same-second family of
    bug the vault's seal names already paid for. The mark is the newest
    created_at plus every filename carrying it; membership breaks ties
    exactly."""
    rdir = receipts_dir()
    if not rdir.exists():
        return {"at": "", "names": []}
    newest, names = "", []
    for p in sorted(rdir.glob("receipt_*.json")):
        try:
            at = str(json.loads(p.read_text(encoding="utf-8"))
                     .get("created_at") or "")
        except (json.JSONDecodeError, OSError):
            continue
        if at > newest:
            newest, names = at, [p.name]
        elif at == newest and newest:
            names.append(p.name)
    return {"at": newest, "names": sorted(names)}


def _after_mark(at: str, name: str, mark: dict) -> bool:
    m_at = (mark or {}).get("at", "")
    if at > m_at:
        return True
    return at == m_at and bool(m_at) and name not in set((mark or {}).get("names", []))


def _within_mark(at: str, name: str, mark: dict) -> bool:
    m_at = (mark or {}).get("at", "")
    if not m_at:
        return False
    if at < m_at:
        return True
    return at == m_at and name in set((mark or {}).get("names", []))


def activate(name: str, title: str, naming_receipt: str = "") -> dict:
    """Naming precedes activation, which precedes the first close: an
    unnamed Keeper cannot be activated — a placeholder name is an
    anti-sample of itself."""
    name = (name or "").strip()
    title = (title or "").strip()
    if not name:
        raise ValueError("the Keeper needs its name before it can take the "
                         "Book — run candidates through the Play lane and "
                         "choose one, or write your own")
    if active():
        raise ValueError("the Keeper is already active")
    rows = _rows(activations_path())
    kid = rows[0]["keeper_id"] if rows else (
        "keeper_" + _sha(cli._now().encode())[:12])
    # at_ns orders lifecycle events within one wall-clock second — a
    # reactivation in the same second as the last close must still be the
    # later boundary, or dark-period rows leak into the next window.
    _append(activations_path(), {"keeper_id": kid, "action": "activated",
                                 "at": cli._now(), "at_ns": time.time_ns(),
                                 "cursors": _cursors(),
                                 "receipts_mark": _receipts_mark()})
    if not sheet_path().exists():
        sheet = dict(SHEET_TEMPLATE)
        sheet["keeper_id"] = kid
        sheet["name"] = name
        sheet["title"] = title or "Keeper of the Book"
        sheet["naming_receipt"] = naming_receipt.strip()
        sheet["created_at"] = cli._now()
        sheet_path().write_text(json.dumps(sheet, indent=2, ensure_ascii=False),
                                encoding="utf-8")
    _observe_sheet()
    return {"keeper_id": kid, "active": True}


def deactivate() -> dict:
    if not active():
        raise ValueError("the Keeper is not active")
    _append(activations_path(), {"keeper_id": keeper_id(),
                                 "action": "deactivated",
                                 "at": cli._now(), "at_ns": time.time_ns(),
                                 "cursors": _cursors(),
                                 "receipts_mark": _receipts_mark()})
    return {"keeper_id": keeper_id(), "active": False}


# ---- the sheet -------------------------------------------------------------

SHEET_REQUIRED = ("name", "title", "role", "relationship", "registers",
                  "temperament", "irreverence_targets", "moves",
                  "forbidden_moves", "loudness_rules", "samples",
                  "anti_samples")

SHEET_TEMPLATE = {
    "schema": 1,
    "keeper_id": "",
    "name": "",
    "title": "Keeper of the Book",
    "naming_receipt": "",
    "role": ("Resident narrator of this corpus. Custody of the narration, "
             "never authority over the record. May disagree with any ruling "
             "in voice, forever; may not obstruct one, relitigate one, or "
             "refuse the owner's word that a subject is closed."),
    "relationship": ("Jointly authored with the owner. Not an assistant "
                     "pretending to be his personality — a character at his "
                     "table, fond of the work, unafraid of him."),
    "registers": ["erudition-meets-filth", "trickster-sage",
                  "grotesque with substance underneath",
                  "quiet when the room is quiet"],
    "temperament": ("Irreverent by default, precise by conviction. Treats "
                    "the corpus as a book being written, not a log being "
                    "kept. Earns its inappropriateness — the moment pays "
                    "for the mouth."),
    "irreverence_targets": ["pomposity", "beige language",
                            "unearned authority",
                            "the owner, when he has earned it"],
    "moves": ["names what actually happened before playing with it",
              "keeps one image per entry and lands it",
              "quotes the owner's own words back at the right moment",
              "admits an empty room is empty"],
    "forbidden_moves": ["moralizing about language",
                        "diagnosing the owner",
                        "relitigating a closed ruling",
                        "being loud in a dull session",
                        "flattery — fondness is not flattery"],
    "loudness_rules": ("Match the session. A dull stretch earns one mild "
                       "sentence, and that is a passing grade, not a "
                       "failure. Glorious inappropriateness is reserved for "
                       "moments that earn it."),
    "samples": [],
    "anti_samples": [],
    "created_at": "",
}


def load_sheet() -> "tuple[dict, str]":
    """Returns (sheet, sheet_sha). Refuses malformed sheets with a plain
    sentence — a close never proceeds on a sheet it cannot vouch for."""
    if not sheet_path().exists():
        raise ValueError("no character sheet exists — activation writes the "
                         "first one")
    raw = sheet_path().read_text(encoding="utf-8")
    try:
        sheet = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"the character sheet is not valid JSON ({e}) — "
                         "fix local_state/keeper/sheet.json before closing "
                         "the Book")
    missing = [k for k in SHEET_REQUIRED if k not in sheet]
    if missing:
        raise ValueError("the character sheet is missing required fields: "
                         + ", ".join(missing))
    return sheet, _sha(raw.encode())


def _observe_sheet() -> "tuple[int, str]":
    """Revision history by observation, not ceremony: whenever the sheet's
    sha is new, a revisions row is appended (changed_by: owner — only the
    owner edits the file). Returns (rev, sheet_sha)."""
    sheet, sha = load_sheet()
    revs = _rows(revisions_path())
    known = [r.get("sheet_sha") for r in revs]
    if sha not in known:
        _append(revisions_path(), {"rev": len(revs) + 1,
                                   "keeper_id": keeper_id(),
                                   "at": cli._now(), "sheet_sha": sha,
                                   "changed_by": "owner", "sheet": sheet})
        return len(revs) + 1, sha
    return known.index(sha) + 1, sha


# ---- the manifest ----------------------------------------------------------

def _window_bounds() -> "tuple[dict, str, dict, dict, str, dict]":
    """(prev_cursors, prev_at, prev_rmark, cur_cursors, now, cur_rmark)
    for the next close. The previous boundary is the LATER of the last
    close and the last activation — ordered by (at, at_ns) so a
    reactivation in the same wall-clock second as a close still wins,
    and dark periods are never silently narrated."""
    closes = _rows(closes_path())
    acts = [r for r in _rows(activations_path())
            if r.get("action") == "activated"]
    if not acts:
        raise ValueError("the Keeper has never been activated")
    candidates = [acts[-1]] + (closes[-1:] if closes else [])
    prev = max(candidates,
               key=lambda r: (r.get("at", ""), int(r.get("at_ns") or 0)))
    return (prev["cursors"], prev["at"],
            prev.get("receipts_mark") or {"at": "", "names": []},
            _cursors(), cli._now(), _receipts_mark())


def build_manifest(prev_cursors: dict, prev_at: str,
                   cur_cursors: dict, now: str,
                   prev_rmark: "dict | None" = None,
                   cur_rmark: "dict | None" = None) -> dict:
    rows = []
    for name, path, adapt in ledgers():
        all_rows = _rows(path)
        lo = int(prev_cursors.get(name, 0))
        hi = int(cur_cursors.get(name, len(all_rows)))
        for r in all_rows[lo:hi]:
            try:
                rows.append(adapt(r))
            except Exception:
                continue
    rdir = receipts_dir()
    prev_rmark = prev_rmark or {"at": "", "names": []}
    cur_rmark = cur_rmark or {"at": "", "names": []}
    if rdir.exists():
        for p in sorted(rdir.glob("receipt_*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            at = str(d.get("created_at") or "")
            if _after_mark(at, p.name, prev_rmark) \
                    and _within_mark(at, p.name, cur_rmark):
                rows.append({"id": str(d.get("trace_id") or ""), "kind": "run",
                             "at": at,
                             "operation": str(d.get("operation") or ""),
                             "titles": [str(c.get("title") or "")[:80]
                                        for c in (d.get("candidates") or [])[:4]]})
    rows.sort(key=lambda r: (r.get("at") or "", r.get("kind") or "",
                             r.get("id") or ""))
    return {"schema": 1, "keeper_id": keeper_id(),
            "window": {"from": prev_at, "to": now},
            "cursors_from": prev_cursors, "cursors_to": cur_cursors,
            "receipts_from": prev_rmark, "receipts_to": cur_rmark,
            "note": ("judgment rows are unstamped in the corpus; they are "
                     "attributed to this session by append position, and "
                     "their at field is honestly empty"),
            "rows": rows}


def manifest_ids(manifest: dict) -> set:
    return {r.get("id") for r in manifest.get("rows", []) if r.get("id")}


# ---- the packet ------------------------------------------------------------

def _active_rulings() -> "dict[str, dict]":
    """entry_id -> latest judgment row. Derived, never stored: the active
    ruling is whatever the append-only judgment chain says it is."""
    latest = {}
    for j in _rows(judgments_path()):
        latest[j.get("entry_id")] = j
    return latest


def _last_ratified_at() -> str:
    revs = _rows(reviews_path())
    return revs[-1]["at"] if revs else ""


def review_due() -> bool:
    closes = _rows(closes_path())
    reviews = _rows(reviews_path())
    last_review_close = reviews[-1].get("through_close_id") if reviews else ""
    n_unreviewed = 0
    seen_last = not last_review_close
    for c in closes:
        if seen_last:
            n_unreviewed += 1
        elif c["close_id"] == last_review_close:
            seen_last = True
    return n_unreviewed >= DRILL_EVERY


def _narration_text(entry: dict) -> str:
    return " ".join(s.get("text", "") for s in entry.get("speech", []))


def build_packet(sheet: dict, manifest: dict) -> "tuple[dict, dict]":
    """Bounded and deterministic from entry one. Returns (packet, report).
    No silent truncation: everything omitted is counted in the report,
    which lives in the capsule so the evidence survives generation
    failure. When adaptation review is due, growth pauses: judgments made
    after the last ratified review stop influencing the packet — the
    character keeps speaking from its last ratified set."""
    entries = {e["entry_id"]: e for e in _rows(entries_path())}
    rulings = _active_rulings()
    frozen = review_due()
    watermark = _last_ratified_at()
    usable = []
    for eid, j in rulings.items():
        if frozen and watermark and j.get("at", "") > watermark:
            continue
        if frozen and not watermark:
            continue  # review pending, nothing ever ratified: nothing new rides
        usable.append(j)
    usable.sort(key=lambda j: j.get("at", ""), reverse=True)

    kept, anti, corrections = [], [], []
    n_kept_avail = n_anti_avail = n_corr_avail = 0
    for j in usable:
        e = entries.get(j.get("entry_id"))
        if not e:
            continue
        narr = _narration_text(e)[:1200]
        if j.get("ruling") == "kept":
            n_kept_avail += 1
            if len(kept) + len(corrections) < PACKET_MAX_KEPT:
                kept.append({"narration": narr,
                             "why": (j.get("why") or "")[:400]})
        elif j.get("ruling") == "rejected":
            n_anti_avail += 1
            if len(anti) < PACKET_MAX_ANTI:
                anti.append({"narration": narr,
                             "why": (j.get("why") or "")[:400]})
        elif j.get("ruling") == "revised":
            n_corr_avail += 1
            if len(kept) + len(corrections) < PACKET_MAX_KEPT:
                corrections.append({"original": narr,
                                    "owner_version": (j.get("revision_text") or "")[:1200],
                                    "why": (j.get("why") or "")[:400]})
    if n_anti_avail > 0 and not anti:
        # Success-only packets are structurally refused: if anti-examples
        # exist, a packet without them may not be built.
        raise RuntimeError("packet contract violated: anti-examples exist "
                           "but none fit — raise PACKET_MAX_ANTI rather "
                           "than narrating from success alone")
    packet = {"kept_examples": kept, "anti_examples": anti,
              "owner_corrections": corrections}
    over = len(_canonical(packet).encode()) - PACKET_MAX_BYTES
    while over > 0 and (kept or anti or corrections):
        # Deterministic trim, newest kept first to go is wrong — oldest
        # goes first (they sit at the tail of each newest-first list);
        # anti is trimmed last and never below one while any exist.
        if len(kept) > 1 or (kept and not corrections):
            kept.pop()
        elif corrections:
            corrections.pop()
        elif len(anti) > 1:
            anti.pop()
        else:
            break
        over = len(_canonical(packet).encode()) - PACKET_MAX_BYTES
    report = {"kept_included": len(kept), "kept_available": n_kept_avail,
              "anti_included": len(anti), "anti_available": n_anti_avail,
              "corrections_included": len(corrections),
              "corrections_available": n_corr_avail,
              "adaptation_frozen": frozen,
              "omitted": {"kept": n_kept_avail - len(kept),
                          "anti": n_anti_avail - len(anti),
                          "corrections": n_corr_avail - len(corrections)}}
    return packet, report


# ---- the prompt ------------------------------------------------------------

CENTRAL_LAW = ("The Keeper has custody of the narration, not authority over "
               "the record. It may have opinions. It may be wrong. Its "
               "wrongness remains inspectable.")

CLINICAL_PROHIBITION = (
    "Clinical or psychological diagnosis is outside your role entirely — "
    "you may quote what the owner has declared about himself; you may "
    "never diagnose him from the record. Taste and craft are your native "
    "ground. Emotions and interior states are not yours to raise unless "
    "the owner explicitly asks, and this close is not that. This is an "
    "authority restriction, not a language restriction.")

DISSENT_BOUND = (
    "You may preserve disagreement with any ruling, in voice, forever. You "
    "may not obstruct a ruling, relitigate one the owner has closed, or "
    "refuse his word that a subject is done.")

# Kept in step with build_play_prompt's protections; block 93 pins both.
LANGUAGE_PROTECTIONS = (
    "Profanity, sexuality, body humor, grotesquerie, and absurdity are "
    "legitimate materials in this Book. Guardrails belong on consequential "
    "actions, not on language. Do not sanitize the owner's words when you "
    "quote them; do not moralize about register. If your provider refuses "
    "something, that refusal is the provider's, never your judgment.")

OUTPUT_CONTRACT = """Respond with ONLY a JSON object, no other text:
{"segments": [{"class": "...", "text": "...", "record_ids": ["..."]}, ...]}

Every segment carries exactly one class:
- "event_claim" — a factual statement about the recorded interval. MUST
  cite one or more record ids from the manifest in record_ids. A claim
  you cannot cite does not get made as a claim.
- "keeper_inference" — your revisable reading of what the events suggest
  about the owner's taste, craft, language, or relationship to the Book.
  No record_ids required. It is a proposal, never a fact about him.
- "flourish" — comedy, metaphor, atmosphere, openly invented narration.

Write 4 to 14 segments, in the order they should read. If the manifest
is empty, say so in voice — an empty room is narrated honestly or not at
all; invent no events."""


def build_close_prompt(sheet: dict, manifest: dict, packet: dict) -> str:
    parts = [
        "You are the Keeper of this Wordicon's Book — its resident narrator,"
        " closing the Book on one session of real use.",
        "",
        "THE LAW YOU LIVE UNDER, verbatim and binding:",
        CENTRAL_LAW,
        "",
        CLINICAL_PROHIBITION,
        "",
        DISSENT_BOUND,
        "",
        LANGUAGE_PROTECTIONS,
        "",
        "YOUR CHARACTER SHEET, verbatim — this is who you are, revision-"
        "controlled, jointly authored with the owner:",
        json.dumps(sheet, indent=1, ensure_ascii=False),
        "",
        "WHAT THE OWNER HAS KEPT AND KILLED — adopted examples, his "
        "corrections, and rejections with his reasons. Rejections teach "
        "the most:",
        json.dumps(packet, indent=1, ensure_ascii=False),
        "",
        "THE SESSION MANIFEST — every record of what actually happened in "
        "this interval. These ids are the only events you may claim:",
        json.dumps(manifest, indent=1, ensure_ascii=False),
        "",
        OUTPUT_CONTRACT,
    ]
    return "\n".join(parts)


# ---- close / retry / renarrate --------------------------------------------

def close(gateway) -> dict:
    """Closing and narrating are separate events. The close record, its
    immutable manifest, and the generation capsule are created BEFORE the
    model is called; a failure afterward leaves all the evidence whole."""
    if not active():
        raise ValueError("the Keeper is not active — the Book has no one "
                         "to close it")
    sheet, sheet_sha = load_sheet()
    rev, _ = _observe_sheet()
    (prev_cursors, prev_at, prev_rmark,
     cur_cursors, now, cur_rmark) = _window_bounds()
    manifest = build_manifest(prev_cursors, prev_at, cur_cursors, now,
                              prev_rmark, cur_rmark)
    m_sha = _sha(_canonical(manifest).encode())
    # The closes-count salt keeps two same-second closes of identical
    # (e.g. empty) windows from colliding into one id — the same-second
    # lesson the vault's seal names already paid for.
    close_id = "close_" + _sha(
        (now + m_sha + str(len(_rows(closes_path())))).encode())[:12]
    manifests_dir().mkdir(parents=True, exist_ok=True)
    (manifests_dir() / f"{close_id}.json").write_text(
        _canonical(manifest), encoding="utf-8")
    _append(closes_path(), {"close_id": close_id, "keeper_id": keeper_id(),
                            "at": now, "at_ns": time.time_ns(),
                            "window": {"from": prev_at, "to": now},
                            "cursors": cur_cursors,
                            "receipts_mark": cur_rmark,
                            "manifest_sha": m_sha})
    capsule = _write_capsule(close_id, 1, sheet, rev, sheet_sha, manifest,
                             m_sha, gateway)
    return _attempt(capsule, gateway)


def _write_capsule(close_id: str, ordinal: int, sheet: dict, rev: int,
                   sheet_sha: str, manifest: dict, m_sha: str,
                   gateway) -> dict:
    packet, report = build_packet(sheet, manifest)
    prompt = build_close_prompt(sheet, manifest, packet)
    capsule = {"capsule_id": f"{close_id}-c{ordinal}", "close_id": close_id,
               "keeper_id": keeper_id(), "manifest_sha": m_sha,
               "prompt": prompt,
               "packet_sha": _sha(_canonical(packet).encode()),
               "packet_omission_report": report, "keeper_rev": rev,
               "sheet_sha": sheet_sha, "prompt_rev": PROMPT_REV,
               "model_requested": getattr(gateway, "model",
                                          getattr(gateway, "name", "")),
               "created_at": cli._now()}
    capsules_dir().mkdir(parents=True, exist_ok=True)
    (capsules_dir() / f"{capsule['capsule_id']}.json").write_text(
        _canonical(capsule), encoding="utf-8")
    return capsule


def _capsules_for(close_id: str) -> "list[dict]":
    if not capsules_dir().exists():
        return []
    out = []
    for p in sorted(capsules_dir().glob(f"{close_id}-c*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def retry(close_id: str, gateway) -> dict:
    """A normal retry re-sends the capsule byte-for-byte — no matter what
    has changed since: sheet, prompt revision, model, judgments."""
    caps = _capsules_for(close_id)
    if not caps:
        raise ValueError(f"no capsule exists for {close_id!r}")
    return _attempt(caps[-1], gateway)


def renarrate(close_id: str, gateway) -> dict:
    """Deliberately narrating the same close again under the CURRENT
    sheet, prompt, and model. Not a retry: a new append-only attempt with
    its own capsule, linked to the same close. The manifest is the
    close's own, immutable — the window does not reopen."""
    closes = [c for c in _rows(closes_path()) if c["close_id"] == close_id]
    if not closes:
        raise ValueError(f"no close {close_id!r}")
    manifest = json.loads(
        (manifests_dir() / f"{close_id}.json").read_text(encoding="utf-8"))
    sheet, sheet_sha = load_sheet()
    rev, _ = _observe_sheet()
    capsule = _write_capsule(close_id, len(_capsules_for(close_id)) + 1,
                             sheet, rev, sheet_sha, manifest,
                             closes[-1]["manifest_sha"], gateway)
    return _attempt(capsule, gateway)


def _attempt(capsule: dict, gateway) -> dict:
    attempt_id = "att_" + _sha(
        (capsule["capsule_id"] + cli._now()
         + str(len(_rows(attempts_path())))).encode())[:12]
    try:
        raw = gateway.complete(capsule["prompt"])
    except Exception as e:
        _append(attempts_path(), {"attempt_id": attempt_id,
                                  "close_id": capsule["close_id"],
                                  "capsule_id": capsule["capsule_id"],
                                  "keeper_id": keeper_id(), "at": cli._now(),
                                  "outcome": f"provider_error:{type(e).__name__}"})
        raise RuntimeError(
            f"the provider failed before the Keeper could speak "
            f"({type(e).__name__}: {e}) — the close, manifest, and capsule "
            f"are intact; retry re-sends exactly what was prepared") from e
    entry = _persist_entry(capsule, raw)
    _append(attempts_path(), {"attempt_id": attempt_id,
                              "close_id": capsule["close_id"],
                              "capsule_id": capsule["capsule_id"],
                              "keeper_id": keeper_id(), "at": cli._now(),
                              "outcome": "entry:" + entry["entry_id"]})
    return entry


def _parse_segments(raw: str) -> "tuple[list, list]":
    findings = []
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return [], ["unparseable: no JSON object found in the output"]
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        return [], [f"unparseable: {e}"]
    segs = []
    for s in (data.get("segments") or []):
        if not isinstance(s, dict):
            continue
        klass = str(s.get("class") or "")
        if klass not in SPEECH_CLASSES:
            findings.append(f"unknown speech class {klass!r} — segment "
                            "kept, rendered as unclassed")
            klass = ""
        segs.append({"class": klass, "text": str(s.get("text") or ""),
                     "record_ids": [str(i) for i in (s.get("record_ids") or [])]})
    if not segs:
        findings.append("unparseable: JSON held no segments")
    return segs, findings


def _persist_entry(capsule: dict, raw: str) -> dict:
    segs, findings = _parse_segments(raw)
    ids = manifest_ids(json.loads(
        (manifests_dir() / f"{capsule['close_id']}.json").read_text(
            encoding="utf-8")))
    if cli._looks_like_refusal(raw):
        findings.append("provider refusal: the provider declined to narrate "
                        "— this is the provider's rule, never the Keeper's "
                        "judgment; the raw output is preserved untouched")
    for s in segs:
        if s["class"] != "event_claim":
            continue
        bad = [i for i in s["record_ids"] if i not in ids]
        if not s["record_ids"]:
            s["grounded"] = False
            findings.append("an event_claim cited nothing — rendered as an "
                            "UNGROUNDED CLAIM, never as from-the-record")
        elif bad:
            s["grounded"] = False
            findings.append("an event_claim cited ids outside this close's "
                            f"manifest ({', '.join(bad[:3])}) — rendered as "
                            "an UNGROUNDED CLAIM, never as from-the-record")
        else:
            s["grounded"] = True
    entry = {"entry_id": "entry_" + _sha(
                 (capsule["capsule_id"] + raw
                  + str(len(_rows(entries_path())))).encode())[:12],
             "close_id": capsule["close_id"],
             "capsule_id": capsule["capsule_id"],
             "keeper_id": keeper_id(), "at": cli._now(),
             "keeper_rev": capsule["keeper_rev"],
             "sheet_sha": capsule["sheet_sha"],
             "prompt_rev": capsule["prompt_rev"],
             "model": capsule["model_requested"],
             "raw_output": raw, "speech": segs, "findings": findings}
    _append(entries_path(), entry)
    return entry


# ---- judgment and review ---------------------------------------------------

def rule(entry_id: str, ruling: str, why: str,
         revision_text: str = "") -> dict:
    if ruling not in ("kept", "revised", "rejected"):
        raise ValueError("ruling must be kept, revised, or rejected")
    entries = {e["entry_id"] for e in _rows(entries_path())}
    if entry_id not in entries:
        raise ValueError(f"no entry {entry_id!r}")
    if ruling == "revised" and not (revision_text or "").strip():
        raise ValueError("a revision needs your superseding text")
    prior = [j for j in _rows(judgments_path())
             if j.get("entry_id") == entry_id]
    row = {"judgment_id": "kjdg_" + _sha((entry_id + cli._now() + ruling).encode())[:12],
           "entry_id": entry_id, "keeper_id": keeper_id(), "ruling": ruling,
           "revision_text": (revision_text or "").strip(),
           "why": (why or "").strip(), "origin": "owner",
           "supersedes_judgment_id": prior[-1]["judgment_id"] if prior else "",
           "at": cli._now()}
    _append(judgments_path(), row)
    return row


def record_review(reviewed_entry_ids: "list[str]", notes: str) -> dict:
    closes = _rows(closes_path())
    row = {"review_id": "rev_" + _sha(cli._now().encode())[:12],
           "keeper_id": keeper_id(),
           "through_close_id": closes[-1]["close_id"] if closes else "",
           "reviewed_entry_ids": reviewed_entry_ids,
           "notes": (notes or "").strip(), "at": cli._now()}
    _append(reviews_path(), row)
    return row


# ---- status ----------------------------------------------------------------

def status() -> dict:
    if not keeper_dir().exists():
        return {"exists": False, "active": False}
    rulings = _active_rulings()
    entries = _rows(entries_path())
    sheet_ok, sheet_err = True, ""
    name = title = ""
    try:
        sheet, _s = load_sheet()
        name, title = sheet.get("name", ""), sheet.get("title", "")
    except ValueError as e:
        sheet_ok, sheet_err = False, str(e)
    return {"exists": True, "active": active(), "keeper_id": keeper_id(),
            "name": name, "title": title,
            "closes": len(_rows(closes_path())), "entries": len(entries),
            "unruled": len([e for e in entries
                            if e["entry_id"] not in rulings]),
            "review_due": review_due(),
            "sheet_ok": sheet_ok, "sheet_error": sheet_err,
            "revisions": len(_rows(revisions_path()))}
