"""Append-only local audit logging.

Every consequential CLI command writes one row here. This is local
SQLite, inspected via `firm-ai audit`, not an external log sink. Never
log secrets or full document text -- only structured, truncated request
metadata and document ids (already non-secret citation metadata).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

AUDIT_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    user_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    command TEXT NOT NULL,
    request_summary TEXT NOT NULL,
    document_ids TEXT NOT NULL,
    tools_invoked TEXT NOT NULL,
    validation_result TEXT NOT NULL,
    approval_state TEXT NOT NULL,
    outcome TEXT NOT NULL,
    error_category TEXT
)
"""

REQUEST_SUMMARY_MAX_CHARS = 200


class AuditEvent(BaseModel):
    user_id: str
    command: str
    request_summary: str
    document_ids: list[str] = []
    tools_invoked: list[str] = []
    validation_result: str = "ok"
    approval_state: str = "not_required"
    outcome: str
    error_category: str | None = None


def init_audit_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(AUDIT_TABLE_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def log_event(db_path: Path, event: AuditEvent) -> str:
    """Write one audit event. Returns the generated event_id."""
    init_audit_db(db_path)
    event_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO audit_events "
            "(event_id, created_at, user_id, request_id, command, request_summary, "
            "document_ids, tools_invoked, validation_result, approval_state, outcome, "
            "error_category) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                datetime.now(UTC).isoformat(),
                event.user_id,
                request_id,
                event.command,
                event.request_summary[:REQUEST_SUMMARY_MAX_CHARS],
                json.dumps(event.document_ids),
                json.dumps(event.tools_invoked),
                event.validation_result,
                event.approval_state,
                event.outcome,
                event.error_category,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return event_id


def read_recent_events(db_path: Path, limit: int = 20) -> list[dict]:
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]
