"""Regressions for bounded research when a question has no exact quote target."""
import pytest

from test_evidence_research import (FakeGateway, complete_rounds, context, execute, final_evidence, found,
                                    isolated, lead, research)


def test_one_readable_landing_page_cannot_end_quoteless_research(isolated):
    _, reads, responses = isolated
    urls = [f"https://archive.example/candidate-{index}" for index in range(6)]
    responses.update({url: found(url, b"Chapter chapters ever his. Listen to this audiobook or download the recording.")
                      for url in urls})
    ctx = context(research_goal={"kind": "followup_question", "target_quote": ""},
                  question="How do beata vita and gaudium connect in Confessions Book X?")
    gateway = FakeGateway(complete_rounds([("Candidate pages.", [lead(url) for url in urls]),
                           ("No new source.", []), ("No new source.", [])]))
    result = execute(gateway, ctx)
    assert reads == urls
    assert len(gateway.search_calls) == 6
    state = result["evidence_research"]
    assert state["status"] == "needs_more_evidence"
    assert all(not set(source["assessment"]["matched_question_terms"]) & {"chapter", "chapters", "ever", "his"}
               for source in state["sources"])


QUESTION = "How do beata vita and gaudium relate to memory in Confessions Book X?"
PASSAGE = ("Augustine examines memory and the search for a happy life. "
           "The expression beata vita concerns happiness, and gaudium names joy. "
           "These ideas are considered together within the argument of Confessions Book X. "
           "Their relationship requires reading the surrounding discussion rather than treating a catalog entry as the work.")
WEAK = "Chapter chapters ever his. Listen to this audiobook or download the recording."


def question_context(**changes):
    value = context(research_goal={"kind": "followup_question", "target_quote": "", "question": QUESTION},
                    question=QUESTION)
    value.update(changes)
    return value


def discovery_rounds(urls):
    return complete_rounds([("Candidate routes for the question.", [lead(url) for url in urls]),
            ("Check another edition.", []), ("Try the specific concepts.", [])])


def test_primary_text_ranked_before_audiobook_catalog_with_same_work_title(isolated):
    _, reads, responses = isolated
    audio = "https://librivox.example/confessions-audiobook"
    work = "https://archive.example/texts/augustine/confessions-book-x"
    responses[audio] = found(audio, WEAK.encode())
    responses[work] = found(work, PASSAGE.encode())
    gateway = FakeGateway(complete_rounds([
        ("Candidates in search return order.", [
            {**lead(audio), "title": "Confessions by Augustine | LibriVox audiobook download"},
            {**lead(work), "title": "Augustine: Confessions, Book X — full text"}]),
        ("Alternate text.", []), ("Precise concepts.", [])]))
    result = execute(gateway, question_context())
    assert reads == [work, audio]
    assert len(gateway.search_calls) == 6
    assert result["evidence_research"]["status"] == "candidate_passages_found"


def test_misleading_relevant_title_does_not_turn_irrelevant_body_into_evidence(isolated):
    _, reads, responses = isolated
    url = "https://catalog.example/confessions-book-x-beata-vita-gaudium-memory"
    responses[url] = found(url, WEAK.encode())
    misleading = {**lead(url), "title": "Confessions Book X: beata vita, gaudium and memory — full text"}
    gateway = FakeGateway(complete_rounds([("Promising title.", [misleading]), ("No new text.", []), ("No new text.", [])]))
    result = execute(gateway, question_context())
    state = result["evidence_research"]
    assert reads == [url]
    assert state["source_count"] == 1
    assert state["usable_source_count"] == 0
    assert state["status"] == "needs_more_evidence"
    assert len(gateway.search_calls) == 6


def test_meaningful_first_page_still_does_not_end_quoteless_research(isolated):
    _, reads, responses = isolated
    urls = [f"https://archive.example/book-x-candidate-{index}" for index in range(6)]
    responses.update({url: found(url, PASSAGE.encode() if index == 0 else WEAK.encode())
                      for index, url in enumerate(urls)})
    gateway = FakeGateway(discovery_rounds(urls))
    result = execute(gateway, question_context())
    state = result["evidence_research"]
    assert reads == urls
    assert len(gateway.search_calls) == 6 and len(gateway.final_prompts) == 1
    assert state["source_count"] == 6 and state["usable_source_count"] == 1
    assert state["status"] == "candidate_passages_found"
    assert state["retrieval_pass_complete"] is True
    assert state["stop_reason"] == "search_budget_reached"
    assert state["proofs"] == []
    assert state["remaining_requirement"]
    assert all(source["assessment"]["relevance_verified"] is False for source in state["sources"])
    assert final_evidence(gateway.final_prompts[0])["answer_support_verified"] is False


