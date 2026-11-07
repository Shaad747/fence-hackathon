"""Proposal review with isolated baseline and source-checked memory citations."""

import asyncio
import json
import re
from collections import defaultdict
from collections.abc import Awaitable
from time import monotonic
from typing import TypeVar

from groq.types.chat import ChatCompletionMessageParam

from core.llm import LLMClient, LLMServiceError
from core.memory import MemoryClient, MemoryServiceError
from core.prompts import CHECKS, EXTRACT_PROPOSAL, GROUNDED_REVIEW, NO_MEMORY_BASELINE
from core.schemas import (
    BaselineReport, FenceReport, PipelineIssue, PipelineResult, Proposal, ProposalExtraction,
    RankedEvidence, RecalledMemory, RecommendationDraft, ServiceFailure, SimilarDecision,
)

MAX_PROPOSAL_LENGTH = 3000
EXTRACTION_SECONDS = 12
RECALL_SECONDS = 16
REPORT_SECONDS = 14
MAX_CANDIDATES = 8
_GENERAL_CHECKS = [CHECKS[theme] for theme in ("customer_impact", "economics", "pilot_criteria")]
_ACTION = {
    "pause": "Pause the rollout until the checks below are resolved.",
    "pilot": "Run a limited pilot before committing to a wider rollout.",
    "proceed_with_checks": "Proceed once the checks below are satisfied.",
}
_STOP_WORDS = set("""about after an and are as at be before by can could does for from has have in into is it
    move next of on only or our plan should some than that the their them then these they this those through to
    under use used want was we were what when where which while
    will with would your company customer kaveri merchant pay proposed proposal team decision""".split())
T = TypeVar("T")


def _messages(instruction: str, data: dict) -> list[ChatCompletionMessageParam]:
    return [{"role": "system", "content": instruction}, {"role": "user", "content": json.dumps(data)}]


async def _bounded(call: Awaitable[T], seconds: int, label: str) -> T | ServiceFailure:
    try:
        async with asyncio.timeout(seconds):
            return await call
    except (LLMServiceError, MemoryServiceError) as exc:
        return exc.error
    except TimeoutError:
        return ServiceFailure(code="timeout", message=f"{label} did not finish in time.",
                              next_step="Try the proposal check again.", retryable=True)


def _terms(text: str) -> set[str]:
    words = re.findall(r"\b[a-z][a-z0-9]+\b", text.lower())
    return {word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word
            for word in words} - _STOP_WORDS


def _source_fields(memory: RecalledMemory) -> dict[str, str]:
    if not memory.source_text or memory.source_truncated or not memory.document_id:
        return {}
    fields = dict(line.split(": ", 1) for line in memory.source_text.splitlines() if ": " in line)
    if (fields.get("Source reference") != memory.document_id or fields.get("Decision") != memory.title
            or not memory.date or fields.get("Date") != memory.date.isoformat()):
        return {}
    return fields


def _conflicting_documents(memories: list[RecalledMemory]) -> set[str]:
    versions: dict[str, set[str]] = defaultdict(set)
    for memory in memories:
        if _source_fields(memory):
            versions[memory.document_id].add(memory.source_text)
    return {document_id for document_id, texts in versions.items() if len(texts) > 1}


def rank_evidence(
    proposal: Proposal, recalls: list[list[RecalledMemory]], feedback: dict[str, float],
) -> list[RankedEvidence]:
    """Fuse ranks across queries. Votes adjust ordering only after the relevance gate."""
    by_id: dict[str, list[RecalledMemory]] = defaultdict(list)
    all_hits: dict[str, list[RecalledMemory]] = defaultdict(list)
    conflicting_documents = _conflicting_documents([hit for matches in recalls for hit in matches])
    for matches in recalls:
        seen: set[str] = set()
        for match in matches:
            all_hits[match.memory_id].append(match)
            if match.memory_id not in seen:
                by_id[match.memory_id].append(match)
                seen.add(match.memory_id)

    topic = _terms(proposal.original_input)
    if proposal.extraction:
        topic |= _terms(proposal.extraction.intent)
    evidence = []
    for memory_id, hits in by_id.items():
        memory = min(hits, key=lambda hit: (not bool(_source_fields(hit)), not bool(hit.document_id), hit.retrieval_rank))
        fields = _source_fields(memory)
        versions = all_hits[memory_id]
        provenance_conflict = (memory.document_id in conflicting_documents
                               or len({(hit.document_id, hit.title, hit.date, hit.evidence_text) for hit in versions}) > 1
                               or len({hit.source_text for hit in versions if _source_fields(hit)}) > 1)
        historical_topic = " ".join([memory.title, fields.get("Proposal", ""), fields.get("Tags", ""), memory.evidence_text])
        shared = sorted(topic & _terms(historical_topic))
        eligible = (len(shared) >= 2 and bool(memory.document_id) and memory.title != "Untitled recalled memory"
                    and not provenance_conflict)
        rank_signal = sum(1 / hit.retrieval_rank for hit in hits) / len(recalls)
        provenance = 1 if fields else 0.5 if memory.document_id and memory.date else 0
        impact = fields.get("Impact")
        reasons = fields.get("Reasons")
        usefulness = (bool(impact) + bool(reasons)) / 2
        adjustment = 0.1 * max(-1.0, min(1.0, feedback.get(memory_id, 0.0))) if eligible else 0.0
        score = 0.5 * min(1, len(shared) / 6) + 0.25 * rank_signal + 0.12 * provenance + 0.13 * usefulness
        outcome = fields.get("Outcome", "").rstrip(".")
        evidence.append(RankedEvidence(
            memory=memory, matched_terms=shared, query_count=len(hits),
            ranking_signal=round(max(0, min(1, score + adjustment)), 4), feedback_adjustment=adjustment,
            eligible=eligible, provenance_conflict=provenance_conflict,
            outcome=outcome if outcome in {"success", "partial", "failed", "rolled_back"} else None,
            what_happened=" ".join(part for part in (impact, reasons) if part) or memory.evidence_text,
        ))
    return sorted(evidence, key=lambda item: (not item.eligible, -item.ranking_signal, item.memory.memory_id))


