#!/usr/bin/env python3
"""Guarded Axon Evidence bulk user and group-membership provisioning application.

This tool deliberately separates validation/preview from write submission.  The
write commands are disabled in configuration by default and require an explicit
--execute flag plus an agency-ID confirmation.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from audit_store import append_event

USER_AGENT = "Axon-BWC-Provisioning-Center/1.0.0"
USER_HEADERS = [
    "EXTERNAL_ID", "EMAIL", "BADGE_NUMBER", "FIRST_NAME", "LAST_NAME",
    "STATUS", "USERNAME", "ROLE", "SUPERVISOR_EMAIL", "LOCATION",
    "EVIDENCE_GROUP_EXT_ID", "PHONE",
]
OPTIONAL_USER_HEADERS = ["RANK"]
GROUP_ENTITY_HEADERS = ["EXTERNAL_ID", "MEMBERSHIP_TYPE", "ENTITY_TYPE", "ENTITY_ID"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def resolved_agency_id(config: dict[str, Any]) -> str:
    env_name = str(config.get("partner_id_env", "AXON_PARTNER_ID"))
    return os.environ.get(env_name, "") or str(config.get("agency_id", ""))


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise ValueError(f"CSV does not exist: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = [str(h or "").strip() for h in (reader.fieldnames or [])]
        rows = []
        for raw in reader:
            if not any(str(v or "").strip() for v in raw.values()):
                continue
            rows.append({str(k or "").strip(): str(v or "").strip() for k, v in raw.items()})
    return headers, rows


def require_headers(actual: Iterable[str], required: Iterable[str]) -> list[str]:
    have = set(actual)
    return [h for h in required if h not in have]


def duplicate_values(rows: list[dict[str, str]], column: str) -> list[str]:
    counts = collections.Counter(
        (r.get(column) or "").casefold() for r in rows if (r.get(column) or "").strip()
    )
    return sorted(v for v, count in counts.items() if count > 1)


def validate_user_csv(path: Path) -> dict[str, Any]:
    headers, rows = load_csv(path)
    errors: list[str] = []
    warnings: list[str] = []
    if path.read_bytes().startswith(b"\xef\xbb\xbf"):
        errors.append("The Axon user-import CSV must be UTF-8 without a byte-order mark (BOM).")
    missing = require_headers(headers, USER_HEADERS)
    if missing:
        errors.append("Missing required headers: " + ", ".join(missing))
    unexpected = sorted(set(headers) - set(USER_HEADERS) - set(OPTIONAL_USER_HEADERS))
    if unexpected:
        errors.append("Unexpected headers: " + ", ".join(unexpected))
    if not rows:
        errors.append("The user CSV contains no data rows.")

    for idx, row in enumerate(rows, start=2):
        email = row.get("EMAIL", "")
        status = row.get("STATUS", "")
        if not email or not EMAIL_RE.match(email):
            errors.append(f"Row {idx}: EMAIL is missing or invalid.")
        if not row.get("FIRST_NAME"):
            errors.append(f"Row {idx}: FIRST_NAME is required.")
        if not row.get("LAST_NAME"):
            errors.append(f"Row {idx}: LAST_NAME is required.")
        if not row.get("USERNAME"):
            errors.append(f"Row {idx}: USERNAME is required.")
        if not row.get("ROLE"):
            errors.append(f"Row {idx}: ROLE is required and must match an existing Axon role.")
        if status.casefold() not in {"active", "inactive"}:
            errors.append(f"Row {idx}: STATUS must be Active or Inactive.")
        supervisor = row.get("SUPERVISOR_EMAIL", "")
        if supervisor and not EMAIL_RE.match(supervisor):
            errors.append(f"Row {idx}: SUPERVISOR_EMAIL is invalid.")
        if not row.get("EXTERNAL_ID"):
            warnings.append(
                f"Row {idx}: EXTERNAL_ID is blank; Axon may generate one, reducing source-system traceability."
            )
        elif len(row["EXTERNAL_ID"]) > 255:
            errors.append(f"Row {idx}: EXTERNAL_ID exceeds 255 characters.")

    for column in ("EXTERNAL_ID", "EMAIL", "BADGE_NUMBER", "USERNAME"):
        dupes = duplicate_values(rows, column)
        if dupes:
            errors.append(f"Duplicate {column} values in input: {', '.join(dupes[:10])}")

    return {
        "path": str(path), "headers": headers, "rows": rows,
        "errors": errors, "warnings": warnings, "sha256": sha256_file(path),
    }


def index_existing_users(path: Path | None) -> dict[str, dict[str, dict[str, str]]]:
    indexes = {"external": {}, "email": {}, "badge": {}}
    if path is None:
        return indexes
    _, rows = load_csv(path)
    for row in rows:
        for key, column in (("external", "External ID"), ("email", "Email"), ("badge", "Badge ID")):
            value = (row.get(column) or "").strip().casefold()
            if value:
                indexes[key][value] = row
    return indexes


def classify_users(rows: list[dict[str, str]], existing_path: Path | None) -> dict[str, Any]:
    indexes = index_existing_users(existing_path)
    create_rows: list[int] = []
    update_rows: list[int] = []
    conflicts: list[str] = []

    for idx, row in enumerate(rows, start=2):
        matches: list[dict[str, str]] = []
        for key, column in (("external", "EXTERNAL_ID"), ("email", "EMAIL"), ("badge", "BADGE_NUMBER")):
            value = (row.get(column) or "").strip().casefold()
            if value and value in indexes[key]:
                matches.append(indexes[key][value])
        distinct = {m.get("Axon User ID") or m.get("Email") or json.dumps(m, sort_keys=True) for m in matches}
        if len(distinct) > 1:
            conflicts.append(f"Row {idx}: identifiers match more than one existing Axon account.")
        elif matches:
            update_rows.append(idx)
        else:
            create_rows.append(idx)

    return {"create_rows": create_rows, "update_rows": update_rows, "conflicts": conflicts}


def validate_group_entities_csv(
    path: Path,
    groups_csv: Path | None = None,
    users_csv: Path | None = None,
    pending_users_csv: Path | None = None,
) -> dict[str, Any]:
    headers, rows = load_csv(path)
    errors: list[str] = []
    warnings: list[str] = []
    missing = require_headers(headers, GROUP_ENTITY_HEADERS)
    if missing:
        errors.append("Missing required headers: " + ", ".join(missing))
    unexpected = sorted(set(headers) - set(GROUP_ENTITY_HEADERS))
    if unexpected:
        errors.append("Unexpected headers: " + ", ".join(unexpected))
    if not rows:
        errors.append("The group-entity CSV contains no data rows.")

    group_ids: set[str] = set()
    if groups_csv:
        _, group_rows = load_csv(groups_csv)
        for row in group_rows:
            value = row.get("External Group ID") or row.get("EXTERNAL_ID") or ""
            if value.strip():
                group_ids.add(value.strip().casefold())

    user_emails: set[str] = set()
    if users_csv:
        _, user_rows = load_csv(users_csv)
        for row in user_rows:
            value = row.get("Email") or row.get("EMAIL") or ""
            if value.strip():
                user_emails.add(value.strip().casefold())
    if pending_users_csv:
        pending = validate_user_csv(pending_users_csv)
        if pending["errors"]:
            errors.append("Pending-user CSV is invalid; validate it separately before group assignment.")
        for row in pending["rows"]:
            if row.get("EMAIL"):
                user_emails.add(row["EMAIL"].casefold())

    seen: set[tuple[str, str, str, str]] = set()
    for idx, row in enumerate(rows, start=2):
        group_id = row.get("EXTERNAL_ID", "")
        membership_type = row.get("MEMBERSHIP_TYPE", "")
        entity_type = row.get("ENTITY_TYPE", "")
        membership_type_normalized = membership_type.upper()
        entity_type_normalized = entity_type.upper()
        entity_id = row.get("ENTITY_ID", "")
        if not group_id:
            errors.append(f"Row {idx}: EXTERNAL_ID is required.")
        elif len(group_id) > 255:
            errors.append(f"Row {idx}: EXTERNAL_ID exceeds 255 characters.")
        if membership_type_normalized not in {"MEMBER", "MONITOR"}:
            errors.append(f"Row {idx}: MEMBERSHIP_TYPE must be MEMBER or MONITOR (case-insensitive).")
        if entity_type_normalized not in {"USER", "GROUP"}:
            errors.append(f"Row {idx}: ENTITY_TYPE must be USER or GROUP (case-insensitive).")
        if not entity_id:
            errors.append(f"Row {idx}: ENTITY_ID is required.")
        if groups_csv and group_id.casefold() not in group_ids:
            errors.append(f"Row {idx}: target group external ID was not found in the Groups snapshot.")
        if entity_type_normalized == "GROUP" and groups_csv and entity_id.casefold() not in group_ids:
            errors.append(f"Row {idx}: member/monitor group external ID was not found in the Groups snapshot.")
        if entity_type_normalized == "USER":
            if not EMAIL_RE.match(entity_id):
                errors.append(f"Row {idx}: USER ENTITY_ID must be an email address.")
            elif (users_csv or pending_users_csv) and entity_id.casefold() not in user_emails:
                errors.append(f"Row {idx}: user email was not found in existing or pending-user snapshots.")
        key = (group_id.casefold(), membership_type_normalized, entity_type_normalized, entity_id.casefold())
        if key in seen:
            errors.append(f"Row {idx}: duplicate group-entity assignment.")
        seen.add(key)

    if not groups_csv:
        warnings.append("No Groups snapshot supplied; external group IDs were not verified.")
    if not users_csv and not pending_users_csv:
        warnings.append("No Users snapshot supplied; user email entities were not verified.")

    return {
        "path": str(path), "headers": headers, "rows": rows,
        "errors": errors, "warnings": warnings, "sha256": sha256_file(path),
    }


def get_path(obj: Any, path: str) -> Any:
    current = obj
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for path in ("data", "value", "items", "results"):
        value = get_path(payload, path)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def find_status(payload: Any) -> str:
    for path in ("status", "data.status", "attributes.status", "job.status", "data.attributes.status"):
        value = get_path(payload, path)
        if value not in (None, ""):
            return str(value)
    return "unknown"


def find_job_id(payload: Any) -> str:
    for path in ("jobId", "job_id", "id", "data.id", "data.jobId", "attributes.jobId", "data.attributes.jobId"):
        value = get_path(payload, path)
        if value not in (None, ""):
            return str(value)
    return "unknown"


class AxonProvisionClient:
    def __init__(self, config: dict[str, Any]):
        self.base_url = str(config["agency_base_url"]).rstrip("/")
        self.agency_id = resolved_agency_id(config)
        self.client_id = os.environ.get(config.get("client_id_env", "AXON_CLIENT_ID"), "")
        self.client_secret = os.environ.get(config.get("client_secret_env", "AXON_CLIENT_SECRET"), "")
        self.timeout = int(config.get("timeout_seconds", 90))
        self.access_token = ""

    def authenticate(self) -> None:
        if not self.agency_id:
            raise RuntimeError("Axon Partner/Agency ID is not present in the configured environment variable.")
        if not self.client_id or not self.client_secret:
            raise RuntimeError("Axon API credentials are not present in the configured environment variables.")
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/api/oauth2/token", data=body, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OAuth token request failed: HTTP {exc.code}: {detail[:800]}") from exc
        self.access_token = str(payload.get("access_token") or "")
        if not self.access_token:
            raise RuntimeError("Token response did not include access_token.")

    def url(self, endpoint: str) -> str:
        endpoint = endpoint.replace("{agency_id}", self.agency_id).replace("{agencyId}", self.agency_id)
        return self.base_url + "/" + endpoint.lstrip("/")

    def get_json(self, endpoint: str, params: dict[str, Any] | None = None, max_retries: int = 5) -> Any:
        url = self.url(endpoint)
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            url += ("&" if "?" in url else "?") + query
        for attempt in range(max_retries + 1):
            request = urllib.request.Request(
                url, method="GET",
                headers={"Authorization": f"Bearer {self.access_token}", "Accept": "application/json", "User-Agent": USER_AGENT},
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < max_retries:
                    retry_after = exc.headers.get("Retry-After")
                    try:
                        wait = max(1, int(retry_after))
                    except (TypeError, ValueError):
                        wait = 300
                    print(f"HTTP 429; waiting {wait}s before retry.")
                    time.sleep(wait)
                    continue
                if 500 <= exc.code < 600 and attempt < max_retries:
                    wait = min(60, 2 ** attempt)
                    print(f"HTTP {exc.code}; retrying GET after {wait}s.")
                    time.sleep(wait)
                    continue
                detail = exc.read().decode("utf-8", errors="replace")
                if exc.code == 404:
                    raise RuntimeError(
                        f"GET failed: HTTP 404: {detail[:1200]}\n"
                        "Do not resubmit a write because of this response. List jobs and verify the exact returned job ID first."
                    ) from exc
                raise RuntimeError(f"GET failed: HTTP {exc.code}: {detail[:1200]}") from exc
        raise RuntimeError("GET retry budget exhausted.")

    def post_csv_once(
        self, endpoint: str, file_path: Path, field_name: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Submit exactly once. Automatic retries are unsafe for ambiguous write failures."""
        url = self.url(endpoint)
        if params:
            query = urllib.parse.urlencode({k: str(v).lower() if isinstance(v, bool) else v for k, v in params.items()})
            url += ("&" if "?" in url else "?") + query
        boundary = "----AxonBWC" + uuid.uuid4().hex
        prefix = (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"{field_name}\"; filename=\"{file_path.name}\"\r\n"
            "Content-Type: text/csv\r\n\r\n"
        ).encode("utf-8")
        body = prefix + file_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
        request = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"POST failed: HTTP {exc.code}: {detail[:1500]}\n"
                "The write was not retried automatically. Check the corresponding job list before resubmitting."
            ) from exc


