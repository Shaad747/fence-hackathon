"""Typed records shared by the memory adapter and proposal pipeline."""

from datetime import date as Date
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
StableId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Decision(Record):
    id: StableId
    title: Text
    date: Date
    owner: Text
    team: Text
    proposal: Text
    outcome: Literal["success", "partial", "failed", "rolled_back"]
    reasons: list[Text] = Field(min_length=1)
    impact: Text
    tags: list[Text] = Field(min_length=1)


class Outcome(Record):
    proposal_reference: Text
    status: Literal["accepted", "approved", "rejected", "modified", "pending", "shipped", "failed"]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    report_reference: StableId | None = None
    proposal_text: str | None = None
    memory_ids: list[Text] = Field(default_factory=list)
    citation_ids: list[Text] = Field(default_factory=list)
    timestamp: AwareDatetime
    event_id: StableId


class Feedback(Record):
    proposal_reference: str | None = None
    proposal_or_report_reference: Text
    lesson: Text
    memory_ids: list[Text] = Field(min_length=1)
    relevance: Literal["relevant", "not_relevant"]
    timestamp: AwareDatetime
    event_id: StableId


class RecalledMemory(Record):
    memory_id: Text
    document_id: str | None = None
    title: Text
    date: Date | None = None
    evidence_text: Text
    source_text: str | None = None
    source_truncated: bool = False
    retrieval_query: Text
    retrieval_rank: int = Field(ge=1)
    ranking_signal: float = Field(ge=0, le=1)
    ranking_label: Literal["Relative ranking signal"] = "Relative ranking signal"
    provider_scores: dict[str, float | None] = Field(default_factory=dict)
    metadata: dict[str, str] = Field(default_factory=dict)


class Activity(Record):
    operation: Literal["retain", "recall", "reflect", "inspect"]
    action: Text
    attempt: int = Field(ge=1)
    status: Literal["succeeded", "failed", "timeout", "cancelled", "unchanged"]
    elapsed_seconds: float = Field(ge=0)
    error_code: str | None = None


class RetainReceipt(Record):
    document_id: Text
    operation_id: str | None = None
    status: Literal["retained", "unchanged"]


class DocumentSnapshot(Record):
    document_id: Text
    content_hash: str | None = None
    memory_unit_count: int = Field(ge=0)


class ServiceFailure(Record):
    code: Literal["authentication", "configuration", "timeout", "rate_limit", "unavailable", "invalid_response", "operation_failed", "conflict"]
    message: Text
    next_step: Text
    retryable: bool = False


class ProposalExtraction(Record):
    intent: Text
    assumptions: list[Text] = Field(max_length=6)
    team_or_domain: Text
    risk_themes: list[Text] = Field(min_length=1, max_length=6)


class Proposal(Record):
    original_input: Text
    extraction: ProposalExtraction | None
    input_truncated: bool = False


RiskLevel = Literal["low", "medium", "high"]
Recommendation = Literal["pause", "pilot", "proceed_with_checks"]
CheckTheme = Literal[
    "support_capacity", "competitor_timing", "migration_path", "pilot_criteria",
    "risk_review", "rollback", "economics", "vendor_performance", "monitoring",
    "customer_impact", "capacity", "ownership", "data_quality", "representative_sample",
]


class RecommendationDraft(Record):
    risk_level: RiskLevel
    recommendation: Recommendation
    memory_ids: list[Text] = Field(max_length=3)
    check_themes: list[CheckTheme] = Field(min_length=3, max_length=3)


class BaselineReport(Record):
    summary: Text
    checks_before_proceeding: list[Text] = Field(min_length=3, max_length=3)


class SimilarDecision(Record):
    decision_title: Text
    decision_date: Date | None
    similarity_reason: Text
    what_happened: Text
    why_it_matters: Text
    memory_ids: list[Text] = Field(min_length=1)


class FenceReport(Record):
    risk_level: RiskLevel
    recommendation: Recommendation
    summary: Text
    similar_decisions: list[SimilarDecision]
    checks_before_proceeding: list[Text] = Field(min_length=3, max_length=3)
    confidence: float = Field(ge=0, le=1)
    memory_found: bool
    mixed_evidence: bool = False


class RankedEvidence(Record):
    memory: RecalledMemory
    matched_terms: list[str]
    query_count: int = Field(ge=1)
    ranking_signal: float = Field(ge=0, le=1)
    feedback_adjustment: float = Field(ge=-0.1, le=0.1)
    eligible: bool
    provenance_conflict: bool = False
    outcome: Literal["success", "partial", "failed", "rolled_back"] | None
    what_happened: Text


class PipelineIssue(Record):
    stage: Literal["extraction", "recall", "feedback", "report", "baseline"]
    error: ServiceFailure


class PipelineResult(Record):
    proposal: Proposal
    report: FenceReport
    baseline: BaselineReport | None
    evidence: list[RankedEvidence]
    citation_ids: list[str]
    retrieval_status: Literal["complete", "partial", "unavailable", "not_run"]
    report_status: Literal["grounded", "no_relevant_history", "unavailable"]
    recall_queries: list[str]
    issues: list[PipelineIssue]
    elapsed_seconds: float = Field(ge=0)
