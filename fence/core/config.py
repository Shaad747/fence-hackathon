"""Explicit, secret-safe configuration shared by Cloud and local deployments."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

ROOT = Path(__file__).resolve().parents[1]


class ConfigurationError(ValueError):
    """A safe message that callers can display without exposing credentials."""


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    outcome_queue_path: Path = ROOT / ".data" / "outcomes.sqlite3"

    hindsight_base_url: str = "https://api.hindsight.vectorize.io"
    hindsight_api_key: SecretStr = SecretStr("")
    hindsight_bank_id: str = Field(default="kaveri-pay", pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}$")
    hindsight_timeout_seconds: float = Field(default=15, gt=0, le=120)
    hindsight_operation_timeout_seconds: float = Field(default=90, gt=0, le=600)
    hindsight_max_attempts: int = Field(default=3, ge=1, le=5)
    hindsight_retry_min_seconds: float = Field(default=0.5, ge=0, le=5)
    hindsight_retry_max_seconds: float = Field(default=2, ge=0, le=10)
    hindsight_poll_interval_seconds: float = Field(default=1, gt=0, le=10)
    groq_api_key: SecretStr = SecretStr("")
    groq_primary_model: str = "openai/gpt-oss-120b"
    groq_fallback_model: str = "openai/gpt-oss-20b"
    groq_timeout_seconds: float = Field(default=8, gt=0, le=60)
    groq_max_attempts: int = Field(default=2, ge=1, le=4)

    @field_validator("groq_primary_model", "groq_fallback_model")
    @classmethod
    def valid_model_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Groq model IDs must be nonempty.")
        return value.strip()

    @field_validator("hindsight_base_url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        url = urlsplit(value)
        if url.scheme not in {"http", "https"} or not url.hostname:
            raise ValueError("HINDSIGHT_BASE_URL must be an HTTP(S) server URL.")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Put credentials in HINDSIGHT_API_KEY, never in the URL.")
        return value.rstrip("/")

    def validate_connection(self) -> None:
        if urlsplit(self.hindsight_base_url).hostname == "api.hindsight.vectorize.io":
            if not self.hindsight_api_key.get_secret_value().strip():
                raise ConfigurationError(
                    "Hindsight Cloud needs HINDSIGHT_API_KEY. Set it in .env, or set "
                    "HINDSIGHT_BASE_URL=http://localhost:8888 for a running local server."
                )


def load_settings(env_file: Path | None = None) -> Settings:
    """Read only Fence's known variables; exported values override the .env file."""
    values = {**dotenv_values(env_file or ROOT / ".env"), **os.environ}
    try:
        return Settings(**{
            field: values[field.upper()]
            for field in Settings.model_fields
            if values.get(field.upper()) is not None
        })
    except ValueError:
        raise ConfigurationError(
            "Fence configuration is invalid. Check the URL, bank ID, model IDs, and numeric limits "
            "against .env.example; credentials belong only in API-key variables."
        ) from None
