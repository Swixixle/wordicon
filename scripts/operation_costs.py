"""Append-only operation accounting on the existing operations event spine.

Reads never reconcile or create a database. Token-rate calculations are estimates,
not invoice amounts. Missing usage/rates remain unknown with a known subtotal.
Writers own a short vault guard by default; authenticated mutation routes already
holding that guard must pass guarded=False (the vault lock is not reentrant).
"""
from __future__ import annotations

from contextlib import nullcontext
from decimal import Decimal
import hashlib
import json
import math
import re
import sqlite3

import operations as ops
import producers
import vault

SCHEMA = "nikodemus.operation-cost.v1"
PRICE_URL = "https://platform.claude.com/docs/en/about-claude/pricing"
CHECKED_AT = "2026-10-18"
CATEGORIES = ("input_tokens", "output_tokens", "cache_read_input_tokens",
              "cache_creation_5m_input_tokens", "cache_creation_1h_input_tokens")


class CostError(ValueError):
    status = 409


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def rate_card(provider, model):
    """Explicit supported family only; Sonnet 5.5 must not inherit Sonnet 5 rates."""
    if provider != "anthropic" or not re.fullmatch(r"claude-sonnet-5(?:-\d{8})?", str(model or "")):
        return None
    return {"version": "anthropic-sonnet5-standard-global-2026-10-18", "provider": provider,
            "model_family": "claude-sonnet-5", "currency": "USD", "checked_at": CHECKED_AT,
            "source_url": PRICE_URL, "scope": "direct_api_standard_global_no_tools",
            "categories": [{"category": c, "usd_per_million": n} for c, n in zip(CATEGORIES, (2, 10, 0.2, 2.5, 4))]}


def _connect_ro():
    path = ops.db_path()
    if not path.is_file():
        return None
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _operation(op):
    if isinstance(op, dict):
        return op
    conn = _connect_ro()
    if conn is None:
        raise CostError("No such operation.")
    try:
        result = ops._row(conn.execute("SELECT * FROM operations WHERE op_id=?", (str(op),)).fetchone())
        if result is None:
            raise CostError("No such operation.")
        return result
    finally:
        conn.close()


def _events(op_id, conn=None):
    own = conn is None
    conn = conn or _connect_ro()
    if conn is None:
        return []
    try:
        out = []
        for row in conn.execute("SELECT detail FROM operation_events WHERE op_id=? AND kind='note' ORDER BY seq", (op_id,)):
            data = json.loads(row[0]).get("accounting")
            if isinstance(data, dict) and data.get("schema") == SCHEMA:
                out.append(data)
        return out
    finally:
        if own:
            conn.close()


def _append(op_id, record, *, guarded=True, check=None):
    with vault.corpus_write() if guarded else nullcontext():
        conn = ops._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = _events(op_id, conn)
            if check:
                prior = check(rows)
                if prior is not None:
                    conn.execute("COMMIT")
                    return prior
            existing = next((r for r in rows if r.get("entry_id") == record["entry_id"]), None)
            if existing:
                conn.execute("COMMIT")
                return existing
            ops._event(conn, op_id, "note", detail={"accounting": record})
            conn.execute("UPDATE operations SET updated_at=? WHERE op_id=?", (ops._now(), op_id))
            conn.execute("COMMIT")
            vault.mark_dirty()
            return record
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()


def _model(op):
    spec = (op.get("execution") or {}).get("plan", {}).get("synthesis") or {}
    return spec.get("provider"), spec.get("model")


def _valid_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _cost(count, rate):
    return float(Decimal(str(count)) * Decimal(str(rate)) / Decimal(1000000))


def proposal_estimate(provider, model, max_input_chars=40000, max_output_tokens=4096, allowance_usd=0.50):
    rate = rate_card(provider, model)
    if rate is None:
        raise CostError("No rate card is available for the configured model; pricing must be established before a billable Start.")
    if (type(max_input_chars) is not int or not 1 <= max_input_chars <= 40000
            or type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 8192
            or not _valid_number(allowance_usd) or allowance_usd <= 0):
        raise CostError("The model allowance is not supported.")
    estimate = round(_cost(max_input_chars * 4 + 1024, 2) + _cost(max_output_tokens, 10), 9)
    if estimate > allowance_usd:
        raise CostError("The conservative maximum request estimate exceeds the proposed allowance.")
    return {"rate_card": rate, "allowance_usd": allowance_usd, "max_estimated_cost_usd": estimate,
            "currency": "USD", "actual_cost_usd": None,
            "accounting_basis": "Versioned standard API token rates; conservative UTF-8 character estimate, not an invoice or provider-guaranteed dollar ceiling."}


