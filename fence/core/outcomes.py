"""Durable immutable submission queue; only Hindsight acknowledgement confirms a save."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from core.schemas import Outcome, PipelineResult, RetainReceipt


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def report_reference(result: PipelineResult) -> str:
    return 'report-' + digest({'proposal': result.proposal.original_input,
                              'report': result.report.model_dump(mode='json'),
                              'evidence': sorted(item.memory.memory_id for item in result.evidence)})


class OutcomeQueue:
    table = "outcomes"
    model = Outcome
    kind = "outcome"

    def __init__(self, path: Path, workspace: str):
        self.path, self.workspace = path, workspace
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute(f'CREATE TABLE IF NOT EXISTS {self.table} (workspace TEXT, event_id TEXT, payload TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(workspace, event_id))')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def prepare(self, result: PipelineResult, status: str, notes: str) -> Outcome:
        ids = sorted({item.memory.memory_id for item in result.evidence})
        if not set(result.citation_ids) <= set(ids):
            raise ValueError('The report has unsupported evidence references. Run a new check before recording an outcome.')
        data = dict(proposal_reference='proposal-' + digest(result.proposal.original_input),
                    report_reference=report_reference(result), proposal_text=result.proposal.original_input,
                    memory_ids=ids, citation_ids=sorted(set(result.citation_ids)), status=status, reason=notes.strip())
        # Validate before creating a durable record. Identical submissions converge across sessions.
        event = Outcome(**data, event_id='outcome-' + digest(data), timestamp=datetime.now(timezone.utc))
        return self.enqueue(event)

    def enqueue(self, event):
        with self.connect() as db:
            db.execute(f'INSERT OR IGNORE INTO {self.table}(workspace,event_id,payload) VALUES (?,?,?)',
                       (self.workspace, event.event_id, event.model_dump_json()))
            payload = db.execute(f'SELECT payload FROM {self.table} WHERE workspace=? AND event_id=?',
                                 (self.workspace, event.event_id)).fetchone()[0]
        return self.model.model_validate_json(payload)

    def records(self):
        with self.connect() as db:
            rows = db.execute(f'SELECT payload,confirmed FROM {self.table} WHERE workspace=? ORDER BY rowid DESC',
                              (self.workspace,)).fetchall()
        return [(self.model.model_validate_json(payload), bool(saved)) for payload, saved in rows]

    def confirm(self, event: Outcome, receipt: RetainReceipt):
        if receipt.document_id != f'fence:{self.kind}:{event.event_id}':
            raise ValueError('The outcome receipt does not match the submitted record.')
        with self.connect() as db:
            changed = db.execute(f'UPDATE {self.table} SET confirmed=1 WHERE workspace=? AND event_id=? AND payload=?',
                                 (self.workspace, event.event_id, event.model_dump_json())).rowcount
            if changed != 1:
                raise ValueError('The queued outcome no longer matches this submission.')

    def confirmed(self, event: Outcome) -> bool:
        return any(item.event_id == event.event_id and saved for item, saved in self.records())
