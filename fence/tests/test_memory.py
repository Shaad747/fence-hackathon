"""Offline provider-contract tests; these do not verify a live Hindsight service."""

import asyncio
import hashlib
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientConnectionError
from hindsight_client import Hindsight
from hindsight_client_api.api.documents_api import DocumentsApi
from hindsight_client_api.api.operations_api import OperationsApi
from hindsight_client_api.exceptions import ApiException
from hindsight_client_api.models import (
    ChunkData, DocumentListItem, DocumentResponse, ListDocumentsResponse,
    OperationStatusResponse, RecallResponse, RecallResult, RecallScores,
    ReflectResponse, RetainResponse,
)

from core.config import Settings
from core.memory import DECISION_PREFIX, MemoryClient, MemoryServiceError, decision_content
from core.schemas import Decision, Feedback, Outcome


def settings(**overrides):
    return Settings(**{
        "hindsight_base_url": "http://localhost:8888",
        "hindsight_timeout_seconds": 0.05,
        "hindsight_operation_timeout_seconds": 0.2,
        "hindsight_retry_min_seconds": 0,
        "hindsight_retry_max_seconds": 0,
        "hindsight_poll_interval_seconds": 0.001,
        **overrides,
    })


def archive():
    path = Path(__file__).resolve().parents[1] / "seed" / "seed_data.json"
    return [Decision.model_validate(item) for item in json.loads(path.read_text())]


def lotus():
    return next(item for item in archive() if item.title == "Project Lotus")


class FakeSDK:
    """A persistent fake server with the installed SDK's signatures and response models."""

    def __init__(self):
        self.stored = {}
        self.jobs = {}
        self.submissions = []
        self.poll_status = "completed"
        self.lose_first_ack = False
        self.documents = SimpleNamespace(get_document=self.get_document, list_documents=self.list_documents)
        self.operations = SimpleNamespace(get_operation_status=self.get_operation_status)
        self.aclose = AsyncMock()
        self.arecall = AsyncMock(return_value=RecallResponse(results=[]))
        self.areflect = AsyncMock(return_value=ReflectResponse(text="No supported pattern yet."))

    async def get_document(self, **kwargs):
        inspect.signature(DocumentsApi.get_document).bind(None, **kwargs)
        key = (kwargs["bank_id"], kwargs["document_id"])
        if key not in self.stored:
            raise ApiException(status=404)
        return self.stored[key]

    async def list_documents(self, **kwargs):
        inspect.signature(DocumentsApi.list_documents).bind(None, **kwargs)
        items = [DocumentListItem(
            id=doc.id, content_hash=doc.content_hash, memory_unit_count=doc.memory_unit_count,
        ) for (bank, _), doc in self.stored.items()
            if bank == kwargs["bank_id"] and set(kwargs["tags"]) <= set(doc.tags or [])]
        offset, limit = kwargs["offset"], kwargs["limit"]
        return ListDocumentsResponse(items=items[offset:offset + limit], total=len(items), limit=limit, offset=offset)

    async def aretain(self, **kwargs):
        inspect.signature(Hindsight.aretain).bind(None, **kwargs)
        assert kwargs["retain_async"] is True
        self.submissions.append(kwargs)
        self.jobs.setdefault(kwargs["operation_id"], kwargs)
        if self.lose_first_ack and len(self.submissions) == 1:
            raise ClientConnectionError("simulated lost acknowledgement")
        return RetainResponse.model_validate({
            "success": True, "bank_id": kwargs["bank_id"], "items_count": 1,
            "async": True, "operation_id": kwargs["operation_id"],
        })

    async def get_operation_status(self, **kwargs):
        inspect.signature(OperationsApi.get_operation_status).bind(None, **kwargs)
        payload = self.jobs[kwargs["operation_id"]]
        if self.poll_status == "completed":
            self.stored[(payload["bank_id"], payload["document_id"])] = DocumentResponse(
                id=payload["document_id"], bank_id=payload["bank_id"], original_text=payload["content"],
                content_hash=hashlib.sha256(payload["content"].encode()).hexdigest(),
                created_at="2026-11-05T00:00:00Z", updated_at="2026-11-05T00:00:00Z",
                memory_unit_count=4, tags=payload["tags"], document_metadata=payload["metadata"],
            )
        return OperationStatusResponse(operation_id=kwargs["operation_id"], status=self.poll_status)