def provisioning(config: dict[str, Any]) -> dict[str, Any]:
    p = dict(config.get("provisioning", {}))
    p.setdefault("write_operations_enabled", False)
    p.setdefault("require_existing_users_snapshot", True)
    p.setdefault("audit_log_csv", "state/provisioning_audit.csv")
    p.setdefault("user_import_file_field", "users_file")
    p.setdefault("group_entities_file_field", "entities_file")
    p.setdefault("group_entities_file_field_confirmed", False)
    p.setdefault("endpoints", {})
    endpoints = p["endpoints"]
    endpoints.setdefault("user_import", "/api/v4/agencies/{agency_id}/users/import")
    endpoints.setdefault("user_jobs", "/api/v4/agencies/{agency_id}/users/import/status")
    endpoints.setdefault("user_job_status", "/api/v4/agencies/{agency_id}/users/import/{job_id}/status")
    endpoints.setdefault("user_job_results", "/api/v4/agencies/{agency_id}/users/import/{job_id}/results")
    endpoints.setdefault("group_entities_import", "/api/v2/agencies/{agency_id}/groups/import/entities")
    endpoints.setdefault("group_jobs", "/api/v2/agencies/{agency_id}/groups/import")
    endpoints.setdefault("group_job_status", "/api/v2/agencies/{agency_id}/groups/import/{job_id}")
    endpoints.setdefault("group_job_results", "/api/v2/agencies/{agency_id}/groups/import/{job_id}/results")
    return p


