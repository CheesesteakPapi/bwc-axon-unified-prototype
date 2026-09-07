#!/usr/bin/env python3
"""
Axon Evidence -> BWC reporting read-only sync prototype (v0.2.6).

Verified against the Axon documentation supplied with the BWC program:
- OAuth2 client credentials: POST /api/oauth2/token
- Users:       GET /api/v4/agencies/{agencyId}/users
- Devices:     GET /api/v1/agencies/{agencyId}/devices
- Groups:      GET /api/v1/agencies/{agencyId}/groups
- DeviceHomes: GET /api/v1/agencies/{agencyId}/devices/homes/list
- Group hierarchy: GET /api/v1/agencies/{agencyId}/hierarchy/{groupId}/children

Safety:
- No Axon create/update/delete methods are implemented.
- Resource calls are GET-only.
- The only POST is OAuth token acquisition.
- Client secrets and Partner/Agency ID come from environment variables.
- Raw JSON persistence is OFF by default because responses can contain PII.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SUITE_ROOT = Path(__file__).resolve().parent.parent
if str(SUITE_ROOT) not in sys.path:
    sys.path.insert(0, str(SUITE_ROOT))

from shared_workspace import RefreshLeaseConflict, SharedWorkspace


USER_AGENT = "BWC-Axon-Reporting-Prototype/0.2.6"
PATH_CONFIG_KEYS = [
    "raw_dir",
    "schema_dir",
    "processed_dir",
    "sync_log_csv",
    "device_home_crosswalk_csv",
    "device_status_map_csv",
    "axon_group_crosswalk_csv",
    "non_site_group_register_csv",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def local_date_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_config_paths(cfg: dict, config_path: Path) -> dict:
    """Resolve package-relative paths from the configuration file's folder."""

    config_dir = config_path.resolve().parent
    for key in PATH_CONFIG_KEYS:
        value = cfg.get(key)
        if not value:
            continue
        path = Path(str(value))
        if not path.is_absolute():
            cfg[key] = str((config_dir / path).resolve())
    return cfg


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def get_path(obj: Any, path: str | None) -> Any:
    if not path:
        return obj
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            idx = int(part)
            cur = cur[idx] if idx < len(cur) else None
        else:
            return None
    return cur


def first_value(obj: Any, spec: str | list[str] | None) -> Any:
    if spec is None:
        return None
    if isinstance(spec, str):
        return get_path(obj, spec)
    for path in spec:
        value = get_path(obj, path)
        if value not in (None, ""):
            return value
    return None


def extract_records(payload: Any, paths: Iterable[str] | None = None) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]

    if not isinstance(payload, dict):
        return []

    candidates = list(paths or []) + ["data", "value", "items", "results"]
    seen = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        value = get_path(payload, path)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]

    return []


def find_next_link(payload: Any, configured_paths: Iterable[str] | None = None) -> str | None:
    # Prefer explicitly configured locations.
    for path in configured_paths or []:
        value = get_path(payload, path)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Axon exports/API versions have used link objects in different shapes.
    # Search dictionary nodes only (not the record arrays) to avoid treating
    # application data as pagination metadata.
    def walk(node: Any, depth: int = 0) -> str | None:
        if depth > 4 or not isinstance(node, dict):
            return None
        for key, value in node.items():
            k = str(key).lower().replace("_", "")
            if k in {"next", "nextlink", "nextpage"} and isinstance(value, str) and value.strip():
                return value.strip()
        for key, value in node.items():
            if isinstance(value, dict) and str(key).lower() in {
                "links", "_links", "pagination", "meta", "metadata", "page"
            }:
                found = walk(value, depth + 1)
                if found:
                    return found
        return None

    return walk(payload)


def collect_field_paths(obj: Any, prefix: str = "", depth: int = 0, max_depth: int = 6) -> list[str]:
    if depth > max_depth:
        return []
    paths: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            paths.append(path)
            if isinstance(value, dict):
                paths.extend(collect_field_paths(value, path, depth + 1, max_depth))
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                paths.extend(collect_field_paths(value[0], f"{path}.0", depth + 1, max_depth))
    return sorted(set(paths))