def test_all_seed_records_twice_are_unchanged_across_new_sessions():
    async def run():
        sdk = FakeSDK()
        first = MemoryClient(settings(), sdk)
        receipts = [await first.retain_decision(item) for item in archive()]
        before = await first.decision_snapshot()
        second = MemoryClient(settings(), sdk)
        repeated = [await second.retain_decision(item) for item in archive()]
        after = await second.decision_snapshot()
        assert len(sdk.submissions) == 14
        assert len(before) == len(after) == 14
        assert before == after
        assert sum(item.memory_unit_count for item in after) == 56
        assert all(item.status == "retained" for item in receipts)
        assert all(item.status == "unchanged" for item in repeated)
        assert first.activity is not second.activity
        first_summary = first.activity_summary()
        assert first_summary["retain_submit"] == {"succeeded": 14}
        assert first_summary["retain"] == {"succeeded": 14}
        second_summary = second.activity_summary()
        assert second_summary["retain_submit"] == {}
        assert second_summary["retain"] == {"unchanged": 14}
    asyncio.run(run())


def test_lost_ack_retries_the_same_operation_and_source_identity():
    async def run():
        sdk = FakeSDK()
        sdk.lose_first_ack = True
        memory = MemoryClient(settings(), sdk)
        receipt = await memory.retain_decision(lotus())
        assert receipt.status == "retained"
        assert len(sdk.jobs) == len(sdk.stored) == 1
        assert len(sdk.submissions) == 2
        assert sdk.submissions[0] == sdk.submissions[1]
        payload = sdk.submissions[0]
        assert payload["document_id"] == DECISION_PREFIX + lotus().id
        assert payload["timestamp"] == "2023-08-07T00:00:00+00:00"
        assert payload["context"] == "past decision"
        assert payload["metadata"]["illustrative"] == "true"
        assert "31% in six weeks" in payload["content"]
        attempts = [item for item in memory.activity if item.action == "submit"]
        assert [item.status for item in attempts] == ["failed", "succeeded"]
        summary = memory.activity_summary()
        assert summary["retain_submit"] == {"failed": 1, "succeeded": 1}
        assert summary["retain"] == {"succeeded": 1}
    asyncio.run(run())


def test_decision_content_preserves_all_authoritative_details():
    decision = lotus()
    content = decision_content(decision)
    for text in [decision.title, decision.proposal, decision.owner, decision.team,
                 decision.impact, decision.outcome, *decision.reasons]:
        assert text in content


@pytest.mark.parametrize("status", [429, 503])
def test_recall_retries_transient_failures_within_budget(status):
    async def run():
        sdk = FakeSDK()
        sdk.arecall.side_effect = [ApiException(status=status), RecallResponse(results=[])]
        memory = MemoryClient(settings(), sdk)
        assert await memory.recall_for_proposal("free merchant tier") == []
        assert sdk.arecall.await_count == 2
        assert [item.status for item in memory.activity] == ["failed", "succeeded"]
    asyncio.run(run())


@pytest.mark.parametrize("status,code", [(401, "authentication"), (403, "authentication"), (422, "configuration")])
def test_terminal_errors_do_not_retry_or_leak_provider_details(status, code):
    async def run():
        sdk = FakeSDK()
        sdk.arecall.side_effect = ApiException(status=status, reason="credential-must-not-leak")
        memory = MemoryClient(settings(), sdk)
        with pytest.raises(MemoryServiceError) as caught:
            await memory.recall_for_proposal("pricing")
        assert caught.value.error.code == code
        assert not caught.value.error.retryable
        assert sdk.arecall.await_count == 1
        assert "credential-must-not-leak" not in str(caught.value)
        assert "credential-must-not-leak" not in repr(memory.activity)
        assert caught.value.error.next_step
    asyncio.run(run())