def endpoint(pcfg: dict[str, Any], name: str, job_id: str | None = None) -> str:
    value = str(pcfg["endpoints"][name])
    if job_id is not None:
        value = value.replace("{job_id}", urllib.parse.quote(job_id, safe=""))
    return value


def audit(config: dict[str, Any], operation: str, mode: str, csv_path: Path | None,
          row_count: int, job_id: str, status: str, notes: str = "") -> None:
    pcfg = provisioning(config)
    path = Path(pcfg["audit_log_csv"])
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["Timestamp", "Operation", "Mode", "Agency ID", "CSV Path", "CSV SHA256",
               "Record Count", "Job ID", "Status", "Notes"]
    row = {
        "Timestamp": utc_now(), "Operation": operation, "Mode": mode,
        "Agency ID": resolved_agency_id(config), "CSV Path": str(csv_path or ""),
        "CSV SHA256": sha256_file(csv_path) if csv_path and csv_path.exists() else "",
        "Record Count": row_count, "Job ID": job_id, "Status": status, "Notes": notes[:1000],
    }
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if new_file:
            writer.writeheader()
        writer.writerow(row)
    append_event(
        "provisioning-center",
        "axon-write-submitted",
        "success",
        {
            "operation": operation,
            "mode": mode,
            "csvSha256": row["CSV SHA256"],
            "recordCount": row_count,
            "jobId": job_id,
            "status": status,
        },
    )


