"""One isolated live reflection probe: three synthetic outcomes, one reflection, no Groq wrapper."""
import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from core.config import load_settings
from core.memory import MemoryClient, MemoryServiceError
from core.reflection import reflect_history
from core.schemas import Outcome


async def check():
    bank='fence-reflect-verify-'+uuid4().hex[:12]
    print(json.dumps({'isolated_bank':bank}), flush=True)
    settings=load_settings().model_copy(update={'hindsight_bank_id':bank, 'hindsight_max_attempts':1,
                                               'hindsight_timeout_seconds':45, 'hindsight_operation_timeout_seconds':120})
    events=[Outcome(proposal_reference=f'verification-proposal-{n}', status='shipped',
                    reason=f'Isolated synthetic verification outcome {n}: support capacity constrained the pilot. Support staffing was checked before rollout.',
                    timestamp=datetime.now(timezone.utc), event_id=f'verification-outcome-{n}') for n in range(3)]
    async with MemoryClient(settings) as writer:
        for event in events:
            await writer.log_outcome(event)
    async with MemoryClient(settings) as reader:
        result=await reflect_history(reader,events)
        assert result['source_count']==3
        for pattern in result['patterns']:
            assert pattern['count']>=2
            assert all(source['id'] in {'fence:outcome:'+e.event_id for e in events} for source in pattern['sources'])
        assert reader.activity_summary()['reflect'].get('succeeded')==1
        return {'passed':True, 'isolated_bank':bank, 'verified_sources':result['source_count'],
                'supported_patterns':len(result['patterns']), 'reflect_calls':1, 'groq_wrapper_calls':0,
                'source_ids_verified':True}


if __name__=='__main__':
    try:
        print(json.dumps(asyncio.run(check())))
    except MemoryServiceError as exc:
        print(json.dumps({'passed':False,'error':exc.error.model_dump()}))
        raise SystemExit(1)
    except Exception as exc:
        print(json.dumps({'passed':False,'error_type':type(exc).__name__,'error':'Reflection probe failed validation or deadline; no provider body is displayed.'}))
        raise SystemExit(1)
