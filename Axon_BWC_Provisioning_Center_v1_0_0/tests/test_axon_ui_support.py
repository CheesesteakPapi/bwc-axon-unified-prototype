from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("axon_ui_support", ROOT / "axon_ui_support.py")
assert SPEC and SPEC.loader
ui_support = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ui_support
SPEC.loader.exec_module(ui_support)


class CsvBuilderTests(unittest.TestCase):
    def test_source_roster_creates_users_and_multiple_group_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source.csv"
            users = temp / "users.csv"
            groups = temp / "groups.csv"
            headers = ui_support.SOURCE_HEADERS + ["MembershipType"]
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()
                writer.writerow({
                    "ExternalId": "HR-1001",
                    "Email": "alex.taylor@example.gov",
                    "BadgeNumber": "1001",
                    "FirstName": "Alex",
                    "LastName": "Taylor",
                    "Status": "Active",
                    "Username": "alex.taylor@example.gov",
                    "Role": "Officer",
                    "SupervisorEmail": "",
                    "Location": "Example Location Alpha",
                    "Phone": "",
                    "Rank": "",
                    "GroupExternalId": "GROUP-TEST-001;GROUP-TEST-002",
                    "MembershipType": "member",
                })
            user_count, group_count = ui_support.build_api_csvs(source, users, groups)
            self.assertEqual(1, user_count)
            self.assertEqual(2, group_count)
            self.assertFalse(users.read_bytes().startswith(b"\xef\xbb\xbf"))
            with users.open("r", newline="", encoding="utf-8-sig") as handle:
                user_rows = list(csv.DictReader(handle))
            with groups.open("r", newline="", encoding="utf-8-sig") as handle:
                group_rows = list(csv.DictReader(handle))
            self.assertEqual("", user_rows[0]["EVIDENCE_GROUP_EXT_ID"])
            self.assertEqual(["MEMBER", "MEMBER"], [row["MEMBERSHIP_TYPE"] for row in group_rows])
            self.assertEqual(["USER", "USER"], [row["ENTITY_TYPE"] for row in group_rows])

    def test_invalid_membership_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source.csv"
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=ui_support.SOURCE_HEADERS + ["MembershipType"])
                writer.writeheader()
                writer.writerow({header: "" for header in ui_support.SOURCE_HEADERS} | {
                    "Email": "alex.taylor@example.gov",
                    "GroupExternalId": "GROUP-TEST-001",
                    "MembershipType": "OWNER",
                })
            with self.assertRaisesRegex(ValueError, "MEMBER or MONITOR"):
                ui_support.build_api_csvs(source, temp / "users.csv", temp / "groups.csv")


class CommandBuilderTests(unittest.TestCase):
    def test_submit_user_command_contains_all_write_gates(self) -> None:
        operation = ui_support.OPERATIONS_BY_KEY["submit_users"]
        values = {
            "config": "config.json",
            "user_csv": "users.csv",
            "existing_users": "axon_users.csv",
            "execute": "yes",
            "confirm_agency": "agency-123",
            "allow_updates": "yes",
        }
        command = ui_support.build_command(ROOT, operation, values)
        self.assertIn("--execute", command)
        self.assertIn("--confirm-agency", command)
        self.assertIn("agency-123", command)
        self.assertIn("--allow-updates", command)
        self.assertNotIn("AXON_CLIENT_SECRET", " ".join(command))

    def test_group_submit_requires_user_job_for_pending_users(self) -> None:
        operation = ui_support.OPERATIONS_BY_KEY["submit_groups"]
        values = {
            "config": "config.json",
            "group_csv": "groups.csv",
            "groups_snapshot": "axon_groups.csv",
            "users_snapshot": "",
            "pending_users": "users.csv",
            "user_job_id": "",
            "execute": "yes",
            "confirm_agency": "agency-123",
        }
        errors = ui_support.validate_inputs(operation, values)
        self.assertTrue(any("user-import job ID" in error for error in errors))

    def test_offline_validation_does_not_require_write_confirmation(self) -> None:
        operation = ui_support.OPERATIONS_BY_KEY["validate_users"]
        errors = ui_support.validate_inputs(operation, {"config": "config.json", "user_csv": "users.csv"})
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