def _candidates(evidence: list[RankedEvidence]) -> dict[str, RankedEvidence]:
    selected = {}
    documents = set()
    for item in evidence:
        doc = item.memory.document_id
        if item.eligible and doc not in documents:
            selected[item.memory.memory_id] = item
            documents.add(doc)
            if len(selected) == MAX_CANDIDATES:
                break
    return selected


def _safe_report(message: str) -> FenceReport:
    return FenceReport(risk_level="medium", recommendation="pause", summary=message,
                       similar_decisions=[], checks_before_proceeding=_GENERAL_CHECKS,
                       confidence=0, memory_found=False)


def _compile_report(
    draft: RecommendationDraft, candidates: dict[str, RankedEvidence], partial: bool,
) -> FenceReport:
    ids = draft.memory_ids
    if (any(memory_id not in candidates for memory_id in ids) or len(set(ids)) != len(ids)
            or len(set(draft.check_themes)) != 3):
        raise ValueError("The recommendation contains unsupported citations or repeated checks.")
    selected = [candidates[memory_id] for memory_id in ids]
    outcomes = {item.outcome for item in selected}
    mixed = "success" in outcomes and bool(outcomes & {"failed", "partial", "rolled_back"})
    action = "pilot" if mixed and draft.recommendation == "proceed_with_checks" else draft.recommendation
    risk = "medium" if mixed and draft.risk_level == "low" else draft.risk_level
    summary = _ACTION[action]
    if mixed:
        summary += " The cited decisions had mixed outcomes. Check which rollout conditions apply here."
    if partial:
        summary += " Some archive evidence was unavailable or inconsistent."
    return FenceReport(
        risk_level=risk, recommendation=action, summary=summary, memory_found=True, mixed_evidence=mixed,
        confidence=0.5 if partial or mixed else 0.7,
        similar_decisions=[SimilarDecision(
            decision_title=item.memory.title, decision_date=item.memory.date,
            similarity_reason="Shared decision terms: " + ", ".join(item.matched_terms[:5]) + ".",
            what_happened=item.what_happened,
            why_it_matters=("Check whether the conditions that helped this decision apply here."
                            if item.outcome == "success" else "Check whether the same conditions could affect this proposal."),
            memory_ids=[item.memory.memory_id],
        ) for item in selected],
        checks_before_proceeding=[CHECKS[theme] for theme in draft.check_themes],
    )


