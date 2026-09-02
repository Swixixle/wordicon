"""The Recovery Review (block 103; backlog items 34, 41, 44, 47).

Six acceptances survived the identity migration as receipt-only: a
judgment row that says "accepted", a receipt with the run's candidate
titles, and nothing else — no result snapshot, so no definition, and no
shelf entry. The audit queued them (recovery_review_queue.jsonl, never
rewritten) for the owner. This module shows each case exactly as the
record holds it and takes the owner's ruling as a NEW judgment event:
Accept requires a definition the owner supplies and mints the concept's
identity at that ruling; Revise takes a corrected title and/or
definition the same way; Reject is a rejection. Nothing is regenerated,
reconstructed, or inferred. Rulings append to
recovery_review_rulings.jsonl; the queue file is read, never written.
The Home band reads queue minus rulings, so it empties through the
record. Not a backlog manager: only the queue's cases exist here."""
from __future__ import annotations

import json
import uuid
import pathlib

import wordicon_cli as cli
from wordicon_corpus.objects import Judgment

QUEUE_NAME = "recovery_review_queue.jsonl"
RULINGS_NAME = "recovery_review_rulings.jsonl"
DECISIONS = ("accept", "reject", "revise")


def queue_path() -> pathlib.Path:
    return pathlib.Path(cli.LOCAL_STATE) / QUEUE_NAME


def rulings_path() -> pathlib.Path:
    return pathlib.Path(cli.LOCAL_STATE) / RULINGS_NAME


