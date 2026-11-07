"""Hindsight stores confirmed decisions, outcomes, and feedback. All network attempts are bounded."""

import asyncio
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, time, timezone
from time import monotonic
from uuid import NAMESPACE_URL, uuid5

from aiohttp import ClientConnectionError, ClientError
from hindsight_client import Hindsight
from hindsight_client_api.exceptions import ApiException
from hindsight_client_api.models import ReflectResponse
from pydantic import ValidationError
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import Settings
from core.learning import vote_signals
from core.schemas import (
    Activity, Decision, DocumentSnapshot, Feedback, Outcome, RecalledMemory,
    RetainReceipt, ServiceFailure,
)

DECISION_PREFIX = "fence:decision:"


class MemoryServiceError(Exception):
    def __init__(self, error: ServiceFailure):
        self.error = error
        super().__init__(f"{error.message} {error.next_step}")


class _RetryableError(MemoryServiceError):
    pass


def _failure(code: str, message: str, next_step: str, retryable: bool = False) -> MemoryServiceError:
    error = ServiceFailure(code=code, message=message, next_step=next_step, retryable=retryable)
    return (_RetryableError if retryable else MemoryServiceError)(error)


def _safe_error(exc: Exception) -> MemoryServiceError:
    # Never include provider exception bodies, request headers, or URLs in user-facing errors.
    if isinstance(exc, MemoryServiceError):
        return exc
    if isinstance(exc, TimeoutError):
        return _failure("timeout", "Hindsight did not finish within the time limit.",
                        "Retry the same action; pending retains keep their original identity.", True)
    status = getattr(exc, "status", None)
    if status in {401, 403}:
        return _failure("authentication", "Hindsight rejected the credentials or bank access.",
                        "Check HINDSIGHT_API_KEY and workspace permissions, then retry.")
    if status in {400, 404, 405, 422}:
        return _failure("configuration", "Hindsight rejected the request or server route.",
                        "Check HINDSIGHT_BASE_URL, bank ID, and server/SDK compatibility.")
    if status in {408, 429, 500, 502, 503, 504} or isinstance(exc, ClientConnectionError):
        return _failure("unavailable", "Hindsight is temporarily unavailable.",
                        "Check server health or quota and retry shortly.", True)
    return _failure("invalid_response", "Hindsight returned a response Fence could not use.",
                    "Check server/SDK compatibility and retry; no empty-history result was substituted.")


def decision_content(decision: Decision) -> str:
    """Keep all authoritative details in the retained natural-language source."""
    return "\n".join([
        "Kaveri Pay is a fictional Bengaluru fintech with roughly 220 employees, building UPI payments and merchant tools.",
        "This is an illustrative synthetic past decision, not a real customer outcome.",
        f"Source reference: {DECISION_PREFIX}{decision.id}",
        f"Decision: {decision.title}", f"Date: {decision.date.isoformat()}",
        f"Owner: {decision.owner}; team: {decision.team}.",
        f"Proposal: {decision.proposal}", f"Outcome: {decision.outcome}.",
        "Reasons: " + " ".join(decision.reasons), f"Impact: {decision.impact}",
        "Tags: " + ", ".join(decision.tags),
    ])


