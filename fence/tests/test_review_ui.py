"""Real pipeline with offline providers, rendered through the real Streamlit app."""

import asyncio
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from core.pipeline import check_proposal
from core.review_service import ReviewRun
from core.schemas import DocumentSnapshot
from test_pipeline import LOTUS, LOTUS_PROPOSAL, providers, recalled, recommendation, memory_timeout
from test_ui import APP


def lotus_run():
    memory, llm = providers([[recalled(LOTUS, "lotus-fact")], [], []], draft=recommendation("lotus-fact"))
    result = asyncio.run(check_proposal(LOTUS_PROPOSAL, memory, llm)).model_copy(deep=True)
    return ReviewRun(result, [DocumentSnapshot(document_id=result.evidence[0].memory.document_id, memory_unit_count=3)], [])


def submit(monkeypatch, run):
    service = Mock()
    service.review.return_value = run
    monkeypatch.setattr("ui.review.get_review_service", lambda: service)
    app = AppTest.from_file(APP).run()
    assert service.review.call_count == 0
    app.button(key="sample_proposal").click().run()
    assert service.review.call_count == 0
    app.button(key="check_proposal").click().run()
    assert not app.exception
    service.review.assert_called_once_with(LOTUS_PROPOSAL)
    return app, service


def test_lotus_comparison_reruns_filters_toggle_and_explicit_retry(monkeypatch):
    app, service = submit(monkeypatch, lotus_run())
    rendered = '\n'.join(item.value for item in app.markdown)
    assert "31%" in rendered and "six weeks" in rendered and "lotus-fact" in rendered
    assert "Test willingness to pay" in rendered
    assert any("Recalled 1 of 1 retained decision documents" in item.value for item in app.caption)
    assert app.progress[0].value > 0
    app.radio(key="comparison_view").set_value("Without memory").run()
    assert "With memory" not in [item.value for item in app.subheader]
    app.radio(key="comparison_view").set_value("With memory").run()
    assert "Without memory" not in [item.value for item in app.subheader]
    app.selectbox(key="archive_outcome").set_value("failed").run()
    app.run()
    app.button(key="check_proposal").click().run()
    assert service.review.call_count == 1
    app.button(key="retry_review").click().run()
    assert service.review.call_count == 2
    app.text_area(key="proposal").set_value("A different proposal to pilot merchant pricing gradually.").run()
    assert service.review.call_count == 2
    assert any("editor differs" in item.value for item in app.info)
    app.button(key="check_proposal").click().run()
    assert service.review.call_count == 3


def test_failure_preserves_previous_report_and_does_not_expose_exception(monkeypatch):
    app, service = submit(monkeypatch, lotus_run())
    service.review.side_effect = RuntimeError("secret-provider-body")
    app.button(key="retry_review").click().run()
    assert not app.exception
    assert "could not finish" in app.error[0].value
    assert "secret-provider-body" not in str(app)
    assert any("previous completed check" in item.value for item in app.caption)
    app.run()
    assert service.review.call_count == 2


@pytest.mark.parametrize("failed", [False, True])
def test_empty_and_failed_retrieval_are_distinct_in_ui(monkeypatch, failed):
    memory, llm = providers([memory_timeout() if failed else [] for _ in range(3)])
    result = asyncio.run(check_proposal(LOTUS_PROPOSAL, memory, llm))
    app, _ = submit(monkeypatch, ReviewRun(result, [] if not failed else None, []))
    messages = ' '.join(item.value for item in [*app.info, *app.warning, *app.caption])
    assert ("No relevant history was found" in messages) == (not failed)
    assert ("does not confirm an empty archive" in messages) == failed
    assert not any('fence-risk-' in item.value and '<span' in item.value for item in app.markdown)


def test_ui_rejects_citations_not_in_current_retrieved_evidence(monkeypatch):
    run = lotus_run()
    run.result.evidence = []
    app, _ = submit(monkeypatch, run)
    assert any("unsupported citations" in item.value for item in app.error)
    assert not any('Cited evidence:' in item.value for item in app.markdown)


def test_sessions_do_not_share_reports(monkeypatch):
    first, service = submit(monkeypatch, lotus_run())
    second = AppTest.from_file(APP).run()
    assert "Fence Report" not in [item.value for item in second.subheader]
    assert first.session_state["review_run"].result.citation_ids == ["lotus-fact"]
    assert service.review.call_count == 1


def test_long_proposal_notice_and_escaped_content(monkeypatch):
    run = lotus_run()
    run.result.proposal.input_truncated = True
    run.result.baseline.summary = '<script>bad()</script>'
    app, _ = submit(monkeypatch, run)
    assert any("first 3,000" in item.value for item in app.warning)
    assert any('&lt;script&gt;bad()&lt;/script&gt;' in item.value for item in app.markdown)
    assert not any('<script>bad()' in item.value for item in app.markdown)


@pytest.mark.parametrize('risk', ['low', 'medium', 'high'])
def test_risk_badge_and_citation_target_match_current_evidence(monkeypatch, risk):
    from ui.review import _anchor
    run = lotus_run()
    run.result.report.risk_level = risk
    app, _ = submit(monkeypatch, run)
    markup = '\n'.join(item.value for item in app.markdown)
    assert f'class="fence-risk fence-risk-{risk}"' in markup
    target = _anchor('lotus-fact')
    assert f'href="#{target}"' in markup and f'id="{target}"' in markup


@pytest.mark.parametrize('stage', ['extraction', 'report', 'baseline'])
def test_model_failure_keeps_independent_answer_visible(monkeypatch, stage):
    from core.llm import LLMServiceError
    failure = LLMServiceError('invalid_response', 'Model output was invalid.', 'Retry the check.')
    options = {'draft': recommendation('lotus-fact')}
    options['draft' if stage == 'report' else stage] = failure
    memory, llm = providers([[recalled(LOTUS, 'lotus-fact')], [], []], **options)
    result = asyncio.run(check_proposal(LOTUS_PROPOSAL, memory, llm))
    app, _ = submit(monkeypatch, ReviewRun(result, [], []))
    assert any('Model output was invalid' in item.value for item in app.warning)
    markup = '\n'.join(item.value for item in app.markdown)
    assert ('Test willingness to pay' in markup) == (stage != 'baseline')
    assert ('Cited evidence:' in markup) == (stage == 'baseline')
    assert app.button(key='retry_review')


def test_sample_submit_shows_status_at_editor_and_report_link(monkeypatch):
    app, service = submit(monkeypatch, lotus_run())
    assert any('Review complete' in item.value and '#fence-report' in item.value for item in app.success)
    assert not any('Your draft is ready' in item.value for item in app.success)
    assert any('id="fence-report"' in item.value for item in app.markdown)
    assert app.text_area(key='proposal').value == LOTUS_PROPOSAL
    app.run()
    assert service.review.call_count == 1
    assert any('Review complete' in item.value for item in app.success)


def test_stale_stage4_module_requires_restart_instead_of_silent_submit(monkeypatch):
    import ui.components
    monkeypatch.delattr(ui.components, 'LIVE_REVIEW_VERSION')
    service = Mock()
    monkeypatch.setattr('ui.review.get_review_service', service)
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert 'older UI module' in app.error[0].value
    assert 'restart' in app.error[0].value
    assert not app.button
    service.assert_not_called()
