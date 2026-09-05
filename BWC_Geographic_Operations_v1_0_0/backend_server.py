#!/usr/bin/env python3
"""Local-only Axon read-only backend for BWC Geographic Operations v1.0.0.

The browser never contacts Axon directly. Credentials remain only in this
Python process. The only Axon POST is OAuth token acquisition; operational
resource calls are GET-only.
"""

from __future__ import annotations

import argparse
import copy
import csv
import errno
import hmac
import json
import mimetypes
import os
import secrets
import shutil
import sys
import tempfile
import threading
import uuid
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

SUITE_ROOT = Path(__file__).resolve().parent.parent
if str(SUITE_ROOT) not in sys.path:
    sys.path.insert(0, str(SUITE_ROOT))

from shared_workspace import RefreshLeaseConflict, RevisionConflict, SharedWorkspace
from inventory_views import FILTER_FIELDS, filter_inventory, inventory_csv, parse_inventory_query
from assignment_views import assignment_csv, filter_assignments, parse_assignment_query

from audit_store import append_event, verify_chain
from axon_sync import (
    AxonClient,
    PullCancelledError,
    fetch_resource,
    map_rows,
    reviewed_site_mapping,
    resolve_url,
    write_assignment_and_status_reports,
    write_csv,
)
from runtime_paths import (
    component_root,
    ensure_private_file,
    governance_backup_root,
    governance_root,
    packaged_governance_starters,
)
from desktop_message import show_error
from instance_lock import SingleInstanceLock

VERSION = "3.2.0"
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "dist" / "client"
RUNTIME_ROOT = component_root("geographic-operations")
CONFIG_PATH = RUNTIME_ROOT / "config.json"
CONFIG_EXAMPLE_PATH = BASE_DIR / "config.example.json"
LOCAL_UI_HEADER = "X-BWC-Local-UI"
LOCAL_SESSION_COOKIE = "BWC_AXON_GEOGRAPHIC_SESSION"
MAX_REQUEST_BYTES = 1_000_000
RESOURCE_ORDER = ["DeviceHomes", "Groups", "Users", "Devices"]
DEFAULT_TRACKED_DEVICE_MODELS = (
    "axon_body_4_dock_8_bay,axon_body_4_dock_1_bay,taser_etm_flex_2,"
    "axon_body_cam_4,taser_body_cam_3,taser_cew_10_handle"
)
CROSSWALK_ROOT = Path(os.environ.get("BWC_GOVERNANCE_ROOT", governance_root())).resolve()
GOVERNANCE_STARTER_ROOT = Path(
    os.environ.get("BWC_GOVERNANCE_STARTER_ROOT", packaged_governance_starters(__file__))
).resolve()
CROSSWALK_BACKUP_DIR = governance_backup_root()
CROSSWALK_LOCK = threading.RLock()
CROSSWALK_SPECS: dict[str, dict[str, Any]] = {
    "approved-roles": {
        "fileName": "approved_axon_role_catalog.csv",
        "rowKey": "rowNumber",
        "editableFields": ["Role Name", "Review Status", "Reviewer", "Reviewed At UTC", "Review Notes"],
        "uniqueFields": ["Role Name"],
        "allowCreate": True,
        "fieldOptions": {"Review Status": ["Needs review", "Approved", "Inactive"]},
    },
    "personnel-aor": {
        "fileName": "personnel_location_aor_crosswalk.csv",
        "rowKey": "rowNumber",
        "editableFields": ["Directory Location", "Effective Location", "Component", "Personnel AOR", "Review Status", "Mapping Method", "Confidence", "Reviewer", "Reviewed At UTC", "Review Notes"],
        "uniqueComposite": ["Directory Location", "Component"],
        "allowCreate": True,
        "fieldOptions": {"Review Status": ["Needs review", "Approved", "Inactive"], "Confidence": ["Not rated", "Low", "Medium", "High"]},
    },
    "job-categories": {
        "fileName": "job_title_category_mapping.csv",
        "rowKey": "rowNumber",
        "editableFields": ["Exact Job Title", "Job Category", "Review Status", "Mapping Method", "Confidence", "Reviewer", "Reviewed At UTC", "Review Notes"],
        "uniqueFields": ["Exact Job Title"],
        "allowCreate": True,
        "fieldOptions": {"Job Category": ["Standard User", "First-Line Supervisor", "Senior/Second-Line Supervisor"], "Review Status": ["Needs review", "Approved", "Inactive"], "Confidence": ["Not rated", "Low", "Medium", "High"]},
    },
    "group-rules": {
        "fileName": "component_aor_group_rules.csv",
        "rowKey": "rowNumber",
        "editableFields": ["Component", "Personnel AOR", "Job Category", "Group Name", "Membership Type", "Review Status", "Mapping Method", "Confidence", "Reviewer", "Reviewed At UTC", "Review Notes"],
        "uniqueComposite": ["Component", "Personnel AOR", "Job Category"],
        "allowCreate": True,
        "fieldOptions": {"Job Category": ["Standard User", "First-Line Supervisor", "Senior/Second-Line Supervisor"], "Membership Type": ["MEMBER", "MONITOR"], "Review Status": ["Needs review", "Approved", "Inactive"], "Confidence": ["Not rated", "Low", "Medium", "High"]},
    },
    "directory-attributes": {
        "fileName": "directory_attribute_mapping.csv",
        "rowKey": "Canonical Field",
        "editableFields": ["Directory Attribute", "Required", "Sent To Axon", "Review Status", "Mapping Method", "Confidence", "Review Notes"],
        "uniqueFields": ["Canonical Field"],
        "fieldOptions": {"Required": ["Yes", "No"], "Sent To Axon": ["Yes", "No"], "Review Status": ["Needs review", "Approved", "Inactive"], "Confidence": ["Not rated", "Low", "Medium", "High"]},
    },
    "device-homes": {
        "fileName": "device_home_crosswalk_starter.csv",
        "rowKey": "Site ID",
        "editableFields": [
            "Device Home Name (API)",
            "Normalized Device Home Key",
            "Mapping Status",
            "Mapping Method",
            "Confidence",
            "Review Notes",
        ],
        "uniqueFields": ["Normalized Device Home Key"],
        "fieldOptions": {
            "Mapping Status": ["Unmapped", "Candidate", "Needs review", "Mapped", "No match"],
            "Mapping Method": [
                "Not assessed",
                "Exact name",
                "Normalized name",
                "Command hierarchy review",
                "Manual exception",
            ],
            "Confidence": ["Not rated", "Low", "Medium", "High"],
        },
    },
    "axon-groups": {
        "fileName": "axon_group_crosswalk_starter.csv",
        "rowKey": "Site ID",
        "editableFields": [
            "Axon Group ID",
            "External Group ID",
            "Axon Group Name",
            "Mapping Status",
            "Mapping Method",
            "Confidence",
            "Review Notes",
        ],
        "uniqueFields": ["Axon Group ID"],
        "fieldOptions": {
            "Mapping Status": ["Unmapped", "Candidate", "Needs review", "Mapped", "No match"],
            "Mapping Method": [
                "Not assessed",
                "Observed ID",
                "Exact name",
                "Normalized name",
                "Command hierarchy review",
                "Manual exception",
            ],
            "Confidence": ["Not rated", "Low", "Medium", "High"],
        },
    },
    "non-site-groups": {
        "fileName": "axon_non_site_group_register_starter.csv",
        "rowKey": "rowNumber",
        "editableFields": [
            "Axon Group ID",
            "External Group ID",
            "Group Name",
            "Group Classification",
            "Command Hierarchy Level",
            "Reporting Inclusion",
            "Mapping Status",
            "Review Notes",
        ],
        "uniqueFields": ["Axon Group ID"],
        "allowCreate": True,
        "fieldOptions": {
            "Group Classification": [
                "Command",
                "Role-related",
                "Training",
                "Enterprise",
                "Administrative",
                "Other non-site",
            ],
            "Command Hierarchy Level": [
                "Enterprise",
                "Component",
                "Region / AOR",
                "Field office",
                "Suboffice",
                "Function",
                "Not applicable",
            ],
            "Reporting Inclusion": ["Include", "Exclude", "Context only", "Pending review"],
            "Mapping Status": ["Pending classification", "Registered non-site", "Needs review"],
        },
    },
    "facility-master": {
        "fileName": "facility_master_starter.csv",
        "rowKey": "Facility ID",
        "editableFields": [
            "Facility ID",
            "Facility Name",
            "Address",
            "City",
            "State",
            "Latitude",
            "Longitude",
            "Shared Facility",
            "Host Organization",
            "Ownership / Occupancy Type",
            "Geocoding Status",
            "Validation Status",
            "Mapping Method",
            "Confidence",
            "Review Notes",
        ],
        "uniqueFields": ["Facility ID"],
        "allowCreate": True,
        "fieldOptions": {
            "Shared Facility": ["Pending review", "No", "Yes - ICE components", "Yes - external organization", "Yes - mixed"],
            "Ownership / Occupancy Type": [
                "Pending review",
                "ICE-owned",
                "ICE-leased",
                "GSA-controlled",
                "Hosted by another federal agency",
                "State / local government facility",
                "Commercial / shared facility",
                "Other",
            ],
            "Geocoding Status": ["Not geocoded", "Candidate", "Validated", "Withheld"],
            "Validation Status": ["Draft", "Needs review", "Validated", "Inactive"],
            "Mapping Method": [
                "Not assessed",
                "Official facility record",
                "Exact address",
                "Reviewed co-location",
                "Manual exception",
            ],
            "Confidence": ["Not rated", "Low", "Medium", "High"],
        },
    },
    "office-presences": {
        "fileName": "office_presence_starter.csv",
        "rowKey": "Office Location ID",
        "editableFields": [
            "Facility ID",
            "Presence Type",
            "Network Environment",
            "Network Scope",
            "Operational Status",
            "Facility Link Status",
            "Mapping Method",
            "Confidence",
            "Review Notes",
        ],
        "uniqueFields": ["Office Location ID"],
        "fieldOptions": {
            "Presence Type": ["Pending classification", "Primary office", "Satellite office", "Shared operational presence", "Temporary presence", "Other"],
            "Network Environment": [
                "Unknown / pending validation",
                "ICE-managed network",
                "Host-agency network",
                "Mixed network environment",
                "Limited ICE connectivity",
                "No operational network",
            ],
            "Network Scope": ["Unknown / pending validation", "Facility-wide", "Office / suite", "Shared service", "Limited / intermittent", "Not applicable"],
            "Operational Status": ["Needs validation", "Planned", "Active", "Inactive", "Temporary"],
            "Facility Link Status": ["Unlinked", "Candidate", "Needs review", "Linked"],
            "Mapping Method": ["Not assessed", "Official facility record", "Exact address", "Reviewed co-location", "Manual exception"],
            "Confidence": ["Not rated", "Low", "Medium", "High"],
        },
    },
    "group-master": {
        "fileName": "axon_group_master_starter.csv",
        "rowKey": "Axon Group ID",
        "editableFields": [
            "Axon Group ID",
            "External Group ID",
            "Group Name",
            "Group Purpose",
            "Group Tier",
            "Parent Group ID",
            "Command Hierarchy Level",
            "Organizational Lens",
            "Component",
            "Organizational Area",
            "Site Relationship",
            "Group Status",
            "Mapping Status",
            "Confidence",
            "Review Notes",
        ],
        "uniqueFields": ["Axon Group ID"],
        "allowCreate": True,
        "fieldOptions": {
            "Group Purpose": ["User assignment", "Organizational area", "Command", "Training", "Enterprise", "Administrative", "Other"],
            "Group Tier": ["Primary", "Secondary", "Organizational area", "Additional", "Not applicable"],
            "Command Hierarchy Level": ["Enterprise", "Component", "Region / AOR", "Field office", "Suboffice", "Function", "Not applicable"],
            "Organizational Lens": ["OCIO Areas", "HSI Domestic AORs", "ERO Field Office AORs", "HSI International", "Cross-component", "Not applicable"],
            "Component": ["ERO", "HSI", "OCIO", "OPR", "Cross-component", "Not applicable"],
            "Site Relationship": ["Pending review", "Office presence", "Facility-wide", "Site-linked", "Non-site"],
            "Group Status": ["Unknown", "Active", "Inactive"],
            "Mapping Status": ["Unclassified", "Needs review", "Classified"],
            "Confidence": ["Not rated", "Low", "Medium", "High"],
        },
    },
    "site-group-relationships": {
        "fileName": "site_group_relationship_starter.csv",
        "rowKey": "rowNumber",
        "editableFields": [
            "Office Location ID",
            "Facility ID",
            "Axon Group ID",
            "Relationship Type",
            "Group Tier",
            "Mapping Status",
            "Mapping Method",
            "Confidence",
            "Review Notes",
        ],
        "uniqueComposite": ["Office Location ID", "Axon Group ID", "Relationship Type"],
        "allowCreate": True,
        "fieldOptions": {
            "Relationship Type": ["Primary operational", "Secondary operational", "Organizational area", "Reporting only", "Facility-wide", "Other"],
            "Group Tier": ["Primary", "Secondary", "Organizational area", "Additional", "Not applicable"],
            "Mapping Status": ["Pending review", "Needs review", "Mapped"],
            "Mapping Method": ["Not assessed", "Observed ID", "Command hierarchy review", "Facility review", "Manual exception"],
            "Confidence": ["Not rated", "Low", "Medium", "High"],
        },
    },
}
MAX_CROSSWALK_PAGE_SIZE = 200
MAX_CROSSWALK_FIELD_CHARS = 4_000
GOVERNANCE_FILE_NAMES = [
    "device_home_crosswalk_starter.csv",
    "axon_group_crosswalk_starter.csv",
    "axon_non_site_group_register_starter.csv",
    "facility_master_starter.csv",
    "office_presence_starter.csv",
    "axon_group_master_starter.csv",
    "site_group_relationship_starter.csv",
    "device_status_map.csv",
    "approved_axon_role_catalog.csv",
    "personnel_location_aor_crosswalk.csv",
    "job_title_category_mapping.csv",
    "component_aor_group_rules.csv",
    "directory_attribute_mapping.csv",
]


