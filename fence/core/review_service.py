"""Synchronous Streamlit bridge with cached clients on one stable worker loop."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from core.config import Settings
from core.llm import LLMClient
from core.memory import MemoryClient, MemoryServiceError
from core.pipeline import check_proposal
from core.schemas import Activity, DocumentSnapshot, PipelineResult


@dataclass
class ReviewRun:
    result: PipelineResult
    documents: list[DocumentSnapshot] | None
    activity: list[Activity]
    snapshot_error: str | None = None


class ReviewService:
    def __init__(self, settings: Settings):
        self.settings = settings
        # One worker per Streamlit session keeps client connections on their original loop.
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fence-review")
        self.runner = None
        self.memory = None
        self.llm = None

    async def _review(self, text: str) -> ReviewRun:
        if self.llm is None:
            self.llm = LLMClient(self.settings)
        if self.memory is None:
            self.memory = MemoryClient(self.settings)
        self.memory.activity.clear()
        result = await check_proposal(text, self.memory, self.llm)
        documents, error = None, None
        try:
            async with asyncio.timeout(8):
                documents = await self.memory.decision_snapshot()
        except (MemoryServiceError, TimeoutError):
            error = "The retained archive count is unavailable. The review above is still available."
        return ReviewRun(result, documents, list(self.memory.activity), error)

    def _run(self, text: str) -> ReviewRun:
        if self.runner is None:
            self.runner = asyncio.Runner()
        return self.runner.run(self._review(text))

    def review(self, text: str) -> ReviewRun:
        return self.worker.submit(self._run, text).result()

    def save_outcome(self, outcome):
        return self._memory_call("log_outcome", outcome)

    def save_feedback(self, feedback):
        return self._memory_call("log_feedback", feedback)

    def read_feedback(self):
        return self._memory_call("feedback_records")

    def reflect(self, outcomes):
        return self._memory_call("reflect_history", outcomes)

    def _memory_call(self, method, *args):
        async def save():
            if self.memory is None:
                self.memory = MemoryClient(self.settings)
            async with asyncio.timeout(self.settings.hindsight_operation_timeout_seconds):
                if method == "reflect_history":
                    from core.reflection import reflect_history
                    return await reflect_history(self.memory, *args)
                return await getattr(self.memory, method)(*args)

        def run():
            if self.runner is None:
                self.runner = asyncio.Runner()
            return self.runner.run(save())

        return self.worker.submit(run).result()

    def close(self) -> None:
        async def cleanup():
            if self.memory:
                await self.memory.client.aclose()
            if self.llm:
                await self.llm.aclose()

        def finish():
            if self.runner:
                self.runner.run(cleanup())
                self.runner.close()

        self.worker.submit(finish).result()
        self.worker.shutdown()
