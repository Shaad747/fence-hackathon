"""Send one small structured request to each configured Groq model."""

import asyncio
from time import monotonic
from typing import Literal

from core.config import ConfigurationError, load_settings
from core.llm import LLMClient, LLMServiceError
from core.schemas import Record


class Probe(Record):
    ok: Literal[True]


async def check() -> int:
    settings = load_settings()
    failed = False
    async with LLMClient(settings) as llm:
        for label, model in (("primary", settings.groq_primary_model), ("fallback", settings.groq_fallback_model)):
            started = monotonic()
            try:
                await llm.structured_chat(
                    [{"role": "user", "content": 'Return only the JSON object {"ok":true}.'}], Probe,
                    model=model, single_attempt=True, max_completion_tokens=128,
                )
            except LLMServiceError as exc:
                http = f" (HTTP {exc.http_status})" if exc.http_status is not None else ""
                print(f"Groq {label} failed [{exc.error.code}]{http}. {exc}")
                failed = True
            else:
                print(f"Groq {label} passed Pydantic validation in {monotonic() - started:.2f}s.")
    return int(failed)


def main() -> int:
    try:
        return asyncio.run(check())
    except (ConfigurationError, LLMServiceError) as exc:
        print(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