async def _review(text: str, truncated: bool, memory: MemoryClient, llm: LLMClient) -> PipelineResult:
    issues: list[PipelineIssue] = []
    evidence: list[RankedEvidence] = []
    queries: list[str] = []
    retrieval_status = "not_run"
    report_status = "unavailable"
    data = {"proposal": text}
    extraction = await _bounded(llm.structured_chat(
        _messages(EXTRACT_PROPOSAL, data), ProposalExtraction, max_completion_tokens=768, reasoning_effort="low",
    ), EXTRACTION_SECONDS, "Proposal extraction")
    if isinstance(extraction, ServiceFailure):
        issues.append(PipelineIssue(stage="extraction", error=extraction))
        proposal = Proposal(original_input=text, extraction=None, input_truncated=truncated)
        report = _safe_report("Proposal analysis is unavailable. Try the check again.")
    else:
        proposal = Proposal(original_input=text, extraction=extraction, input_truncated=truncated)
        intent = extraction.intent[:250]
        queries = [
            f"Past decisions with the same action and affected group: {intent} {text[:150]}",
            f"Historical decisions in {extraction.team_or_domain[:100]} comparable to {intent}",
            f"Comparable decision outcomes for {intent[:140]}. Risks: {', '.join(extraction.risk_themes)[:140]}. "
            f"Unverified assumptions: {', '.join(extraction.assumptions)[:110]}",
        ]
        results = await asyncio.gather(*[
            _bounded(memory.recall_for_proposal(query, budget="low", max_tokens=1200), RECALL_SECONDS, "Archive search")
            for query in queries
        ], _bounded(memory.feedback_signals(f"Past relevance votes on decisions comparable to {intent}"),
                    RECALL_SECONDS, "Feedback search"))
        recalls = []
        for result in results[:len(queries)]:
            if isinstance(result, ServiceFailure):
                issues.append(PipelineIssue(stage="recall", error=result))
            else:
                recalls.append(result)
        feedback = results[-1]
        if isinstance(feedback, ServiceFailure):
            issues.append(PipelineIssue(stage="feedback", error=feedback))
            feedback = {}
        retrieval_status = "complete" if len(recalls) == len(queries) else "partial" if recalls else "unavailable"
        evidence = rank_evidence(proposal, recalls, feedback)
        if any(item.provenance_conflict for item in evidence):
            retrieval_status = "partial"
            issues.append(PipelineIssue(stage="recall", error=ServiceFailure(
                code="conflict", message="Some recalled facts had inconsistent source records and were excluded.",
                next_step="Inspect the conflicting archive records before using them.",
            )))
        candidates = _candidates(evidence)
        if not candidates:
            report = _safe_report("No relevant history was found." if retrieval_status == "complete"
                                  else "Archive evidence was unavailable or incomplete. Relevant history could not be confirmed.")
            if retrieval_status == "complete":
                report_status = "no_relevant_history"
        else:
            draft = await _bounded(llm.structured_chat(_messages(GROUNDED_REVIEW, {
                **data, "check_themes": CHECKS,
                "candidates": [{"memory_id": key, "title": item.memory.title,
                                "date": item.memory.date.isoformat() if item.memory.date else None,
                                "outcome": item.outcome, "what_happened": item.what_happened[:1100],
                                "matched_terms": item.matched_terms}
                               for key, item in candidates.items()],
            }), RecommendationDraft, max_completion_tokens=1024, reasoning_effort="low"), REPORT_SECONDS, "Grounded review")
            if isinstance(draft, ServiceFailure):
                issues.append(PipelineIssue(stage="report", error=draft))
                report = _safe_report("The archive was searched, but the grounded review is unavailable. Try again.")
            else:
                try:
                    if draft.memory_ids:
                        report = _compile_report(draft, candidates, retrieval_status == "partial")
                        report_status = "grounded"
                    elif retrieval_status == "complete":
                        report = _safe_report("No relevant history was found.")
                        report_status = "no_relevant_history"
                    else:
                        report = _safe_report("The partial search did not confirm relevant history. Try again.")
                except ValueError:
                    issues.append(PipelineIssue(stage="report", error=ServiceFailure(
                        code="invalid_response", message="The review could not be verified against retrieved evidence.",
                        next_step="Inspect the recalled evidence or try the proposal check again.",
                    )))
                    report = _safe_report("The grounded review did not pass verification. Inspect the evidence or try again.")

    return PipelineResult(
        proposal=proposal, report=report, baseline=None, evidence=evidence,
        citation_ids=[memory_id for decision in report.similar_decisions for memory_id in decision.memory_ids],
        retrieval_status=retrieval_status, report_status=report_status, recall_queries=queries, issues=issues,
        elapsed_seconds=0,
    )


async def check_proposal(text: str, memory: MemoryClient, llm: LLMClient) -> PipelineResult:
    """Run the baseline with the same proposal, concurrently and without archive context."""
    started = monotonic()
    text = text.strip()
    if len(text) < 20:
        raise ValueError("Describe the decision in at least 20 characters before running a check.")
    truncated = len(text) > MAX_PROPOSAL_LENGTH
    text = text[:MAX_PROPOSAL_LENGTH].rstrip()
    baseline, review = await asyncio.gather(_bounded(llm.structured_chat(
        _messages(NO_MEMORY_BASELINE, {"proposal": text}), BaselineReport,
        max_completion_tokens=768, reasoning_effort="low",
    ), REPORT_SECONDS, "No-memory baseline"), _review(text, truncated, memory, llm))
    if isinstance(baseline, ServiceFailure):
        review.issues.append(PipelineIssue(stage="baseline", error=baseline))
    else:
        review.baseline = baseline
    review.elapsed_seconds = round(monotonic() - started, 3)
    return review