def test_retry_exhaustion_returns_typed_unavailable():
    async def run():
        sdk = FakeSDK()
        sdk.arecall.side_effect = ApiException(status=503)
        memory = MemoryClient(settings(), sdk)
        with pytest.raises(MemoryServiceError) as caught:
            await memory.recall_for_proposal("pricing")
        assert caught.value.error.code == "unavailable"
        assert sdk.arecall.await_count == 3
    asyncio.run(run())


def test_timeout_is_not_an_empty_archive():
    async def slow(**kwargs):
        await asyncio.sleep(1)
        return RecallResponse(results=[])

    async def run():
        sdk = FakeSDK()
        sdk.arecall.side_effect = slow
        memory = MemoryClient(settings(hindsight_timeout_seconds=0.005), sdk)
        with pytest.raises(MemoryServiceError) as caught:
            await memory.recall_for_proposal("pricing")
        assert caught.value.error.code == "timeout"
        assert sdk.arecall.await_count == 3
        assert all(item.status == "timeout" for item in memory.activity)
    asyncio.run(run())


@pytest.mark.parametrize("operation", ["recall", "retain"])
def test_cancelling_an_inflight_call_records_cancellation_and_propagates(operation):
    async def run():
        started = asyncio.Event()

        async def blocked(**kwargs):
            started.set()
            await asyncio.Future()

        sdk = FakeSDK()
        memory = MemoryClient(settings(hindsight_timeout_seconds=2,
                                       hindsight_operation_timeout_seconds=3), sdk)
        if operation == "recall":
            sdk.arecall.side_effect = blocked
            call = memory.recall_for_proposal("pricing")
        else:
            sdk.aretain = AsyncMock(side_effect=blocked)
            call = memory.retain_decision(lotus())

        task = asyncio.create_task(call)
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        summary = memory.activity_summary()
        assert summary[operation] == {"cancelled": 1}
        if operation == "retain":
            assert sdk.aretain.await_count == 1
            assert summary["retain_submit"] == {"cancelled": 1}
        else:
            assert sdk.arecall.await_count == 1

    asyncio.run(run())


def test_recall_preserves_evidence_identity_source_and_relative_ranking():
    async def run():
        sdk = FakeSDK()
        fact = RecallResult(id="fact-lotus", text="Project Lotus churn reached 31% in six weeks.",
                            document_id=DECISION_PREFIX + lotus().id, chunk_id="chunk-lotus",
                            metadata={"title": "Project Lotus", "date": "2023-08-07"},
                            scores=RecallScores(final=0.91, reranker=0.87))
        sdk.arecall.return_value = RecallResponse(
            results=[fact, fact, RecallResult(id="fact-other", text="Support lacked migration capacity.")],
            chunks={"chunk-lotus": ChunkData(id="chunk-lotus", text=decision_content(lotus()), chunk_index=0)},
        )
        memory = MemoryClient(settings(), sdk)
        recalled = await memory.recall_for_proposal("free tier removal")
        assert [item.memory_id for item in recalled] == ["fact-lotus", "fact-other"]
        assert recalled[0].date.isoformat() == "2023-08-07"
        assert recalled[0].document_id == DECISION_PREFIX + lotus().id
        assert recalled[0].source_text == decision_content(lotus())
        assert recalled[0].provider_scores["final"] == 0.91
        assert recalled[0].ranking_label == "Relative ranking signal"
        assert recalled[0].ranking_signal > recalled[1].ranking_signal
        kwargs = sdk.arecall.call_args.kwargs
        inspect.signature(Hindsight.arecall).bind(None, **kwargs)
        assert kwargs["tags"] == ["fence-decision"]
        assert kwargs["tags_match"] == "all_strict"
    asyncio.run(run())


def test_optional_null_chunk_flag_is_accepted():
    async def run():
        sdk = FakeSDK()
        sdk.arecall.return_value = RecallResponse(
            results=[RecallResult(id="fact-1", text="A supported fact.", chunk_id="chunk-1")],
            chunks={"chunk-1": ChunkData(id="chunk-1", text="Source text.", chunk_index=0, truncated=None)},
        )
        recalled = await MemoryClient(settings(), sdk).recall_for_proposal("pricing")
        assert recalled[0].source_truncated is False
    asyncio.run(run())


