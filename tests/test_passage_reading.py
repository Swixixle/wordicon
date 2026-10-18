"""A single read must expose distinct, addressable parts of a complete work."""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evidence_fetch as ef
import library

FIXTURES = Path(__file__).parent / "fixtures" / "evidence"
QUESTION = ("Help me understand Shakuntala's ring more deeply on its own terms. "
            "Explain the idea in context and where in the work I should continue.")


def assert_resolvable(result, body, kind="html"):
    rep = library.build_representation(hashlib.sha256(body).hexdigest(), kind, body)
    sections = {section["path"]: section["text"] for section in rep["sections"]}
    locations = {}
    for passage in result["passages"]:
        loc = passage["excerpt_selection"]
        text = sections[loc["section_path"]]
        assert text[loc["start"]:loc["end"]] == passage["text"]
        assert passage["text_sha256"] == hashlib.sha256(passage["text"].encode()).hexdigest()
        assert passage["section_sha256"] == hashlib.sha256(text.encode()).hexdigest()
        assert 0 < len(passage["text"]) <= 3000
        assert passage["relevance_verified"] is False
        spans = locations.setdefault(loc["section_path"], [])
        assert all(min(loc["end"], end) <= max(loc["start"], start) for start, end in spans)
        spans.append((loc["start"], loc["end"]))


def test_complete_ryder_body_exposes_offer_departure_and_recollection_in_one_read():
    body = gzip.decompress((FIXTURES / "gutenberg-16659-ryder.html.gz").read_bytes())
    metadata = json.loads((FIXTURES / "gutenberg-16659-ryder.json").read_text())
    assert len(body) == metadata["body_bytes"] == 578395
    assert hashlib.sha256(body).hexdigest() == metadata["body_sha256"]
    result = ef.inspect_quote(body, "text/html", "", question=QUESTION, passage_limit=6)
    assert result["ok"] and result["status"] == "no_quote"
    assert_resolvable(result, body)
    requirements = {
        "ACT I": ("I therefore remit her debt.", "you ought not to part with it",
                  "Your word is enough to remit the debt."),
        "ACT IV": ("When the good king went away, he put a ring, engraved with his own name, "
                   "on Shakuntala's finger to remember him by.",),
        "ACT VI": ("Then I put this engraved ring on her finger",),
    }
    for heading, needles in requirements.items():
        matching = [p for p in result["passages"]
                    if (p["excerpt_selection"]["heading"] == heading
                        or p["excerpt_selection"]["heading"].startswith(heading + " "))]
        assert matching, f"missing printed division: {heading}"
        assert any(all(needle in p["text"] for needle in needles) for p in matching), heading
    assert result["verified"] is False and result["source_admitted"] is False


def test_unrelated_novel_diversifies_chapters_and_keeps_topic_reply_together():
    paragraphs = []
    for number, message in [(1, "Nara receives the compass. Her companion says it is borrowed."),
                            (2, "Nara loses the compass. The river carries it away."),
                            (3, "Nara recovers the compass. Its inscription proves whose it is.")]:
        paragraphs.append(f"<h2>Chapter {number}</h2><p>" + "Nara travelled through the hills. " * 160
                          + message + "</p><p>" + "Evening fell over the valley. " * 120 + "</p>")
    body = ("<title>A Journey</title>" + "".join(paragraphs)).encode()
    result = ef.inspect_quote(body, "text/html", "", question="Nara and the compass", passage_limit=3)
    assert_resolvable(result, body)
    assert {p["excerpt_selection"]["heading"] for p in result["passages"]} == {
        "Chapter 1", "Chapter 2", "Chapter 3"}
    for needle in ("Her companion says it is borrowed.", "The river carries it away.",
                   "Its inscription proves whose it is."):
        assert any(needle in p["text"] for p in result["passages"])


def test_prior_passages_are_bypassed_and_fallback_is_named_only_when_exhausted():
    body = ("compass north. " + "forest path. " * 350 + "compass south. "
            + "meadow path. " * 350 + "compass west.").encode()
    first = ef.inspect_quote(body, "text/plain", "", question="compass", passage_limit=1)
    loc = first["passages"][0]["excerpt_selection"]
    shown = {loc["section_path"]: [(loc["start"], loc["end"])]}
    second = ef.inspect_quote(body, "text/plain", "", question="compass",
                              passage_limit=2, exclude_spans=shown)
    assert_resolvable(second, body, "txt")
    assert all(p["excerpt_selection"].get("advanced_past_shown_windows", 0) > 0
               for p in second["passages"])
    assert all(not ef._span_overlap(p["excerpt_selection"]["start"],
                                    p["excerpt_selection"]["end"], shown["0"])
               for p in second["passages"])
    short = ef.inspect_quote(b"The compass points north.", "text/plain", "",
                             question="compass", passage_limit=6, exclude_spans={"0": [(0, 100)]})
    assert len(short["passages"]) == 1
    assert short["passages"][0]["excerpt_selection"]["reselected_previously_shown_window"] is True


