"""Seed the scratch record the journeys read. Sanitized fixtures only —
public fixture titles ("Parrot Box", "Threshold Grief"), the neutral
duplicate-title fixture ("Common Ground"), and invented titles for the
pre-wiring shapes ("Lantern Debt", "Hinge Silence", "Ledger Fog"). Runs
against JOURNEY_STATE (never the real store). Idempotent."""
import os
import sys
import json
import pathlib
import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import wordicon_cli as cli  # noqa: E402
DIR = pathlib.Path(os.environ.get("JOURNEY_DIR", "/tmp/anat"))
STATE = pathlib.Path(os.environ.get("JOURNEY_STATE", str(DIR / "state")))
STATE.mkdir(parents=True, exist_ok=True)
for _n in ("JUDGMENTS_LOG", "RECEIPTS_DIR", "RESULTS_DIR", "ACCEPTED_CONCEPTS_PATH", "EDGES_LOG", "WARPS_LOG", "WARP_NOTES_LOG",
           "BENCH_CORRECTIONS", "CONCEPT_NAMES_LOG", "BENCH_DIR", "INPUTS_LOG", "WAYFINDER_LOG",
           "DEFINITION_EVENTS_LOG", "ENCOUNTER_SWITCH_LOG", "ENCOUNTERS_LOG",   # block 104
           "OPEN_QUESTIONS_LOG"):   # block 105
    setattr(cli, _n, STATE / str(getattr(cli, _n)).split("/")[-1])
cli.LOCAL_STATE = STATE
(STATE / "receipts").mkdir(exist_ok=True)
(STATE / "results").mkdir(exist_ok=True)
import library  # noqa: E402
import clinic  # noqa: E402
import server  # noqa: E402
import gate  # noqa: E402


def stamp(days_ago):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)).isoformat()


def receipt(trace, title, days_ago, op="forge"):
    cli.RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    (cli.RECEIPTS_DIR / f"{trace}.json").write_text(json.dumps({
        "trace_id": trace, "receipt_id": "rcpt_" + trace, "operation": op,
        "created_at": stamp(days_ago), "candidates": [{"title": title}],
        "input_preview": "fixture", "titles": [title]}))


