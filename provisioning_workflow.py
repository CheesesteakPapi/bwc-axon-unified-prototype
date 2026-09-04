"""Canonical, fileless provisioning-run workflow for BWC Axon V3.1.0."""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

from shared_workspace import SharedWorkspace, canonical_json, safe_csv_value, value_hash


USER_HEADERS = [
    "EXTERNAL_ID",
    "EMAIL",
    "BADGE_NUMBER",
    "FIRST_NAME",
    "LAST_NAME",
    "STATUS",
    "USERNAME",
    "ROLE",
    "SUPERVISOR_EMAIL",
    "LOCATION",
    "EVIDENCE_GROUP_EXT_ID",
    "PHONE",
    "RANK",
]
GROUP_HEADERS = ["EXTERNAL_ID", "MEMBERSHIP_TYPE", "ENTITY_TYPE", "ENTITY_ID"]
ASSIGNMENT_EDIT_FIELDS = {
    "role",
    "groupName",
    "groupExternalId",
    "location",
    "personnelAor",
    "jobCategory",
    "supervisorEmail",
    "supervisorUpn",
}
INPUT_ALIASES = {
    "email": {"email", "email address", "mail", "user email", "work email"},
    "role": {"role", "axon role", "user role"},
    "groupName": {"group", "group name", "axon group", "axon group name", "organizational group"},
    "externalId": {"external id", "externalid", "employee id", "employeeid", "directory id", "object id"},
    "badgeNumber": {"badge", "badge number", "badgenumber"},
    "firstName": {"first name", "firstname", "given name", "givenname"},
    "lastName": {"last name", "lastname", "surname"},
    "username": {"username", "user name", "samaccountname"},
    "directoryAccountStatus": {"directory account status", "account enabled", "account status", "enabled"},
    "supervisorEmail": {"supervisor email", "manager email"},
    "supervisorUpn": {"supervisor upn", "manager upn"},
    "directoryLocation": {"directory location", "office location", "officelocation", "location", "site"},
    "component": {"component", "organization", "org component"},
    "jobTitle": {"job title", "jobtitle", "title"},
    "phone": {"phone", "phone number", "business phone", "mobile phone"},
    "rank": {"rank"},
}


class WorkflowError(ValueError):
    pass


def normalize_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().casefold()).strip()


def normalize_email(value: Any) -> str:
    return str(value or "").strip().casefold()


def truthy_account_status(value: Any) -> tuple[str, bool]:
    text = str(value if value is not None else "").strip()
    lowered = text.casefold()
    if lowered in {"false", "0", "disabled", "inactive", "no"}:
        return text or "Disabled", False
    return text or "Enabled", True


def detect_columns(headers: Iterable[str]) -> dict[str, Any]:
    normalized = {header: normalize_header(header) for header in headers}
    candidates: dict[str, list[str]] = {}
    for field, aliases in INPUT_ALIASES.items():
        matches = [header for header, key in normalized.items() if key in aliases]
        if matches:
            candidates[field] = matches
    ambiguous = {field: values for field, values in candidates.items() if len(values) > 1}
    mapping = {field: values[0] for field, values in candidates.items() if len(values) == 1}
    missing = [field for field in ("email", "role") if field not in mapping]
    return {"mapping": mapping, "ambiguous": ambiguous, "missingRequired": missing, "needsMapper": bool(ambiguous or missing)}


