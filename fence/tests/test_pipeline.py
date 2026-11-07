"""Pipeline tests use the real seed and scripted provider responses."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.llm import LLMServiceError
from core.memory import DECISION_PREFIX, MemoryServiceError, decision_content
from core.pipeline import MAX_PROPOSAL_LENGTH, check_proposal, rank_evidence
from core.schemas import (
    BaselineReport, Proposal, ProposalExtraction, RecalledMemory, RecommendationDraft, ServiceFailure,
)
from seed.seed import load_decisions

LOTUS_PROPOSAL = "Remove the free tier for small merchants and move them to a Rs 299/month plan next quarter."
LOTUS = next(item for item in load_decisions() if item.title == "Project Lotus")
SMS = next(item for item in load_decisions() if item.title == "SMS provider switch")
EXTRACTION = ProposalExtraction(
    intent="End the free merchant tier and migrate small merchants to a paid monthly plan",
    assumptions=["Small merchants can absorb the price increase"], team_or_domain="Pricing and growth",
    risk_themes=["merchant churn", "support capacity", "competitor campaigns"],
)
BASELINE = BaselineReport(summary="Test willingness to pay before changing pricing.",
                          checks_before_proceeding=["Interview merchants", "Model churn", "Pilot the price"])
LOTUS_CHECKS = ["support_capacity", "competitor_timing", "migration_path"]


def recalled(decision, memory_id, rank=1):
    return RecalledMemory(memory_id=memory_id, document_id=DECISION_PREFIX + decision.id,
                          title=decision.title, date=decision.date, evidence_text=decision.impact,
                          source_text=decision_content(decision), retrieval_query="test query", retrieval_rank=rank,
                          ranking_signal=1 / rank)


def recommendation(*ids):
    return RecommendationDraft(risk_level="high", recommendation="pause",
                               memory_ids=list(ids), check_themes=LOTUS_CHECKS)


def providers(recalls, *, draft=None, extraction=EXTRACTION, baseline=BASELINE, votes=None):
    async def structured(messages, schema, **kwargs):
        value = {ProposalExtraction: extraction, BaselineReport: baseline, RecommendationDraft: draft}[schema]
        if isinstance(value, Exception):
            raise value
        assert isinstance(value, schema)
        return value

    return (
        SimpleNamespace(recall_for_proposal=AsyncMock(side_effect=recalls),
                        feedback_signals=AsyncMock(return_value=votes or {})),
        SimpleNamespace(structured_chat=AsyncMock(side_effect=structured)),
    )


def test_lotus_preserves_original_proposal_and_cites_source_facts():
    lotus = recalled(LOTUS, "lotus-fact")
    sms = recalled(SMS, "sms-fact", rank=2)
    memory, llm = providers([[lotus, sms], [lotus], [lotus]], draft=recommendation("lotus-fact"))
    result = asyncio.run(check_proposal(LOTUS_PROPOSAL, memory, llm))

    assert result.proposal.original_input == LOTUS_PROPOSAL
    assert result.proposal.extraction == EXTRACTION
    assert "absorb the price increase" not in result.proposal.original_input
    assert result.baseline == BASELINE
    assert result.retrieval_status == "complete" and result.report_status == "grounded"
    assert len(result.recall_queries) == len(set(result.recall_queries)) == 3
    assert "Pricing and growth" in result.recall_queries[1]
    assert "support capacity" in result.recall_queries[2]
    assert "Unverified assumptions:" in result.recall_queries[2]
    assert memory.recall_for_proposal.await_count == 3
    assert all(call.kwargs == {"budget": "low", "max_tokens": 1200}
               for call in memory.recall_for_proposal.await_args_list)
    assert result.report.risk_level == "high" and result.report.memory_found
    assert result.citation_ids == ["lotus-fact"]
    assert [item.memory.memory_id for item in result.evidence] == ["lotus-fact", "sms-fact"]
    assert result.evidence[0].query_count == 3
    assert not result.evidence[1].eligible
    [similar] = result.report.similar_decisions
    assert similar.decision_title == LOTUS.title and similar.decision_date == LOTUS.date
    assert similar.what_happened == " ".join([LOTUS.impact, *LOTUS.reasons])
    assert similar.memory_ids == ["lotus-fact"]
    assert len(result.report.checks_before_proceeding) == 3
    assert "support" in result.report.checks_before_proceeding[0]
    assert "competitor" in result.report.checks_before_proceeding[1]
    assert "migration path" in result.report.checks_before_proceeding[2]
    grounded = next(call.args[0] for call in llm.structured_chat.await_args_list if call.args[1] is RecommendationDraft)
    payload = json.loads(grounded[1]["content"])
    assert [item["memory_id"] for item in payload["candidates"]] == ["lotus-fact"]


def test_baseline_starts_independently_and_receives_only_the_same_proposal():
    async def run():
        baseline_started = asyncio.Event()
        all_searches_started = asyncio.Event()
        queries = []

        async def structured(messages, schema, **kwargs):
            payload = json.loads(messages[1]["content"])
            assert payload == {"proposal": LOTUS_PROPOSAL}
            if schema is BaselineReport:
                baseline_started.set()
                assert "Project Lotus" not in json.dumps(messages)
                assert EXTRACTION.intent not in json.dumps(messages)
                return BASELINE
            await baseline_started.wait()
            return EXTRACTION

        async def recall(query, **kwargs):
            queries.append(query)
            if len(queries) == 3:
                all_searches_started.set()
            await all_searches_started.wait()
            return []

        memory = SimpleNamespace(recall_for_proposal=recall, feedback_signals=AsyncMock(return_value={}))
        result = await asyncio.wait_for(check_proposal(LOTUS_PROPOSAL, memory,
                                                       SimpleNamespace(structured_chat=structured)), timeout=1)
        assert result.baseline == BASELINE
        assert result.report_status == "no_relevant_history"

    asyncio.run(run())


@pytest.mark.parametrize("memory_id", ["invented-citation", "sms-fact"])
def test_fabricated_and_unsupplied_citations_never_become_valid(memory_id):
    memory, llm = providers([[recalled(LOTUS, "lotus-fact"), recalled(SMS, "sms-fact")], [], []],
                            draft=recommendation("lotus-fact", memory_id))
    result = asyncio.run(check_proposal(LOTUS_PROPOSAL, memory, llm))
    assert result.retrieval_status == "complete"
    assert result.report_status == "unavailable"
    assert result.citation_ids == [] and result.report.similar_decisions == []
    assert not result.report.memory_found
    assert len(result.evidence) == 2
    assert result.issues[0].stage == "report" and result.issues[0].error.code == "invalid_response"
    assert result.baseline == BASELINE


def test_votes_can_reorder_comparable_records_without_promoting_irrelevant_evidence():
    proposal = Proposal(original_input=LOTUS_PROPOSAL, extraction=EXTRACTION)
    other = LOTUS.model_copy(update={"id": "alternate-pricing", "title": "Alternate pricing rollout"})
    hits = [[recalled(LOTUS, "lotus", 1), recalled(other, "other", 2), recalled(SMS, "irrelevant", 1)]]
    before = rank_evidence(proposal, hits, {})
    after = rank_evidence(proposal, hits, {"other": 8, "lotus": -1, "irrelevant": 1})
    assert [item.memory.memory_id for item in before] == ["lotus", "other", "irrelevant"]
    assert [item.memory.memory_id for item in after] == ["other", "lotus", "irrelevant"]
    assert after[0].feedback_adjustment == 0.1 and after[1].feedback_adjustment == -0.1
    assert after[2].feedback_adjustment == 0 and not after[2].eligible


def test_provenance_and_documented_outcomes_win_when_relevance_is_similar():
    proposal = Proposal(original_input=LOTUS_PROPOSAL, extraction=EXTRACTION)
    full = recalled(LOTUS, "full", rank=2)
    truncated = full.model_copy(update={"memory_id": "truncated", "source_truncated": True, "retrieval_rank": 1,
                                        "evidence_text": LOTUS.proposal})
    ranked = rank_evidence(proposal, [[truncated, full]], {})
    assert [item.memory.memory_id for item in ranked] == ["full", "truncated"]
    assert ranked[0].outcome == "failed"
    assert ranked[1].what_happened == truncated.evidence_text and ranked[1].outcome is None


def test_conflicting_versions_of_one_fact_cannot_be_cited():
    fact = recalled(LOTUS, "same")
    contradictory = fact.model_copy(update={"evidence_text": "No merchants churned after free tier removal."})
    memory, llm = providers([[fact], [contradictory], [fact]], votes={"same": 1})
    result = asyncio.run(check_proposal(LOTUS_PROPOSAL, memory, llm))
    assert result.citation_ids == []
    assert not result.evidence[0].eligible and result.evidence[0].feedback_adjustment == 0
    assert result.evidence[0].provenance_conflict
    assert result.retrieval_status == "partial" and result.report_status == "unavailable"
    assert result.issues[0].error.code == "conflict"


def test_mixed_precedents_are_preserved_and_recommend_a_pilot():
    success = LOTUS.model_copy(update={"id": "staged-pricing", "title": "Staged pricing pilot", "outcome": "success",
                                       "reasons": ["Support was staffed for the pilot."], "impact": "98% renewed."})
    draft = RecommendationDraft(risk_level="low", recommendation="proceed_with_checks",
                                memory_ids=["lotus", "success"], check_themes=LOTUS_CHECKS)
    memory, llm = providers([[recalled(LOTUS, "lotus"), recalled(success, "success")], [], []], draft=draft)
    result = asyncio.run(check_proposal(LOTUS_PROPOSAL, memory, llm))
    assert result.citation_ids == ["lotus", "success"] and result.report.mixed_evidence
    assert result.report.recommendation == "pilot" and result.report.risk_level == "medium"
    assert "mixed outcomes" in result.report.summary
    assert "98% renewed." in result.report.similar_decisions[1].what_happened


def memory_timeout():
    return MemoryServiceError(ServiceFailure(code="timeout", message="Search timed out.", next_step="Retry the search."))


@pytest.mark.parametrize("recall_results,retrieval_status,report_status", [
    ([[], [], []], "complete", "no_relevant_history"),
    ([memory_timeout(), [], []], "partial", "unavailable"),
    ([memory_timeout(), memory_timeout(), memory_timeout()], "unavailable", "unavailable"),
])
def test_empty_recall_is_distinct_from_partial_or_failed_retrieval(recall_results, retrieval_status, report_status):
    memory, llm = providers(recall_results)
    result = asyncio.run(check_proposal(LOTUS_PROPOSAL, memory, llm))
    assert result.retrieval_status == retrieval_status and result.report_status == report_status
    assert (result.report.summary == "No relevant history was found.") == (retrieval_status == "complete")
    assert not result.report.memory_found and result.citation_ids == []
    assert len(result.report.checks_before_proceeding) == 3
    assert result.baseline == BASELINE
    assert all(issue.error.code == "timeout" for issue in result.issues)
    assert llm.structured_chat.await_count == 2


def test_partial_retrieval_can_still_return_verified_citations():
    memory, llm = providers([memory_timeout(), [recalled(LOTUS, "lotus")], []], draft=recommendation("lotus"))
    result = asyncio.run(check_proposal(LOTUS_PROPOSAL, memory, llm))
    assert result.retrieval_status == "partial" and result.report_status == "grounded"
    assert result.citation_ids == ["lotus"]
    assert "Some archive evidence was unavailable or inconsistent." in result.report.summary
    assert result.issues[0].stage == "recall"


def test_deadline_cancels_hanging_searches_without_reporting_empty_history(monkeypatch):
    monkeypatch.setattr("core.pipeline.RECALL_SECONDS", 0.02)
    memory, llm = providers([])

    async def hang(query, **kwargs):
        await asyncio.Future()

    memory.recall_for_proposal.side_effect = hang
    result = asyncio.run(check_proposal(LOTUS_PROPOSAL, memory, llm))
    assert result.retrieval_status == "unavailable" and result.report_status == "unavailable"
    assert [(issue.stage, issue.error.code) for issue in result.issues] == [("recall", "timeout")] * 3
    assert result.baseline == BASELINE and result.citation_ids == []


@pytest.mark.parametrize("stage", ["extraction", "report", "baseline"])
def test_one_model_failure_preserves_the_other_answer(stage):
    failure = LLMServiceError("invalid_response", "Model output was invalid.", "Retry the check.")
    options = {"draft": recommendation("lotus")}
    options["draft" if stage == "report" else stage] = failure
    memory, llm = providers([[recalled(LOTUS, "lotus")], [], []], **options)
    result = asyncio.run(check_proposal(LOTUS_PROPOSAL, memory, llm))
    assert any(issue.stage == stage and issue.error.code == "invalid_response" for issue in result.issues)
    assert (result.baseline is None) == (stage == "baseline")
    assert (result.report_status == "grounded") == (stage == "baseline")
    if stage == "extraction":
        assert result.retrieval_status == "not_run" and result.proposal.extraction is None
        assert memory.recall_for_proposal.await_count == 0


def test_input_validation_and_identical_truncation_for_both_model_paths():
    memory, llm = providers([[], [], []])
    with pytest.raises(ValueError, match="at least 20 characters"):
        asyncio.run(check_proposal("too short", memory, llm))
    assert llm.structured_chat.await_count == 0
    long_proposal = LOTUS_PROPOSAL + "x" * MAX_PROPOSAL_LENGTH
    result = asyncio.run(check_proposal(long_proposal, memory, llm))
    assert result.proposal.input_truncated
    assert result.proposal.original_input == long_proposal[:MAX_PROPOSAL_LENGTH]
    for call in llm.structured_chat.await_args_list:
        assert json.loads(call.args[0][1]["content"]) == {"proposal": result.proposal.original_input}


def test_conflicting_duplicate_fact_within_one_query_is_not_citable():
    first = recalled(LOTUS, 'same-fact')
    conflicting = first.model_copy(update={'evidence_text':'No churn occurred.'})
    memory, llm = providers([[first, conflicting], [], []], draft=recommendation('same-fact'))
    result = asyncio.run(check_proposal(LOTUS_PROPOSAL, memory, llm))
    assert result.citation_ids == []
    assert result.evidence[0].provenance_conflict
    assert result.evidence[0].query_count == 1
    assert result.report_status == 'unavailable'


def test_different_facts_with_conflicting_document_versions_are_excluded():
    first = recalled(LOTUS, 'fact-one')
    second = first.model_copy(update={'memory_id':'fact-two','source_text':first.source_text.replace('31%', '0%')})
    memory, llm = providers([[first,second],[],[]], draft=recommendation('fact-one'))
    result = asyncio.run(check_proposal(LOTUS_PROPOSAL, memory, llm))
    assert result.citation_ids == []
    assert all(item.provenance_conflict and not item.eligible for item in result.evidence)