def seed_entrance():
    out = {}
    with server.app.test_client() as c:
        c.set_cookie(gate.SESSION_COOKIE, gate.issue_session("fixtures")["token"])
        # two concepts that share a title, each ruled on with its own id
        receipt("tr_fix1", "Common Ground", 2)
        r = c.post("/api/judge", json={"trace_id": "tr_fix1", "candidate_title": "Common Ground", "decision": "a",
                                       "concept_id": "concept_fix00000001",
                                       "definition": "the part of a disagreement both sides would sign", "note": ""})
        assert r.status_code == 200, r.get_data(as_text=True)
        receipt("tr_fix2", "Common Ground", 5)
        r = c.post("/api/judge", json={"trace_id": "tr_fix2", "candidate_title": "Common Ground", "decision": "a",
                                       "concept_id": "concept_fix00000002",
                                       "definition": "the floor a room agrees to stand on before arguing", "note": "the tension line overreaches"})
        assert r.status_code == 200, r.get_data(as_text=True)
        # a run that was never ruled on: must NOT appear in Continue
        receipt("tr_fix3", "Threshold Grief", 1)
        # legacy rulings with no concept id: one ambiguous title, one unmatched
        with open(cli.JUDGMENTS_LOG, "a") as f:
            f.write(json.dumps({"id": "jdg_legacy_1", "decision": "accepted", "candidate_text": "Common Ground",
                                "originating_operation": "tr_fix1", "decision_source": "owner", "confidence": 1.0}) + "\n")
            f.write(json.dumps({"id": "jdg_legacy_2", "decision": "rejected", "candidate_text": "Parrot Box",
                                "originating_operation": "tr_legacy", "decision_source": "owner", "confidence": 1.0}) + "\n")
        # a document with a claim whose support is unruled
        text = ("Readiness screening precedes every liberation attempt. A trial of spontaneous breathing follows "
                "the screen. The policy requires a physician order before the trial begins.")
        ing = library.ingest(text.encode("utf-8"), "policy-notes.txt", source="fixture", title="Policy notes (fixture)")
        rep = library.load_representation(ing["representation_id"])
        r = c.post("/api/library/crossing", json={"kind": "claim", "representation_id": ing["representation_id"],
                                                  "start_path": "0.0.0", "start_offset": 0, "end_path": "0.0.0", "end_offset": 20,
                                                  "owner_text": "screening comes first, by policy"})
        assert r.status_code == 200, r.get_data(as_text=True)
        out["representation_id"] = ing["representation_id"]; out["document_id"] = ing["document_id"]
        # a Clinic room with one seat filled
        room = clinic.create_room("Adult Ventilator Liberation (fixture)")
        ing2 = library.ingest(b"Current guidance: screen daily; attempt a trial when the screen passes.", "guideline.txt",
                              source="fixture", title="Current guideline (fixture)")
        src = clinic.declare_source(ing2["document_id"], ing2["representation_id"], ing2["blob_id"],
                                    role="professional_guideline", issuer="a guideline body", title="Current guideline (fixture)",
                                    published_at="2023", effective_from="not_applicable", review_or_expiry="unknown", status="current")
        clinic.add_to_room(room["room_id"], src["source_id"])
        out["room_id"] = room["room_id"]
        # the recovery review queue, in the real store's shape (block 103): an
        # accepted title-only judgment, a receipt with the run's titles, no
        # snapshot, no shelf entry; the queue row names the judgment
        for i, t in enumerate(("Quorum Pedagogy", "Gutter Loop")):
            tr, jid = f"trace_cli_oldfix{i}", f"jdg_cli_candidate_oldfix{i}"
            with open(cli.JUDGMENTS_LOG, "a") as f:
                f.write(json.dumps({"id": jid, "object_type": "judgment", "decision": "accepted", "candidate_text": t,
                                    "originating_operation": tr, "decision_source": "owner", "confidence": 1.0,
                                    "review_status": "unreviewed", "scope": "local_to_concept"}) + "\n")
            (cli.RECEIPTS_DIR / f"receipt_{tr}.json").write_text(json.dumps({
                "trace_id": tr, "receipt_id": "rcpt_" + tr, "operation": "forge", "created_at": stamp(9),
                "candidates": [{"title": t}, {"title": "Sibling A"}, {"title": "Sibling B"}], "sources": [{"id": "s1"}, {"id": "s2"}],
                "rejections": [], "engine_version": "cli-0.2.0", "kernel_version": 1,
                "model_calls": [{"gateway": "anthropic", "is_external": True}], "input_hash": "fixture"}))
            with open(cli.LOCAL_STATE / "recovery_review_queue.jsonl", "a") as f:
                f.write(json.dumps({"title": t, "trace": tr, "judgment_id": jid, "status": "needs_owner_ruling",
                                    "note": "accepted; no lexicon entry; no results snapshot survives — needs owner ruling",
                                    "queued_at": stamp(3)}) + "\n")
        # the epoch, as the owner declared it (block 103)
        cli.declare_epoch("development_and_calibration", declared_by="owner", note="journey fixture",
                          first_record_at=stamp(10))
    return out



def legacy(eid, name):
    return {"id": eid, "object_type": "concept", "name": name, "definition": "an older definition, kept as written",
            "status": "accepted", "accepted_from": "tr_pre_wiring", "accepted_at": "2026-08-20T00:00:00+00:00",
            "supporting_claims": [], "governing_constraints": [], "related_mechanisms": [], "version": 1}


def row(title, decision, trace, cid=""):
    r = {"id": f"jdg_{trace}", "decision": decision, "candidate_text": title, "originating_operation": trace,
         "decision_source": "owner", "confidence": 1.0}
    if cid:
        r["concept_id"] = cid
    return r




