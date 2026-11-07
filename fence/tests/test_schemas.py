"""Record boundaries, editorial invariants, and secret-safe configuration."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.config import ConfigurationError, Settings, load_settings
from core.schemas import Decision, Feedback, Outcome, RecalledMemory


SEED_PATH = Path(__file__).resolve().parents[1] / "seed" / "seed_data.json"


@pytest.fixture
def archive():
    return [Decision.model_validate(item) for item in json.loads(SEED_PATH.read_text())]


@pytest.fixture
def clean_config_env(monkeypatch):
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)


def test_archive_is_valid_unique_and_clearly_illustrative(archive):
    assert len(archive) == len({decision.id for decision in archive}) == 14
    assert {decision.date.year for decision in archive} == {2022, 2023, 2024, 2025, 2026}
    assert {decision.outcome for decision in archive} == {
        "success", "partial", "failed", "rolled_back"
    }
    assert all("illustrative" in decision.tags for decision in archive)


def test_archive_preserves_required_anchor_facts(archive):
    decisions = {decision.title: decision for decision in archive}
    lotus = decisions["Project Lotus"]
    assert lotus.date.year == 2023 and 7 <= lotus.date.month <= 9
    assert "free merchant tier" in lotus.proposal
    assert "31%" in lotus.impact and "six weeks" in lotus.impact
    reasons = " ".join(lotus.reasons).lower()
    assert "support lacked migration capacity" in reasons
    assert "competitor" in reasons and "free-tier campaign" in reasons and "same month" in reasons

    settlement = decisions["Instant Settlement"]
    assert settlement.date.year == 2024 and settlement.outcome == "rolled_back"
    assert "without a fraud-ops review" in " ".join(settlement.reasons)
    assert "Month-one chargebacks" in settlement.impact and "₹38 lakh" in settlement.impact

    sms = decisions["SMS provider switch"]
    assert sms.date.year == 2023 and sms.outcome == "rolled_back"
    assert all(text in sms.impact for text in ("91%", "tier-2 cities", "three weeks"))

    soundbox = decisions["QR soundbox rollout"]
    assert soundbox.outcome == "success"
    assert "Mysuru, the only pilot city" in soundbox.proposal
    assert all(text in soundbox.reasons[0] for text in ("99.5%", "80%", "four consecutive weeks"))
    assert "3,200" in soundbox.impact and "28%" in soundbox.impact


@pytest.mark.parametrize(
    "change",
    [
        {"outcome": "pending"},
        {"reasons": []},
        {"reasons": [" \t "]},
        {"title": "  "},
        {"tags": []},
        {"tags": ["\n"]},
        {"id": "contains spaces"},
        {"id": "../unsafe-source"},
        {"id": ""},
        {"id": "a" * 161},
        {"unrecognised_fact": "must not silently enter the archive"},
    ],
)
def test_decision_rejects_invalid_boundary_values(archive, change):
    payload = archive[0].model_dump()
    payload.update(change)
    with pytest.raises(ValidationError):
        Decision.model_validate(payload)


def test_decision_strips_text_without_changing_stable_identity(archive):
    payload = archive[0].model_dump()
    payload.update(title="  Merchant onboarding  ", reasons=["  A reviewed reason.  "])
    decision = Decision.model_validate(payload)
    assert decision.title == "Merchant onboarding"
    assert decision.reasons == ["A reviewed reason."]
    assert decision.id == archive[0].id


@pytest.mark.parametrize("model", [Outcome, Feedback])
def test_event_timestamps_must_be_aware_and_ids_stable(model):
    timestamp = datetime(2026, 7, 14, 10, 30, tzinfo=timezone.utc)
    if model is Outcome:
        payload = dict(proposal_reference="proposal-1", status="approved", reason="Pilot first.")
    else:
        payload = dict(
            proposal_or_report_reference="report-1",
            lesson="Pilot before expanding.",
            memory_ids=["memory-1"],
            relevance="relevant",
        )
    payload.update(timestamp=timestamp, event_id="event:2026-07-14.1")
    event = model.model_validate(payload)
    assert event.timestamp.utcoffset().total_seconds() == 0
    assert model.model_validate_json(event.model_dump_json()).event_id == event.event_id
    with pytest.raises(ValidationError):
        model.model_validate({**payload, "timestamp": timestamp.replace(tzinfo=None)})
    with pytest.raises(ValidationError):
        model.model_validate({**payload, "event_id": "event with spaces"})


def test_feedback_requires_a_lesson_and_cited_memories():
    payload = dict(
        proposal_or_report_reference="report-1",
        lesson="Pilot before expanding.",
        memory_ids=["memory-1"],
        relevance="relevant",
        timestamp="2026-07-14T10:30:00+05:30",
        event_id="feedback-1",
    )
    for change in ({"memory_ids": []}, {"memory_ids": [" "]}, {"lesson": " "}, {"relevance": "yes"}):
        with pytest.raises(ValidationError):
            Feedback.model_validate({**payload, **change})


def test_recall_requires_bounded_relative_ranking():
    payload = dict(
        memory_id="memory-1",
        title="Project Lotus",
        evidence_text="Merchant churn reached 31% in six weeks.",
        retrieval_query="Removing the free merchant tier",
        retrieval_rank=1,
        ranking_signal=1.0,
    )
    memory = RecalledMemory.model_validate(payload)
    assert memory.ranking_label == "Relative ranking signal"
    assert memory.date is None
    for change in ({"retrieval_rank": 0}, {"ranking_signal": -0.1}, {"ranking_signal": 1.1}):
        with pytest.raises(ValidationError):
            RecalledMemory.model_validate({**payload, **change})


def test_env_file_is_read_without_mutating_process_environment(tmp_path, monkeypatch, clean_config_env):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "HINDSIGHT_BASE_URL=http://localhost:8888/\n"
        "HINDSIGHT_BANK_ID=from-file\n"
        "HINDSIGHT_TIMEOUT_SECONDS=7.5\n"
        "GROQ_PRIMARY_MODEL=override-model\n"
        "UNRELATED_FENCE_TEST_SETTING=ignored\n"
    )
    monkeypatch.setenv("HINDSIGHT_BANK_ID", "from-export")
    before = dict(os.environ)
    settings = load_settings(env_file)
    assert settings.hindsight_base_url == "http://localhost:8888"
    assert settings.hindsight_bank_id == "from-export"
    assert settings.hindsight_timeout_seconds == 7.5
    assert settings.groq_primary_model == "override-model"
    assert settings.groq_fallback_model == "openai/gpt-oss-20b"
    assert dict(os.environ) == before


def test_defaults_are_cloud_demo_bank_and_requested_groq_models(tmp_path, clean_config_env):
    settings = load_settings(tmp_path / "missing.env")
    assert settings.hindsight_base_url == "https://api.hindsight.vectorize.io"
    assert settings.hindsight_bank_id == "kaveri-pay"
    assert settings.groq_primary_model == "openai/gpt-oss-120b"
    assert settings.groq_fallback_model == "openai/gpt-oss-20b"


def test_cloud_requires_key_but_local_docker_does_not():
    with pytest.raises(ConfigurationError, match="HINDSIGHT_API_KEY"):
        Settings().validate_connection()
    with pytest.raises(ConfigurationError, match="HINDSIGHT_API_KEY"):
        Settings(hindsight_api_key="  ").validate_connection()
    Settings(hindsight_base_url="http://localhost:8888").validate_connection()
    Settings(hindsight_base_url="http://127.0.0.1:8888").validate_connection()
    Settings(hindsight_api_key="nonsecret-test-sentinel").validate_connection()


def test_secret_values_are_hidden_in_repr_and_serialized_settings():
    sentinel = "nonsecret-test-sentinel"
    settings = Settings(hindsight_api_key=sentinel, groq_api_key=sentinel)
    assert sentinel not in repr(settings)
    assert sentinel not in settings.model_dump_json()
    assert settings.hindsight_api_key.get_secret_value() == sentinel


@pytest.mark.parametrize(
    "invalid_url",
    [
        "ftp://localhost:8888",
        "localhost:8888",
        "https://",
        "https://user:nonsecret-test-sentinel@api.hindsight.vectorize.io",
        "https://api.hindsight.vectorize.io?key=nonsecret-test-sentinel",
        "https://api.hindsight.vectorize.io#nonsecret-test-sentinel",
    ],
)
def test_config_rejects_unsafe_urls_without_exposing_inputs(tmp_path, clean_config_env, invalid_url):
    env_file = tmp_path / ".env"
    env_file.write_text(f"HINDSIGHT_BASE_URL={invalid_url}\n")
    with pytest.raises(ConfigurationError) as error:
        load_settings(env_file)
    assert "nonsecret-test-sentinel" not in str(error.value)
    assert "configuration is invalid" in str(error.value)


@pytest.mark.parametrize(
    "setting",
    [
        "HINDSIGHT_TIMEOUT_SECONDS=0",
        "HINDSIGHT_OPERATION_TIMEOUT_SECONDS=601",
        "HINDSIGHT_MAX_ATTEMPTS=0",
        "HINDSIGHT_MAX_ATTEMPTS=6",
        "HINDSIGHT_BANK_ID=bank with spaces",
    ],
)
def test_config_enforces_bounded_calls_and_valid_workspace_names(tmp_path, clean_config_env, setting):
    env_file = tmp_path / ".env"
    env_file.write_text(setting + "\n")
    with pytest.raises(ConfigurationError):
        load_settings(env_file)
