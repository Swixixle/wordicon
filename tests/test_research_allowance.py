"""R6 acceptance: a research press can reach and actually show later evidence.

Model/HTTP boundaries are synthetic. The public-domain Ryder fixture is the
complete downloaded work, not a fabricated answer or shortened excerpt. These
checks inspect the saved final request; they do not claim a live model answered
correctly merely because the appropriate source passages were supplied.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path
import re

import pytest

from test_evidence_research import (FakeGateway, complete_rounds, context, execute,
                                   final_evidence, found, isolated, lead, missing,
                                   research, saved)


RYDER_PATH = Path(__file__).parent / "fixtures" / "evidence" / "gutenberg-16659-ryder.html.gz"
RYDER_URL = "https://www.gutenberg.org/files/16659/16659-h/16659-h.htm"
QUESTION = "Help me understand Shakuntala's ring more deeply on its own terms. Explain the idea in context and where in the work I should continue."


def reading_context(**changes):
    value = context(question=QUESTION,
                    focus={"title": "Shakuntala's ring", "work": "Kalidasa, Shakuntala"},
                    research_goal={"kind": "followup_question", "target_quote": "", "question": QUESTION})
    value["root"]["selection"].update(quote="", quote_status="none")
    value.update(changes)
    return value


def location(row):
    selection = row.get("excerpt_selection", row)
    return selection["section_path"], selection["start"], selection["end"]


def normalized(text):
    return re.sub(r"\s+", " ", text)


def test_one_press_discloses_enough_room_for_discovery_reading_and_answer():
    plan = research.plan()
    assert plan["version"] == 6
    assert plan["limits"]["max_search_rounds"] == 6
    assert plan["limits"]["max_source_reads"] == 18
    assert plan["limits"]["max_model_calls"] == 7
    assert plan["limits"]["max_grounding_chars"] == 60000
    assert plan["limits"]["searches_per_request"] == 1
    assert plan["limits"]["max_passages_per_source"] == 6
    assert len(plan["strategies"]) == 6
    assert len(set(plan["strategies"])) == 6


def test_six_failed_reads_do_not_prevent_the_seventh_from_locating_the_quote(isolated):
    _, reads, responses = isolated
    urls = [f"https://texts.example/edition-{index}" for index in range(7)]
    responses.update({url: missing(url) for url in urls[:-1]})
    responses[urls[-1]] = found(urls[-1])
    # Exact wording still permits an early stop: adding room does not force
    # all six searches after the quotation has actually been located.
    gateway = FakeGateway([("First editions.", [lead(url) for url in urls[:3]]),
                           ("Alternate editions.", [lead(url) for url in urls[3:6]]),
                           ("Readable edition.", [lead(urls[-1])])])
    result = execute(gateway)
    assert reads == urls
    assert result["evidence_research"]["status"] == "quote_located"
    assert result["evidence_research"]["sources_tried"] == 7
    assert result["evidence_research"]["model_calls"] == 4
    assert len(gateway.search_calls) == 3 and len(gateway.final_prompts) == 1
    assert result["evidence_research"]["proofs"][0]["url"] == urls[-1]


def test_transport_failures_consume_attempts_without_hidden_retries(isolated):
    tmp, reads, responses = isolated
    urls = [f"https://texts.example/shakuntala-{index}" for index in range(30)]
    responses.update({url: missing(url) for url in urls})
    ctx = reading_context(research_resume={"leads": [lead(url) for url in urls]})
    gateway = FakeGateway([TimeoutError("ambiguous transport outcome")] * 6,
                          final=RuntimeError("answer transport unavailable"))
    state = execute(gateway, ctx)["evidence_research"]
    assert len(reads) == len(set(reads)) == 18
    assert len(gateway.search_calls) == 6 and len(gateway.final_prompts) == 1
    assert all(max_uses == 1 for _, max_uses in gateway.search_calls)
    assert state["rounds_used"] == 6 and state["sources_tried"] == 18 and state["model_calls"] == 7
    assert state["status"] == "needs_more_evidence"
    assert state["final_answer_status"] == "unavailable"
    checkpoint = saved(tmp)
    assert len(checkpoint["model_records"]) == 7
    assert all(call["status"] == "failed" and call["max_http_attempts"] == 1
               for call in checkpoint["model_records"])
    assert all(record["response_observed"] is False and record["web_search_requests"] is None
               for record in checkpoint["acquisition_records"])


def test_real_ryder_one_read_supplies_acts_i_iv_and_vi_with_preserved_locations(isolated):
    tmp, reads, responses = isolated
    body = gzip.decompress(RYDER_PATH.read_bytes())
    responses[RYDER_URL] = found(RYDER_URL, body, "text/html")
    gateway = FakeGateway(complete_rounds([("A complete primary text.", [lead(RYDER_URL)])]))
    result = execute(gateway, reading_context())
    record = final_evidence(gateway.final_prompts[0])
    packed = record["sources"]
    needles = {
        "ACT I": "you ought not to part with it",
        "ACT IV": "put a ring, engraved with his own name, on Shakuntala's finger",
        "ACT VI": "Then I put this engraved ring on her finger",
    }
    for heading, needle in needles.items():
        matching = [row for row in packed if needle in normalized(row["text"])]
        assert matching, f"{heading} ring passage never reached the answer's actual input"
        row = matching[0]
        selection = row["excerpt_selection"]
        assert selection["heading"].upper().startswith(heading)
        assert selection["end"] - selection["start"] == len(row["text"])
        assert row["body_sha256"] == hashlib.sha256(body).hexdigest()
        assert row["url"] == RYDER_URL
    assert reads == [RYDER_URL]
    assert sum(len(row["text"]) for row in packed) <= 60000
    assert len({location(row) for row in packed}) == len(packed)
    assert record["answer_support_verified"] is False
    assert result["evidence_research"]["status"] == "candidate_passages_found"
    # The durable record is the same request observed at the model boundary.
    checkpoint = saved(tmp)
    assert checkpoint["model_records"][-1]["prompt"] == gateway.final_prompts[0]


def test_byte_identical_mirrors_cannot_crowd_out_the_reading(isolated):
    _, reads, responses = isolated
    body = gzip.decompress(RYDER_PATH.read_bytes())
    urls = [RYDER_URL] + [f"https://mirror{index}.example/shakuntala" for index in range(5)]
    responses.update({url: found(url, body, "text/html") for url in urls})
    gateway = FakeGateway(complete_rounds([("Mirrors of the full work.", [lead(url) for url in urls])]))
    result = execute(gateway, reading_context())
    packed = final_evidence(gateway.final_prompts[0])["sources"]
    assert set(reads) == set(urls)
    assert len({(row["body_sha256"], location(row)) for row in packed}) == len(packed)
    assert len({row["url"] for row in packed}) == 1
    text = normalized(" ".join(row["text"] for row in packed))
    assert "you ought not to part with it" in text
    assert "put a ring, engraved with his own name, on Shakuntala's finger" in text
    assert "Then I put this engraved ring on her finger" in text
    sources = result["evidence_research"]["sources"]
    assert len([source for source in sources if source.get("duplicate_of_url")]) == 5


def test_selected_but_unpacked_passages_do_not_become_shown_history(isolated, monkeypatch):
    _, _, responses = isolated
    body = gzip.decompress(RYDER_PATH.read_bytes())
    responses[RYDER_URL] = found(RYDER_URL, body, "text/html")
    # An intentionally small approved synthesis envelope exercises packing,
    # while extraction still selects several passages from the whole work.
    monkeypatch.setitem(research.LIMITS, "max_grounding_chars", 3000)
    gateway = FakeGateway(complete_rounds([("Full work.", [lead(RYDER_URL)])]))
    result = execute(gateway, reading_context())
    packed = final_evidence(gateway.final_prompts[0])["sources"]
    assert sum(len(row["text"]) for row in packed) <= 3000
    source = result["evidence_research"]["sources"][0]
    selected = {location(passage) for passage in source["inspection"]["passages"]}
    actual = {location(row) for row in packed}
    shown = {location(row) for row in source["shown_windows"]}
    assert selected - actual, "fixture must select more passages than fit in the final request"
    assert shown == actual
    assert not (shown & (selected - actual))
    resume = research.freeze_resume({**result, "trace_id": "trace_evidence_test"})
    assert {location(row) for row in resume["sources"][0]["shown_windows"]} == actual


def test_frozen_r5_allowance_cannot_dispatch_under_r6(isolated):
    tmp, reads, _ = isolated
    ctx = reading_context()
    ctx["research_plan"] = copy.deepcopy(ctx["research_plan"])
    ctx["research_plan"]["version"] = 5
    ctx["research_plan"]["limits"].update(max_search_rounds=3, max_source_reads=6,
                                         max_model_calls=4, max_grounding_chars=12000)
    gateway = FakeGateway()
    with pytest.raises(ValueError, match="fresh proposal"):
        execute(gateway, ctx)
    assert not reads and not gateway.search_calls and not gateway.final_prompts
    assert not (tmp / "deeper_evidence").exists()


def test_answer_can_use_beyond_old_allowance_but_never_over_sixty_thousand(isolated):
    _, reads, responses = isolated
    urls = [f"https://texts.example/shakuntala-edition-{book}" for book in range(18)]
    for book, url in enumerate(urls):
        sections = []
        for act in range(1, 7):
            text = " ".join(f"Shakuntala considers the ring in edition {book}, act {act}, line {line}."
                            for line in range(100))
            sections.append(f"<h2>ACT {act}</h2><p>{text}</p>")
        responses[url] = found(url, ("<html><body>" + "".join(sections) + "</body></html>").encode(), "text/html")
    gateway = FakeGateway([("More complete editions.", [lead(url) for url in urls[start:start + 3]])
                           for start in range(0, 18, 3)])
    result = execute(gateway, reading_context())
    packed = final_evidence(gateway.final_prompts[0])["sources"]
    assert sum(len(row["text"]) for row in packed) == 60000
    assert len(reads) == 18 and len(gateway.search_calls) == 6 and len(gateway.final_prompts) == 1
    assert result["evidence_research"]["model_calls"] == 7
    for row in packed:
        assert row["excerpt_selection"]["end"] - row["excerpt_selection"]["start"] == len(row["text"])


def test_failed_answer_retries_the_actual_ryder_passages_instead_of_advancing(isolated):
    _, reads, responses = isolated
    body = gzip.decompress(RYDER_PATH.read_bytes())
    responses[RYDER_URL] = found(RYDER_URL, body, "text/html")
    ctx = reading_context()
    first_gateway = FakeGateway(
        complete_rounds([("A complete primary text.", [lead(RYDER_URL)])]),
        final=RuntimeError("final answer transport unavailable"))
    first = execute(first_gateway, ctx, trace="trace_ryder_answer_failed")
    parent = {**first, "trace_id": "trace_ryder_answer_failed", "mode": "deepen"}
    retry_goal = research.goal(parent, ctx["root"], continue_evidence=True)
    assert retry_goal["retry_answer_only"] is True
    retry_gateway = FakeGateway()
    retry = execute(retry_gateway, reading_context(
        research_resume=research.freeze_resume(parent), research_goal=retry_goal),
        trace="trace_ryder_answer_retried")
    original = final_evidence(first_gateway.final_prompts[0])["sources"]
    retried = final_evidence(retry_gateway.final_prompts[0])["sources"]
    # A failed answer is not a request to advance away from the useful evidence
    # it never explained. Compare the actual dispatched text and addresses.
    def identity(row):
        return (row["body_sha256"], row["representation_sha256"],
                row["section_sha256"], location(row), row["text_sha256"], row["text"])
    assert [identity(row) for row in retried] == [identity(row) for row in original]
    text = normalized(" ".join(row["text"] for row in retried))
    assert "you ought not to part with it" in text
    assert "put a ring, engraved with his own name, on Shakuntala's finger" in text
    assert "Then I put this engraved ring on her finger" in text
    assert reads == [RYDER_URL]
    assert retry_gateway.search_calls == []
    assert retry["evidence_research"]["model_calls"] == 1
    assert retry["evidence_research"]["stop_reason"] == "reused_complete_pass_for_answer_retry"


@pytest.mark.parametrize("corruption", ["wrong_hash", "missing_hash"])
def test_answer_retry_manifest_mismatch_records_gap_and_returns_to_research(isolated, corruption):
    _, _, responses = isolated
    body = gzip.decompress(RYDER_PATH.read_bytes())
    responses[RYDER_URL] = found(RYDER_URL, body, "text/html")
    ctx = reading_context()
    first = execute(FakeGateway(
        complete_rounds([("A complete primary text.", [lead(RYDER_URL)])]),
        final=RuntimeError("final answer transport unavailable")),
        ctx, trace="trace_ryder_bad_manifest_parent")
    parent = {**first, "trace_id": "trace_ryder_bad_manifest_parent", "mode": "deepen"}
    resume = research.freeze_resume(parent)
    assert resume["answer_input"], "answer retry must preserve the actual prior input manifest"
    if corruption == "wrong_hash":
        resume["answer_input"][0]["text_sha256"] = "0" * 64
    else:
        resume["answer_input"][0].pop("text_sha256")
    gateway = FakeGateway(complete_rounds([]))
    result = execute(gateway, reading_context(
        research_resume=resume,
        research_goal=research.goal(parent, ctx["root"], continue_evidence=True)),
        trace="trace_ryder_bad_manifest_retry")
    state = result["evidence_research"]
    assert gateway.search_calls, "a mismatched prior payload cannot silently take the answer-only shortcut"
    assert state["stop_reason"] != "reused_complete_pass_for_answer_retry"
    assert any(step["kind"] == "replay" and step["status"] == "passage_replay_mismatch"
               for step in state["steps"])
    for row in final_evidence(gateway.final_prompts[0])["sources"]:
        assert row["text_sha256"] == hashlib.sha256(row["text"].encode()).hexdigest()


def test_answer_retry_cannot_silently_drop_a_body_missing_from_frozen_references(isolated):
    _, _, responses = isolated
    body = gzip.decompress(RYDER_PATH.read_bytes())
    second_url = "https://texts.example/shakuntala-ring-commentary"
    responses[RYDER_URL] = found(RYDER_URL, body, "text/html")
    responses[second_url] = found(second_url,
        ("Shakuntala's ring is discussed in this separate account of the king's memory. " * 8).encode())
    ctx = reading_context()
    first = execute(FakeGateway(
        complete_rounds([("Two texts.", [lead(RYDER_URL), lead(second_url)])]),
        final=RuntimeError("final answer transport unavailable")),
        ctx, trace="trace_missing_replay_body_parent")
    parent = {**first, "trace_id": "trace_missing_replay_body_parent", "mode": "deepen"}
    resume = research.freeze_resume(parent)
    assert len({row["body_sha256"] for row in resume["answer_input"]}) == 2
    # The bounded frozen reference list can omit a body that appeared in a
    # larger pass's input. Useful remaining bytes cannot certify full replay.
    resume["sources"] = [row for row in resume["sources"] if row["url"] != second_url]
    gateway = FakeGateway(complete_rounds([]))
    result = execute(gateway, reading_context(
        research_resume=resume,
        research_goal=research.goal(parent, ctx["root"], continue_evidence=True)),
        trace="trace_missing_replay_body_retry")
    state = result["evidence_research"]
    assert gateway.search_calls, "partial replay must not silently claim the completed pass was revalidated"
    assert state["stop_reason"] != "reused_complete_pass_for_answer_retry"
    assert state["answer_replay_mismatch"] is True
    assert any(step["kind"] == "replay" and step["status"] == "passage_replay_mismatch"
               for step in state["steps"])


def test_continuation_advances_to_unshown_sections_of_the_same_saved_body(isolated):
    _, reads, responses = isolated
    url = "https://texts.example/eight-acts"
    numerals = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
    body = ("<html><body>" + "".join(
        f"<h2>ACT {numeral}</h2><p>Shakuntala examines the ring in scene {index}. " +
        "The surrounding speech describes the remembered journey. " * 12 + "</p>"
        for index, numeral in enumerate(numerals)) + "</body></html>").encode()
    responses[url] = found(url, body, "text/html")
    first_gateway = FakeGateway(complete_rounds([("The complete work.", [lead(url)])]))
    first = execute(first_gateway, reading_context(), trace="trace_eight_acts_first")
    first_input = final_evidence(first_gateway.final_prompts[0])["sources"]
    assert len(first_input) == 6
    resume = research.freeze_resume({**first, "trace_id": "trace_eight_acts_first"})
    second_gateway = FakeGateway(complete_rounds([]))
    second = execute(second_gateway, reading_context(research_resume=resume,
                     research_goal={"kind": "continue_evidence", "target_quote": "", "question": QUESTION}),
                     trace="trace_eight_acts_second")
    second_input = final_evidence(second_gateway.final_prompts[0])["sources"]
    assert len(second_input) == 2
    assert {location(row) for row in first_input}.isdisjoint(location(row) for row in second_input)
    assert all(row["excerpt_selection"]["advanced_past_shown_windows"] >= 6 for row in second_input)
    assert reads == [url], "continuation must use saved bytes rather than fetch the same body again"
    assert len(second["evidence_research"]["sources"][0]["shown_windows"]) == 8


def test_strongest_work_keeps_all_its_passages_when_the_budget_binds(isolated):
    # Integration sabotage finding (2026-10-18): flattening the strongest-
    # work-first schedule to a round robin was caught by NOTHING — the
    # acceptance fixture has one body, so the priority law lived only in a
    # comment. Here the budget binds: one rich multi-act work competes with
    # seventeen single-passage pages for twenty 3,000-character slots. The
    # law under test: the work with the broadest section coverage presents
    # its whole sequence before remaining space is distributed — a round
    # robin would drop its later acts for interchangeable one-scene pages.
    _, reads, responses = isolated
    rich_url = "https://texts.example/whole-play"
    numerals = ["I", "II", "III", "IV", "V", "VI"]
    rich_body = ("<html><body>" + "".join(
        f"<h2>ACT {numeral}</h2><p>Shakuntala examines the ring in act {index}. " +
        "The surrounding speech recalls the hermitage and the court. " * 48 + "</p>"
        for index, numeral in enumerate(numerals)) + "</body></html>").encode()
    responses[rich_url] = found(rich_url, rich_body, "text/html")
    distractors = [f"https://pages.example/scene-{n}" for n in range(17)]
    for n, url in enumerate(distractors):
        page = ("<html><body><p>Shakuntala and the ring, a single scene note %d. " % n +
                "Commentary circles the same moment without the play's sequence. " * 44 +
                "</p></body></html>").encode()
        responses[url] = found(url, page, "text/html")
    gateway = FakeGateway(complete_rounds([("Everything at once.", [lead(rich_url)] + [lead(u) for u in distractors])]))
    result = execute(gateway, reading_context(), trace="trace_budget_binds")
    sources = final_evidence(gateway.final_prompts[-1])["sources"]
    packed_chars = sum(len(s["text"]) for s in sources)
    assert packed_chars > 54000, f"the budget did not bind ({packed_chars} chars) — this test must compete for slots"
    rich_passages = [s for s in sources if s["url"] == rich_url]
    assert len(rich_passages) == 6, (
        f"the strongest work kept only {len(rich_passages)} of its 6 passages — "
        "its later acts were traded for interchangeable one-scene pages")
    headings = {(s.get("excerpt_selection") or {}).get("heading", "") for s in rich_passages}
    assert sum(1 for h in headings if h.startswith("ACT")) >= 5
