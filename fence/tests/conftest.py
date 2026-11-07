"""Keep UI tests independent of the developer's durable submission history."""
import pytest


@pytest.fixture(autouse=True)
def isolated_ui_outcomes(request, monkeypatch, tmp_path):
    if request.path.name in {'test_ui.py', 'test_review_ui.py', 'test_outcomes_ui.py', 'test_learning_ui.py', 'test_reflection_ui.py'}:
        monkeypatch.setenv('OUTCOME_QUEUE_PATH', str(tmp_path / 'ui-outcomes.sqlite3'))
