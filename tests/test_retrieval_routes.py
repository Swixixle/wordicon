"""Keep distinct retrieval routes useful within the existing approved caps.

These are synthetic HTTP/model boundaries, including a shape resembling the
Dante report. They do not replay that saved run or make real network calls.
"""
import json

import pytest

from test_evidence_research import (FakeGateway, context, execute,
                                    found, isolated, lead, research)


QUESTION = "How does Dante connect desire and freedom?"
PASSAGE = b"Dante considers desire and freedom together while describing the will."


def quoteless_context(*, inherited=()):
    value = context(question=QUESTION,
                    focus={"title": "Dante on desire and freedom", "work": "Dante, Purgatorio"},
                    research_resume={"leads": list(inherited)})
    value["root"]["selection"].update(quote="", quote_status="none")
    return value


def failure(url, status, http_status=None):
    return {"ok": False, "status": http_status, "final_url": url,
            "outcome": status, "detail": "Synthetic retrieval outcome."}


class ObservedGateway(FakeGateway):
    def __init__(self, rounds, reads):
        super().__init__(rounds)
        self.reads = reads
        self.reads_before_search = []

    def complete_with_search_budget(self, prompt, *, max_uses):
        self.reads_before_search.append(len(self.reads))
        return super().complete_with_search_budget(prompt, max_uses=max_uses)


def test_inherited_failures_leave_a_read_for_third_search_strategy(isolated):
    _, reads, responses = isolated
    urls = ["https://translation.example/dante/purgatorio.html",
            "https://reviews.example/book/show/17-purgatorio",
            "https://essay.example/posts/dante-desire",
            "https://books.example/9780000000001/purgatorio",
            "https://academy.example/articles/dante.pdf",
            "https://research.example/publication/dante-freedom"]
    outcomes = [("timeout", None), ("timeout", None), ("access_denied", 403),
                ("access_denied", 403), ("unsupported_content_type", 200),
                ("access_denied", 403)]
    responses.update({url: failure(url, status, http_status)
                      for url, (status, http_status) in zip(urls, outcomes)})
    actual = "https://edition.example/texts/dante-purgatorio-desire-freedom"
    responses[actual] = found(actual, PASSAGE)
    gateway = ObservedGateway([
        ("Try the first candidates.", [lead(url) for url in urls[2:4]]),
        ("Try another edition.", [lead(url) for url in urls[4:6]]),
        ("A public text of the relevant passage.", [lead(actual)])], reads)
    state = execute(gateway, quoteless_context(inherited=[lead(url) for url in urls[:2]]))["evidence_research"]
    assert len(gateway.search_calls) == 3
    assert gateway.reads_before_search == [2, 4, 5]
    assert reads[-1] == actual and len(reads) == 6
    assert state["rounds_used"] == 3 and state["model_calls"] == 4
    assert state["source_count"] == 1 and state["usable_source_count"] == 1
    assert state["status"] == "candidate_passages_found"
    assert actual in gateway.final_prompts[0]
    assert set(urls + [actual]) <= set(state["candidate_rankings"])
    assert len(state["attempted_urls"]) == 6  # An untried lead remains available.


@pytest.mark.parametrize("failed_rounds", [False, True])
def test_reservation_preserves_final_read_after_empty_or_failed_searches(isolated, failed_rounds):
    _, reads, responses = isolated
    inherited = [f"https://archive.example/lead-{n}" for n in range(10)]
    responses.update({url: failure(url, "timeout") for url in inherited})
    actual = "https://edition.example/texts/dante-purgatorio-desire-freedom"
    responses[actual] = found(actual, PASSAGE)
    first_rounds = [TimeoutError("one transport attempt"), OSError("one transport attempt")] if failed_rounds else [
        ("No new leads.", []), ("No new leads.", [])]
    gateway = ObservedGateway(first_rounds + [("A fresh text.", [lead(actual)])], reads)
    state = execute(gateway, quoteless_context(inherited=[lead(url) for url in inherited]))["evidence_research"]
    assert gateway.reads_before_search == [2, 4, 5]
    assert reads[-1] == actual and len(reads) == 6
    assert state["rounds_used"] == 3 and state["model_calls"] == 4
    assert len(gateway.final_prompts) == 1
    assert all(max_uses == 1 for _, max_uses in gateway.search_calls)


