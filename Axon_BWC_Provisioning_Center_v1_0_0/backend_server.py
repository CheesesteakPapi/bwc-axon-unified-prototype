"""Localhost-only bridge between the web UI and the Axon provisioning scripts.

Secrets are retained only in this process. They are passed to child commands
through environment variables and are never written to config.json, command
arguments, logs, responses, or browser storage.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import csv
import errno
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import webbrowser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

SUITE_ROOT = Path(__file__).resolve().parent.parent
if str(SUITE_ROOT) not in sys.path:
    sys.path.insert(0, str(SUITE_ROOT))

from provisioning_workflow import (
    EntraDelegatedProvider,
    GROUP_HEADERS,
    RowDirectoryProvider,
    SyntheticDirectoryProvider,
    USER_HEADERS,
    WorkflowError,
    canonicalize_input,
    detect_columns,
    edit_rows,
    enrich_rows,
    export_run_package,
    parse_intake_file,
    write_csv,
)
from shared_workspace import RefreshLeaseConflict, RevisionConflict, SharedWorkspace

from audit_store import append_event, verify_chain
from axon_provision import (
    classify_users,
    provisioning,
    sha256_file,
    validate_group_entities_csv,
    validate_user_csv,
)
from axon_ui_support import OPERATIONS_BY_KEY, build_api_csvs, build_command, display_command
from runtime_paths import component_root, ensure_private_file, governance_root, initialize_governance_files
from desktop_message import show_error
from instance_lock import SingleInstanceLock


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "dist" / "client"
RUNTIME_ROOT = component_root("provisioning-center")
CONFIG_PATH = RUNTIME_ROOT / "config.json"
CONFIG_EXAMPLE_PATH = BASE_DIR / "config.example.json"
VERSION = "3.1.0"
MAX_REQUEST_BYTES = 28 * 1024 * 1024
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
LOCAL_UI_HEADER = "X-Axon-Local-UI"
LOCAL_SESSION_COOKIE = "BWC_AXON_PROVISIONING_SESSION"

UI_TO_FUNCTIONAL = {
    "download-users": "sync_users",
    "download-groups": "sync_groups",
    "validate-users": "validate_users",
    "preview-users": "preview_users",
    "submit-users": "submit_users",
    "list-user-jobs": "list_user_jobs",
    "user-job-status": "user_job_status",
    "user-job-results": "user_job_results",
    "validate-groups": "validate_groups",
    "preview-groups": "preview_groups",
    "submit-groups": "submit_groups",
    "list-group-jobs": "list_group_jobs",
    "group-job-status": "group_job_status",
    "group-job-results": "group_job_results",
}


class UserInputError(ValueError):
    """An expected, safe-to-display request validation error."""


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def apply_runtime_paths(config: dict[str, Any]) -> dict[str, Any]:
    configured = dict(config)
    data_root = component_root("provisioning-center")
    shared = governance_root()
    configured["raw_dir"] = str(data_root / "data" / "raw")
    configured["schema_dir"] = str(data_root / "data" / "schemas")
    configured["processed_dir"] = str(data_root / "data" / "processed")
    configured["sync_log_csv"] = str(data_root / "state" / "sync_log.csv")
    configured["device_home_crosswalk_csv"] = str(shared / "device_home_crosswalk_starter.csv")
    configured["device_status_map_csv"] = str(shared / "device_status_map.csv")
    configured["axon_group_crosswalk_csv"] = str(shared / "axon_group_crosswalk_starter.csv")
    provision_config = dict(configured.get("provisioning") or {})
    provision_config["audit_log_csv"] = str(data_root / "state" / "provisioning_audit.csv")
    configured["provisioning"] = provision_config
    return configured


def load_config() -> tuple[dict[str, Any], bool]:
    path = CONFIG_PATH if CONFIG_PATH.exists() else CONFIG_EXAMPLE_PATH
    if not path.exists():
        raise RuntimeError("config.example.json is missing from the package.")
    return apply_runtime_paths(read_json(path)), CONFIG_PATH.exists()


def public_config() -> dict[str, Any]:
    config, exists = load_config()
    pcfg = provisioning(config)
    return {
        "exists": exists,
        "agencyBaseUrl": str(config.get("agency_base_url") or ""),
        "timeoutSeconds": int(config.get("timeout_seconds", 90)),
        "writeOperationsEnabled": bool(pcfg.get("write_operations_enabled")),
        "groupFileFieldConfirmed": bool(pcfg.get("group_entities_file_field_confirmed")),
    }


def save_public_config(values: dict[str, Any]) -> dict[str, Any]:
    config, _ = load_config()
    base_url = str(values.get("agencyBaseUrl") or "").strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise UserInputError("Axon Evidence tenant URL must be a complete HTTPS URL.")
    try:
        timeout = int(values.get("timeoutSeconds", 90))
    except (TypeError, ValueError) as exc:
        raise UserInputError("Timeout must be a whole number of seconds.") from exc
    if timeout < 15 or timeout > 1800:
        raise UserInputError("Timeout must be between 15 and 1800 seconds.")

    config["agency_base_url"] = base_url
    config["timeout_seconds"] = timeout
    provision_config = dict(config.get("provisioning") or {})
    provision_config["write_operations_enabled"] = bool(values.get("writeOperationsEnabled", False))
    provision_config["group_entities_file_field_confirmed"] = bool(values.get("groupFileFieldConfirmed", False))
    config["provisioning"] = provision_config

    temporary_path = CONFIG_PATH.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_path, CONFIG_PATH)
    ensure_private_file(CONFIG_PATH)
    append_event(
        "provisioning-center",
        "connection-settings-updated",
        "success",
        {
            "timeoutSeconds": timeout,
            "writeOperationsEnabled": provision_config["write_operations_enabled"],
            "groupFileFieldConfirmed": provision_config["group_entities_file_field_confirmed"],
        },
    )
    return public_config()


def safe_name(value: str, default: str = "upload.csv") -> str:
    name = Path(value or default).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or default


class SessionState:
    def __init__(self) -> None:
        test_token = (
            os.environ.get("BWC_AXON_TEST_LAUNCH_TOKEN", "")
            if os.environ.get("BWC_AXON_TEST_MODE") == "1"
            else ""
        )
        self.local_token = test_token if len(test_token) >= 32 else secrets.token_urlsafe(32)
        self._temp = tempfile.TemporaryDirectory(prefix="axon_bwc_web_")
        self.root = Path(self._temp.name)
        self.upload_dir = self.root / "uploads"
        self.output_dir = self.root / "outputs"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._credentials: dict[str, str] = {}
        self._uploads: dict[str, Path] = {}
        self._upload_names: dict[str, str] = {}
        self._downloads: dict[str, Path] = {}
        self._download_names: dict[str, str] = {}
        self._user_previews: dict[str, dict[str, Any]] = {}
        self._latest_user_preview_token = ""
        self._lock = threading.RLock()
        self._refresh_jobs: dict[str, dict[str, Any]] = {}
        self.workspace = SharedWorkspace()
        self.workspace.migrate_governance_csvs(governance_root())

    def close(self) -> None:
        with self._lock:
            processes = [job.get("process") for job in self._refresh_jobs.values() if job.get("status") == "running"]
        for process in processes:
            if process and process.poll() is None:
                process.terminate()
        self.clear_credentials()
        self._temp.cleanup()

    def set_credentials(self, partner_id: str, client_id: str, client_secret: str) -> None:
        values = {
            "partner_id": str(partner_id or "").strip(),
            "client_id": str(client_id or "").strip(),
            "client_secret": str(client_secret or ""),
        }
        if not all(values.values()):
            raise UserInputError("Partner/Agency ID, Client ID, and Client Secret are all required.")
        with self._lock:
            self._credentials = values

    def start_shared_refresh(self, resource: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        allowed = {"Users", "Groups", "Devices", "DeviceHomes"}
        if resource not in allowed:
            raise UserInputError("Resource must be Users, Groups, Devices, or DeviceHomes.")
        if not self.session_status()["configured"]:
            raise UserInputError("Save the Axon session credentials before refreshing shared data.")
        config, exists = load_config()
        if not exists or "YOUR_AGENCY" in str(config.get("agency_base_url") or ""):
            raise UserInputError("Save the Axon Evidence tenant HTTPS URL before refreshing shared data.")

        normalized_filters: dict[str, str] = {}
        if resource == "Devices":
            for key in ("model", "status2", "homeId"):
                value = str((filters or {}).get(key) or "").strip()
                if value:
                    normalized_filters[key] = value
        scope = {"type": "filtered" if normalized_filters else "full", "filters": normalized_filters}
        job_id = uuid.uuid4().hex
        owner_id = f"provisioning-center-{os.getpid()}-{job_id}"
        refresh_id = self.workspace.acquire_refresh_lease(resource, owner_id, scope)
        command = [sys.executable, str(BASE_DIR / "axon_sync.py"), "sync", "--config", str(CONFIG_PATH), "--resource", resource]
        if normalized_filters.get("model"):
            command.extend(["--device-model", normalized_filters["model"]])
        if normalized_filters.get("status2"):
            command.extend(["--device-status", normalized_filters["status2"]])
        if normalized_filters.get("homeId"):
            command.extend(["--device-home-id", normalized_filters["homeId"]])
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            process = subprocess.Popen(
                command,
                cwd=BASE_DIR,
                env=self.credential_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creation_flags,
            )
        except Exception:
            self.workspace.release_refresh_lease(resource, owner_id, refresh_id, "failed", "Refresh process could not start.")
            raise
        job = {
            "jobId": job_id,
            "resource": resource,
            "scope": scope,
            "status": "running",
            "message": "Refresh started.",
            "output": "",
            "snapshotId": "",
            "ownerId": owner_id,
            "refreshId": refresh_id,
            "cancelRequested": False,
            "process": process,
        }
        with self._lock:
            self._refresh_jobs[job_id] = job
        threading.Thread(target=self._finish_shared_refresh, args=(job_id,), daemon=True).start()
        return self.refresh_job(job_id)

    def _finish_shared_refresh(self, job_id: str) -> None:
        with self._lock:
            job = self._refresh_jobs[job_id]
            process = job["process"]
        output, _ = process.communicate()
        with self._lock:
            canceled = bool(job.get("cancelRequested"))
        status = "canceled" if canceled else ("completed" if process.returncode == 0 else "failed")
        message = "Refresh canceled; the prior baseline remains active." if canceled else output.strip()[-4000:]
        snapshot_id = ""
        try:
            if status == "completed":
                config, _ = load_config()
                resource_config = dict(config.get("resources", {}).get(job["resource"], {}))
                output_path = Path(str(config.get("processed_dir", "data/processed"))) / str(resource_config.get("output_csv") or "")
                if not output_path.exists():
                    raise RuntimeError("The completed refresh did not create its normalized output.")
                with output_path.open("r", newline="", encoding="utf-8-sig") as handle:
                    rows = list(csv.DictReader(handle))
                activated = self.workspace.activate_snapshot(
                    job["resource"], rows, job["scope"], "Axon API via Provisioning Center"
                )
                snapshot_id = activated["snapshotId"]
                message = f"Activated {len(rows)} normalized {job['resource']} rows."
        except Exception as exc:
            status = "failed"
            message = f"Refresh output could not be activated: {exc}"
        finally:
            self.workspace.release_refresh_lease(job["resource"], job["ownerId"], job["refreshId"], status, message, snapshot_id)
            with self._lock:
                job.update({"status": status, "message": message, "output": output.strip()[-4000:], "snapshotId": snapshot_id, "process": None})

    def refresh_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._refresh_jobs.get(job_id)
            if not job:
                raise UserInputError("Refresh job was not found in this local session.")
            return {key: value for key, value in job.items() if key not in {"process", "ownerId", "refreshId"}}

    def cancel_refresh(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._refresh_jobs.get(job_id)
            if not job:
                raise UserInputError("Refresh job was not found in this local session.")
            if job["status"] != "running":
                return self.refresh_job(job_id)
            job["cancelRequested"] = True
            job["message"] = "Cancellation requested."
            process = job.get("process")
        if process and process.poll() is None:
            process.terminate()
        return self.refresh_job(job_id)

    def clear_credentials(self) -> None:
        with self._lock:
            for key in tuple(self._credentials):
                self._credentials[key] = ""
            self._credentials = {}

    def session_status(self) -> dict[str, Any]:
        with self._lock:
            partner_id = self._credentials.get("partner_id", "")
            configured = bool(partner_id and self._credentials.get("client_id") and self._credentials.get("client_secret"))
        return {
            "configured": configured,
            "partnerHint": f"…{partner_id[-4:]}" if configured and len(partner_id) > 4 else (partner_id if configured else ""),
        }

    def credential_env(self) -> dict[str, str]:
        with self._lock:
            if not self.session_status()["configured"]:
                raise UserInputError("Enter session credentials before running a function that contacts Axon.")
            credentials = dict(self._credentials)
        environment = os.environ.copy()
        environment["AXON_PARTNER_ID"] = credentials["partner_id"]
        environment["AXON_CLIENT_ID"] = credentials["client_id"]
        environment["AXON_CLIENT_SECRET"] = credentials["client_secret"]
        return environment

    def partner_id(self) -> str:
        with self._lock:
            return self._credentials.get("partner_id", "")

    def save_upload(self, name: str, content: bytes) -> tuple[str, Path]:
        if not content:
            raise UserInputError("The selected file is empty.")
        if len(content) > MAX_UPLOAD_BYTES:
            raise UserInputError("The selected file exceeds the 20 MB session upload limit.")
        filename = safe_name(name)
        if Path(filename).suffix.lower() not in {".csv", ".json", ".xlsx"}:
            raise UserInputError("Only CSV, XLSX, and JSON files can be selected.")
        handle = uuid.uuid4().hex
        path = self.upload_dir / f"{handle}_{filename}"
        path.write_bytes(content)
        with self._lock:
            self._uploads[handle] = path
            self._upload_names[handle] = filename
        return handle, path

    def resolve_upload(self, handle: str) -> Path:
        with self._lock:
            path = self._uploads.get(str(handle or ""))
        if not path or not path.exists():
            raise UserInputError("A selected session file is missing. Choose the file again.")
        return path

    def upload_name(self, handle: str) -> str:
        with self._lock:
            name = self._upload_names.get(str(handle or ""))
        if not name:
            raise UserInputError("A selected session file is missing. Choose the file again.")
        return name

    def create_output_path(self, display_name: str) -> Path:
        filename = safe_name(display_name)
        return self.output_dir / f"{uuid.uuid4().hex}_{filename}"

    def register_session_file(self, path: Path, display_name: str | None = None) -> dict[str, Any]:
        resolved = path.resolve()
        if self.root.resolve() not in resolved.parents or not resolved.is_file():
            raise RuntimeError("Only generated session files can be registered for reuse.")
        name = safe_name(display_name or path.name)
        handle = uuid.uuid4().hex
        with self._lock:
            self._uploads[handle] = path
            self._upload_names[handle] = name
        size = path.stat().st_size
        count = csv_row_count(path)
        return {
            "handle": handle,
            "name": name,
            "size": size,
            "detail": f"{count} rows" if count is not None else f"{size} bytes",
        }

    def register_download(
        self,
        path: Path,
        *,
        kind: str | None = None,
        display_name: str | None = None,
        row_count: int | None = None,
    ) -> dict[str, Any]:
        if not path.exists() or not path.is_file():
            raise RuntimeError(f"Generated file was not found: {path.name}")
        handle = uuid.uuid4().hex
        name = safe_name(display_name or path.name)
        with self._lock:
            self._downloads[handle] = path
            self._download_names[handle] = name
        result = {"name": name, "url": f"/api/download/{handle}"}
        if kind:
            result["kind"] = kind
        if row_count is not None:
            result["rowCount"] = int(row_count)
        return result

    def resolve_download(self, handle: str) -> Path | None:
        with self._lock:
            path = self._downloads.get(handle)
        return path if path and path.exists() else None

    def download_name(self, handle: str, fallback: str) -> str:
        with self._lock:
            return self._download_names.get(handle, fallback)

    def register_user_preview(
        self,
        user_path: Path,
        snapshot_path: Path | None,
        payload: dict[str, Any],
    ) -> str:
        token = uuid.uuid4().hex
        record = {
            "userPath": str(user_path.resolve()),
            "userSha256": payload["sha256"],
            "snapshotPath": str(snapshot_path.resolve()) if snapshot_path else "",
            "snapshotSha256": sha256_file(snapshot_path) if snapshot_path else "",
            "matchCount": int(payload["matchCount"]),
            "blockerCount": int(payload["blockerCount"]),
            "fileErrors": list(payload["fileErrors"]),
            "errors": list(payload["errors"]),
        }
        with self._lock:
            self._user_previews = {token: record}
            self._latest_user_preview_token = token
        return token

    def require_user_preview(
        self,
        token: str,
        user_path: Path,
        snapshot_path: Path | None,
    ) -> dict[str, Any]:
        with self._lock:
            record = self._user_previews.get(str(token or ""))
            is_latest = bool(token) and token == self._latest_user_preview_token
        if not record or not is_latest:
            raise UserInputError("Run Preview Users again before using this reviewed result.")
        current_snapshot_path = str(snapshot_path.resolve()) if snapshot_path else ""
        if record["userPath"] != str(user_path.resolve()) or record["snapshotPath"] != current_snapshot_path:
            raise UserInputError("The selected files changed after preview. Run Preview Users again.")
        if record["userSha256"] != sha256_file(user_path):
            raise UserInputError("The user CSV changed after preview. Run Preview Users again.")
        current_snapshot_sha = sha256_file(snapshot_path) if snapshot_path else ""
        if record["snapshotSha256"] != current_snapshot_sha:
            raise UserInputError("The Users snapshot changed after preview. Run Preview Users again.")
        return dict(record)


def csv_row_count(path: Path) -> int | None:
    if path.suffix.lower() != ".csv":
        return None
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            return sum(1 for row in reader if any(str(value).strip() for value in row))
    except (OSError, UnicodeError, csv.Error):
        return None


def file_value(state: SessionState, files: dict[str, Any], label: str, required: bool = True) -> str:
    handle = str(files.get(label) or "")
    if not handle:
        if required:
            raise UserInputError(f"Choose {label} before running this function.")
        return ""
    return str(state.resolve_upload(handle))


ROW_ERROR_RE = re.compile(r"^Row (\d+):\s*(.+)$")
DUPLICATE_ERROR_RE = re.compile(r"^Duplicate ([A-Z_]+) values in input:")
UNIQUE_USER_COLUMNS = ("EXTERNAL_ID", "EMAIL", "BADGE_NUMBER", "USERNAME")


def analyze_user_file(
    user_csv: Path,
    existing_csv: Path | None,
    require_snapshot: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    result = validate_user_csv(user_csv)
    classification = classify_users(result["rows"], existing_csv)
    errors = list(result["errors"]) + list(classification["conflicts"])
    if require_snapshot and existing_csv is None:
        errors.append("A recent Users snapshot is required by configuration.")

    blockers: dict[int, list[str]] = {}

    def add_blocker(row_number: int, message: str) -> None:
        messages = blockers.setdefault(row_number, [])
        if message not in messages:
            messages.append(message)

    file_errors: list[str] = []
    for error in errors:
        row_match = ROW_ERROR_RE.match(error)
        if row_match:
            add_blocker(int(row_match.group(1)), row_match.group(2))
        elif not DUPLICATE_ERROR_RE.match(error):
            file_errors.append(error)

    # The validator reports duplicate values at file level. Mark every row in
    # each duplicate set so cleanup never makes an arbitrary "keep first" choice.
    for column in UNIQUE_USER_COLUMNS:
        by_value: dict[str, list[int]] = {}
        display_values: dict[str, str] = {}
        for row_number, row in enumerate(result["rows"], start=2):
            raw_value = str(row.get(column) or "").strip()
            if not raw_value:
                continue
            normalized = raw_value.casefold()
            by_value.setdefault(normalized, []).append(row_number)
            display_values.setdefault(normalized, raw_value)
        for normalized, row_numbers in by_value.items():
            if len(row_numbers) < 2:
                continue
            message = f'Duplicate {column} value "{display_values[normalized]}".'
            for row_number in row_numbers:
                add_blocker(row_number, message)

    header_counts: dict[str, int] = {}
    for header in result["headers"]:
        header_counts[header] = header_counts.get(header, 0) + 1
    duplicate_headers = sorted(header for header, count in header_counts.items() if count > 1)
    if duplicate_headers:
        message = "Duplicate headers: " + ", ".join(duplicate_headers)
        errors.append(message)
        file_errors.append(message)

    update_rows = set(classification["update_rows"])
    create_rows = set(classification["create_rows"])
    rows = []
    for row_number, row in enumerate(result["rows"], start=2):
        is_match = row_number in update_rows
        is_create = row_number in create_rows
        row_blockers = blockers.get(row_number, [])
        is_blocked = bool(row_blockers)
        if is_blocked:
            row_result = "Blocked — remove or review"
        elif is_match:
            row_result = "Existing match — review"
        else:
            row_result = "New account"
        rows.append({
            "sourceRow": row_number,
            "externalId": row.get("EXTERNAL_ID", ""),
            "email": row.get("EMAIL", ""),
            "name": " ".join(part for part in (row.get("FIRST_NAME", ""), row.get("LAST_NAME", "")) if part),
            "status": row.get("STATUS", ""),
            "role": row.get("ROLE", ""),
            "result": row_result,
            "type": "match" if is_match else ("new" if is_create else "blocker"),
            "existingMatch": is_match,
            "createCandidate": is_create,
            "blocked": is_blocked,
            "blockers": row_blockers,
        })
    payload = {
        "rows": rows,
        "rowCount": len(rows),
        "createCount": len(create_rows),
        "matchCount": len(update_rows),
        "blockerCount": len(blockers),
        "cleanCreateCount": len(create_rows - set(blockers)),
        "eligibleMatchCount": len(update_rows - set(blockers)),
        "removableCount": len(update_rows | set(blockers)),
        "errors": errors,
        "fileErrors": file_errors,
        "warnings": result["warnings"],
        "sha256": result["sha256"],
    }
    return result, classification, payload


def user_preview_payload(user_csv: Path, existing_csv: Path | None, require_snapshot: bool) -> dict[str, Any]:
    return analyze_user_file(user_csv, existing_csv, require_snapshot)[2]


def write_csv_rows(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore", lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)


def csv_rows_for_output(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read source values without trimming cells so generated copies only remove rows."""
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = [str(header or "").strip() for header in (reader.fieldnames or [])]
        rows: list[dict[str, str]] = []
        for raw in reader:
            if not any(str(value or "").strip() for value in raw.values()):
                continue
            rows.append({str(key or "").strip(): str(value or "") for key, value in raw.items()})
    return headers, rows


