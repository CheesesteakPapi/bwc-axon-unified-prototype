from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared_workspace import SharedWorkspace, value_hash


FULL_SCOPE = {"type": "full", "filters": {}}


class SnapshotBatchActivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = SharedWorkspace(Path(self.temporary.name) / "shared.sqlite3")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _create_submitted_user_overlay(self, email: str, external_id: str) -> None:
        row = {
            "rowId": "row-1",
            "email": email,
            "externalId": external_id,
            "validationState": "Ready",
            "existingAccount": False,
            "groupExternalId": "",
        }
        user_records = [{"EMAIL": email, "EXTERNAL_ID": external_id}]
        generation = {
            "userHash": value_hash(user_records),
            "groupHash": value_hash([]),
            "userChunks": [
                {
                    "rowIds": ["row-1"],
                    "records": user_records,
                    "sha256": value_hash(user_records),
                }
            ],
            "groupChunks": [],
        }
        run = self.workspace.create_run(
            "Snapshot confirmation",
            "test",
            [row],
            {"blockerCount": 0},
            generation,
            "Ready for Preview",
        )
        approved = self.workspace.approve_preview(run["runId"], run["revision"], False, 0)
        user_chunk = next(chunk for chunk in approved["chunks"] if chunk["kind"] == "users")
        self.workspace.record_chunk_submission(
            approved["runId"],
            approved["revision"],
            user_chunk["chunkId"],
            "TEST-JOB",
            "test",
        )

    def test_batch_uses_one_revision_and_preserves_snapshot_side_effects(self) -> None:
        email = "batch.user@example.test"
        external_id = "batch.user@tenant.example.test"
        self._create_submitted_user_overlay(email, external_id)
        before_revision = self.workspace.revision()

        results = self.workspace.activate_snapshots_batch(
            [
                {
                    "resource": "Users",
                    "rows": [{"Email": email.upper(), "External ID": external_id.upper()}],
                    "scope": FULL_SCOPE,
                    "source": "Axon users test",
                },
                {
                    "resource": "Devices",
                    "rows": [
                        {
                            "id": "device-1",
                            "Assigned User ID": "user-1",
                            "Device Status": "Assigned",
                            "Device Model": "Body 4",
                            "Device Home Name (API)": "Test Home",
                        },
                        {
                            "id": "device-2",
                            "Assigned User ID": "",
                            "Device Status": "In Stock",
                            "Device Model": "Body 4",
                            "Device Home Name (API)": "Test Home",
                        },
                    ],
                    "scope": FULL_SCOPE,
                    "source": "Axon devices test",
                },
            ]
        )

        self.assertEqual([result["resource"] for result in results], ["Users", "Devices"])
        self.assertEqual({result["workspaceRevision"] for result in results}, {before_revision + 1})
        self.assertEqual(self.workspace.revision(), before_revision + 1)
        self.assertEqual(self.workspace.active_snapshot("Users")["source"], "Axon users test")
        self.assertEqual(self.workspace.active_snapshot("Devices")["source"], "Axon devices test")
        relationships = self.workspace.active_user_device_relationships()
        self.assertEqual([row["assignment_state"] for row in relationships], ["Assigned", "Unassigned"])
        overlay = next(
            item
            for item in self.workspace.pending_overlays()
            if item["entityType"] == "User" and item["payload"].get("email") == email
        )
        self.assertEqual(overlay["state"], "Confirmed")

        with self.workspace.connection() as db:
            audit_rows = db.execute(
                "SELECT details_json FROM audit_events WHERE event_type='snapshot-activated' ORDER BY sequence"
            ).fetchall()
        audit_details = [json.loads(row["details_json"]) for row in audit_rows]
        self.assertEqual([details["resource"] for details in audit_details], ["Users", "Devices"])
        self.assertEqual({details["revision"] for details in audit_details}, {before_revision + 1})
        self.assertEqual(audit_details[0]["confirmedUserOverlays"], 1)
        self.assertTrue(self.workspace.verify_audit_chain()["valid"])

    def test_batch_rolls_back_every_resource_overlay_revision_and_audit(self) -> None:
        email = "rollback.user@example.test"
        external_id = "rollback.user@tenant.example.test"
        self._create_submitted_user_overlay(email, external_id)
        baseline_results = self.workspace.activate_snapshots_batch(
            [
                {
                    "resource": "Users",
                    "rows": [{"Email": "other.user@example.test", "External ID": "other-user"}],
                    "scope": FULL_SCOPE,
                    "source": "baseline users",
                },
                {
                    "resource": "Devices",
                    "rows": [
                        {
                            "id": "device-old",
                            "Assigned User ID": "old-user",
                            "Device Status": "Assigned",
                            "Device Model": "Body 3",
                            "Device Home Name (API)": "Old Home",
                        }
                    ],
                    "scope": FULL_SCOPE,
                    "source": "baseline devices",
                },
            ]
        )
        baseline_ids = {result["resource"]: result["snapshotId"] for result in baseline_results}
        before_revision = self.workspace.revision()
        before_audit = self.workspace.verify_audit_chain()
        original_audit = self.workspace._audit_in_connection
        snapshot_audit_calls = 0

        def fail_second_snapshot_audit(db, actor, event_type, outcome, details=None):
            nonlocal snapshot_audit_calls
            if event_type == "snapshot-activated":
                snapshot_audit_calls += 1
                if snapshot_audit_calls == 2:
                    raise RuntimeError("forced batch audit failure")
            return original_audit(db, actor, event_type, outcome, details)

        with patch.object(self.workspace, "_audit_in_connection", side_effect=fail_second_snapshot_audit):
            with self.assertRaisesRegex(RuntimeError, "forced batch audit failure"):
                self.workspace.activate_snapshots_batch(
                    [
                        {
                            "resource": "Users",
                            "rows": [{"Email": email, "External ID": external_id}],
                            "scope": FULL_SCOPE,
                            "source": "replacement users",
                        },
                        {
                            "resource": "Devices",
                            "rows": [
                                {
                                    "id": "device-new",
                                    "Assigned User ID": "new-user",
                                    "Device Status": "Assigned",
                                    "Device Model": "Body 4",
                                    "Device Home Name (API)": "New Home",
                                }
                            ],
                            "scope": FULL_SCOPE,
                            "source": "replacement devices",
                        },
                    ]
                )

        self.assertEqual(self.workspace.revision(), before_revision)
        self.assertEqual(self.workspace.active_snapshot("Users")["snapshotId"], baseline_ids["Users"])
        self.assertEqual(self.workspace.active_snapshot("Devices")["snapshotId"], baseline_ids["Devices"])
        self.assertEqual(self.workspace.active_user_device_relationships()[0]["device_id"], "device-old")
        with self.workspace.connection() as db:
            stored_snapshot_ids = {
                row["snapshot_id"]
                for row in db.execute("SELECT snapshot_id FROM resource_snapshots").fetchall()
            }
        self.assertEqual(stored_snapshot_ids, set(baseline_ids.values()))
        overlay = next(
            item
            for item in self.workspace.pending_overlays()
            if item["entityType"] == "User" and item["payload"].get("email") == email
        )
        self.assertEqual(overlay["state"], "Submitted—awaiting confirmation")
        self.assertEqual(self.workspace.verify_audit_chain(), before_audit)

    def test_batch_validates_all_entries_before_writing(self) -> None:
        before_revision = self.workspace.revision()
        with self.assertRaisesRegex(ValueError, "share one non-empty normalized schema"):
            self.workspace.activate_snapshots_batch(
                [
                    {
                        "resource": "Users",
                        "rows": [{"Email": "valid.user@example.test"}],
                        "scope": FULL_SCOPE,
                        "source": "valid test entry",
                    },
                    {
                        "resource": "Groups",
                        "rows": [{"id": "one"}, {"id": "two", "name": "Different schema"}],
                        "scope": FULL_SCOPE,
                        "source": "invalid test entry",
                    },
                ]
            )
        self.assertEqual(self.workspace.revision(), before_revision)
        self.assertIsNone(self.workspace.active_snapshot("Users"))
        self.assertIsNone(self.workspace.active_snapshot("Groups"))
        self.assertTrue(self.workspace.verify_audit_chain()["valid"])

    def test_operational_view_cannot_mix_snapshots_across_batch_activation(self) -> None:
        original_results = self.workspace.activate_snapshots_batch(
            [
                {"resource": "Users", "rows": [{"Email": "old@example.test"}], "scope": FULL_SCOPE},
                {"resource": "Devices", "rows": [{"id": "old-device"}], "scope": FULL_SCOPE},
            ]
        )
        original_ids = {item["resource"]: item["snapshotId"] for item in original_results}
        original_revision = self.workspace.revision()
        revision_read = threading.Event()
        continue_read = threading.Event()
        original_revision_reader = self.workspace._workspace_revision
        view_holder: dict[str, object] = {}

        def pause_reader_after_revision(db):
            revision = original_revision_reader(db)
            if threading.current_thread().name == "operational-view-reader":
                revision_read.set()
                self.assertTrue(continue_read.wait(5), "writer did not complete during read transaction")
            return revision

        def read_view() -> None:
            view_holder["view"] = self.workspace.read_operational_view()

        with patch.object(self.workspace, "_workspace_revision", side_effect=pause_reader_after_revision):
            reader = threading.Thread(target=read_view, name="operational-view-reader")
            reader.start()
            self.assertTrue(revision_read.wait(5), "reader did not establish its SQLite snapshot")
            replacement_results = self.workspace.activate_snapshots_batch(
                [
                    {"resource": "Users", "rows": [{"Email": "new@example.test"}], "scope": FULL_SCOPE},
                    {"resource": "Devices", "rows": [{"id": "new-device"}], "scope": FULL_SCOPE},
                ]
            )
            continue_read.set()
            reader.join(5)
            self.assertFalse(reader.is_alive(), "operational view reader did not finish")

        view = view_holder["view"]
        visible_ids = {item["resource"]: item["snapshotId"] for item in view["snapshots"]}
        replacement_ids = {item["resource"]: item["snapshotId"] for item in replacement_results}
        self.assertEqual(view["workspaceRevision"], original_revision)
        self.assertEqual(visible_ids, original_ids)
        self.assertNotEqual(visible_ids, replacement_ids)
        self.assertEqual(
            {item["resource"]: item["snapshotId"] for item in view["snapshotMetadata"]},
            original_ids,
        )

    def test_operational_view_loads_only_the_device_scope_used_by_dashboard(self) -> None:
        first = self.workspace.activate_snapshot(
            "Devices",
            [{"id": "body-device"}],
            {"type": "filtered", "filters": {"model": "Body 4"}},
        )
        second = self.workspace.activate_snapshot(
            "Devices",
            [{"id": "fleet-device"}],
            {"type": "filtered", "filters": {"model": "Fleet 3"}},
        )

        filtered_view = self.workspace.read_operational_view()

        self.assertEqual(len(filtered_view["snapshotMetadata"]), 2)
        self.assertEqual(len(filtered_view["snapshots"]), 1)
        self.assertEqual(filtered_view["snapshots"][0]["snapshotId"], second["snapshotId"])
        self.assertNotEqual(filtered_view["snapshots"][0]["snapshotId"], first["snapshotId"])

        full = self.workspace.activate_snapshot(
            "Devices",
            [{"id": "full-device"}],
            FULL_SCOPE,
        )
        full_view = self.workspace.read_operational_view()

        self.assertEqual(len(full_view["snapshotMetadata"]), 3)
        self.assertEqual(len(full_view["snapshots"]), 1)
        self.assertEqual(full_view["snapshots"][0]["snapshotId"], full["snapshotId"])


if __name__ == "__main__":
    unittest.main()