def _reduced(rows):
    """Latest correction per attempt, and one charge per provider response id."""
    attempts = {}
    for row in rows:
        aid = (row["operation_id"], row["component"], row["attempt_id"])
        if row["event_type"] == "reservation" and aid in attempts and attempts[aid]["event_type"] != "reservation":
            continue
        attempts[aid] = row
    result, identities = [], set()
    for row in attempts.values():
        identity = row.get("charge_identity")
        if identity and identity in identities:
            continue
        if identity:
            identities.add(identity)
        result.append(row)
    return result


def reserve(op_id, component, attempt_id, prompt, max_output_tokens, allowance_usd=0.50,
            *, provider=None, model=None, rate=None, guarded=True):
    """Reserve one tool-free, uncached request before its dispatch intent.

    The utf8 byte count plus 1024 framing units is a conservative token estimate,
    not a provider-certified bound. It is compared with the disclosed USD
    allowance; all outstanding reservations in this operation count against it.
    """
    op = _operation(op_id)
    p, m = _model(op)
    provider, model = provider or p, model or m
    current = rate_card(provider, model)
    if current is None or (rate is not None and rate != current):
        raise CostError("No matching frozen rate card is available; no billable request is authorized.")
    if not isinstance(prompt, str) or type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 8192:
        raise CostError("A text prompt and an output allowance from 1 through 8192 are required.")
    if not _valid_number(allowance_usd) or allowance_usd <= 0:
        raise CostError("A positive finite USD allowance is required.")
    if not isinstance(component, str) or not component or not isinstance(attempt_id, str) or not attempt_id:
        raise CostError("Component and attempt identities are required.")
    limit = len(prompt.encode("utf-8")) + 1024
    bound = _cost(limit, 2) + _cost(max_output_tokens, 10)
    request = {"provider": provider, "model": model, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
               "input_units_upper_estimate": limit, "output_limit": max_output_tokens, "rate_card": current,
               "allowance_usd": allowance_usd, "tools": False, "prompt_cache": "not_requested"}
    row = {"schema": SCHEMA, "event_type": "reservation", "operation_id": op["op_id"], "component": component,
           "attempt_id": attempt_id, **request, "request_fingerprint": _hash(request), "currency": "USD",
           "accounting_status": "reserved", "basis": "utf8_bytes_plus_1024_and_output_limit_estimate",
           "reserved_usd": round(bound, 9), "estimated_cost_usd": None, "actual_cost_usd": None,
           "known_estimated_subtotal_usd": 0.0, "usage": []}
    row["entry_id"] = _hash([op["op_id"], component, attempt_id, "reservation"])
    def check(rows):
        prior = next((r for r in rows if r["component"] == component and r["attempt_id"] == attempt_id and r["event_type"] == "reservation"), None)
        if prior:
            if prior["request_fingerprint"] != row["request_fingerprint"]:
                raise CostError("This attempt identity already reserved a different request.")
            return prior
        liable = 0.0
        for old in _reduced(rows):
            if old.get("estimated_cost_usd") is not None:
                liable += old["estimated_cost_usd"]
            elif old.get("reserved_usd") is not None:
                liable += old["reserved_usd"]
            elif old.get("accounting_status") != "reported_zero":
                raise CostError("An earlier charge is unknown without a reservation; reconcile it before spending again.")
        if liable + bound > allowance_usd + 1e-12:
            raise CostError("The conservative request estimate exceeds the remaining operation allowance.")
    # Validate request reuse even when its entry id already exists.
    existing = next((r for r in _events(op["op_id"]) if r["entry_id"] == row["entry_id"]), None)
    if existing and existing.get("request_fingerprint") != row["request_fingerprint"]:
        raise CostError("This attempt identity already reserved a different request.")
    return _append(op["op_id"], row, guarded=guarded, check=check)


