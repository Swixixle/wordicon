"""The Deflate door into Go deeper (2026-10-17, ADR extraction W1 follow-on (b)).

An imported, VERIFIED deposition's reading or claim becomes the frozen subject
of a focused exploration, resolved from custody — the exact bytes, re-hashed
and re-verified against the owner's currently pinned keys at every resolution
(prepare, Start, and every follow-up) — never from client prose. The evidence
labels travel intact, and the signature law travels with them: verification
establishes origin and integrity, custody, never truth.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import deeper
import federation
import wordicon_cli as cli

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "federation" / "deflate.exemplar.deposition.json"
PUBKEY = Path(__file__).resolve().parent / "fixtures" / "federation" / "deflate.fixture.pub.b64"


@pytest.fixture
def store(tmp_path, monkeypatch):
    for name, path in (("LOCAL_STATE", tmp_path), ("RESULTS_DIR", tmp_path / "results"),
                       ("RECEIPTS_DIR", tmp_path / "receipts"), ("EDGES_LOG", tmp_path / "edges.jsonl")):
        monkeypatch.setattr(cli, name, path)
    cli.RESULTS_DIR.mkdir()
    federation.register_connector("deflate-test", "deflate", "http://127.0.0.1:1", dev_loopback=True, by="tests")
    federation.pin_key("deflate-test", PUBKEY.read_text().strip(), label="fixture", by="tests")
    body = FIXTURE.read_bytes()
    out = federation.import_package(federation.get_connector("deflate-test"), body, how="pasted")
    assert (out.get("verification") or {}).get("ok") is True
    env = json.loads(body)
    return {"deposition_id": out["deposition_id"], "env": env,
            "claim_id": env["payload"]["claims"]["claims"][0]["id"],
            "passage_id": env["payload"]["claims"]["passages"][0]["id"],
            "held_id": env["payload"]["claims"]["passagesHeld"][0]["id"]}


def subject(store, ref):
    return {"kind": "deposition", "deposition_id": store["deposition_id"], "item_ref": ref}


class FixtureGateway(cli.MockGateway):
    pass


# ---- resolution: custody first, producer's labels intact --------------------

def test_claim_context_carries_custody_verbatim_lines_and_labels(store):
    ctx = deeper.build_context(subject(store, f"deflate:claim:{store['claim_id']}"), {})
    root = ctx["root"]
    dep = root["selection"]["deposition"]
    claim = store["env"]["payload"]["claims"]["claims"][0]
    assert ctx["parent_trace_id"] == ""
    assert ctx["focus"]["title"] == claim["text"]
    assert dep["item"]["kind"] == "claim" and dep["item"]["text"] == claim["text"]
    assert dep["item"]["status_attributed_to"].startswith("Deflate's export's own meaning")
    assert dep["verification"]["ok"] is True
    assert "custody, never the truth" in dep["verification"]["establishes"]
    # the transcript lines are the producer's verbatim text at the claim's stated turns
    t0, t1 = claim["turns"]
    expected = store["env"]["payload"]["transcript"]["text"].split("\n")[t0 - 1:t1]
    assert dep["transcript"]["lines_at_turns"] == expected
    assert dep["transcript"]["sha256"] == store["env"]["payload"]["transcript"]["sha256"]
    assert f"turns {t0}–{t1}" in dep["transcript"]["location"]
    assert "never a public-source verification" in dep["transcript"]["lines_meaning"]
    assert root["source_standing"]["kind"] == "federated_deposition"
    assert root["source_standing"]["verified"] is False and root["source_standing"]["source_admitted"] is False
    assert "custody, never truth" in root["source_standing"]["note"]


def test_passage_context_and_default_question(store):
    ctx = deeper.build_context(subject(store, f"deflate:passage:{store['passage_id']}"), {})
    item = ctx["root"]["selection"]["deposition"]["item"]
    assert item["kind"] == "reading"
    assert item["attributed_to"].endswith("not independent validation")
    assert "'matched' means the quoted words are in the saved transcript" in item["quotes_meaning"]
    assert "do not treat them as publicly verified" in ctx["question"].lower()


def test_quoteless_evidence_goal_full_allowance(store):
    # a deposition's transcript line is custody text, not a public-source
    # quote target: the evidence goal starts quoteless, so research runs the
    # full allowance on the question instead of stopping on a wording match
    ctx = deeper.build_context(subject(store, f"deflate:claim:{store['claim_id']}"), {})
    assert ctx["research_goal"] == {"kind": "starting_selection", "target_quote": "", "question": ctx["question"]}
    assert ctx["research_resume"]["sources"] == [] and ctx["research_resume"]["leads"] == []


def test_roots_are_stable_across_resolutions(store):
    # a follow-up compares the re-resolved root for EQUALITY with the frozen
    # one, so resolution must be deterministic: no clock, no counter
    ref = f"deflate:claim:{store['claim_id']}"
    a = deeper.build_context(subject(store, ref), {})["root"]
    b = deeper.build_context(subject(store, ref), {})["root"]
    assert a == b


# ---- refusals, each by name --------------------------------------------------

def test_refusals_by_name(store):
    cases = (
        (subject(store, "deflate:claim:absent"), "no claim"),
        (subject(store, f"deflate:passage:{store['held_id']}"), "no passage"),   # held stays held: not resolvable
        ({"kind": "deposition", "deposition_id": "dep_absent", "item_ref": f"deflate:claim:{store['claim_id']}"}, "in custody"),
        (subject(store, "evil:claim:x"), "producer ref"),
        ({"kind": "deposition", "deposition_id": store["deposition_id"]}, "producer ref"),
    )
    for subj, needle in cases:
        with pytest.raises(ValueError) as e:
            deeper.build_context(subj, {})
        assert needle in str(e.value), (subj, str(e.value))


def test_unverified_import_refused(store, tmp_path):
    federation.register_connector("deflate-stray", "deflate", "http://127.0.0.1:2", dev_loopback=True, by="tests")
    body = FIXTURE.read_bytes().replace(b"The Exemplar Hour", b"The Altered Hour")
    out = federation.import_package(federation.get_connector("deflate-stray"), body, how="pasted")
    assert not (out.get("verification") or {}).get("ok")
    with pytest.raises(ValueError) as e:
        deeper.build_context({"kind": "deposition", "deposition_id": out["deposition_id"],
                              "item_ref": f"deflate:claim:{store['claim_id']}"}, {})
    assert "does not verify against a pinned key" in str(e.value)


def test_tampered_custody_refused(store):
    dep = federation.get_deposition(store["deposition_id"])
    blob = federation.blobs_dir() / dep["sha256"]
    original = blob.read_bytes()
    try:
        blob.write_bytes(original.replace(b"15%", b"51%", 1))
        with pytest.raises(ValueError) as e:
            deeper.build_context(subject(store, f"deflate:claim:{store['claim_id']}"), {})
        assert "custody check failed" in str(e.value)
    finally:
        blob.write_bytes(original)


def test_unpinned_key_refuses_at_start_even_after_prepare(store):
    # the pinned keys are live authority: a verdict taken at prepare is not
    # inherited by Start — unpinning between the two refuses the dispatch
    ctx = deeper.build_context(subject(store, f"deflate:claim:{store['claim_id']}"), {})
    kid = ctx["root"]["selection"]["deposition"]["verification"]["key_id"]
    federation.unpin_key("deflate-test", kid, by="tests")
    with pytest.raises(ValueError) as e:
        deeper.run(ctx, FixtureGateway())
    assert "does not verify against a pinned key" in str(e.value)
    federation.pin_key("deflate-test", PUBKEY.read_text().strip(), label="fixture", by="tests")
    result = deeper.run(ctx, FixtureGateway())   # same key id re-pinned: the frozen root still matches
    assert result["trace_id"]


# ---- the run and its records --------------------------------------------------

def test_run_records_preserve_the_originating_reading(store):
    ref = f"deflate:claim:{store['claim_id']}"
    ctx = deeper.build_context(subject(store, ref), {})
    result = deeper.run(ctx, FixtureGateway())
    assert result["trail_root_id"] == store["deposition_id"]
    assert result["source_standing"]["kind"] == "federated_deposition"
    assert result["context"]["root"]["item_ref"] == ref
    assert result["trail"][0] == {"deposition_id": store["deposition_id"], "item_ref": ref,
                                  "title": ctx["focus"]["title"], "kind": "deposition"}
    receipt = json.loads((cli.RECEIPTS_DIR / f"{result['receipt_id']}.json").read_text(encoding="utf-8"))
    assert receipt["warnings"][0] == deeper.DEPOSITION_SOURCE_NOTE
    # the lineage edge continues from the deposition itself, not from a blank run
    edges = [json.loads(l) for l in Path(cli.EDGES_LOG).read_text(encoding="utf-8").splitlines()]
    mine = [e for e in edges if e.get("rel") == "continued_from" and (e.get("target") or {}).get("key") == result["trace_id"]]
    assert mine and mine[0]["source"]["kind"] == "deposition" and mine[0]["source"]["key"] == store["deposition_id"]


def test_followup_re_resolves_the_deposition_root(store):
    ctx = deeper.build_context(subject(store, f"deflate:claim:{store['claim_id']}"), {})
    first = deeper.run(ctx, FixtureGateway())
    ctx2 = deeper.build_context({"kind": "result", "trace_id": first["trace_id"]},
                                {"question": "What would bear against this claim?"})
    assert ctx2["root"]["deposition_id"] == store["deposition_id"]
    assert len(ctx2["ancestry"]) == 1 and ctx2["ancestry"][0]["trace_id"] == first["trace_id"]
    second = deeper.run(ctx2, FixtureGateway())
    assert second["depth"] == 2 and second["trail_root_id"] == store["deposition_id"]
    # and the follow-up still refuses when custody breaks underneath it
    dep = federation.get_deposition(store["deposition_id"])
    blob = federation.blobs_dir() / dep["sha256"]
    original = blob.read_bytes()
    try:
        blob.write_bytes(original + b" ")
        with pytest.raises(ValueError):
            deeper.build_context({"kind": "result", "trace_id": second["trace_id"]}, {"question": "And then?"})
    finally:
        blob.write_bytes(original)


def test_tampered_frozen_context_refused_at_start(store):
    # Start re-resolves the frozen root against custody: a context whose
    # claim text was edited after prepare does not match the record
    ctx = deeper.build_context(subject(store, f"deflate:claim:{store['claim_id']}"), {})
    bent = copy.deepcopy(ctx)
    bent["root"]["selection"]["deposition"]["item"]["text"] = "A claim no one deposed."
    with pytest.raises(ValueError) as e:
        deeper.run(bent, FixtureGateway())
    assert "does not match the record" in str(e.value)
