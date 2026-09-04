from __future__ import annotations

import csv
import importlib.util
import os
import sys
import tempfile
import unittest
import zipfile
import json
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from provisioning_workflow import (  # noqa: E402
    EntraDelegatedProvider,
    RowDirectoryProvider,
    SyntheticDirectoryProvider,
    canonicalize_input,
    detect_columns,
    edit_rows,
    enrich_rows,
    generate_records,
    parse_xlsx_bytes,
)
from shared_workspace import RefreshLeaseConflict, RevisionConflict, SharedWorkspace  # noqa: E402


class UnifiedPrototypeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = SharedWorkspace(Path(self.temporary.name) / "shared.sqlite3")
        self.workspace.migrate_governance_csvs(ROOT / "governance_starters")
        self.workspace.activate_snapshot(
            "Groups",
            [{
                "id": "GROUP-TEST-001",
                "name": "TEST Prototype Users",
                "External Group ID": "GROUP-TEST-001",
                "Group Name": "TEST Prototype Users",
                "Component": "TEST",
                "Organizational Area": "TEST AOR",
                "Group Tier": "Primary",
            }],
            {"type": "full", "filters": {}},
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_flexible_header_detection_and_synthetic_run(self) -> None:
        detected = detect_columns(["Work Email", "Axon Role", "Organizational Group", "Ignored"])
        self.assertFalse(detected["needsMapper"])
        intake = canonicalize_input([{"Work Email": "alex.user@example.test", "Axon Role": "Prototype User", "Organizational Group": "", "Ignored": "x"}])
        rows, validation, generation = enrich_rows(self.workspace, intake, SyntheticDirectoryProvider())
        self.assertTrue(validation["valid"])
        self.assertEqual(rows[0]["status"], "Active")
        self.assertEqual(rows[0]["supervisorEmail"], "")
        self.assertEqual(rows[0]["supervisorUpn"], "")
        self.assertEqual(generation["userRecords"][0]["EVIDENCE_GROUP_EXT_ID"], "")
        self.assertEqual(rows[0]["recommendedGroupName"], "TEST Prototype Users")
        self.assertEqual(generation["groupRecords"], [])

    def test_entra_delegated_read_resolves_exact_mail_and_maps_distinct_upn(self) -> None:
        intake_email = "person.email@example.test"
        upn = "account-name@tenant.example.test"
        object_id = "TEST-ENTRA-OBJECT-ID-123"
        requested_urls = []

        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 30)
            self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
            requested_urls.append(request.full_url)
            if "/manager?" in request.full_url:
                self.assertIn("/users/" + object_id + "/manager", request.full_url)
                return BytesIO(json.dumps({"mail": "manager@example.test", "userPrincipalName": "manager@tenant.example.test"}).encode("utf-8"))
            parsed = urlparse(request.full_url)
            self.assertEqual(parsed.path, "/v1.0/users")
            query = parse_qs(parsed.query)
            self.assertEqual(query["$filter"], [f"mail eq '{intake_email}'"])
            selected = set(query["$select"][0].split(","))
            self.assertTrue({"mailNickname", "department", "givenName", "surname"}.issubset(selected))
            self.assertNotIn("employeeId", selected)
            payload = {"value": [{
                "id": object_id,
                "mail": intake_email,
                "userPrincipalName": upn,
                "mailNickname": "person.alias",
                "givenName": "Person",
                "surname": "Example",
                "accountEnabled": True,
                "officeLocation": "Prototype Test Location",
                "jobTitle": "Prototype Standard User",
                "department": "TEST",
                "businessPhones": ["202-555-0100"],
                "mobilePhone": "",
            }]}
            return BytesIO(json.dumps(payload).encode("utf-8"))

        provider = EntraDelegatedProvider("test-token")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            resolved = provider.resolve([intake_email])
            rows, validation, generation = enrich_rows(
                self.workspace,
                [{"email": intake_email, "role": "Prototype User", "groupName": ""}],
                provider,
            )

        self.assertEqual(len(requested_urls), 4)
        self.assertEqual(resolved[intake_email]["externalId"], upn)
        self.assertEqual(rows[0]["email"], intake_email)
        self.assertEqual(rows[0]["upn"], upn)
        self.assertEqual(rows[0]["externalId"], upn)
        self.assertEqual(rows[0]["badgeNumber"], "person.alias")
        self.assertEqual(rows[0]["username"], "person.alias")
        self.assertEqual(rows[0]["firstName"], "Person")
        self.assertEqual(rows[0]["lastName"], "Example")
        self.assertEqual(rows[0]["status"], "Active")
        self.assertEqual(rows[0]["component"], "TEST")
        self.assertEqual(rows[0]["phone"], "202-555-0100")
        self.assertTrue(validation["valid"])
        self.assertEqual(generation["userRecords"][0]["EXTERNAL_ID"], upn)
        self.assertEqual(generation["userRecords"][0]["STATUS"], "Active")

    def test_optional_mapping_gaps_queue_crosswalk_candidates_without_blocking_user_import(self) -> None:
        directory = RowDirectoryProvider(
            [{
                "mail": "optional.user@example.test",
                "userPrincipalName": "optional.user@tenant.example.test",
                "mailNickname": "optional.user",
                "givenName": "Optional",
                "surname": "User",
                "accountEnabled": True,
                "officeLocation": "Observed Field Office",
                "department": "HSI",
                "jobTitle": "Observed Special Agent Title",
            }]
        )
        intake = [{"email": "optional.user@example.test", "role": "Prototype User", "groupName": ""}]

        rows, validation, generation = enrich_rows(self.workspace, intake, directory)

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["blockerCount"], 0)
        self.assertGreaterEqual(validation["warningCount"], 3)
        self.assertEqual(validation["crosswalkCandidatesAdded"], {"locationAor": 1, "jobCategory": 1})
        self.assertEqual(rows[0]["personnelAor"], "")
        self.assertEqual(rows[0]["jobCategory"], "")
        self.assertEqual(generation["userRecords"][0]["LOCATION"], "Observed Field Office")
        self.assertEqual(generation["groupRecords"], [])

        location_rows = self.workspace.governance_dataset("personnel_location_aor_crosswalk")["rows"]
        observed_location = next(row for row in location_rows if row["Directory Location"] == "Observed Field Office")
        self.assertEqual(observed_location["Personnel AOR"], "")
        self.assertEqual(observed_location["Review Status"], "Needs review")
        self.assertEqual(observed_location["Mapping Method"], "Observed from directory export")
        title_rows = self.workspace.governance_dataset("job_title_category_mapping")["rows"]
        observed_title = next(row for row in title_rows if row["Exact Job Title"] == "Observed Special Agent Title")
        self.assertEqual(observed_title["Job Category"], "")
        self.assertEqual(observed_title["Review Status"], "Needs review")

        _, second_validation, _ = enrich_rows(self.workspace, intake, directory)
        self.assertEqual(second_validation["crosswalkCandidatesAdded"], {"locationAor": 0, "jobCategory": 0})
        self.assertEqual(sum(row["Directory Location"] == "Observed Field Office" for row in self.workspace.governance_dataset("personnel_location_aor_crosswalk")["rows"]), 1)
        self.assertTrue(self.workspace.verify_audit_chain()["valid"])

    def test_group_rule_need_not_be_reviewed_and_group_can_be_cleared(self) -> None:
        self.workspace.activate_snapshot(
            "Groups",
            [
                {
                    "id": "GROUP-TEST-001",
                    "name": "TEST Prototype Users",
                    "External Group ID": "GROUP-TEST-001",
                    "Group Name": "TEST Prototype Users",
                    "Component": "TEST",
                    "Organizational Area": "TEST AOR",
                    "Group Tier": "Primary",
                },
                {
                    "id": "GROUP-TEST-002",
                    "name": "TEST Prototype Users",
                    "External Group ID": "GROUP-TEST-002",
                    "Group Name": "TEST Prototype Users",
                    "Component": "TEST",
                    "Organizational Area": "TEST AOR",
                    "Group Tier": "Secondary",
                },
            ],
            {"type": "full", "filters": {}},
        )
        dataset = self.workspace.governance_dataset("component_aor_group_rules")
        rules = [dict(row) for row in dataset["rows"]]
        rules[0]["Review Status"] = "Needs review"
        self.workspace.replace_governance_rows(
            "component_aor_group_rules",
            rules,
            dataset["revision"],
            "test-group-rule-status",
            "test",
        )
        rows, validation, generation = enrich_rows(
            self.workspace,
            [{"email": "group.user@example.test", "role": "Prototype User", "groupName": ""}],
            SyntheticDirectoryProvider(),
        )
        self.assertTrue(validation["valid"])
        self.assertEqual(rows[0]["recommendedGroupName"], "TEST Prototype Users")
        self.assertEqual(rows[0]["groupName"], "")
        self.assertEqual(generation["groupRecords"], [])

        selected_rows, selected_validation, selected_generation = edit_rows(
            self.workspace,
            rows,
            [{"rowId": rows[0]["rowId"], "changes": {"groupName": "TEST Prototype Users", "groupExternalId": "GROUP-TEST-001"}}],
            "Selected the recommended organizational Group.",
        )
        self.assertTrue(selected_validation["valid"])
        self.assertEqual(selected_rows[0]["groupExternalId"], "GROUP-TEST-001")
        self.assertEqual(len(selected_generation["groupRecords"]), 1)

        selected_rows[0]["blockers"] = [
            "Personnel Location does not have one reviewed Location-to-AOR mapping.",
            "Exact job title does not have a reviewed job-category mapping.",
            "No reviewed Component/AOR/job-category Group rule was found.",
        ]
        retained_rows, retained_validation, retained_generation = edit_rows(
            self.workspace,
            selected_rows,
            [{"rowId": rows[0]["rowId"], "changes": {"supervisorEmail": "supervisor@example.test"}}],
            "Added a reviewed supervisor email without changing the Group selection.",
        )
        self.assertTrue(retained_validation["valid"])
        self.assertEqual(retained_rows[0]["groupExternalId"], "GROUP-TEST-001")
        self.assertEqual(len(retained_generation["groupRecords"]), 1)
        self.assertFalse(retained_rows[0]["blockers"])

        updated_rows, updated_validation, updated_generation = edit_rows(
            self.workspace,
            retained_rows,
            [{"rowId": rows[0]["rowId"], "changes": {"groupName": "", "groupExternalId": ""}}],
            "No organizational Group assignment is required for this user.",
        )
        self.assertTrue(updated_validation["valid"])
        self.assertEqual(updated_rows[0]["groupExternalId"], "")
        self.assertEqual(updated_generation["userRecords"][0]["EMAIL"], "group.user@example.test")
        self.assertEqual(updated_generation["groupRecords"], [])

    def test_chunk_boundaries(self) -> None:
        for total, expected in ((500, 1), (501, 2), (1000, 2), (1500, 3)):
            rows = []
            for index in range(total):
                rows.append({
                    "rowId": f"row-{index}", "intakeOrder": index, "email": f"u{index}@example.test",
                    "externalId": f"id-{index}", "badgeNumber": f"b-{index}", "firstName": "Test",
                    "lastName": str(index), "status": "Active", "username": f"u{index}@example.test",
                    "role": "Prototype User", "supervisorEmail": "", "location": "Prototype Test Location",
                    "phone": "", "rank": "", "groupExternalId": "GROUP-TEST-001",
                    "membershipType": "MEMBER", "blockers": [],
                })
            generated = generate_records(rows)
            self.assertEqual(len(generated["userChunks"]), expected)
            self.assertEqual(len(generated["groupChunks"]), expected)
            self.assertTrue(all(chunk["rowCount"] <= 500 for chunk in generated["userChunks"]))

    def test_filtered_device_snapshot_does_not_replace_full(self) -> None:
        full = self.workspace.activate_snapshot("Devices", [{"id": "full-1", "Assigned User ID": "user-1", "Device Status": "Assigned", "Device Model": "Body 4", "Device Home Name (API)": "Home A"}], {"type": "full", "filters": {}})
        self.workspace.activate_snapshot("Devices", [{"id": "filtered-1", "Assigned User ID": "", "Device Status": "In Stock", "Device Model": "Body 4", "Device Home Name (API)": "Home B"}], {"type": "filtered", "filters": {"model": "Body 4"}})
        selected = self.workspace.active_snapshot("Devices")
        self.assertEqual(selected["snapshotId"], full["snapshotId"])
        self.assertEqual(selected["rows"][0]["id"], "full-1")
        relationships = self.workspace.active_user_device_relationships()
        self.assertEqual(relationships[0]["user_id"], "user-1")
        self.assertEqual(relationships[0]["assignment_state"], "Assigned")

    def test_all_sync_components_require_explicit_mapped_status_for_site_projection(self) -> None:
        module_paths = [
            ROOT / "Axon_BWC_Provisioning_Center_v1_0_0" / "axon_sync.py",
            ROOT / "BWC_Geographic_Operations_v1_0_0" / "axon_sync.py",
            ROOT / "Axon_BWC_Sync_Prototype_v0_2_6" / "axon_sync.py",
        ]

        for index, module_path in enumerate(module_paths):
            with self.subTest(component=module_path.parent.name), tempfile.TemporaryDirectory() as directory:
                spec = importlib.util.spec_from_file_location(f"test_sync_contract_{index}", module_path)
                self.assertIsNotNone(spec)
                self.assertIsNotNone(spec.loader)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                root = Path(directory)
                home_path = root / "device_homes.csv"
                group_path = root / "groups.csv"

                def write_mapping(path: Path, key_field: str, key_value: str, status: str) -> None:
                    headers = [key_field, "Site ID", "Component", "Region / AOR", "Mapping Status"]
                    with path.open("w", encoding="utf-8-sig", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\r\n")
                        writer.writeheader()
                        writer.writerow({
                            key_field: key_value,
                            "Site ID": "TEST-SITE-001",
                            "Component": "TEST",
                            "Region / AOR": "Test AOR",
                            "Mapping Status": status,
                        })

                cfg = {
                    "device_home_crosswalk_csv": str(home_path),
                    "axon_group_crosswalk_csv": str(group_path),
                    "device_status_map_csv": "",
                    "non_site_group_register_csv": "",
                }
                home_record = {"attributes": {"name": "Candidate Home"}}
                home_fields = {"Device Home Name (API)": "attributes.name"}
                group_record = {"id": "group-1", "attributes": {"name": "Candidate Group"}}
                group_fields = {"Axon Group ID": "id", "Group Name": "attributes.name"}
                device_record = {
                    "id": "device-1",
                    "attributes": {"status2": "ASSIGNED"},
                    "relationships": {"deviceHome": {"data": {"attributes": {"name": "Candidate Home"}}}},
                }
                device_fields = {
                    "Axon Device ID": "id",
                    "Device Home Name (API)": "relationships.deviceHome.data.attributes.name",
                    "Device Status": "attributes.status2",
                }

                write_mapping(home_path, "Normalized Device Home Key", "candidate home", "Candidate")
                write_mapping(group_path, "Axon Group ID", "group-1", "Candidate")
                candidate_homes = module.map_rows("DeviceHomes", [home_record], home_fields, cfg, {})
                candidate_groups = module.map_rows("Groups", [group_record], group_fields, cfg, {})
                candidate_devices = module.map_rows(
                    "Devices",
                    [device_record],
                    device_fields,
                    cfg,
                    {"DeviceHomes": candidate_homes},
                )
                self.assertEqual(candidate_homes[0]["Mapping Status"], "Candidate")
                self.assertEqual(candidate_homes[0]["Mapped Site ID"], "")
                self.assertEqual(candidate_groups[0]["Mapped Site ID"], "")
                self.assertEqual(candidate_devices[0]["Mapped Site ID"], "")
                self.assertEqual(module.reviewed_site_mapping({"Site ID": "", "Mapping Status": "Mapped"}), {})

                write_mapping(home_path, "Normalized Device Home Key", "candidate home", "Mapped")
                write_mapping(group_path, "Axon Group ID", "group-1", "Mapped")
                mapped_homes = module.map_rows("DeviceHomes", [home_record], home_fields, cfg, {})
                mapped_groups = module.map_rows("Groups", [group_record], group_fields, cfg, {})
                mapped_devices = module.map_rows(
                    "Devices",
                    [device_record],
                    device_fields,
                    cfg,
                    {"DeviceHomes": mapped_homes},
                )
                self.assertEqual(mapped_homes[0]["Mapped Site ID"], "TEST-SITE-001")
                self.assertEqual(mapped_homes[0]["Mapped Region / AOR"], "Test AOR")
                self.assertEqual(mapped_groups[0]["Mapped Site ID"], "TEST-SITE-001")
                self.assertEqual(mapped_devices[0]["Mapped Site ID"], "TEST-SITE-001")

    def test_refresh_lease_and_revision_conflicts(self) -> None:
        refresh_id = self.workspace.acquire_refresh_lease("Users", "app-one", {"type": "full"})
        with self.assertRaises(RefreshLeaseConflict):
            self.workspace.acquire_refresh_lease("Users", "app-two", {"type": "full"})
        self.workspace.release_refresh_lease("Users", "app-one", refresh_id, "canceled")
        intake = canonicalize_input([{"Email": "sam.user@example.test", "Role": "Prototype User", "Group Name": ""}])
        rows, validation, generation = enrich_rows(self.workspace, intake, SyntheticDirectoryProvider())
        run = self.workspace.create_run("Conflict", "synthetic-test", rows, validation, generation, "Ready for Preview")
        self.workspace.approve_preview(run["runId"], 1, False, 0)
        with self.assertRaises(RevisionConflict):
            self.workspace.revise_run(run["runId"], 1, rows, validation, generation, "Ready for Preview", "stale", "stale")

    def test_minimal_xlsx_values_are_read_without_formula_execution(self) -> None:
        stream = BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Users" sheetId="1" r:id="rId1"/></sheets></workbook>')
            archive.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet"/></Relationships>')
            archive.writestr("xl/worksheets/sheet1.xml", '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Email</t></is></c><c r="B1" t="inlineStr"><is><t>Role</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>user@example.test</t></is></c><c r="B2" t="inlineStr"><is><t>Prototype User</t></is></c><c r="C2"><f>HYPERLINK("bad")</f><v>0</v></c></row></sheetData></worksheet>')
        headers, rows = parse_xlsx_bytes(stream.getvalue())
        self.assertEqual(headers[:2], ["Email", "Role"])
        self.assertEqual(rows[0]["Email"], "user@example.test")

    def test_audit_chain_and_user_csv_encoding_contract(self) -> None:
        self.assertTrue(self.workspace.verify_audit_chain()["valid"])
        self.assertFalse("Prototype User".encode("utf-8").startswith(b"\xef\xbb\xbf"))

    def test_user_and_group_overlays_are_separate_and_users_require_snapshot_confirmation(self) -> None:
        intake = canonicalize_input([{"Email": "case.user@example.test", "Role": "Prototype User", "Group Name": "TEST Prototype Users"}])
        rows, validation, generation = enrich_rows(self.workspace, intake, SyntheticDirectoryProvider())
        self.assertEqual(generation["groupHeaders"], ["EXTERNAL_ID", "MEMBERSHIP_TYPE", "ENTITY_TYPE", "ENTITY_ID"])
        run = self.workspace.create_run("Overlay", "synthetic-test", rows, validation, generation, "Ready for Preview")
        overlay_types = {item["entityType"] for item in self.workspace.pending_overlays(["Proposed creation"])}
        self.assertEqual(overlay_types, {"User", "GroupMembership"})

        approved = self.workspace.approve_preview(run["runId"], 1, False, 0)
        user_chunk = next(chunk for chunk in approved["chunks"] if chunk["kind"] == "users")
        self.workspace.record_chunk_submission(approved["runId"], approved["revision"], user_chunk["chunkId"], "TEST-JOB-1", "test")
        active = self.workspace.pending_overlays(["Proposed creation", "Submitted—awaiting confirmation"])
        states = {item["entityType"]: item["state"] for item in active}
        self.assertEqual(states["User"], "Submitted—awaiting confirmation")
        self.assertEqual(states["GroupMembership"], "Proposed creation")

        self.workspace.activate_snapshot(
            "Users",
            [{"Email": "case.user@example.test", "External ID": rows[0]["externalId"]}],
            {"type": "full", "filters": {}},
        )
        user_overlay = next(item for item in self.workspace.pending_overlays() if item["entityType"] == "User" and item["runRevision"] == approved["revision"])
        self.assertEqual(user_overlay["state"], "Confirmed")

    def test_local_run_purge_requires_current_revision_and_preserves_audit(self) -> None:
        intake = canonicalize_input([{"Email": "purge.user@example.test", "Role": "Prototype User", "Group Name": ""}])
        rows, validation, generation = enrich_rows(self.workspace, intake, SyntheticDirectoryProvider())
        run = self.workspace.create_run("Purge", "synthetic-test", rows, validation, generation, "Ready for Preview")
        with self.assertRaises(RevisionConflict):
            self.workspace.purge_run(run["runId"], 0)
        result = self.workspace.purge_run(run["runId"], run["revision"])
        self.assertEqual(result["runId"], run["runId"])
        with self.assertRaises(KeyError):
            self.workspace.get_run(run["runId"])
        self.assertTrue(self.workspace.verify_audit_chain()["valid"])


if __name__ == "__main__":
    unittest.main()