def _usage(receipt):
    response = receipt.get("response") or {}
    raw = response.get("response") or {}
    if isinstance(raw.get("usage"), dict):
        return raw["usage"]
    return response.get("usage") or receipt.get("usage") or {}


def _settlement(op, component, attempt_id, receipt, receipt_sha256, *, reservation=None, provisional=False):
    provider = receipt.get("provider") or (reservation or {}).get("provider") or _model(op)[0]
    response = receipt.get("response") or {}
    raw = response.get("response") or {}
    model = raw.get("model") or receipt.get("model") or (reservation or {}).get("model") or _model(op)[1]
    rate = (reservation or {}).get("rate_card") or rate_card(provider, model)
    if rate and rate_card(provider, model) != rate:
        rate = None
    rates = {r["category"]: r["usd_per_million"] for r in (rate or {}).get("categories", [])}
    raw_usage = _usage(receipt)
    unknown, measured = [], []
    usage_complete = response.get("usage_complete", not bool(receipt.get("error")))
    if not usage_complete:
        unknown.append("Provider usage is incomplete; measured categories are only a subtotal.")
    if not rate:
        unknown.append("No applicable recorded price for this provider/model/scope.")
    def category(name, count, *, absent_zero=False):
        if count is None and absent_zero:
            count = 0
        valid = type(count) is int and count >= 0
        estimate = _cost(count, rates[name]) if valid and name in rates else None
        measured.append({"category": name, "count": count if valid else None, "usd_per_million": rates.get(name), "estimated_usd": estimate})
        if not valid:
            unknown.append("Missing or invalid " + name + ".")
    category("input_tokens", raw_usage.get("input_tokens"))
    category("output_tokens", raw_usage.get("output_tokens"))
    no_cache = (reservation or {}).get("prompt_cache") == "not_requested"
    category("cache_read_input_tokens", raw_usage.get("cache_read_input_tokens"), absent_zero=no_cache)
    creation = raw_usage.get("cache_creation_input_tokens")
    split = raw_usage.get("cache_creation") or {}
    if (type(creation) is int and creation == 0) or (creation is None and no_cache):
        category("cache_creation_5m_input_tokens", 0)
        category("cache_creation_1h_input_tokens", 0)
    elif isinstance(split, dict) and all(type(split.get(k)) is int and split[k] >= 0 for k in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")):
        category("cache_creation_5m_input_tokens", split["ephemeral_5m_input_tokens"])
        category("cache_creation_1h_input_tokens", split["ephemeral_1h_input_tokens"])
        if type(creation) is not int or sum(split[k] for k in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")) != creation:
            unknown.append("Cache write duration categories do not reconcile with the provider total.")
    else:
        category("cache_creation_5m_input_tokens", None)
        category("cache_creation_1h_input_tokens", None)
        unknown.append("Cache write duration is unavailable; a five-minute price was not assumed.")
    tool_usage = raw_usage.get("server_tool_use") or {}
    if not isinstance(tool_usage, dict) or (tool_usage and any(v for v in tool_usage.values())):
        unknown.append("Server tool charges are outside this rate card.")
    if raw_usage.get("service_tier") not in (None, "standard") or raw_usage.get("inference_geo") not in (None, "global"):
        unknown.append("Nonstandard service tier or inference geography requires its own price.")
    response_id = response.get("response_id") or raw.get("id")
    identity = [provider, response_id] if response_id else [op["op_id"], component, attempt_id]
    subtotal = round(sum(x["estimated_usd"] or 0 for x in measured), 9)
    row = {"schema": SCHEMA, "event_type": "settlement", "operation_id": op["op_id"], "component": component,
        "attempt_id": attempt_id, "provider": provider, "model": model, "provider_run_id": response_id,
        "charge_identity": _hash(identity), "receipt_sha256": receipt_sha256, "currency": "USD", "rate_card": rate,
        "basis": "provider_usage_rate_card_estimate", "accounting_status": "unknown" if unknown else "estimated",
        "usage": measured, "cache_write_total": creation, "server_tool_usage": tool_usage,
        "usage_complete": usage_complete, "stop_reason": response.get("stop_reason") or raw.get("stop_reason"),
        "known_estimated_subtotal_usd": subtotal, "estimated_cost_usd": None if unknown else subtotal,
        "actual_cost_usd": None, "unknown_reasons": unknown, "provisional": provisional,
        "reserved_usd": (reservation or {}).get("reserved_usd"), "request_fingerprint": (reservation or {}).get("request_fingerprint")}
    row["entry_id"] = _hash([row["charge_identity"], receipt_sha256, rate, usage_complete])
    return row


def settle(op_id, component, attempt_id, receipt, receipt_sha256=None, *, receipt_artifact=None, guarded=True):
    op = _operation(op_id)
    if not isinstance(receipt, dict):
        raise CostError("A preserved model receipt is required.")
    prior = next((r for r in _events(op["op_id"]) if r["component"] == component and r["attempt_id"] == attempt_id and r["event_type"] == "reservation"), None)
    row = _settlement(op, component, attempt_id, receipt, receipt_sha256 or _hash(receipt), reservation=prior)
    if receipt_artifact:
        row["receipt_artifact"] = {k: receipt_artifact[k] for k in ("name", "sha256") if k in receipt_artifact}
    return _append(op["op_id"], row, guarded=guarded)


def _legacy(op):
    """Read hash-verified saved receipts; never modify their original pricing."""
    ref = op.get("result_ref") or {}
    rows = []
    for kept in ref.get("kept", []):
        name = kept.get("name", "")
        if not re.fullmatch(r"synthesis-receipt(?:[-.]\d+)?\.json", name):
            continue
        raw = producers.artifact_bytes(op["op_id"], name)
        if hashlib.sha256(raw).hexdigest() != kept.get("sha256"):
            continue
        try:
            receipt = json.loads(raw)
        except (ValueError, TypeError):
            continue
        # Historical plain complete_record_once had no cache controls or tools.
        # Do not manufacture a reservation, but record the known request mode.
        request_mode = {"prompt_cache": "not_requested"} if op.get("action_id") == "investigate.opencase.question" else None
        row = _settlement(op, "synthesis", "synthesis:1" if name == "synthesis-receipt.json" else name,
                          receipt, kept["sha256"], reservation=request_mode, provisional=True)
        row["receipt_artifact"] = {"name": name, "sha256": kept["sha256"]}
        rows.append(row)
    return rows


def _source_zero(op):
    if op.get("action_id") != "investigate.opencase.question":
        return None
    ref = op.get("result_ref") or {}
    kept = ref.get("result_artifact")
    if not kept:
        return None
    raw = producers.artifact_bytes(op["op_id"], kept.get("name", ""))
    if hashlib.sha256(raw).hexdigest() != kept.get("sha256"):
        return None
    try:
        result = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if result.get("model_runs") != [] or type(result.get("actual_cost_usd")) not in (int, float) or result["actual_cost_usd"] != 0:
        return None
    return {"schema": SCHEMA, "event_type": "source_cost", "entry_id": _hash([op["op_id"], "collection", kept["sha256"]]),
        "operation_id": op["op_id"], "component": "collection", "attempt_id": "collection:1", "provider": "open_case",
        "accounting_status": "reported_zero", "basis": "upstream_zero_model_collection_contract", "currency": "USD",
        "estimated_cost_usd": 0.0, "known_estimated_subtotal_usd": 0.0, "actual_cost_usd": 0.0,
        "receipt_sha256": kept["sha256"], "usage": [], "provisional": True}


def reconcile(op, *, guarded=True):
    """Explicit append-only correction; safe to repeat. No signed artifact edits."""
    op = _operation(op)
    recorded = _events(op["op_id"])
    aliases = {(r.get("receipt_sha256"), r.get("charge_identity")) for r in recorded if r["event_type"] != "reservation"}
    added = []
    for row in [*_legacy(op), *([_source_zero(op)] if _source_zero(op) else [])]:
        if (row.get("receipt_sha256"), row.get("charge_identity")) in aliases:
            continue
        row = {**row, "provisional": False, "correction": "Append-only accounting derived from the preserved original receipt."}
        added.append(_append(op["op_id"], row, guarded=guarded))
    return {"operation_id": op["op_id"], "recorded": added, "total": total(op)}


def _rows_for(op):
    rows = _events(op["op_id"])
    known = {r.get("receipt_sha256") for r in rows if r["event_type"] != "reservation"}
    rows.extend(r for r in _legacy(op) if r.get("receipt_sha256") not in known)
    source = _source_zero(op)
    if source and source["receipt_sha256"] not in known:
        rows.append(source)
    conn = _connect_ro()
    try:
        dispatched = bool(conn and conn.execute("SELECT 1 FROM operation_events WHERE op_id=? AND kind='stage_intent' AND stage='open_case.synthesis' LIMIT 1", (op["op_id"],)).fetchone())
    finally:
        if conn:
            conn.close()
    state = (op.get("result_ref") or {}).get("synthesis") or {}
    model_record = any(r.get("component") != "collection" for r in rows)
    if (dispatched or state.get("status") in ("running", "complete", "unknown", "truncated", "rejected")) and not model_record:
        rows.append({"schema": SCHEMA, "entry_id": _hash([op["op_id"], "unknown-model"]), "operation_id": op["op_id"],
            "event_type": "unresolved", "component": "synthesis", "attempt_id": "synthesis:1", "accounting_status": "unknown",
            "estimated_cost_usd": None, "actual_cost_usd": None, "known_estimated_subtotal_usd": 0.0, "usage": [],
            "unknown_reasons": ["A model dispatch or outcome exists without a usable preserved receipt."], "provisional": True})
    return rows


def _summary(rows, op_ids):
    charges = _reduced(rows)
    unknown = [r for r in charges if r.get("estimated_cost_usd") is None]
    subtotal = round(sum(r.get("known_estimated_subtotal_usd", 0) for r in charges), 9)
    actual_known = bool(charges) and all(r.get("actual_cost_usd") is not None for r in charges)
    return {"schema": SCHEMA, "currency": "USD", "operation_ids": op_ids, "entries": charges,
        "components": [{"component": c, "known_estimated_subtotal_usd": round(sum(r.get("known_estimated_subtotal_usd", 0) for r in charges if r["component"] == c), 9),
            "accounting_status": "unknown" if any(r.get("estimated_cost_usd") is None for r in charges if r["component"] == c) else "estimated"}
            for c in sorted({r["component"] for r in charges})],
        "accounting_status": "unknown" if unknown or not charges else ("reported_zero" if actual_known else "estimated"),
        "estimated_cost_usd": None if unknown or not charges else subtotal,
        "known_estimated_subtotal_usd": subtotal,
        "actual_cost_usd": round(sum(r["actual_cost_usd"] for r in charges), 9) if actual_known else None,
        "reserved_usd": round(sum(r.get("reserved_usd") or 0 for r in unknown), 9),
        "unknown_components": [r["component"] + ":" + r["attempt_id"] for r in unknown],
        "provisional": any(r.get("provisional") for r in charges),
        "basis": "Provider usage and dated rate cards are estimates; final billed amounts are unavailable for model calls."}


def total(op, ancestry=False):
    op = _operation(op)
    operations, seen = [], set()
    while op and op["op_id"] not in seen:
        seen.add(op["op_id"])
        operations.append(op)
        parent = ((op.get("execution") or {}).get("plan") or {}).get("follow_up_of") or op.get("retry_parent")
        if not ancestry or not parent:
            break
        op = _operation(parent)
    all_rows = [(op, _rows_for(op)) for op in operations]
    result = _summary([row for _, rows in all_rows for row in rows], [op["op_id"] for op in operations])
    result["unaccounted_operation_ids"] = [op["op_id"] for op, rows in all_rows if not rows]
    if result["unaccounted_operation_ids"]:
        result.update(accounting_status="unknown", estimated_cost_usd=None, actual_cost_usd=None)
    return result


def ledger_summary():
    """Settings and operation views share this exact ledger, without writes."""
    conn = _connect_ro()
    if conn is None:
        return _summary([], [])
    try:
        operations = [ops._row(row) for row in conn.execute("SELECT * FROM operations ORDER BY created_at, op_id")]
    finally:
        conn.close()
    all_rows = [(op, _rows_for(op)) for op in operations]
    result = _summary([row for _, rows in all_rows for row in rows], [op["op_id"] for op in operations])
    result["population"] = "Operations with accounting records or preserved Open Case receipts; other operations are listed as unaccounted."
    result["unaccounted_operation_ids"] = [op["op_id"] for op, rows in all_rows if not rows]
    if result["unaccounted_operation_ids"]:
        result.update(accounting_status="unknown", estimated_cost_usd=None, actual_cost_usd=None)
    return result
