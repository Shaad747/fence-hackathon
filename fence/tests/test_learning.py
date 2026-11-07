import asyncio
from datetime import datetime, timezone

import pytest

from core.learning import FeedbackQueue, learning_points, vote_signals
from core.memory import MemoryClient, MemoryServiceError
from core.pipeline import rank_evidence
from core.schemas import Feedback, RetainReceipt
from test_memory import FakeSDK, settings
from test_pipeline import LOTUS, recalled
from test_review_ui import lotus_run


def test_confirmed_vote_changes_rank_across_restart_without_changing_evidence(tmp_path):
    result = lotus_run().result
    first = recalled(LOTUS, 'lotus-fact', rank=1)
    second = recalled(LOTUS.model_copy(update={'id':'other','title':'Other pricing'}), 'other', rank=1)
    original = first.model_dump()
    async def run():
        sdk = FakeSDK()
        queue = FeedbackQueue(tmp_path/'q', 'bank')
        event = queue.prepare(result, 'lotus-fact', 'not_relevant')
        assert vote_signals([e for e, saved in queue.records() if saved]) == {}
        before = rank_evidence(result.proposal, [[first, second]], {})
        assert before[0].memory.memory_id == 'lotus-fact'
        writer = MemoryClient(settings(), sdk)
        queue.confirm(event, await writer.log_feedback(event))
        reader = MemoryClient(settings(), sdk)
        signal = await reader.feedback_signals('anything')
        after = rank_evidence(result.proposal, [[first, second]], signal)
        assert after[0].memory.memory_id == 'other'
        assert next(e for e in after if e.memory.memory_id == 'lotus-fact').feedback_adjustment == -0.1
        assert first.model_dump() == original
        assert result.citation_ids == ['lotus-fact']
        assert await MemoryClient(settings(), sdk).feedback_signals('different') == signal
        duplicate = FeedbackQueue(tmp_path/'q', 'bank').prepare(result, 'lotus-fact', 'not_relevant')
        assert duplicate == event
        assert (await writer.log_feedback(duplicate)).status == 'unchanged'
        assert await reader.feedback_signals('anything') == signal
    asyncio.run(run())


def test_conflicting_duplicate_and_corrupt_events_are_order_independent(tmp_path):
    result = lotus_run().result
    queue = FeedbackQueue(tmp_path/'q','bank')
    positive = queue.prepare(result, 'lotus-fact', 'relevant')
    negative = queue.prepare(result, 'lotus-fact', 'not_relevant')
    assert vote_signals([positive, negative, positive]) == {'lotus-fact': 0}
    assert vote_signals([negative, positive]) == {'lotus-fact': 0}
    corrupt = positive.model_copy(update={'relevance':'not_relevant'})
    assert vote_signals([positive, corrupt]) == {}
    assert learning_points([positive, negative, positive])[-1]['relevant_share'] == 50
    assert learning_points([]) == []


@pytest.mark.parametrize('state', ['pending','processing','failed','cancelled'])
def test_unfinished_remote_operations_cannot_influence_learning(tmp_path, state):
    result = lotus_run().result
    event = FeedbackQueue(tmp_path/'q','bank').prepare(result, 'lotus-fact', 'relevant')
    async def run():
        sdk = FakeSDK()
        memory = MemoryClient(settings(), sdk)
        await memory.log_feedback(event)
        sdk.poll_status = state  # Even if partially extracted documents exist, status must be completed.
        assert await memory.feedback_records() == []
        assert await memory.feedback_signals('pricing') == {}
    asyncio.run(run())


def test_invalid_vote_is_not_queued_and_changed_report_does_not_duplicate(tmp_path):
    queue = FeedbackQueue(tmp_path/'q','bank')
    result = lotus_run().result
    with pytest.raises(ValueError):
        queue.prepare(result, 'fabricated', 'relevant')
    first = queue.prepare(result, 'lotus-fact', 'relevant')
    result.report.summary = 'Different wording for the same proposal.'
    assert queue.prepare(result, 'lotus-fact', 'relevant') == first
    assert len(queue.records()) == 1


def test_unavailable_feedback_fails_explicitly():
    from hindsight_client_api.exceptions import ApiException
    from unittest.mock import AsyncMock
    async def run():
        sdk = FakeSDK()
        sdk.documents.list_documents = AsyncMock(side_effect=ApiException(status=401))
        with pytest.raises(MemoryServiceError):
            await MemoryClient(settings(), sdk).feedback_records()
    asyncio.run(run())


def test_tampered_feedback_source_is_not_trusted(tmp_path):
    event = FeedbackQueue(tmp_path/'q','bank').prepare(lotus_run().result, 'lotus-fact', 'relevant')
    async def run():
        sdk = FakeSDK()
        memory = MemoryClient(settings(), sdk)
        receipt = await memory.log_feedback(event)
        sdk.stored[(settings().hindsight_bank_id, receipt.document_id)].original_text = 'Altered source'
        with pytest.raises(MemoryServiceError) as caught:
            await memory.feedback_records()
        assert caught.value.error.code == 'invalid_response'
    asyncio.run(run())


def test_legacy_feedback_remains_readable_without_rewriting_source():
    async def run():
        sdk = FakeSDK()
        memory = MemoryClient(settings(), sdk)
        event = Feedback(proposal_or_report_reference='old-report', lesson='Original lesson.', memory_ids=['old-fact'],
                         relevance='relevant', timestamp=datetime(2026,11,5,tzinfo=timezone.utc), event_id='old-vote')
        payload = memory._feedback_payload(event)
        payload['metadata'].pop('record_json')
        await memory._retain_tracked(**payload)
        original = dict(sdk.stored)
        assert await memory.feedback_records() == [event]
        assert sdk.stored == original
    asyncio.run(run())