def rows_from_session_file(state: SessionState, handle: str) -> tuple[list[str], list[dict[str, str]]]:
    path = state.resolve_upload(handle)
    return parse_intake_file(state.upload_name(handle), path.read_bytes())


def provisioning_run_payload(state: SessionState, body: dict[str, Any]) -> dict[str, Any]:
    file_handle = str(body.get("fileHandle") or "")
    if file_handle:
        headers, raw_rows = rows_from_session_file(state, file_handle)
        detection = detect_columns(headers)
        mapping = dict(body.get("columnMapping") or {})
        if detection["needsMapper"] and not mapping:
            return {"needsColumnMapping": True, "headers": headers, **detection}
    else:
        raw_rows = list(body.get("rows") or [])
        mapping = dict(body.get("columnMapping") or {})
    intake_rows = canonicalize_input(raw_rows, mapping)
    provider_name = str(body.get("provider") or "directory-file")
    if provider_name == "synthetic-test":
        provider = SyntheticDirectoryProvider()
    elif provider_name == "entra-delegated":
        token = str(body.get("entraAccessToken") or "")
        if not token:
            raise UserInputError("A delegated Microsoft Graph access token is required for live Entra enrichment.")
        provider = EntraDelegatedProvider(token)
    else:
        directory_handle = str(body.get("directoryFileHandle") or "")
        if directory_handle:
            _headers, directory_rows = rows_from_session_file(state, directory_handle)
        else:
            directory_rows = list(body.get("directoryRows") or raw_rows)
        provider = RowDirectoryProvider(directory_rows, "sharepoint-export" if provider_name == "sharepoint-export" else "directory-file")
    rows, validation, generation = enrich_rows(state.workspace, intake_rows, provider)
    status = "Ready for Preview" if validation["valid"] else "Needs Review"
    return state.workspace.create_run(str(body.get("title") or "Provisioning run"), provider.name, rows, validation, generation, status)