class UserInputError(ValueError):
    pass


class CrosswalkConflictError(UserInputError):
    pass


def initialize_governance_working_files() -> list[str]:
    """Create missing working files from pristine starters without overwriting edits."""

    CROSSWALK_ROOT.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for file_name in GOVERNANCE_FILE_NAMES:
        destination = CROSSWALK_ROOT / file_name
        if destination.exists():
            continue
        source = GOVERNANCE_STARTER_ROOT / file_name
        if not source.is_file():
            source = SUITE_ROOT / "governance_starters" / file_name
        if not source.is_file():
            raise RuntimeError(f"Governance starter is missing: {source}")
        shutil.copy2(source, destination)
        created.append(file_name)
    return created


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_crosswalk_spec(key: str) -> dict[str, Any]:
    """Return a copy of an allowlisted crosswalk specification."""

    spec = CROSSWALK_SPECS.get(str(key or ""))
    if not spec:
        raise UserInputError(f"Local table must be one of: {', '.join(sorted(CROSSWALK_SPECS))}.")
    return copy.deepcopy(spec)


def governance_workspace() -> SharedWorkspace:
    """Resolve the current shared store lazily so tests and portable overrides remain isolated."""
    return SharedWorkspace()


def crosswalk_path(key: str) -> Path:
    spec = get_crosswalk_spec(key)
    root = CROSSWALK_ROOT.resolve()
    path = (root / spec["fileName"]).resolve()
    if path.parent != root:
        raise RuntimeError("Crosswalk path is outside the local package.")
    return path


def governance_file_path(file_name: str) -> Path:
    if file_name not in GOVERNANCE_FILE_NAMES:
        raise RuntimeError("Governance file is not allowlisted.")
    root = CROSSWALK_ROOT.resolve()
    path = (root / file_name).resolve()
    if path.parent != root:
        raise RuntimeError("Governance path is outside the shared working directory.")
    return path


def _read_crosswalk(key: str) -> tuple[dict[str, Any], Path, list[str], list[dict[str, str]], int]:
    spec = get_crosswalk_spec(key)
    path = crosswalk_path(key)
    try:
        workspace = governance_workspace()
        dataset = workspace.governance_dataset(path.stem)
    except KeyError:
        if not path.is_file():
            raise RuntimeError(f"{spec['fileName']} is missing from the package.")
        workspace.migrate_governance_csvs(path.parent)
        dataset = workspace.governance_dataset(path.stem)
    headers = dataset["headers"]
    rows = dataset["rows"]
    if not headers or (spec["rowKey"] != "rowNumber" and spec["rowKey"] not in headers):
        raise RuntimeError(f"{spec['fileName']} has an invalid or missing header row.")
    missing = [field for field in spec["editableFields"] if field not in headers]
    if missing:
        raise RuntimeError(f"{spec['fileName']} is missing required columns: {', '.join(missing)}")
    return spec, path, headers, rows, int(dataset["revision"])


def _positive_int(value: object, label: str, default: int) -> int:
    if value in (None, ""):
        value = default
    try:
        number = int(str(value))
    except (TypeError, ValueError) as exc:
        raise UserInputError(f"{label} must be a whole number.") from exc
    if number < 1:
        raise UserInputError(f"{label} must be at least 1.")
    return number


