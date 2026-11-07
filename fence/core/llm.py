"""One bounded Groq request path for plain text and validated JSON."""

import asyncio
import json
import math
import re
from collections.abc import Callable, Sequence
from typing import Literal, TypeVar

from groq import APIConnectionError, APIResponseValidationError, APIStatusError, APITimeoutError, AsyncGroq
from groq.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ValidationError
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_random_exponential

from core.config import Settings
from core.schemas import ServiceFailure

Model = TypeVar("Model", bound=BaseModel)
Result = TypeVar("Result")
MAX_BACKOFF_SECONDS = 2.0
_GPT_OSS_MODELS = {"openai/gpt-oss-120b", "openai/gpt-oss-20b"}
_FENCE = re.compile(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.IGNORECASE | re.DOTALL)
_JSON_TOKENS = re.compile(r'"(?:[^"\\]|\\.)*"|,(?=\s*[}\]])')


class LLMServiceError(Exception):
    """A safe error for callers to display. Provider bodies and model output stay private."""

    def __init__(self, code, message, next_step, *, retryable=False, http_status=None, retry_after=0.0):
        self.error = ServiceFailure(code=code, message=message, next_step=next_step, retryable=retryable)
        self.http_status = http_status
        self.retry_after = retry_after
        super().__init__(f"{message} {next_step}")


def _invalid_response(http_status=None) -> LLMServiceError:
    return LLMServiceError(
        "invalid_response", "Groq returned incomplete or invalid output.",
        "Try again. If the issue persists, check the model and response schema.",
        retryable=True, http_status=http_status,
    )


def _timeout(http_status=None) -> LLMServiceError:
    return LLMServiceError(
        "timeout", "Groq did not finish within the request time limit.",
        "Try again or adjust GROQ_TIMEOUT_SECONDS.", retryable=True, http_status=http_status,
    )


def _retry_after(exc: APIStatusError) -> float:
    # Groq documents Retry-After as seconds. Ignore malformed values.
    try:
        seconds = float(exc.response.headers.get("retry-after", "0"))
    except ValueError:
        return 0.0
    return seconds if math.isfinite(seconds) and seconds > 0 else 0.0


def _status_error(exc: APIStatusError) -> LLMServiceError:
    status = exc.status_code
    if status in {401, 403}:
        return LLMServiceError(
            "authentication", "Groq rejected the credentials or model access.",
            "Check GROQ_API_KEY and the project's model permissions.", http_status=status,
        )
    if status == 429:
        return LLMServiceError(
            "rate_limit", "Groq rate limited the request.",
            "Wait before trying again or check the project's rate limits.",
            retryable=True, http_status=status, retry_after=_retry_after(exc),
        )
    if status == 408:
        return _timeout(status)
    if status in {498, 500, 502, 503, 504}:
        return LLMServiceError(
            "unavailable", "Groq is temporarily unavailable.",
            "Try again shortly.", retryable=True, http_status=status, retry_after=_retry_after(exc),
        )
    return LLMServiceError(
        "configuration", "Groq rejected the request or configured model.",
        "Check the model IDs and request schema. Select a supported model if necessary.",
        http_status=status,
    )


def _repair_json(text: str) -> str:
    """Remove one full Markdown fence and trailing commas outside quoted strings."""
    text = text.strip()
    if match := _FENCE.fullmatch(text):
        text = match[1].strip()

    def replace(token: re.Match[str]) -> str:
        if token[0] != ",":
            return token[0]
        previous = text[:token.start()].rstrip()[-1:]
        return "" if previous and previous not in "{[,:" else token[0]

    return _JSON_TOKENS.sub(replace, text)


def _validate_json(text: str, schema: type[Model]) -> Model:
    try:
        return schema.model_validate_json(text, strict=True)
    except ValidationError as exc:
        issues = exc.errors(include_input=False, include_context=False)
        if any(issue["type"] == "json_invalid" for issue in issues):
            repaired = _repair_json(text)
            if repaired != text:
                try:
                    return schema.model_validate_json(repaired, strict=True)
                except ValidationError:
                    pass
        raise _invalid_response() from None