def resolve_url(base_url: str, endpoint_or_url: str) -> str:
    if endpoint_or_url.startswith("https://"):
        base = urllib.parse.urlparse(base_url)
        candidate = urllib.parse.urlparse(endpoint_or_url)
        if candidate.netloc.casefold() != base.netloc.casefold():
            raise RuntimeError("Axon pagination URL changed hosts; request refused to protect the access token.")
        return endpoint_or_url
    if endpoint_or_url.startswith(("http://", "//")):
        raise RuntimeError("Axon endpoints and pagination URLs must use the configured HTTPS tenant host.")
    return base_url.rstrip("/") + "/" + endpoint_or_url.lstrip("/")


def format_endpoint(endpoint: str, agency_id: str) -> str:
    return endpoint.replace("{agency_id}", agency_id).replace("{agencyId}", agency_id)


class AxonClient:
    def __init__(self, agency_base_url: str, client_id: str, client_secret: str, timeout_seconds: int = 90):
        self.agency_base_url = agency_base_url.rstrip("/")
        self.token_url = self.agency_base_url + "/api/oauth2/token"
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout_seconds = timeout_seconds
        self.access_token: str | None = None
        self.token_expires_in: int | None = None
        self.http_429_count = 0
        self.http_5xx_retry_count = 0
        self._last_request_monotonic: float | None = None

    def wait_for_request_slot(self, minimum_interval_seconds: float) -> None:
        """Apply a documented per-IP request interval before a read request."""
        if minimum_interval_seconds <= 0:
            return
        now = time.monotonic()
        if self._last_request_monotonic is not None:
            elapsed = now - self._last_request_monotonic
            remaining = minimum_interval_seconds - elapsed
            if remaining > 0:
                print(f"Request pacing: waiting {remaining:.1f}s.")
                time.sleep(remaining)
        self._last_request_monotonic = time.monotonic()

    def authenticate(self) -> None:
        # Axon documentation: Partner/Agency ID is NOT submitted in the token body.
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }).encode("utf-8")

        req = urllib.request.Request(
            self.token_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OAuth token request failed: HTTP {exc.code}\n{detail[:1000]}") from exc

        token = payload.get("access_token")
        if not token:
            raise RuntimeError("Token response did not contain access_token.")
        self.access_token = token
        try:
            self.token_expires_in = int(payload.get("expires_in"))
        except (TypeError, ValueError):
            self.token_expires_in = None

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        minimum_interval_seconds: float = 0,
        max_retries: int = 6,
    ) -> Any:
        if not self.access_token:
            raise RuntimeError("Client is not authenticated.")

        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}{'&' if '?' in url else '?'}{query}"

        attempt = 0
        while True:
            self.wait_for_request_slot(minimum_interval_seconds)
            req = urllib.request.Request(
                url,
                method="GET",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT,
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < max_retries:
                    self.http_429_count += 1
                    retry_after = exc.headers.get("Retry-After")
                    try:
                        wait_seconds = max(1, int(retry_after))
                    except (TypeError, ValueError):
                        # Axon guidance: if Retry-After is absent, wait at least 5 minutes.
                        wait_seconds = 300
                    print(f"HTTP 429; waiting {wait_seconds}s before retry.")
                    time.sleep(wait_seconds)
                    attempt += 1
                    continue

                if 500 <= exc.code < 600 and attempt < max_retries:
                    self.http_5xx_retry_count += 1
                    wait_seconds = min(60, 2 ** attempt)
                    print(f"HTTP {exc.code}; retrying after {wait_seconds}s.")
                    time.sleep(wait_seconds)
                    attempt += 1
                    continue

                detail = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"GET failed: HTTP {exc.code} {url}\n{detail[:1500]}") from exc


def load_lookup_csv(path: str | None, key_col: str, value_cols: list[str]) -> dict[str, dict[str, str]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with p.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row.get(key_col) or "").strip()
            if key:
                out[key] = {c: (row.get(c) or "").strip() for c in value_cols}
    return out


def rows_index(rows: list[dict], key: str) -> dict[str, dict]:
    out = {}
    for row in rows:
        value = str(row.get(key) or "").strip()
        if value:
            out[value] = row
    return out


def normalize_device_home_key(value: object) -> str:
    """Conservative join key; duplicate/rename review remains mandatory."""
    return " ".join(str(value or "").casefold().split())