def test_late_meaningful_passage_survives_earlier_noisy_pages(isolated):
    _, reads, responses = isolated
    urls = [f"https://archive.example/candidate-{index}" for index in range(6)]
    responses.update({url: found(url, PASSAGE.encode() if index == 5 else WEAK.encode())
                      for index, url in enumerate(urls)})
    gateway = FakeGateway(discovery_rounds(urls))
    result = execute(gateway, question_context())
    state = result["evidence_research"]
    assert reads == urls
    assert state["status"] == "candidate_passages_found"
    assert state["source_count"] == 6 and state["usable_source_count"] == 1
    assert urls[-1] in gateway.final_prompts[0]
    assert "beata vita" in gateway.final_prompts[0]


def test_quoteless_search_read_and_model_limits_remain_hard_caps(isolated):
    _, reads, responses = isolated
    urls = [f"https://archive.example/candidate-{index}" for index in range(24)]
    responses.update({url: found(url, PASSAGE.encode()) for url in urls})
    rounds = complete_rounds([("Many distinct candidates.", [lead(url) for url in urls[offset:offset + 4]])
              for offset in (0, 4, 8, 12, 16, 20)])
    gateway = FakeGateway(rounds)
    result = execute(gateway, question_context())
    state = result["evidence_research"]
    assert len(reads) == 18 and len(set(reads)) == 18
    assert len(gateway.search_calls) == 6
    assert all(max_uses == 1 for _, max_uses in gateway.search_calls)
    assert len(gateway.final_prompts) == 1
    assert state["rounds_used"] == 6 and state["sources_tried"] == 18 and state["model_calls"] == 7
    assert len(result["research_model_records"]) == 7
    assert state["retrieval_pass_complete"] is True
    assert state["status"] == "candidate_passages_found"


def test_all_readable_but_weak_pages_remain_unresolved(isolated):
    _, reads, responses = isolated
    urls = [f"https://archive.example/page-{index}" for index in range(6)]
    responses.update({url: found(url, WEAK.encode()) for url in urls})
    gateway = FakeGateway(discovery_rounds(urls))
    state = execute(gateway, question_context())["evidence_research"]
    assert len(reads) == 6
    assert state["source_count"] == 6 and state["usable_source_count"] == 0
    assert state["status"] == "needs_more_evidence"
    assert state["retrieval_pass_complete"] is True
    assert state["final_answer_status"] == "available"
    assert state["remaining_requirement"]
    assert final_evidence(gateway.final_prompts[0])["sources"] == []


def test_rediscovered_saved_source_is_a_candidate_not_a_stop_condition(isolated):
    _, reads, responses = isolated
    saved_url = "https://archive.example/book-x"
    new_url = "https://alternate.example/book-x"
    responses[saved_url] = found(saved_url, PASSAGE.encode())
    first = execute(FakeGateway(discovery_rounds([saved_url])), question_context(), trace="trace_quoteless_initial")
    responses[new_url] = found(new_url, PASSAGE.encode())
    resume = research.freeze_resume({**first, "trace_id": "trace_quoteless_initial"})
    ctx = question_context(research_resume=resume)
    gateway = FakeGateway(complete_rounds([("The same work.", [lead(saved_url)]),
                           ("Another edition.", [lead(new_url)]), ("No new source.", [])]))
    result = execute(gateway, ctx, trace="trace_quoteless_rediscovered")
    assert reads == [saved_url, new_url]
    assert len(gateway.search_calls) == 6
    assert result["evidence_research"]["usable_source_count"] == 2
    assert result["evidence_research"]["status"] == "candidate_passages_found"
    assert new_url in gateway.final_prompts[0]


def test_old_failed_final_on_readable_landing_page_requires_new_research(isolated):
    _, reads, responses = isolated
    landing, actual = "https://catalog.example/audiobook", "https://archive.example/book-x"
    responses[landing] = found(landing, WEAK.encode())
    ctx = question_context()
    first = execute(FakeGateway(discovery_rounds([landing]), final=RuntimeError("Final transport failed")),
                    ctx, trace="trace_legacy_landing")
    # This is the exact legacy fact pattern: a readable landing page and a failed final call.
    parent = {**first, "trace_id": "trace_legacy_landing", "mode": "deepen"}
    parent["evidence_research"]["version"] = 1
    parent["evidence_research"]["status"] = "source_text_obtained"
    parent["evidence_research"].pop("retrieval_pass_complete", None)
    parent["evidence_research"].pop("usable_source_count", None)
    for source in parent["evidence_research"]["sources"]:
        source.pop("assessment", None)
    continuation = question_context(research_resume=research.freeze_resume(parent),
                                    research_goal=research.goal(parent, ctx["root"], continue_evidence=True))
    assert continuation["research_goal"]["requires_new_source"] is True
    responses[actual] = found(actual, PASSAGE.encode())
    gateway = FakeGateway(discovery_rounds([actual]))
    result = execute(gateway, continuation, trace="trace_legacy_repaired")
    assert reads == [landing, actual]
    assert len(gateway.search_calls) == 6
    assert result["evidence_research"]["status"] == "candidate_passages_found"