class LLMClient:
    """Use in one async context. The app owns retry and fallback policy."""

    def __init__(self, settings: Settings, client: AsyncGroq | None = None):
        self.settings = settings
        if client is None:
            key = settings.groq_api_key.get_secret_value().strip()
            if not key:
                raise LLMServiceError("configuration", "Groq credentials are missing.", "Set GROQ_API_KEY in .env.")
            client = AsyncGroq(
                api_key=key, base_url="https://api.groq.com",
                timeout=settings.groq_timeout_seconds, max_retries=0,
            )
        self.client = client

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.aclose()

    async def aclose(self) -> None:
        await self.client.close()

    async def chat(
        self, messages: Sequence[ChatCompletionMessageParam], *, max_completion_tokens: int = 1024,
        model: str | None = None, single_attempt: bool = False,
    ) -> str:
        return await self._complete(messages, str.strip, None, max_completion_tokens, model, single_attempt)

    async def structured_chat(
        self, messages: Sequence[ChatCompletionMessageParam], schema: type[Model], *,
        max_completion_tokens: int = 1024, model: str | None = None, single_attempt: bool = False,
        reasoning_effort: Literal["low", "medium", "high"] | None = None,
    ) -> Model:
        response_format = {"type": "json_schema", "json_schema": {
            "name": schema.__name__, "strict": False, "schema": schema.model_json_schema(),
        }}
        return await self._complete(
            messages, lambda content: _validate_json(content, schema), response_format,
            max_completion_tokens, model, single_attempt, reasoning_effort,
        )

    async def _complete(
        self, messages, decode: Callable[[str], Result], response_format,
        max_completion_tokens: int, model: str | None, single_attempt: bool,
        reasoning_effort: str | None = None,
    ) -> Result:
        primary = model or self.settings.groq_primary_model
        fallback = self.settings.groq_fallback_model
        models = (primary,) if single_attempt or primary == fallback else (primary, fallback)
        attempts = 1 if single_attempt else self.settings.groq_max_attempts
        backoff = wait_random_exponential(multiplier=0.25, max=MAX_BACKOFF_SECONDS)

        def can_retry(exc: BaseException) -> bool:
            return (isinstance(exc, LLMServiceError) and exc.error.retryable
                    and exc.retry_after <= MAX_BACKOFF_SECONDS)

        def wait(state) -> float:
            error = state.outcome.exception()
            return max(backoff(state), error.retry_after)

        for current_model in models:
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(attempts), wait=wait,
                    retry=retry_if_exception(can_retry), reraise=True,
                ):
                    with attempt:
                        return await self._request(
                            current_model, messages, decode, response_format, max_completion_tokens, reasoning_effort,
                        )
            except LLMServiceError as exc:
                if current_model == models[-1] or not exc.error.retryable:
                    raise

        raise AssertionError("At least one Groq model is required")

    async def _request(self, model, messages, decode, response_format, max_completion_tokens, reasoning_effort):
        options = {"response_format": response_format} if response_format is not None else {}
        if reasoning_effort is not None and model in _GPT_OSS_MODELS:
            options["reasoning_effort"] = reasoning_effort
        try:
            async with asyncio.timeout(self.settings.groq_timeout_seconds):
                response = await self.client.chat.completions.create(
                    model=model, messages=messages, max_completion_tokens=max_completion_tokens,
                    **options,
                )
        except (APITimeoutError, TimeoutError):
            raise _timeout() from None
        except APIConnectionError:
            raise LLMServiceError(
                "unavailable", "Could not connect to Groq.",
                "Check network connectivity and try again.", retryable=True,
            ) from None
        except (APIResponseValidationError, json.JSONDecodeError, UnicodeDecodeError):
            raise _invalid_response() from None
        except APIStatusError as exc:
            body = exc.body if isinstance(exc.body, dict) else {}
            error = body.get("error", body)
            if (response_format is not None and exc.status_code in {400, 422}
                    and isinstance(error, dict) and error.get("code") == "json_validate_failed"):
                generated = error.get("failed_generation")
                if isinstance(generated, str):
                    try:
                        return decode(generated)
                    except LLMServiceError:
                        pass
                raise _invalid_response(exc.status_code) from None
            raise _status_error(exc) from None

        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or not choices:
            raise _invalid_response()
        choice = choices[0]
        content = getattr(getattr(choice, "message", None), "content", None)
        if getattr(choice, "finish_reason", None) != "stop" or not isinstance(content, str) or not content.strip():
            raise _invalid_response()
        return decode(content)