def reviewed_site_mapping(mapping: dict[str, str] | None) -> dict[str, str]:
    """Return a site mapping only after the governed row is explicitly mapped."""
    candidate = mapping or {}
    site_id = str(candidate.get("Site ID") or "").strip()
    status = str(candidate.get("Mapping Status") or "").strip().casefold()
    return candidate if site_id and status == "mapped" else {}


def user_display_name(user: dict | None) -> str:
    if not user:
        return ""
    return " ".join(x for x in [str(user.get("First Name") or "").strip(),
                                str(user.get("Last Name") or "").strip()] if x).strip()


def map_rows(
    resource_name: str,
    records: list[dict],
    field_map: dict[str, str | list[str]],
    cfg: dict,
    context_rows: dict[str, list[dict]],
) -> list[dict]:
    now = utc_now_iso()

    group_crosswalk = load_lookup_csv(
        cfg.get("axon_group_crosswalk_csv"),
        "Axon Group ID",
        ["Site ID", "Component", "Region / AOR", "Mapping Status"],
    )
    non_site_group_register = load_lookup_csv(
        cfg.get("non_site_group_register_csv"),
        "Axon Group ID",
        [
            "Group Classification",
            "Command Hierarchy Level",
            "Reporting Inclusion",
            "Mapping Status",
            "Review Notes",
        ],
    )
    home_crosswalk = load_lookup_csv(
        cfg.get("device_home_crosswalk_csv"),
        "Normalized Device Home Key",
        ["Site ID", "Component", "Region / AOR", "Mapping Status"],
    )
    status_map = load_lookup_csv(
        cfg.get("device_status_map_csv"),
        "Raw Axon Device Status",
        ["Reporting State"],
    )
    status_map = {str(key).strip().casefold(): value for key, value in status_map.items()}

    groups_by_id = rows_index(context_rows.get("Groups", []), "Axon Group ID")
    homes_by_key = rows_index(context_rows.get("DeviceHomes", []), "Normalized Device Home Key")
    users_by_id = rows_index(context_rows.get("Users", []), "Axon User ID")

    rows: list[dict] = []
    for rec in records:
        row = {target: first_value(rec, source) for target, source in field_map.items()}

        if resource_name == "DeviceHomes":
            home_name = str(row.get("Device Home Name (API)") or "").strip()
            home_key = normalize_device_home_key(home_name)
            row["Normalized Device Home Key"] = home_key
            x = home_crosswalk.get(home_key, {})
            site_mapping = reviewed_site_mapping(x)
            poc_id = str(row.get("Point of Contact User ID") or "").strip()
            row["Point of Contact Name"] = user_display_name(users_by_id.get(poc_id))
            row["Mapped Site ID"] = site_mapping.get("Site ID", "")
            row["Mapped Component"] = site_mapping.get("Component", "")
            row["Mapped Region / AOR"] = site_mapping.get("Region / AOR", "")
            row["Mapping Status"] = x.get("Mapping Status", "Unmapped")
            row["Last Sync At"] = now
            row["Sync Status"] = "Synced"

        elif resource_name == "Groups":
            group_id = str(row.get("Axon Group ID") or "").strip()
            x = group_crosswalk.get(group_id, {})
            site_mapping = reviewed_site_mapping(x)
            non_site = non_site_group_register.get(group_id, {})
            row["Mapped Site ID"] = site_mapping.get("Site ID", "")
            row["Mapped Component"] = site_mapping.get("Component", "")
            row["Mapped Region / AOR"] = site_mapping.get("Region / AOR", "")
            if site_mapping:
                row["Group Classification"] = "Site-Mapped"
                row["Command Hierarchy Level"] = "Site / Office"
                row["Reporting Inclusion"] = "Include"
                row["Mapping Status"] = x.get("Mapping Status", "Mapped")
                row["Review Notes"] = "Mapped through reviewed Axon Group crosswalk."
            else:
                row["Group Classification"] = non_site.get("Group Classification", "Unclassified")
                row["Command Hierarchy Level"] = non_site.get("Command Hierarchy Level", "")
                row["Reporting Inclusion"] = non_site.get("Reporting Inclusion", "Review")
                row["Mapping Status"] = non_site.get("Mapping Status") or x.get("Mapping Status", "Unmapped")
                row["Review Notes"] = non_site.get("Review Notes", "")
            row["Last Sync At"] = now
            row["Sync Status"] = "Synced"

        elif resource_name == "Users":
            # Users are account/profile records only. Site mapping is based on the
            # reviewed command hierarchy and Axon Groups, never on a user group field.
            row["Last Sync At"] = now
            row["Sync Status"] = "Synced"

        elif resource_name == "Devices":
            home_name = str(row.get("Device Home Name (API)") or "").strip()
            home_key = normalize_device_home_key(home_name)
            owner_id = str(row.get("Assigned User ID") or "").strip()
            home = homes_by_key.get(home_key, {})
            owner = users_by_id.get(owner_id, {})
            x = home_crosswalk.get(home_key, {})
            raw_status = str(row.get("Device Status") or "").strip()

            if not row.get("Device Home Name (API)"):
                row["Device Home Name (API)"] = home.get("Device Home Name (API)", "")
            row["Normalized Device Home Key"] = normalize_device_home_key(row.get("Device Home Name (API)"))
            if not row.get("Assigned User Name"):
                row["Assigned User Name"] = user_display_name(owner)
            poc_id = str(home.get("Point of Contact User ID") or "").strip()
            row["Point of Contact"] = user_display_name(users_by_id.get(poc_id))
            site_mapping = reviewed_site_mapping(x)
            row["Mapped Site ID"] = site_mapping.get("Site ID", "")
            row["Last Sync At"] = now
            row["Sync Status"] = "Synced"
            row["Reporting Device State"] = status_map.get(raw_status.casefold(), {}).get("Reporting State", "Unmapped")

        rows.append(row)

    return rows


