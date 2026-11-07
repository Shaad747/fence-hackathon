"""Live retain/recall smoke check. No fake retrieval or local evidence fallback."""

import asyncio
import json
import sys
from time import monotonic

from core.config import ConfigurationError, load_settings
from core.memory import DECISION_PREFIX, MemoryClient, MemoryServiceError
from seed.seed import load_decisions

LOTUS_ID = "kp-2023-project-lotus"
QUERY = "What happened when Project Lotus removed Kaveri Pay's free merchant tier in Q3 2023? Include churn, timing, support capacity, and the competitor campaign."


async def check_memory() -> dict:
    lotus = next(d for d in load_decisions() if d.id == LOTUS_ID)
    started = monotonic()
    async with MemoryClient(load_settings()) as memory:
        receipt = await memory.retain_decision(lotus)
        recalled = await memory.recall_for_proposal(QUERY)
        matches = [item for item in recalled if item.document_id == f"{DECISION_PREFIX}{LOTUS_ID}"]
        evidence = " ".join(f"{item.evidence_text} {item.source_text or ''}" for item in matches).lower()
        checks = {
            "lotus_source_recalled": bool(matches),
            "31_percent_churn": "31%" in evidence or "31 percent" in evidence,
            "six_weeks": "six weeks" in evidence or "6 weeks" in evidence,
            "support_capacity": "support" in evidence and "migration" in evidence,
            "competitor_campaign": "competitor" in evidence and "campaign" in evidence,
        }
        return {
            "mode": "live", "passed": all(checks.values()), "checks": checks,
            "retain_status": receipt.status,
            "recalled_fact_count": len(recalled),
            "recalled_decision_document_count": len({m.document_id for m in recalled if m.document_id}),
            "lotus_memory_ids": [m.memory_id for m in matches],
            "ranking_label": "Relative ranking signal",
            "elapsed_seconds": round(monotonic() - started, 2),
            "activity": memory.activity_summary(),
        }


def main() -> int:
    try:
        result = asyncio.run(check_memory())
        print(json.dumps(result, indent=2))
        if not result["passed"]:
            print("Lotus evidence was incomplete. Inspect the source document in Hindsight, then rerun the smoke check.", file=sys.stderr)
        return 0 if result["passed"] else 1
    except MemoryServiceError as exc:
        print(json.dumps(exc.error.model_dump()), file=sys.stderr)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