@pytest.mark.parametrize("parent_policy", [2, 3, 4, 5, 6])
def test_useful_completed_pass_can_retry_answer_using_saved_passages(isolated, parent_policy):
    _, reads, responses = isolated
    url = "https://archive.example/book-x"
    responses[url] = found(url, PASSAGE.encode())
    ctx = question_context()
    first = execute(FakeGateway(discovery_rounds([url]), final=RuntimeError("Final transport failed")),
                    ctx, trace="trace_v2_final_failed")
    parent = {**first, "trace_id": "trace_v2_final_failed", "mode": "deepen"}
    parent["evidence_research"]["retrieval_policy_rev"] = parent_policy
    continuation = question_context(research_resume=research.freeze_resume(parent),
                                    research_goal=research.goal(parent, ctx["root"], continue_evidence=True))
    assert continuation["research_goal"]["requires_new_source"] is False
    gateway = FakeGateway()
    result = execute(gateway, continuation, trace="trace_v2_answer_retry")
    assert reads == [url]
    assert gateway.search_calls == [] and len(gateway.final_prompts) == 1
    assert result["evidence_research"]["status"] == "candidate_passages_found"
    assert result["evidence_research"]["final_answer_status"] == "available"
    assert result["evidence_research"]["stop_reason"] == "reused_complete_pass_for_answer_retry"


def test_fresh_normal_question_always_researches_despite_useful_saved_passage(isolated):
    _, reads, responses = isolated
    url = "https://archive.example/book-x"
    responses[url] = found(url, PASSAGE.encode())
    first = execute(FakeGateway(discovery_rounds([url]), final=RuntimeError("Final transport failed")),
                    question_context(), trace="trace_first_question")
    parent = {**first, "trace_id": "trace_first_question", "mode": "deepen"}
    normal_goal = research.goal(parent, context()["root"], question=QUESTION, continue_evidence=False)
    assert normal_goal["kind"] == "followup_question"
    gateway = FakeGateway(discovery_rounds([url]))
    result = execute(gateway, question_context(research_resume=research.freeze_resume(parent),
                                             research_goal=normal_goal), trace="trace_fresh_normal_question")
    assert reads == [url]
    assert len(gateway.search_calls) == 6
    assert result["evidence_research"]["status"] == "candidate_passages_found"


def test_useful_saved_source_survives_eighteen_later_weak_reads_in_resume_references(isolated):
    _, _, responses = isolated
    useful = "https://archive.example/useful-book-x"
    responses[useful] = found(useful, PASSAGE.encode())
    first = execute(FakeGateway(discovery_rounds([useful])), question_context(), trace="trace_useful_source")
    weak = [f"https://catalog.example/weak-{index}" for index in range(18)]
    responses.update({url: found(url, (f"Catalog item {index}. " + WEAK).encode())
                      for index, url in enumerate(weak)})
    first_parent = {**first, "trace_id": "trace_useful_source", "mode": "deepen"}
    continuation = question_context(research_resume=research.freeze_resume(first_parent),
                                    research_goal=research.goal(first_parent, context()["root"], continue_evidence=True))
    second = execute(FakeGateway(discovery_rounds(weak)), continuation, trace="trace_later_weak_sources")
    assert second["evidence_research"]["source_count"] == 19
    resumed = research.freeze_resume({**second, "trace_id": "trace_later_weak_sources"})
    assert len(resumed["sources"]) == 18
    assert useful in {source["url"] for source in resumed["sources"]}
    assert resumed["source_references_omitted"] == 1


def test_concept_words_on_a_catalog_page_remain_weak_grounding(isolated):
    _, reads, responses = isolated
    url = "https://catalog.example/confessions"
    body = ("Confessions Book X. Beata vita, gaudium, memory. "
            "Listen now to the audiobook. Read by volunteers. Audio download available.").encode()
    responses[url] = found(url, body)
    gateway = FakeGateway(discovery_rounds([url]))
    result = execute(gateway, question_context())
    state = result["evidence_research"]
    assert reads == [url]
    assert state["sources"][0]["assessment"]["matched_question_terms"]
    assert state["sources"][0]["assessment"]["weak"] is True
    assert state["source_count"] == 1 and state["usable_source_count"] == 0
    assert state["status"] == "needs_more_evidence"
    assert final_evidence(gateway.final_prompts[0])["sources"] == []
    assert len(gateway.search_calls) == 6


