import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

import pytest
from hindsight_client_api.models import ReflectResponse

from core.reflection import ReflectionJobs, reflect_history
from core.memory import MemoryClient
from core.schemas import RetainReceipt
from test_memory import FakeSDK, settings
from test_pipeline import LOTUS, recalled
from test_review_ui import lotus_run


def confirm(jobs, number, status='accepted'):
    result = lotus_run().result
    result.proposal.original_input += f' Distinct decision {number}.'
    event = jobs.prepare(result, status, f'Support staffing required for decision {number}.')
    jobs.confirm(event, RetainReceipt(document_id='fence:outcome:'+event.event_id, status='retained'))
    return event


def test_milestones_deduplicate_restart_and_concurrent_claims(tmp_path):
    jobs = ReflectionJobs(tmp_path/'q','bank')
    confirm(jobs, 0, 'pending')
    for number in range(1,10):
        event = confirm(jobs, number)
        jobs.confirm(event, RetainReceipt(document_id='fence:outcome:'+event.event_id,status='unchanged'))
        assert jobs.sync() == number
        assert len(jobs.jobs()) == number//3
    with ThreadPoolExecutor(4) as workers:
        counts = list(workers.map(lambda _: ReflectionJobs(tmp_path/'q','bank').sync(), range(4)))
        claims = list(workers.map(lambda _: jobs.claim('auto-3'), range(4)))
    assert counts == [9]*4 and sum(c is not None for c in claims)==1
    token, outcomes = next(c for c in claims if c)
    assert len(outcomes)==3
    assert jobs.finish('auto-3',token,result={'patterns':[]})
    assert ReflectionJobs(tmp_path/'q','bank').claim('auto-3') is None
    assert [j['job_id'] for j in jobs.jobs()] == ['auto-3','auto-6','auto-9']
    assert [len(json.loads(j['payload'])) for j in jobs.jobs()] == [3,6,9]


def test_failure_and_uncertain_interruption_require_explicit_retry(tmp_path):
    jobs = ReflectionJobs(tmp_path/'q','bank')
    for n in range(3): confirm(jobs,n)
    jobs.sync()
    token,_ = jobs.claim('auto-3')
    jobs.finish('auto-3',token,error='timeout')
    assert jobs.claim('auto-3') is None
    next_token,_ = jobs.claim('auto-3',retry=True)
    assert not jobs.finish('auto-3',token,result={})
    with jobs.connect() as db:
        db.execute('UPDATE reflections SET started=0')
    jobs.sync()
    assert jobs.jobs()[0]['status']=='failed'
    assert not jobs.finish('auto-3',next_token,result={})
    assert len(jobs.records())==3 and all(saved for _,saved in jobs.records())
    assert jobs.claim('auto-3',retry=True) is not None


def test_unconfirmed_and_votes_do_not_create_milestones(tmp_path):
    from core.learning import FeedbackQueue
    jobs=ReflectionJobs(tmp_path/'q','bank')
    result=lotus_run().result
    jobs.prepare(result,'accepted','Unconfirmed.')
    votes=FeedbackQueue(tmp_path/'q','bank')
    event=votes.prepare(result,'lotus-fact','relevant')
    votes.confirm(event,RetainReceipt(document_id='fence:feedback:'+event.event_id,status='retained'))
    jobs.sync()
    assert jobs.jobs()==[]


def test_grounded_reflection_uses_exact_outcomes_and_source_ids(tmp_path):
    jobs=ReflectionJobs(tmp_path/'q','bank')
    events=[confirm(jobs,n) for n in range(3)]
    async def run():
        sdk=FakeSDK()
        memory=MemoryClient(settings(),sdk)
        for event in events: await memory.log_outcome(event)
        memory.recall_for_proposal=AsyncMock(return_value=[])
        ids=['fence:outcome:'+e.event_id for e in events]
        sdk.areflect.return_value=ReflectResponse(text='Unsupported model prose must never appear.',structured_output={'patterns':[{'theme':'support_capacity','source_ids':ids}]})
        result=await reflect_history(memory,events)
        assert result['patterns'][0]['count']==3
        assert [s['id'] for s in result['patterns'][0]['sources']]==ids
        assert 'Unsupported model prose' not in json.dumps(result)
        assert all(event.reason in source['text'] for event,source in zip(events,result['patterns'][0]['sources']))
        assert sdk.areflect.call_args.kwargs['response_schema']
        assert sdk.areflect.call_args.kwargs['tags']==['fence-decision','fence-outcome']
    asyncio.run(run())