def seed_pre_wiring():
    """The real store's shape: a concept-aware judgment beside a title-keyed
    shelf entry (bridge), beside two entries sharing a title (ambiguous),
    and one with no entry at all (title-only row)."""
    existing = json.loads(cli.ACCEPTED_CONCEPTS_PATH.read_text()) if cli.ACCEPTED_CONCEPTS_PATH.exists() else []
    if any(e.get("id") == "acc_bridgefix" for e in existing):
        return "already seeded"
    existing += [legacy("acc_bridgefix", "Lantern Debt"),
                 legacy("acc_sibfix", "Hinge Silence"),
                 dict(legacy("acc2_sibfixother", "Hinge Silence"), concept_id="concept_fix_sib_other")]
    cli.ACCEPTED_CONCEPTS_PATH.write_text(json.dumps(existing, indent=2))
    receipt("tr_fix_bridge", "Lantern Debt", 0.5)
    receipt("tr_fix_sib", "Hinge Silence", 0.6)
    receipt("tr_fix_fallback", "Ledger Fog", 0.7)
    with open(cli.JUDGMENTS_LOG, "a") as f:
        f.write(json.dumps(row("Lantern Debt", "accepted", "tr_fix_bridge", "concept_fix_bridge")) + "\n")
        f.write(json.dumps(row("Hinge Silence", "accepted", "tr_fix_sib", "concept_fix_sib")) + "\n")
        f.write(json.dumps(row("Ledger Fog", "accepted", "tr_fix_fallback", "concept_fix_fallback")) + "\n")
    return "seeded"


def seed_epistemic():
    """Two real runs, written by the real writers, for the epistemic journey.

    Deliberately NOT hand-authored JSON. The last hand-authored fixture in
    this directory described a job shape the server has never emitted, and
    thirty-one checks passed against it for as long as it stood. These call
    the same run_* functions the app calls, against the offline gateway, so
    what the browser opens is what the real path writes."""
    ids = {}
    g = cli.MockGateway()
    # a sprout: carries the review call's acquisition record and the
    # reviewer's own prose
    sp = cli.run_sprout({"title": "Threshold Grief",
                         "definition": "the grief that belongs to a door, not a loss"}, g)
    ids["sprout"] = sp["trace_id"]
    # a decompose: carries candidate cards, their example sentences, and the
    # grounded/well-made rows
    dc = cli.run_decompose("A passage about pretending while poor, and guilt at arriving.",
                            g, interactive=False)
    ids["decompose"] = dc.get("trace_id") or ""
    # The two groups are named by WHAT THEY ARE, read back out of the
    # snapshots the run just wrote — never by index. An index would be a
    # second place where "the second group is the unanchored one" is
    # asserted, and the day the mock's order changes the journey would keep
    # passing against the wrong card.
    # run_decompose's RETURN value carries groups with no trace_id — the id
    # is written into the persisted parent, not into the dict handed back.
    # Read the parent from disk rather than trusting the two to match.
    parent = json.loads((cli.RESULTS_DIR / f"{ids['decompose']}.json").read_text())
    for grp in parent.get("groups") or []:
        t = grp.get("trace_id") or ""
        snap = cli.RESULTS_DIR / f"{t}.json"
        if not t or not snap.exists():
            continue
        for row in json.loads(snap.read_text()).get("candidates") or []:
            st = ((row.get("bff") or row).get("anchor_integrity") or {}).get("status")
            if st in ("exact", "normalized"):
                ids.setdefault("groupOk", t)
            elif st in ("not_found", "near", "absent"):
                ids.setdefault("groupFailed", t)
    assert "groupOk" in ids and "groupFailed" in ids, (
        "the offline decompose no longer produces both an anchored and an unanchored "
        f"group, so the epistemic journey has nothing to compare: {ids}")
    (DIR / "epistemic.json").write_text(json.dumps(ids))
    return ids


if __name__ == "__main__":
    marker = STATE / ".seeded"
    if marker.exists():
        print(json.dumps({"entrance": "already seeded", "pre_wiring": seed_pre_wiring(),
                          "epistemic": seed_epistemic()}))
    else:
        out = seed_entrance()
        marker.write_text("1")
        print(json.dumps({"entrance": out, "pre_wiring": seed_pre_wiring(),
                          "epistemic": seed_epistemic()}))