def print_validation(result: dict[str, Any]) -> None:
    print(f"Rows: {len(result['rows'])}")
    print(f"SHA-256: {result['sha256']}")
    for warning in result["warnings"]:
        print(f"WARNING: {warning}")
    for error in result["errors"]:
        print(f"ERROR: {error}")
    print("Validation: " + ("PASS" if not result["errors"] else "FAIL"))


def print_user_preview(result: dict[str, Any], classification: dict[str, Any]) -> None:
    print_validation(result)
    print(f"Create candidates: {len(classification['create_rows'])}")
    print(f"Existing/update candidates: {len(classification['update_rows'])}")
    for conflict in classification["conflicts"]:
        print(f"ERROR: {conflict}")
    roles = collections.Counter(r.get("ROLE", "") for r in result["rows"])
    statuses = collections.Counter(r.get("STATUS", "") for r in result["rows"])
    print("Roles: " + ", ".join(f"{k}={v}" for k, v in sorted(roles.items())))
    print("Statuses: " + ", ".join(f"{k}={v}" for k, v in sorted(statuses.items())))


def print_group_preview(result: dict[str, Any]) -> None:
    print_validation(result)
    by_type = collections.Counter((r.get("MEMBERSHIP_TYPE", ""), r.get("ENTITY_TYPE", "")) for r in result["rows"])
    groups = {r.get("EXTERNAL_ID", "") for r in result["rows"]}
    print(f"Target groups: {len(groups)}")
    print("Assignments: " + ", ".join(f"{a}/{b}={n}" for (a, b), n in sorted(by_type.items())))


