"""Exercise the Groq SDK request path with an offline HTTP transport."""

import asyncio
import json
from functools import partial
from unittest.mock import AsyncMock

import httpx
import pytest
from groq import AsyncGroq
from tenacity import AsyncRetrying

from core.config import Settings, load_settings
from core.llm import LLMClient, LLMServiceError
from core.schemas import Record

PRIMARY = "openai/gpt-oss-120b"
FALLBACK = "openai/gpt-oss-20b"
MESSAGES = [{"role": "user", "content": "Return a JSON object with count and note."}]


class Answer(Record):
    count: int
    note: str


def completion(content, finish_reason="stop"):
    return httpx.Response(200, json={
        "id": "test-completion", "object": "chat.completion", "created": 0, "model": PRIMARY,
        "choices": [{"index": 0, "finish_reason": finish_reason,
                     "message": {"role": "assistant", "content": content}}],
    })


def error(status, *, retry_after=None, **details):
    headers = {"retry-after": str(retry_after)} if retry_after is not None else {}
    return httpx.Response(status, headers=headers, json={"error": {"message": "private-provider-body", **details}})


def client_for(responses, **settings):
    """Record HTTP bodies so assertions include the model and exact network budget."""
    requests = []
    pending = iter(responses)

    async def handle(request):
        requests.append(json.loads(request.content))
        response = next(pending)
        return await response() if callable(response) else response

    sdk = AsyncGroq(
        api_key="test-placeholder", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    return LLMClient(Settings(**settings), sdk), requests


def test_groq_config_reads_env_file_and_bounds_requests(tmp_path, monkeypatch):
    for name in ("GROQ_API_KEY", "GROQ_TIMEOUT_SECONDS", "GROQ_MAX_ATTEMPTS", "GROQ_PRIMARY_MODEL"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=test-placeholder\nGROQ_TIMEOUT_SECONDS=3.5\nGROQ_MAX_ATTEMPTS=1\n")
    settings = load_settings(env_file)
    assert settings.groq_timeout_seconds == 3.5
    assert settings.groq_max_attempts == 1
    assert settings.groq_api_key.get_secret_value() == "test-placeholder"
    assert "test-placeholder" not in repr(settings)


def test_missing_key_has_typed_configuration_error():
    with pytest.raises(LLMServiceError) as caught:
        LLMClient(Settings())
    assert caught.value.error.code == "configuration"
    assert "GROQ_API_KEY" in caught.value.error.next_step


def test_chat_uses_primary_model_once():
    async def run():
        llm, requests = client_for([completion("  A short answer.  ")])
        async with llm:
            assert await llm.chat(MESSAGES) == "A short answer."
        assert llm.client.is_closed()
        assert [request["model"] for request in requests] == [PRIMARY]
        assert "response_format" not in requests[0]

    asyncio.run(run())


def test_production_client_uses_official_route_and_handles_malformed_http_json(monkeypatch):
    urls = []

    async def handle(request):
        urls.append(str(request.url))
        if len(urls) == 1:
            return httpx.Response(200, headers={"content-type": "application/json"}, content=b"broken JSON")
        return completion("Recovered")

    async def run():
        transport = httpx.MockTransport(handle)
        monkeypatch.setattr("core.llm.AsyncGroq", partial(AsyncGroq, http_client=httpx.AsyncClient(transport=transport)))
        settings = Settings(groq_api_key="test-placeholder")
        async with LLMClient(settings) as llm:
            assert llm.client.max_retries == 0
            assert await llm.chat(MESSAGES) == "Recovered"
        assert urls == ["https://api.groq.com/openai/v1/chat/completions"] * 2

    asyncio.run(run())


def test_structured_primary_repairs_syntax_without_changing_quoted_data_or_retrying():
    async def run():
        note = 'Preserve ,} and ",] inside the note.'
        payload = json.dumps({"count": 2, "note": note})[:-1] + ",}"
        llm, requests = client_for([completion(f"```json\n{payload}\n```")])
        async with llm:
            assert await llm.structured_chat(MESSAGES, Answer) == Answer(count=2, note=note)
        assert [request["model"] for request in requests] == [PRIMARY]
        fmt = requests[0]["response_format"]
        assert fmt == {"type": "json_schema", "json_schema": {
            "name": "Answer", "strict": False, "schema": Answer.model_json_schema(),
        }}
        assert "tools" not in requests[0]

    asyncio.run(run())


def test_repairs_groq_rejected_generation_before_another_request():
    async def run():
        llm, requests = client_for([error(400, code="json_validate_failed", failed_generation='{"count":2,"note":"ok",}')])
        async with llm:
            assert await llm.structured_chat(MESSAGES, Answer) == Answer(count=2, note="ok")
        assert len(requests) == 1

    asyncio.run(run())


def test_short_reasoning_budget_is_sent_only_to_known_gpt_oss_models():
    async def run():
        response = '{"count":2,"note":"ok"}'
        llm, requests = client_for([completion(response), completion(response)])
        async with llm:
            for model in (PRIMARY, "configured-model-override"):
                await llm.structured_chat(MESSAGES, Answer, model=model, single_attempt=True, reasoning_effort="low")
        assert requests[0]["reasoning_effort"] == "low"
        assert "reasoning_effort" not in requests[1]

    asyncio.run(run())


@pytest.mark.parametrize("invalid", ['{"count":', '{"count":"2","note":"no coercion"}', '{"count":2}'])
def test_invalid_structure_retries_then_falls_back(invalid):
    async def run():
        llm, requests = client_for([
            completion(invalid), completion(invalid), completion('{"count":2,"note":"fallback"}'),
        ])
        async with llm:
            assert await llm.structured_chat(MESSAGES, Answer) == Answer(count=2, note="fallback")
        assert [request["model"] for request in requests] == [PRIMARY, PRIMARY, FALLBACK]

    asyncio.run(run())


def test_rate_limit_honors_retry_after_then_falls_back(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("core.llm.AsyncRetrying", partial(AsyncRetrying, sleep=sleep))

    async def run():
        llm, requests = client_for([error(429, retry_after=1), error(503), completion("fallback")])
        async with llm:
            assert await llm.chat(MESSAGES) == "fallback"
        assert [request["model"] for request in requests] == [PRIMARY, PRIMARY, FALLBACK]
        sleep.assert_awaited_once_with(1.0)

    asyncio.run(run())


def test_long_rate_limit_skips_same_model_retries_and_preserves_terminal_status():
    async def run():
        llm, requests = client_for([error(429, retry_after=60), error(429, retry_after=60)])
        async with llm:
            with pytest.raises(LLMServiceError) as caught:
                await llm.chat(MESSAGES)
        assert [request["model"] for request in requests] == [PRIMARY, FALLBACK]
        assert caught.value.error.code == "rate_limit"
        assert caught.value.http_status == 429

    asyncio.run(run())


@pytest.mark.parametrize("status, code", [(401, "authentication"), (403, "authentication"), (400, "configuration"), (404, "configuration")])
def test_terminal_http_errors_do_not_retry_fall_back_or_expose_body(status, code):
    async def run():
        llm, requests = client_for([error(status)])
        async with llm:
            with pytest.raises(LLMServiceError) as caught:
                await llm.structured_chat(MESSAGES, Answer)
        assert [request["model"] for request in requests] == [PRIMARY]
        assert caught.value.error.code == code
        assert caught.value.http_status == status
        assert not caught.value.error.retryable
        assert caught.value.error.next_step
        assert "private-provider-body" not in str(caught.value)

    asyncio.run(run())


def test_request_timeout_is_bounded_and_exhausts_both_model_budgets():
    async def stall():
        await asyncio.Future()

    async def run():
        llm, requests = client_for([stall] * 4, groq_timeout_seconds=0.01)
        async with llm:
            with pytest.raises(LLMServiceError) as caught:
                await asyncio.wait_for(llm.chat(MESSAGES), timeout=2)
        assert [request["model"] for request in requests] == [PRIMARY, PRIMARY, FALLBACK, FALLBACK]
        assert caught.value.error.code == "timeout"

    asyncio.run(run())


def test_exhausted_invalid_responses_remain_typed():
    async def run():
        llm, requests = client_for([
            httpx.Response(200, json={"unexpected": "response envelope"}), completion(None),
            completion('{"count":2,"note":"truncated"}', finish_reason="length"), completion("private output"),
        ])
        async with llm:
            with pytest.raises(LLMServiceError) as caught:
                await llm.structured_chat(MESSAGES, Answer)
        assert [request["model"] for request in requests] == [PRIMARY, PRIMARY, FALLBACK, FALLBACK]
        assert caught.value.error.code == "invalid_response"
        assert "private output" not in str(caught.value)

    asyncio.run(run())


@pytest.mark.parametrize("model", [PRIMARY, FALLBACK])
def test_independent_model_check_cannot_retry_or_fall_back(model):
    async def run():
        llm, requests = client_for([error(503)])
        async with llm:
            with pytest.raises(LLMServiceError) as caught:
                await llm.structured_chat(MESSAGES, Answer, model=model, single_attempt=True)
        assert [request["model"] for request in requests] == [model]
        assert caught.value.error.code == "unavailable"

    asyncio.run(run())
