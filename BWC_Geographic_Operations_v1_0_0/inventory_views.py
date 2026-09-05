"""Local inventory filtering and review CSVs; no external API calls."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from shared_workspace import safe_csv_value


FILTER_FIELDS = ("model", "disposition", "assignmentState", "deviceHome", "component", "regionAor")
CSV_FIELDS = (
    ("Serial Number", "serialNumber"), ("Device ID", "deviceId"),
    ("Model", "model"), ("Disposition", "disposition"),
    ("Assignment State", "assignmentState"), ("Assigned User", "assignedUser"),
    ("Device Home", "deviceHome"), ("Mapped Site ID", "mappedSiteId"),
    ("Component", "component"), ("Mapped AOR", "regionAor"),
    ("Needs Review", "needsReview"),
)


def parse_inventory_query(query: dict[str, list[str]], *, export: bool = False) -> dict[str, Any]:
    allowed = set(FILTER_FIELDS) | {"search", "exceptionsOnly", "page", "pageSize", "expectedRevision"}
    if set(query) - allowed or any(len(values) != 1 for values in query.values()):
        raise ValueError("Use one value per supported inventory filter.")
    values = {key: items[0].strip() for key, items in query.items()}
    if any(len(value) > 500 or any(ord(char) < 32 for char in value) for value in values.values()):
        raise ValueError("Inventory filter values must be at most 500 characters without control characters.")
    filters = {key: values.get(key, "") for key in (*FILTER_FIELDS, "search")}
    if values.get("exceptionsOnly", "false") not in {"true", "false"}:
        raise ValueError("exceptionsOnly must be true or false.")
    filters["exceptionsOnly"] = values.get("exceptionsOnly") == "true"
    try:
        page = int(values.get("page", "1"))
        page_size = int(values.get("pageSize", "50"))
        revision = int(values["expectedRevision"]) if "expectedRevision" in values else None
    except ValueError as exc:
        raise ValueError("Page, page size, and expected revision must be whole numbers.") from exc
    if page < 1 or not 1 <= page_size <= 200 or (revision is not None and revision < 0):
        raise ValueError("Page must be positive; page size must be 1–200; revision cannot be negative.")
    if export and revision is None:
        raise ValueError("Reload inventory before exporting; expectedRevision is required.")
    return {"filters": filters, "page": page, "pageSize": page_size, "expectedRevision": revision}


def filter_inventory(rows: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    search = str(filters.get("search") or "").casefold()
    selected = [
        row for row in rows
        if all(not filters.get(key) or str(row.get(key) or "") == filters[key] for key in FILTER_FIELDS)
        and (not filters.get("exceptionsOnly") or row.get("needsReview"))
        and (not search or search in " ".join(str(row.get(key) or "") for _, key in CSV_FIELDS).casefold())
    ]
    return sorted(selected, key=lambda row: (
        str(row.get("serialNumber") or "").casefold(), str(row.get("deviceId") or "").casefold(),
    ))


def inventory_csv(rows: list[dict[str, Any]], context: dict[str, Any]) -> bytes:
    """Export every filtered row with its scope and formula-safe UTF-8 values."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow([label for label, _ in CSV_FIELDS] + [
        "Data Scope", "Devices Snapshot ID", "Devices Snapshot UTC", "Devices SHA256",
        "Workspace Revision", "View Filters", "Export UTC",
    ])
    snapshot = context["deviceSnapshot"]
    provenance = [context["mode"], snapshot["snapshotId"], snapshot["activatedAt"], snapshot["sha256"],
                  context["workspaceRevision"], json.dumps(context["filters"], sort_keys=True), context["exportedAt"]]
    for row in rows:
        writer.writerow([safe_csv_value(value) for value in
                         [row.get(key, "") for _, key in CSV_FIELDS] + provenance])
    return output.getvalue().encode("utf-8")
