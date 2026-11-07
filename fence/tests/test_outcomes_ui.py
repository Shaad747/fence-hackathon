from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from core.outcomes import OutcomeQueue
from core.schemas import RetainReceipt
from test_review_ui import lotus_run
from test_ui import APP


def setup(monkeypatch, tmp_path):
    queue = OutcomeQueue(tmp_path / 'q', 'bank')
    monkeypatch.setattr('ui.outcomes.get_queue', lambda: queue)
    service = Mock()
    service.save_outcome.side_effect = lambda event: RetainReceipt(document_id='fence:outcome:' + event.event_id, status='retained')
    monkeypatch.setattr('ui.outcomes.get_review_service', lambda: service)
    app = AppTest.from_file(APP)
    app.session_state['review_run'] = lotus_run()
    app.run()
    return queue, service, app


def submit(app, notes):
    next(item for item in app.text_area if item.label == 'Reason or supporting notes').set_value(notes)
    next(item for item in app.button if item.label == 'Save outcome').click().run()


def test_explicit_submit_validation_reruns_and_reload(monkeypatch, tmp_path):
    queue, service, app = setup(monkeypatch, tmp_path)
    submit(app, ' ')
    assert any('add a reason' in item.value for item in app.error)
    assert service.save_outcome.call_count == 0
    submit(app, 'Pilot approved with migration support.')
    assert not app.exception
    assert any('Outcome saved' in item.value for item in app.success)
    assert len(queue.records()) == 1 and queue.records()[0][1]
    app.run()
    submit(app, 'Pilot approved with migration support.')
    assert service.save_outcome.call_count == 1
    second = AppTest.from_file(APP).run()
    assert any('Accepted' in item.label and 'Saved' in item.label for item in second.expander)
    assert service.save_outcome.call_count == 1


def test_failed_save_retries_original_event_and_preserves_report(monkeypatch, tmp_path):
    queue, service, app = setup(monkeypatch, tmp_path)
    service.save_outcome.side_effect = RuntimeError('private provider details')
    submit(app, 'Pending executive approval.')
    assert not queue.records()[0][1]
    assert any('could not be confirmed' in item.value for item in app.error)
    assert 'private provider details' not in str(app)
    event = service.save_outcome.call_args.args[0]
    app.run()
    assert service.save_outcome.call_count == 1
    service.save_outcome.side_effect = lambda e: RetainReceipt(document_id='fence:outcome:' + e.event_id, status='unchanged')
    next(item for item in app.button if item.label == 'Retry saving this outcome').click().run()
    assert queue.confirmed(event)
    assert service.save_outcome.call_args.args[0] == event
    assert app.session_state['review_run'].result.citation_ids == ['lotus-fact']
