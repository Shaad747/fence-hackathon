from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from core.reflection import ReflectionJobs
from test_reflection import confirm
from test_ui import APP


RESULT={'patterns':[], 'source_count':0, 'limitation':'Insufficient evidence.'}


def setup(monkeypatch,tmp_path):
    jobs=ReflectionJobs(tmp_path/'q','bank')
    monkeypatch.setattr('ui.reflection.get_queue',lambda:jobs)
    service=Mock()
    service.reflect.return_value=RESULT
    monkeypatch.setattr('ui.reflection.get_review_service',lambda:service)
    return jobs,service


def test_manual_reruns_restart_and_empty_result(monkeypatch,tmp_path):
    jobs,service=setup(monkeypatch,tmp_path)
    app=AppTest.from_file(APP).run()
    service.reflect.assert_not_called()
    app.button(key='manual_reflection').click().run()
    assert not app.exception and service.reflect.call_count==1
    assert any('No recurring pattern' in item.value for item in app.info)
    app.run()
    reloaded=AppTest.from_file(APP).run()
    assert not reloaded.exception and service.reflect.call_count==1
    assert jobs.jobs()[0]['status']=='succeeded'


def test_automatic_third_outcome_and_failed_retry_preserve_last_success(monkeypatch,tmp_path):
    jobs,service=setup(monkeypatch,tmp_path)
    confirm(jobs,1); confirm(jobs,2)
    app=AppTest.from_file(APP).run()
    service.reflect.assert_not_called()
    confirm(jobs,3)
    app.run()
    assert service.reflect.call_count==1
    app.run()
    assert service.reflect.call_count==1
    service.reflect.side_effect=RuntimeError('secret provider body')
    for n in range(4,7): confirm(jobs,n)
    app.run()
    assert service.reflect.call_count==2 and not app.exception
    assert 'secret provider body' not in str(app)
    assert any('auto-3' in c.value for c in app.caption)
    app.run()
    assert service.reflect.call_count==2
    service.reflect.side_effect=None
    app.button(key='retry-reflection-auto-6').click().run()
    assert service.reflect.call_count==3
    assert all(job['status']=='succeeded' for job in jobs.jobs())
    assert len(jobs.records())==6


def test_third_successful_form_save_triggers_once_in_same_rerun(monkeypatch,tmp_path):
    from core.schemas import RetainReceipt
    from test_review_ui import lotus_run
    jobs,service=setup(monkeypatch,tmp_path)
    monkeypatch.setattr('ui.outcomes.get_queue',lambda:jobs)
    writer=Mock()
    writer.save_outcome.side_effect=lambda event: RetainReceipt(document_id='fence:outcome:'+event.event_id,status='retained')
    monkeypatch.setattr('ui.outcomes.get_review_service',lambda:writer)
    app=AppTest.from_file(APP)
    app.session_state['review_run']=lotus_run()
    app.run()
    for n in range(1,4):
        next(w for w in app.text_area if w.label=='Reason or supporting notes').set_value(f'Confirmed pilot decision note {n}.')
        next(w for w in app.button if w.label=='Save outcome').click().run()
        assert service.reflect.call_count == n//3
    next(w for w in app.button if w.label=='Save outcome').click().run()
    app.run()
    assert writer.save_outcome.call_count==3
    assert service.reflect.call_count==1
    assert jobs.jobs()[0]['job_id']=='auto-3' and jobs.jobs()[0]['status']=='succeeded'