def test_failed_answer_retry_rechecks_saved_bytes_before_skipping_research(isolated):
    tmp, reads, responses = isolated
    first_url, new_url = "https://archive.example/book-x", "https://alternate.example/book-x"
    responses[first_url] = found(first_url, PASSAGE.encode())
    ctx = question_context()
    first = execute(FakeGateway(discovery_rounds([first_url]), final=RuntimeError("Final transport failed")),
                    ctx, trace="trace_v2_before_tamper")
    parent = {**first, "trace_id": "trace_v2_before_tamper", "mode": "deepen"}
    continuation = question_context(research_resume=research.freeze_resume(parent),
                                    research_goal=research.goal(parent, ctx["root"], continue_evidence=True))
    assert continuation["research_goal"]["retry_answer_only"] is True
    source = first["evidence_research"]["sources"][0]
    artifact = tmp / "deeper_evidence" / "trace_v2_before_tamper" / f"{source['body_sha256']}.body"
    artifact.write_bytes(b"Changed cached content.")
    responses[new_url] = found(new_url, PASSAGE.encode())
    gateway = FakeGateway(discovery_rounds([new_url]))
    result = execute(gateway, continuation, trace="trace_v2_after_tamper")
    assert reads == [first_url, new_url]
    assert len(gateway.search_calls) == 6
    assert result["evidence_research"]["status"] == "candidate_passages_found"
    assert result["evidence_research"]["stop_reason"] == "search_budget_reached"
    assert any(step["kind"] == "reuse" and step["status"] == "unavailable"
               for step in result["evidence_research"]["steps"])


def test_generic_question_uses_frozen_focus_for_screening_without_changing_goal(isolated):
    _, reads, responses = isolated
    url = "https://archive.example/confessions-book-x"
    generic = "Can you explain more?"
    body = ("Memory preserves impressions and brings past experience into the present. "
            "Its power raises questions about how a person searches inward for understanding.")
    responses[url] = found(url, body.encode())
    ctx = question_context(question=generic,
                           research_goal={"kind": "followup_question", "target_quote": "", "question": generic})
    gateway = FakeGateway(discovery_rounds([url]))
    result = execute(gateway, ctx)
    state = result["evidence_research"]
    assert reads == [url]
    assert len(gateway.search_calls) == 6
    assert state["status"] == "candidate_passages_found"
    assert state["proofs"] == [] and state["retrieval_pass_complete"] is True
    assert state["screening_basis"] == "frozen_focus_fallback"
    assert state["goal"]["question"] == generic and ctx["question"] == generic
    assessment = state["sources"][0]["assessment"]
    assert assessment["question_basis"] == "frozen_focus_fallback"
    assert "memory" in assessment["matched_question_terms"]
    assert assessment["relevance_verified"] is False
    final_record = final_evidence(gateway.final_prompts[0])
    assert final_record["research_question"] == generic
    assert final_record["screening_basis"] == "frozen_focus_fallback"
    assert final_record["answer_support_verified"] is False


def test_specific_question_cannot_fall_back_to_work_only_overlap(isolated):
    _, reads, responses = isolated
    url = "https://archive.example/confessions-book-x"
    question = "What does gaudium mean?"
    responses[url] = found(url, b"Confessions Book X. Chapters from Augustine's work. Memory preserves impressions.")
    ctx = question_context(question=question,
                           research_goal={"kind": "followup_question", "target_quote": "", "question": question})
    gateway = FakeGateway(discovery_rounds([url]))
    result = execute(gateway, ctx)
    state = result["evidence_research"]
    assert reads == [url] and len(gateway.search_calls) == 6
    assert state["screening_basis"] == "question_terms"
    assert state["status"] == "needs_more_evidence"
    assert state["source_count"] == 1 and state["usable_source_count"] == 0
    assessment = state["sources"][0]["assessment"]
    assert assessment["question_basis"] == "question_terms"
    assert "confessions" in assessment["matched_work_terms"]
    assert "gaudium" in assessment["meaningful_question_terms"]
    assert assessment["matched_question_terms"] == []
    final_record = final_evidence(gateway.final_prompts[0])
    assert final_record["research_question"] == question
    assert final_record["sources"] == []