def revise_provisioning_run(state: SessionState, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
    current = state.workspace.get_run(run_id)
    rows, validation, generation = edit_rows(
        state.workspace,
        current["rows"],
        list(body.get("edits") or []),
        str(body.get("reason") or ""),
    )
    status = "Ready for Preview" if validation["valid"] else "Needs Review"
    changed_count = len(body.get("edits") or [])
    return state.workspace.revise_run(
        run_id,
        int(body.get("expectedRevision", -1)),
        rows,
        validation,
        generation,
        status,
        f"Assignment fields changed for {changed_count} users",
        str(body.get("reason") or ""),
    )


def write_snapshot_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    if not headers:
        headers = ["External ID", "Email", "Badge ID"]
    write_csv_rows(path, headers, [{key: str(row.get(key) or "") for key in headers} for row in rows])


def _run_axon_command(state: SessionState, spec_key: str, values: dict[str, str]) -> subprocess.CompletedProcess[str]:
    config, exists = load_config()
    if not exists or not str(config.get("agency_base_url") or "").startswith("https://"):
        raise UserInputError("Save the Axon Evidence tenant HTTPS URL before submission or tracking.")
    pcfg = provisioning(config)
    if not pcfg["write_operations_enabled"] and spec_key in {"submit_users", "submit_groups"}:
        raise UserInputError("Axon write operations are disabled in local settings.")
    spec = OPERATIONS_BY_KEY[spec_key]
    command = build_command(BASE_DIR, spec, {"config": str(CONFIG_PATH), **values})
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.run(
        command,
        cwd=BASE_DIR,
        env=state.credential_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
        creationflags=creation_flags,
        check=False,
    )


def submit_next_run_chunk(state: SessionState, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
    expected_revision = int(body.get("expectedRevision", -1))
    run = state.workspace.get_run(run_id)
    if run["revision"] != expected_revision:
        raise RevisionConflict(f"Run revision {expected_revision} is stale; current revision is {run['revision']}.")
    if run["status"] not in {"Awaiting Submission", "Monitoring"} or not run.get("approval"):
        raise UserInputError("Approve the current preview revision before submission.")
    if not body.get("confirmWrite"):
        raise UserInputError("Final Axon submission requires an explicit confirmation.")
    confirmation = str(body.get("confirmAgency") or "").strip()
    if not confirmation or confirmation != state.partner_id():
        raise UserInputError("The confirmation Agency ID does not match this credential session.")
    chunk = state.workspace.eligible_chunk(run_id, expected_revision)
    if not chunk:
        raise UserInputError("No chunk is eligible. Track submitted user jobs before Group jobs are unlocked.")
    kind = chunk["kind"]
    generated_chunks = run["generation"]["userChunks" if kind == "users" else "groupChunks"]
    payload = generated_chunks[chunk["ordinal"] - 1]
    csv_path = state.create_output_path(f"{kind}_chunk_{chunk['ordinal']:03d}.csv")
    write_csv(csv_path, USER_HEADERS if kind == "users" else GROUP_HEADERS, payload["records"])
    values = {"execute": "yes", "confirm_agency": confirmation}
    if kind == "users":
        values["user_csv"] = str(csv_path)
        snapshot = state.workspace.active_snapshot("Users")
        if snapshot:
            snapshot_path = state.create_output_path("confirmed_users_snapshot.csv")
            write_snapshot_csv(snapshot_path, snapshot["rows"])
            values["existing_users"] = str(snapshot_path)
        if run["validation"].get("updateCount", 0):
            values["allow_updates"] = "yes"
        spec_key = "submit_users"
    else:
        values["group_csv"] = str(csv_path)
        groups = state.workspace.active_snapshot("Groups")
        if not groups:
            raise UserInputError("A complete confirmed Groups snapshot is required before Group submission.")
        groups_path = state.create_output_path("confirmed_groups_snapshot.csv")
        write_snapshot_csv(groups_path, groups["rows"])
        users_path = state.create_output_path("pending_users.csv")
        write_csv(users_path, USER_HEADERS, run["generation"]["userRecords"])
        completed_users = [item for item in run["chunks"] if item["kind"] == "users" and item["status"] == "completed" and item["axonJobId"]]
        values.update({"groups_snapshot": str(groups_path), "pending_users": str(users_path), "user_job_id": completed_users[-1]["axonJobId"] if completed_users else ""})
        spec_key = "submit_groups"
    completed = _run_axon_command(state, spec_key, values)
    if completed.returncode != 0:
        raise UserInputError(completed.stdout.strip() or "Axon submission failed before a job ID was returned.")
    job_match = re.search(r"Job ID:\s*([^\s]+)", completed.stdout)
    if not job_match or job_match.group(1).casefold() == "unknown":
        raise UserInputError("Axon accepted the request but no unambiguous job ID was returned. Do not retry automatically; inspect the Axon job queue.")
    updated = state.workspace.record_chunk_submission(run_id, expected_revision, chunk["chunkId"], job_match.group(1), completed.stdout.strip())
    return {"run": updated, "submittedChunk": chunk["chunkId"], "axonJobId": job_match.group(1), "output": completed.stdout.strip()}


def track_run_jobs(state: SessionState, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
    expected_revision = int(body.get("expectedRevision", -1))
    run = state.workspace.get_run(run_id)
    if run["revision"] != expected_revision:
        raise RevisionConflict(f"Run revision {expected_revision} is stale; current revision is {run['revision']}.")
    checked = []
    for chunk in run["chunks"]:
        if chunk["status"] not in {"submitted", "monitoring"} or not chunk["axonJobId"]:
            continue
        spec_key = "user_job_status" if chunk["kind"] == "users" else "group_job_status"
        completed = _run_axon_command(state, spec_key, {"job_id": chunk["axonJobId"]})
        output = completed.stdout.strip()
        status_match = re.search(r":\s*([^\r\n]+)$", output)
        status = status_match.group(1).strip() if status_match else "unknown"
        run = state.workspace.record_chunk_result(run_id, expected_revision, chunk["chunkId"], status, {"checkedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "status": status, "summary": output[:1000]})
        checked.append({"chunkId": chunk["chunkId"], "axonJobId": chunk["axonJobId"], "status": status})
    return {"run": run, "checked": checked}


def export_user_preview_files(
    state: SessionState,
    source_name: str,
    source_path: Path,
    validation: dict[str, Any],
    classification: dict[str, Any],
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    stem = Path(source_name).stem or "users"
    blocked_rows = {row["sourceRow"] for row in payload["rows"] if row["blocked"]}
    create_rows = set(classification["create_rows"]) - blocked_rows
    match_rows = set(classification["update_rows"])
    output_headers, output_rows = csv_rows_for_output(source_path)
    indexed_rows = list(enumerate(output_rows, start=2))
    exports = (
        (
            "newAccounts",
            f"{stem}_new_accounts.csv",
            [row for row_number, row in indexed_rows if row_number in create_rows],
        ),
        (
            "matchedAccounts",
            f"{stem}_matched_accounts.csv",
            [row for row_number, row in indexed_rows if row_number in match_rows],
        ),
    )
    downloads: list[dict[str, Any]] = []
    for kind, display_name, rows in exports:
        output_path = state.create_output_path(display_name)
        write_csv_rows(output_path, output_headers, rows)
        downloads.append(
            state.register_download(
                output_path,
                kind=kind,
                display_name=display_name,
                row_count=len(rows),
            )
        )
    return downloads


def text_user_result(payload: dict[str, Any]) -> str:
    lines = [
        f"Rows: {payload['rowCount']}",
        f"Create candidates: {payload['createCount']}",
        f"Existing/update candidates: {payload['matchCount']}",
        f"Blocker rows: {payload['blockerCount']}",
        f"Clean create candidates: {payload['cleanCreateCount']}",
        f"SHA-256: {payload['sha256']}",
    ]
    lines.extend(f"WARNING: {value}" for value in payload["warnings"])
    lines.extend(f"ERROR: {value}" for value in payload["errors"])
    lines.append("Validation: " + ("PASS" if not payload["errors"] else "FAIL"))
    return "\n".join(lines)


def execute_operation(state: SessionState, body: dict[str, Any]) -> dict[str, Any]:
    operation_key = str(body.get("operation") or "")
    files = dict(body.get("files") or {})
    fields = dict(body.get("fields") or {})
    downloads: list[dict[str, str]] = []

    if operation_key == "build-files":
        source = Path(file_value(state, files, "Source roster"))
        user_name = safe_name(str(fields.get("User CSV destination") or "users_import.csv"), "users_import.csv")
        group_name = safe_name(str(fields.get("Group CSV destination") or "group_entities.csv"), "group_entities.csv")
        user_output = state.output_dir / user_name
        group_output = state.output_dir / group_name
        user_count, group_count = build_api_csvs(source, user_output, group_output)
        downloads.extend((state.register_download(user_output), state.register_download(group_output)))
        return {
            "success": True,
            "exitCode": 0,
            "output": f"Created {user_count} user rows.\nCreated {group_count} group-assignment rows.",
            "downloads": downloads,
        }

    if operation_key in {"edit-users", "edit-groups"}:
        label = "User import CSV" if operation_key == "edit-users" else "Group assignment CSV"
        path = Path(file_value(state, files, label))
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        if len(rows) > 500:
            raise UserInputError(
                "The integrated editor is limited to 500 rows to prevent an incomplete download. "
                "Edit this larger file in Excel or another approved CSV editor, then choose it again."
            )
        return {
            "success": True,
            "exitCode": 0,
            "output": f"Loaded {len(rows)} rows from {path.name}. The integrated row editor will use this session copy.",
            "data": {"headers": list(reader.fieldnames or []), "rows": rows, "fileLabel": label},
            "downloads": [],
        }

    if operation_key in {"prepare-user-files", "cleanup-users"}:
        config, _ = load_config()
        pcfg = provisioning(config)
        user_handle = str(files.get("User import CSV") or "")
        user_path = Path(file_value(state, files, "User import CSV"))
        snapshot_value = file_value(
            state,
            files,
            "Current Users snapshot",
            required=pcfg["require_existing_users_snapshot"],
        )
        snapshot_path = Path(snapshot_value) if snapshot_value else None
        state.require_user_preview(str(body.get("previewToken") or ""), user_path, snapshot_path)

        validation, classification, source_preview = analyze_user_file(
            user_path,
            snapshot_path,
            pcfg["require_existing_users_snapshot"],
        )
        if source_preview["fileErrors"]:
            raise UserInputError(
                "The source CSV has structural errors that cannot be removed safely: "
                + " ".join(source_preview["fileErrors"])
            )
        remove_blockers = bool(body.get("removeBlockers", True))
        remove_matches = bool(body.get("removeMatches", True))
        if not remove_blockers and not remove_matches:
            raise UserInputError("Choose at least one cleanup option before creating a clean copy.")

        blocked_rows = {row["sourceRow"] for row in source_preview["rows"] if row["blocked"]}
        match_rows = set(classification["update_rows"])
        removed_rows: set[int] = set()
        if remove_blockers:
            removed_rows.update(blocked_rows)
        if remove_matches:
            removed_rows.update(match_rows)
        output_headers, output_rows = csv_rows_for_output(user_path)
        kept_rows = [
            row
            for row_number, row in enumerate(output_rows, start=2)
            if row_number not in removed_rows
        ]

        source_name = state.upload_name(user_handle)
        requested_name = str(body.get("outputName") or fields.get("Clean CSV destination") or "").strip()
        default_name = f"{Path(source_name).stem or 'users'}_clean_create_only.csv"
        clean_name = safe_name(requested_name or default_name, default_name)
        if Path(clean_name).suffix.lower() != ".csv":
            clean_name = safe_name(f"{clean_name}.csv", default_name)
        clean_path = state.create_output_path(clean_name)
        write_csv_rows(clean_path, output_headers, kept_rows)
        session_file = state.register_session_file(clean_path, clean_name)

        _, _, clean_preview = analyze_user_file(
            clean_path,
            snapshot_path,
            pcfg["require_existing_users_snapshot"],
        )
        clean_preview["snapshotSha256"] = sha256_file(snapshot_path) if snapshot_path else ""
        clean_preview["previewToken"] = state.register_user_preview(clean_path, snapshot_path, clean_preview)

        downloads = export_user_preview_files(
            state,
            source_name,
            user_path,
            validation,
            classification,
            source_preview,
        )
        downloads.append(
            state.register_download(
                clean_path,
                kind="cleanCopy",
                display_name=clean_name,
                row_count=len(kept_rows),
            )
        )
        return {
            "success": not clean_preview["errors"],
            "exitCode": 0 if not clean_preview["errors"] else 2,
            "output": (
                f"Created {clean_name} with {len(kept_rows)} rows.\n"
                f"Removed {len(removed_rows)} unique rows: "
                f"{len(blocked_rows & removed_rows)} blocker rows and "
                f"{len(match_rows & removed_rows)} existing-match rows.\n"
                "The uploaded source CSV was not changed."
            ),
            "data": {
                "sessionFile": session_file,
                "preview": clean_preview,
                "sourceSha256": source_preview["sha256"],
                "originalUnchanged": sha256_file(user_path) == source_preview["sha256"],
                "removedRowCount": len(removed_rows),
                "removedBlockerCount": len(blocked_rows & removed_rows),
                "removedMatchCount": len(match_rows & removed_rows),
                "cleanRowCount": len(kept_rows),
            },
            "downloads": downloads,
        }

    functional_key = UI_TO_FUNCTIONAL.get(operation_key)
    if not functional_key:
        raise UserInputError("The selected function is not available in the integrated layer.")
    spec = OPERATIONS_BY_KEY[functional_key]
    config, config_exists = load_config()
    pcfg = provisioning(config)

    if operation_key in {"validate-users", "preview-users"}:
        user_handle = str(files.get("User import CSV") or "")
        user_path = Path(file_value(state, files, "User import CSV"))
        existing_path_value = file_value(
            state, files, "Current Users snapshot", required=operation_key == "preview-users" and pcfg["require_existing_users_snapshot"],
        )
        validation, classification, data = analyze_user_file(
            user_path,
            Path(existing_path_value) if existing_path_value else None,
            operation_key == "preview-users" and pcfg["require_existing_users_snapshot"],
        )
        if operation_key == "preview-users":
            snapshot_path = Path(existing_path_value) if existing_path_value else None
            data["snapshotSha256"] = sha256_file(snapshot_path) if snapshot_path else ""
            data["previewToken"] = state.register_user_preview(user_path, snapshot_path, data)
            downloads = export_user_preview_files(
                state,
                state.upload_name(user_handle),
                user_path,
                validation,
                classification,
                data,
            )
        return {
            "success": not data["errors"],
            "exitCode": 0 if not data["errors"] else 2,
            "output": text_user_result(data),
            "data": data,
            "downloads": downloads,
        }

    if operation_key in {"validate-groups", "preview-groups"}:
        group_path = Path(file_value(state, files, "Group assignment CSV"))
        groups_path = Path(file_value(state, files, "Current Groups snapshot"))
        users_value = file_value(state, files, "Current Users snapshot", required=False)
        pending_value = file_value(state, files, "User import CSV", required=False)
        result = validate_group_entities_csv(
            group_path,
            groups_path,
            Path(users_value) if users_value else None,
            Path(pending_value) if pending_value else None,
        )
        output_lines = [f"Rows: {len(result['rows'])}", f"SHA-256: {result['sha256']}"]
        output_lines.extend(f"WARNING: {value}" for value in result["warnings"])
        output_lines.extend(f"ERROR: {value}" for value in result["errors"])
        output_lines.append("Validation: " + ("PASS" if not result["errors"] else "FAIL"))
        return {
            "success": not result["errors"],
            "exitCode": 0 if not result["errors"] else 2,
            "output": "\n".join(output_lines),
            "data": {
                "rowCount": len(result["rows"]),
                "errors": result["errors"],
                "warnings": result["warnings"],
                "sha256": result["sha256"],
            },
            "downloads": [],
        }

    if not config_exists:
        raise UserInputError("Save the Axon Evidence tenant URL before running this function.")
    base_url = str(config.get("agency_base_url") or "")
    if "YOUR_AGENCY" in base_url or not base_url.startswith("https://"):
        raise UserInputError("Replace the placeholder with the Axon Evidence tenant HTTPS URL.")

    values: dict[str, str] = {"config": str(CONFIG_PATH)}
    if "user_csv" in spec.fields:
        values["user_csv"] = file_value(state, files, "User import CSV")
    if "existing_users" in spec.fields:
        values["existing_users"] = file_value(state, files, "Current Users snapshot")
    if "group_csv" in spec.fields:
        values["group_csv"] = file_value(state, files, "Group assignment CSV")
    if "groups_snapshot" in spec.fields:
        values["groups_snapshot"] = file_value(state, files, "Current Groups snapshot")
    if "users_snapshot" in spec.fields:
        values["users_snapshot"] = file_value(state, files, "Current Users snapshot", required=False)
    if "pending_users" in spec.fields:
        values["pending_users"] = file_value(state, files, "User import CSV", required=False)
    if "job_id" in spec.fields:
        job_label = "User job ID" if spec.key.startswith("user_") or "user" in spec.key else "Group job ID"
        values["job_id"] = str(fields.get(job_label) or "").strip()
    if "user_job_id" in spec.fields:
        values["user_job_id"] = str(fields.get("Successful user job ID") or "").strip()
    values["allow_updates"] = "yes" if body.get("allowUpdates") else ""
    if operation_key == "submit-users" and body.get("allowUpdates"):
        user_path = Path(values["user_csv"])
        snapshot_path = Path(values["existing_users"])
        preview = state.require_user_preview(
            str(body.get("previewToken") or ""),
            user_path,
            snapshot_path,
        )
        approved_value = body.get("approvedMatchCount")
        if isinstance(approved_value, bool) or not str(approved_value or "").strip().isdigit():
            raise UserInputError("Confirm the exact reviewed existing-account count before allowing updates.")
        approved_match_count = int(str(approved_value).strip())
        if preview["matchCount"] <= 0:
            raise UserInputError("This preview contains no existing accounts to update.")
        if approved_match_count != preview["matchCount"]:
            raise UserInputError(
                "The approved existing-account count does not match the latest preview. Run Preview Users again."
            )
        if preview["errors"] or preview["blockerCount"] or preview["fileErrors"]:
            raise UserInputError("Resolve all preview blockers before allowing updates to existing accounts.")

    if spec.write:
        if not body.get("confirmWrite"):
            raise UserInputError("Review the preview and explicitly approve the Axon-changing action.")
        confirm_agency = str(body.get("confirmAgency") or "").strip()
        if not confirm_agency or confirm_agency != state.partner_id():
            raise UserInputError("The confirmation Agency ID does not match this credential session.")
        values["execute"] = "yes"
        values["confirm_agency"] = confirm_agency

    if spec.command.endswith("job-results"):
        result_name = safe_name(f"{spec.command}_{values.get('job_id', 'results')}.json", "job_results.json")
        values["output"] = str(state.output_dir / result_name)

    environment = state.credential_env()
    command = build_command(BASE_DIR, spec, values)
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    refresh_id = ""
    refresh_owner = f"provisioning-center-{os.getpid()}"
    if spec.action == "sync":
        refresh_id = state.workspace.acquire_refresh_lease(spec.command, refresh_owner, {"type": "full", "filters": {}})
    try:
        completed = subprocess.run(
            command,
            cwd=BASE_DIR,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
            creationflags=creation_flags,
            check=False,
        )
    except Exception as exc:
        if refresh_id:
            state.workspace.release_refresh_lease(spec.command, refresh_owner, refresh_id, "failed", type(exc).__name__)
        raise

    if values.get("output") and Path(values["output"]).exists():
        downloads.append(state.register_download(Path(values["output"])))
    if spec.action == "sync" and completed.returncode == 0:
        resource = spec.command
        resource_config = dict(config.get("resources", {}).get(resource, {}))
        output_name = str(resource_config.get("output_csv") or "")
        if output_name:
            output_path = BASE_DIR / str(config.get("processed_dir", "data/processed")) / output_name
            if output_path.exists():
                downloads.append(state.register_download(output_path))
                with output_path.open("r", newline="", encoding="utf-8-sig") as handle:
                    snapshot_rows = list(csv.DictReader(handle))
                activated = state.workspace.activate_snapshot(resource, snapshot_rows, {"type": "full", "filters": {}}, "Axon API via Provisioning Center")
                state.workspace.release_refresh_lease(resource, refresh_owner, refresh_id, "completed", snapshot_id=activated["snapshotId"])
                refresh_id = ""
    if refresh_id:
        state.workspace.release_refresh_lease(spec.command, refresh_owner, refresh_id, "failed", f"Axon sync exit code {completed.returncode}")

    return {
        "success": completed.returncode == 0,
        "exitCode": completed.returncode,
        "output": completed.stdout.strip() or "Function completed without console output.",
        "command": display_command(command),
        "downloads": downloads,
    }


class LocalAxonHandler(BaseHTTPRequestHandler):
    server_version = "AxonBWCWeb/1.0.0"
    state: SessionState

    def log_message(self, format_string: str, *args: Any) -> None:
        # Request bodies and headers are intentionally excluded from logs.
        sys.stdout.write(f"[local-ui] {self.command} {self.path.split('?', 1)[0]}\n")

    def _valid_host(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        return host.startswith("127.0.0.1:") or host == "127.0.0.1" or host.startswith("localhost:") or host == "localhost"

    def _authorized(self) -> bool:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie") or "")
        except Exception:
            return False
        value = cookie.get(LOCAL_SESSION_COOKIE)
        return bool(value and hmac.compare_digest(value.value, self.state.local_token))

    def _accept_launch(self, parsed: Any) -> bool:
        supplied = (parse_qs(parsed.query).get("launch") or [""])[0]
        if not supplied or not hmac.compare_digest(supplied, self.state.local_token):
            return False
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            f"{LOCAL_SESSION_COOKIE}={self.state.local_token}; HttpOnly; SameSite=Strict; Path=/",
        )
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        return True

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
        )

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        content = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        self.wfile.write(content)

    def _error(self, status: int, message: str) -> None:
        self._send_json(status, {"success": False, "error": message})

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise UserInputError("Invalid request size.") from exc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise UserInputError("Request is empty or exceeds the local size limit.")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise UserInputError("Request body must be valid JSON.") from exc
        if not isinstance(payload, dict):
            raise UserInputError("Request body must be a JSON object.")
        return payload

    def _require_local_post(self) -> bool:
        if self.headers.get(LOCAL_UI_HEADER) != "1":
            self._error(HTTPStatus.FORBIDDEN, "Missing local UI request header.")
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        if not self._valid_host():
            self._error(HTTPStatus.FORBIDDEN, "Host is not allowed.")
            return
        parsed = urlparse(self.path)
        if parsed.path == "/" and self._accept_launch(parsed):
            return
        if not self._authorized():
            self._error(HTTPStatus.UNAUTHORIZED, "This local desktop session is not authorized. Launch the application again.")
            return
        if parsed.path == "/api/health":
            self._send_json(HTTPStatus.OK, {
                "success": True,
                "version": VERSION,
                "staticReady": STATIC_DIR.exists(),
                "productionMode": True,
                "audit": verify_chain(),
            })
            return
        if parsed.path == "/api/session":
            self._send_json(HTTPStatus.OK, {"success": True, **self.state.session_status()})
            return
        if parsed.path == "/api/config":
            try:
                self._send_json(HTTPStatus.OK, {"success": True, **public_config()})
            except Exception as exc:  # configuration file is local and error text contains no secrets
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        if parsed.path == "/api/workspace/status":
            self._send_json(HTTPStatus.OK, {"success": True, **self.state.workspace.status()})
            return
        refresh_match = re.fullmatch(r"/api/workspace/refresh/([^/]+)", parsed.path)
        if refresh_match:
            try:
                job = self.state.refresh_job(unquote(refresh_match.group(1)))
                self._send_json(HTTPStatus.OK, {"success": True, "job": job})
            except UserInputError as exc:
                self._error(HTTPStatus.NOT_FOUND, str(exc))
            return
        if parsed.path == "/api/runs/latest":
            self._send_json(HTTPStatus.OK, {"success": True, "run": self.state.workspace.latest_run()})
            return
        if parsed.path.startswith("/api/runs/") and parsed.path.count("/") == 3:
            run_id = unquote(parsed.path.rsplit("/", 1)[-1])
            try:
                self._send_json(HTTPStatus.OK, {"success": True, "run": self.state.workspace.get_run(run_id)})
            except KeyError as exc:
                self._error(HTTPStatus.NOT_FOUND, str(exc))
            return
        if parsed.path.startswith("/api/download/"):
            handle = parsed.path.rsplit("/", 1)[-1]
            path = self.state.resolve_download(handle)
            if not path:
                self._error(HTTPStatus.NOT_FOUND, "Generated file is no longer available in this session.")
                return
            content = path.read_bytes()
            download_name = self.state.download_name(handle, path.name)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mimetypes.guess_type(download_name)[0] or "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{safe_name(download_name)}"')
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            self.end_headers()
            self.wfile.write(content)
            return
        if parsed.path.startswith("/api/"):
            self._error(HTTPStatus.NOT_FOUND, "Local API route not found.")
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        if not self._valid_host() or not self._authorized() or not self._require_local_post():
            if not self._valid_host():
                self._error(HTTPStatus.FORBIDDEN, "Host is not allowed.")
            elif not self._authorized():
                self._error(HTTPStatus.UNAUTHORIZED, "This local desktop session is not authorized.")
            return
        path = urlparse(self.path).path
        try:
            body = self._read_json()
            if path == "/api/session/credentials":
                self.state.set_credentials(body.get("partnerId", ""), body.get("clientId", ""), body.get("clientSecret", ""))
                self._send_json(HTTPStatus.OK, {"success": True, **self.state.session_status()})
                return
            if path == "/api/config":
                self._send_json(HTTPStatus.OK, {"success": True, **save_public_config(body)})
                return
            if path == "/api/app/shutdown":
                self.state.clear_credentials()
                append_event("provisioning-center", "application-stop-requested", "success")
                self._send_json(HTTPStatus.OK, {"success": True, "message": "The local desktop service is stopping."})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if path == "/api/files":
                try:
                    content = base64.b64decode(str(body.get("contentBase64") or ""), validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise UserInputError("Selected file could not be decoded.") from exc
                handle, file_path = self.state.save_upload(str(body.get("name") or "upload.csv"), content)
                count = csv_row_count(file_path)
                detail = f"{count} rows" if count is not None else f"{len(content)} bytes"
                self._send_json(HTTPStatus.OK, {
                    "success": True,
                    "handle": handle,
                    "name": Path(str(body.get("name") or file_path.name)).name,
                    "size": len(content),
                    "detail": detail,
                })
                return
            if path == "/api/runs/intake/detect":
                handle = str(body.get("fileHandle") or "")
                headers, _rows = rows_from_session_file(self.state, handle)
                self._send_json(HTTPStatus.OK, {"success": True, "headers": headers, **detect_columns(headers)})
                return
            if path == "/api/runs":
                result = provisioning_run_payload(self.state, body)
                self._send_json(HTTPStatus.OK, {"success": True, "run": result})
                return
            if path == "/api/workspace/refresh":
                job = self.state.start_shared_refresh(str(body.get("resource") or ""), dict(body.get("filters") or {}))
                self._send_json(HTTPStatus.ACCEPTED, {"success": True, "job": job})
                return
            refresh_cancel_match = re.fullmatch(r"/api/workspace/refresh/([^/]+)/cancel", path)
            if refresh_cancel_match:
                job = self.state.cancel_refresh(unquote(refresh_cancel_match.group(1)))
                self._send_json(HTTPStatus.OK, {"success": True, "job": job})
                return
            run_match = re.fullmatch(r"/api/runs/([^/]+)/(edit|approve|export|submit-next|track|purge)", path)
            if run_match:
                run_id = unquote(run_match.group(1))
                action = run_match.group(2)
                if action == "edit":
                    run = revise_provisioning_run(self.state, run_id, body)
                    self._send_json(HTTPStatus.OK, {"success": True, "run": run})
                    return
                if action == "approve":
                    run = self.state.workspace.approve_preview(
                        run_id,
                        int(body.get("expectedRevision", -1)),
                        bool(body.get("approveUpdates")),
                        int(body.get("updateCount", 0)),
                    )
                    self._send_json(HTTPStatus.OK, {"success": True, "run": run, "message": "Updates approved for submission. Nothing has been submitted to Axon yet."})
                    return
                if action == "export":
                    run = self.state.workspace.get_run(run_id)
                    if int(body.get("expectedRevision", -1)) != run["revision"]:
                        raise RevisionConflict(f"Run revision {body.get('expectedRevision')} is stale; current revision is {run['revision']}.")
                    output = export_run_package(run, self.state.output_dir)
                    download = self.state.register_download(output, kind="runPackage", display_name=output.name)
                    self._send_json(HTTPStatus.OK, {"success": True, "download": download})
                    return
                if action == "submit-next":
                    result = submit_next_run_chunk(self.state, run_id, body)
                    self._send_json(HTTPStatus.OK, {"success": True, **result})
                    return
                if action == "track":
                    result = track_run_jobs(self.state, run_id, body)
                    self._send_json(HTTPStatus.OK, {"success": True, **result})
                    return
                if action == "purge":
                    if str(body.get("confirmRunId") or "") != run_id:
                        raise UserInputError("Type the exact run ID to confirm this local purge.")
                    result = self.state.workspace.purge_run(run_id, int(body.get("expectedRevision", -1)))
                    self._send_json(HTTPStatus.OK, {"success": True, "purged": result})
                    return
            if path == "/api/operations/run":
                result = execute_operation(self.state, body)
                self._send_json(HTTPStatus.OK, result)
                return
            self._error(HTTPStatus.NOT_FOUND, "Local API route not found.")
        except (RevisionConflict, RefreshLeaseConflict) as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except (UserInputError, WorkflowError, ValueError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except subprocess.TimeoutExpired:
            self._error(HTTPStatus.REQUEST_TIMEOUT, "The function exceeded the 30-minute local timeout and was stopped.")
        except Exception as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Local function failed: {exc}")

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._valid_host() or not self._authorized() or not self._require_local_post():
            if not self._valid_host():
                self._error(HTTPStatus.FORBIDDEN, "Host is not allowed.")
            elif not self._authorized():
                self._error(HTTPStatus.UNAUTHORIZED, "This local desktop session is not authorized.")
            return
        if urlparse(self.path).path == "/api/session/credentials":
            self.state.clear_credentials()
            self._send_json(HTTPStatus.OK, {"success": True, **self.state.session_status()})
            return
        self._error(HTTPStatus.NOT_FOUND, "Local API route not found.")

    def _serve_static(self, request_path: str) -> None:
        if not STATIC_DIR.exists():
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "The web build is missing. Run npm run build once.")
            return
        relative = unquote(request_path).lstrip("/") or "index.html"
        candidate = (STATIC_DIR / relative).resolve()
        static_root = STATIC_DIR.resolve()
        if candidate != static_root and static_root not in candidate.parents:
            self._error(HTTPStatus.FORBIDDEN, "Invalid static path.")
            return
        if not candidate.is_file():
            candidate = STATIC_DIR / "index.html"
        content = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(candidate.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store" if candidate.name == "index.html" else "public, max-age=3600")
        self._security_headers()
        self.end_headers()
        self.wfile.write(content)


def make_server(port: int, state: SessionState, auto_port: bool = False) -> ThreadingHTTPServer:
    handler = type("BoundLocalAxonHandler", (LocalAxonHandler,), {"state": state})
    candidates = range(port, min(port + 11, 65536)) if auto_port else [port]
    last_error: OSError | None = None
    for candidate in candidates:
        try:
            return ThreadingHTTPServer(("127.0.0.1", candidate), handler)
        except OSError as exc:
            last_error = exc
            if not auto_port or exc.errno != errno.EADDRINUSE:
                raise
    raise OSError(
        errno.EADDRINUSE,
        f"No available loopback port was found from {port} through {min(port + 10, 65535)}.",
    ) from last_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8797)
    parser.add_argument("--auto-port", action="store_true", default=bool(getattr(sys, "frozen", False)), help="Use the next available loopback port when the requested port is occupied.")
    parser.add_argument("--open", action="store_true", default=bool(getattr(sys, "frozen", False)), help="Open the local UI in the default browser.")
    parser.add_argument("--no-open", action="store_false", dest="open", help=argparse.SUPPRESS)
    parser.add_argument("--no-auto-port", action="store_false", dest="auto_port", help=argparse.SUPPRESS)
    args, _unknown = parser.parse_known_args()
    instance_lock = SingleInstanceLock("provisioning-center")
    if not instance_lock.acquire():
        show_error("Axon BWC Provisioning Center", "The application is already running for this user.")
        return 3
    initialized = initialize_governance_files(
        __file__,
        [
            "axon_group_crosswalk_starter.csv",
            "axon_group_master_starter.csv",
            "device_home_crosswalk_starter.csv",
            "device_status_map.csv",
            "approved_axon_role_catalog.csv",
            "personnel_location_aor_crosswalk.csv",
            "job_title_category_mapping.csv",
            "component_aor_group_rules.csv",
            "directory_attribute_mapping.csv",
        ],
    )
    append_event(
        "provisioning-center",
        "application-started",
        "success",
        {"version": VERSION, "initializedGovernanceFiles": len(initialized)},
    )
    state = SessionState()
    server = make_server(args.port, state, auto_port=args.auto_port)
    selected_port = int(server.server_address[1])
    url = f"http://127.0.0.1:{selected_port}/"
    launch_url = f"{url}?launch={state.local_token}"
    print(f"Axon BWC Provisioning Center v{VERSION}")
    print(f"Local address: {url}")
    if selected_port != args.port:
        print(f"Port {args.port} was already in use; selected the next available local port.")
    print("Credentials remain only in this process and are cleared when it exits.")
    if args.open:
        threading.Timer(0.35, lambda: webbrowser.open(launch_url)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping local UI.")
    finally:
        server.server_close()
        state.close()
        append_event("provisioning-center", "application-stopped", "success", {"version": VERSION})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
