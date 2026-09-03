from __future__ import annotations

import os
import sys
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from provisioning_workflow import (  # noqa: E402
    SyntheticDirectoryProvider,
    canonicalize_input,
    detect_columns,
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
        self.assertEqual(generation["groupRecords"][0]["ENTITY_ID"], "alex.user@example.test")

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
        intake = canonicalize_input([{"Email": "case.user@example.test", "Role": "Prototype User", "Group Name": ""}])
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
