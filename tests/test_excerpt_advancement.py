"""Revision five — the reading problem, first slice (2026-10-18).

The deployed Shakuntala records showed the gap exactly: the pass held Ryder's
full translation in custody — Act IV's departure gift and Act VI's "virtue,
ring" lament included — while the final model request was packed with the
same Act I window twice, plus archive.org navigation chrome and a Wikipedia
references region, steered by the question template's own framing words.

These pins hold the two repairs: retail product routes rank as catalog hints
(an ISBN alone stays a weak clue), and a continuation that reuses a saved
text ADVANCES through it — already-shown windows are passed over while any
unshown window still matches, and a forced reselection says so by name.
"""
import json

import pytest

from test_evidence_research import (FakeGateway, context, execute,
                                    found, isolated, lead, research)

import evidence_fetch
import evidence_quality

WORK = "Mahabharata / Kalidasa's play Abhijnanashakuntalam"
QUESTION = "Help me understand Shakuntala's ring more deeply on its own terms. Explain the idea in context and where in the work I should continue."

# A Ryder-shaped body: three act regions far apart in one plain-text stream.
# Term densities make Act I the strongest first window; Act IV and Act VI
# still carry the substantive terms, so an advancing selection has somewhere
# real to go. Filler is term-free.
ACT_I = ("ACT I. The hermitage. Shakuntala waters the trees with her friends. "
         "The king offers his engraved ring to remit the watering debt; her friends read the "
         "name upon the ring and know him. Shakuntala keeps the ring of the king. ")
ACT_IV = ("ACT IV. The departure. Dushyanta gives Shakuntala the signet ring at the farewell: "
          "wear this ring, count one day for each letter of the name upon it. The ring is the pledge "
          "Shakuntala carries from the hermitage toward the court. ")
ACT_VI = ("ACT VI. The fisherman brings the recovered ring. The king laments to the ring: "
          "your virtue, ring, like mine, is proved but small; Shakuntala wore you and was forgotten. ")
FILLER = "The forest path continues between the rivers and the evening settles over the fields. "


def ryder_body():
    return (ACT_I + FILLER * 60 + ACT_IV + FILLER * 60 + ACT_VI + FILLER * 20).encode()


def shak_context(**changes):
    value = context(question=QUESTION,
                    focus={"title": "Shakuntala's ring", "work": WORK})
    value["root"]["selection"].update(quote="", quote_status="none")
    value.update(changes)
    return value


# ---- requirement 1: actual text pages move ahead of retail listings ----------

def test_recorded_retail_row_now_defers_behind_the_recorded_text_rows():
    az = evidence_quality.rank_candidate(
        {"title": "Abhijnanashakuntalam: The Recognition of Shakuntala: 9780670087464: Kalidasa, Vinay Dharwadker: Books",
         "url": "https://www.amazon.com/Abhijnanashakuntalam-Recognition-Shakuntala-Kalidasa/dp/0670087467"},
        work=WORK, question=QUESTION)
    gb = evidence_quality.rank_candidate(
        {"title": "The Project Gutenberg eBook of Translations of Shakuntala and Other Works, by Kalidasa",
         "url": "https://www.gutenberg.org/files/16659/16659-h/16659-h.htm"},
        work=WORK, question=QUESTION)
    st = evidence_quality.rank_candidate(
        {"title": "Kalidasa: Shakuntala and Other Works: Shakuntala: Act VI....",
         "url": "https://sacred-texts.com/hin/sha/sha10.htm"},
        work=WORK, question=QUESTION)
    assert az["retrieval_tier"] == 1 and "retail_product_path" in az["metadata_signals"]["route_catalog_indications"]
    for text_row in (gb, st):
        assert text_row["retrieval_tier"] == 0
        assert (text_row["retrieval_tier"], -text_row["score"]) < (az["retrieval_tier"], -az["score"])
    gp = evidence_quality.rank_candidate({"title": "Shakuntala book", "url": "https://retail.example/gp/product/0670087467"},
                                         work=WORK, question=QUESTION)
    assert gp["retrieval_tier"] == 1


def test_isbn_alone_stays_a_weak_clue_on_a_text_page():
    ft = evidence_quality.rank_candidate(
        {"title": "Full text of Shakuntala, complete translation (print ISBN 978-0-14-044585-2)",
         "url": "https://texts.example/shakuntala/full-text"},
        work=WORK, question=QUESTION)
    assert ft["retrieval_tier"] == 0
    assert ft["candidate_kind"] == "text_indicated"
    assert "isbn_in_title_weak_catalog_clue" in ft["reason"]
    bare = evidence_quality.rank_candidate(
        {"title": "Full text of Shakuntala, complete translation",
         "url": "https://texts.example/shakuntala/full-text"},
        work=WORK, question=QUESTION)
    assert bare["score"] - ft["score"] == 4          # a nudge, not a verdict


def test_template_framing_words_no_longer_count_as_question_terms():
    # the live records matched "help" in all four packed excerpts
    assert evidence_quality.meaningful_terms(QUESTION) == ["shakuntala", "ring"]


# ---- requirement 3: continuation advances through a reused saved text --------

