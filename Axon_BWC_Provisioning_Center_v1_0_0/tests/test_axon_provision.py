from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("axon_provision", ROOT / "axon_provision.py")
assert SPEC and SPEC.loader
axon_provision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(axon_provision)


def write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def user_row(**overrides: str) -> dict[str, str]:
    row = {
        "EXTERNAL_ID": "HR-1001",
        "EMAIL": "alex.taylor@example.gov",
        "BADGE_NUMBER": "1001",
        "FIRST_NAME": "Alex",
        "LAST_NAME": "Taylor",
        "STATUS": "Active",
        "USERNAME": "alex.taylor@example.gov",
        "ROLE": "Officer",
        "SUPERVISOR_EMAIL": "",
        "LOCATION": "Example Location Alpha",
        "EVIDENCE_GROUP_EXT_ID": "",
        "PHONE": "",
        "RANK": "",
    }
    row.update(overrides)
    return row


class UserCsvTests(unittest.TestCase):
    def test_valid_user_csv_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "users.csv"
            write_csv(path, axon_provision.USER_HEADERS + axon_provision.OPTIONAL_USER_HEADERS, [user_row()])
            result = axon_provision.validate_user_csv(path)
            self.assertEqual([], result["errors"])
            self.assertEqual(1, len(result["rows"]))

    def test_user_csv_with_utf8_bom_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "users.csv"
            write_csv(path, axon_provision.USER_HEADERS + axon_provision.OPTIONAL_USER_HEADERS, [user_row()])
            path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
            result = axon_provision.validate_user_csv(path)
            self.assertTrue(any("without a byte-order mark" in error for error in result["errors"]))

    def test_empty_user_csv_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "users.csv"
            write_csv(path, axon_provision.USER_HEADERS, [])
            result = axon_provision.validate_user_csv(path)
            self.assertTrue(any("no data rows" in error for error in result["errors"]))

    def test_duplicate_email_is_rejected_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "users.csv"
            rows = [
                user_row(),
                user_row(
                    EXTERNAL_ID="HR-1002",
                    EMAIL="ALEX.TAYLOR@EXAMPLE.GOV",
                    BADGE_NUMBER="1002",
                    USERNAME="alex.taylor2@example.gov",
                ),
            ]
            write_csv(path, axon_provision.USER_HEADERS + axon_provision.OPTIONAL_USER_HEADERS, rows)
            result = axon_provision.validate_user_csv(path)
            self.assertTrue(any("Duplicate EMAIL" in error for error in result["errors"]))

    def test_classifies_create_and_existing_update_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            existing = temp / "axon_users.csv"
            write_csv(
                existing,
                ["Axon User ID", "External ID", "Badge ID", "Email"],
                [{
                    "Axon User ID": "axon-user-1",
                    "External ID": "HR-1001",
                    "Badge ID": "1001",
                    "Email": "alex.taylor@example.gov",
                }],
            )
            rows = [user_row(), user_row(
                EXTERNAL_ID="HR-1002",
                EMAIL="sam.lee@example.gov",
                BADGE_NUMBER="1002",
                USERNAME="sam.lee@example.gov",
            )]
            classification = axon_provision.classify_users(rows, existing)
            self.assertEqual([3], classification["create_rows"])
            self.assertEqual([2], classification["update_rows"])
            self.assertEqual([], classification["conflicts"])


class GroupEntityCsvTests(unittest.TestCase):
    def test_group_file_field_confirmation_defaults_to_false(self) -> None:
        config = axon_provision.provisioning({})
        self.assertFalse(config["group_entities_file_field_confirmed"])

    def make_snapshots(self, temp: Path) -> tuple[Path, Path]:
        groups = temp / "axon_groups.csv"
        users = temp / "axon_users.csv"
        write_csv(
            groups,
            ["External Group ID", "Group Name"],
            [
                {"External Group ID": "GROUP-TEST-001", "Group Name": "TEST Group Alpha"},
                {"External Group ID": "GROUP-TEST-002", "Group Name": "TEST Group Beta"},
            ],
        )
        write_csv(
            users,
            ["Email", "Axon User ID"],
            [{"Email": "alex.taylor@example.gov", "Axon User ID": "axon-user-1"}],
        )
        return groups, users

    def test_member_and_user_values_are_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            groups, users = self.make_snapshots(temp)
            entities = temp / "group_entities.csv"
            write_csv(
                entities,
                axon_provision.GROUP_ENTITY_HEADERS,
                [{
                    "EXTERNAL_ID": "GROUP-TEST-001",
                    "MEMBERSHIP_TYPE": "member",
                    "ENTITY_TYPE": "user",
                    "ENTITY_ID": "alex.taylor@example.gov",
                }],
            )
            result = axon_provision.validate_group_entities_csv(entities, groups, users)
            self.assertEqual([], result["errors"])

    def test_group_as_entity_uses_external_group_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            groups, users = self.make_snapshots(temp)
            entities = temp / "group_entities.csv"
            write_csv(
                entities,
                axon_provision.GROUP_ENTITY_HEADERS,
                [{
                    "EXTERNAL_ID": "GROUP-TEST-002",
                    "MEMBERSHIP_TYPE": "MONITOR",
                    "ENTITY_TYPE": "GROUP",
                    "ENTITY_ID": "GROUP-TEST-001",
                }],
            )
            result = axon_provision.validate_group_entities_csv(entities, groups, users)
            self.assertEqual([], result["errors"])

    def test_unknown_target_group_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            groups, users = self.make_snapshots(temp)
            entities = temp / "group_entities.csv"
            write_csv(
                entities,
                axon_provision.GROUP_ENTITY_HEADERS,
                [{
                    "EXTERNAL_ID": "NOT-A-REAL-GROUP",
                    "MEMBERSHIP_TYPE": "MEMBER",
                    "ENTITY_TYPE": "USER",
                    "ENTITY_ID": "alex.taylor@example.gov",
                }],
            )
            result = axon_provision.validate_group_entities_csv(entities, groups, users)
            self.assertTrue(any("target group external ID" in error for error in result["errors"]))

    def test_target_external_id_over_255_characters_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            groups, users = self.make_snapshots(temp)
            entities = temp / "group_entities.csv"
            write_csv(
                entities,
                axon_provision.GROUP_ENTITY_HEADERS,
                [{
                    "EXTERNAL_ID": "X" * 256,
                    "MEMBERSHIP_TYPE": "MEMBER",
                    "ENTITY_TYPE": "USER",
                    "ENTITY_ID": "alex.taylor@example.gov",
                }],
            )
            result = axon_provision.validate_group_entities_csv(entities, groups, users)
            self.assertTrue(any("exceeds 255 characters" in error for error in result["errors"]))

    def test_duplicate_assignment_is_rejected_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            groups, users = self.make_snapshots(temp)
            entities = temp / "group_entities.csv"
            rows = [
                {
                    "EXTERNAL_ID": "GROUP-TEST-001",
                    "MEMBERSHIP_TYPE": "MEMBER",
                    "ENTITY_TYPE": "USER",
                    "ENTITY_ID": "alex.taylor@example.gov",
                },
                {
                    "EXTERNAL_ID": "group-test-001",
                    "MEMBERSHIP_TYPE": "member",
                    "ENTITY_TYPE": "user",
                    "ENTITY_ID": "ALEX.TAYLOR@EXAMPLE.GOV",
                },
            ]
            write_csv(entities, axon_provision.GROUP_ENTITY_HEADERS, rows)
            result = axon_provision.validate_group_entities_csv(entities, groups, users)
            self.assertTrue(any("duplicate group-entity assignment" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
