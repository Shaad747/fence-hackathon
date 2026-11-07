import asyncio
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from core.memory import MemoryClient, MemoryServiceError
from core.outcomes import OutcomeQueue, report_reference
from core.schemas import RetainReceipt
from test_memory import FakeSDK, settings, lotus
from test_review_ui import lotus_run


def test_persistent_reload_deduplication_and_association(tmp_path):
    path = tmp_path / 'queue.sqlite3'
    result = lotus_run().result
    queue = OutcomeQueue(path, 'bank')
    first = queue.prepare(result, 'modified', '  Pilot first.  ')
    again = OutcomeQueue(path, 'bank').prepare(result, 'modified', 'Pilot first.')
    assert again == first
    assert first.report_reference == report_reference(result)
    assert first.proposal_text == result.proposal.original_input
    assert first.memory_ids == first.citation_ids == ['lotus-fact']
    assert not queue.confirmed(first)
    queue.confirm(first, RetainReceipt(document_id='fence:outcome:' + first.event_id, status='retained'))
    assert OutcomeQueue(path, 'bank').confirmed(first)
    changed = queue.prepare(result, 'accepted', 'Approved after pilot.')
    assert changed.event_id != first.event_id
    assert len(queue.records()) == 2
    assert next(item for item, saved in queue.records() if saved) == first
    assert OutcomeQueue(path, 'other-bank').records() == []


@pytest.mark.parametrize('status,notes', [('unknown', 'reason'), ('accepted', '  '), ('modified', 'x'*2001)])
def test_invalid_submission_never_creates_record(tmp_path, status, notes):
    queue = OutcomeQueue(tmp_path / 'q', 'bank')
    with pytest.raises(ValidationError):
        queue.prepare(lotus_run().result, status, notes)
    assert queue.records() == []


def test_fabricated_evidence_and_mismatched_receipt_cannot_be_confirmed(tmp_path):
    queue = OutcomeQueue(tmp_path / 'q', 'bank')
    result = lotus_run().result
    result.citation_ids = ['invented']
    with pytest.raises(ValueError):
        queue.prepare(result, 'pending', 'Waiting for review.')
    event = queue.prepare(lotus_run().result, 'pending', 'Waiting for review.')
    with pytest.raises(ValueError):
        queue.confirm(event, RetainReceipt(document_id='wrong', status='retained'))
    assert not queue.confirmed(event)


def test_lost_local_confirmation_retries_same_remote_record_without_overwriting_history(tmp_path):
    result = lotus_run().result
    async def run():
        sdk = FakeSDK()
        memory = MemoryClient(settings(), sdk)
        await memory.retain_decision(lotus())
        original = dict(sdk.stored)
        path = tmp_path / 'q'
        queue = OutcomeQueue(path, 'bank')
        event = queue.prepare(result, 'accepted', 'Limited pilot approved.')
        assert (await memory.log_outcome(event)).status == 'retained'
        # Simulate process death after remote success but before local confirmation.
        restarted = OutcomeQueue(path, 'bank')
        retried = restarted.prepare(result, 'accepted', 'Limited pilot approved.')
        receipt = await MemoryClient(settings(), sdk).log_outcome(retried)
        assert receipt.status == 'unchanged'
        restarted.confirm(retried, receipt)
        assert len(sdk.submissions) == 2  # one decision and one outcome
        assert all(sdk.stored[key] == value for key, value in original.items())
        assert retried == event and restarted.confirmed(event)
        content = sdk.submissions[-1]['content']
        assert event.report_reference in content and 'lotus-fact' in content
        assert len(await memory.decision_snapshot()) == 1
    asyncio.run(run())


@pytest.mark.parametrize('cancelled', [False, True])
def test_failed_or_cancelled_writes_remain_unconfirmed(tmp_path, cancelled):
    result = lotus_run().result
    async def run():
        queue = OutcomeQueue(tmp_path / 'q', 'bank')
        event = queue.prepare(result, 'rejected', 'Do not migrate yet.')
        sdk = FakeSDK()
        if cancelled:
            sdk.get_document = None
            async def stop(**kwargs):
                raise asyncio.CancelledError()
            sdk.documents.get_document = stop
        else:
            sdk.poll_status = 'failed'
        memory = MemoryClient(settings(), sdk)
        with pytest.raises(asyncio.CancelledError if cancelled else MemoryServiceError):
            await memory.log_outcome(event)
        assert not OutcomeQueue(tmp_path / 'q', 'bank').confirmed(event)
        assert memory.activity_summary()['retain'].get('succeeded', 0) == 0
    asyncio.run(run())


@pytest.mark.parametrize('status', ['accepted', 'rejected', 'modified', 'pending', 'approved', 'shipped', 'failed'])
def test_supported_outcome_states(tmp_path, status):
    queue = OutcomeQueue(tmp_path / 'q', 'bank')
    event = queue.prepare(lotus_run().result, status, 'Decision notes.')
    assert event.status == status and queue.records() == [(event, False)]


def test_concurrent_identical_submissions_share_timestamp_and_id(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    queue = OutcomeQueue(tmp_path / 'q', 'bank')
    result = lotus_run().result
    with ThreadPoolExecutor(max_workers=2) as worker:
        events = list(worker.map(lambda _: queue.prepare(result, 'accepted', 'Pilot first.'), range(2)))
    assert events[0] == events[1]
    assert len(queue.records()) == 1