def pass_one(reads, responses):
    url = "https://texts.example/ryder/full"
    responses[url] = found(url, ryder_body())
    gateway = FakeGateway([("A full text.", [lead(url)]), ("No new leads.", []), ("No new leads.", [])])
    result = execute(gateway, shak_context(), trace="trace_pass_one")
    sel = result["evidence_research"]["sources"][0]["inspection"]["excerpt_selection"]
    text = result["evidence_research"]["sources"][0]  # inspection text removed; read packed window from checkpoint sources
    return url, result, sel


def test_first_pass_selects_the_act_i_window(isolated):
    tmp, reads, responses = isolated
    url, result, sel = pass_one(reads, responses)
    assert sel["matched_terms"] == ["ring", "shakuntala"]
    assert sel["start"] == 0                          # the Act I region leads the stream
    assert "advanced_past_shown_windows" not in sel and "reselected_previously_shown_window" not in sel


def test_continuation_reaches_the_act_iv_and_vi_regions_instead_of_the_same_window(isolated):
    tmp, reads, responses = isolated
    url, first, sel1 = pass_one(reads, responses)
    resume = research.freeze_resume({**first, "trace_id": "trace_pass_one"})
    # the continuation reuses the saved body before any new read
    gateway2 = FakeGateway([("No new leads.", []), ("No new leads.", []), ("No new leads.", [])])
    second = execute(gateway2, shak_context(research_resume=resume,
                                            research_goal={"kind": "continue_evidence", "target_quote": "",
                                                           "question": QUESTION}), trace="trace_pass_two")
    reused = [s for s in second["evidence_research"]["sources"] if s.get("url") == url]
    assert reused, "the saved text was not reused"
    sel2 = reused[0]["inspection"]["excerpt_selection"]
    assert sel2.get("advanced_past_shown_windows", 0) >= 1
    assert sel2["start"] != sel1["start"]
    # the newly shown window is a REAL act region, not filler: it carries the
    # departure gift or the king's lament
    ck = json.loads((tmp / "deeper_evidence" / "trace_pass_two" / "checkpoint.json").read_text())
    final = [r for r in ck["model_records"] if r.get("stage") == "complete"]
    prompt = final[-1]["prompt"] if final else ""
    assert ("wear this ring" in prompt) or ("virtue, ring" in prompt), "the advanced window did not reach Act IV/VI text"
    assert prompt.count(ACT_I[:40]) == 0 or sel2["start"] != sel1["start"]
    # a third pass excludes both shown windows and still advances or says it reused
    resume3 = research.freeze_resume({**second, "trace_id": "trace_pass_two"})
    gateway3 = FakeGateway([("No new leads.", []), ("No new leads.", []), ("No new leads.", [])])
    third = execute(gateway3, shak_context(research_resume=resume3,
                                           research_goal={"kind": "continue_evidence", "target_quote": "",
                                                          "question": QUESTION}), trace="trace_pass_three")
    reused3 = [s for s in third["evidence_research"]["sources"] if s.get("url") == url]
    sel3 = reused3[0]["inspection"]["excerpt_selection"]
    assert sel3.get("advanced_past_shown_windows") or sel3.get("reselected_previously_shown_window")


def test_same_pass_duplicate_bytes_advance_rather_than_repeat(isolated):
    tmp, reads, responses = isolated
    a, b = "https://texts.example/ryder/full", "https://mirror.example/ryder/full"
    body = ryder_body()
    responses[a] = found(a, body)
    responses[b] = found(b, body)
    gateway = FakeGateway([("Two copies.", [lead(a), lead(b)]), ("No new leads.", []), ("No new leads.", [])])
    result = execute(gateway, shak_context(), trace="trace_twin")
    sources = [s for s in result["evidence_research"]["sources"] if s.get("url") in (a, b)]
    assert len(sources) == 2
    sels = [s["inspection"]["excerpt_selection"] for s in sources]
    assert sels[0]["start"] != sels[1]["start"], "identical bytes were shown twice at the same window"
    assert sels[1].get("advanced_past_shown_windows", 0) >= 1


def test_reselection_is_disclosed_when_only_the_shown_window_matches(isolated):
    tmp, reads, responses = isolated
    url = "https://texts.example/one-scene"
    body = (ACT_I + FILLER * 80).encode()            # the terms live in one window only
    responses[url] = found(url, body)
    gateway = FakeGateway([("One scene.", [lead(url)]), ("No new leads.", []), ("No new leads.", [])])
    first = execute(gateway, shak_context(), trace="trace_one_scene")
    resume = research.freeze_resume({**first, "trace_id": "trace_one_scene"})
    gateway2 = FakeGateway([("No new leads.", []), ("No new leads.", []), ("No new leads.", [])])
    second = execute(gateway2, shak_context(research_resume=resume,
                                            research_goal={"kind": "continue_evidence", "target_quote": "",
                                                           "question": QUESTION}), trace="trace_one_scene_b")
    reused = [s for s in second["evidence_research"]["sources"] if s.get("url") == url][0]
    sel = reused["inspection"]["excerpt_selection"]
    assert sel.get("reselected_previously_shown_window") is True


def test_plan_names_the_advancement():
    plan = research.plan()
    assert plan["version"] == 5
    assert "excerpt selection prefers windows not yet shown to the model" in plan["source_selection"]
    assert "disclosed by name" in plan["source_selection"]
