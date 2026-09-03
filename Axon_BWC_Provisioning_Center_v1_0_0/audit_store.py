"""Append-only, hash-chained local audit store for the standalone desktop suite."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime_paths import audit_database_path, ensure_private_file


SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    component TEXT NOT NULL,
    event_type TEXT NOT NULL,
    outcome TEXT NOT NULL,
    details_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_audit_events_time ON audit_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_events_component ON audit_events(component, event_type);
"""


def _canonical_event(
    occurred_at: str,
    component: str,
    event_type: str,
    outcome: str,
    details_json: str,
    previous_hash: str,
) -> bytes:
    return "\n".join(
        (occurred_at, component, event_type, outcome, details_json, previous_hash)
    ).encode("utf-8")


def _connect(path: Path | None = None) -> sqlite3.Connection:
    database = path or audit_database_path()
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database, timeout=15)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(SCHEMA)
    ensure_private_file(database)
    return connection


def append_event(
    component: str,
    event_type: str,
    outcome: str,
    details: dict[str, Any] | None = None,
    *,
    path: Path | None = None,
) -> str:
    occurred_at = datetime.now(timezone.utc).isoformat()
    details_json = json.dumps(details or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    connection = _connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = str(row[0]) if row else "GENESIS"
        event_hash = hashlib.sha256(
            _canonical_event(
                occurred_at,
                component,
                event_type,
                outcome,
                details_json,
                previous_hash,
            )
        ).hexdigest()
        connection.execute(
            """
            INSERT INTO audit_events
            (occurred_at, component, event_type, outcome, details_json, previous_hash, event_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                occurred_at,
                component,
                event_type,
                outcome,
                details_json,
                previous_hash,
                event_hash,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return event_hash


def verify_chain(*, path: Path | None = None) -> dict[str, Any]:
    database = path or audit_database_path()
    if not database.exists():
        return {"valid": True, "events": 0, "firstInvalidSequence": None}
    previous_hash = "GENESIS"
    count = 0
    connection = _connect(database)
    try:
        rows = connection.execute(
            """
            SELECT sequence, occurred_at, component, event_type, outcome,
                   details_json, previous_hash, event_hash
            FROM audit_events ORDER BY sequence
            """
        ).fetchall()
    finally:
        connection.close()
    for row in rows:
        sequence, occurred_at, component, event_type, outcome, details_json, stored_previous, stored_hash = row
        expected = hashlib.sha256(
            _canonical_event(
                occurred_at,
                component,
                event_type,
                outcome,
                details_json,
                previous_hash,
            )
        ).hexdigest()
        if stored_previous != previous_hash or stored_hash != expected:
            return {
                "valid": False,
                "events": count,
                "firstInvalidSequence": int(sequence),
            }
        previous_hash = stored_hash
        count += 1
    return {"valid": True, "events": count, "firstInvalidSequence": None}
