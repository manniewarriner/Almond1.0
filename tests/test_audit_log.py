"""Tests for app.audit.log: append-only local audit event storage."""

from __future__ import annotations

from app.audit.log import AuditEvent, init_audit_db, log_event, read_recent_events


def test_init_audit_db_creates_table(tmp_path):
    db_path = tmp_path / "audit.db"

    init_audit_db(db_path)

    assert db_path.is_file()


def test_log_event_and_read_back(tmp_path):
    db_path = tmp_path / "audit.db"
    event = AuditEvent(
        user_id="alice",
        command="search",
        request_summary="KYC verification",
        document_ids=["abc123"],
        outcome="ok",
    )

    event_id = log_event(db_path, event)

    events = read_recent_events(db_path)
    assert len(events) == 1
    assert events[0]["event_id"] == event_id
    assert events[0]["user_id"] == "alice"
    assert events[0]["outcome"] == "ok"


def test_read_recent_events_missing_db_returns_empty(tmp_path):
    assert read_recent_events(tmp_path / "missing.db") == []


def test_read_recent_events_respects_limit(tmp_path):
    db_path = tmp_path / "audit.db"
    for i in range(5):
        log_event(
            db_path,
            AuditEvent(user_id="u", command="search", request_summary=str(i), outcome="ok"),
        )

    events = read_recent_events(db_path, limit=2)

    assert len(events) == 2


def test_request_summary_is_truncated(tmp_path):
    db_path = tmp_path / "audit.db"
    long_text = "x" * 1000

    log_event(
        db_path,
        AuditEvent(user_id="u", command="search", request_summary=long_text, outcome="ok"),
    )

    events = read_recent_events(db_path)
    assert len(events[0]["request_summary"]) == 200
