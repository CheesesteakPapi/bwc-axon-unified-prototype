"""Pure helpers for the Axon provisioning desktop UI.

The functions in this module do not open windows or contact Axon. Keeping the
command builder and CSV conversion here makes them easy to test offline.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


USER_HEADERS = [
    "EXTERNAL_ID", "EMAIL", "BADGE_NUMBER", "FIRST_NAME", "LAST_NAME",
    "STATUS", "USERNAME", "ROLE", "SUPERVISOR_EMAIL", "LOCATION",
    "EVIDENCE_GROUP_EXT_ID", "PHONE", "RANK",
]
GROUP_HEADERS = ["EXTERNAL_ID", "MEMBERSHIP_TYPE", "ENTITY_TYPE", "ENTITY_ID"]
SOURCE_HEADERS = [
    "ExternalId", "Email", "BadgeNumber", "FirstName", "LastName", "Status",
    "Username", "Role", "SupervisorEmail", "Location", "Phone", "Rank",
    "GroupExternalId",
]


@dataclass(frozen=True)
class OperationSpec:
    key: str
    label: str
    description: str
    fields: tuple[str, ...]
    action: str
    command: str = ""
    write: bool = False


OPERATIONS: tuple[OperationSpec, ...] = (
    OperationSpec(
        "build_csvs", "1 · Input — Build API CSVs from a source roster",
        "Choose a source roster and create separate user-import and Axon Group assignment files.",
        ("source_roster", "user_csv", "group_csv"), "build",
    ),
    OperationSpec(
        "sync_groups", "2 · Snapshot — Download current Groups",
        "Run the existing read-only Groups sync to create the validation snapshot.",
        ("config",), "sync", "Groups",
    ),
    OperationSpec(
        "sync_users", "2 · Snapshot — Download current Users",
        "Run the existing read-only Users sync to create the create-versus-update snapshot.",
        ("config",), "sync", "Users",
    ),
    OperationSpec(
        "validate_users", "3 · Users — Validate CSV offline",
        "Check headers, required values, formats, duplicates, and empty files without contacting Axon.",
        ("config", "user_csv"), "provision", "validate-users",
    ),
    OperationSpec(
        "preview_users", "3 · Users — Preview creates and updates",
        "Compare the import file with the current Users snapshot without writing to Axon.",
        ("config", "user_csv", "existing_users"), "provision", "preview-users",
    ),
    OperationSpec(
        "submit_users", "4 · Users — Submit import job",
        "Submit the reviewed user CSV once. Synchronization remains disabled.",
        ("config", "user_csv", "existing_users"), "provision", "submit-users", True,
    ),
    OperationSpec(
        "list_user_jobs", "5 · User jobs — List recent jobs",
        "Read the recent user-import job list.", ("config",), "provision", "list-user-jobs",
    ),
    OperationSpec(
        "user_job_status", "5 · User jobs — Check status",
        "Read the status of one user-import job.", ("config", "job_id"),
        "provision", "user-job-status",
    ),
    OperationSpec(
        "user_job_results", "5 · User jobs — Review results",
        "Summarize one user job; optionally save detailed results to an approved location.",
        ("config", "job_id", "output"), "provision", "user-job-results",
    ),
    OperationSpec(
        "validate_groups", "6 · Groups — Validate assignments offline",
        "Validate target external IDs, member or monitor values, entity types, users, and duplicates.",
        ("config", "group_csv", "groups_snapshot", "users_snapshot", "pending_users"),
        "provision", "validate-group-entities",
    ),
    OperationSpec(
        "preview_groups", "6 · Groups — Preview assignments",
        "Review assignment counts and validation findings without writing to Axon.",
        ("config", "group_csv", "groups_snapshot", "users_snapshot", "pending_users"),
        "provision", "preview-group-entities",
    ),
    OperationSpec(
        "submit_groups", "7 · Groups — Submit assignment job",
        "Submit the reviewed group-entity CSV once after the related user job succeeds.",
        ("config", "group_csv", "groups_snapshot", "users_snapshot", "pending_users", "user_job_id"),
        "provision", "submit-group-entities", True,
    ),
    OperationSpec(
        "list_group_jobs", "8 · Group jobs — List recent jobs",
        "Read the recent group-entity import job list.", ("config",),
        "provision", "list-group-jobs",
    ),
    OperationSpec(
        "group_job_status", "8 · Group jobs — Check status",
        "Read the status of one group-entity import job.", ("config", "job_id"),
        "provision", "group-job-status",
    ),
    OperationSpec(
        "group_job_results", "8 · Group jobs — Review results",
        "Summarize one group job; optionally save detailed results to an approved location.",
        ("config", "job_id", "output"), "provision", "group-job-results",
    ),
)

OPERATIONS_BY_KEY = {operation.key: operation for operation in OPERATIONS}


def build_api_csvs(source_path: Path, user_output: Path, group_output: Path) -> tuple[int, int]:
    """Convert a source roster into the two documented Axon CSV contracts."""
    if not source_path.exists():
        raise ValueError(f"Source roster does not exist: {source_path}")
    with source_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = [str(value or "").strip() for value in (reader.fieldnames or [])]
        missing = [header for header in SOURCE_HEADERS if header not in headers]
        if missing:
            raise ValueError("Source roster is missing headers: " + ", ".join(missing))
        source_rows = [
            {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
            for row in reader
            if any(str(value or "").strip() for value in row.values())
        ]
    if not source_rows:
        raise ValueError("The source roster contains no data rows.")

    user_rows: list[dict[str, str]] = []
    group_rows: list[dict[str, str]] = []
    assignments: set[tuple[str, str, str]] = set()
    for index, row in enumerate(source_rows, start=2):
        user_rows.append({
            "EXTERNAL_ID": row.get("ExternalId", ""),
            "EMAIL": row.get("Email", ""),
            "BADGE_NUMBER": row.get("BadgeNumber", ""),
            "FIRST_NAME": row.get("FirstName", ""),
            "LAST_NAME": row.get("LastName", ""),
            "STATUS": row.get("Status", ""),
            "USERNAME": row.get("Username", ""),
            "ROLE": row.get("Role", ""),
            "SUPERVISOR_EMAIL": row.get("SupervisorEmail", ""),
            "LOCATION": row.get("Location", ""),
            "EVIDENCE_GROUP_EXT_ID": "",
            "PHONE": row.get("Phone", ""),
            "RANK": row.get("Rank", ""),
        })
        membership = (row.get("MembershipType", "") or "MEMBER").strip().upper()
        if membership not in {"MEMBER", "MONITOR"}:
            raise ValueError(f"Source row {index}: MembershipType must be MEMBER or MONITOR.")
        for raw_group_id in row.get("GroupExternalId", "").split(";"):
            group_id = raw_group_id.strip()
            if not group_id:
                continue
            key = (group_id.casefold(), membership, row.get("Email", "").casefold())
            if key in assignments:
                raise ValueError(f"Source row {index}: duplicate group assignment for {group_id}.")
            assignments.add(key)
            group_rows.append({
                "EXTERNAL_ID": group_id,
                "MEMBERSHIP_TYPE": membership,
                "ENTITY_TYPE": "USER",
                "ENTITY_ID": row.get("Email", ""),
            })

    for path in (user_output, group_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    with user_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=USER_HEADERS)
        writer.writeheader()
        writer.writerows(user_rows)
    with group_output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=GROUP_HEADERS)
        writer.writeheader()
        writer.writerows(group_rows)
    return len(user_rows), len(group_rows)


def validate_inputs(operation: OperationSpec, values: Mapping[str, str]) -> list[str]:
    """Return user-facing preflight errors for a selected UI operation."""
    errors: list[str] = []
    optional = {"output", "users_snapshot", "pending_users", "user_job_id"}
    for field in operation.fields:
        if field not in optional and not str(values.get(field, "")).strip():
            errors.append(f"{field} is required.")
    if operation.key in {"validate_groups", "preview_groups", "submit_groups"}:
        if not values.get("users_snapshot", "").strip() and not values.get("pending_users", "").strip():
            errors.append("Choose a current Users snapshot, a pending user CSV, or both.")
    if operation.key == "submit_groups" and values.get("pending_users", "").strip():
        if not values.get("user_job_id", "").strip():
            errors.append("The successful user-import job ID is required for pending users.")
    if operation.write:
        if not values.get("execute", "").strip():
            errors.append("Confirm that this is an intentional write operation.")
        if not values.get("confirm_agency", "").strip():
            errors.append("Type the active Axon Partner/Agency ID to confirm the target.")
    return errors


def build_command(
    base_dir: Path,
    operation: OperationSpec,
    values: Mapping[str, str],
) -> list[str]:
    """Build an argument-list command. No shell is used and no secret is included."""
    if operation.action == "build":
        return []
    if operation.action == "sync":
        prefix = (
            [sys.executable, "--internal-cli", "sync"]
            if getattr(sys, "frozen", False)
            else [sys.executable, str(base_dir / "axon_sync.py")]
        )
        return [
            *prefix, "sync",
            "--config", values["config"], "--resource", operation.command,
        ]

    prefix = (
        [sys.executable, "--internal-cli", "provision"]
        if getattr(sys, "frozen", False)
        else [sys.executable, str(base_dir / "axon_provision.py")]
    )
    command = [*prefix, operation.command]
    flag_map = (
        ("config", "--config"),
        ("user_csv", "--csv"),
        ("group_csv", "--csv"),
        ("existing_users", "--existing-users-csv"),
        ("groups_snapshot", "--groups-csv"),
        ("users_snapshot", "--users-csv"),
        ("pending_users", "--pending-users-csv"),
        ("job_id", "--job-id"),
        ("user_job_id", "--user-job-id"),
        ("output", "--output"),
    )
    allowed_fields = set(operation.fields)
    for field, flag in flag_map:
        value = str(values.get(field, "")).strip()
        if field in allowed_fields and value:
            command.extend([flag, value])
    if operation.key == "submit_users" and values.get("allow_updates", "").strip():
        command.append("--allow-updates")
    if operation.write:
        command.extend(["--execute", "--confirm-agency", values["confirm_agency"].strip()])
    return command


def display_command(command: Sequence[str]) -> str:
    if not command:
        return "The CSV files will be generated locally; no Axon API call will occur."
    return subprocess.list2cmdline(list(command))