@pytest.mark.parametrize('mode',['fabricated','same_proposal','wrong_theme','malformed'])
def test_unsupported_patterns_fail_closed(tmp_path,mode):
    jobs=ReflectionJobs(tmp_path/'q','bank')
    events=[confirm(jobs,n) for n in range(2)]
    if mode=='same_proposal':
        events[1]=events[1].model_copy(update={'proposal_reference':events[0].proposal_reference})
    async def run():
        sdk=FakeSDK(); memory=MemoryClient(settings(),sdk)
        for event in events: await memory.log_outcome(event)
        memory.recall_for_proposal=AsyncMock(return_value=[])
        ids=['fence:outcome:'+e.event_id for e in events]
        if mode=='fabricated': ids[1]='invented'
        sdk.areflect.return_value=ReflectResponse(text='',structured_output=None if mode=='malformed' else {'patterns':[{'theme':'vendor_reliability' if mode=='wrong_theme' else 'support_capacity','source_ids':ids}]})
        if mode=='same_proposal':
            assert (await reflect_history(memory,events))['patterns']==[]
            sdk.areflect.assert_not_awaited()
        else:
            with pytest.raises(ValueError): await reflect_history(memory,events)
    asyncio.run(run())


def test_empty_history_does_not_call_reflect():
    async def run():
        sdk=FakeSDK(); memory=MemoryClient(settings(),sdk)
        memory.recall_for_proposal=AsyncMock(return_value=[])
        assert (await reflect_history(memory,[]))['patterns']==[]
        sdk.areflect.assert_not_awaited()
    asyncio.run(run())


def test_historical_provenance_is_required_and_original_sources_preserved():
    async def run():
        sdk=FakeSDK(); memory=MemoryClient(settings(),sdk)
        first=recalled(LOTUS,'one')
        second=recalled(LOTUS.model_copy(update={'id':'other','title':'Other pricing decision'}),'two')
        before=[first.model_dump(),second.model_dump()]
        memory.recall_for_proposal=AsyncMock(return_value=[first,second])
        sdk.areflect.return_value=ReflectResponse(text='',structured_output={'patterns':[{'theme':'support_capacity','source_ids':[first.document_id,second.document_id]}]})
        result=await reflect_history(memory,[])
        assert result['patterns'][0]['count']==2
        assert [first.model_dump(),second.model_dump()]==before
        memory.recall_for_proposal.return_value=[first.model_copy(update={'source_truncated':True})]
        assert (await reflect_history(memory,[]))['patterns']==[]
    asyncio.run(run())


def test_remote_outcome_tamper_and_incomplete_operation_are_rejected(tmp_path):
    events=[confirm(ReflectionJobs(tmp_path/'q','bank'),n) for n in range(2)]
    async def run():
        sdk=FakeSDK(); memory=MemoryClient(settings(),sdk)
        for event in events: await memory.log_outcome(event)
        sdk.poll_status='processing'
        with pytest.raises(ValueError,match='persistence'):
            await reflect_history(memory,events)
        sdk.poll_status='completed'
        sdk.stored[(settings().hindsight_bank_id,'fence:outcome:'+events[0].event_id)].original_text='Different content'
        with pytest.raises(ValueError,match='missing or inconsistent'):
            await reflect_history(memory,events)
        sdk.areflect.assert_not_awaited()
    asyncio.run(run())


def test_reflect_source_context_survives_generated_sdk_serialization():
    from hindsight_client_api.models.reflect_request import ReflectRequest
    async def run():
        sdk=FakeSDK(); memory=MemoryClient(settings(),sdk)
        await memory.reflect_patterns('Find themes.',context='source-id-123',response_schema={'type':'object','properties':{'patterns':{'type':'array'}}})
        kwargs=sdk.areflect.call_args.kwargs
        # Installed SDK's ReflectRequest drops context; evidence must travel in query.
        wire=ReflectRequest(**{k:v for k,v in kwargs.items() if k in ReflectRequest.model_fields}).to_dict()
        assert 'source-id-123' in wire['query']
        assert 'source-id-123' in kwargs['query']
        assert 'context' not in kwargs
    asyncio.run(run())


def test_wire_schema_inlines_nested_type_without_relaxing_validation():
    from core.reflection import reflection_schema, ReflectionSelection
    schema=reflection_schema()
    assert '$ref' not in json.dumps(schema) and '$defs' not in schema
    assert schema['properties']['patterns']['items']['required']==['theme','source_ids']
    with pytest.raises(ValueError):
        ReflectionSelection.model_validate({'patterns':[{'theme':'invented','source_ids':['a','b']}]})


def test_conflicting_historical_source_versions_cannot_ground_reflection():
    async def run():
        sdk=FakeSDK(); memory=MemoryClient(settings(),sdk)
        first=recalled(LOTUS,'fact-a')
        conflicting=first.model_copy(update={'memory_id':'fact-b','source_text':first.source_text.replace('31%', '0%')})
        other=recalled(LOTUS.model_copy(update={'id':'other','title':'Other pricing'}),'fact-c')
        memory.recall_for_proposal=AsyncMock(return_value=[first,conflicting,other])
        sdk.areflect.return_value=ReflectResponse(text='',structured_output={'patterns':[{'theme':'support_capacity','source_ids':[first.document_id,other.document_id]}]})
        with pytest.raises(ValueError,match='inconsistent'):
            await reflect_history(memory,[])
        sdk.areflect.assert_not_awaited()
    asyncio.run(run())