def list_crosswalk(
    key: str,
    *,
    page: object = 1,
    page_size: object = 50,
    search: object = "",
) -> dict[str, Any]:
    page_number = _positive_int(page, "Page", 1)
    page_length = _positive_int(page_size, "Page size", 50)
    if page_length > MAX_CROSSWALK_PAGE_SIZE:
        raise UserInputError(f"Page size cannot exceed {MAX_CROSSWALK_PAGE_SIZE}.")
    search_text = str(search or "").strip()
    if len(search_text) > 250 or any(char in search_text for char in "\r\n\0"):
        raise UserInputError("Search must be 250 characters or fewer and cannot contain control characters.")

    with CROSSWALK_LOCK:
        spec, _, headers, all_rows, _ = _read_crosswalk(key)
        indexed_rows = list(enumerate(all_rows, start=1))
    if search_text:
        needle = search_text.casefold()
        indexed_rows = [
            (row_number, row)
            for row_number, row in indexed_rows
            if any(needle in value.casefold() for value in row.values())
        ]
    total = len(indexed_rows)
    total_pages = max(1, (total + page_length - 1) // page_length)
    if page_number > total_pages:
        page_rows: list[tuple[int, dict[str, str]]] = []
    else:
        start = (page_number - 1) * page_length
        page_rows = indexed_rows[start:start + page_length]
    editable = set(spec["editableFields"])
    field_options = copy.deepcopy(spec.get("fieldOptions", {}))
    return {
        "key": key,
        "fileName": spec["fileName"],
        "rowKey": spec["rowKey"],
        "editableFields": list(spec["editableFields"]),
        "allowCreate": bool(spec.get("allowCreate")),
        "fieldOptions": field_options,
        "columns": [
            {
                "key": header,
                "label": header,
                "editable": header in editable,
                "options": field_options.get(header, []),
            }
            for header in headers
        ],
        "total": total,
        "page": page_number,
        "pageSize": page_length,
        "totalPages": total_pages,
        "search": search_text,
        "rows": [{"rowNumber": row_number, "values": row} for row_number, row in page_rows],
        "storage": "shared-sqlite",
        "axonWrite": False,
    }


def review_targets(key: str, source_key: str) -> dict[str, Any]:
    """Read exact matches or vacant site slots; never infer a geographic link."""
    fields = {"device-homes": "Normalized Device Home Key", "axon-groups": "Axon Group ID", "non-site-groups": "Axon Group ID"}
    if key not in fields or not source_key.strip() or len(source_key) > 250:
        raise UserInputError("Choose an observed Device Home or Axon Group.")
    with CROSSWALK_LOCK:
        spec, _, headers, rows, revision = _read_crosswalk(key)
        identity = fields[key]
        matches = [
            {"rowNumber": number, "values": dict(row)}
            for number, row in enumerate(rows, 1)
            if row.get(identity, "").strip().casefold() == source_key.strip().casefold()
        ]
        vacant = [
            {"rowNumber": number, "values": dict(row)}
            for number, row in enumerate(rows, 1)
            if not any(row.get(field, "").strip() for field in
                       ([identity, "Device Home Name (API)"] if key == "device-homes"
                        else [identity, "Axon Group Name", "External Group ID"]))
            and row.get("Site ID", "").strip()
        ] if key != "non-site-groups" else []
    return {"key": key, "matches": matches, "targets": matches or vacant,
            "editableFields": list(spec["editableFields"]), "fieldOptions": spec.get("fieldOptions", {}),
            "allowCreate": bool(spec.get("allowCreate")), "revision": revision}


def _clean_crosswalk_value(field: str, value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, (str, int, float, bool)):
        raise UserInputError(f"{field} must be a text value.")
    text = str(value).strip()
    if "\0" in text:
        raise UserInputError(f"{field} cannot contain null characters.")
    if text and text[0] in {"=", "+", "-", "@"}:
        raise UserInputError(
            f"{field} cannot begin with =, +, -, or @ because spreadsheet applications may treat it as a formula."
        )
    limit = MAX_CROSSWALK_FIELD_CHARS if field == "Review Notes" else 500
    if len(text) > limit:
        raise UserInputError(f"{field} cannot exceed {limit} characters.")
    if field != "Review Notes" and any(char in text for char in "\r\n"):
        raise UserInputError(f"{field} cannot contain line breaks.")
    if field == "Normalized Device Home Key" and text != text.casefold():
        raise UserInputError("Normalized Device Home Key must use lowercase text.")
    return text


def _validate_crosswalk_option(spec: dict[str, Any], field: str, value: str) -> None:
    options = spec.get("fieldOptions", {}).get(field)
    if options and value not in options:
        raise UserInputError(f"{field} must be one of: {', '.join(options)}")


def _crosswalk_reference_values(key: str, field: str) -> set[str]:
    _, _, headers, rows, _ = _read_crosswalk(key)
    if field not in headers:
        raise RuntimeError(f"{field} is missing from {key}.")
    return {row.get(field, "").strip().casefold() for row in rows if row.get(field, "").strip()}


def _validate_crosswalk_row(
    key: str,
    row: dict[str, str],
    *,
    creating: bool = False,
) -> None:
    if key in {"device-homes", "axon-groups"} and row.get("Mapping Status", "") == "Mapped":
        required_source_fields = (
            ["Device Home Name (API)", "Normalized Device Home Key"]
            if key == "device-homes"
            else ["Axon Group ID", "Axon Group Name"]
        )
        missing = [field for field in required_source_fields if not row.get(field, "").strip()]
        if not row.get("Review Notes", "").strip():
            missing.append("Review Notes")
        if row.get("Mapping Method", "").strip() in {"", "Not assessed"}:
            missing.append("reviewed Mapping Method")
        if row.get("Confidence", "").strip() in {"", "Not rated"}:
            missing.append("rated Confidence")
        if missing:
            raise UserInputError(
                "Mapped site rows require observed source values and a documented review basis. "
                f"Complete: {', '.join(missing)}."
            )

    if key != "non-site-groups":
        pass
    elif creating:
        missing_identity = [
            field
            for field in ["Axon Group ID", "Group Name"]
            if not row.get(field, "").strip()
        ]
        if missing_identity:
            raise UserInputError(
                "New non-site Group rows require exact observed identifiers and names. "
                f"Complete: {', '.join(missing_identity)}."
            )
    if row.get("Mapping Status", "") == "Registered non-site":
        required = [
            "Axon Group ID",
            "Group Name",
            "Group Classification",
            "Command Hierarchy Level",
            "Reporting Inclusion",
            "Review Notes",
        ]
        missing = [field for field in required if not row.get(field, "").strip()]
        if missing:
            raise UserInputError(
                "Registered non-site Groups require complete classification and review evidence. "
                f"Complete: {', '.join(missing)}."
            )

    if key == "facility-master":
        if creating:
            missing = [field for field in ["Facility ID", "Facility Name"] if not row.get(field, "").strip()]
            if missing:
                raise UserInputError(f"New facilities require: {', '.join(missing)}.")
        latitude = row.get("Latitude", "").strip()
        longitude = row.get("Longitude", "").strip()
        if bool(latitude) != bool(longitude):
            raise UserInputError("Latitude and Longitude must either both be entered or both remain blank.")
        if latitude:
            try:
                latitude_number = float(latitude)
                longitude_number = float(longitude)
            except ValueError as exc:
                raise UserInputError("Latitude and Longitude must be numeric values.") from exc
            if not -90 <= latitude_number <= 90 or not -180 <= longitude_number <= 180:
                raise UserInputError("Latitude must be -90 to 90 and Longitude must be -180 to 180.")
        if row.get("Ownership / Occupancy Type") == "Hosted by another federal agency" and not row.get("Host Organization", "").strip():
            raise UserInputError("Host Organization is required for facilities hosted by another federal agency.")
        if row.get("Validation Status") == "Validated":
            required = ["Facility ID", "Facility Name", "Ownership / Occupancy Type", "Mapping Method", "Confidence", "Review Notes"]
            missing = [field for field in required if not row.get(field, "").strip()]
            if row.get("Ownership / Occupancy Type") == "Pending review":
                missing.append("reviewed Ownership / Occupancy Type")
            if row.get("Mapping Method") == "Not assessed":
                missing.append("reviewed Mapping Method")
            if row.get("Confidence") == "Not rated":
                missing.append("rated Confidence")
            if missing:
                raise UserInputError(f"Validated facilities require complete review evidence. Complete: {', '.join(missing)}.")

    if key == "office-presences" and row.get("Facility Link Status") == "Linked":
        required = ["Facility ID", "Mapping Method", "Confidence", "Review Notes"]
        missing = [field for field in required if not row.get(field, "").strip()]
        if row.get("Mapping Method") == "Not assessed":
            missing.append("reviewed Mapping Method")
        if row.get("Confidence") == "Not rated":
            missing.append("rated Confidence")
        if missing:
            raise UserInputError(f"Linked office presences require complete review evidence. Complete: {', '.join(missing)}.")
    if key == "office-presences" and row.get("Facility ID", "").strip():
        if row["Facility ID"].strip().casefold() not in _crosswalk_reference_values("facility-master", "Facility ID"):
            raise UserInputError("Facility ID must match an existing Facility Master record before an office presence can be linked.")

    if key == "group-master":
        if creating:
            missing = [field for field in ["Axon Group ID", "Group Name"] if not row.get(field, "").strip()]
            if missing:
                raise UserInputError(f"New Group master rows require exact observed values for: {', '.join(missing)}.")
        if row.get("Parent Group ID", "").strip().casefold() == row.get("Axon Group ID", "").strip().casefold() and row.get("Parent Group ID", "").strip():
            raise UserInputError("A Group cannot be its own parent.")
        if row.get("Parent Group ID", "").strip() and row["Parent Group ID"].strip().casefold() not in _crosswalk_reference_values("group-master", "Axon Group ID"):
            raise UserInputError("Parent Group ID must match an existing Group Master record.")
        if row.get("Mapping Status") == "Classified":
            required = ["Axon Group ID", "Group Name", "Group Purpose", "Group Tier", "Command Hierarchy Level", "Site Relationship", "Confidence", "Review Notes"]
            missing = [field for field in required if not row.get(field, "").strip()]
            if row.get("Confidence") == "Not rated":
                missing.append("rated Confidence")
            if missing:
                raise UserInputError(f"Classified Groups require complete tier and hierarchy evidence. Complete: {', '.join(missing)}.")

    if key == "site-group-relationships":
        if creating:
            missing = [field for field in ["Office Location ID", "Axon Group ID", "Relationship Type"] if not row.get(field, "").strip()]
            if missing:
                raise UserInputError(f"New site-to-Group relationships require: {', '.join(missing)}.")
        if row.get("Mapping Status") == "Mapped":
            required = ["Office Location ID", "Axon Group ID", "Relationship Type", "Group Tier", "Mapping Method", "Confidence", "Review Notes"]
            missing = [field for field in required if not row.get(field, "").strip()]
            if row.get("Mapping Method") == "Not assessed":
                missing.append("reviewed Mapping Method")
            if row.get("Confidence") == "Not rated":
                missing.append("rated Confidence")
            if missing:
                raise UserInputError(f"Mapped site-to-Group relationships require a documented basis. Complete: {', '.join(missing)}.")
        office_id = row.get("Office Location ID", "").strip()
        group_id = row.get("Axon Group ID", "").strip()
        facility_id = row.get("Facility ID", "").strip()
        if office_id and office_id.casefold() not in _crosswalk_reference_values("office-presences", "Office Location ID"):
            raise UserInputError("Office Location ID must match an existing Office Presence record.")
        if group_id and group_id.casefold() not in _crosswalk_reference_values("group-master", "Axon Group ID"):
            raise UserInputError("Axon Group ID must match an existing Group Master record.")
        if facility_id and facility_id.casefold() not in _crosswalk_reference_values("facility-master", "Facility ID"):
            raise UserInputError("Facility ID must match an existing Facility Master record.")


def _validate_unique_fields(
    spec: dict[str, Any],
    rows: list[dict[str, str]],
    row_index: int,
) -> None:
    for field in spec.get("uniqueFields", []):
        candidate = rows[row_index].get(field, "").strip().casefold()
        if not candidate:
            continue
        for other_index, row in enumerate(rows):
            if other_index == row_index:
                continue
            if row.get(field, "").strip().casefold() == candidate:
                raise UserInputError(f"{field} must be unique; the same value exists on row {other_index + 1}.")
    composite_fields = list(spec.get("uniqueComposite", []))
    if composite_fields:
        candidate = tuple(rows[row_index].get(field, "").strip().casefold() for field in composite_fields)
        if all(candidate):
            for other_index, row in enumerate(rows):
                if other_index == row_index:
                    continue
                other = tuple(row.get(field, "").strip().casefold() for field in composite_fields)
                if other == candidate:
                    raise UserInputError(
                        f"The combination of {', '.join(composite_fields)} must be unique; it already exists on row {other_index + 1}."
                    )


def _write_crosswalk_atomic(
    path: Path,
    headers: list[str],
    rows: list[dict[str, str]],
) -> Path:
    CROSSWALK_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = CROSSWALK_BACKUP_DIR / f"{path.stem}.{timestamp}{path.suffix}"
    shutil.copy2(path, backup_path)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="raise", lineterminator="\r\n")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        raise
    return backup_path


def _refresh_crosswalk_projection(
    workspace: SharedWorkspace,
    path: Path,
    headers: list[str],
    rows: list[dict[str, str]],
    event_type: str,
    event_details: dict[str, Any],
) -> dict[str, str]:
    """Refresh the derived CSV without misreporting an authoritative DB commit."""
    try:
        backup_path = _write_crosswalk_atomic(path, headers, rows)
    except Exception:
        warning = (
            "The shared workspace was saved, but its CSV review/export projection could not be refreshed. "
            "Retry the save or export after checking local file access."
        )
        try:
            workspace.audit(
                "geographic-operations",
                "governance-projection-refresh",
                "failure",
                {"dataset": path.stem, "projection": path.name},
            )
        except Exception:
            pass
        return {"projectionStatus": "warning", "projectionWarning": warning, "backupFileName": ""}

    warning = ""
    try:
        append_event(
            "geographic-operations",
            event_type,
            "success",
            {**event_details, "backupFile": backup_path.name},
        )
    except Exception:
        warning = (
            "The shared workspace and CSV projection were saved, but the supplemental local audit log "
            "could not be updated. The shared workspace audit chain remains authoritative."
        )
        try:
            workspace.audit(
                "geographic-operations",
                "supplemental-audit-log",
                "failure",
                {"dataset": path.stem, "projection": path.name},
            )
        except Exception:
            pass
    return {
        "projectionStatus": "warning" if warning else "updated",
        "projectionWarning": warning,
        "backupFileName": backup_path.name,
    }


def update_crosswalk_row(key: str, row_number: object, body: dict[str, Any]) -> dict[str, Any]:
    number = _positive_int(row_number, "Row number", 0)
    changes = body.get("changes")
    expected = body.get("expected", {})
    if not isinstance(changes, dict) or not changes:
        raise UserInputError("Changes must be a non-empty JSON object.")
    if not isinstance(expected, dict):
        raise UserInputError("Expected values must be a JSON object when provided.")

    with CROSSWALK_LOCK:
        spec, path, headers, rows, dataset_revision = _read_crosswalk(key)
        if number > len(rows):
            raise UserInputError(f"Row number must be between 1 and {len(rows)}.")
        invalid_changes = sorted(set(changes) - set(spec["editableFields"]))
        if invalid_changes:
            raise UserInputError(f"Fields are not editable: {', '.join(invalid_changes)}")
        invalid_expected = sorted(set(expected) - set(headers))
        if invalid_expected:
            raise UserInputError(f"Expected values contain unknown fields: {', '.join(invalid_expected)}")

        row_index = number - 1
        current = rows[row_index]
        conflicts = [field for field, value in expected.items() if current.get(field, "") != str(value or "")]
        if conflicts:
            raise CrosswalkConflictError(
                f"Row {number} changed after it was loaded. Refresh before editing: {', '.join(conflicts)}"
            )
        for field, value in changes.items():
            cleaned = _clean_crosswalk_value(field, value)
            _validate_crosswalk_option(spec, field, cleaned)
            current[field] = cleaned
        _validate_crosswalk_row(key, current)
        if not current.get("Review Notes", "").strip():
            raise UserInputError("Review Notes are required for every governed mapping change.")
        _validate_unique_fields(spec, rows, row_index)
        workspace = governance_workspace()
        try:
            workspace.replace_governance_rows(
                path.stem,
                rows,
                dataset_revision,
                "governance-row-updated",
                str(body.get("reviewer") or "operator"),
                {
                    "table": key,
                    "rowNumber": number,
                    "changedFields": sorted(changes),
                    "mappingMethod": current.get("Mapping Method", ""),
                    "confidence": current.get("Confidence", ""),
                    "reviewNotes": current.get("Review Notes", ""),
                },
            )
        except RevisionConflict as exc:
            raise CrosswalkConflictError(str(exc)) from exc
        projection = _refresh_crosswalk_projection(
            workspace,
            path,
            headers,
            rows,
            "governance-row-updated",
            {"table": key, "rowNumber": number, "changedFields": sorted(changes)},
        )

    return {
        "key": key,
        "rowNumber": number,
        "row": {"rowNumber": number, "values": dict(current)},
        **projection,
        "savedAt": utc_now_iso(),
        "storage": "shared-sqlite",
        "axonWrite": False,
    }


