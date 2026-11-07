from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from core.schemas import RetainReceipt
from test_review_ui import lotus_run
from test_ui import APP


def test_votes_chart_counts_and_reruns(monkeypatch):
    service = Mock()
    service.save_feedback.side_effect = lambda event: RetainReceipt(document_id='fence:feedback:'+event.event_id, status='retained')
    service.read_feedback.return_value = []
    monkeypatch.setattr('ui.learning.get_review_service',lambda:service)
    app = AppTest.from_file(APP)
    app.session_state['review_run'] = lotus_run()
    app.run()
    assert service.save_feedback.call_count == 0
    app.button(key='vote-lotus-fact-relevant').click().run()
    assert not app.exception
    assert next(m for m in app.metric if m.label == 'Confirmed votes').value == '1'
    assert len(app.get('plotly_chart')) == 1
    app.run()
    app.button(key='vote-lotus-fact-relevant').click().run()
    assert service.save_feedback.call_count == 1
    app.button(key='vote-lotus-fact-not_relevant').click().run()
    assert service.save_feedback.call_count == 2
    assert next(m for m in app.metric if m.label == 'Confirmed votes').value == '2'
    assert any('vote signal +0.00' in t.value for t in app.text)
    assert app.session_state['review_run'].result.citation_ids == ['lotus-fact']
    reloaded = AppTest.from_file(APP).run()
    assert next(m for m in reloaded.metric if m.label == 'Confirmed votes').value == '2'
    assert service.read_feedback.call_count == 0


def test_failed_vote_and_refresh_do_not_invent_learning(monkeypatch):
    service = Mock()
    service.save_feedback.side_effect = RuntimeError('private error')
    service.read_feedback.side_effect = RuntimeError('private error')
    monkeypatch.setattr('ui.learning.get_review_service',lambda:service)
    app = AppTest.from_file(APP)
    app.session_state['review_run'] = lotus_run()
    app.run()
    app.button(key='vote-lotus-fact-relevant').click().run()
    assert next(m for m in app.metric if m.label == 'Confirmed votes').value == '0'
    assert next(m for m in app.metric if m.label == 'Unconfirmed submissions').value == '1'
    assert len(app.get('plotly_chart')) == 0
    app.run()
    assert service.save_feedback.call_count == 1
    app.button(key='refresh_feedback').click().run()
    assert any('unavailable' in w.value for w in app.warning)
    assert 'private error' not in str(app)
