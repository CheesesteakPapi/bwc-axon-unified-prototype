"""Shared, revision-aware SQLite workspace for the BWC Axon prototype.

The database contains normalized snapshots and proposed changes only. Axon
credentials and raw API responses are deliberately outside this module.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any, Iterator, Sequence


RUN_STATES = {
    "Draft",
    "Enriching",
    "Needs Review",
    "Ready for Preview",
    "Previewed",
    "Awaiting Submission",
    "Submitted",
    "Monitoring",
    "Completed",
    "Failed",
}
PENDING_STATES = {
    "Confirmed",
    "Proposed creation",
    "Proposed update",
    "Submitted—awaiting confirmation",
    "Failed",
    "Superseded",
}


class RevisionConflict(RuntimeError):
    """Raised when the caller edits a stale workspace or run revision."""


class RefreshLeaseConflict(RuntimeError):
    """Raised when another process already owns a resource refresh lease."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def value_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def workspace_path() -> Path:
    override = os.environ.get("BWC_SHARED_WORKSPACE_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    data_root_override = os.environ.get("BWC_AXON_DATA_ROOT", "").strip()
    if data_root_override:
        return Path(data_root_override).expanduser().resolve() / "shared" / "shared_workspace.sqlite3"
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path.home() / "Library" / "Application Support"
    return base / "ICE" / "BWC Axon Operations" / "shared" / "shared_workspace.sqlite3"


def safe_csv_value(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


class SharedWorkspace:
    """Thread-safe connection factory and data contract for both local apps."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or workspace_path()).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._lease_stops: dict[str, threading.Event] = {}
        self._initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self.connection() as db:
            db.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = FULL;
                CREATE TABLE IF NOT EXISTS workspace_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT OR IGNORE INTO workspace_meta(key, value) VALUES ('revision', '0');
                INSERT OR IGNORE INTO workspace_meta(key, value) VALUES ('schema_version', '3.1.0');

                CREATE TABLE IF NOT EXISTS resource_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    resource TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    pulled_at TEXT NOT NULL,
                    activated_at TEXT,
                    superseded_at TEXT,
                    source TEXT NOT NULL DEFAULT 'Axon API'
                );
                CREATE INDEX IF NOT EXISTS idx_snapshots_active
                    ON resource_snapshots(resource, scope_key, status, activated_at DESC);
                CREATE TABLE IF NOT EXISTS snapshot_rows (
                    snapshot_id TEXT NOT NULL REFERENCES resource_snapshots(snapshot_id) ON DELETE CASCADE,
                    row_index INTEGER NOT NULL,
                    record_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(snapshot_id, row_index)
                );
                CREATE TABLE IF NOT EXISTS user_device_relationships (
                    snapshot_id TEXT NOT NULL REFERENCES resource_snapshots(snapshot_id) ON DELETE CASCADE,
                    row_index INTEGER NOT NULL,
                    device_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    assignment_state TEXT NOT NULL,
                    device_status TEXT NOT NULL,
                    device_model TEXT NOT NULL,
                    device_home TEXT NOT NULL,
                    PRIMARY KEY(snapshot_id, row_index)
                );

                CREATE TABLE IF NOT EXISTS refresh_leases (
                    resource TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    scope_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS refresh_history (
                    refresh_id TEXT PRIMARY KEY,
                    resource TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    snapshot_id TEXT,
                    message TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS provisioning_runs (
                    run_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    rows_json TEXT NOT NULL,
                    validation_json TEXT NOT NULL,
                    generation_json TEXT NOT NULL,
                    approval_json TEXT NOT NULL,
                    active_snapshot_ids_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provisioning_revisions (
                    run_id TEXT NOT NULL REFERENCES provisioning_runs(run_id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    PRIMARY KEY(run_id, revision)
                );
                CREATE TABLE IF NOT EXISTS pending_overlays (
                    overlay_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES provisioning_runs(run_id) ON DELETE CASCADE,
                    run_revision INTEGER NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_key TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_pending_entity
                    ON pending_overlays(entity_type, state, updated_at DESC);
                CREATE TABLE IF NOT EXISTS submission_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES provisioning_runs(run_id) ON DELETE CASCADE,
                    run_revision INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    row_ids_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    dependency_chunk_ids_json TEXT NOT NULL,
                    axon_job_id TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(run_id, run_revision, kind, ordinal)
                );

                CREATE TABLE IF NOT EXISTS governance_datasets (
                    dataset_key TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    headers_json TEXT NOT NULL,
                    rows_json TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    migrated_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS governance_history (
                    history_id TEXT PRIMARY KEY,
                    dataset_key TEXT NOT NULL,
                    row_key TEXT NOT NULL,
                    expected_revision INTEGER NOT NULL,
                    new_revision INTEGER NOT NULL,
                    prior_json TEXT NOT NULL,
                    current_json TEXT NOT NULL,
                    mapping_method TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    review_notes TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    changed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL
                );
                """
            )
            db.execute("BEGIN IMMEDIATE")
            if "refresh_id" not in {row[1] for row in db.execute("PRAGMA table_info(refresh_leases)")}:
                db.execute("ALTER TABLE refresh_leases ADD COLUMN refresh_id TEXT NOT NULL DEFAULT ''")
            self._audit_in_connection(db, "workspace", "workspace-opened", "success", {"schema": "3.1.0"})
            db.commit()

    def _workspace_revision(self, db: sqlite3.Connection) -> int:
        return int(db.execute("SELECT value FROM workspace_meta WHERE key='revision'").fetchone()[0])

    def revision(self) -> int:
        with self.connection() as db:
            return self._workspace_revision(db)

    def _increment_revision(self, db: sqlite3.Connection) -> int:
        revision = self._workspace_revision(db) + 1
        db.execute("UPDATE workspace_meta SET value=? WHERE key='revision'", (str(revision),))
        return revision

    def _audit_in_connection(
        self,
        db: sqlite3.Connection,
        actor: str,
        event_type: str,
        outcome: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        previous = db.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
        previous_hash = previous[0] if previous else "0" * 64
        created_at = utc_now()
        event_id = uuid.uuid4().hex
        safe_details = details or {}
        material = canonical_json(
            {
                "eventId": event_id,
                "createdAt": created_at,
                "actor": actor,
                "eventType": event_type,
                "outcome": outcome,
                "details": safe_details,
                "previousHash": previous_hash,
            }
        )
        event_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()
        db.execute(
            "INSERT INTO audit_events(event_id,created_at,actor,event_type,outcome,details_json,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?)",
            (event_id, created_at, actor, event_type, outcome, canonical_json(safe_details), previous_hash, event_hash),
        )

    def audit(self, actor: str, event_type: str, outcome: str, details: dict[str, Any] | None = None) -> None:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._audit_in_connection(db, actor, event_type, outcome, details)
            db.commit()

    def verify_audit_chain(self) -> dict[str, Any]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM audit_events ORDER BY sequence").fetchall()
        prior = "0" * 64
        for row in rows:
            material = canonical_json(
                {
                    "eventId": row["event_id"],
                    "createdAt": row["created_at"],
                    "actor": row["actor"],
                    "eventType": row["event_type"],
                    "outcome": row["outcome"],
                    "details": json.loads(row["details_json"]),
                    "previousHash": row["previous_hash"],
                }
            )
            expected = hashlib.sha256(material.encode("utf-8")).hexdigest()
            if row["previous_hash"] != prior or row["event_hash"] != expected:
                return {"valid": False, "count": len(rows), "failedSequence": row["sequence"]}
            prior = row["event_hash"]
        return {"valid": True, "count": len(rows), "lastHash": prior}

    def acquire_refresh_lease(
        self,
        resource: str,
        owner_id: str,
        scope: dict[str, Any],
        ttl_seconds: int = 1800,
    ) -> str:
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z")
        refresh_id = uuid.uuid4().hex
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM refresh_leases WHERE resource=?", (resource,)).fetchone()
            if existing and existing["expires_at"] > utc_now():
                db.rollback()
                raise RefreshLeaseConflict(f"{resource} is already being refreshed by another local application.")
            db.execute("DELETE FROM refresh_leases WHERE resource=?", (resource,))
            db.execute(
                "INSERT INTO refresh_leases(resource,owner_id,acquired_at,expires_at,scope_json,refresh_id) VALUES(?,?,?,?,?,?)",
                (resource, owner_id, utc_now(), expires, canonical_json(scope), refresh_id),
            )
            db.execute(
                "INSERT INTO refresh_history(refresh_id,resource,owner_id,scope_json,status,started_at) VALUES(?,?,?,?,?,?)",
                (refresh_id, resource, owner_id, canonical_json(scope), "running", utc_now()),
            )
            self._audit_in_connection(db, owner_id, "refresh-lease-acquired", "success", {"resource": resource, "refreshId": refresh_id})
            db.commit()
        stop = threading.Event()
        self._lease_stops[refresh_id] = stop
        def heartbeat() -> None:
            try:
                while not stop.wait(max(0.05, min(30, ttl_seconds / 3))):
                    try:
                        self.renew_refresh_lease(resource, owner_id, refresh_id, ttl_seconds)
                    except Exception:
                        # Fail closed: activation checks ownership and expiry again.
                        return
            finally:
                self._lease_stops.pop(refresh_id, None)
        threading.Thread(target=heartbeat, name="bwc-refresh-lease", daemon=True).start()
        return refresh_id

    def renew_refresh_lease(self, resource: str, owner_id: str, refresh_id: str, ttl_seconds: int = 1800) -> None:
        expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z")
        with self.connection() as db:
            changed = db.execute(
                "UPDATE refresh_leases SET expires_at=? WHERE resource=? AND owner_id=? AND refresh_id=? AND expires_at>?",
                (expires, resource, owner_id, refresh_id, utc_now()),
            ).rowcount
        if changed != 1:
            raise RefreshLeaseConflict("Refresh ownership expired or changed. The prior baseline was preserved.")

    def tenant_status(self) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT value FROM workspace_meta WHERE key='tenant_host'").fetchone()
            legacy = db.execute("SELECT EXISTS(SELECT 1 FROM resource_snapshots) OR EXISTS(SELECT 1 FROM provisioning_runs)").fetchone()[0]
            return {"tenantHost": row[0] if row else "", "legacyBindingRequired": bool(legacy and not row), "workspaceRevision": self._workspace_revision(db)}

    def bind_tenant(self, url: str, *, confirm_legacy: bool = False, expected_revision: int | None = None) -> None:
        parsed = urlsplit(url.strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/") or parsed.port not in (None, 443):
            raise ValueError("Use a tenant HTTPS origin without credentials, path, query, or custom port.")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            bound = db.execute("SELECT value FROM workspace_meta WHERE key='tenant_host'").fetchone()
            if bound:
                if bound[0] != host:
                    raise ValueError("This workspace is bound to another Axon tenant. Use a separate workspace; existing data has not been changed.")
                return
            legacy = db.execute("SELECT EXISTS(SELECT 1 FROM resource_snapshots) OR EXISTS(SELECT 1 FROM provisioning_runs)").fetchone()[0]
            if legacy and (not confirm_legacy or expected_revision is None):
                raise ValueError("Existing local data has no tenant binding. In connection settings, confirm that this data belongs to the entered tenant before continuing.")
            if expected_revision is not None and self._workspace_revision(db) != int(expected_revision):
                raise RevisionConflict("Workspace changed. Reload connection settings before confirming its tenant.")
            db.execute("INSERT INTO workspace_meta(key,value) VALUES('tenant_host',?)", (host,))
            self._increment_revision(db)
            self._audit_in_connection(db, "local-operator", "tenant-bound", "success", {"legacyConfirmed": bool(legacy)})
            db.commit()

    def release_refresh_lease(self, resource: str, owner_id: str, refresh_id: str, status: str, message: str = "", snapshot_id: str = "") -> None:
        stop = self._lease_stops.pop(refresh_id, None)
        if stop:
            stop.set()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM refresh_leases WHERE resource=? AND owner_id=? AND refresh_id=?", (resource, owner_id, refresh_id))
            db.execute(
                "UPDATE refresh_history SET status=?,finished_at=?,snapshot_id=?,message=? WHERE refresh_id=?",
                (status, utc_now(), snapshot_id, message[:500], refresh_id),
            )
            self._audit_in_connection(db, owner_id, "refresh-finished", status, {"resource": resource, "refreshId": refresh_id, "snapshotId": snapshot_id})
            db.commit()

    def lease_status(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM refresh_leases ORDER BY resource").fetchall()
        return [{**dict(row), "scope": json.loads(row["scope_json"])} for row in rows]

    def activate_snapshot(
        self,
        resource: str,
        rows: Sequence[dict[str, Any]],
        scope: dict[str, Any] | None = None,
        source: str = "Axon API",
        *, lease_id: str = "",
    ) -> dict[str, Any]:
        return self.activate_snapshots_batch(
            [{"resource": resource, "rows": rows, "scope": scope, "source": source, "leaseId": lease_id}]
        )[0]

    def activate_snapshots_batch(
        self,
        entries: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Validate, stage, and activate resource snapshots in one transaction.

        Every resource activation retains the single-snapshot behavior, while
        the batch advances the shared workspace revision only once. If any
        staging, relationship, overlay-confirmation, or audit operation fails,
        no snapshot in the batch is activated.
        """
        if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)) or not entries:
            raise ValueError("Snapshot batch entries must be a non-empty sequence of objects.")

        prepared: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Snapshot batch entries must be objects.")
            if "resource" not in entry or "rows" not in entry:
                raise ValueError("Each snapshot batch entry must contain resource and rows.")
            resource = entry["resource"]
            rows = entry["rows"]
            if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("Snapshot rows must be a sequence of objects.")
            normalized_rows = list(rows)
            normalized_scope = entry.get("scope") or {"type": "full", "filters": {}}
            if normalized_scope.get("type") not in {"full", "filtered"} or not isinstance(normalized_scope.get("filters", {}), dict):
                raise ValueError("Snapshot scope must be full or filtered and contain an object of filters.")
            if normalized_rows:
                expected_schema = set(normalized_rows[0])
                if not expected_schema or any(set(row) != expected_schema for row in normalized_rows):
                    raise ValueError("Snapshot rows must share one non-empty normalized schema.")
            prepared.append(
                {
                    "resource": resource,
                    "rows": normalized_rows,
                    "scope": normalized_scope,
                    "source": entry.get("source", "Axon API"),
                    "scopeKey": value_hash(normalized_scope),
                    "snapshotId": uuid.uuid4().hex,
                    "pulledAt": utc_now(),
                    "sha256": value_hash(normalized_rows),
                    "leaseId": entry.get("leaseId", ""),
                }
            )

        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                for item in prepared:
                    lease = db.execute("SELECT refresh_id,expires_at FROM refresh_leases WHERE resource=?", (item["resource"],)).fetchone()
                    if item["leaseId"] or lease:
                        if not lease or lease["refresh_id"] != item["leaseId"] or lease["expires_at"] <= utc_now():
                            raise RefreshLeaseConflict("Snapshot activation rejected: refresh ownership is no longer valid.")
                    db.execute(
                        "INSERT INTO resource_snapshots(snapshot_id,resource,scope_key,scope_json,status,row_count,content_hash,pulled_at,source) VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            item["snapshotId"],
                            item["resource"],
                            item["scopeKey"],
                            canonical_json(item["scope"]),
                            "staging",
                            len(item["rows"]),
                            item["sha256"],
                            item["pulledAt"],
                            item["source"],
                        ),
                    )
                    self._stage_snapshot_rows(db, item["snapshotId"], item["resource"], item["rows"])
                    inserted = db.execute(
                        "SELECT COUNT(*) FROM snapshot_rows WHERE snapshot_id=?",
                        (item["snapshotId"],),
                    ).fetchone()[0]
                    if inserted != len(item["rows"]):
                        raise RuntimeError("Staged snapshot row count did not validate.")

                activated_at = utc_now()
                for item in prepared:
                    db.execute(
                        "UPDATE resource_snapshots SET status='superseded',superseded_at=? WHERE resource=? AND scope_key=? AND status='active'",
                        (activated_at, item["resource"], item["scopeKey"]),
                    )
                    db.execute(
                        "UPDATE resource_snapshots SET status='active',activated_at=? WHERE snapshot_id=?",
                        (activated_at, item["snapshotId"]),
                    )
                    item["confirmedUserOverlays"] = self._confirm_user_overlays(
                        db,
                        item["resource"],
                        item["scope"],
                        item["rows"],
                        activated_at,
                    )

                revision = self._increment_revision(db)
                for item in prepared:
                    self._audit_in_connection(
                        db,
                        "snapshot-service",
                        "snapshot-activated",
                        "success",
                        {
                            "resource": item["resource"],
                            "scope": item["scope"],
                            "rows": len(item["rows"]),
                            "snapshotId": item["snapshotId"],
                            "revision": revision,
                            "confirmedUserOverlays": item["confirmedUserOverlays"],
                        },
                    )
                db.commit()
            except Exception:
                db.rollback()
                raise

        return [
            {
                "snapshotId": item["snapshotId"],
                "resource": item["resource"],
                "scope": item["scope"],
                "rowCount": len(item["rows"]),
                "sha256": item["sha256"],
                "activatedAt": activated_at,
                "workspaceRevision": revision,
            }
            for item in prepared
        ]

    def _stage_snapshot_rows(
        self,
        db: sqlite3.Connection,
        snapshot_id: str,
        resource: str,
        rows: Sequence[dict[str, Any]],
    ) -> None:
        for index, row in enumerate(rows):
            key = str(row.get("id") or row.get("ID") or row.get("External ID") or row.get("EXTERNAL_ID") or index)
            db.execute(
                "INSERT INTO snapshot_rows(snapshot_id,row_index,record_key,payload_json) VALUES(?,?,?,?)",
                (snapshot_id, index, key, canonical_json(row)),
            )
            if resource == "Devices":
                user_id = str(row.get("Assigned User ID") or row.get("ownerId") or row.get("userId") or "").strip()
                db.execute(
                    "INSERT INTO user_device_relationships VALUES(?,?,?,?,?,?,?,?)",
                    (
                        snapshot_id,
                        index,
                        str(row.get("Axon Device ID") or row.get("id") or row.get("Serial Number") or index),
                        user_id,
                        "Assigned" if user_id else "Unassigned",
                        str(row.get("Device Status") or row.get("status2") or ""),
                        str(row.get("Device Model") or row.get("model") or ""),
                        str(row.get("Device Home Name (API)") or row.get("homeId") or ""),
                    ),
                )

    def _confirm_user_overlays(
        self, db: sqlite3.Connection, resource: str, scope: dict[str, Any],
        rows: Sequence[dict[str, Any]], activated_at: str,
    ) -> int:
        if resource != "Users" or scope.get("type") != "full":
            return 0
        aliases = {
            "email": ("Email", "EMAIL", "email"),
            "externalId": ("External ID", "EXTERNAL_ID", "externalId"),
            "role": ("Role", "ROLE", "role"),
            "status": ("User Status", "Status", "STATUS", "status"),
            "location": ("Location", "LOCATION", "location"),
            "supervisorEmail": ("Supervisor Email", "SUPERVISOR_EMAIL", "supervisorEmail"),
            "firstName": ("First Name", "FIRST_NAME", "firstName"),
            "lastName": ("Last Name", "LAST_NAME", "lastName"),
            "username": ("Username", "UserName", "USERNAME", "username"),
            "badgeNumber": ("Badge Number", "Badge ID", "BADGE_NUMBER", "badgeNumber"),
            "phone": ("Phone", "PHONE", "phone"),
            "rank": ("Rank", "RANK", "rank"),
        }
        def normalized(record, field):
            for key in aliases[field]:
                if key in record:
                    return str(record[key] or "").strip().casefold()
            return None
        email_index: dict[str, set[int]] = {}
        external_index: dict[str, set[int]] = {}
        for index, row in enumerate(rows):
            email_index.setdefault(normalized(row, "email"), set()).add(index)
            external_index.setdefault(normalized(row, "externalId"), set()).add(index)
        completed_rows: dict[tuple[str, int], set[str]] = {}
        overlays = db.execute("SELECT * FROM pending_overlays WHERE entity_type='User' AND state='Submitted—awaiting confirmation'").fetchall()
        count = 0
        for overlay in overlays:
            proposed = json.loads(overlay["payload_json"])
            run_key = (overlay["run_id"], overlay["run_revision"])
            if run_key not in completed_rows:
                chunks = db.execute("SELECT row_ids_json FROM submission_chunks WHERE run_id=? AND run_revision=? AND kind='users' AND status='completed'", run_key).fetchall()
                completed_rows[run_key] = {row_id for chunk in chunks for row_id in json.loads(chunk["row_ids_json"])}
            if proposed.get("rowId") not in completed_rows[run_key]:
                continue
            email = str(proposed.get("email") or "").strip().casefold()
            external_id = str(proposed.get("externalId") or "").strip().casefold()
            # Both identities must resolve uniquely to the same record.
            matches = email_index.get(email, set()) | external_index.get(external_id, set())
            if not email or not external_id or len(matches) != 1:
                continue
            current = rows[next(iter(matches))]
            if normalized(current, "email") != email or normalized(current, "externalId") != external_id:
                continue
            required = {field for field in aliases if str(proposed.get(field) or "").strip()}
            # Blank proposed values can be intentional updates and must reconcile too.
            difference_fields = {"Role": "role", "Location": "location", "Status": "status", "Supervisor Email": "supervisorEmail"}
            required.update(difference_fields[d["field"]] for d in proposed.get("differences", []) if d.get("field") in difference_fields)
            mismatched = [field for field in required if normalized(current, field) is not None and normalized(current, field) != str(proposed.get(field) or "").strip().casefold()]
            unobservable = [field for field in required if normalized(current, field) is None]
            proposed["confirmation"] = {"checkedAt": activated_at, "mismatchedFields": sorted(mismatched), "unobservableFields": sorted(unobservable), "jobCompleted": True}
            confirmed = not mismatched and not unobservable
            db.execute("UPDATE pending_overlays SET state=?,payload_json=?,updated_at=? WHERE overlay_id=?",
                       ("Confirmed" if confirmed else "Submitted—awaiting confirmation", canonical_json(proposed), activated_at, overlay["overlay_id"]))
            count += int(confirmed)
        return count

    def active_snapshot(self, resource: str, prefer_full: bool = True) -> dict[str, Any] | None:
        with self.connection() as db:
            snapshots = db.execute(
                "SELECT * FROM resource_snapshots WHERE resource=? AND status='active' ORDER BY activated_at DESC",
                (resource,),
            ).fetchall()
            selected = None
            if prefer_full:
                for item in snapshots:
                    if json.loads(item["scope_json"]).get("type") == "full":
                        selected = item
                        break
            selected = selected or (snapshots[0] if snapshots else None)
            if not selected:
                return None
            row_data = db.execute(
                "SELECT payload_json FROM snapshot_rows WHERE snapshot_id=? ORDER BY row_index",
                (selected["snapshot_id"],),
            ).fetchall()
        return {
            "snapshotId": selected["snapshot_id"],
            "resource": resource,
            "scope": json.loads(selected["scope_json"]),
            "rowCount": selected["row_count"],
            "sha256": selected["content_hash"],
            "activatedAt": selected["activated_at"],
            "source": selected["source"],
            "rows": [json.loads(row["payload_json"]) for row in row_data],
        }

    def read_operational_view(self) -> dict[str, Any]:
        """Read active snapshots, overlays, metadata, and revision atomically.

        A single SQLite read transaction prevents a multi-resource activation
        from becoming visible halfway through a dashboard response. The caller
        therefore receives either the complete pre-activation view or the
        complete post-activation view, with the matching workspace revision.
        """
        with self.connection() as db:
            db.execute("BEGIN")
            revision = self._workspace_revision(db)
            snapshot_records = db.execute(
                "SELECT snapshot_id,resource,scope_json,row_count,content_hash,activated_at,source "
                "FROM resource_snapshots WHERE status='active' "
                "ORDER BY resource,activated_at DESC"
            ).fetchall()
            snapshots: list[dict[str, Any]] = []
            metadata: list[dict[str, Any]] = []
            selected_records: list[sqlite3.Row] = []
            records_by_resource: dict[str, list[sqlite3.Row]] = {}
            for record in snapshot_records:
                records_by_resource.setdefault(record["resource"], []).append(record)
            for resource, resource_records in records_by_resource.items():
                selected = next(
                    (
                        record
                        for record in resource_records
                        if json.loads(record["scope_json"]).get("type") == "full"
                    ),
                    None,
                )
                if selected is None and resource == "Devices":
                    selected = resource_records[0]
                if selected is not None:
                    selected_records.append(selected)
            for record in snapshot_records:
                scope = json.loads(record["scope_json"])
                item = {
                    "snapshotId": record["snapshot_id"],
                    "resource": record["resource"],
                    "scope": scope,
                    "rowCount": record["row_count"],
                    "sha256": record["content_hash"],
                    "activatedAt": record["activated_at"],
                    "source": record["source"],
                }
                metadata.append(dict(item))
                if record not in selected_records:
                    continue
                row_data = db.execute(
                    "SELECT payload_json FROM snapshot_rows WHERE snapshot_id=? ORDER BY row_index",
                    (record["snapshot_id"],),
                ).fetchall()
                snapshots.append({**item, "rows": [json.loads(row["payload_json"]) for row in row_data]})
            overlay_rows = db.execute(
                "SELECT * FROM pending_overlays ORDER BY updated_at DESC"
            ).fetchall()
            overlays = [
                {
                    "overlayId": row["overlay_id"],
                    "runId": row["run_id"],
                    "runRevision": row["run_revision"],
                    "entityType": row["entity_type"],
                    "entityKey": row["entity_key"],
                    "state": row["state"],
                    "payload": json.loads(row["payload_json"]),
                    "updatedAt": row["updated_at"],
                }
                for row in overlay_rows
            ]
            db.commit()
        return {
            "workspaceRevision": revision,
            "snapshots": snapshots,
            "snapshotMetadata": metadata,
            "pendingOverlays": overlays,
        }

    def snapshot_metadata(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT snapshot_id,resource,scope_json,row_count,content_hash,activated_at,source FROM resource_snapshots WHERE status='active' ORDER BY resource,activated_at DESC"
            ).fetchall()
        return [
            {
                "snapshotId": row["snapshot_id"],
                "resource": row["resource"],
                "scope": json.loads(row["scope_json"]),
                "rowCount": row["row_count"],
                "sha256": row["content_hash"],
                "activatedAt": row["activated_at"],
                "source": row["source"],
            }
            for row in rows
        ]

    def active_user_device_relationships(self) -> list[dict[str, Any]]:
        snapshot = self.active_snapshot("Devices", prefer_full=True)
        if not snapshot:
            return []
        with self.connection() as db:
            rows = db.execute(
                "SELECT device_id,user_id,assignment_state,device_status,device_model,device_home FROM user_device_relationships WHERE snapshot_id=? ORDER BY row_index",
                (snapshot["snapshotId"],),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_run(self, title: str, provider: str, rows: list[dict[str, Any]], validation: dict[str, Any], generation: dict[str, Any], status: str) -> dict[str, Any]:
        if status not in RUN_STATES:
            raise ValueError("Invalid provisioning run state.")
        run_id = f"RUN-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6].upper()}"
        now = utc_now()
        active_ids = {item["resource"]: item["snapshotId"] for item in self.snapshot_metadata() if item["scope"].get("type") == "full"}
        record = {
            "runId": run_id,
            "revision": 1,
            "status": status,
            "createdAt": now,
            "updatedAt": now,
            "title": title or run_id,
            "provider": provider,
            "rows": rows,
            "validation": validation,
            "generation": generation,
            "approval": {},
            "activeSnapshotIds": active_ids,
        }
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO provisioning_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, 1, status, now, now, record["title"], provider, canonical_json(rows), canonical_json(validation), canonical_json(generation), "{}", canonical_json(active_ids)),
            )
            db.execute(
                "INSERT INTO provisioning_revisions VALUES(?,?,?,?,?,?,?)",
                (run_id, 1, "Run created and enriched", "Initial intake", "operator", now, canonical_json(record)),
            )
            self._replace_overlays(db, record)
            self._replace_chunks(db, record)
            revision = self._increment_revision(db)
            self._audit_in_connection(db, "provisioning-center", "run-created", "success", {"runId": run_id, "runRevision": 1, "workspaceRevision": revision, "rowCount": len(rows)})
            db.commit()
        record["workspaceRevision"] = revision
        return record

    def _decode_run(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "runId": row["run_id"],
            "revision": row["revision"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "title": row["title"],
            "provider": row["provider"],
            "rows": json.loads(row["rows_json"]),
            "validation": json.loads(row["validation_json"]),
            "generation": json.loads(row["generation_json"]),
            "approval": json.loads(row["approval_json"]),
            "activeSnapshotIds": json.loads(row["active_snapshot_ids_json"]),
        }

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM provisioning_runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError("Provisioning run was not found.")
            record = self._decode_run(row)
            revisions = db.execute(
                "SELECT revision,event_type,reason,actor,created_at FROM provisioning_revisions WHERE run_id=? ORDER BY revision DESC",
                (run_id,),
            ).fetchall()
            chunks = db.execute(
                "SELECT chunk_id,run_revision,kind,ordinal,row_ids_json,payload_hash,status,dependency_chunk_ids_json,axon_job_id,result_json FROM submission_chunks WHERE run_id=? AND run_revision=? ORDER BY kind,ordinal",
                (run_id, record["revision"]),
            ).fetchall()
            overlays = db.execute("SELECT state,payload_json FROM pending_overlays WHERE run_id=? AND run_revision=? AND entity_type='User'", (run_id, record["revision"])).fetchall()
        record["confirmationSummary"] = {
            "confirmed": sum(item["state"] == "Confirmed" for item in overlays),
            "awaiting": sum(item["state"] == "Submitted—awaiting confirmation" for item in overlays),
            "unobservableFields": sorted({field for item in overlays for field in json.loads(item["payload_json"]).get("confirmation", {}).get("unobservableFields", [])}),
            "mismatchedFields": sorted({field for item in overlays for field in json.loads(item["payload_json"]).get("confirmation", {}).get("mismatchedFields", [])}),
        }
        record["history"] = [
            {"revision": item["revision"], "event": item["event_type"], "reason": item["reason"], "actor": item["actor"], "createdAt": item["created_at"]}
            for item in revisions
        ]
        record["chunks"] = [
            {"chunkId": item["chunk_id"], "runRevision": item["run_revision"], "kind": item["kind"], "ordinal": item["ordinal"], "rowIds": json.loads(item["row_ids_json"]), "sha256": item["payload_hash"], "status": item["status"], "dependencies": json.loads(item["dependency_chunk_ids_json"]), "axonJobId": item["axon_job_id"], "result": json.loads(item["result_json"])}
            for item in chunks
        ]
        record["workspaceRevision"] = self.revision()
        return record

    def latest_run(self) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute("SELECT run_id FROM provisioning_runs ORDER BY updated_at DESC LIMIT 1").fetchone()
        return self.get_run(row[0]) if row else None

    def purge_run(self, run_id: str, expected_revision: int, actor: str = "operator") -> dict[str, Any]:
        """Remove one local run after exact-ID confirmation; retain a redacted audit event."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM provisioning_runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                db.rollback()
                raise KeyError("Provisioning run was not found.")
            if row["revision"] != int(expected_revision):
                db.rollback()
                raise RevisionConflict(f"Run revision {expected_revision} is stale; current revision is {row['revision']}.")
            if row["status"] in {"Submitted", "Monitoring"}:
                db.rollback()
                raise ValueError("A run with active or unconfirmed Axon jobs cannot be purged.")
            jobs = db.execute("SELECT COUNT(*) FROM submission_chunks WHERE run_id=? AND axon_job_id!=''", (run_id,)).fetchone()[0]
            details = {
                "runId": run_id,
                "runRevision": row["revision"],
                "rowCount": len(json.loads(row["rows_json"])),
                "userHash": json.loads(row["generation_json"]).get("userHash", ""),
                "groupHash": json.loads(row["generation_json"]).get("groupHash", ""),
                "recordedAxonJobCount": jobs,
            }
            db.execute("DELETE FROM provisioning_runs WHERE run_id=?", (run_id,))
            revision = self._increment_revision(db)
            self._audit_in_connection(db, actor, "provisioning-run-purged", "success", {**details, "workspaceRevision": revision})
            db.commit()
        return {**details, "workspaceRevision": revision}

    def revise_run(
        self,
        run_id: str,
        expected_revision: int,
        rows: list[dict[str, Any]],
        validation: dict[str, Any],
        generation: dict[str, Any],
        status: str,
        event_type: str,
        reason: str,
        actor: str = "operator",
        approval: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in RUN_STATES:
            raise ValueError("Invalid provisioning run state.")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current_row = db.execute("SELECT * FROM provisioning_runs WHERE run_id=?", (run_id,)).fetchone()
            if not current_row:
                db.rollback()
                raise KeyError("Provisioning run was not found.")
            current = self._decode_run(current_row)
            if current["revision"] != int(expected_revision):
                db.rollback()
                raise RevisionConflict(f"Run revision {expected_revision} is stale; current revision is {current['revision']}.")
            new_revision = current["revision"] + 1
            now = utc_now()
            record = {**current, "revision": new_revision, "status": status, "updatedAt": now, "rows": rows, "validation": validation, "generation": generation, "approval": approval or {}}
            db.execute(
                "UPDATE provisioning_runs SET revision=?,status=?,updated_at=?,rows_json=?,validation_json=?,generation_json=?,approval_json=? WHERE run_id=?",
                (new_revision, status, now, canonical_json(rows), canonical_json(validation), canonical_json(generation), canonical_json(record["approval"]), run_id),
            )
            db.execute(
                "INSERT INTO provisioning_revisions VALUES(?,?,?,?,?,?,?)",
                (run_id, new_revision, event_type, reason, actor, now, canonical_json(record)),
            )
            db.execute("UPDATE pending_overlays SET state='Superseded',updated_at=? WHERE run_id=? AND state NOT IN ('Failed','Superseded')", (now, run_id))
            self._replace_overlays(db, record)
            self._replace_chunks(db, record)
            workspace_revision = self._increment_revision(db)
            self._audit_in_connection(db, actor, "run-revised", "success", {"runId": run_id, "runRevision": new_revision, "workspaceRevision": workspace_revision, "event": event_type})
            db.commit()
        return self.get_run(run_id)

    def _replace_overlays(self, db: sqlite3.Connection, run: dict[str, Any]) -> None:
        now = utc_now()
        for row in run["rows"]:
            if row.get("validationState") == "Blocked":
                state = "Failed"
            else:
                state = "Proposed update" if row.get("existingAccount") else "Proposed creation"
            db.execute(
                "INSERT INTO pending_overlays VALUES(?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, run["runId"], run["revision"], "User", str(row.get("email") or row.get("rowId")), state, canonical_json(row), now, now),
            )
            if row.get("validationState") != "Blocked" and row.get("groupExternalId"):
                group_payload = {
                    "rowId": row.get("rowId", ""),
                    "email": row.get("email", ""),
                    "groupName": row.get("groupName", ""),
                    "groupExternalId": row.get("groupExternalId", ""),
                    "membershipType": row.get("membershipType", ""),
                }
                group_key = f"{row.get('groupExternalId', '')}:{row.get('email', '')}:{row.get('membershipType', '')}"
                db.execute(
                    "INSERT INTO pending_overlays VALUES(?,?,?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex, run["runId"], run["revision"], "GroupMembership", group_key, state, canonical_json(group_payload), now, now),
                )

    def _replace_chunks(self, db: sqlite3.Connection, run: dict[str, Any]) -> None:
        generation = run.get("generation") or {}
        user_chunk_ids: list[str] = []
        for kind, chunks in (("users", generation.get("userChunks", [])), ("groups", generation.get("groupChunks", []))):
            for ordinal, chunk in enumerate(chunks, start=1):
                chunk_id = f"{run['runId']}-R{run['revision']}-{kind.upper()}-{ordinal:03d}"
                dependencies = user_chunk_ids if kind == "groups" else []
                db.execute(
                    "INSERT INTO submission_chunks(chunk_id,run_id,run_revision,kind,ordinal,row_ids_json,payload_hash,status,dependency_chunk_ids_json) VALUES(?,?,?,?,?,?,?,?,?)",
                    (chunk_id, run["runId"], run["revision"], kind, ordinal, canonical_json(chunk.get("rowIds", [])), chunk.get("sha256") or value_hash(chunk.get("records", [])), "ready" if kind == "users" else "blocked-by-users", canonical_json(dependencies)),
                )
                if kind == "users":
                    user_chunk_ids.append(chunk_id)

    def approve_preview(self, run_id: str, expected_revision: int, approve_updates: bool, update_count: int) -> dict[str, Any]:
        current = self.get_run(run_id)
        if current["revision"] != int(expected_revision):
            raise RevisionConflict(f"Run revision {expected_revision} is stale; current revision is {current['revision']}.")
        if current["validation"].get("blockerCount", 0):
            raise ValueError("All blockers must be resolved before preview approval.")
        actual_updates = sum(1 for row in current["rows"] if row.get("existingAccount") and row.get("validationState") != "Blocked")
        if actual_updates and (not approve_updates or int(update_count) != actual_updates):
            raise ValueError("Approve the exact existing-account update count before continuing.")
        approval = {
            "approvedAt": utc_now(),
            "runId": run_id,
            "revision": expected_revision + 1,
            "updateCount": actual_updates,
            "userHash": current["generation"].get("userHash", ""),
            "groupHash": current["generation"].get("groupHash", ""),
            "snapshotIds": current["activeSnapshotIds"],
            "blockerCount": 0,
        }
        return self.revise_run(run_id, expected_revision, current["rows"], current["validation"], current["generation"], "Awaiting Submission", "Existing-account updates approved" if actual_updates else "Preview approved", f"Approved {actual_updates} existing-account updates; no Axon submission occurred", approval=approval)

    def pending_overlays(self, states: Sequence[str] | None = None) -> list[dict[str, Any]]:
        requested = list(states or ["Confirmed", "Proposed creation", "Proposed update", "Submitted—awaiting confirmation", "Failed", "Superseded"])
        placeholders = ",".join("?" for _ in requested)
        with self.connection() as db:
            rows = db.execute(
                f"SELECT * FROM pending_overlays WHERE state IN ({placeholders}) ORDER BY updated_at DESC", requested
            ).fetchall()
        return [{"overlayId": row["overlay_id"], "runId": row["run_id"], "runRevision": row["run_revision"], "entityType": row["entity_type"], "entityKey": row["entity_key"], "state": row["state"], "payload": json.loads(row["payload_json"]), "updatedAt": row["updated_at"]} for row in rows]

    def eligible_chunk(self, run_id: str, expected_revision: int) -> dict[str, Any] | None:
        run = self.get_run(run_id)
        if run["revision"] != int(expected_revision):
            raise RevisionConflict(f"Run revision {expected_revision} is stale; current revision is {run['revision']}.")
        user_pending = [chunk for chunk in run["chunks"] if chunk["kind"] == "users" and chunk["status"] == "ready"]
        if user_pending:
            return user_pending[0]
        user_incomplete = [chunk for chunk in run["chunks"] if chunk["kind"] == "users" and chunk["status"] not in {"completed", "not-required"}]
        if user_incomplete:
            return None
        group_ready = [chunk for chunk in run["chunks"] if chunk["kind"] == "groups" and chunk["status"] in {"ready", "blocked-by-users"}]
        return group_ready[0] if group_ready else None

    def record_chunk_submission(self, run_id: str, expected_revision: int, chunk_id: str, axon_job_id: str, console_summary: str) -> dict[str, Any]:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            run = db.execute("SELECT revision FROM provisioning_runs WHERE run_id=?", (run_id,)).fetchone()
            if not run:
                db.rollback()
                raise KeyError("Provisioning run was not found.")
            if run["revision"] != int(expected_revision):
                db.rollback()
                raise RevisionConflict(f"Run revision {expected_revision} is stale; current revision is {run['revision']}.")
            chunk = db.execute("SELECT kind,status,row_ids_json FROM submission_chunks WHERE chunk_id=? AND run_id=?", (chunk_id, run_id)).fetchone()
            if not chunk or chunk["status"] not in {"ready", "blocked-by-users"}:
                db.rollback()
                raise ValueError("The selected chunk is no longer eligible for submission.")
            if chunk["kind"] == "groups":
                incomplete = db.execute("SELECT COUNT(*) FROM submission_chunks WHERE run_id=? AND run_revision=? AND kind='users' AND status NOT IN ('completed','not-required')", (run_id, expected_revision)).fetchone()[0]
                if incomplete:
                    db.rollback()
                    raise ValueError("Group jobs remain locked until every applicable user job completes successfully.")
            db.execute("UPDATE submission_chunks SET status='submitted',axon_job_id=?,result_json=? WHERE chunk_id=?", (axon_job_id, canonical_json({"submittedAt": utc_now(), "summary": console_summary[:1000]}), chunk_id))
            db.execute("UPDATE provisioning_runs SET status='Monitoring',updated_at=? WHERE run_id=?", (utc_now(), run_id))
            submitted_row_ids = set(json.loads(chunk["row_ids_json"]))
            submitted_entity_type = "User" if chunk["kind"] == "users" else "GroupMembership"
            for overlay in db.execute("SELECT overlay_id,payload_json FROM pending_overlays WHERE run_id=? AND run_revision=? AND entity_type=? AND state IN ('Proposed creation','Proposed update')", (run_id, expected_revision, submitted_entity_type)).fetchall():
                if json.loads(overlay["payload_json"]).get("rowId") in submitted_row_ids:
                    db.execute("UPDATE pending_overlays SET state='Submitted—awaiting confirmation',updated_at=? WHERE overlay_id=?", (utc_now(), overlay["overlay_id"]))
            workspace_revision = self._increment_revision(db)
            self._audit_in_connection(db, "provisioning-center", "chunk-submitted", "success", {"runId": run_id, "runRevision": expected_revision, "chunkId": chunk_id, "kind": chunk["kind"], "axonJobId": axon_job_id, "workspaceRevision": workspace_revision})
            db.commit()
        return self.get_run(run_id)

    def record_chunk_result(self, run_id: str, expected_revision: int, chunk_id: str, status: str, result: dict[str, Any]) -> dict[str, Any]:
        normalized = status.casefold()
        if normalized in {"completed", "complete", "success", "succeeded"}:
            chunk_status = "completed"
        elif normalized in {"failed", "error", "rejected"}:
            chunk_status = "failed"
        else:
            chunk_status = "monitoring"
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            run = db.execute("SELECT revision FROM provisioning_runs WHERE run_id=?", (run_id,)).fetchone()
            if not run or run["revision"] != int(expected_revision):
                db.rollback()
                raise RevisionConflict("The run changed while job status was being recorded.")
            chunk = db.execute("SELECT kind,row_ids_json FROM submission_chunks WHERE chunk_id=? AND run_id=?", (chunk_id, run_id)).fetchone()
            if not chunk:
                db.rollback()
                raise ValueError("The submission chunk was not found.")
            db.execute("UPDATE submission_chunks SET status=?,result_json=? WHERE chunk_id=? AND run_id=?", (chunk_status, canonical_json(result), chunk_id, run_id))
            if chunk_status == "failed":
                failed_row_ids = set(json.loads(chunk["row_ids_json"]))
                failed_entity_type = "User" if chunk["kind"] == "users" else "GroupMembership"
                for overlay in db.execute("SELECT overlay_id,payload_json FROM pending_overlays WHERE run_id=? AND run_revision=? AND entity_type=?", (run_id, expected_revision, failed_entity_type)).fetchall():
                    if json.loads(overlay["payload_json"]).get("rowId") in failed_row_ids:
                        db.execute("UPDATE pending_overlays SET state='Failed',updated_at=? WHERE overlay_id=?", (utc_now(), overlay["overlay_id"]))
            if chunk_status == "completed":
                remaining_users = db.execute("SELECT COUNT(*) FROM submission_chunks WHERE run_id=? AND run_revision=? AND kind='users' AND status NOT IN ('completed','not-required')", (run_id, expected_revision)).fetchone()[0]
                if not remaining_users:
                    db.execute("UPDATE submission_chunks SET status='ready' WHERE run_id=? AND run_revision=? AND kind='groups' AND status='blocked-by-users'", (run_id, expected_revision))
            failed = db.execute("SELECT COUNT(*) FROM submission_chunks WHERE run_id=? AND run_revision=? AND status='failed'", (run_id, expected_revision)).fetchone()[0]
            outstanding = db.execute("SELECT COUNT(*) FROM submission_chunks WHERE run_id=? AND run_revision=? AND status NOT IN ('completed','not-required')", (run_id, expected_revision)).fetchone()[0]
            run_status = "Failed" if failed else ("Completed" if not outstanding else "Monitoring")
            db.execute("UPDATE provisioning_runs SET status=?,updated_at=? WHERE run_id=?", (run_status, utc_now(), run_id))
            workspace_revision = self._increment_revision(db)
            self._audit_in_connection(db, "provisioning-center", "chunk-status-recorded", chunk_status, {"runId": run_id, "chunkId": chunk_id, "workspaceRevision": workspace_revision})
            db.commit()
        return self.get_run(run_id)

    def migrate_governance_csvs(self, directory: Path | str) -> dict[str, Any]:
        root = Path(directory).resolve()
        migrated: list[dict[str, Any]] = []
        for path in sorted(root.glob("*.csv")):
            with path.open("rb") as source:
                raw = source.read()
            digest = hashlib.sha256(raw).hexdigest()
            text = raw.decode("utf-8-sig")
            reader = csv.DictReader(text.splitlines())
            headers = list(reader.fieldnames or [])
            rows = [{header: str(row.get(header) or "") for header in headers} for row in reader]
            dataset_key = path.stem
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                exists = db.execute("SELECT source_sha256,revision FROM governance_datasets WHERE dataset_key=?", (dataset_key,)).fetchone()
                if exists:
                    db.rollback()
                    migrated.append({"dataset": dataset_key, "status": "already-migrated", "sha256": exists["source_sha256"], "revision": exists["revision"]})
                    continue
                now = utc_now()
                db.execute(
                    "INSERT INTO governance_datasets VALUES(?,?,?,?,?,?,?,?,?)",
                    (dataset_key, path.name, canonical_json(headers), canonical_json(rows), digest, str(path), 1, now, now),
                )
                workspace_revision = self._increment_revision(db)
                self._audit_in_connection(db, "migration", "governance-csv-migrated", "success", {"dataset": dataset_key, "sha256": digest, "rows": len(rows), "workspaceRevision": workspace_revision})
                db.commit()
                migrated.append({"dataset": dataset_key, "status": "migrated", "sha256": digest, "rows": len(rows), "revision": 1})
        return {"sourceDirectory": str(root), "datasets": migrated, "workspaceRevision": self.revision()}

    def governance_dataset(self, dataset_key: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM governance_datasets WHERE dataset_key=?", (dataset_key,)).fetchone()
        if not row:
            raise KeyError("Governance dataset was not found.")
        return {"dataset": row["dataset_key"], "fileName": row["file_name"], "headers": json.loads(row["headers_json"]), "rows": json.loads(row["rows_json"]), "sourceSha256": row["source_sha256"], "sourcePath": row["source_path"], "revision": row["revision"], "migratedAt": row["migrated_at"], "updatedAt": row["updated_at"]}

    def ensure_governance_candidates(
        self,
        dataset_key: str,
        candidates: list[dict[str, Any]],
        unique_fields: Sequence[str],
        actor: str = "provisioning-center",
    ) -> dict[str, Any]:
        """Append distinct, unapproved observed values to a governance dataset.

        Candidate creation is deliberately separate from review and approval. It
        never changes an existing row, and the audit event records counts rather
        than directory-derived values.
        """
        if not unique_fields:
            raise ValueError("At least one governance candidate key field is required.")

        def normalized_key(row: dict[str, Any]) -> tuple[str, ...]:
            return tuple(
                re.sub(r"[^a-z0-9]+", " ", str(row.get(field) or "").strip().casefold()).strip()
                for field in unique_fields
            )

        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            source = db.execute("SELECT * FROM governance_datasets WHERE dataset_key=?", (dataset_key,)).fetchone()
            if not source:
                db.rollback()
                raise KeyError("Governance dataset was not found.")
            headers = json.loads(source["headers_json"])
            missing_fields = [field for field in unique_fields if field not in headers]
            if missing_fields:
                db.rollback()
                raise ValueError("Governance candidate key fields are missing: " + ", ".join(missing_fields))

            rows = json.loads(source["rows_json"])
            known = {normalized_key(row) for row in rows}
            additions: list[dict[str, str]] = []
            for raw in candidates:
                candidate = {header: "" if raw.get(header) is None else str(raw.get(header, "")).strip() for header in headers}
                key = normalized_key(candidate)
                if not all(key) or key in known:
                    continue
                unsafe_key = any(
                    candidate[field].lstrip().startswith(("=", "+", "-", "@"))
                    or "\n" in candidate[field]
                    or "\r" in candidate[field]
                    for field in unique_fields
                )
                if unsafe_key:
                    continue
                additions.append(candidate)
                known.add(key)

            if not additions:
                db.rollback()
                return {"dataset": dataset_key, "added": 0, "revision": source["revision"], "workspaceRevision": self._workspace_revision(db)}

            rows.extend(additions)
            new_revision = source["revision"] + 1
            now = utc_now()
            db.execute(
                "UPDATE governance_datasets SET rows_json=?,revision=?,updated_at=? WHERE dataset_key=?",
                (canonical_json(rows), new_revision, now, dataset_key),
            )
            first_index = len(rows) - len(additions)
            for offset, candidate in enumerate(additions):
                db.execute(
                    "INSERT INTO governance_history VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        uuid.uuid4().hex,
                        dataset_key,
                        str(first_index + offset),
                        source["revision"],
                        new_revision,
                        "{}",
                        canonical_json(candidate),
                        candidate.get("Mapping Method", "Observed during directory enrichment"),
                        candidate.get("Confidence", "Not rated"),
                        candidate.get("Review Notes", "Observed during provisioning enrichment; governance review is required."),
                        actor,
                        now,
                    ),
                )
            workspace_revision = self._increment_revision(db)
            self._audit_in_connection(
                db,
                actor,
                "governance-candidates-observed",
                "success",
                {"dataset": dataset_key, "added": len(additions), "datasetRevision": new_revision, "workspaceRevision": workspace_revision},
            )
            db.commit()
        return {"dataset": dataset_key, "added": len(additions), "revision": new_revision, "workspaceRevision": workspace_revision}

    def update_governance_row(self, dataset_key: str, row_index: int, changes: dict[str, Any], expected_revision: int, reviewer: str, mapping_method: str, confidence: str, review_notes: str) -> dict[str, Any]:
        if not review_notes.strip():
            raise ValueError("Review notes are required for governed mapping changes.")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            source = db.execute("SELECT * FROM governance_datasets WHERE dataset_key=?", (dataset_key,)).fetchone()
            if not source:
                db.rollback()
                raise KeyError("Governance dataset was not found.")
            if source["revision"] != int(expected_revision):
                db.rollback()
                raise RevisionConflict(f"Dataset revision {expected_revision} is stale; current revision is {source['revision']}.")
            rows = json.loads(source["rows_json"])
            if row_index < 0 or row_index >= len(rows):
                db.rollback()
                raise IndexError("Governance row was not found.")
            prior = dict(rows[row_index])
            rows[row_index].update({key: "" if value is None else str(value) for key, value in changes.items() if key in prior})
            new_revision = source["revision"] + 1
            now = utc_now()
            db.execute("UPDATE governance_datasets SET rows_json=?,revision=?,updated_at=? WHERE dataset_key=?", (canonical_json(rows), new_revision, now, dataset_key))
            db.execute(
                "INSERT INTO governance_history VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, dataset_key, str(row_index), expected_revision, new_revision, canonical_json(prior), canonical_json(rows[row_index]), mapping_method, confidence, review_notes, reviewer or "operator", now),
            )
            workspace_revision = self._increment_revision(db)
            self._audit_in_connection(db, reviewer or "operator", "governance-row-updated", "success", {"dataset": dataset_key, "rowIndex": row_index, "datasetRevision": new_revision, "workspaceRevision": workspace_revision})
            db.commit()
        return self.governance_dataset(dataset_key)

    def replace_governance_rows(self, dataset_key: str, rows: list[dict[str, Any]], expected_revision: int, event_type: str, reviewer: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            source = db.execute("SELECT revision,headers_json FROM governance_datasets WHERE dataset_key=?", (dataset_key,)).fetchone()
            if not source:
                db.rollback()
                raise KeyError("Governance dataset was not found.")
            if source["revision"] != int(expected_revision):
                db.rollback()
                raise RevisionConflict(f"Dataset revision {expected_revision} is stale; current revision is {source['revision']}.")
            headers = json.loads(source["headers_json"])
            normalized = [{header: "" if row.get(header) is None else str(row.get(header, "")) for header in headers} for row in rows]
            new_revision = expected_revision + 1
            now = utc_now()
            db.execute("UPDATE governance_datasets SET rows_json=?,revision=?,updated_at=? WHERE dataset_key=?", (canonical_json(normalized), new_revision, now, dataset_key))
            workspace_revision = self._increment_revision(db)
            self._audit_in_connection(db, reviewer or "operator", event_type, "success", {"dataset": dataset_key, "datasetRevision": new_revision, "workspaceRevision": workspace_revision, **(details or {})})
            db.commit()
        return self.governance_dataset(dataset_key)

    def export_governance_csv(self, dataset_key: str, destination: Path | str) -> Path:
        dataset = self.governance_dataset(dataset_key)
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=dataset["headers"], lineterminator="\r\n")
            writer.writeheader()
            for row in dataset["rows"]:
                writer.writerow({key: safe_csv_value(row.get(key, "")) for key in dataset["headers"]})
        return path

    def status(self) -> dict[str, Any]:
        latest = self.latest_run()
        return {
            "schemaVersion": "3.1.0",
            "workspacePath": str(self.path),
            "workspaceRevision": self.revision(),
            "snapshots": self.snapshot_metadata(),
            "refreshLeases": self.lease_status(),
            "pendingCounts": self._pending_counts(),
            "latestRun": {"runId": latest["runId"], "revision": latest["revision"], "status": latest["status"], "updatedAt": latest["updatedAt"]} if latest else None,
            "audit": self.verify_audit_chain(),
        }

    def _pending_counts(self) -> dict[str, int]:
        with self.connection() as db:
            rows = db.execute("SELECT state,COUNT(*) AS count FROM pending_overlays WHERE state NOT IN ('Superseded','Confirmed') GROUP BY state").fetchall()
        return {row["state"]: row["count"] for row in rows}