def require_write_gate(config: dict[str, Any], args: argparse.Namespace) -> None:
    pcfg = provisioning(config)
    if not pcfg["write_operations_enabled"]:
        raise RuntimeError("Write operations are disabled in config.json (provisioning.write_operations_enabled=false).")
    if not args.execute:
        raise RuntimeError("Write command requires --execute.")
    agency_id = resolved_agency_id(config)
    if not agency_id:
        raise RuntimeError("The configured Partner/Agency ID environment variable is empty.")
    if args.confirm_agency != agency_id:
        raise RuntimeError("--confirm-agency must exactly match the active AXON_PARTNER_ID value.")


def fetch_job_results(client: AxonProvisionClient, endpoint_value: str, output: Path | None) -> None:
    records: list[dict[str, Any]] = []
    offset = 0
    while True:
        payload = client.get_json(endpoint_value, {"limit": 500, "offset": offset})
        page = extract_records(payload)
        if not page:
            if not records and output:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            break
        records.extend(page)
        if len(page) < 500:
            break
        offset += len(page)
    actions = collections.Counter(str(r.get("action") or get_path(r, "attributes.action") or "Unknown") for r in records)
    errors = collections.Counter(str(r.get("errorCode") or get_path(r, "attributes.errorCode") or "") for r in records)
    print(f"Result rows: {len(records)}")
    print("Actions: " + (", ".join(f"{k}={v}" for k, v in sorted(actions.items())) or "none"))
    nonempty_errors = {k: v for k, v in errors.items() if k}
    print("Errors: " + (", ".join(f"{k}={v}" for k, v in sorted(nonempty_errors.items())) or "none"))
    if output and records:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(f"Detailed results written to {output} (may contain PII).")


