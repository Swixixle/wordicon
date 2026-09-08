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


def seed_vault_states():
    """The four Vault states, produced by the REAL vault.status().

    block 117. Every journey mocked this endpoint with one healthy literal, so
    the red path had never rendered in a browser and renaming a field the
    producer emits would have left the strip permanently green. These four
    dicts are captured from vault.status() itself, in a THROWAWAY directory —
    the owner's vault is never touched, read or configured here — so a
    renamed or dropped field breaks the journey the day it changes.
    """
    import tempfile
    import vault  # noqa: E402
    out = {}
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="vault_states_"))
    keep = (vault._DIRTY.get("since"), vault._LAST_FAILURE.get("msg"))
    try:
        # NOT INITIALISED — no config at all.
        _real_cfg = vault.load_config
        vault.load_config = lambda *a, **k: {}
        vault._DIRTY["since"] = None
        vault._LAST_FAILURE["msg"] = ""
        out["uninitialised"] = vault.status()

        vault.load_config = lambda *a, **k: {"destination": str(tmp)}
        # HEALTHY — initialised, nothing dirty, nothing failed.
        out["healthy"] = vault.status()
        # DIRTY — unsealed changes, but under the ceiling, so not red yet.
        vault._DIRTY["since"] = __import__("time").monotonic() - 5
        out["dirty"] = vault.status()
        # STALE — dirty for longer than the ceiling, which turns red by itself.
        vault._DIRTY["since"] = __import__("time").monotonic() - (vault.CEILING_SECONDS + 60)
        out["stale"] = vault.status()
        # FAILED — a real recorded failure message.
        vault._DIRTY["since"] = None
        vault._LAST_FAILURE["msg"] = "the last seal did not complete"
        out["failed"] = vault.status()
    finally:
        vault.load_config = _real_cfg
        vault._DIRTY["since"], vault._LAST_FAILURE["msg"] = keep
    (DIR / "vault_states.json").write_text(json.dumps(out, indent=1))
    return {k: {"stale_red": v.get("stale_red"), "failure": bool(v.get("failure")),
                "initialized": v.get("initialized")} for k, v in out.items()}


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


def seed_partial():
    """A REAL partial deep run (block 119), through the real path.

    Not hand-authored JSON, for the reason stated above: the last
    hand-authored fixture here described a shape the server never emits and
    thirty-one checks passed against it. This drives run_deep with a
    gateway that answers the first component and dies on every one after —
    which is the shape of the run that prompted this block — so what the
    browser opens is what a real partial run writes, completion state,
    scoped counts, retry seeds and all."""

    class _DiesAfterOne(cli.MockGateway):
        name = "mock"

        def __init__(self):
            self.gen = 0

        def complete(self, prompt):
            if str(prompt).startswith("You are the generation stage"):
                self.gen += 1
                if self.gen > 1:
                    raise RuntimeError("Request timed out or interrupted.")
            if str(prompt).startswith("You are the anchor-support stage"):
                # Since block 123b the server takes a carry's standing from
                # the RECORD, so the record the carry journey reads must
                # hold the standings that journey tests — a partial fit and
                # a contradicted one — and the mock's default answer is
                # "supported" for everything. These are the mock's own
                # keyed answers, keyed here on the candidate's title; the
                # shaping (verdict flipped to "contradicted", the caught-by
                # note) is the real path's, not this file's.
                if "Title: The Refusenik Posture" in prompt:
                    return json.dumps({
                        "support": "partial",
                        "note": "The description is licensed; the causal claim is not.",
                        "deciding_anchor_words": "pretending",
                        "deciding_claim_words": "without pretending the exit resolves it"})
                if "Title: Threshold Grief" in prompt:
                    return json.dumps({
                        "support": "contradicted",
                        "note": "The anchor is a person pretending; the claim is a doorway "
                                "with nobody in it.",
                        "deciding_anchor_words": "pretending",
                        "deciding_claim_words": "standing at a boundary"})
            return super().complete(prompt)

    r = cli.run_deep(
        "A passage about pretending while poor, and guilt at arriving, and the slow "
        "descent that follows, and what the word demon was doing in it.",
        _DiesAfterOne(), interactive=False)
    # The server's own shaping, imported rather than imitated. The rule at
    # the top of this file is that a fixture must not describe a shape the
    # server never emits — a hand-rolled candidate list broke exactly that
    # way here, and the journey crashed inside renderCandidateCard on a
    # key the real path always supplies.
    import server as _srv
    groups = []
    for g in r["groups"]:
        base = {k: g.get(k) for k in
                ("label", "gist", "anchor", "anchor_verified", "anchor_near_miss",
                 "recurrence_unsupported", "constraint_beyond_anchor", "source_check",
                 "constraints", "background", "grounding")}
        if g.get("failed"):
            groups.append({**base, "failed": True, "error": g.get("error", ""),
                           "failure_explanation": g.get("failure_explanation", ""),
                           "forge_input": g.get("forge_input", "")})
            continue
        res = g["result"]
        groups.append({**base, "trace_id": res["trace_id"],
                       "candidates": _srv._shape_candidates(res),
                       "receipt_id": res["private_receipt"]["receipt_id"],
                       "summary": cli.summary_line(res["private_receipt"], res["candidates"]),
                       "metrics": res.get("metrics", {})})
    result = {"mode": "deep", "source_text": r["source_text"], "attack": r["attack"],
              "gesture": r.get("gesture", "trial"), "partial": r["partial"],
              "n_failed": r["n_failed"], "n_components": r["n_components"],
              "n_completed": r["n_completed"],
              "attempts": r.get("attempts") or [],
              "attempt_summary": r.get("attempt_summary") or {},
              "pending_roads": r.get("pending_roads") or [],
              "groups": groups, "trace_id": r["trace_id"], "gateway": "mock"}
    rec = cli.record_composite_run("deep", result, r["source_text"],
                                   trace_id=r["trace_id"])
    ids = {"deepPartial": r["trace_id"], "recorded": bool(rec.get("recorded")),
           "n_components": r["n_components"], "n_completed": r["n_completed"]}
    assert r["n_failed"] >= 1 and r["n_completed"] >= 1, (
        f"the partial fixture is not partial: {ids}")
    # The completed component's own trace — what a candidate card inside
    # this result actually carries (block 123b: the card's trace is the
    # component's, whose record holds the dissection's gist, not the
    # draft) — and a rabbithole opened FROM that card, the way the page
    # opens one, so a thread carried from it has a recorded road back:
    # sprout → component → this deep run → the draft.
    done = [g for g in groups if not g.get("failed")]
    ids["component"] = done[0]["trace_id"]
    cand = done[0]["candidates"][0]
    bff = cand.get("bone_flesh_friction") or {}
    sp = cli.run_sprout({"title": bff.get("title") or cand.get("title") or "",
                         "definition": (bff.get("flesh") or {}).get("definition") or "",
                         "concept_id": bff.get("concept_id") or ""},
                        cli.MockGateway(), parent_trace_id=ids["component"])
    ids["sproutFromComponent"] = sp["trace_id"]
    (DIR / "partial.json").write_text(json.dumps(ids))
    return ids