def test_fresh_question_still_allocates_two_reads_per_search(isolated):
    _, reads, responses = isolated
    urls = [f"https://archive.example/lead-{n}" for n in range(6)]
    responses.update({url: failure(url, "access_denied", 403) for url in urls})
    gateway = ObservedGateway([("Candidate leads.", [lead(url) for url in urls[offset:offset + 2]])
                               for offset in (0, 2, 4)], reads)
    ctx = quoteless_context()
    ctx["research_goal"] = {"kind": "followup_question", "target_quote": "", "question": QUESTION}
    state = execute(gateway, ctx)["evidence_research"]
    assert gateway.reads_before_search == [0, 2, 4]
    assert reads == urls and state["sources_tried"] == 6


def test_unreadable_formats_and_catalogs_are_deferred_but_retained(isolated):
    _, reads, responses = isolated
    pdf = "https://academy.example/dante-purgatorio-desire-freedom.pdf"
    catalog = "https://books.example/book/show/123-dante-purgatorio-desire-freedom"
    text = "https://edition.example/chapter"
    rows = [dict(lead(pdf), title="Dante Purgatorio desire freedom full text PDF"),
            dict(lead(catalog), title="Dante Purgatorio desire freedom"),
            dict(lead(text), title="A passage")]
    responses[pdf] = failure(pdf, "unsupported_content_type", 200)
    responses[catalog] = failure(catalog, "access_denied", 403)
    responses[text] = found(text, PASSAGE)
    gateway = FakeGateway([("Candidates in return order.", rows), ("No new leads.", []), ("No new leads.", [])])
    result = execute(gateway, quoteless_context())
    assert reads == [text, catalog, pdf]
    assert {row["url"] for row in result["citations"]} == {text, catalog, pdf}
    ranks = result["evidence_research"]["candidate_rankings"]
    assert [ranks[url]["retrieval_tier"] for url in (text, catalog, pdf)] == [0, 1, 2]


def test_only_catalog_and_pdf_candidates_are_not_silently_dropped(isolated):
    _, reads, responses = isolated
    catalog = "https://store.example/book/show/123-dante"
    pdf = "https://academy.example/dante.pdf"
    responses[catalog] = failure(catalog, "access_denied", 403)
    responses[pdf] = failure(pdf, "unsupported_content_type", 200)
    gateway = FakeGateway([("Only difficult routes.", [lead(pdf), lead(catalog)]),
                           ("No alternate format.", []), ("No public text.", [])])
    state = execute(gateway, quoteless_context())["evidence_research"]
    assert reads == [catalog, pdf]
    assert set(state["url_outcomes"]) == {catalog, pdf}
    assert state["source_count"] == 0
    assert state["remaining_requirement"].startswith("No readable source text was obtained")


def test_rediscovered_candidate_can_improve_retrieval_tier_despite_lower_overlap_score(isolated):
    _, reads, responses = isolated
    first = ["https://edition.example/first", "https://edition.example/second"]
    revisited, catalog = "https://edition.example/revisited", "https://store.example/item"
    responses.update({url: failure(url, "access_denied", 403)
                      for url in first + [revisited, catalog]})
    work = "Dante, Purgatorio, Divine Comedy"
    earlier = dict(lead(revisited), title="Dante Purgatorio Divine Comedy desire freedom catalogue")
    later = dict(lead(revisited), title="A passage")
    competitor = dict(lead(catalog), title="Dante Purgatorio Divine Comedy desire freedom catalogue")
    earlier_rank = research.evidence_quality.rank_candidate(earlier, work=work, question=QUESTION)
    later_rank = research.evidence_quality.rank_candidate(later, work=work, question=QUESTION)
    assert earlier_rank["retrieval_tier"] == 1 and later_rank["retrieval_tier"] == 0
    assert later_rank["score"] < earlier_rank["score"]
    gateway = FakeGateway([
        ("Initial candidates.", [earlier] + [lead(url) for url in first]),
        ("Revised metadata for the pending URL.", [competitor, later]),
        ("No new candidates.", [])])
    ctx = quoteless_context()
    ctx["focus"]["work"] = work
    state = execute(gateway, ctx)["evidence_research"]
    assert reads == first + [revisited, catalog]
    assert state["candidate_rankings"][revisited]["retrieval_tier"] == 0
    assert state["candidate_rankings"][revisited]["score"] == later_rank["score"]


