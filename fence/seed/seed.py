"""Validate locally, or retain the reviewed archive without a Groq call."""

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from pydantic import TypeAdapter

from core.config import ConfigurationError, load_settings
from core.memory import DECISION_PREFIX, MemoryClient, MemoryServiceError
from core.schemas import Decision, RetainReceipt

SEED_PATH = Path(__file__).with_name("seed_data.json")


def load_decisions(path: Path = SEED_PATH) -> list[Decision]:
    decisions = TypeAdapter(list[Decision]).validate_json(path.read_text(encoding="utf-8"))
    if len({decision.id for decision in decisions}) != len(decisions):
        raise ValueError("Seed decision IDs must be unique.")
    if not decisions:
        raise ValueError("The seed archive must not be empty.")
    return decisions


async def seed_archive(memory: MemoryClient, decisions: list[Decision]) -> list[RetainReceipt]:
    # Seed before the demo timer. Serial ingestion avoids flooding a small local server.
    return [await memory.retain_decision(decision) for decision in decisions]


async def run_seed(decisions: list[Decision], verify: bool) -> dict:
    async with MemoryClient(load_settings()) as memory:
        receipts = await seed_archive(memory, decisions)
        first = await memory.decision_snapshot()
        expected = {f"{DECISION_PREFIX}{decision.id}" for decision in decisions}
        actual = {document.document_id for document in first}
        if not expected <= actual or len(actual) != len(first):
            raise ValueError("Seed verification failed: expected source documents are missing or duplicated.")
        result = {
            "mode": "live", "bank": memory.settings.hindsight_bank_id,
            "decisions": len(decisions), "first_pass": dict(Counter(r.status for r in receipts)),
            "retained_decision_documents": len(first),
            "extracted_facts": sum(d.memory_unit_count for d in first),
        }
        if verify:
            second_pass = await seed_archive(memory, decisions)
            second = await memory.decision_snapshot()
            if first != second or any(r.status != "unchanged" for r in second_pass):
                raise ValueError("Reseed verification failed: documents or fact counts changed.")
            result.update(idempotency="passed", second_pass=dict(Counter(r.status for r in second_pass)))
        result["activity"] = memory.activity_summary()
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Validate checked-in records; make no API calls.")
    parser.add_argument("--verify-idempotency", action="store_true", help="Seed twice and compare live source documents and fact counts.")
    args = parser.parse_args()
    try:
        decisions = load_decisions()
        if args.dry_run:
            print(json.dumps({"mode": "offline validation", "decisions": len(decisions),
                              "unique_ids": len({d.id for d in decisions}), "api_calls": 0,
                              "illustrative": True}))
        else:
            print(json.dumps(asyncio.run(run_seed(decisions, args.verify_idempotency)), indent=2))
        return 0
    except MemoryServiceError as exc:
        print(json.dumps(exc.error.model_dump()), file=sys.stderr)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
    except (ValueError, OSError):
        print("Seed validation or verification failed. Check seed/seed_data.json and rerun tests; no success is assumed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