def create_crosswalk_row(key: str, body: dict[str, Any]) -> dict[str, Any]:
    values = body.get("values")
    if not isinstance(values, dict) or not values:
        raise UserInputError("Values must be a non-empty JSON object.")

    with CROSSWALK_LOCK:
        spec, path, headers, rows, dataset_revision = _read_crosswalk(key)
        if not spec.get("allowCreate"):
            raise UserInputError(f"New rows cannot be added to {spec['fileName']} from the local app.")
        invalid_fields = sorted(set(values) - set(spec["editableFields"]))
        if invalid_fields:
            raise UserInputError(f"Fields are not editable: {', '.join(invalid_fields)}")
        row = {header: "" for header in headers}
        if key == "non-site-groups":
            row["Mapping Status"] = "Pending classification"
            row["Reporting Inclusion"] = "Pending review"
        elif key == "facility-master":
            row.update({
                "Shared Facility": "Pending review",
                "Ownership / Occupancy Type": "Pending review",
                "Geocoding Status": "Not geocoded",
                "Validation Status": "Draft",
                "Mapping Method": "Not assessed",
                "Confidence": "Not rated",
            })
        elif key == "group-master":
            row.update({
                "Group Status": "Unknown",
                "Mapping Status": "Unclassified",
                "Confidence": "Not rated",
            })
        elif key == "site-group-relationships":
            row.update({
                "Mapping Status": "Pending review",
                "Mapping Method": "Not assessed",
                "Confidence": "Not rated",
            })
        for field, value in values.items():
            cleaned = _clean_crosswalk_value(field, value)
            _validate_crosswalk_option(spec, field, cleaned)
            row[field] = cleaned
        _validate_crosswalk_row(key, row, creating=True)
        if not row.get("Review Notes", "").strip():
            row["Review Notes"] = "Draft record created; review evidence pending."
        rows.append(row)
        row_index = len(rows) - 1
        _validate_unique_fields(spec, rows, row_index)
        workspace = governance_workspace()
        try:
            workspace.replace_governance_rows(
                path.stem,
                rows,
                dataset_revision,
                "governance-row-created",
                str(body.get("reviewer") or "operator"),
                {
                    "table": key,
                    "rowNumber": row_index + 1,
                    "mappingMethod": row.get("Mapping Method", ""),
                    "confidence": row.get("Confidence", ""),
                    "reviewNotes": row.get("Review Notes", ""),
                },
            )
        except RevisionConflict as exc:
            raise CrosswalkConflictError(str(exc)) from exc
        projection = _refresh_crosswalk_projection(
            workspace,
            path,
            headers,
            rows,
            "governance-row-created",
            {
                "table": key,
                "rowNumber": row_index + 1,
                "populatedFields": sorted(field for field, value in row.items() if value),
            },
        )

    row_number = row_index + 1
    return {
        "key": key,
        "rowNumber": row_number,
        "row": {"rowNumber": row_number, "values": dict(row)},
        **projection,
        "savedAt": utc_now_iso(),
        "storage": "shared-sqlite",
        "axonWrite": False,
    }


def local_governance_summary() -> dict[str, Any]:
    """Return non-sensitive aggregates from the governed local model files."""

    with CROSSWALK_LOCK:
        _, _, _, facilities, _ = _read_crosswalk("facility-master")
        _, _, _, offices, _ = _read_crosswalk("office-presences")
        _, _, _, groups, _ = _read_crosswalk("group-master")
        _, _, _, relationships, _ = _read_crosswalk("site-group-relationships")

    office_by_facility: dict[str, list[dict[str, str]]] = defaultdict(list)
    for office in offices:
        facility_id = office.get("Facility ID", "").strip()
        if facility_id:
            office_by_facility[facility_id.casefold()].append(office)

    co_located = sum(1 for rows in office_by_facility.values() if len(rows) > 1)
    multi_component = sum(
        1
        for rows in office_by_facility.values()
        if len({row.get("Component", "").strip() for row in rows if row.get("Component", "").strip()}) > 1
    )
    external_network_values = {
        "host-agency network",
        "mixed network environment",
        "limited ice connectivity",
        "no operational network",
    }
    return {
        "facilities": {
            "total": len(facilities),
            "validated": sum(1 for row in facilities if row.get("Validation Status") == "Validated"),
            "shared": sum(1 for row in facilities if row.get("Shared Facility", "").startswith("Yes")),
            "externallyHosted": sum(
                1
                for row in facilities
                if row.get("Ownership / Occupancy Type") == "Hosted by another federal agency"
                or row.get("Shared Facility") in {"Yes - external organization", "Yes - mixed"}
            ),
            "coLocated": co_located,
            "multiComponent": multi_component,
        },
        "officePresences": {
            "total": len(offices),
            "linked": sum(1 for row in offices if row.get("Facility Link Status") == "Linked"),
            "unlinked": sum(1 for row in offices if row.get("Facility Link Status") != "Linked"),
            "networkPending": sum(1 for row in offices if row.get("Network Environment") == "Unknown / pending validation"),
            "nonIceOrLimitedNetwork": sum(1 for row in offices if row.get("Network Environment", "").casefold() in external_network_values),
        },
        "groups": {
            "total": len(groups),
            "classified": sum(1 for row in groups if row.get("Mapping Status") == "Classified"),
            "primary": sum(1 for row in groups if row.get("Group Tier") == "Primary"),
            "secondary": sum(1 for row in groups if row.get("Group Tier") == "Secondary"),
            "organizationalArea": sum(1 for row in groups if row.get("Group Tier") == "Organizational area"),
            "hierarchyLinks": sum(1 for row in groups if row.get("Parent Group ID", "").strip()),
        },
        "siteGroupRelationships": {
            "total": len(relationships),
            "mapped": sum(1 for row in relationships if row.get("Mapping Status") == "Mapped"),
        },
        "storage": "shared-sqlite",
        "axonWrite": False,
    }


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path.name} must contain a JSON object.")
    return payload


def load_config() -> tuple[dict[str, Any], bool]:
    if not CONFIG_EXAMPLE_PATH.exists():
        raise RuntimeError("config.example.json is missing from the package.")
    if CONFIG_PATH.exists():
        return read_json(CONFIG_PATH), True
    return read_json(CONFIG_EXAMPLE_PATH), False


