"""Offline Streamlit interaction checks for the Stage 4 shell."""

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from seed.seed import load_decisions
from ui.components import LOTUS_ID, SAMPLE_PROPOSAL, decision_details

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_shell_shows_the_illustrative_archive_and_lotus_first():
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert len(app.expander) == len(load_decisions()) == 14
    assert "Project Lotus" in app.expander[0].label and "Failed" in app.expander[0].label
    assert any("31%" in item.value and "Fictional case study" in item.value for item in app.markdown)
    assert app.text_area(key="proposal").value == ""


def test_sample_and_local_draft_validation(monkeypatch):
    from unittest.mock import Mock
    from core.config import ConfigurationError
    service = Mock(side_effect=ConfigurationError("Configure providers before reviewing."))
    monkeypatch.setattr("ui.review.get_review_service", service)
    app = AppTest.from_file(APP).run()
    app.button(key="check_proposal").click().run()
    assert "at least 20 characters" in app.error[0].value
    app.button(key="sample_proposal").click().run()
    assert app.text_area(key="proposal").value == SAMPLE_PROPOSAL
    assert not app.error
    app.button(key="check_proposal").click().run()
    assert "Configure providers" in app.error[0].value
    assert service.call_count == 1
    assert any("Live review" in item.value for item in app.caption)


@pytest.mark.parametrize(("key", "value", "matching"), [
    ("outcome", "failed", lambda decision: decision.outcome == "failed"),
    ("team", "Pricing and growth", lambda decision: decision.team == "Pricing and growth"),
    ("year", 2023, lambda decision: decision.date.year == 2023),
    ("tag", "free-tier", lambda decision: "free-tier" in decision.tags),
])
def test_archive_filter_matches_seed_records(key, value, matching):
    app = AppTest.from_file(APP).run()
    app.selectbox(key=f"archive_{key}").set_value(value).run()
    expected = [item for item in load_decisions() if matching(item)]
    labels = [item.label for item in app.expander]
    assert not app.exception
    assert len(labels) == len(expected)
    assert all(any(item.title in label for label in labels) for item in expected)


def test_combined_empty_filters_can_be_cleared_without_losing_the_draft():
    app = AppTest.from_file(APP).run()
    app.button(key="sample_proposal").click().run()
    app.selectbox(key="archive_outcome").set_value("success").run()
    app.selectbox(key="archive_tag").set_value("free-tier").run()
    assert not app.expander
    assert "No decisions match" in app.info[0].value
    app.button(key="reset_archive").click().run()
    assert len(app.expander) == 14
    assert all(widget.value is None for widget in app.selectbox)
    assert app.text_area(key="proposal").value == SAMPLE_PROPOSAL


def test_missing_archive_shows_an_error_and_keeps_the_draft_available(monkeypatch):
    def missing():
        raise FileNotFoundError("private/path")

    st.cache_data.clear()
    monkeypatch.setattr("seed.seed.load_decisions", missing)
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert not app.expander
    assert "The local decision archive could not be loaded" in app.error[0].value
    assert "private/path" not in app.error[0].value
    app.button(key="sample_proposal").click().run()
    assert app.text_area(key="proposal").value == SAMPLE_PROPOSAL


def test_archive_detail_escapes_seed_fields():
    lotus = next(item for item in load_decisions() if item.id == LOTUS_ID)
    hostile = lotus.model_copy(update={"owner": "<img src=x>", "reasons": ["<script>bad()</script>"],
                                      "tags": ["<b>tag</b>"]})
    markup = decision_details(hostile)
    assert "<img" not in markup and "<script" not in markup and "<b>tag" not in markup
    assert "&lt;img src=x&gt;" in markup and "&lt;script&gt;bad()&lt;/script&gt;" in markup