def test_search_prompt_discloses_reader_formats_and_inherited_failures(isolated):
    _, reads, _ = isolated
    blocked = "https://archive.example/previously-blocked"
    pdf = "https://academy.example/previously-unreadable.pdf"
    ctx = quoteless_context()
    ctx["research_resume"].update(attempted_urls=[blocked, pdf],
        url_outcomes={blocked: {"status": "access_denied", "http_status": 403},
                      pdf: {"status": "unsupported_content_type", "http_status": 200}})
    gateway = FakeGateway([("No public alternative.", [])] * 3)
    execute(gateway, ctx)
    assert reads == []
    for prompt, _ in gateway.search_calls:
        assert "HTML" in prompt and "plain text" in prompt
        assert "PDF" in prompt
        assert blocked in prompt and "access_denied" in prompt
        assert pdf in prompt and "unsupported_content_type" in prompt
        record, _ = json.JSONDecoder().raw_decode(prompt[prompt.index('{"research_question"'):])
        assert record["prior_pass_outcomes"] == [
            {"url": blocked, "status": "access_denied", "http_status": 403},
            {"url": pdf, "status": "unsupported_content_type", "http_status": 200}]
        assert record["prior_pass_outcomes_omitted"] == 0


def test_search_prompt_bounds_prior_history_and_retains_original_failure_on_retry(isolated):
    _, reads, responses = isolated
    historical = [f"https://archive.example/old-{n}" for n in range(25)]
    retry = historical[-1]
    ctx = quoteless_context(inherited=[lead(retry)])
    ctx["research_resume"].update(attempted_urls=historical, retryable_urls=[retry],
        url_outcomes={url: {"status": "timeout", "http_status": None} for url in historical})
    responses[retry] = failure(retry, "not_found", 404)
    gateway = FakeGateway([("No public alternative.", [])] * 3)
    execute(gateway, ctx)
    assert reads == [retry]
    for prompt, _ in gateway.search_calls:
        record, _ = json.JSONDecoder().raw_decode(prompt[prompt.index('{"research_question"'):])
        assert len(record["prior_pass_outcomes"]) == 18
        assert record["prior_pass_outcomes_omitted"] == 7
        assert record["prior_pass_outcomes"][-1] == {"url": retry, "status": "timeout", "http_status": None}
        assert any(item.get("url") == retry and item.get("status") == "not_found"
                   for item in record["previous_outcomes"])


def test_zero_reads_and_weak_readable_text_have_different_missing_evidence_messages(isolated):
    _, reads, responses = isolated
    none = execute(FakeGateway([("No usable route.", [])] * 3), quoteless_context(), trace="trace_no_text")
    url = "https://archive.example/irrelevant"
    responses[url] = found(url, b"An entirely unrelated weather bulletin about rain and snow.")
    weak = execute(FakeGateway([("A candidate.", [lead(url)]), ("No more.", []), ("No more.", [])]),
                   quoteless_context(), trace="trace_weak_text")
    assert none["evidence_research"]["source_count"] == 0
    assert none["evidence_research"]["remaining_requirement"].startswith("No readable source text was obtained")
    assert weak["evidence_research"]["source_count"] == 1
    assert weak["evidence_research"]["usable_source_count"] == 0
    assert "lexical screen" in weak["evidence_research"]["remaining_requirement"]
    assert "No readable source text" not in weak["evidence_research"]["remaining_requirement"]


def test_prior_research_plan_requires_fresh_proposal_before_dispatch(isolated):
    tmp, reads, _ = isolated
    ctx = quoteless_context()
    assert ctx["research_plan"]["version"] == 3
    ctx["research_plan"]["version"] = 2
    gateway = FakeGateway()
    with pytest.raises(ValueError, match="fresh proposal"):
        execute(gateway, ctx)
    assert not reads and not gateway.search_calls and not gateway.final_prompts
    assert not (tmp / "deeper_evidence").exists()
