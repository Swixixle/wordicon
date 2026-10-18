"""Revision four — defer question-blind initial reads (the Freud run, 2026-10-17).

The first live r3 pass spent its two initial reads on inherited Dante leads
for a Freud question; the record itself had ranked each one tier 0, score 0,
no matched question or work term. When NOTHING pending shows any meaningful
overlap, the initial batch now defers to the first search. The law stays
defer-never-exclude: the carried leads remain queued and readable once
discovery has had its chance, a previously attempted retryable URL keeps its
promised retry whatever its lexical score, and the deferral is recorded with
its reason instead of silently reordering the pass.
"""
import json

import pytest

from test_evidence_research import (FakeGateway, complete_rounds, context, execute,
                                    found, isolated, lead, research)

QUESTION = "Help me understand manifest and latent dream content on its own terms?"
PASSAGE = b"The manifest dream content disguises the latent dream thoughts beneath it."


def blind_lead(url, n):
    # the live shape: a lead carried from an earlier, differently-aimed step —
    # its title shares no meaningful term with this question or work
    return {**lead(url), "title": f"Letter to Cangrande allegory page {n}"}


def freud_context(*, inherited=(), retryable=(), goal=None):
    value = context(question=QUESTION,
                    focus={"title": "Manifest and latent dream content", "work": "Freud, The Interpretation of Dreams"},
                    research_resume={"leads": list(inherited), "retryable_urls": list(retryable)})
    value["root"]["selection"].update(quote="", quote_status="none")
    if goal is not None:
        value["research_goal"] = goal
    return value


class ObservedGateway(FakeGateway):
    def __init__(self, rounds, reads):
        super().__init__(rounds)
        self.reads = reads
        self.reads_before_search = []

    def complete_with_search_budget(self, prompt, *, max_uses):
        self.reads_before_search.append(len(self.reads))
        return super().complete_with_search_budget(prompt, max_uses=max_uses)


def test_question_blind_inherited_queue_defers_initial_reads_to_discovery(isolated):
    _, reads, responses = isolated
    blind = [f"https://dante.example/cangrande-{n}" for n in range(4)]
    responses.update({url: found(url, b"Allegory of the Cangrande letter, four senses.") for url in blind})
    on_question = "https://texts.example/freud-interpretation-dreams-ch6"
    responses[on_question] = found(on_question, PASSAGE)
    gateway = ObservedGateway(complete_rounds([("A primary text.", [{**lead(on_question), "title": "Freud, The Interpretation of Dreams, Chapter VI"}]),
                               ("No new leads.", []), ("No new leads.", [])]), reads)
    state = execute(gateway, freud_context(inherited=[blind_lead(u, n) for n, u in enumerate(blind)]))["evidence_research"]
    # no read before the first search; the on-question lead is read first after it
    assert gateway.reads_before_search[0] == 0
    assert reads[0] == on_question
    # the deferral is a recorded step with its reason, not a silent reordering
    deferrals = [s for s in state["steps"] if s.get("status") == "initial_reads_deferred"]
    assert len(deferrals) == 1 and "carried-over lead" in deferrals[0]["reason"]
    assert "stay saved" in deferrals[0]["reason"]
    # defer, never exclude: the blind leads remain ranked and pending or read later
    for url in blind:
        assert url in state["candidate_rankings"]
        rank = state["candidate_rankings"][url]
        assert rank["matched_question_terms"] == [] and rank["matched_work_terms"] == []


def test_any_meaningful_inherited_lead_keeps_the_initial_batch(isolated):
    _, reads, responses = isolated
    blind = "https://dante.example/cangrande-letter"
    named = "https://texts.example/freud-dreams-overview"
    responses[blind] = found(blind, b"Allegory page.")
    responses[named] = found(named, PASSAGE)
    inherited = [blind_lead(blind, 0), {**lead(named), "title": "Freud on dreams: an overview"}]
    gateway = ObservedGateway(complete_rounds([]), reads)
    state = execute(gateway, freud_context(inherited=inherited))["evidence_research"]
    # one lead names the work, so the initial batch proceeds — and the
    # ordering puts the matching lead first
    assert gateway.reads_before_search[0] == 2
    assert reads[0] == named
    assert not [s for s in state["steps"] if s.get("status") == "initial_reads_deferred"]


def test_deferred_leads_are_still_read_once_discovery_has_had_its_chance(isolated):
    _, reads, responses = isolated
    blind = [f"https://dante.example/cangrande-{n}" for n in range(2)]
    responses.update({url: found(url, b"Allegory of the letter.") for url in blind})
    # every search fails: no fresh lead ever arrives
    gateway = ObservedGateway([TimeoutError("down")] * 6, reads)
    state = execute(gateway, freud_context(inherited=[blind_lead(u, n) for n, u in enumerate(blind)]))["evidence_research"]
    assert gateway.reads_before_search[0] == 0          # deferred at the start
    assert set(reads) == set(blind)                     # but read after the strategies ran: never excluded
    assert state["rounds_used"] == 6


def test_retryable_url_keeps_its_promised_retry_whatever_its_score(isolated):
    _, reads, responses = isolated
    retry = "https://dante.example/timed-out-last-pass"
    responses[retry] = found(retry, PASSAGE)
    gateway = ObservedGateway(complete_rounds([]), reads)
    state = execute(gateway, freud_context(inherited=[blind_lead(retry, 0)], retryable=[retry]))["evidence_research"]
    # attempted-for-a-question beats lexical blindness: the retry happens in
    # the initial batch, as revision three promised
    assert gateway.reads_before_search[0] == 1
    assert reads[0] == retry
    assert not [s for s in state["steps"] if s.get("status") == "initial_reads_deferred"]


def test_plan_names_the_deferral_and_proposal_wording_matches(isolated):
    plan = research.plan()
    assert plan["version"] == 6
    assert "initial reads wait for fresh search leads" in plan["source_selection"]
    assert "Preserve all leads" in plan["source_selection"]
