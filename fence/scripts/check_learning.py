"""One isolated persistence probe, no Groq calls and no demonstration-bank writes."""
import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from core.config import load_settings
from core.memory import MemoryClient, MemoryServiceError
from core.schemas import Feedback, Outcome


async def check():
    bank = 'fence-verify-' + uuid4().hex[:16]
    settings = load_settings().model_copy(update={'hindsight_bank_id': bank, 'hindsight_max_attempts': 1})
    now = datetime.now(timezone.utc)
    # Synthetic identifiers are intentionally confined to a separate verification bank.
    vote = Feedback(proposal_reference='verification-proposal', proposal_or_report_reference='verification-report',
                    lesson='Isolated persistence check; not demonstration evidence.', memory_ids=['verification-evidence'],
                    relevance='relevant', timestamp=now, event_id='verification-vote')
    outcome = Outcome(proposal_reference='verification-proposal', report_reference='verification-report',
                      proposal_text='Isolated test proposal', memory_ids=['verification-evidence'], citation_ids=[],
                      status='pending', reason='Persistence verification only.', timestamp=now, event_id='verification-outcome')
    async with MemoryClient(settings) as writer:
        vr = await writer.log_feedback(vote)
        ore = await writer.log_outcome(outcome)
    async with MemoryClient(settings) as reader:
        records = await reader.feedback_records()
        assert records == [vote]
        signals = await reader.feedback_signals('verification')
        assert signals == {'verification-evidence': 1.0}
        source = await reader._get_document(ore.document_id)
        assert source and outcome.report_reference in source.original_text and 'verification-evidence' in source.original_text
        duplicate = await reader.log_feedback(vote)
        assert duplicate.status == 'unchanged'
    return dict(passed=True, isolated_bank=bank, feedback_retained=vr.status, outcome_retained=ore.status,
                fresh_client_readback=True, associations_verified=True, duplicate_status=duplicate.status,
                vote_signal=signals['verification-evidence'], groq_calls=0)


def main():
    try:
        print(json.dumps(asyncio.run(check())))
    except MemoryServiceError as exc:
        print(json.dumps({'passed': False, 'error': exc.error.model_dump()}))
        raise SystemExit(1)
    except Exception:
        print(json.dumps({'passed': False, 'error': 'Verification failed; no credential or provider body is displayed.'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