def _rows(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def load_queue() -> list[dict]:
    return [r for r in _rows(queue_path()) if r.get("status") == "needs_owner_ruling"]


def load_rulings() -> list[dict]:
    return _rows(rulings_path())


def ruled_ids() -> set:
    return {r.get("queue_judgment_id") for r in load_rulings() if r.get("queue_judgment_id")}


def open_cases() -> list[dict]:
    """Queue rows the owner has not ruled on. The queue is never rewritten;
    a ruling row is what closes a case."""
    done = ruled_ids()
    return [r for r in load_queue() if r.get("judgment_id") not in done]


def _receipt_for(trace: str) -> dict:
    if not trace or not cli.RECEIPTS_DIR.exists():
        return {}
    direct = cli.RECEIPTS_DIR / f"receipt_{trace}.json"
    candidates = [direct] if direct.exists() else list(cli.RECEIPTS_DIR.glob("*.json"))
    for p in candidates:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if r.get("trace_id") == trace:
            return r
    return {}


def _judgment_row(judgment_id: str) -> dict:
    for j in _rows(pathlib.Path(cli.JUDGMENTS_LOG)):
        if j.get("id") == judgment_id:
            return j
    return {}


def case_evidence(row: dict) -> dict:
    """What actually survived for one case — and, said explicitly, what did
    not. Nothing here is reconstructed: every value is read from a file."""
    trace = row.get("trace") or ""
    receipt = _receipt_for(trace)
    judgment = _judgment_row(row.get("judgment_id") or "")
    snapshot_exists = bool(trace) and (cli.RESULTS_DIR / f"{trace}.json").exists()
    titles = [c.get("title", "") for c in (receipt.get("candidates") or []) if c.get("title")]
    return {
        "title": row.get("title", ""),
        "queue_judgment_id": row.get("judgment_id", ""),
        "queued_at": row.get("queued_at", ""),
        "queue_note": row.get("note", ""),
        "trace": trace,
        "acceptance": {
            "found": bool(judgment),
            "decision": judgment.get("decision", ""),
            "owner_note": judgment.get("reason") or "",
            "has_clock": bool(judgment.get("ruled_at")),
            "concept_id": judgment.get("concept_id") or "",
        },
        "receipt": {
            "found": bool(receipt),
            "receipt_id": receipt.get("receipt_id", ""),
            "created_at": receipt.get("created_at", ""),
            "operation": receipt.get("operation", ""),
            "candidate_titles": titles,
            "n_sources": len(receipt.get("sources") or []),
            "n_rejections": len(receipt.get("rejections") or []),
            "engine_version": receipt.get("engine_version", ""),
            "kernel_version": receipt.get("kernel_version", ""),
            "model_calls": receipt.get("model_calls", ""),
            "input_hash": receipt.get("input_hash", ""),
        },
        "survives": {
            "definition": False,          # by construction: no snapshot survives for a queued case
            "result_snapshot": snapshot_exists,
            "shelf_entry": _has_persisted_entry(row.get("title", "")),
        },
        "unknowable": ["the definition the model produced", "its anatomy, contradiction and friction text",
                       "the clock of the original acceptance (judgment rows carried none)"],
        "owner_must_supply": ["a definition, if accepted or revised", "whether it is still accepted"],
    }


def _has_persisted_entry(title: str) -> bool:
    if not cli.ACCEPTED_CONCEPTS_PATH.exists():
        return False
    try:
        rows = json.loads(cli.ACCEPTED_CONCEPTS_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    return any((e.get("name") or "") == title for e in rows)


def cases() -> dict:
    open_ = [case_evidence(r) for r in open_cases()]
    rulings = load_rulings()
    return {"open": open_, "open_count": len(open_), "ruled": rulings, "ruled_count": len(rulings),
            "queue_total": len(load_queue()), "epoch": cli.current_epoch(),
            "note": "Only what the record holds is shown. No definition is reconstructed; "
                    "Accept needs one from you, and the concept's identity is minted at that ruling."}


def _mint_concept_id() -> str:
    # unique, collision-resistant, unrelated to any title (item 34's law)
    return "concept_" + uuid.uuid4().hex[:12]


def rule(queue_judgment_id: str, decision: str, definition: str = "", new_title: str = "",
         note: str = "") -> dict:
    """The owner's ruling on one queued case, as new judgment events that
    cite the old acceptance and its receipt. Refuses anything the record
    cannot honestly hold: a second ruling on a closed case, an accept or
    revise without an owner-supplied definition, a revise that changes
    nothing, an unknown case."""
    if decision not in DECISIONS:
        raise ValueError("decision must be accept, reject, or revise")
    row = next((r for r in load_queue() if r.get("judgment_id") == queue_judgment_id), None)
    if not row:
        raise ValueError("that case is not in the recovery queue")
    if queue_judgment_id in ruled_ids():
        raise ValueError("that case has already been ruled on — a ruling is not rewritten")
    title = row.get("title") or ""
    trace = row.get("trace") or ""
    definition = (definition or "").strip()
    new_title = (new_title or "").strip()
    note = (note or "").strip()
    if decision in ("accept", "revise") and not definition:
        raise ValueError("Accept and Revise need a definition from you — none survives, and none is invented")
    if decision == "revise" and new_title == title:
        new_title = ""
    if decision == "revise" and not new_title and not definition:
        raise ValueError("Revise changes the title, the definition, or both")
    receipt = _receipt_for(trace)
    cites = {"judgment_id": queue_judgment_id, "queue": "recovery_review"}
    if receipt.get("receipt_id"):
        cites["receipt_id"] = receipt["receipt_id"]
    if trace:
        cites["trace_id"] = trace
    now = cli._now()
    epoch = cli.current_epoch()
    concept_id = _mint_concept_id()
    events = []

    def _event(dec: str, text: str, reason: str) -> str:
        j = Judgment(id="jdg_evt_" + uuid.uuid4().hex[:16], decision=dec, candidate_text=text,
                     originating_operation=trace or "trace_recovery_review", decision_source="owner",
                     confidence=1.0, review_status="unreviewed", reason=reason or None,
                     scope="local_to_concept", concept_id=concept_id, ruled_at=now, epoch=epoch,
                     origin="recovery_review", cites=dict(cites))
        cli.persist_judgment(j)
        events.append(j.id)
        return j.id

    added = False
    kept_title = title
    if decision == "accept":
        _event("accepted", title, note)
        added = cli.persist_accepted_concept(title, definition, trace or "trace_recovery_review",
                                             concept_id=concept_id)
    elif decision == "reject":
        _event("rejected", title, note)
    else:
        kept_title = new_title or title
        if new_title:
            _event("revised", title, note or f"revised to: {new_title}")
        _event("accepted", kept_title, note)
        added = cli.persist_accepted_concept(kept_title, definition, trace or "trace_recovery_review",
                                             concept_id=concept_id)
    ruling = {"object_type": "recovery_ruling", "ruling_id": "rr_" + uuid.uuid4().hex[:12],
              "queue_judgment_id": queue_judgment_id, "title": title, "trace": trace,
              "decision": decision, "kept_title": kept_title if decision != "reject" else "",
              "concept_id": concept_id, "judgment_ids": events, "shelf_entry_added": bool(added),
              "definition_supplied_by": "owner" if definition else "", "note": note,
              "ruled_at": now, "epoch": epoch}
    cli.LOCAL_STATE.mkdir(exist_ok=True)
    with rulings_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(ruling, ensure_ascii=False) + "\n")
    return ruling