def seed_map():
    """The record the Map · focus journey opens — every road written by the
    real road writers against the offline gateway, so what the browser reads
    is what the real path writes. Two manipulations, each the only honest
    way to manufacture a state the writers can no longer produce:

      · a pre-104 row: one real parallels road has its origin and producer
        keys removed after the write (that is what a legacy row IS);
      · the eighteen's state: one real sprout's receipt is deleted after
        the write, so its roads cite a receipt that is not there; for a
        second sprout the snapshot is deleted as well, which is exactly the
        state of the eighteen roads in the owner's record.

    And one pre-tracking row: a real road whose created_at is moved before
    the tracked history, so the page has an "issuer not recorded" road to
    render — the fixture's date, never the page's; the page synthesizes no
    time and this fixture is the only place a time is written by hand."""
    g = cli.MockGateway()
    ids = {}
    text = "A passage for the map: a lantern kept lit for a debt nobody named, and the quiet after the naming."
    f = cli.run("forge", text, g, interactive=False)
    ids["forge"] = f["trace_id"]
    snap = json.loads((cli.RESULTS_DIR / f"{f['trace_id']}.json").read_text())
    bff = (snap["candidates"][0].get("bff") or {})
    cand = {"title": bff.get("title", ""), "definition": (bff.get("flesh") or {}).get("definition", ""),
            "concept_id": bff.get("concept_id", ""), "central_contradiction": (bff.get("bone") or {}).get("central_contradiction", "c"),
            "axiom": (bff.get("bone") or {}).get("axiom", "a"), "plain_gloss": (bff.get("flesh") or {}).get("plain_gloss", "g")}
    assert cand["title"] and cand["concept_id"], f"the offline forge no longer yields a concept-keyed candidate: {cand}"
    ids["seedTitle"] = cand["title"]
    ids["seedKey"] = cli.node_concept(cand["concept_id"], cand["title"])["key"]
    # the seed's ring: two sprouts (the second reviews Cassandra differently,
    # so the same target carries two verdicts — a dispute), two refracts (the
    # same terms reached again), an archetype, a revise, and a declared road

    class _ReviewsDifferently(cli.MockGateway):
        def complete(self, prompt: str) -> str:
            out = super().complete(prompt)
            if prompt.startswith("You are the sprout-review stage"):
                d = json.loads(out)
                for r in d.get("reviews") or []:
                    if r.get("index") == 0:
                        r["verdict"] = "strained"; r["note"] = "On a second reading the attribution leans on the divergence more than the resemblance."
                return json.dumps(d)
            return out
    # A trace id is the hash of the input text and the SECOND (wordicon_cli
    # _now() has no finer grain), so two runs on one candidate inside one
    # second share an id and the second overwrites the first's receipt and
    # snapshot. This fixture waits for the clock; the defect is reported in
    # the Map Focus build report, not repaired here.
    def next_second():
        import time as _t
        was = cli._now()
        while cli._now() == was:
            _t.sleep(0.05)
    next_second()   # the partial fixture sprouts this same mock title moments earlier
    sp1 = cli.run_sprout(cand, g, parent_trace_id=f["trace_id"])
    next_second(); sp2 = cli.run_sprout(cand, _ReviewsDifferently())
    rf1 = cli.run_refract(cand, g)
    next_second(); rf2 = cli.run_refract(cand, g)
    ar = cli.run_archetype(cand, g)
    rv = cli.run_revise(dict(cand), g)
    ids.update({"sprout1": sp1["trace_id"], "sprout2": sp2["trace_id"], "refract1": rf1["trace_id"],
                "refract2": rf2["trace_id"], "archetype": ar["trace_id"], "revise": rv["trace_id"]})
    ow = cli.build_overworld()
    keys = {it["key"] for r in ow["runs"] for it in r["items"]}
    cassandra = cli.node_external("Cassandra", "Greek myth (Aeschylus, Agamemnon)")
    assert cassandra["key"] in keys, "the offline sprout no longer reaches Cassandra"
    decl = cli.declare_road({"kind": "concept", "key": ids["seedKey"], "label": cand["title"]},
                            {"kind": "external", "key": cassandra["key"], "label": cassandra["label"]},
                            "answers", "the lantern is kept lit for what the prophecy names", keys)
    ids["declaredId"] = decl["declaration_id"]
    ids["disputeTargetKey"] = cassandra["key"]
    # a legacy title-keyed place: a sprout from a candidate with no concept id
    lg = cli.run_sprout({"title": "Lantern Debt", "definition": "a debt kept lit rather than paid"}, g)
    ids["legacySprout"] = lg["trace_id"]
    ids["legacyKey"] = cli.node_word("Lantern Debt")["key"]
    # the eighteen's state, twice: a sprout whose receipt is gone, and one
    # whose receipt and snapshot are both gone
    next_second(); sp3 = cli.run_sprout(cand, g)
    (cli.RECEIPTS_DIR / f"receipt_{sp3['trace_id']}.json").unlink()
    ids["missingReceipt"] = sp3["trace_id"]
    next_second(); sp4 = cli.run_sprout(cand, g)
    (cli.RECEIPTS_DIR / f"receipt_{sp4['trace_id']}.json").unlink()
    (cli.RESULTS_DIR / f"{sp4['trace_id']}.json").unlink()
    ids["missingBoth"] = sp4["trace_id"]
    # a pre-104 row and a pre-tracking row, from real rows of the first sprout
    rows = [json.loads(l) for l in cli.EDGES_LOG.read_text().splitlines() if l.strip()]
    par = [r for r in rows if r.get("run_trace_id") == sp1["trace_id"] and r.get("rel") == "parallels"
           and (r.get("source") or {}).get("key") == ids["seedKey"]]
    assert len(par) >= 2, "the first sprout wrote fewer than two parallels"
    legacy_id, pretrack_id = par[0]["edge_id"], par[1]["edge_id"]
    out_rows = []
    for r in rows:
        if r.get("edge_id") == legacy_id:
            r = {k: v for k, v in r.items() if k not in ("origin", "producer")}
        elif r.get("edge_id") == pretrack_id:
            r = {k: v for k, v in r.items() if k not in ("origin", "producer")}
            r["run_trace_id"] = "trace_cli_gone_" + r["run_trace_id"][-6:]   # its snapshot is not there either
            r["created_at"] = "2026-08-20T12:00:00+00:00"                     # before the tracked history
        out_rows.append(r)
    cli.EDGES_LOG.write_text("".join(json.dumps(r) + "\n" for r in out_rows))
    ids["legacyEdge"] = legacy_id
    ids["pretrackEdge"] = pretrack_id
    assert len({sp1["trace_id"], sp2["trace_id"], sp3["trace_id"], sp4["trace_id"], rf1["trace_id"], rf2["trace_id"]}) == 6, \
        "two runs shared a trace id — the fixture's clock wait failed"
    (DIR / "map.json").write_text(json.dumps(ids))
    return ids


if __name__ == "__main__":
    marker = STATE / ".seeded"
    if marker.exists():
        print(json.dumps({"entrance": "already seeded", "pre_wiring": seed_pre_wiring(),
                          "epistemic": seed_epistemic(), "partial": seed_partial(),
                          "vault_states": seed_vault_states(), "map": seed_map()}))
    else:
        out = seed_entrance()
        marker.write_text("1")
        print(json.dumps({"entrance": out, "pre_wiring": seed_pre_wiring(),
                          "epistemic": seed_epistemic(), "partial": seed_partial(),
                          "vault_states": seed_vault_states(), "map": seed_map()}))
