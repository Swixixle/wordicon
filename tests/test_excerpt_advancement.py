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

from test_evidence_research import (FakeGateway, complete_rounds, context, execute, final_evidence,
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
    gateway = FakeGateway(complete_rounds([("A full text.", [lead(url)]), ("No new leads.", []), ("No new leads.", [])]))
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


def test_first_pass_now_supplies_all_three_act_regions_without_another_press(isolated):
    tmp, reads, responses = isolated
    url, result, _ = pass_one(reads, responses)
    checkpoint = json.loads((tmp / "deeper_evidence" / "trace_pass_one" / "checkpoint.json").read_text())
    prompt = next(call["prompt"] for call in checkpoint["model_records"] if call["stage"] == "complete")
    sources = final_evidence(prompt)["sources"]
    text = "\n".join(source["text"] for source in sources)
    assert all(needle in text for needle in ("watering debt", "wear this ring", "virtue, ring"))
    assert reads == [url]
    locations = [(source["excerpt_selection"]["section_path"],
                  source["excerpt_selection"]["start"], source["excerpt_selection"]["end"])
                 for source in sources]
    assert len(locations) >= 3 and len(set(locations)) == len(locations)


def test_same_pass_duplicate_bytes_do_not_repeat_packed_passages(isolated):
    _, reads, responses = isolated
    a, b = "https://texts.example/ryder/full", "https://mirror.example/ryder/full"
    body = ryder_body()
    responses[a] = found(a, body)
    responses[b] = found(b, body)
    gateway = FakeGateway(complete_rounds([("Two copies.", [lead(a), lead(b)])]))
    result = execute(gateway, shak_context(), trace="trace_twin")
    sources = [s for s in result["evidence_research"]["sources"] if s.get("url") in (a, b)]
    assert len(sources) == 2 and reads == [a, b]
    assert sources[1]["duplicate_of_url"] == a
    packed = final_evidence(gateway.final_prompts[0])["sources"]
    assert {source["url"] for source in packed} == {a}
    locations = [(source["body_sha256"], source["excerpt_selection"]["section_path"],
                  source["excerpt_selection"]["start"], source["excerpt_selection"]["end"])
                 for source in packed]
    assert len(set(locations)) == len(locations)
    assert all(needle in "\n".join(source["text"] for source in packed)
               for needle in ("watering debt", "wear this ring", "virtue, ring"))


def test_reselection_is_disclosed_when_only_the_shown_window_matches(isolated):
    tmp, reads, responses = isolated
    url = "https://texts.example/one-scene"
    body = (ACT_I + FILLER * 80).encode()            # the terms live in one window only
    responses[url] = found(url, body)
    gateway = FakeGateway(complete_rounds([("One scene.", [lead(url)]), ("No new leads.", []), ("No new leads.", [])]))
    first = execute(gateway, shak_context(), trace="trace_one_scene")
    resume = research.freeze_resume({**first, "trace_id": "trace_one_scene"})
    gateway2 = FakeGateway(complete_rounds([("No new leads.", []), ("No new leads.", []), ("No new leads.", [])]))
    second = execute(gateway2, shak_context(research_resume=resume,
                                            research_goal={"kind": "continue_evidence", "target_quote": "",
                                                           "question": QUESTION}), trace="trace_one_scene_b")
    reused = [s for s in second["evidence_research"]["sources"] if s.get("url") == url][0]
    sel = reused["inspection"]["excerpt_selection"]
    assert sel.get("reselected_previously_shown_window") is True


def test_plan_names_the_advancement():
    plan = research.plan()
    assert plan["version"] == 6
    assert "six distinct passages" in plan["source_selection"]
    assert "Only passages actually supplied" in plan["source_selection"]
    assert "reselecting a previously shown window is disclosed" in plan["source_selection"]