def test_invalid_evidence_becomes_a_typed_error():
    async def run():
        sdk = FakeSDK()
        sdk.arecall.return_value = RecallResponse(results=[RecallResult(id="fact-1", text=" ")])
        memory = MemoryClient(settings(), sdk)
        with pytest.raises(MemoryServiceError) as caught:
            await memory.recall_for_proposal("pricing")
        assert caught.value.error.code == "invalid_response"
        assert sdk.arecall.await_count == 1
        assert memory.activity_summary()["recall"] == {"failed": 1}
    asyncio.run(run())


def test_outcomes_and_feedback_use_separate_stable_live_sources():
    async def run():
        sdk = FakeSDK()
        memory = MemoryClient(settings(), sdk)
        now = datetime(2026, 11, 5, tzinfo=timezone.utc)
        outcome = Outcome(proposal_reference="proposal-1", status="approved", reason="Pilot first.",
                          timestamp=now, event_id="event-1")
        feedback = Feedback(proposal_or_report_reference="report-1", lesson="Check migration capacity.",
                            memory_ids=["fact-lotus"], relevance="relevant", timestamp=now, event_id="vote-1")
        assert (await memory.log_outcome(outcome)).status == "retained"
        assert (await memory.log_feedback(feedback)).status == "retained"
        other_session = MemoryClient(settings(), sdk)
        assert (await other_session.log_outcome(outcome)).status == "unchanged"
        assert (await other_session.log_feedback(feedback)).status == "unchanged"
        assert len(sdk.submissions) == 2
        assert [item["context"] for item in sdk.submissions] == ["outcome log", "user feedback"]
        assert all(item["metadata"]["illustrative"] == "false" for item in sdk.submissions)
        assert json.loads(sdk.submissions[1]["metadata"]["memory_ids"]) == ["fact-lotus"]
        assert await memory.decision_snapshot() == []
    asyncio.run(run())


def test_changed_content_cannot_reuse_an_immutable_event_id():
    async def run():
        sdk = FakeSDK()
        memory = MemoryClient(settings(), sdk)
        await memory.retain_decision(lotus())
        with pytest.raises(MemoryServiceError) as caught:
            await memory.retain_decision(lotus().model_copy(update={"impact": "Changed impact."}))
        assert caught.value.error.code == "conflict"
        assert len(sdk.submissions) == 1
    asyncio.run(run())


def test_feedback_is_read_across_sessions_and_counted_once_per_event():
    async def run():
        sdk = FakeSDK()
        writer = MemoryClient(settings(), sdk)
        for event, relevance, ids in (
            ("vote-1", "relevant", ["lotus", "lotus", "another"]),
            ("vote-2", "not_relevant", ["lotus"]),
        ):
            await writer.log_feedback(Feedback(
                proposal_or_report_reference="report-1", lesson="Check migration capacity.", memory_ids=ids,
                relevance=relevance, event_id=event, timestamp=datetime(2026, 11, 5, tzinfo=timezone.utc),
            ))
        reader = MemoryClient(settings(), sdk)
        assert await reader.feedback_signals("Pricing migration") == {"lotus": 0.0, "another": 1.0}
        assert await MemoryClient(settings(), sdk).feedback_signals("Another query") == {"lotus": 0.0, "another": 1.0}
        assert len(await reader.feedback_records()) == 2
        # Multiple extracted facts never multiply votes: the reader uses source documents.
        sdk.arecall.assert_not_awaited()

    asyncio.run(run())


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_enqueue_acknowledgement_is_not_successful_ingestion(status):
    async def run():
        sdk = FakeSDK()
        sdk.poll_status = status
        memory = MemoryClient(settings(), sdk)
        with pytest.raises(MemoryServiceError) as caught:
            await memory.retain_decision(lotus())
        assert caught.value.error.code == "operation_failed"
        assert not sdk.stored
        assert memory.activity[-1].action == "complete"
        assert memory.activity[-1].status == "failed"
        summary = memory.activity_summary()
        assert summary["retain_submit"] == {"succeeded": 1}
        assert summary["retain"] == {"failed": 1}
    asyncio.run(run())