def write_csv(rows: list[dict], headers: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_schema_summary(resource: str, payload: Any, records: list[dict], next_link: str | None, path: Path) -> None:
    summary = {
        "resource": resource,
        "captured_at": utc_now_iso(),
        "record_count_on_probe_page": len(records),
        "top_level_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        "next_link_detected": bool(next_link),
        "first_record_field_paths": collect_field_paths(records[0]) if records else [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def fetch_resource(
    client: AxonClient,
    cfg: dict,
    resource_name: str,
    resource_cfg: dict,
    agency_id: str,
    probe_only: bool = False,
) -> tuple[list[dict], int, str | None]:
    base_url = cfg["agency_base_url"].rstrip("/")
    endpoint = format_endpoint(resource_cfg["endpoint"], agency_id)
    current_url = resolve_url(base_url, endpoint)

    params = dict(resource_cfg.get("probe_params" if probe_only else "sync_params", {}))
    page_size = int(resource_cfg.get("page_size", params.get("limit", 0) or 0))
    offset_param = resource_cfg.get("offset_param", "offset")
    next_paths = resource_cfg.get("next_paths", [])
    max_pages = 1 if probe_only else int(resource_cfg.get("max_pages", 10000))
    items_paths = resource_cfg.get("items_paths", ["data", "value"])
    pagination_mode = resource_cfg.get("pagination_mode", "none")
    request_interval_seconds = float(resource_cfg.get("request_interval_seconds", 0) or 0)
    keep_raw = bool(cfg.get("keep_raw_json", False))

    all_records: list[dict] = []
    pages = 0
    last_next: str | None = None

    for page in range(1, max_pages + 1):
        pages = page
        payload = client.get_json(current_url, params, request_interval_seconds)
        records = extract_records(payload, items_paths)
        all_records.extend(records)

        if keep_raw:
            raw_path = Path(cfg.get("raw_dir", "data/raw")) / (
                f"{resource_name.lower()}_{utc_stamp()}_page_{page:05d}.json"
            )
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        next_link = find_next_link(payload, next_paths)
        last_next = next_link

        if probe_only or pagination_mode == "none":
            break

        if next_link:
            next_url = resolve_url(base_url, next_link)
            if next_url == current_url:
                break
            current_url = next_url
            params = {}  # next link already contains its query string
            continue

        # Fallback for documented Axon limit/offset resources if a next link
        # is not present or is not exposed by a particular API version.
        if pagination_mode in {"offset", "next_or_offset"} and page_size > 0:
            if not records or len(records) < page_size:
                break
            current_offset = int(params.get(offset_param, 0) or 0)
            params[offset_param] = current_offset + len(records)
            continue

        break

    return all_records, pages, last_next


def write_legacy_exports(context_rows: dict[str, list[dict]], processed_dir: Path) -> None:
    """Create transition-friendly extracts for the existing BWC analytics process."""
    date = local_date_stamp()
    users_by_id = rows_index(context_rows.get("Users", []), "Axon User ID")
    devices = context_rows.get("Devices", [])

    device_headers = [
        "Device Model", "Device Name", "Serial Number", "Device Status",
        "Last Name", "First Name", "Badge ID", "Last Connected Dock", "Device Home"
    ]
    device_rows = []
    for d in devices:
        owner = users_by_id.get(str(d.get("Assigned User ID") or "").strip(), {})
        device_rows.append({
            "Device Model": d.get("Device Model", ""),
            "Device Name": d.get("Device Name", ""),
            "Serial Number": d.get("Serial Number", ""),
            "Device Status": d.get("Device Status", ""),
            "Last Name": owner.get("Last Name", ""),
            "First Name": owner.get("First Name", ""),
            "Badge ID": owner.get("Badge ID", ""),
            # Not verified in the supplied Partner API device-list contract.
            "Last Connected Dock": "",
            "Device Home": d.get("Device Home Name (API)", ""),
        })
    write_csv(
        device_rows,
        device_headers,
        processed_dir / f"reports.devicesSummary_API_{date}.csv",
    )

    user_headers = [
        "Axon User ID", "External ID", "Badge ID", "First Name", "Last Name",
        "Email", "User Status", "Role", "Last Activity", "Source Updated At"
    ]
    write_csv(
        context_rows.get("Users", []),
        user_headers,
        processed_dir / f"reports.userSummary_for_All_users_API_{date}.csv",
    )


def compact_counts(values: Iterable[str]) -> str:
    counts: dict[str, int] = {}
    for value in values:
        text = str(value or "").strip() or "Blank"
        counts[text] = counts.get(text, 0) + 1
    return "; ".join(f"{key}: {counts[key]}" for key in sorted(counts))


def write_assignment_and_status_reports(context_rows: dict[str, list[dict]], processed_dir: Path) -> None:
    """Create review reports without changing Axon data or inferring a site from a user."""
    date = local_date_stamp()
    users = context_rows.get("Users", [])
    devices = context_rows.get("Devices", [])
    devices_by_owner: dict[str, list[dict]] = {}
    for device in devices:
        owner_id = str(device.get("Assigned User ID") or "").strip()
        if owner_id:
            devices_by_owner.setdefault(owner_id, []).append(device)

    assignment_headers = [
        "Axon User ID", "External ID", "Badge ID", "First Name", "Last Name", "Email",
        "User Status", "Role", "Assigned Device Count", "Assigned Device Models",
        "Reporting Device State Counts", "Raw Device Status Counts", "Mapped Device Site IDs",
    ]
    assignment_rows = []
    for user in users:
        user_id = str(user.get("Axon User ID") or "").strip()
        assigned = devices_by_owner.get(user_id, [])
        assignment_rows.append({
            "Axon User ID": user_id,
            "External ID": user.get("External ID", ""),
            "Badge ID": user.get("Badge ID", ""),
            "First Name": user.get("First Name", ""),
            "Last Name": user.get("Last Name", ""),
            "Email": user.get("Email", ""),
            "User Status": user.get("User Status", ""),
            "Role": user.get("Role", ""),
            "Assigned Device Count": len(assigned),
            "Assigned Device Models": "; ".join(sorted({str(d.get("Device Model") or "").strip() for d in assigned if d.get("Device Model")})),
            "Reporting Device State Counts": compact_counts(d.get("Reporting Device State") for d in assigned),
            "Raw Device Status Counts": compact_counts(d.get("Device Status") for d in assigned),
            "Mapped Device Site IDs": "; ".join(sorted({str(d.get("Mapped Site ID") or "").strip() for d in assigned if d.get("Mapped Site ID")})),
        })
    write_csv(
        assignment_rows,
        assignment_headers,
        processed_dir / f"reports.user_device_assignment_summary_{date}.csv",
    )

    summary_counts: dict[tuple[str, str, str, str], int] = {}
    exception_rows = []
    review_states = {"unassigned", "in stock", "lost", "relinquished", "unmapped"}
    for device in devices:
        owner_id = str(device.get("Assigned User ID") or "").strip()
        assignment_state = "Assigned" if owner_id else "Unassigned"
        reporting_state = str(device.get("Reporting Device State") or "Unmapped").strip() or "Unmapped"
        raw_status = str(device.get("Device Status") or "").strip() or "Blank"
        model = str(device.get("Device Model") or "").strip() or "Blank"
        key = (model, raw_status, reporting_state, assignment_state)
        summary_counts[key] = summary_counts.get(key, 0) + 1
        if not owner_id or reporting_state.casefold() in review_states or not device.get("Mapped Site ID"):
            exception_rows.append(device)

    status_headers = ["Device Model", "Raw Axon Device Status", "Reporting Device State", "Assignment State", "Device Count"]
    status_rows = [
        {
            "Device Model": model,
            "Raw Axon Device Status": raw_status,
            "Reporting Device State": reporting_state,
            "Assignment State": assignment_state,
            "Device Count": count,
        }
        for (model, raw_status, reporting_state, assignment_state), count in sorted(summary_counts.items())
    ]
    write_csv(status_rows, status_headers, processed_dir / f"reports.device_status_summary_{date}.csv")

    exception_headers = [
        "Axon Device ID", "Serial Number", "Device Model", "Device Name", "Device Status",
        "Reporting Device State", "Assigned User ID", "Assigned User Name", "Device Home Name (API)",
        "Mapped Site ID", "Last Upload", "Last Connected", "Error Status",
    ]
    write_csv(
        exception_rows,
        exception_headers,
        processed_dir / f"reports.device_assignment_and_status_exceptions_{date}.csv",
    )


def apply_device_filters(cfg: dict, args: argparse.Namespace) -> None:
    """Apply documented device-list filters only; values are sent to Axon unchanged."""
    if not any([args.device_model, args.device_status, args.device_home_id]):
        return
    devices = cfg.get("resources", {}).get("Devices")
    if not devices:
        raise SystemExit("Devices resource is not configured.")
    params = devices.setdefault("sync_params", {})
    if args.device_model:
        params["model"] = ",".join(args.device_model)
    if args.device_status:
        if len(args.device_status) != 1:
            raise SystemExit("Use one exact --device-status value; multiple status values are not documented for this endpoint.")
        params["status2"] = args.device_status[0]
    if args.device_home_id:
        if len(args.device_home_id) != 1:
            raise SystemExit("Use one exact --device-home-id value; multiple home IDs are not documented for this endpoint.")
        params["homeId"] = args.device_home_id[0]


def run_group_hierarchy(client: AxonClient, cfg: dict, agency_id: str, group_ids: list[str]) -> None:
    if not group_ids:
        raise SystemExit("Hierarchy requests require one or more --group-id values.")
    processed_dir = Path(cfg.get("processed_dir", "data/processed"))
    interval = float(cfg.get("group_hierarchy_request_interval_seconds", 5) or 0)
    base_url = cfg["agency_base_url"].rstrip("/")
    rows = []
    for root_group_id in group_ids:
        endpoint = f"/api/v1/agencies/{agency_id}/hierarchy/{urllib.parse.quote(root_group_id, safe='')}/children"
        payload = client.get_json(resolve_url(base_url, endpoint), minimum_interval_seconds=interval)
        children = extract_records(payload, ["data", "children", "value", "items", "results"])
        retrieved = utc_now_iso()
        if not children:
            rows.append({
                "Root Group ID": root_group_id,
                "Child Group ID": "",
                "Child Group Name": "",
                "Child External Group ID": "",
                "Retrieved At": retrieved,
                "Result": "No child records returned",
            })
            continue
        for child in children:
            rows.append({
                "Root Group ID": root_group_id,
                "Child Group ID": first_value(child, ["id", "attributes.id"]) or "",
                "Child Group Name": first_value(child, ["attributes.name", "name"]) or "",
                "Child External Group ID": first_value(child, ["attributes.externalId", "externalId"]) or "",
                "Retrieved At": retrieved,
                "Result": "Retrieved",
            })
    headers = ["Root Group ID", "Child Group ID", "Child Group Name", "Child External Group ID", "Retrieved At", "Result"]
    out = processed_dir / f"axon_group_hierarchy_{local_date_stamp()}.csv"
    write_csv(rows, headers, out)
    print(f"Group hierarchy: {len(rows)} rows -> {out}")


def append_sync_log(path: Path, row: dict) -> None:
    headers = [
        "Run ID", "Start Time", "End Time", "Resource", "Mode", "Records Read",
        "Pages", "HTTP 429 Count", "HTTP 5XX Retries", "Status", "Next Link Seen", "Notes"
    ]
    exists = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def configured_resources(cfg: dict, names: list[str] | None) -> list[tuple[str, dict]]:
    resources = cfg.get("resources", {})
    wanted = names or list(resources.keys())
    selected = []
    for name in wanted:
        if name not in resources:
            raise SystemExit(f"Unknown resource: {name}")
        rcfg = resources[name]
        if rcfg.get("method", "GET").upper() != "GET":
            raise SystemExit(f"{name}: only GET resource calls are allowed.")
        selected.append((name, rcfg))
    return selected


def validate(cfg: dict) -> int:
    errors: list[str] = []
    base = cfg.get("agency_base_url", "")
    if not base.startswith("https://"):
        errors.append("agency_base_url must be an HTTPS Axon Evidence tenant URL.")
    for name, rcfg in cfg.get("resources", {}).items():
        if not rcfg.get("endpoint"):
            errors.append(f"{name}: endpoint missing")
        if rcfg.get("method", "GET").upper() != "GET":
            errors.append(f"{name}: resource method must be GET")
        if not rcfg.get("field_map"):
            errors.append(f"{name}: field_map missing")

    if errors:
        for e in errors:
            print("ERROR:", e)
        return 2

    print("Configuration is structurally valid.")
    print("Credentials are intentionally not checked by validate.")
    for name, rcfg in cfg.get("resources", {}).items():
        print(
            f"- {name}: {rcfg['endpoint']} | "
            f"page_size={rcfg.get('page_size', 'n/a')} | "
            f"pagination={rcfg.get('pagination_mode', 'none')}"
        )
    return 0


def run_probe(client: AxonClient, cfg: dict, names: list[str] | None, agency_id: str) -> None:
    schema_dir = Path(cfg.get("schema_dir", "data/schemas"))
    for name, rcfg in configured_resources(cfg, names):
        records, pages, next_link = fetch_resource(client, cfg, name, rcfg, agency_id, probe_only=True)
        # Fetch once more only when needed to capture the payload schema? Instead,
        # build a schema summary from mapped sample records to avoid PII retention.
        mapped = map_rows(name, records[:1], rcfg["field_map"], cfg, {})
        summary = {
            "resource": name,
            "captured_at": utc_now_iso(),
            "records_on_probe_page": len(records),
            "pages_requested": pages,
            "next_link_detected": bool(next_link),
            "mapped_sample_columns": list(mapped[0].keys()) if mapped else list(rcfg["field_map"].keys()),
            "record_field_paths": collect_field_paths(records[0]) if records else [],
        }
        out = schema_dir / f"{name.lower()}_schema_{utc_stamp()}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"{name}: {len(records)} records on probe page; schema -> {out}")


def run_sync(client: AxonClient, cfg: dict, names: list[str] | None, agency_id: str) -> None:
    processed_dir = Path(cfg.get("processed_dir", "data/processed"))
    log_path = Path(cfg.get("sync_log_csv", "state/sync_log.csv"))
    run_id = f"SYNC-{utc_stamp()}"
    workspace = SharedWorkspace()
    workspace.bind_tenant(cfg["agency_base_url"])
    owner_id = f"read-only-sync-{os.getpid()}"
    context_rows: dict[str, list[dict]] = {}

    # Dependencies matter for enrichment: Device Homes + Groups -> Users -> Devices.
    preferred_order = ["DeviceHomes", "Groups", "Users", "Devices"]
    requested = [n for n, _ in configured_resources(cfg, names)]
    ordered = [n for n in preferred_order if n in requested] + [n for n in requested if n not in preferred_order]

    for name in ordered:
        rcfg = cfg["resources"][name]
        start = utc_now_iso()
        status = "Success"
        notes = ""
        records: list[dict] = []
        pages = 0
        next_link = None
        refresh_id = ""
        snapshot_id = ""
        before_429 = client.http_429_count
        before_5xx = client.http_5xx_retry_count

        device_filters = {
            key: value
            for key, value in rcfg.get("sync_params", {}).items()
            if key in {"model", "status2", "homeId"} and value not in (None, "")
        }
        scope = {
            "type": "filtered" if name == "Devices" and device_filters else "full",
            "filters": device_filters,
        }

        try:
            refresh_id = workspace.acquire_refresh_lease(name, owner_id, scope)
            records, pages, next_link = fetch_resource(client, cfg, name, rcfg, agency_id, probe_only=False)
            mapped = map_rows(name, records, rcfg["field_map"], cfg, context_rows)
            context_rows[name] = mapped
            output_headers = rcfg["output_headers"]
            out_csv = processed_dir / rcfg["output_csv"]
            write_csv(mapped, output_headers, out_csv)
            snapshot = workspace.activate_snapshot(
                name,
                mapped,
                scope=scope,
                source="Axon read-only sync prototype v0.2.6",
                lease_id=refresh_id,
            )
            snapshot_id = snapshot["snapshotId"]
            workspace.release_refresh_lease(name, owner_id, refresh_id, "completed", snapshot_id=snapshot_id)
            refresh_id = ""
            scope_label = "filtered" if scope["type"] == "filtered" else "full"
            print(
                f"{name}: {len(mapped)} records across {pages} page(s) -> {out_csv}; "
                f"activated shared {scope_label} snapshot {snapshot_id}"
            )
        except RefreshLeaseConflict as exc:
            status = "Blocked"
            notes = str(exc)[:1000]
            raise SystemExit(str(exc)) from exc
        except Exception as exc:
            status = "Failed"
            notes = str(exc)[:1000]
            raise
        finally:
            if refresh_id:
                workspace.release_refresh_lease(name, owner_id, refresh_id, "failed", notes or "Refresh did not complete.")
            append_sync_log(log_path, {
                "Run ID": run_id,
                "Start Time": start,
                "End Time": utc_now_iso(),
                "Resource": name,
                "Mode": f"{scope['type'].title()}/Read-Only",
                "Records Read": len(records),
                "Pages": pages,
                "HTTP 429 Count": client.http_429_count - before_429,
                "HTTP 5XX Retries": client.http_5xx_retry_count - before_5xx,
                "Status": status,
                "Next Link Seen": "Y" if next_link else "N",
                "Notes": notes,
            })

    write_legacy_exports(context_rows, processed_dir)
    if "Devices" in context_rows:
        write_assignment_and_status_reports(context_rows, processed_dir)
    print("Compatibility, device-status, and user-device assignment reports created.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate", "probe", "sync", "hierarchy"])
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--resource", action="append", help="Limit to one/more resources; repeatable.")
    parser.add_argument("--device-model", action="append", help="Exact Axon model string; repeat or use comma-separated values.")
    parser.add_argument("--device-status", action="append", help="One exact documented status2 value.")
    parser.add_argument("--device-home-id", action="append", help="One exact documented homeId value.")
    parser.add_argument("--group-id", action="append", help="Group ID for the read-only hierarchy command; repeatable.")
    args = parser.parse_args()

    config_path = Path(args.config)
    cfg = resolve_config_paths(load_json(config_path), config_path)
    if args.command == "validate":
        return validate(cfg)
    apply_device_filters(cfg, args)

    agency_id = require_env("AXON_PARTNER_ID")
    client = AxonClient(
        agency_base_url=cfg["agency_base_url"],
        client_id=require_env("AXON_CLIENT_ID"),
        client_secret=require_env("AXON_CLIENT_SECRET"),
        timeout_seconds=int(cfg.get("timeout_seconds", 90)),
    )
    client.authenticate()

    if args.command == "probe":
        run_probe(client, cfg, args.resource, agency_id)
    elif args.command == "sync":
        run_sync(client, cfg, args.resource, agency_id)
    else:
        run_group_hierarchy(client, cfg, agency_id, args.group_id or [])

    if client.token_expires_in is not None:
        print(f"Token lifetime reported by Axon: {client.token_expires_in}s")
    if client.http_429_count:
        print(f"HTTP 429 responses handled: {client.http_429_count}")
    if client.http_5xx_retry_count:
        print(f"5XX retries handled: {client.http_5xx_retry_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