def validate_tenant_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname:
        raise UserInputError("Axon tenant URL must use HTTPS.")
    if hostname != "evidence.com" and not hostname.endswith(".evidence.com"):
        raise UserInputError("Axon tenant URL must be an evidence.com tenant host.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise UserInputError("Axon tenant URL cannot contain credentials, a query string, or a fragment.")
    return url


def public_config() -> dict[str, Any]:
    config, exists = load_config()
    return {
        "exists": exists,
        "agencyBaseUrl": str(config.get("agency_base_url") or ""),
        "timeoutSeconds": int(config.get("timeout_seconds", 90)),
        "deviceModel": str(config.get("tracked_device_models", DEFAULT_TRACKED_DEVICE_MODELS) or ""),
        "rawJsonEnabled": False,
        "readOnly": True,
    }


def save_public_config(values: dict[str, Any]) -> dict[str, Any]:
    config, _ = load_config()
    config["agency_base_url"] = validate_tenant_url(str(values.get("agencyBaseUrl") or ""))
    try:
        timeout = int(values.get("timeoutSeconds", 90))
    except (TypeError, ValueError) as exc:
        raise UserInputError("Timeout must be a whole number of seconds.") from exc
    if timeout < 15 or timeout > 600:
        raise UserInputError("Timeout must be between 15 and 600 seconds.")
    config["timeout_seconds"] = timeout
    if "deviceModel" in values:
        config["tracked_device_models"] = clean_filter(values["deviceModel"], allow_commas=True)
    config["keep_raw_json"] = False
    temporary = CONFIG_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temporary.replace(CONFIG_PATH)
    ensure_private_file(CONFIG_PATH)
    append_event(
        "geographic-operations",
        "connection-settings-updated",
        "success",
        {"timeoutSeconds": timeout, "tenantConfigured": True},
    )
    return public_config()


def clean_filter(value: object, *, allow_commas: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if any(ch in text for ch in "\r\n\0"):
        raise UserInputError("Filter values cannot contain line breaks or null characters.")
    if allow_commas:
        values = [part.strip() for part in text.split(",") if part.strip()]
        if len(values) > 25:
            raise UserInputError("Use no more than 25 comma-separated device models per pull.")
        return ",".join(values)
    if "," in text:
        raise UserInputError("Only the device model filter accepts comma-separated values.")
    return text


def title_state(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "Unmapped"
    return " ".join(part.capitalize() for part in text.replace("-", "_").split("_") if part)


def counter_text(values: list[str]) -> str:
    counts = Counter(value for value in values if value)
    return "; ".join(f"{key}: {counts[key]}" for key in sorted(counts)) or "—"


def region_bucket(value: str) -> str:
    # A Device Home name is a comparison signal, not geographic authority.
    # Operational buckets must come from the reviewed local crosswalk.
    return value.strip() or "Unassigned"


def apply_current_group_governance(
    groups: list[dict[str, Any]],
    site_rows: list[dict[str, str]],
    non_site_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Overlay current governed Group decisions onto an immutable Axon snapshot."""
    site_by_id = {
        str(row.get("Axon Group ID") or "").strip(): row
        for row in site_rows
        if str(row.get("Axon Group ID") or "").strip()
    }
    non_site_by_id = {
        str(row.get("Axon Group ID") or "").strip(): row
        for row in non_site_rows
        if str(row.get("Axon Group ID") or "").strip()
    }
    current: list[dict[str, Any]] = []
    for source in groups:
        group = dict(source)
        group_id = str(group.get("Axon Group ID") or "").strip()
        site_source = site_by_id.get(group_id, {})
        site_mapping = reviewed_site_mapping(site_source)
        non_site = non_site_by_id.get(group_id, {})
        group["Mapped Site ID"] = site_mapping.get("Site ID", "")
        group["Mapped Component"] = site_mapping.get("Component", "")
        group["Mapped Region / AOR"] = site_mapping.get("Region / AOR", "")
        if site_mapping:
            group["Group Classification"] = "Site-Mapped"
            group["Command Hierarchy Level"] = "Site / Office"
            group["Reporting Inclusion"] = "Include"
            group["Mapping Status"] = "Mapped"
            group["Review Notes"] = site_source.get("Review Notes", "Mapped through reviewed Axon Group crosswalk.")
        elif non_site:
            group["Group Classification"] = non_site.get("Group Classification", "Unclassified")
            group["Command Hierarchy Level"] = non_site.get("Command Hierarchy Level", "")
            group["Reporting Inclusion"] = non_site.get("Reporting Inclusion", "Review")
            group["Mapping Status"] = non_site.get("Mapping Status", "Unmapped")
            group["Review Notes"] = non_site.get("Review Notes", "")
        else:
            group["Group Classification"] = "Unclassified"
            group["Command Hierarchy Level"] = ""
            group["Reporting Inclusion"] = "Review"
            group["Mapping Status"] = site_source.get("Mapping Status", "Unmapped")
            group["Review Notes"] = site_source.get("Review Notes", "")
        current.append(group)
    return current


def build_dashboard_payload(
    rows: dict[str, list[dict[str, Any]]],
    last_sync_at: str,
    filters: dict[str, str],
    job_resources: list[str],
    *,
    mode: str = "live",
    inventory_limit: int | None = 500,
    assignment_limit: int | None = 500,
) -> dict[str, Any]:
    devices = rows.get("Devices", [])
    users = rows.get("Users", [])
    homes = rows.get("DeviceHomes", [])
    groups = rows.get("Groups", [])
    devices_available = "Devices" in rows
    users_available = "Users" in rows
    homes_available = "DeviceHomes" in rows or devices_available
    groups_available = "Groups" in rows

    with CROSSWALK_LOCK:
        _, _, _, home_crosswalk_rows, _ = _read_crosswalk("device-homes")
        _, _, _, group_crosswalk_rows, _ = _read_crosswalk("axon-groups")
        _, _, _, non_site_group_rows, _ = _read_crosswalk("non-site-groups")
    home_crosswalk = {
        str(row.get("Normalized Device Home Key") or "").strip(): {
            field: str(row.get(field) or "").strip()
            for field in ("Site ID", "Component", "Region / AOR", "Mapping Status")
        }
        for row in home_crosswalk_rows
        if str(row.get("Normalized Device Home Key") or "").strip()
    }
    groups = apply_current_group_governance(groups, group_crosswalk_rows, non_site_group_rows)

    assigned_by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
    inventory: list[dict[str, Any]] = []
    exceptions = 0
    mapped_devices = 0
    region_counts: Counter[str] = Counter()
    disposition_counts: Counter[str] = Counter()

    for device in devices:
        owner_id = str(device.get("Assigned User ID") or "").strip()
        if owner_id:
            assigned_by_user[owner_id].append(device)
        key = str(device.get("Normalized Device Home Key") or "").strip()
        crosswalk = reviewed_site_mapping(home_crosswalk.get(key, {}))
        mapped_site = str(crosswalk.get("Site ID") or "").strip()
        region = str(crosswalk.get("Region / AOR") or "").strip()
        component = str(crosswalk.get("Component") or "").strip()
        reporting_state = title_state(device.get("Reporting Device State"))
        raw_status = title_state(device.get("Device Status"))
        assignment_state = "Assigned" if owner_id else "Unassigned"
        disposition = reporting_state if reporting_state != "Unmapped" else raw_status
        if disposition == "Unmapped":
            disposition = assignment_state
        disposition_counts[disposition] += 1
        needs_review = (
            not owner_id
            or not mapped_site
            or bool(str(device.get("Error Status") or "").strip())
            or any(term in disposition.casefold() for term in ["lost", "relinquished", "in stock", "unassigned", "unmapped"])
        )
        if needs_review:
            exceptions += 1
        if mapped_site:
            mapped_devices += 1
        region_counts[region_bucket(region)] += 1
        inventory.append({
            "deviceId": str(device.get("Axon Device ID") or ""),
            "serialNumber": str(device.get("Serial Number") or ""),
            "model": str(device.get("Device Model") or ""),
            "rawStatus": raw_status,
            "disposition": disposition,
            "assignmentState": assignment_state,
            "assignedUser": str(device.get("Assigned User Name") or owner_id),
            "assignedUserId": owner_id,
            "deviceHome": str(device.get("Device Home Name (API)") or ""),
            "mappedSiteId": mapped_site,
            "component": component,
            "regionAor": region,
            "firmware": str(device.get("Firmware") or ""),
            "lastConnected": str(device.get("Last Connected") or ""),
            "needsReview": needs_review,
        })

    assignments: list[dict[str, Any]] = []
    user_id_counts = Counter(str(user.get("Axon User ID") or "").strip() for user in users)
    for user in users:
        user_id = str(user.get("Axon User ID") or "").strip()
        identity_status = "Exact Axon User ID" if user_id and user_id_counts[user_id] == 1 else "Missing or duplicate Axon User ID"
        counts_available = devices_available and identity_status == "Exact Axon User ID"
        assigned = assigned_by_user.get(user_id, [])
        display_name = " ".join(
            part for part in [str(user.get("First Name") or "").strip(), str(user.get("Last Name") or "").strip()] if part
        ) or str(user.get("External ID") or user_id)
        models = sorted({str(device.get("Device Model") or "").strip() for device in assigned if device.get("Device Model")})
        states = [title_state(device.get("Reporting Device State") or device.get("Device Status")) for device in assigned]
        role = str(user.get("Role") or "").strip()
        assignments.append({
            "userId": user_id,
            "identityStatus": identity_status,
            "displayName": display_name,
            "externalId": str(user.get("External ID") or ""),
            "role": role,
            "roleException": not role or ";" in role,
            "primaryGroup": "",
            "secondaryGroup": "",
            "organizationalAreaGroups": "",
            "additionalGroupCount": 0,
            "groupDataStatus": "Not observed in the current Users pull contract",
            "userStatus": str(user.get("User Status") or ""),
            "deviceCount": len(assigned) if counts_available else None,
            "deviceModels": (
                "; ".join(models) or "—"
                if counts_available
                else "Unavailable"
            ),
            "deviceStates": counter_text(states) if counts_available else "Unavailable",
        })

    observed_home_keys = {
        str(home.get("Normalized Device Home Key") or "").strip()
        for home in homes
        if str(home.get("Normalized Device Home Key") or "").strip()
    }
    if not observed_home_keys:
        observed_home_keys = {
            str(device.get("Normalized Device Home Key") or "").strip()
            for device in devices
            if str(device.get("Normalized Device Home Key") or "").strip()
        }
    mapped_home_keys = {
        key
        for key in observed_home_keys
        if reviewed_site_mapping(home_crosswalk.get(key, {}))
    }
    unmapped_homes = len(observed_home_keys - mapped_home_keys)

    crosswalk_review: list[dict[str, str]] = []
    for home in homes:
        home_key = str(home.get("Normalized Device Home Key") or "").strip()
        if reviewed_site_mapping(home_crosswalk.get(home_key, {})):
            continue
        crosswalk_review.append({
            "sourceType": "Device Home",
            "sourceId": str(home.get("Device Home Name (API)") or ""),
            "normalizedKey": str(home.get("Normalized Device Home Key") or ""),
            "suggestedUnit": "Not yet reviewed",
            "mappingMethod": "Unmapped",
            "confidence": "Needs Review",
            "reviewNotes": "Map the observed API name to a physical site and organizational AOR.",
        })
    for group in groups:
        if str(group.get("Mapping Status") or "").casefold() in {"mapped", "classified", "registered non-site"}:
            continue
        crosswalk_review.append({
            "sourceType": "Axon Group",
            "sourceId": str(group.get("Group Name") or group.get("Axon Group ID") or ""),
            "externalGroupId": str(group.get("External Group ID") or ""),
            "normalizedKey": str(group.get("Axon Group ID") or ""),
            "suggestedUnit": str(group.get("Group Classification") or "Unclassified"),
            "mappingMethod": "Group register",
            "confidence": "Needs Review",
            "reviewNotes": str(group.get("Review Notes") or "Confirm whether this Group is site-based or non-site."),
        })

    group_counts = Counter(str(group.get("Group Classification") or "Unclassified") for group in groups)
    assigned_count = sum(1 for device in devices if str(device.get("Assigned User ID") or "").strip())
    mapping_completion = round((mapped_devices / len(devices)) * 100, 1) if devices else 0.0

    component_summaries: dict[str, dict[str, Any]] = {}
    for component_name in sorted({str(row.get("component") or "").strip() for row in inventory} - {""}):
        component_inventory = [row for row in inventory if row.get("component") == component_name]
        component_assigned = sum(1 for row in component_inventory if row.get("assignmentState") == "Assigned")
        component_mapped = sum(1 for row in component_inventory if row.get("mappedSiteId"))
        component_region_counts = Counter(region_bucket(str(row.get("regionAor") or "")) for row in component_inventory)
        component_dispositions = Counter(str(row.get("disposition") or "Unmapped") for row in component_inventory)
        component_unmapped_homes = {
            str(row.get("deviceHome") or "").strip()
            for row in component_inventory
            if row.get("deviceHome") and not row.get("mappedSiteId")
        }
        component_summaries[component_name] = {
            "totalDevices": len(component_inventory),
            "assignedDevices": component_assigned,
            "unassignedDevices": len(component_inventory) - component_assigned,
            "inventoryExceptions": sum(1 for row in component_inventory if row.get("needsReview")),
            "mappedDevices": component_mapped,
            "mappingCompletion": round((component_mapped / len(component_inventory)) * 100, 1) if component_inventory else 0.0,
            "unmappedDeviceHomes": len(component_unmapped_homes),
            "totalUsers": len(users) if users_available else None,
            "totalGroups": len(groups) if groups_available else None,
            "roleExceptions": sum(1 for row in assignments if row.get("roleException")) if users_available else None,
            "regionCounts": dict(component_region_counts),
            "dispositionCounts": dict(component_dispositions),
            "groupClassificationCounts": dict(group_counts) if groups_available else {},
        }

    return {
        "mode": mode,
        "confirmedDeviceBaseline": mode == "live",
        "deviceMetricsScope": "full" if mode == "live" else ("filtered" if mode == "filtered" else "unavailable"),
        "lastSyncAt": last_sync_at,
        "filters": filters,
        "resources": job_resources,
        "resourceCounts": {name: len(rows[name]) if name in rows else None for name in RESOURCE_ORDER},
        "summary": {
            "totalDevices": len(devices) if mode != "partial" else None,
            "assignedDevices": assigned_count if mode != "partial" else None,
            "unassignedDevices": len(devices) - assigned_count if mode != "partial" else None,
            "inventoryExceptions": exceptions if mode != "partial" else None,
            "mappedDevices": mapped_devices if mode != "partial" else None,
            "mappingCompletion": mapping_completion if mode != "partial" else None,
            "unmappedDeviceHomes": unmapped_homes if homes_available else None,
            "totalUsers": len(users) if users_available else None,
            "totalGroups": len(groups) if groups_available else None,
            "roleExceptions": sum(1 for row in assignments if row.get("roleException")) if users_available else None,
            "regionCounts": dict(region_counts),
            "dispositionCounts": dict(disposition_counts),
            "groupClassificationCounts": dict(group_counts) if groups_available else {},
        },
        "componentSummaries": component_summaries,
        "inventory": inventory[:inventory_limit] if inventory_limit is not None else inventory,
        "assignments": assignments[:assignment_limit] if assignment_limit is not None else assignments,
        "crosswalkReview": crosswalk_review[:500],
        "groups": [
            {
                "groupId": str(group.get("Axon Group ID") or ""),
                "name": str(group.get("Group Name") or ""),
                "classification": str(group.get("Group Classification") or "Unclassified"),
                "hierarchyLevel": str(group.get("Command Hierarchy Level") or ""),
                "reportingInclusion": str(group.get("Reporting Inclusion") or "Review"),
                "mappedSiteId": str(group.get("Mapped Site ID") or ""),
                "mappingStatus": str(group.get("Mapping Status") or "Unmapped"),
            }
            for group in groups[:500]
        ],
        "truncated": {
            "inventory": len(inventory) > 500,
            "assignments": len(assignments) > 500,
            "crosswalkReview": len(crosswalk_review) > 500,
            "groups": len(groups) > 500,
        },
    }


class SessionState:
    def __init__(self, client_factory: Callable[..., Any] = AxonClient) -> None:
        test_token = (
            os.environ.get("BWC_AXON_TEST_LAUNCH_TOKEN", "")
            if os.environ.get("BWC_AXON_TEST_MODE") == "1"
            else ""
        )
        self.local_token = test_token if len(test_token) >= 32 else secrets.token_urlsafe(32)
        self._lock = threading.RLock()
        self._credentials = {"partner_id": "", "client_id": "", "client_secret": ""}
        self._jobs: dict[str, dict[str, Any]] = {}
        self._active_job_id = ""
        self._rows: dict[str, list[dict[str, Any]]] = {}
        self._dashboard: dict[str, Any] | None = None
        self._downloads: dict[str, Path] = {}
        self._download_scope: dict[str, Any] = {}
        self._temporary_dir = Path(tempfile.mkdtemp(prefix="bwc-axon-live-"))
        self.client_factory = client_factory
        self.workspace = SharedWorkspace()
        self.workspace.migrate_governance_csvs(CROSSWALK_ROOT)
        persisted, activated_at, scopes, mode = self._dashboard_source()
        if persisted:
            device_scope = scopes.get("Devices", {})
            device_filters = dict(device_scope.get("filters") or {}) if mode == "filtered" else {}
            self._rows = persisted
            self._dashboard = build_dashboard_payload(
                persisted,
                activated_at or utc_now_iso(),
                {
                    "deviceModel": str(device_filters.get("model") or ""),
                    "deviceStatus": str(device_filters.get("status2") or ""),
                    "deviceHomeId": str(device_filters.get("homeId") or ""),
                },
                list(persisted),
                mode=mode,
            )
            self._dashboard["baselineScopes"] = scopes

    def close(self) -> None:
        with self._lock:
            self._credentials = {"partner_id": "", "client_id": "", "client_secret": ""}
            self._rows = {}
            self._dashboard = None
            self._downloads = {}
            self._download_scope = {}
        shutil.rmtree(self._temporary_dir, ignore_errors=True)

    def _active_baseline(
        self,
        operational_view: dict[str, Any] | None = None,
    ) -> tuple[dict[str, list[dict[str, Any]]], str, dict[str, dict[str, Any]]]:
        view = operational_view or self.workspace.read_operational_view()
        active_snapshots = list(view.get("snapshots") or [])
        rows: dict[str, list[dict[str, Any]]] = {}
        scopes: dict[str, dict[str, Any]] = {}
        activated_at = ""
        for resource in RESOURCE_ORDER:
            snapshot = next(
                (
                    item
                    for item in active_snapshots
                    if item.get("resource") == resource
                    and str((item.get("scope") or {}).get("type") or "") == "full"
                ),
                None,
            )
            if not snapshot:
                continue
            rows[resource] = snapshot["rows"]
            scopes[resource] = dict(snapshot.get("scope") or {})
            activated_at = max(activated_at, str(snapshot.get("activatedAt") or ""))
        return rows, activated_at, scopes

    def _dashboard_source(
        self,
        operational_view: dict[str, Any] | None = None,
    ) -> tuple[dict[str, list[dict[str, Any]]], str, dict[str, dict[str, Any]], str]:
        """Return confirmed full rows, or an explicitly scoped non-baseline view."""
        view = operational_view or self.workspace.read_operational_view()
        rows, activated_at, scopes = self._active_baseline(view)
        if "Devices" in rows:
            return rows, activated_at, scopes, "live"

        latest_devices = next(
            (item for item in (view.get("snapshots") or []) if item.get("resource") == "Devices"),
            None,
        )
        latest_scope = dict((latest_devices or {}).get("scope") or {})
        if latest_devices and latest_scope.get("type") == "filtered":
            rows["Devices"] = latest_devices["rows"]
            scopes["Devices"] = latest_scope
            activated_at = max(activated_at, str(latest_devices.get("activatedAt") or ""))
            return rows, activated_at, scopes, "filtered"

        return rows, activated_at, scopes, "partial" if rows else "illustrative"

    def set_credentials(self, partner_id: object, client_id: object, client_secret: object) -> None:
        values = [str(value or "").strip() for value in (partner_id, client_id, client_secret)]
        if not all(values):
            raise UserInputError("Partner / Agency ID, Client ID, and Client Secret are all required.")
        if any(any(ch in value for ch in "\r\n\0") for value in values):
            raise UserInputError("Credential values cannot contain line breaks or null characters.")
        with self._lock:
            self._credentials = {"partner_id": values[0], "client_id": values[1], "client_secret": values[2]}

    def clear_credentials(self) -> None:
        with self._lock:
            self._credentials = {"partner_id": "", "client_id": "", "client_secret": ""}

    def session_status(self) -> dict[str, Any]:
        with self._lock:
            partner_id = self._credentials["partner_id"]
            configured = all(self._credentials.values())
            dashboard = copy.deepcopy(self._dashboard)
            active_job = copy.deepcopy(self._jobs.get(self._active_job_id)) if self._active_job_id else None
        return {
            "configured": configured,
            "partnerHint": f"…{partner_id[-4:]}" if configured and len(partner_id) > 4 else ("••••" if configured else ""),
            "dataMode": str((dashboard or {}).get("mode") or "illustrative"),
            "lastSyncAt": dashboard.get("lastSyncAt", "") if dashboard else "",
            "activeJob": active_job,
            "credentialsPersisted": False,
            "workspaceRevision": self.workspace.revision(),
        }

    def dashboard(self) -> dict[str, Any]:
        operational_view = self.workspace.read_operational_view()
        workspace_revision = operational_view["workspaceRevision"]
        with self._lock:
            cached = copy.deepcopy(self._dashboard)
        current_rows, activated_at, baseline_scopes, mode = self._dashboard_source(operational_view)
        if current_rows:
            device_scope = baseline_scopes.get("Devices", {})
            device_filters = dict(device_scope.get("filters") or {}) if mode == "filtered" else {}
            dashboard = build_dashboard_payload(
                current_rows,
                activated_at or str((cached or {}).get("lastSyncAt") or utc_now_iso()),
                {
                    "deviceModel": str(device_filters.get("model") or ""),
                    "deviceStatus": str(device_filters.get("status2") or ""),
                    "deviceHomeId": str(device_filters.get("homeId") or ""),
                },
                list(current_rows),
                mode=mode,
            )
            dashboard["baselineScopes"] = baseline_scopes
            with self._lock:
                self._rows = copy.deepcopy(current_rows)
                self._dashboard = copy.deepcopy(dashboard)
        else:
            dashboard = cached or {"mode": "illustrative"}
        all_overlays = operational_view["pendingOverlays"]
        pending = [item for item in all_overlays if item["entityType"] == "User"]
        group_changes = [item for item in all_overlays if item["entityType"] == "GroupMembership"]
        dashboard["workspaceRevision"] = workspace_revision
        dashboard["sharedSnapshots"] = operational_view["snapshotMetadata"]
        dashboard["pendingUsers"] = [
            {
                "runId": item["runId"],
                "runRevision": item["runRevision"],
                "state": item["state"],
                "email": item["payload"].get("email", ""),
                "name": " ".join(value for value in (item["payload"].get("firstName", ""), item["payload"].get("lastName", "")) if value),
                "role": item["payload"].get("role", ""),
                "group": item["payload"].get("groupName", ""),
                "location": item["payload"].get("location", ""),
                "personnelAor": item["payload"].get("personnelAor", ""),
            }
            for item in pending[:500]
        ]
        dashboard["pendingSummary"] = {
            "total": len(pending),
            "proposedCreations": sum(1 for item in pending if item["state"] == "Proposed creation"),
            "proposedUpdates": sum(1 for item in pending if item["state"] == "Proposed update"),
            "awaitingConfirmation": sum(1 for item in pending if item["state"] == "Submitted—awaiting confirmation"),
            "failed": sum(1 for item in pending if item["state"] == "Failed"),
            "confirmed": sum(1 for item in pending if item["state"] == "Confirmed"),
            "superseded": sum(1 for item in pending if item["state"] == "Superseded"),
            "groupRelationshipChanges": sum(1 for item in group_changes if item["state"] not in {"Confirmed", "Superseded"}),
        }
        confirmed_user_value = (dashboard.get("summary") or {}).get("totalUsers")
        if confirmed_user_value is None:
            dashboard["projectedSummary"] = {
                "confirmedUsers": None,
                "baselinePlusPendingUsers": None,
            }
        else:
            confirmed_users = int(confirmed_user_value)
            dashboard["projectedSummary"] = {
                "confirmedUsers": confirmed_users,
                "baselinePlusPendingUsers": confirmed_users + sum(
                    1
                    for item in pending
                    if item["state"] in {"Proposed creation", "Submitted—awaiting confirmation"}
                ),
            }
        with self._lock:
            dashboard["availableDownloads"] = sorted(
                key for key, path in self._downloads.items() if path and path.is_file()
            )
            dashboard["downloadScope"] = copy.deepcopy(self._download_scope)
        return dashboard

    def inventory_view(self, query: dict[str, list[str]], *, export: bool = False) -> dict[str, Any]:
        """Filter the complete saved device scope, independent of session downloads."""
        try:
            options = parse_inventory_query(query, export=export)
        except ValueError as exc:
            raise UserInputError(str(exc)) from exc
        view = self.workspace.read_operational_view()
        revision = view["workspaceRevision"]
        expected = options["expectedRevision"]
        if expected is not None and expected != revision:
            raise RevisionConflict("The shared data changed. Reload inventory before exporting this view.")
        rows, activated_at, scopes, mode = self._dashboard_source(view)
        device_snapshot = next((item for item in view["snapshotMetadata"] if
            item["resource"] == "Devices" and item["scope"] == scopes.get("Devices")), None)
        filters = options["filters"]
        if "Devices" in rows:
            # Governance is read separately by the existing dashboard mapper.
            # The revision check below rejects a concurrent governance change.
            payload = build_dashboard_payload(rows, activated_at, {}, list(rows), mode=mode, inventory_limit=None)
            inventory = payload["inventory"]
        else:
            inventory = []
        matched = filter_inventory(inventory, filters)
        total_pages = max(1, (len(matched) + options["pageSize"] - 1) // options["pageSize"])
        page = min(options["page"], total_pages)
        start = (page - 1) * options["pageSize"]
        context = {
            "mode": "full" if mode == "live" else "filtered" if mode == "filtered" else "unavailable",
            "workspaceRevision": revision,
            "deviceSnapshot": device_snapshot,
            "filters": filters,
            "total": len(matched),
            "scopeTotal": len(inventory) if device_snapshot else None,
            "page": page,
            "pageSize": options["pageSize"],
            "totalPages": total_pages,
            "facets": {key: sorted({str(row.get(key) or "") for row in inventory} - {""}, key=str.casefold)
                       for key in FILTER_FIELDS},
            "rows": matched[start:start + options["pageSize"]],
        }
        if self.workspace.revision() != revision:
            raise RevisionConflict("The shared data changed while inventory was loading. Reload this view.")
        if export:
            if device_snapshot is None:
                raise UserInputError("Complete a Devices refresh before exporting inventory.")
            context["exportedAt"] = utc_now_iso()
            context["content"] = inventory_csv(matched, context)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            context["filename"] = f"BWC_inventory_{context['mode']}_R{revision}_{timestamp}.csv"
        return context

    def assignment_view(self, query: dict[str, list[str]], *, detail=False, export=False) -> dict[str, Any]:
        try:
            options = parse_assignment_query(query, detail=detail, export=export)
        except ValueError as exc:
            raise UserInputError(str(exc)) from exc
        view = self.workspace.read_operational_view()
        revision = view["workspaceRevision"]
        if options["expectedRevision"] is not None and options["expectedRevision"] != revision:
            raise RevisionConflict("The shared data changed. Reload assignments before continuing.")
        rows, activated_at, scopes, mode = self._dashboard_source(view)
        snapshots = {item["resource"]: {key: value for key, value in item.items() if key != "rows"}
                     for item in view["snapshots"] if item["scope"] == scopes.get(item["resource"])}
        user_snapshot, device_snapshot = snapshots.get("Users"), snapshots.get("Devices")
        payload = build_dashboard_payload(rows, activated_at, {}, list(rows), mode=mode,
                                          inventory_limit=None if detail else 0, assignment_limit=None) if user_snapshot else {}
        assignments = payload.get("assignments", [])
        context = {
            "workspaceRevision": revision, "userSnapshot": user_snapshot, "deviceSnapshot": device_snapshot,
            "deviceScope": device_snapshot["scope"]["type"] if device_snapshot else "unavailable",
            "scopeTotal": len(assignments) if user_snapshot else None,
            "roles": sorted({row["role"] for row in assignments if row["role"]}, key=str.casefold),
            "filters": options["filters"],
        }
        if detail:
            selected = [row for row in assignments if row["userId"] == options["userId"]]
            if len(selected) != 1 or selected[0]["identityStatus"] != "Exact Axon User ID":
                raise UserInputError("This user cannot be resolved to one exact Axon User ID in the saved Users snapshot.")
            context["user"] = selected[0]
            matched = sorted((device for device in payload["inventory"] if device["assignedUserId"] == options["userId"]),
                             key=lambda device: (device["serialNumber"].casefold(), device["deviceId"]))
        else:
            matched = filter_assignments(assignments, options["filters"])
        total_pages = max(1, (len(matched) + options["pageSize"] - 1) // options["pageSize"])
        page = min(options["page"], total_pages)
        start = (page - 1) * options["pageSize"]
        context.update({"rows": matched[start:start + options["pageSize"]], "total": len(matched),
                        "page": page, "pageSize": options["pageSize"], "totalPages": total_pages})
        if detail and device_snapshot is None:
            context["total"] = None
        if self.workspace.revision() != revision:
            raise RevisionConflict("The shared data changed while assignments were loading. Reload this view.")
        if export:
            if user_snapshot is None:
                raise UserInputError("Complete a Users refresh before exporting assignments.")
            context["exportedAt"] = utc_now_iso()
            context["content"] = assignment_csv(matched, context)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            context["filename"] = f"BWC_assignments_{context['deviceScope']}_R{revision}_{timestamp}.csv"
        return context

    def job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            return copy.deepcopy(self._jobs.get(job_id))

    def resolve_download(self, resource: str) -> Path | None:
        with self._lock:
            path = self._downloads.get(resource.casefold())
        return path if path and path.is_file() else None

    def start_sync(self, body: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if not all(self._credentials.values()):
                raise UserInputError("Session credentials are required before a live pull.")
            if self._active_job_id:
                active = self._jobs.get(self._active_job_id, {})
                if active.get("status") in {"queued", "running", "cancel-requested"}:
                    raise UserInputError("A read-only Axon pull is already running.")

        requested = body.get("resources", list(RESOURCE_ORDER))
        if not isinstance(requested, list):
            raise UserInputError("Resources must be a list.")
        resources = [str(name) for name in requested if str(name) in RESOURCE_ORDER]
        if not resources:
            raise UserInputError("Select at least one Axon resource.")
        # Reuse saved context. A Devices pull must not silently refresh all Users
        # or Device Homes; absent resources remain unavailable until selected.
        resources = [name for name in RESOURCE_ORDER if name in resources]

        filters = {
            "deviceModel": clean_filter(body.get("deviceModel"), allow_commas=True),
            "deviceStatus": clean_filter(body.get("deviceStatus")),
            "deviceHomeId": clean_filter(body.get("deviceHomeId")),
        }
        job_id = uuid.uuid4().hex
        job = {
            "jobId": job_id,
            "status": "queued",
            "phase": "Queued",
            "resources": resources,
            "completedResources": [],
            "resourceCounts": {},
            "filters": filters,
            "startedAt": "",
            "finishedAt": "",
            "error": "",
            "cancelRequested": False,
            "currentResource": "",
            "currentPage": 0,
            "receivedRecords": 0,
        }
        with self._lock:
            self._jobs[job_id] = job
            self._active_job_id = job_id
        threading.Thread(target=self._run_sync, args=(job_id, resources, filters), daemon=True).start()
        return copy.deepcopy(job)

    def _update_job(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            self._jobs[job_id].update(changes)

    def request_cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise UserInputError("Live-pull job was not found in this session.")
            if job.get("status") not in {"queued", "running", "cancel-requested"}:
                raise UserInputError("That live pull is no longer running.")
            job.update(
                cancelRequested=True,
                status="cancel-requested",
                phase="Stopping safely after the current request",
            )
            return copy.deepcopy(job)

    def _run_sync(self, job_id: str, resources: list[str], filters: dict[str, str]) -> None:
        self._update_job(job_id, status="running", phase="Authenticating", startedAt=utc_now_iso())
        refresh_owner = f"geographic-operations-{os.getpid()}-{job_id}"
        leases: dict[str, str] = {}
        try:
            def cancel_check() -> bool:
                with self._lock:
                    return bool(self._jobs[job_id].get("cancelRequested"))

            def update_progress(resource_name: str, page: int, record_count: int) -> None:
                self._update_job(
                    job_id,
                    currentResource=resource_name,
                    currentPage=page,
                    receivedRecords=record_count,
                    phase=f"Pulling {resource_name} — page {page}, {record_count} records received",
                )

            config, exists = load_config()
            if not exists:
                raise UserInputError("Save the Axon tenant URL before starting a live pull.")
            config = copy.deepcopy(config)
            config["keep_raw_json"] = False
            run_dir = self._temporary_dir / job_id
            run_dir.mkdir(parents=True, exist_ok=True)
            governance_dir = run_dir / "governance"
            governance_dir.mkdir(parents=True, exist_ok=True)
            governance_exports = {
                "device_home_crosswalk_csv": ("device_home_crosswalk_starter", "device_home_crosswalk_starter.csv"),
                "axon_group_crosswalk_csv": ("axon_group_crosswalk_starter", "axon_group_crosswalk_starter.csv"),
                "non_site_group_register_csv": ("axon_non_site_group_register_starter", "axon_non_site_group_register_starter.csv"),
            }
            for config_field, (dataset_key, file_name) in governance_exports.items():
                export_path = governance_dir / file_name
                try:
                    self.workspace.export_governance_csv(dataset_key, export_path)
                    config[config_field] = str(export_path)
                except KeyError:
                    config[config_field] = str(governance_file_path(file_name))
            # The status map remains an explicitly file-governed reference rather
            # than an editable SQLite dataset. Always consume its current file so
            # an administrator's reviewed status change is not shadowed by the
            # one-time CSV migration copy.
            config["device_status_map_csv"] = str(governance_file_path("device_status_map.csv"))
            devices_config = config.get("resources", {}).get("Devices", {})
            params = dict(devices_config.get("sync_params") or {})
            for key in ["model", "status2", "homeId"]:
                params.pop(key, None)
            if filters["deviceModel"]:
                params["model"] = filters["deviceModel"]
            if filters["deviceStatus"]:
                params["status2"] = filters["deviceStatus"]
            if filters["deviceHomeId"]:
                params["homeId"] = filters["deviceHomeId"]
            devices_config["sync_params"] = params

            with self._lock:
                credentials = dict(self._credentials)
            client = self.client_factory(
                agency_base_url=config["agency_base_url"],
                client_id=credentials["client_id"],
                client_secret=credentials["client_secret"],
                timeout_seconds=int(config.get("timeout_seconds", 90)),
            )
            client.authenticate()
            if cancel_check():
                raise PullCancelledError("Pull canceled by the local operator after authentication.")
            context_rows: dict[str, list[dict[str, Any]]] = {}
            for existing_resource in RESOURCE_ORDER:
                existing_snapshot = self.workspace.active_snapshot(existing_resource)
                if existing_snapshot:
                    context_rows[existing_resource] = existing_snapshot["rows"]
            resource_counts: dict[str, int] = {}
            downloads: dict[str, Path] = {}
            pending_snapshots: list[dict[str, Any]] = []
            for name in resources:
                detail = "API pacing is one request every five seconds" if name == "Devices" else "Read-only GET"
                self._update_job(job_id, phase=f"Pulling {name} — {detail}")
                is_filtered_device_scope = name == "Devices" and any(filters.values())
                resource_scope = {
                    "type": "filtered" if is_filtered_device_scope else "full",
                    "filters": filters if name == "Devices" else {},
                }
                leases[name] = self.workspace.acquire_refresh_lease(name, refresh_owner, resource_scope)
                resource_config = config["resources"][name]
                records, pages, _ = fetch_resource(
                    client,
                    config,
                    name,
                    resource_config,
                    credentials["partner_id"],
                    probe_only=False,
                    progress_callback=update_progress,
                    cancel_check=cancel_check,
                )
                mapped = map_rows(name, records, resource_config["field_map"], config, context_rows)
                context_rows[name] = mapped
                pending_snapshots.append({
                    "resource": name,
                    "rows": mapped,
                    "scope": resource_scope,
                    "source": "Axon API via Geographic Operations",
                })
                resource_counts[name] = len(mapped)
                output_path = run_dir / resource_config["output_csv"]
                write_csv(mapped, resource_config["output_headers"], output_path)
                downloads[name.casefold()] = output_path
                with self._lock:
                    completed = [*self._jobs[job_id]["completedResources"], name]
                self._update_job(
                    job_id,
                    completedResources=completed,
                    resourceCounts=dict(resource_counts),
                    phase=f"Validated {name}: {len(mapped)} records across {pages} page(s)",
                )

            # A missing Devices snapshot means device relationships are unknown,
            # not zero. Suppress device-derived reports until a full or explicitly
            # filtered Devices scope is present.
            if "Devices" in context_rows:
                write_assignment_and_status_reports(context_rows, run_dir)
                for report in run_dir.glob("reports.*.csv"):
                    downloads[report.stem.casefold()] = report
                    if "user_device_assignment_summary" in report.stem:
                        downloads["assignments"] = report
                    elif "device_status_summary" in report.stem:
                        downloads["device-status"] = report
                    elif "device_assignment_and_status_exceptions" in report.stem:
                        downloads["exceptions"] = report
            if cancel_check():
                raise PullCancelledError("Pull canceled by the local operator before snapshot activation.")
            activated_snapshots = self.workspace.activate_snapshots_batch(pending_snapshots)
            activated_by_resource = {item["resource"]: item for item in activated_snapshots}
            for name, refresh_id in list(leases.items()):
                activated = activated_by_resource[name]
                self.workspace.release_refresh_lease(
                    name,
                    refresh_owner,
                    refresh_id,
                    "completed",
                    snapshot_id=activated["snapshotId"],
                )
                leases.pop(name, None)
            last_sync_at = utc_now_iso()
            baseline_rows, baseline_at, baseline_scopes, dashboard_mode = self._dashboard_source()
            device_scope = baseline_scopes.get("Devices", {})
            baseline_filters = dict(device_scope.get("filters") or {}) if dashboard_mode == "filtered" else {}
            dashboard = build_dashboard_payload(
                baseline_rows,
                baseline_at or last_sync_at,
                {
                    "deviceModel": str(baseline_filters.get("model") or ""),
                    "deviceStatus": str(baseline_filters.get("status2") or ""),
                    "deviceHomeId": str(baseline_filters.get("homeId") or ""),
                },
                list(baseline_rows),
                mode=dashboard_mode,
            )
            dashboard["baselineScopes"] = baseline_scopes
            summary_path = run_dir / "bwc_geographic_live_summary.json"
            summary_path.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
            downloads["summary"] = summary_path
            with self._lock:
                self._rows = baseline_rows
                self._dashboard = dashboard
                self._downloads = downloads
                self._download_scope = {
                    "resources": list(resources),
                    "filters": dict(filters),
                    "deviceScope": (
                        "filtered"
                        if "Devices" in resources and any(filters.values())
                        else "full" if "Devices" in resources else "unavailable"
                    ),
                }
            self._update_job(
                job_id,
                status="complete",
                phase="Live snapshot ready",
                resourceCounts=resource_counts,
                finishedAt=last_sync_at,
            )
        except PullCancelledError:
            for name, refresh_id in list(leases.items()):
                self.workspace.release_refresh_lease(name, refresh_owner, refresh_id, "canceled", "Canceled by local operator")
                leases.pop(name, None)
            self._update_job(
                job_id,
                status="canceled",
                phase="Pull canceled safely; prior dashboard snapshot preserved",
                finishedAt=utc_now_iso(),
                error="",
            )
        except Exception as exc:
            for name, refresh_id in list(leases.items()):
                self.workspace.release_refresh_lease(name, refresh_owner, refresh_id, "failed", type(exc).__name__)
                leases.pop(name, None)
            self._update_job(
                job_id,
                status="failed",
                phase="Live pull failed",
                finishedAt=utc_now_iso(),
                error=str(exc)[:1500],
            )


class LocalAxonGeographicHandler(BaseHTTPRequestHandler):
    server_version = "BWCGeographicAxon/1.0.0"
    state: SessionState

    def log_message(self, format_string: str, *args: Any) -> None:
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

    def _send_attachment(self, file_path: Path) -> None:
        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(file_path.name)[0] or "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        self.wfile.write(content)

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

    def _require_local_change(self) -> bool:
        if self.headers.get(LOCAL_UI_HEADER) != "1":
            self._error(HTTPStatus.FORBIDDEN, "Missing local UI request header.")
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        if not self._valid_host():
            self._error(HTTPStatus.FORBIDDEN, "Host is not allowed.")
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/" and self._accept_launch(parsed):
            return
        if not self._authorized():
            self._error(HTTPStatus.UNAUTHORIZED, "This local desktop session is not authorized. Launch the application again.")
            return
        if path == "/api/health":
            self._send_json(HTTPStatus.OK, {
                "success": True,
                "version": VERSION,
                "staticReady": STATIC_DIR.exists(),
                "readOnly": True,
                "productionMode": True,
                "audit": verify_chain(),
            })
            return
        if path == "/api/session":
            self._send_json(HTTPStatus.OK, {"success": True, **self.state.session_status()})
            return
        if path == "/api/config":
            try:
                self._send_json(HTTPStatus.OK, {"success": True, **public_config()})
            except Exception as exc:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        if path == "/api/live/dashboard":
            self._send_json(HTTPStatus.OK, {"success": True, **self.state.dashboard()})
            return
        if path in {"/api/inventory", "/api/inventory/export", "/api/assignments", "/api/assignments/export", "/api/assignments/devices"}:
            try:
                export = path.endswith("/export")
                query = parse_qs(parsed.query, keep_blank_values=True)
                payload = (self.state.assignment_view(query, detail=path.endswith("/devices"), export=export)
                           if path.startswith("/api/assignments") else self.state.inventory_view(query, export=export))
                if export:
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.send_header("Content-Disposition", f'attachment; filename="{payload["filename"]}"')
                    self.send_header("Content-Length", str(len(payload["content"])))
                    self.send_header("Cache-Control", "no-store")
                    self._security_headers()
                    self.end_headers()
                    self.wfile.write(payload["content"])
                else:
                    self._send_json(HTTPStatus.OK, {"success": True, **payload})
            except RevisionConflict as exc:
                self._error(HTTPStatus.CONFLICT, str(exc))
            except UserInputError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "Unable to read saved records. Reload and try again.")
            return
        if path == "/api/workspace/revision":
            self._send_json(HTTPStatus.OK, {"success": True, "workspaceRevision": self.state.workspace.revision()})
            return
        if path == "/api/review/targets":
            try:
                query = parse_qs(parsed.query, keep_blank_values=True)
                payload = review_targets((query.get("key") or [""])[0], (query.get("sourceKey") or [""])[0])
                self._send_json(HTTPStatus.OK, {"success": True, **payload})
            except UserInputError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Review target table could not load: {exc}")
            return
        if path == "/api/workspace/status":
            self._send_json(HTTPStatus.OK, {"success": True, **self.state.workspace.status()})
            return
        if path == "/api/workspace/pending-users":
            rows = [item for item in self.state.workspace.pending_overlays() if item["entityType"] == "User"]
            self._send_json(HTTPStatus.OK, {"success": True, "rows": rows})
            return
        if path == "/api/governance/summary":
            try:
                self._send_json(HTTPStatus.OK, {"success": True, **local_governance_summary()})
            except Exception as exc:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Local governance summary failed: {exc}")
            return
        segments = [unquote(segment) for segment in path.split("/") if segment]
        if len(segments) >= 3 and segments[:2] == ["api", "crosswalks"]:
            key = segments[2]
            try:
                if len(segments) == 3:
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    payload = list_crosswalk(
                        key,
                        page=(query.get("page") or [1])[0],
                        page_size=(query.get("pageSize") or [50])[0],
                        search=(query.get("search") or [""])[0],
                    )
                    self._send_json(HTTPStatus.OK, {"success": True, **payload})
                    return
                if len(segments) == 4 and segments[3] == "export":
                    with CROSSWALK_LOCK:
                        _, file_path, _, _, _ = _read_crosswalk(key)
                    export_dir = self.state._temporary_dir / "governance-exports" / uuid.uuid4().hex
                    export_path = export_dir / file_path.name
                    self.state.workspace.export_governance_csv(file_path.stem, export_path)
                    self._send_attachment(export_path)
                    return
                self._error(HTTPStatus.NOT_FOUND, "Local crosswalk route not found.")
            except UserInputError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Local crosswalk function failed: {exc}")
            return
        if path.startswith("/api/live/sync/"):
            job_id = path.rsplit("/", 1)[-1]
            job = self.state.job(job_id)
            if not job:
                self._error(HTTPStatus.NOT_FOUND, "Live-pull job was not found in this session.")
            else:
                self._send_json(HTTPStatus.OK, {"success": True, **job})
            return
        if path.startswith("/api/live/export/"):
            resource = unquote(path.rsplit("/", 1)[-1])
            file_path = self.state.resolve_download(resource)
            if not file_path:
                self._error(HTTPStatus.NOT_FOUND, "That live export is not available in this session.")
                return
            self._send_attachment(file_path)
            return
        if path.startswith("/api/"):
            self._error(HTTPStatus.NOT_FOUND, "Local API route not found.")
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        if not self._valid_host() or not self._authorized() or not self._require_local_change():
            if not self._valid_host():
                self._error(HTTPStatus.FORBIDDEN, "Host is not allowed.")
            elif not self._authorized():
                self._error(HTTPStatus.UNAUTHORIZED, "This local desktop session is not authorized.")
            return
        path = urlparse(self.path).path
        try:
            body = self._read_json()
            if path == "/api/config":
                self._send_json(HTTPStatus.OK, {"success": True, **save_public_config(body)})
                return
            if path == "/api/app/shutdown":
                self.state.clear_credentials()
                append_event("geographic-operations", "application-stop-requested", "success")
                self._send_json(HTTPStatus.OK, {"success": True, "message": "The local desktop service is stopping."})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if path == "/api/session/credentials":
                self.state.set_credentials(body.get("partnerId"), body.get("clientId"), body.get("clientSecret"))
                self._send_json(HTTPStatus.OK, {"success": True, **self.state.session_status()})
                return
            if path == "/api/live/sync":
                job = self.state.start_sync(body)
                self._send_json(HTTPStatus.ACCEPTED, {"success": True, **job})
                return
            segments = [unquote(segment) for segment in path.split("/") if segment]
            if (
                len(segments) == 5
                and segments[:3] == ["api", "live", "sync"]
                and segments[4] == "cancel"
            ):
                job = self.state.request_cancel(segments[3])
                self._send_json(HTTPStatus.ACCEPTED, {"success": True, **job})
                return
            if (
                len(segments) == 5
                and segments[:2] == ["api", "crosswalks"]
                and segments[3] == "rows"
            ):
                payload = update_crosswalk_row(segments[2], segments[4], body)
                self._send_json(HTTPStatus.OK, {"success": True, **payload})
                return
            if (
                len(segments) == 4
                and segments[:2] == ["api", "crosswalks"]
                and segments[3] == "rows"
            ):
                payload = create_crosswalk_row(segments[2], body)
                self._send_json(HTTPStatus.CREATED, {"success": True, **payload})
                return
            self._error(HTTPStatus.NOT_FOUND, "Local API route not found.")
        except CrosswalkConflictError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except UserInputError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Local function failed: {exc}")

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._valid_host() or not self._authorized() or not self._require_local_change():
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
    handler = type("BoundLocalAxonGeographicHandler", (LocalAxonGeographicHandler,), {"state": state})
    # On Windows, adjacent ports can fall inside an excluded/reserved range and
    # return WSAEACCES even when the original failure was EADDRINUSE. Ask the
    # OS for a safe ephemeral loopback port instead of incrementing blindly.
    candidates = [port, 0] if auto_port and port else [port]
    retryable_errors = {errno.EADDRINUSE, errno.EACCES, 10013}
    last_error: OSError | None = None
    for candidate in candidates:
        try:
            return ThreadingHTTPServer(("127.0.0.1", candidate), handler)
        except OSError as exc:
            last_error = exc
            if not auto_port or exc.errno not in retryable_errors:
                raise
    raise OSError(
        errno.EADDRINUSE,
        f"No available loopback port could be selected for requested port {port}.",
    ) from last_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8798)
    parser.add_argument("--auto-port", action="store_true", default=bool(getattr(sys, "frozen", False)), help="Use the next available loopback port when the requested port is occupied.")
    parser.add_argument("--open", action="store_true", default=bool(getattr(sys, "frozen", False)), help="Open the local UI in the default browser.")
    parser.add_argument("--no-open", action="store_false", dest="open", help=argparse.SUPPRESS)
    parser.add_argument("--no-auto-port", action="store_false", dest="auto_port", help=argparse.SUPPRESS)
    args, _unknown = parser.parse_known_args()
    instance_lock = SingleInstanceLock("geographic-operations")
    if not instance_lock.acquire():
        show_error("BWC Geographic Operations", "The application is already running for this user.")
        return 3
    created = initialize_governance_working_files()
    append_event(
        "geographic-operations",
        "application-started",
        "success",
        {"version": VERSION, "initializedGovernanceFiles": len(created)},
    )
    state = SessionState()
    server = make_server(args.port, state, auto_port=args.auto_port)
    selected_port = int(server.server_address[1])
    url = f"http://127.0.0.1:{selected_port}/"
    launch_url = f"{url}?launch={state.local_token}"
    print(f"BWC Geographic Operations v{VERSION}")
    print(f"Local address: {url}")
    if selected_port != args.port:
        print(f"Port {args.port} was unavailable; selected an available local loopback port.")
    print("Credentials remain in this process. Completed normalized snapshots persist in the shared workspace.")
    print("Axon operational resource calls are read-only GET requests.")
    print(f"Governance working directory: {CROSSWALK_ROOT}")
    if created:
        print(f"Initialized {len(created)} missing governance file(s) from pristine starters.")
    if args.open:
        threading.Timer(0.35, lambda: webbrowser.open(launch_url)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping local UI.")
    finally:
        server.server_close()
        state.close()
        append_event("geographic-operations", "application-stopped", "success", {"version": VERSION})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