def build_parser() -> argparse.ArgumentParser:
    commands = [
        "validate-users", "preview-users", "submit-users", "list-user-jobs",
        "user-job-status", "user-job-results", "validate-group-entities",
        "preview-group-entities", "submit-group-entities", "list-group-jobs",
        "group-job-status", "group-job-results",
    ]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=commands)
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--csv")
    parser.add_argument("--existing-users-csv")
    parser.add_argument("--groups-csv")
    parser.add_argument("--users-csv")
    parser.add_argument("--pending-users-csv")
    parser.add_argument("--job-id")
    parser.add_argument("--user-job-id")
    parser.add_argument("--output")
    parser.add_argument("--allow-updates", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-agency")
    return parser


def required_path(value: str | None, label: str) -> Path:
    if not value:
        raise ValueError(f"{label} is required.")
    return Path(value)


def main() -> int:
    args = build_parser().parse_args()
    config = load_json(Path(args.config))
    pcfg = provisioning(config)

    try:
        if args.command in {"validate-users", "preview-users", "submit-users"}:
            csv_path = required_path(args.csv, "--csv")
            result = validate_user_csv(csv_path)
            existing_path = Path(args.existing_users_csv) if args.existing_users_csv else None
            classification = classify_users(result["rows"], existing_path)
            print_user_preview(result, classification)
            all_errors = list(result["errors"]) + list(classification["conflicts"])
            if args.command == "validate-users":
                return 0 if not all_errors else 2
            if pcfg["require_existing_users_snapshot"] and not existing_path:
                all_errors.append("A recent --existing-users-csv snapshot is required by configuration.")
            if classification["update_rows"] and not args.allow_updates:
                all_errors.append("Existing/update candidates are present; create-only mode blocks submission.")
            if args.command == "preview-users":
                for error in all_errors:
                    print(f"ERROR: {error}")
                return 0 if not all_errors else 2
            if all_errors:
                raise RuntimeError("Submission blocked: " + " ".join(all_errors))
            require_write_gate(config, args)
            client = AxonProvisionClient(config)
            client.authenticate()
            payload = client.post_csv_once(
                endpoint(pcfg, "user_import"), csv_path, pcfg["user_import_file_field"],
                {"synchronize": False, "synchronizeEvidenceGroups": False},
            )
            job_id = find_job_id(payload)
            print(f"User import submitted once. Job ID: {job_id}")
            audit(config, "User import", "Execute", csv_path, len(result["rows"]), job_id, "Submitted")
            return 0

        if args.command in {"validate-group-entities", "preview-group-entities", "submit-group-entities"}:
            csv_path = required_path(args.csv, "--csv")
            groups_path = Path(args.groups_csv) if args.groups_csv else None
            users_path = Path(args.users_csv) if args.users_csv else None
            pending_path = Path(args.pending_users_csv) if args.pending_users_csv else None
            result = validate_group_entities_csv(csv_path, groups_path, users_path, pending_path)
            print_group_preview(result)
            if args.command == "validate-group-entities":
                return 0 if not result["errors"] else 2
            required_errors = list(result["errors"])
            if not groups_path:
                required_errors.append("A recent --groups-csv snapshot is required for group submission.")
            if not users_path and not pending_path:
                required_errors.append("A Users snapshot or pending-user CSV is required for group submission.")
            if args.command == "preview-group-entities":
                for error in required_errors:
                    print(f"ERROR: {error}")
                return 0 if not required_errors else 2
            if required_errors:
                raise RuntimeError("Submission blocked: " + " ".join(required_errors))
            if not pcfg["group_entities_file_field_confirmed"]:
                raise RuntimeError(
                    "Group submission is blocked until provisioning.group_entities_file_field_confirmed=true "
                    "after verifying the multipart field name in the authorized Axon API Explorer."
                )
            require_write_gate(config, args)
            client = AxonProvisionClient(config)
            client.authenticate()
            if pending_path:
                if not args.user_job_id:
                    raise RuntimeError("--user-job-id is required when assigning users from a pending-user CSV.")
                status_payload = client.get_json(endpoint(pcfg, "user_job_status", args.user_job_id))
                if find_status(status_payload).casefold() != "success":
                    raise RuntimeError("The referenced user-import job is not successful; group assignment is blocked.")
            payload = client.post_csv_once(
                endpoint(pcfg, "group_entities_import"), csv_path, pcfg["group_entities_file_field"]
            )
            job_id = find_job_id(payload)
            print(f"Group-entity import submitted once. Job ID: {job_id}")
            audit(config, "Group entity import", "Execute", csv_path, len(result["rows"]), job_id, "Submitted")
            return 0

        client = AxonProvisionClient(config)
        client.authenticate()
        if args.command == "list-user-jobs":
            payload = client.get_json(endpoint(pcfg, "user_jobs"))
            rows = extract_records(payload)
            print(f"User import jobs returned: {len(rows)}")
            for row in rows[:25]:
                print(f"{find_job_id(row)}\t{find_status(row)}")
        elif args.command == "user-job-status":
            job_id = args.job_id or ""
            if not job_id:
                raise ValueError("--job-id is required.")
            payload = client.get_json(endpoint(pcfg, "user_job_status", job_id))
            print(f"User job {job_id}: {find_status(payload)}")
        elif args.command == "user-job-results":
            job_id = args.job_id or ""
            if not job_id:
                raise ValueError("--job-id is required.")
            fetch_job_results(client, endpoint(pcfg, "user_job_results", job_id), Path(args.output) if args.output else None)
        elif args.command == "list-group-jobs":
            payload = client.get_json(endpoint(pcfg, "group_jobs"))
            rows = extract_records(payload)
            print(f"Group import jobs returned: {len(rows)}")
            for row in rows[:25]:
                print(f"{find_job_id(row)}\t{find_status(row)}")
        elif args.command == "group-job-status":
            job_id = args.job_id or ""
            if not job_id:
                raise ValueError("--job-id is required.")
            payload = client.get_json(endpoint(pcfg, "group_job_status", job_id))
            print(f"Group job {job_id}: {find_status(payload)}")
        elif args.command == "group-job-results":
            job_id = args.job_id or ""
            if not job_id:
                raise ValueError("--job-id is required.")
            fetch_job_results(client, endpoint(pcfg, "group_job_results", job_id), Path(args.output) if args.output else None)
        return 0
    except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
        if args.command in {"submit-users", "submit-group-entities"}:
            csv_value = str(args.csv or "")
            csv_path = Path(csv_value) if csv_value else None
            append_event(
                "provisioning-center",
                "axon-write-not-completed",
                "blocked-or-failed",
                {
                    "command": args.command,
                    "csvSha256": sha256_file(csv_path) if csv_path and csv_path.is_file() else "",
                    "reasonCategory": type(exc).__name__,
                },
            )
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
