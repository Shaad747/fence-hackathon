"""Verify cached async clients, loop affinity, and per-run activity isolation."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, Mock

from core.config import Settings
from core.review_service import ReviewService
from core.schemas import Activity
from test_review_ui import lotus_run


def test_clients_use_one_loop_and_isolate_activity_between_checks(monkeypatch):
    memory = Mock(activity=[], client=Mock(aclose=AsyncMock()), decision_snapshot=AsyncMock(return_value=[]))
    llm = Mock(aclose=AsyncMock())
    memory_factory, llm_factory = Mock(return_value=memory), Mock(return_value=llm)
    monkeypatch.setattr('core.review_service.MemoryClient', memory_factory)
    monkeypatch.setattr('core.review_service.LLMClient', llm_factory)
    loops = []
    expected = lotus_run().result

    async def check(text, mem, model):
        loops.append(asyncio.get_running_loop())
        assert mem is memory and model is llm
        assert mem.activity == []
        mem.activity.append(Activity(operation='recall', action=text, attempt=1, status='succeeded', elapsed_seconds=0))
        return expected

    monkeypatch.setattr('core.review_service.check_proposal', check)
    service = ReviewService(Settings())
    try:
        with ThreadPoolExecutor(max_workers=2) as callers:
            first, second = list(callers.map(service.review, ['first', 'second']))
        assert loops[0] is loops[1]
        assert [item.action for item in first.activity] == ['first']
        assert [item.action for item in second.activity] == ['second']
        memory_factory.assert_called_once()
        llm_factory.assert_called_once()
    finally:
        service.close()
    memory.client.aclose.assert_awaited_once()
    llm.aclose.assert_awaited_once()


def test_snapshot_failure_preserves_pipeline_result(monkeypatch):
    from test_pipeline import memory_timeout
    memory = Mock(activity=[], client=Mock(aclose=AsyncMock()), decision_snapshot=AsyncMock(side_effect=memory_timeout()))
    llm = Mock(aclose=AsyncMock())
    expected = lotus_run().result
    monkeypatch.setattr('core.review_service.MemoryClient', lambda settings: memory)
    monkeypatch.setattr('core.review_service.LLMClient', lambda settings: llm)
    monkeypatch.setattr('core.review_service.check_proposal', AsyncMock(return_value=expected))
    service = ReviewService(Settings())
    try:
        run = service.review('proposal')
        assert run.result is expected
        assert run.documents is None and 'count is unavailable' in run.snapshot_error
    finally:
        service.close()


def test_outcome_write_reuses_memory_without_initializing_groq(monkeypatch):
    from datetime import datetime, timezone
    from core.schemas import Outcome, RetainReceipt
    event = Outcome(proposal_reference='proposal-1', status='accepted', reason='Pilot first.',
                    timestamp=datetime.now(timezone.utc), event_id='event-1')
    receipt = RetainReceipt(document_id='fence:outcome:event-1', status='retained')
    memory = Mock(log_outcome=AsyncMock(return_value=receipt), client=Mock(aclose=AsyncMock()))
    monkeypatch.setattr('core.review_service.MemoryClient', lambda settings: memory)
    model = Mock(side_effect=AssertionError('Outcome saving must not call Groq'))
    monkeypatch.setattr('core.review_service.LLMClient', model)
    service = ReviewService(Settings())
    try:
        assert service.save_outcome(event) == receipt
        memory.log_outcome.assert_awaited_once_with(event)
        model.assert_not_called()
    finally:
        service.close()