def parse_csv_bytes(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    if content.startswith(b"\xef\xbb\xbf"):
        text = content.decode("utf-8-sig")
    else:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkflowError("The intake CSV must be UTF-8. Save it as UTF-8 and try again.") from exc
    reader = csv.DictReader(io.StringIO(text))
    headers = [str(value or "").strip() for value in (reader.fieldnames or [])]
    if not headers:
        raise WorkflowError("The intake file does not contain a header row.")
    rows = [
        {str(key or "").strip(): str(value or "").strip() for key, value in raw.items()}
        for raw in reader
        if any(str(value or "").strip() for value in raw.values())
    ]
    return headers, rows


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    return ["".join(node.text or "" for node in item.iter(namespace + "t")) for item in root.findall(namespace + "si")]


def _column_number(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference.upper())
    result = 0
    for char in (letters.group(0) if letters else "A"):
        result = result * 26 + ord(char) - 64
    return result - 1


def parse_xlsx_bytes(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if any(name.casefold().endswith("vbaproject.bin") for name in archive.namelist()):
                raise WorkflowError("Macro-enabled workbooks are not accepted. Provide a plain .xlsx file.")
            shared = _xlsx_shared_strings(archive)
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
            rel_ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
            target_by_id = {rel.attrib["Id"]: rel.attrib["Target"] for rel in relationships.findall(rel_ns + "Relationship")}
            first_sheet = workbook.find("m:sheets/m:sheet", ns)
            if first_sheet is None:
                raise WorkflowError("The workbook contains no worksheets.")
            rel_id = first_sheet.attrib.get("{" + ns["r"] + "}id", "")
            target = target_by_id.get(rel_id, "worksheets/sheet1.xml").lstrip("/")
            sheet_path = target if target.startswith("xl/") else "xl/" + target
            sheet_root = ElementTree.fromstring(archive.read(sheet_path))
            main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
            table: list[list[str]] = []
            for row_node in sheet_root.findall(".//" + main + "sheetData/" + main + "row"):
                row: list[str] = []
                for cell in row_node.findall(main + "c"):
                    index = _column_number(cell.attrib.get("r", "A1"))
                    while len(row) <= index:
                        row.append("")
                    cell_type = cell.attrib.get("t", "")
                    if cell_type == "inlineStr":
                        value = "".join(node.text or "" for node in cell.iter(main + "t"))
                    else:
                        value_node = cell.find(main + "v")
                        raw = value_node.text if value_node is not None and value_node.text is not None else ""
                        value = shared[int(raw)] if cell_type == "s" and raw.isdigit() and int(raw) < len(shared) else raw
                    row[index] = value
                table.append(row)
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise WorkflowError("The .xlsx file could not be read safely.") from exc
    if not table:
        raise WorkflowError("The first worksheet is empty.")
    headers = [str(value).strip() for value in table[0]]
    rows = []
    for values in table[1:]:
        values = values + [""] * (len(headers) - len(values))
        if any(str(value).strip() for value in values):
            rows.append({header: str(values[index]).strip() for index, header in enumerate(headers) if header})
    return headers, rows


def parse_intake_file(name: str, content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    suffix = Path(name).suffix.casefold()
    if suffix == ".csv":
        return parse_csv_bytes(content)
    if suffix == ".xlsx":
        return parse_xlsx_bytes(content)
    raise WorkflowError("Intake accepts only .csv and .xlsx files.")


def canonicalize_input(rows: list[dict[str, Any]], mapping: dict[str, str] | None = None) -> list[dict[str, str]]:
    if not rows:
        raise WorkflowError("Add at least one user.")
    if len(rows) > 1500:
        raise WorkflowError("A provisioning run is limited to 1,500 users.")
    headers = list(rows[0])
    detection = detect_columns(headers)
    selected = dict(detection["mapping"])
    selected.update(mapping or {})
    missing = [field for field in ("email", "role") if not selected.get(field)]
    if missing:
        raise WorkflowError("Map the required columns before continuing: " + ", ".join(missing))
    result = []
    for raw in rows:
        row = {field: str(raw.get(header) or "").strip() for field, header in selected.items()}
        if not row.get("email") and not any(row.values()):
            continue
        result.append(row)
    return result


def _lookup_value(row: dict[str, Any], *names: str) -> str:
    by_key = {normalize_header(key): str(value or "").strip() for key, value in row.items()}
    for name in names:
        if normalize_header(name) in by_key:
            return by_key[normalize_header(name)]
    return ""


def _first_phone(value: Any) -> str:
    if isinstance(value, list):
        return next((str(item).strip() for item in value if str(item or "").strip()), "")
    return str(value or "").strip()


class DirectoryProvider:
    name = "directory"

    def resolve(self, emails: list[str]) -> dict[str, dict[str, Any]]:
        raise NotImplementedError


class RowDirectoryProvider(DirectoryProvider):
    def __init__(self, rows: list[dict[str, Any]], name: str = "directory-file") -> None:
        self.rows = rows
        self.name = name

    def resolve(self, emails: list[str]) -> dict[str, dict[str, Any]]:
        by_email = {}
        for row in self.rows:
            email = normalize_email(_lookup_value(row, "email", "mail"))
            if email:
                by_email[email] = row
        return {email: by_email[email] for email in emails if email in by_email}


class SyntheticDirectoryProvider(DirectoryProvider):
    name = "synthetic-test"

    def resolve(self, emails: list[str]) -> dict[str, dict[str, Any]]:
        resolved = {}
        for index, email in enumerate(emails, start=1):
            local = email.split("@", 1)[0]
            parts = [part for part in re.split(r"[._-]+", local) if part]
            first = (parts[0] if parts else f"Test{index}").title()
            last = (parts[-1] if len(parts) > 1 else "User").title()
            resolved[email] = {
                "mail": email,
                "userPrincipalName": email,
                "mailNickname": local,
                "givenName": first,
                "surname": last,
                "accountEnabled": True,
                "officeLocation": "Prototype Test Location",
                "department": "TEST",
                "externalId": f"SYNTH-{value_hash(email)[:12].upper()}",
                "badgeNumber": f"T{index:05d}",
                "firstName": first,
                "lastName": last,
                "username": email,
                "directoryAccountStatus": "Enabled",
                "directoryLocation": "Prototype Test Location",
                "component": "TEST",
                "jobTitle": "Prototype Standard User",
                "phone": "",
                "supervisorEmail": "",
                "supervisorUpn": "",
                "rank": "",
            }
        return resolved


class EntraDelegatedProvider(DirectoryProvider):
    """Read individual Entra users with a caller-supplied delegated token.

    Tokens are used only for these calls and are not stored in the workspace.
    No group endpoint or Graph write endpoint is used.
    """

    name = "entra-delegated"

    def __init__(self, access_token: str, timeout: int = 30) -> None:
        self.access_token = access_token
        self.timeout = timeout

    def resolve(self, emails: list[str]) -> dict[str, dict[str, Any]]:
        result = {}
        select = "id,mail,userPrincipalName,mailNickname,givenName,surname,accountEnabled,officeLocation,jobTitle,department,businessPhones,mobilePhone"
        for email in emails:
            escaped_email = email.replace("'", "''")
            query = urllib.parse.urlencode({"$filter": f"mail eq '{escaped_email}'", "$select": select, "$top": "2"})
            url = "https://graph.microsoft.com/v1.0/users?" + query
            request = urllib.request.Request(url, headers={"Authorization": "Bearer " + self.access_token, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                raise WorkflowError(f"Microsoft Graph could not resolve {email} (HTTP {exc.code}).") from exc

            candidates = payload.get("value", []) if isinstance(payload, dict) else []
            exact_matches = [item for item in candidates if isinstance(item, dict) and normalize_email(item.get("mail")) == email]
            if not exact_matches:
                continue
            if len(exact_matches) > 1:
                raise WorkflowError(f"Microsoft Graph returned more than one exact mail match for {email}.")

            data = exact_matches[0]
            object_id = str(data.get("id") or "").strip()
            if not object_id:
                raise WorkflowError(f"Microsoft Graph returned an exact mail match for {email} without an object ID.")

            manager_url = "https://graph.microsoft.com/v1.0/users/" + urllib.parse.quote(object_id, safe="") + "/manager?$select=mail,userPrincipalName"
            manager_request = urllib.request.Request(manager_url, headers={"Authorization": "Bearer " + self.access_token, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(manager_request, timeout=self.timeout) as response:
                    manager = json.loads(response.read().decode("utf-8"))
                data["supervisorEmail"] = str(manager.get("mail") or "")
                data["supervisorUpn"] = str(manager.get("userPrincipalName") or "")
            except urllib.error.HTTPError as exc:
                if exc.code not in {404}:
                    raise WorkflowError(f"Microsoft Graph could not read the manager for {email} (HTTP {exc.code}).") from exc

            upn = str(data.get("userPrincipalName") or "").strip()
            alias = str(data.get("mailNickname") or "").strip()
            data.update({
                "externalId": upn,
                "upn": upn,
                "badgeNumber": alias,
                "username": alias,
                "firstName": str(data.get("givenName") or "").strip(),
                "lastName": str(data.get("surname") or "").strip(),
                "directoryAccountStatus": data.get("accountEnabled"),
                "directoryLocation": str(data.get("officeLocation") or "").strip(),
                "component": str(data.get("department") or "").strip(),
                "phone": str(data.get("mobilePhone") or "").strip() or _first_phone(data.get("businessPhones")),
                "directoryMatchMethod": "Exact mail",
            })
            result[email] = data
        return result


def _dataset_rows(workspace: SharedWorkspace, key: str) -> list[dict[str, Any]]:
    try:
        return workspace.governance_dataset(key)["rows"]
    except KeyError:
        return []


def _current_users(workspace: SharedWorkspace) -> dict[str, dict[str, Any]]:
    snapshot = workspace.active_snapshot("Users")
    users = snapshot["rows"] if snapshot else []
    result = {}
    for row in users:
        email = normalize_email(_lookup_value(row, "EMAIL", "Email", "mail", "userName", "username"))
        if email:
            result[email] = row
    return result


def _group_candidates(workspace: SharedWorkspace) -> list[dict[str, Any]]:
    snapshot = workspace.active_snapshot("Groups")
    rows = snapshot["rows"] if snapshot else []
    if not rows:
        rows = _dataset_rows(workspace, "axon_group_master_starter")
    candidates = []
    for row in rows:
        name = _lookup_value(row, "Group Name", "name", "groupName", "Axon Group Name")
        external_id = _lookup_value(row, "External Group ID", "externalId", "EXTERNAL_ID", "id", "Axon Group ID")
        if name and external_id:
            candidates.append({"name": name, "externalId": external_id, "component": _lookup_value(row, "Component"), "aor": _lookup_value(row, "Organizational Area", "AOR", "Region / AOR"), "tier": _lookup_value(row, "Group Tier"), "parent": _lookup_value(row, "Parent Group ID"), "status": _lookup_value(row, "Mapping Status", "status")})
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in candidates:
        unique[(candidate["externalId"].casefold(), candidate["name"].casefold())] = candidate
    return sorted(
        unique.values(),
        key=lambda item: (
            item["name"].casefold(),
            item["component"].casefold(),
            item["aor"].casefold(),
            item["externalId"].casefold(),
        ),
    )


def group_options(workspace: SharedWorkspace) -> list[dict[str, Any]]:
    """Return current friendly Group choices for the local provisioning UI."""
    return _group_candidates(workspace)


def _directory_value(row: dict[str, Any], canonical: str, *aliases: str) -> str:
    if canonical in row and row[canonical] is not None:
        return str(row[canonical]).strip()
    return _lookup_value(row, canonical, *aliases)


def _governed_directory_value(workspace: SharedWorkspace, row: dict[str, Any], canonical: str, *fallback_aliases: str) -> str:
    for mapping in _dataset_rows(workspace, "directory_attribute_mapping"):
        if normalize_header(_lookup_value(mapping, "Canonical Field")) != normalize_header(canonical):
            continue
        if _lookup_value(mapping, "Review Status", "Status").casefold() not in {"approved", "reviewed", "active"}:
            break
        configured = _lookup_value(mapping, "Directory Attribute")
        attributes = [item.strip() for item in re.split(r"\s+or\s+|[,;]", configured, flags=re.IGNORECASE) if item.strip()]
        value = _lookup_value(row, *attributes)
        if value:
            return value
        break
    return _directory_value(row, canonical, *fallback_aliases)


def _map_location(workspace: SharedWorkspace, location: str, component: str) -> tuple[str, str]:
    normalized_location = normalize_header(location)
    normalized_component = normalize_header(component)
    matches = []
    for rule in _dataset_rows(workspace, "personnel_location_aor_crosswalk"):
        if normalize_header(_lookup_value(rule, "Directory Location", "Location")) != normalized_location:
            continue
        rule_component = normalize_header(_lookup_value(rule, "Component"))
        if rule_component and rule_component != normalized_component:
            continue
        if _lookup_value(rule, "Review Status", "Status").casefold() not in {"reviewed", "approved", "active"}:
            continue
        matches.append(rule)
    if len(matches) == 1:
        return _lookup_value(matches[0], "Effective Location", "Location") or location, _lookup_value(matches[0], "Personnel AOR", "AOR")
    return location, ""


def _classify_title(workspace: SharedWorkspace, title: str) -> str:
    normalized = normalize_header(title)
    for rule in _dataset_rows(workspace, "job_title_category_mapping"):
        if normalize_header(_lookup_value(rule, "Exact Job Title", "Job Title")) == normalized and _lookup_value(rule, "Review Status", "Status").casefold() in {"reviewed", "approved", "active"}:
            return _lookup_value(rule, "Job Category")
    return ""


def _group_rule(workspace: SharedWorkspace, component: str, aor: str, category: str) -> tuple[str, str]:
    if not component or not aor or not category:
        return "", "MEMBER" if category in {"", "Standard User"} else "MONITOR"
    for rule in _dataset_rows(workspace, "component_aor_group_rules"):
        if normalize_header(_lookup_value(rule, "Component")) != normalize_header(component):
            continue
        if normalize_header(_lookup_value(rule, "Personnel AOR", "AOR")) != normalize_header(aor):
            continue
        if normalize_header(_lookup_value(rule, "Job Category")) != normalize_header(category):
            continue
        if _lookup_value(rule, "Review Status", "Status").casefold() == "inactive":
            continue
        membership = _lookup_value(rule, "Membership Type") or ("MEMBER" if category == "Standard User" else "MONITOR")
        return _lookup_value(rule, "Group Name"), membership.upper()
    return "", "MEMBER" if category in {"", "Standard User"} else "MONITOR"


def _approved_roles(workspace: SharedWorkspace) -> set[str]:
    roles = set()
    for row in _dataset_rows(workspace, "approved_axon_role_catalog"):
        if _lookup_value(row, "Review Status", "Status").casefold() in {"reviewed", "approved", "active"}:
            role = _lookup_value(row, "Role Name", "Role")
            if role:
                roles.add(role.casefold())
    return roles


def resolve_group(workspace: SharedWorkspace, name: str, component: str, aor: str) -> tuple[dict[str, Any] | None, str]:
    matches = [item for item in _group_candidates(workspace) if item["name"].casefold() == name.casefold()]
    if not matches:
        return None, f'Group "{name}" does not resolve to the current Axon Groups snapshot or local Group master.'
    if len(matches) > 1:
        narrowed = [item for item in matches if (not item["component"] or normalize_header(item["component"]) == normalize_header(component)) and (not item["aor"] or normalize_header(item["aor"]) == normalize_header(aor))]
        if len(narrowed) == 1:
            return narrowed[0], ""
        descriptions = "; ".join(f"{item['name']} [{item['component'] or '—'} / {item['aor'] or '—'} / {item['tier'] or '—'} / {item['externalId']}]" for item in matches[:5])
        return None, f"Group name is ambiguous. Select one exact Group: {descriptions}"
    return matches[0], ""


def _ensure_observed_crosswalk_candidates(
    workspace: SharedWorkspace,
    directory: dict[str, dict[str, Any]],
    provider_name: str,
) -> dict[str, int]:
    """Queue new directory-derived mapping values for review without identities."""
    mapping_method = {
        "entra-delegated": "Observed from Entra",
        "sharepoint-export": "Observed from SharePoint export",
        "directory-file": "Observed from directory export",
        "synthetic-test": "Synthetic observation",
    }.get(provider_name, "Observed during directory enrichment")
    location_counts: Counter[tuple[str, str]] = Counter()
    location_display: dict[tuple[str, str], tuple[str, str]] = {}
    title_counts: Counter[str] = Counter()
    title_display: dict[str, str] = {}

    for source in directory.values():
        location = _governed_directory_value(
            workspace, source, "Directory Location", "directoryLocation", "officeLocation", "location"
        )
        component = _governed_directory_value(
            workspace, source, "Component", "component", "department", "companyName"
        )
        location_key = (normalize_header(location), normalize_header(component))
        if all(location_key):
            location_counts[location_key] += 1
            location_display.setdefault(location_key, (location, component))

        title = _governed_directory_value(workspace, source, "Job Title", "jobTitle", "title")
        title_key = normalize_header(title)
        if title_key:
            title_counts[title_key] += 1
            title_display.setdefault(title_key, title)

    location_candidates = []
    for key, count in location_counts.items():
        location, component = location_display[key]
        location_candidates.append(
            {
                "Directory Location": location,
                "Effective Location": location,
                "Component": component,
                "Personnel AOR": "",
                "Review Status": "Needs review",
                "Mapping Method": mapping_method,
                "Confidence": "Not rated",
                "Reviewer": "",
                "Reviewed At UTC": "",
                "Review Notes": f"Observed during provisioning enrichment for {count} intake row(s); optional AOR mapping requires review.",
            }
        )

    title_candidates = []
    for key, count in title_counts.items():
        title_candidates.append(
            {
                "Exact Job Title": title_display[key],
                "Job Category": "",
                "Review Status": "Needs review",
                "Mapping Method": mapping_method,
                "Confidence": "Not rated",
                "Reviewer": "",
                "Reviewed At UTC": "",
                "Review Notes": f"Observed during provisioning enrichment for {count} intake row(s); optional category mapping requires review.",
            }
        )

    location_result = workspace.ensure_governance_candidates(
        "personnel_location_aor_crosswalk",
        location_candidates,
        ("Directory Location", "Component"),
    )
    title_result = workspace.ensure_governance_candidates(
        "job_title_category_mapping",
        title_candidates,
        ("Exact Job Title",),
    )
    return {
        "locationAor": int(location_result.get("added", 0)),
        "jobCategory": int(title_result.get("added", 0)),
    }


def enrich_rows(workspace: SharedWorkspace, intake_rows: list[dict[str, str]], provider: DirectoryProvider) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    emails = [normalize_email(row.get("email")) for row in intake_rows]
    directory = provider.resolve(sorted(set(email for email in emails if email)))
    candidates_added = _ensure_observed_crosswalk_candidates(workspace, directory, provider.name)
    existing_users = _current_users(workspace)
    approved_roles = _approved_roles(workspace)
    duplicates = {email for email, count in Counter(emails).items() if email and count > 1}
    output = []
    for index, intake in enumerate(intake_rows, start=1):
        email = normalize_email(intake.get("email"))
        source = directory.get(email)
        blockers: list[str] = []
        warnings: list[str] = []
        if not email or "@" not in email:
            blockers.append("A valid email address is required.")
        if email in duplicates:
            blockers.append("Duplicate email appears in this run; all duplicate rows are blocked.")
        role = str(intake.get("role") or "").strip()
        if not role:
            blockers.append("Role is required.")
        elif not approved_roles:
            blockers.append("The approved Axon Role catalog is empty; an administrator must review at least one role.")
        elif role.casefold() not in approved_roles:
            blockers.append(f'Role "{role}" is not in the approved Axon Role catalog.')
        if not source:
            blockers.append("No exact directory match was found for this email.")
            source = {}
        status_text, account_enabled = truthy_account_status(_directory_value(source, "directoryAccountStatus", "accountEnabled", "enabled"))
        if not account_enabled:
            blockers.append("Directory account is disabled; explicit review is required before finalization.")
        directory_location = _governed_directory_value(workspace, source, "Directory Location", "directoryLocation", "officeLocation", "location")
        component = _governed_directory_value(workspace, source, "Component", "component", "department", "companyName")
        location, personnel_aor = _map_location(workspace, directory_location, component)
        if directory_location and not personnel_aor:
            warnings.append("Personnel Location has no reviewed Location-to-AOR mapping. A review candidate is available in the crosswalk; user import is not blocked.")
        job_title = _governed_directory_value(workspace, source, "Job Title", "jobTitle", "title")
        category = _classify_title(workspace, job_title)
        if job_title and not category:
            warnings.append("Job Title has no reviewed job-category mapping. A review candidate is available in the crosswalk; user import is not blocked.")
        recommended_group, membership = _group_rule(workspace, component, personnel_aor, category)
        requested_group = str(intake.get("groupName") or "").strip()
        group_name = requested_group
        group, group_error = resolve_group(workspace, group_name, component, personnel_aor) if group_name else (None, "")
        if group_error:
            warnings.append(group_error + " No Group-assignment record will be generated; user import is not blocked.")
        elif not group_name:
            recommendation_note = f' The governed recommendation is "{recommended_group}".' if recommended_group else ""
            warnings.append("No Axon Group was selected." + recommendation_note + " No Group-assignment record will be generated; user import is not blocked.")
        existing = existing_users.get(email)
        upn = _governed_directory_value(workspace, source, "UPN", "upn", "userPrincipalName")
        external_id = _governed_directory_value(workspace, source, "External ID", "externalId", "userPrincipalName", "upn")
        badge_number = _governed_directory_value(workspace, source, "Badge Number", "badgeNumber", "mailNickname")
        first_name = _governed_directory_value(workspace, source, "First Name", "firstName", "givenName")
        last_name = _governed_directory_value(workspace, source, "Last Name", "lastName", "surname")
        username = _governed_directory_value(workspace, source, "Username", "username", "mailNickname")
        for label, value in (
            ("UPN", upn),
            ("External ID", external_id),
            ("Badge Number", badge_number),
            ("First Name", first_name),
            ("Last Name", last_name),
            ("UserName", username),
        ):
            if not value:
                blockers.append(f"{label} was not returned by the directory mapping.")
        row = {
            "rowId": f"ROW-{index:04d}-{uuid.uuid4().hex[:6]}",
            "intakeOrder": index,
            "email": email,
            "upn": upn,
            "role": role,
            "groupNameOverride": requested_group,
            "externalId": external_id,
            "badgeNumber": badge_number,
            "firstName": first_name,
            "lastName": last_name,
            "status": "Active",
            "username": username,
            "directoryAccountStatus": status_text,
            "supervisorEmail": _governed_directory_value(workspace, source, "Supervisor Email", "supervisorEmail", "managerEmail"),
            "supervisorUpn": _governed_directory_value(workspace, source, "Supervisor UPN", "supervisorUpn", "managerUpn"),
            "rank": _directory_value(source, "rank"),
            "directoryLocation": directory_location,
            "location": location,
            "personnelAor": personnel_aor,
            "component": component,
            "jobTitle": job_title,
            "jobCategory": category,
            "recommendedGroupName": recommended_group,
            "groupName": group["name"] if group else group_name,
            "groupExternalId": group["externalId"] if group else "",
            "membershipType": membership,
            "phone": _governed_directory_value(workspace, source, "Phone", "phone", "mobilePhone", "businessPhones"),
            "evidenceGroupExternalId": "",
            "existingAccount": bool(existing),
            "currentAxon": existing or {},
            "source": provider.name,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": warnings,
            "validationState": "Blocked" if blockers else "Ready",
        }
        row["differences"] = field_differences(row, existing or {})
        output.append(row)
    validation = validate_run(output)
    validation["crosswalkCandidatesAdded"] = candidates_added
    generation = generate_records(output)
    return output, validation, generation


def field_differences(row: dict[str, Any], existing: dict[str, Any]) -> list[dict[str, str]]:
    if not existing:
        return []
    fields = {
        "Role": ("role", ("ROLE", "Role", "role")),
        "Location": ("location", ("LOCATION", "Location", "location")),
        "Status": ("status", ("STATUS", "Status", "status")),
        "Supervisor Email": ("supervisorEmail", ("SUPERVISOR_EMAIL", "Supervisor Email", "supervisorEmail")),
    }
    differences = []
    for label, (proposed_key, current_keys) in fields.items():
        current = _lookup_value(existing, *current_keys)
        proposed = str(row.get(proposed_key) or "")
        if current.strip().casefold() != proposed.strip().casefold():
            differences.append({"field": label, "current": current, "proposed": proposed})
    return differences


def validate_run(rows: list[dict[str, Any]]) -> dict[str, Any]:
    blockers = [row for row in rows if row.get("blockers")]
    updates = [row for row in rows if row.get("existingAccount") and not row.get("blockers")]
    creates = [row for row in rows if not row.get("existingAccount") and not row.get("blockers")]
    unchanged = [row for row in updates if not row.get("differences")]
    return {
        "rowCount": len(rows),
        "blockerCount": len(blockers),
        "createCount": len(creates),
        "updateCount": len(updates) - len(unchanged),
        "existingCount": len(updates),
        "unchangedCount": len(unchanged),
        "warningCount": sum(len(row.get("warnings", [])) for row in rows),
        "valid": not blockers and bool(rows),
    }


def _user_record(row: dict[str, Any]) -> dict[str, str]:
    return {
        "EXTERNAL_ID": str(row.get("externalId") or ""),
        "EMAIL": str(row.get("email") or ""),
        "BADGE_NUMBER": str(row.get("badgeNumber") or ""),
        "FIRST_NAME": str(row.get("firstName") or ""),
        "LAST_NAME": str(row.get("lastName") or ""),
        "STATUS": "Active",
        "USERNAME": str(row.get("username") or row.get("email") or ""),
        "ROLE": str(row.get("role") or ""),
        "SUPERVISOR_EMAIL": str(row.get("supervisorEmail") or ""),
        "LOCATION": str(row.get("location") or ""),
        "EVIDENCE_GROUP_EXT_ID": "",
        "PHONE": str(row.get("phone") or ""),
        "RANK": str(row.get("rank") or ""),
    }


def _group_record(row: dict[str, Any]) -> dict[str, str]:
    return {
        "EXTERNAL_ID": str(row.get("groupExternalId") or ""),
        "MEMBERSHIP_TYPE": str(row.get("membershipType") or "MEMBER").upper(),
        "ENTITY_TYPE": "USER",
        "ENTITY_ID": str(row.get("email") or ""),
    }


def _chunks(records: list[dict[str, str]], row_ids: list[str], size: int = 500) -> list[dict[str, Any]]:
    result = []
    for start in range(0, len(records), size):
        selected = records[start : start + size]
        result.append({"records": selected, "rowIds": row_ids[start : start + size], "rowCount": len(selected), "sha256": value_hash(selected)})
    return result


def generate_records(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = sorted((row for row in rows if not row.get("blockers")), key=lambda row: row.get("intakeOrder", 0))
    user_records = [_user_record(row) for row in eligible]
    group_rows = [row for row in eligible if row.get("groupExternalId") and row.get("externalId")]
    group_records = [_group_record(row) for row in group_rows]
    ids = [row["rowId"] for row in eligible]
    group_ids = [row["rowId"] for row in group_rows]
    return {
        "userRecords": user_records,
        "groupRecords": group_records,
        "userHash": value_hash(user_records),
        "groupHash": value_hash(group_records),
        "userChunks": _chunks(user_records, ids),
        "groupChunks": _chunks(group_records, group_ids),
        "userEncoding": "UTF-8 without BOM",
        "groupEncoding": "UTF-8 without BOM",
        "userHeaders": USER_HEADERS,
        "groupHeaders": GROUP_HEADERS,
    }


def _recalculate_assignment(
    workspace: SharedWorkspace,
    row: dict[str, Any],
    changed_fields: set[str] | None = None,
) -> dict[str, Any]:
    updated = dict(row)
    changed_fields = changed_fields or set()
    stale_assignment_markers = (
        "role",
        "personnel location",
        "personnel aor",
        "location-to-aor",
        "job title",
        "job category",
        "job-category",
        "group",
    )
    blockers = [
        value
        for value in updated.get("blockers", [])
        if not any(marker in value.casefold() for marker in stale_assignment_markers)
    ]
    warnings = [
        value
        for value in updated.get("warnings", [])
        if not any(fragment in value for fragment in ("Location-to-AOR", "job-category", "Axon Group", "Group-assignment", "Group name"))
    ]
    approved_roles = _approved_roles(workspace)
    if not updated.get("role", "").strip():
        blockers.append("Role is required.")
    elif not approved_roles:
        blockers.append("The approved Axon Role catalog is empty; an administrator must review at least one role.")
    elif updated.get("role", "").casefold() not in approved_roles:
        blockers.append(f'Role "{updated.get("role", "")}" is not in the approved Axon Role catalog.')
    if updated.get("directoryLocation") and not updated.get("personnelAor"):
        warnings.append("Personnel Location has no reviewed Location-to-AOR mapping. User import is not blocked.")
    if updated.get("jobTitle") and not updated.get("jobCategory"):
        warnings.append("Job Title has no reviewed job-category mapping. User import is not blocked.")
    recommended, membership = _group_rule(workspace, updated.get("component", ""), updated.get("personnelAor", ""), updated.get("jobCategory", ""))
    updated["recommendedGroupName"] = recommended
    if "groupExternalId" in changed_fields:
        external_id = updated.get("groupExternalId", "")
        exact = [item for item in _group_candidates(workspace) if item["externalId"] == external_id] if external_id else []
        group, error = ((exact[0], "") if len(exact) == 1 else (None, "The selected Axon Group is no longer available in the current Group pool.")) if external_id else (None, "")
    elif "groupName" in changed_fields:
        group, error = resolve_group(workspace, updated.get("groupName", ""), updated.get("component", ""), updated.get("personnelAor", "")) if updated.get("groupName") else (None, "")
    elif updated.get("groupExternalId"):
        exact = [item for item in _group_candidates(workspace) if item["externalId"] == updated["groupExternalId"]]
        group, error = (exact[0], "") if len(exact) == 1 else (None, "The selected Axon Group is no longer available in the current Group pool.")
    else:
        group, error = resolve_group(workspace, updated.get("groupName", ""), updated.get("component", ""), updated.get("personnelAor", "")) if updated.get("groupName") else (None, "")
    if error:
        warnings.append(error + " No Group-assignment record will be generated; user import is not blocked.")
        updated["groupExternalId"] = ""
    elif group:
        updated["groupExternalId"] = group["externalId"]
        updated["groupName"] = group["name"]
    else:
        updated["groupExternalId"] = ""
        warnings.append("No Axon Group was selected. No Group-assignment record will be generated; user import is not blocked.")
    updated["membershipType"] = membership
    updated["blockers"] = list(dict.fromkeys(blockers))
    updated["warnings"] = list(dict.fromkeys(warnings))
    updated["validationState"] = "Blocked" if blockers else "Ready"
    updated["differences"] = field_differences(updated, updated.get("currentAxon") or {})
    return updated


def edit_rows(workspace: SharedWorkspace, rows: list[dict[str, Any]], edits: list[dict[str, Any]], reason: str) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    if not reason.strip():
        raise WorkflowError("A change reason is required.")
    by_id = {row["rowId"]: dict(row) for row in rows}
    for edit in edits:
        row_id = str(edit.get("rowId") or "")
        if row_id not in by_id:
            raise WorkflowError(f"Provisioning row {row_id} was not found.")
        changes = dict(edit.get("changes") or {})
        forbidden = set(changes) - ASSIGNMENT_EDIT_FIELDS
        if forbidden:
            raise WorkflowError("Identity fields are read-only in Preview: " + ", ".join(sorted(forbidden)))
        by_id[row_id].update({key: str(value or "").strip() for key, value in changes.items()})
        by_id[row_id]["lastChangeReason"] = reason.strip()
        by_id[row_id] = _recalculate_assignment(workspace, by_id[row_id], set(changes))
    updated = [by_id[row["rowId"]] for row in rows]
    return updated, validate_run(updated), generate_records(updated)


def write_csv(path: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\r\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: safe_csv_value(row.get(header, "")) for header in headers})


def export_run_package(run: dict[str, Any], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    package_name = f"BWC_{run['runId']}_R{run['revision']}_{timestamp}.zip"
    output = destination / package_name
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        enriched = io.StringIO(newline="")
        roster_headers = ["rowId", "email", "upn", "externalId", "badgeNumber", "firstName", "lastName", "status", "username", "role", "supervisorEmail", "supervisorUpn", "directoryAccountStatus", "directoryLocation", "location", "personnelAor", "component", "jobTitle", "jobCategory", "groupName", "groupExternalId", "membershipType", "validationState"]
        writer = csv.DictWriter(enriched, fieldnames=roster_headers, lineterminator="\r\n", extrasaction="ignore")
        writer.writeheader()
        for row in run["rows"]:
            writer.writerow({key: safe_csv_value(row.get(key, "")) for key in roster_headers})
        archive.writestr("enriched_roster.csv", enriched.getvalue().encode("utf-8"))
        archive.writestr("validation_summary.json", json.dumps(run["validation"], indent=2).encode("utf-8"))
        archive.writestr("review_provenance.json", json.dumps({"runId": run["runId"], "revision": run["revision"], "provider": run["provider"], "history": run.get("history", []), "snapshotIds": run["activeSnapshotIds"]}, indent=2).encode("utf-8"))
        manifest_files: list[dict[str, Any]] = []
        for kind, headers, chunks in (("users", USER_HEADERS, run["generation"]["userChunks"]), ("groups", GROUP_HEADERS, run["generation"]["groupChunks"])):
            for index, chunk in enumerate(chunks, start=1):
                stream = io.StringIO(newline="")
                chunk_writer = csv.DictWriter(stream, fieldnames=headers, lineterminator="\r\n", extrasaction="ignore")
                chunk_writer.writeheader()
                for row in chunk["records"]:
                    chunk_writer.writerow({key: safe_csv_value(row.get(key, "")) for key in headers})
                data = stream.getvalue().encode("utf-8")
                name = f"{kind}/{kind}_chunk_{index:03d}.csv"
                archive.writestr(name, data)
                manifest_files.append({"path": name, "sha256": value_hash(chunk["records"]), "rowCount": chunk["rowCount"], "encoding": "UTF-8 without BOM", "headers": headers})
        manifest = {"runId": run["runId"], "revision": run["revision"], "createdAt": timestamp, "approval": run.get("approval", {}), "activeSnapshotIds": run["activeSnapshotIds"], "files": manifest_files, "jobDependencies": "All applicable user chunks must complete before Group chunks are eligible."}
        archive.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))
    return output
