"""Saved user/device investigation and formula-safe review exports."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from shared_workspace import safe_csv_value


def parse_assignment_query(query: dict[str, list[str]], *, detail=False, export=False) -> dict[str, Any]:
    allowed = {"page", "pageSize", "expectedRevision"} | ({"userId"} if detail else {"search", "role", "deviceCount"})
    if set(query) - allowed or any(len(values) != 1 for values in query.values()):
        raise ValueError("Use one value per supported assignment filter.")
    values = {key: items[0].strip() for key, items in query.items()}
    if any(len(value) > 500 or any(ord(char) < 32 for char in value) for value in values.values()):
        raise ValueError("Assignment filters must be at most 500 characters without control characters.")
    count = values.get("deviceCount", "")
    if count not in {"", "0", "1", "2", "3+", "unavailable"}:
        raise ValueError("Choose all, 0, 1, 2, 3+, or unavailable for device count.")
    try:
        page, size = int(values.get("page", "1")), int(values.get("pageSize", "50"))
        revision = int(values["expectedRevision"]) if "expectedRevision" in values else None
    except ValueError as exc:
        raise ValueError("Page, page size, and expected revision must be whole numbers.") from exc
    if page < 1 or not 1 <= size <= 200 or (revision is not None and revision < 0):
        raise ValueError("Page must be positive; page size must be 1–200; revision cannot be negative.")
    if (detail or export) and revision is None:
        raise ValueError("Reload assignments first; expectedRevision is required.")
    if detail and not values.get("userId"):
        raise ValueError("An exact Axon User ID is required for a device drilldown.")
    return {"filters": {"search": values.get("search", ""), "role": values.get("role", ""), "deviceCount": count},
            "page": page, "pageSize": size, "expectedRevision": revision, "userId": values.get("userId", "")}


def filter_assignments(rows: list[dict[str, Any]], filters: dict[str, str]) -> list[dict[str, Any]]:
    search, role, count = filters["search"].casefold(), filters["role"], filters["deviceCount"]
    def matches(row):
        value = row["deviceCount"]
        count_matches = (not count or (count == "unavailable" and value is None)
                         or (value is not None and ((count == "3+" and value >= 3) or str(value) == count)))
        return (count_matches and (not role or row["role"] == role)
                and (not search or search in " ".join(str(row.get(key) or "") for key in
                    ("userId", "externalId", "displayName", "role", "deviceModels", "deviceStates")).casefold()))
    return sorted((row for row in rows if matches(row)), key=lambda row: (row["displayName"].casefold(), row["userId"], row["externalId"]))


def assignment_csv(rows: list[dict[str, Any]], context: dict[str, Any]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["User ID", "External ID", "User", "Role", "Device Count", "Device Models", "Device States",
                     "Identity Status", "Device Scope", "Users Snapshot ID", "Users Snapshot UTC", "Users SHA256",
                     "Devices Snapshot ID", "Devices Snapshot UTC", "Devices SHA256", "Device Scope Filters",
                     "Workspace Revision", "View Filters", "Export UTC"])
    users, devices = context["userSnapshot"], context["deviceSnapshot"] or {}
    provenance = [context["deviceScope"], users["snapshotId"], users["activatedAt"], users["sha256"],
                  devices.get("snapshotId", ""), devices.get("activatedAt", ""), devices.get("sha256", ""),
                  json.dumps(devices.get("scope", {}).get("filters", {}), sort_keys=True),
                  context["workspaceRevision"], json.dumps(context["filters"], sort_keys=True), context["exportedAt"]]
    for row in rows:
        writer.writerow([safe_csv_value(value) for value in [row["userId"], row["externalId"], row["displayName"], row["role"],
            row["deviceCount"] if row["deviceCount"] is not None else "Unavailable",
            row["deviceModels"], row["deviceStates"], row["identityStatus"]] + provenance])
    return output.getvalue().encode("utf-8")