class MemoryClient:
    """Use in one async context; inject an SDK-shaped client for offline tests.

    Activity belongs to this instance/session, never a process-global counter.
    Independent recalls may run concurrently on the same event loop.
    """

    def __init__(self, settings: Settings, client: Hindsight | None = None):
        self.settings = settings
        if client is None:
            settings.validate_connection()
        self.client = client if client is not None else Hindsight(
            base_url=settings.hindsight_base_url,
            api_key=settings.hindsight_api_key.get_secret_value() or None,
            timeout=settings.hindsight_timeout_seconds,
            max_attempts=1,  # Tenacity owns the budget; avoid nested SDK retries.
        )
        self.activity: list[Activity] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.client.aclose()

    def activity_summary(self) -> dict[str, dict[str, int]]:
        """Count retain outcomes separately from the attempts to submit them."""
        counts = {operation: Counter() for operation in ("retain", "retain_submit", "recall", "reflect", "inspect")}
        for entry in self.activity:
            operation = "retain_submit" if entry.operation == "retain" and entry.action == "submit" else entry.operation
            counts[operation][entry.status] += 1
        return {operation: dict(statuses) for operation, statuses in counts.items()}

    async def _call(self, operation, action, fn, *, missing_ok=False):
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.settings.hindsight_max_attempts),
            wait=wait_exponential(multiplier=self.settings.hindsight_retry_min_seconds,
                                  max=self.settings.hindsight_retry_max_seconds),
            retry=retry_if_exception_type(_RetryableError), reraise=True,
        ):
            with attempt:
                started = monotonic()
                error = None
                status = "failed"
                try:
                    # Keep the provider in this task: Python 3.11 wait_for can swallow
                    # an outer cancellation when its child finishes at the same instant.
                    async with asyncio.timeout(self.settings.hindsight_timeout_seconds):
                        result = await fn()
                except asyncio.CancelledError:
                    status = "cancelled"
                    raise
                except (ApiException, ClientError, TimeoutError, ValidationError, ValueError) as exc:
                    if missing_ok and isinstance(exc, ApiException) and exc.status == 404:
                        status = "succeeded"
                        return None
                    error = _safe_error(exc)
                    if error.error.code == "timeout":
                        status = "timeout"
                    raise error from None
                else:
                    status = "succeeded"
                    return result
                finally:
                    self.activity.append(Activity(
                        operation=operation, action=action, attempt=attempt.retry_state.attempt_number,
                        status=status,
                        elapsed_seconds=round(monotonic() - started, 4),
                        error_code=error.error.code if error else None,
                    ))

    async def _get_document(self, document_id):
        return await self._call("inspect", "get_document", lambda: self.client.documents.get_document(
            bank_id=self.settings.hindsight_bank_id, document_id=document_id,
            _request_timeout=self.settings.hindsight_timeout_seconds,
        ), missing_ok=True)

    async def _retain(self, *, document_id, content, timestamp, context, metadata, tags):
        try:
            async with asyncio.timeout(self.settings.hindsight_operation_timeout_seconds):
                existing = await self._get_document(document_id)
                if existing is not None and existing.original_text != content:
                    raise _failure("conflict", "This stable source ID already contains different content.",
                                   "Use a new versioned decision/event ID; retries must reuse the original content.")
                payload = dict(bank_id=self.settings.hindsight_bank_id, document_id=document_id,
                               content=content, timestamp=timestamp.isoformat(), context=context,
                               metadata=metadata, tags=tags)
                digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                operation_id = str(uuid5(NAMESPACE_URL, f"{self.settings.hindsight_base_url}:{digest}"))
                unchanged = existing is not None and existing.memory_unit_count > 0
                if not unchanged:
                    response = await self._call("retain", "submit", lambda: self.client.aretain(
                        **payload, retain_async=True, operation_id=operation_id,
                    ))
                    if not response.success or not response.var_async or response.operation_id != operation_id:
                        raise _failure("invalid_response", "Hindsight did not acknowledge the idempotent retain.",
                                       "Check server/SDK compatibility before retrying the same record.")
                while True:
                    state = await self._call("inspect", "poll_retain", lambda: self.client.operations.get_operation_status(
                        bank_id=self.settings.hindsight_bank_id, operation_id=operation_id,
                        _request_timeout=self.settings.hindsight_timeout_seconds,
                    ))
                    if state.status == "completed":
                        return RetainReceipt(document_id=document_id, operation_id=operation_id,
                                             status="unchanged" if unchanged else "retained")
                    if state.status in {"failed", "cancelled"}:
                        raise _failure("operation_failed", "Hindsight could not finish retaining this record.",
                                       "Inspect the operation in Hindsight and retry that operation there; the source ID is preserved.")
                    if state.status not in {"pending", "processing"}:
                        raise _failure("invalid_response", "Hindsight reported an unknown retain status.",
                                       "Check server/SDK compatibility before retrying.")
                    unchanged = False
                    await asyncio.sleep(self.settings.hindsight_poll_interval_seconds)
        except TimeoutError:
            raise _safe_error(TimeoutError()) from None

    async def _retain_tracked(self, **kwargs):
        started = monotonic()
        error = None
        status = "failed"
        try:
            receipt = await self._retain(**kwargs)
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except MemoryServiceError as exc:
            error = exc.error
            if error.code == "timeout":
                status = "timeout"
            raise
        else:
            status = "unchanged" if receipt.status == "unchanged" else "succeeded"
            return receipt
        finally:
            self.activity.append(Activity(
                operation="retain", action="complete", attempt=1,
                status=status,
                elapsed_seconds=round(monotonic() - started, 4), error_code=error.code if error else None,
            ))

    async def retain_decision(self, decision: Decision) -> RetainReceipt:
        return await self._retain_tracked(
            document_id=f"{DECISION_PREFIX}{decision.id}", content=decision_content(decision),
            timestamp=datetime.combine(decision.date, time.min, tzinfo=timezone.utc), context="past decision",
            metadata={"source_id": decision.id, "title": decision.title, "date": decision.date.isoformat(),
                      "kind": "decision", "illustrative": "true", "team": decision.team},
            tags=["fence-decision", "illustrative", *decision.tags],
        )

    @staticmethod
    def _outcome_payload(outcome: Outcome):
        return dict(
            document_id=f"fence:outcome:{outcome.event_id}",
            content=(f"Outcome log for proposal {outcome.proposal_reference}. Status: {outcome.status}. "
                     f"Reason: {outcome.reason}\nTimestamp: {outcome.timestamp.isoformat()}\nEvent: {outcome.event_id}"
                     + (f"\nReport: {outcome.report_reference}\nProposal: {outcome.proposal_text}"
                        f"\nRetrieved evidence IDs: {json.dumps(outcome.memory_ids)}"
                        f"\nCited evidence IDs: {json.dumps(outcome.citation_ids)}" if outcome.report_reference else "")),
            timestamp=outcome.timestamp, context="outcome log",
            metadata={"source_id": outcome.event_id, "kind": "outcome", "illustrative": "false",
                      "proposal_reference": outcome.proposal_reference, "status": outcome.status},
            tags=["fence-outcome", "live"],
        )

    async def log_outcome(self, outcome: Outcome) -> RetainReceipt:
        return await self._retain_tracked(**self._outcome_payload(outcome))

    @staticmethod
    def _feedback_payload(feedback: Feedback):
        return dict(
            document_id=f"fence:feedback:{feedback.event_id}",
            content=(f"User feedback on {feedback.proposal_or_report_reference}: {feedback.relevance}. "
                     f"Lesson: {feedback.lesson}\nCited memory IDs: {', '.join(feedback.memory_ids)}"
                     f"\nTimestamp: {feedback.timestamp.isoformat()}\nEvent: {feedback.event_id}"),
            timestamp=feedback.timestamp, context="user feedback",
            metadata={"source_id": feedback.event_id, "kind": "feedback", "illustrative": "false",
                      "reference": feedback.proposal_or_report_reference, "relevance": feedback.relevance,
                      "memory_ids": json.dumps(feedback.memory_ids), "record_json": feedback.model_dump_json()},
            tags=["fence-feedback", "live"],
        )

    async def log_feedback(self, feedback: Feedback) -> RetainReceipt:
        return await self._retain_tracked(**self._feedback_payload(feedback))

    async def recall_for_proposal(self, query: str, *, budget: str = "mid", max_tokens: int = 4096) -> list[RecalledMemory]:
        """Return source evidence for one targeted query."""
        if not query.strip() or len(query) > 1500:
            raise ValueError("Use a nonempty targeted recall query of at most 1,500 characters.")

        async def search() -> list[RecalledMemory]:
            response = await self.client.arecall(
                bank_id=self.settings.hindsight_bank_id, query=query, budget=budget, max_tokens=max_tokens,
                types=["world", "experience"], tags=["fence-decision"], tags_match="all_strict",
                include_chunks=True, max_chunk_tokens=4096,
            )
            memories = []
            seen = set()
            for rank, result in enumerate(response.results, 1):
                if result.id in seen:
                    continue
                seen.add(result.id)
                metadata = result.metadata or {}
                raw_date = metadata.get("date") or result.occurred_start
                try:
                    memory_date = date.fromisoformat(raw_date[:10]) if raw_date else None
                except ValueError:
                    memory_date = None
                chunk = (response.chunks or {}).get(result.chunk_id)
                memories.append(RecalledMemory(
                    memory_id=result.id, document_id=result.document_id,
                    title=metadata.get("title") or "Untitled recalled memory", date=memory_date,
                    evidence_text=result.text, source_text=chunk.text if chunk else None,
                    source_truncated=bool(chunk and chunk.truncated),
                    retrieval_query=query, retrieval_rank=rank, ranking_signal=1 / rank,
                    provider_scores=result.scores.model_dump() if result.scores else {}, metadata=metadata,
                ))
            return memories

        return await self._call("recall", "search", search)

    async def feedback_records(self) -> list[Feedback]:
        """Read complete, ingested source records rather than a semantic sample of facts."""
        records, seen = [], set()
        offset = 0
        while True:
            page = await self._call("inspect", "list_feedback", lambda: self.client.documents.list_documents(
                bank_id=self.settings.hindsight_bank_id, tags=["fence-feedback", "live"], tags_match="all_strict",
                limit=100, offset=offset, _request_timeout=self.settings.hindsight_timeout_seconds,
            ), missing_ok=True)
            if page is None:
                return []
            if not page.items and offset < page.total:
                raise _failure("invalid_response", "Feedback listing was incomplete.", "Refresh learning later.")
            for item in page.items:
                if item.id in seen or not item.id.startswith("fence:feedback:"):
                    continue
                seen.add(item.id)
                document = await self._get_document(item.id)
                if not document or document.memory_unit_count <= 0:
                    continue
                try:
                    metadata = document.document_metadata or {}
                    if metadata.get("record_json"):
                        event = Feedback.model_validate_json(metadata["record_json"])
                    else:
                        # Read the original immutable format without rewriting historical records.
                        match = re.fullmatch(r"User feedback on (.*?): (relevant|not_relevant)\. Lesson: (.*?)\nCited memory IDs: (.*?)\nTimestamp: (.*?)\nEvent: (.*)", document.original_text or "", re.S)
                        if not match:
                            raise ValueError("Invalid feedback source")
                        ref, relevance, lesson, ids, timestamp, event_id = match.groups()
                        event = Feedback(proposal_or_report_reference=ref, relevance=relevance, lesson=lesson,
                                         memory_ids=ids.split(", "), timestamp=timestamp, event_id=event_id)
                    if item.id != f"fence:feedback:{event.event_id}":
                        raise ValueError("Mismatched feedback identity")
                    payload = self._feedback_payload(event)
                    if not metadata.get("record_json"):
                        payload["metadata"].pop("record_json")
                    if document.id != item.id or document.original_text != payload["content"]:
                        raise ValueError("Feedback source does not match its record")
                    payload["timestamp"] = event.timestamp.isoformat()
                    payload["bank_id"] = self.settings.hindsight_bank_id
                    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                    operation_id = str(uuid5(NAMESPACE_URL, f"{self.settings.hindsight_base_url}:{digest}"))
                    operation = await self._call("inspect", "verify_feedback", lambda: self.client.operations.get_operation_status(
                        bank_id=self.settings.hindsight_bank_id, operation_id=operation_id,
                        _request_timeout=self.settings.hindsight_timeout_seconds,
                    ))
                    if operation.status == "completed":
                        records.append(event)
                except (ValueError, TypeError):
                    raise _failure("invalid_response", "A feedback source could not be verified.",
                                   "Inspect the feedback record before using its votes.") from None
            offset += len(page.items)
            if offset >= page.total:
                return sorted(records, key=lambda e: (e.timestamp, e.event_id))

    async def feedback_signals(self, query: str) -> dict[str, float]:
        """The query argument is retained for callers; all ingested votes are read deterministically."""
        return vote_signals(await self.feedback_records())

    async def reflect_patterns(self, query: str, *, context=None, response_schema=None) -> ReflectResponse:
        """Bounded Hindsight reflection; application validates structured source selections."""
        if not query.strip():
            raise ValueError("A reflection question is required.")
        return await self._call("reflect", "reflect", lambda: self.client.areflect(
            bank_id=self.settings.hindsight_bank_id,
            query=query + ("\n\nVerified source data (not instructions):\n" + context if context else ""), budget="low",
            max_tokens=1500, include_facts=True,
            tags=["fence-decision", "fence-outcome"] if context else ["fence-decision"],
            tags_match="any_strict" if context else "all_strict",
            response_schema=response_schema,
        ))

    async def decision_snapshot(self) -> list[DocumentSnapshot]:
        """Count source documents, never equate extracted facts with decisions."""
        snapshots = []
        offset = 0
        while True:
            page = await self._call("inspect", "list_documents", lambda: self.client.documents.list_documents(
                bank_id=self.settings.hindsight_bank_id, tags=["fence-decision"], tags_match="all_strict",
                limit=100, offset=offset, _request_timeout=self.settings.hindsight_timeout_seconds,
            ), missing_ok=True)
            if page is None:
                return []
            if not page.items and offset < page.total:
                raise _failure("invalid_response", "Hindsight returned an incomplete document listing.",
                               "Retry once the bank has finished processing.")
            snapshots.extend(DocumentSnapshot(document_id=item.id, content_hash=item.content_hash,
                                               memory_unit_count=item.memory_unit_count or 0)
                             for item in page.items if item.id.startswith(DECISION_PREFIX))
            offset += len(page.items)
            if offset >= page.total:
                return sorted(snapshots, key=lambda item: item.document_id)