def test_optional_passages_preserve_legacy_excerpt_and_exact_quote_path():
    body = b"<h2>Chapter 1</h2><p>The compass points north.</p><h2>Chapter 2</h2><p>The compass is lost.</p>"
    original = ef.inspect_quote(body, "text/html", "", question="compass")
    expanded = ef.inspect_quote(body, "text/html", "", question="compass", passage_limit=6)
    assert "passages" not in original
    assert {key: value for key, value in expanded.items() if key != "passages"} == original
    for quote in ("The compass points north.", "The  compass points north."):
        original = ef.inspect_quote(body, "text/html", quote, question="compass")
        expanded = ef.inspect_quote(body, "text/html", quote, question="compass", passage_limit=6)
        assert expanded == original
        assert expanded["matched"]


def test_missing_quote_can_still_inspect_multiple_passages_without_claiming_a_match():
    body = b"<h2>Chapter 1</h2><p>The compass points north.</p><h2>Chapter 2</h2><p>The compass is lost.</p>"
    result = ef.inspect_quote(body, "text/html", "The compass is broken.",
                              question="compass", passage_limit=3)
    assert result["status"] == "not_found" and not result["matched"]
    assert len(result["passages"]) == 2
    assert_resolvable(result, body)


def test_absent_question_overlap_does_not_invent_passages_or_promote_opening_text():
    result = ef.inspect_quote(b"A quiet forest.", "text/plain", "",
                              question="compass", passage_limit=6)
    assert result["ok"] and result["passages"] == []
    assert result["selection_method"] == "opening_excerpt"
    assert result["text"] == "A quiet forest."


def test_answer_retry_replays_recorded_passages_despite_shown_window_exclusions():
    body = ("<h2>Chapter 1</h2><p>The compass points north.</p>"
            "<h2>Chapter 2</h2><p>The compass is lost.</p>").encode()
    original = ef.inspect_quote(body, "text/html", "", question="compass", passage_limit=2)
    manifest = [{**p["excerpt_selection"], "text_sha256": p["text_sha256"],
                 "section_sha256": p["section_sha256"]} for p in original["passages"]]
    retry = ef.inspect_quote(body, "text/html", "", question="different question",
                             passage_limit=2, exclude_spans={"0": [(0, 1000)]},
                             requested_passages=manifest)
    assert retry["ok"]
    assert [p["text"] for p in retry["passages"]] == [p["text"] for p in original["passages"]]
    assert_resolvable(retry, body)
    assert all(p["selection_method"] == "replayed_answer_input" for p in retry["passages"])
    assert all(p["excerpt_selection"]["replayed_answer_input"] for p in retry["passages"])


@pytest.mark.parametrize("change", ["text_hash", "section_hash", "representation_hash", "range", "section"])
def test_answer_retry_fails_by_name_when_recorded_passage_cannot_be_resolved(change):
    body = b"The compass points north."
    original = ef.inspect_quote(body, "text/plain", "", question="compass", passage_limit=1)
    passage = original["passages"][0]
    descriptor = {**passage["excerpt_selection"], "text_sha256": passage["text_sha256"],
                  "section_sha256": passage["section_sha256"]}
    if change == "text_hash":
        descriptor["text_sha256"] = "0" * 64
    elif change == "section_hash":
        descriptor["section_sha256"] = "0" * 64
    elif change == "representation_hash":
        descriptor["representation_sha256"] = "0" * 64
    elif change == "range":
        descriptor["end"] = len(body) + 1
    else:
        descriptor["section_path"] = "missing"
    retry = ef.inspect_quote(body, "text/plain", "", question="compass", requested_passages=[descriptor])
    assert retry["ok"] is False and retry["status"] == "passage_replay_mismatch"
    assert retry["passages"] == []


def test_unicode_case_matching_and_numbered_prose_do_not_break_reading():
    body = "<p>Chapter IV explains the irises.</p><p>The İris is blue.</p>".encode()
    result = ef.inspect_quote(body, "text/html", "", question="iris", passage_limit=2)
    assert result["ok"]
    assert result["passages"]
    assert all(p["excerpt_selection"]["heading"] == "article" for p in result["passages"])


@pytest.mark.parametrize("limit", [0, -1, 9, True, "6"])
def test_passage_limit_remains_bounded(limit):
    with pytest.raises(ValueError, match="passage_limit"):
        ef.inspect_quote(b"compass", "text/plain", "", question="compass", passage_limit=limit)