def test_pending_ingestion_has_a_bounded_wait_and_stable_retry():
    async def run():
        sdk = FakeSDK()
        sdk.poll_status = "pending"
        memory = MemoryClient(settings(hindsight_operation_timeout_seconds=0.015), sdk)
        with pytest.raises(MemoryServiceError) as caught:
            await memory.retain_decision(lotus())
        assert caught.value.error.code == "timeout"
        sdk.poll_status = "completed"
        receipt = await MemoryClient(settings(), sdk).retain_decision(lotus())
        assert receipt.status == "retained"
        assert len(sdk.jobs) == 1
        assert sdk.submissions[0]["operation_id"] == sdk.submissions[1]["operation_id"]
    asyncio.run(run())


def test_retain_deadline_cancels_inspection_without_counting_a_success():
    async def blocked(**kwargs):
        await asyncio.Future()

    async def run():
        sdk = FakeSDK()
        sdk.documents.get_document = AsyncMock(side_effect=blocked)
        memory = MemoryClient(settings(hindsight_timeout_seconds=1,
                                       hindsight_operation_timeout_seconds=0.02), sdk)
        with pytest.raises(MemoryServiceError) as caught:
            await memory.retain_decision(lotus())

        assert caught.value.error.code == "timeout"
        assert sdk.documents.get_document.await_count == 1
        assert sdk.submissions == []
        summary = memory.activity_summary()
        assert summary["inspect"] == {"cancelled": 1}
        assert summary["retain_submit"] == {}
        assert summary["retain"] == {"timeout": 1}

    asyncio.run(run())


def test_reflect_uses_official_sdk_and_tracks_activity_and_close():
    async def run():
        sdk = FakeSDK()
        async with MemoryClient(settings(), sdk) as memory:
            result = await memory.reflect_patterns("What does our history say?")
            assert isinstance(result, ReflectResponse)
            kwargs = sdk.areflect.call_args.kwargs
            inspect.signature(Hindsight.areflect).bind(None, **kwargs)
            assert kwargs["include_facts"] is True
            assert memory.activity_summary()["reflect"] == {"succeeded": 1}
        sdk.aclose.assert_awaited_once()
    asyncio.run(run())


@pytest.mark.parametrize("terminal_status", ["failed", "cancelled", "pending", "processing"])
def test_retry_cannot_confirm_a_partially_ingested_failed_retain(terminal_status):
    async def run():
        sdk = FakeSDK()
        memory = MemoryClient(settings(), sdk)
        event = Outcome(proposal_reference='proposal-1', status='approved', reason='Pilot first.',
                        timestamp=datetime(2026,11,5,tzinfo=timezone.utc), event_id='partial-outcome')
        await memory.log_outcome(event)
        # The document exists with extracted facts, but the provider's terminal status is failed.
        sdk.poll_status = terminal_status
        retry = MemoryClient(settings(hindsight_operation_timeout_seconds=0.02), sdk)
        with pytest.raises(MemoryServiceError):
            await retry.log_outcome(event)
        assert retry.activity_summary()['retain'].get('unchanged',0) == 0
        assert retry.activity_summary()['retain'].get('succeeded',0) == 0
    asyncio.run(run())


def test_provider_completion_cannot_swallow_outer_cancellation():
    async def run():
        memory = MemoryClient(settings(), FakeSDK())
        parent = None

        async def completes_as_parent_is_cancelled():
            parent.cancel()
            return 'completed'

        async def call():
            result = await memory._call('inspect', 'race', completes_as_parent_is_cancelled)
            await asyncio.sleep(0)  # Deliver cancellation if the provider completed synchronously.
            return result

        parent = asyncio.create_task(call())
        with pytest.raises(asyncio.CancelledError):
            await parent
    asyncio.run(run())
