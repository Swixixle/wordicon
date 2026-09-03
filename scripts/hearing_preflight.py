"""The Hearing preflight — read-only.

Revision 3 of the interface design proposes that Review becomes a Hearing:
one consequential claim at a time, with its witness, its evidence, the
strongest recorded opposition, and what changes under each ruling. Before
any of that is built, this asks the only honest question: does the record
we actually have contain items that can be presented that way?

It writes nothing. It opens no page. It calls no model. It reads the
owner's record, applies the reviewer's four admission laws to every
unresolved item it can find, and prints what qualifies and what does not
and why. An item that fails is reported, never repaired — the point of a
preflight is to describe the record, not to make it pass.

The laws, as ruled:

  IDENTITY   Reuse an existing stable record id. Never derive identity
             from a title or from wording. If no stable id exists, the
             item fails here — minting one is a build decision, not a
             preflight's to make.
  OPPOSITION Only explicit, mechanically traceable opposition counts: an
             owner-declared contradiction; a prior ruling rejecting,
             correcting or overturning the same claim; two mutually
             exclusive values for the same subject, field, scope and
             time; a contrary analyzer result on the same object and
             question. Keyword similarity, shared vocabulary, Map
             proximity and generated counterarguments do not count.
             Absence is reported as absence, never filled.
  CONSEQUENCE  A ruling must name a real record transition — what becomes
             admitted, operative, quarantined, reopened or silent — and
             where possible the stable ids it touches. No transition
             means recorded-and-silent, not a hearing.
  TEMPLATE   A deterministic, type-specific sentence. No model rewrites
             unresolved material into more persuasive prose.

Usage:  python3 scripts/hearing_preflight.py [--json]
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import wordicon_cli as cli  # noqa: E402

# The six claim types the reviewer named. A type with no template is a
# reason to fail an item, not a reason to invent prose for it.
TEMPLATES = {
    "factual_assertion": "{subject} — the record asserts: {proposition}",
    "admission_or_custody": "{subject} was admitted as {role}; its {field} is recorded as {proposition}",
    "identity_or_relationship": "{subject} and {other} are proposed to be {proposition}",
    "recovery_claim": "{subject} was accepted, but only a receipt survives: {proposition}",
    "design_or_policy_proposal": "{subject} — proposed: {proposition}",
    "correction_of_a_finding": "{subject} — a previous finding is said to be wrong: {proposition}",
}


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        return {"__error__": str(e)} if isinstance(default, dict) else default


def _item(kind, stable_id, id_source, subject, proposition, template, consequence,
          consequence_ids, opposition, opposition_basis, note=""):
    return {"kind": kind, "stable_id": stable_id, "id_source": id_source, "subject": subject,
            "proposition": proposition, "template": template, "consequence": consequence,
            "consequence_ids": consequence_ids, "opposition": opposition,
            "opposition_basis": opposition_basis, "note": note}


def collect():
    """Every unresolved thing the record can name, with the four laws applied.
    Reads only. Each collector is defensive: a missing module or a changed
    field is reported, never guessed around."""
    items, notes = [], []

    # ---- 1. unruled claims crossed from a document -----------------------
    try:
        import library
        crossings = library.load_crossings()
        ruled_by_target = {}
        for c in crossings:
            key = (c.get("document_id", ""), json.dumps(c.get("span_ref") or {}, sort_keys=True))
            if c.get("support") in ("supported", "unsupported", "contradicted"):
                ruled_by_target.setdefault(key, []).append(c)
        for c in crossings:
            if c.get("kind") != "claim" or c.get("support") != "unruled" or c.get("retracted"):
                continue
            key = (c.get("document_id", ""), json.dumps(c.get("span_ref") or {}, sort_keys=True))
            # OPPOSITION: a prior ruling on the same anchored target that
            # contradicted it. Same subject, same field, same scope — a
            # traceable relation, not a resemblance.
            contra = [x for x in ruled_by_target.get(key, []) if x.get("support") == "contradicted"]
            items.append(_item(
                "document_claim", c.get("crossing_id", ""), "crossing_id",
                c.get("document_id", ""), (c.get("owner_text") or "")[:200],
                "factual_assertion",
                "the claim becomes supported / unsupported / contradicted against this anchor; "
                "the crossing's support field transitions from unruled",
                [c.get("crossing_id", "")],
                bool(contra),
                [f"a prior ruling contradicted the same anchored target ({x.get('crossing_id')})" for x in contra]))
    except Exception as e:  # noqa: BLE001
        notes.append(f"document claims could not be read: {e}")

    # ---- 2. unruled claims crossed from a recording ----------------------
    try:
        import library
        for c in library.load_media_crossings():
            if c.get("kind") != "claim" or c.get("support") != "unruled" or c.get("retracted"):
                continue
            items.append(_item(
                "recording_claim", c.get("crossing_id", ""), "crossing_id",
                c.get("media_id", ""), (c.get("owner_text") or "")[:200],
                "factual_assertion",
                "the claim becomes supported / unsupported / contradicted against this timecode",
                [c.get("crossing_id", "")], False, []))
    except Exception as e:  # noqa: BLE001
        notes.append(f"recording claims could not be read: {e}")

    # ---- 3. clinic disagreement proposals awaiting the owner -------------
    try:
        import clinic
        ruled = {r.get("proposal_id") for r in clinic._rows("disagreements.jsonl")}
        rulings = {r.get("proposal_id"): r for r in clinic._rows("disagreements.jsonl")}
        for r in clinic._rows("proposals.jsonl"):
            if r.get("kind") != "disagreement" or r.get("status") != "awaiting_owner":
                continue
            if r.get("proposal_id") in ruled:
                continue
            # OPPOSITION: this item IS an analyzer's contrary result about two
            # passages. Its recorded opposition is a prior owner ruling on the
            # same pair, if one exists.
            pair = tuple(sorted([r.get("anchor_a", ""), r.get("anchor_b", "")]))
            prior = [k for k, v in rulings.items()
                     if tuple(sorted([v.get("anchor_a", ""), v.get("anchor_b", "")])) == pair]
            items.append(_item(
                "clinic_disagreement", r.get("proposal_id", ""), "proposal_id",
                r.get("room_id", ""),
                (r.get("model_says", {}) or {}).get("point", "")[:200] or "the model proposes two passages disagree",
                "correction_of_a_finding",
                "an owner ruling is appended; the proposal leaves awaiting_owner and the two passages "
                "are recorded as disagreeing or not, in the room",
                [r.get("proposal_id", ""), r.get("anchor_a", ""), r.get("anchor_b", "")],
                bool(prior),
                [f"the owner already ruled on the same passage pair ({p})" for p in prior]))
    except Exception as e:  # noqa: BLE001
        notes.append(f"clinic proposals could not be read: {e}")

    # ---- 4. the Recovery Review's open cases -----------------------------
    try:
        import recovery
        for r in recovery.open_cases():
            items.append(_item(
                "recovery_case", r.get("judgment_id", ""), "judgment_id",
                r.get("title", ""), (r.get("note") or "")[:200],
                "recovery_claim",
                "the case leaves the queue by an owner ruling — accepted with a definition the owner "
                "supplies, rejected, revised, or left unresolved; the shelf and the ruling count change",
                [r.get("judgment_id", ""), r.get("trace", "")], False, []))
        for r in recovery.unresolved_cases():
            items.append(_item(
                "recovery_unresolved", r.get("judgment_id", ""), "judgment_id",
                r.get("title", ""), "the owner ruled that not enough survives",
                "recovery_claim",
                "NONE unless new evidence arrives — the owner has already ruled; reopening is his act, "
                "not a due item",
                [r.get("judgment_id", "")], False, [],
                note="already ruled — recorded-and-silent by the reviewer's own rule"))
    except Exception as e:  # noqa: BLE001
        notes.append(f"recovery cases could not be read: {e}")

    # ---- 5. Keeper entries awaiting a ruling -----------------------------
    try:
        import keeper
        ks = keeper.status()
        if ks.get("active") and ks.get("unruled"):
            items.append(_item(
                "keeper_entries", "keeper", "aggregate — NOT a stable per-item id",
                "the Keeper", f"{ks['unruled']} entries await a ruling",
                "factual_assertion",
                "each entry is ruled individually; this row is a count, not a claim",
                [], False, [],
                note="an aggregate, not one claim — it cannot be a hearing item as it stands"))
    except Exception as e:  # noqa: BLE001
        notes.append(f"keeper status could not be read: {e}")

    # ---- 6. open questions kept verbatim ---------------------------------
    try:
        for q in cli.load_open_questions():
            items.append(_item(
                "open_question", q.get("id", "") or q.get("question_id", ""), "question id",
                "an open question", (q.get("text") or "")[:200],
                "design_or_policy_proposal",
                "NONE — the owner chose to keep it as a question; nothing transitions until he opens it",
                [], False, [],
                note="kept by choice, not awaiting judgment"))
    except Exception as e:  # noqa: BLE001
        notes.append(f"open questions could not be read: {e}")

    # ---- 7. identity proposals between instruments (block 107) -----------
    try:
        import federation
        rulings = federation.load_rulings()
        for p in federation.load_proposals():
            state = federation.relationship_state(p["proposal_id"])
            if state != "proposed_same_entity":
                continue
            prior = [r for r in rulings if r.get("proposal_id") == p["proposal_id"]]
            items.append(_item(
                "identity_proposal", p.get("proposal_id", ""), "proposal_id",
                p.get("a", ""), p.get("basis", "")[:200],
                "identity_or_relationship",
                "the owner declares, rejects or leaves unresolved; a declaration makes convergence "
                "available for the pair and seats a ruling in the room",
                [p.get("proposal_id", ""), p.get("a", ""), p.get("b", "")],
                bool(prior),
                [f"an earlier ruling on the same proposal ({r.get('state')})" for r in prior]))
    except Exception as e:  # noqa: BLE001
        notes.append(f"identity proposals could not be read: {e}")

    return items, notes


def judge(items):
    """Apply the four admission laws. Nothing here repairs an item."""
    for it in items:
        fails = []
        if not it["stable_id"]:
            fails.append("no stable record id — identity would have to be minted, which a preflight may not do")
        if "NOT a stable per-item id" in it["id_source"]:
            fails.append("the id is an aggregate, not this claim's own")
        if it["consequence"].startswith("NONE"):
            fails.append("nothing turns on the ruling — recorded-and-silent, not a hearing item")
        if it["template"] not in TEMPLATES:
            fails.append(f"no deterministic template for type {it['template']!r}")
        it["qualifies"] = not fails
        it["fails"] = fails
    return items


def report(items, notes, as_json=False):
    if as_json:
        print(json.dumps({"items": items, "notes": notes}, indent=1, ensure_ascii=False))
        return
    ok = [i for i in items if i["qualifies"]]
    bad = [i for i in items if not i["qualifies"]]
    print("=" * 72)
    print("THE HEARING PREFLIGHT — read-only, no model, nothing written")
    print(f"record: {cli.LOCAL_STATE}")
    print("=" * 72)
    print(f"\n{len(items)} unresolved item(s) found · {len(ok)} qualify · {len(bad)} do not\n")

    print("--- QUALIFY --------------------------------------------------------")
    if not ok:
        print("  none")
    for i in ok:
        print(f"  [{i['kind']}] {i['stable_id']}  (id from {i['id_source']})")
        print(f"      subject     : {i['subject'][:70]}")
        print(f"      template    : {i['template']}")
        print(f"      turns on it : {i['consequence'][:110]}")
        print(f"      touches     : {', '.join([x for x in i['consequence_ids'] if x][:4]) or '—'}")
        print(f"      opposition  : {'; '.join(i['opposition_basis']) if i['opposition'] else 'No recorded opposition.'}")

    print("\n--- DO NOT QUALIFY -------------------------------------------------")
    if not bad:
        print("  none")
    for i in bad:
        print(f"  [{i['kind']}] {i['stable_id'] or '(no id)'} — {'; '.join(i['fails'])}")
        if i["note"]:
            print(f"      note: {i['note']}")

    print("\n--- BY REASON ------------------------------------------------------")
    for reason, test in (
            ("no claim identity", lambda i: any("stable record id" in f or "aggregate" in f for f in i["fails"])),
            ("nothing turns on the ruling", lambda i: any("nothing turns on" in f for f in i["fails"])),
            ("no template", lambda i: any("no deterministic template" in f for f in i["fails"]))):
        n = [i for i in bad if test(i)]
        print(f"  {reason}: {len(n)}" + (f" — {', '.join(sorted({i['kind'] for i in n}))}" if n else ""))
    no_opp = [i for i in ok if not i["opposition"]]
    print(f"  qualify but have NO recorded opposition: {len(no_opp)}"
          + (f" — {', '.join(sorted({i['kind'] for i in no_opp}))}" if no_opp else ""))

    print("\n--- TEMPLATES REQUIRED ---------------------------------------------")
    need = sorted({i["template"] for i in ok})
    for t in need:
        print(f"  {t}: {TEMPLATES[t]}")
    unused = sorted(set(TEMPLATES) - set(need))
    print(f"  not required by this record: {', '.join(unused) or 'none'}")

    print("\n--- WOULD ONLY QUALIFY BY INFERENCE --------------------------------")
    print("  none — no collector here uses keyword similarity, shared vocabulary,")
    print("  Map proximity, or a generated counterargument. Opposition is read")
    print("  from explicit relations only, and its absence is printed as absence.")

    if notes:
        print("\n--- COULD NOT BE READ ----------------------------------------------")
        for n in notes:
            print(f"  {n}")
    print()


if __name__ == "__main__":
    _items, _notes = collect()
    report(judge(_items), _notes, as_json="--json" in sys.argv)
