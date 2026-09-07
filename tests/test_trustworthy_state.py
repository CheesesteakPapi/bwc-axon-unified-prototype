import json
import tempfile
import time
import unittest
from pathlib import Path
from shared_workspace import SharedWorkspace, RefreshLeaseConflict, RevisionConflict, value_hash
from local_diagnostics import LocalDiagnostics

FULL = {"type": "full", "filters": {}}


class TrustworthyStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = SharedWorkspace(Path(self.temp.name) / "workspace.sqlite3")

    def tearDown(self):
        for event in list(self.workspace._lease_stops.values()):
            event.set()
        self.temp.cleanup()

    def submitted(self):
        row = {"rowId": "test-row", "email": "test@example.test", "externalId": "test@tenant.example.test",
               "role": "Supervisor", "status": "Active", "location": "", "existingAccount": True,
               "validationState": "Ready", "differences": [{"field": "Role", "current": "User", "proposed": "Supervisor"}]}
        records = [{"EMAIL": row["email"], "EXTERNAL_ID": row["externalId"], "ROLE": row["role"]}]
        generation = {"userHash": value_hash(records), "groupHash": value_hash([]),
                      "userChunks": [{"rowIds": ["test-row"], "records": records}], "groupChunks": []}
        run = self.workspace.create_run("TEST", "synthetic", [row], {"blockerCount": 0}, generation, "Ready for Preview")
        run = self.workspace.approve_preview(run["runId"], run["revision"], True, 1)
        chunk = run["chunks"][0]["chunkId"]
        self.workspace.record_chunk_submission(run["runId"], run["revision"], chunk, "TEST-JOB", "")
        return row, run, chunk

    def current_overlay(self):
        return next(row for row in self.workspace.pending_overlays() if row["state"] != "Superseded")

    def test_confirmation_requires_completed_job_and_matching_fields(self):
        row, run, chunk = self.submitted()
        self.workspace.activate_snapshot("Users", [row], FULL)
        self.assertEqual(self.current_overlay()["state"], "Submitted—awaiting confirmation")
        self.workspace.record_chunk_result(run["runId"], run["revision"], chunk, "completed", {})
        self.workspace.activate_snapshot("Users", [{**row, "role": "User"}], FULL)
        overlay = self.current_overlay()
        self.assertEqual(overlay["state"], "Submitted—awaiting confirmation")
        self.assertEqual(overlay["payload"]["confirmation"]["mismatchedFields"], ["role"])
        self.workspace.activate_snapshot("Users", [row], FULL)
        self.assertEqual(self.current_overlay()["state"], "Confirmed")

    def test_missing_field_stays_unverified_and_filtered_cannot_confirm(self):
        row, run, chunk = self.submitted()
        self.workspace.record_chunk_result(run["runId"], run["revision"], chunk, "completed", {})
        self.workspace.activate_snapshot("Users", [{"Email": row["email"], "External ID": row["externalId"]}], FULL)
        self.assertIn("role", self.current_overlay()["payload"]["confirmation"]["unobservableFields"])
        self.workspace.activate_snapshot("Users", [row], {"type": "filtered", "filters": {"email": row["email"]}})
        self.assertNotEqual(self.current_overlay()["state"], "Confirmed")

    def test_duplicate_or_disagreeing_identity_cannot_confirm(self):
        row, run, chunk = self.submitted()
        self.workspace.record_chunk_result(run["runId"], run["revision"], chunk, "completed", {})
        for rows in ([row, row], [{**row, "externalId": "different@example.test"}]):
            self.workspace.activate_snapshot("Users", rows, FULL)
            self.assertNotEqual(self.current_overlay()["state"], "Confirmed")

    def test_lease_renews_and_fences_activation(self):
        lease = self.workspace.acquire_refresh_lease("Devices", "test-owner", FULL, ttl_seconds=1)
        time.sleep(1.2)
        with self.assertRaises(RefreshLeaseConflict):
            self.workspace.acquire_refresh_lease("Devices", "other", FULL)
        with self.assertRaises(RefreshLeaseConflict):
            self.workspace.activate_snapshot("Devices", [{"id": "test"}], FULL)
        self.workspace.activate_snapshot("Devices", [{"id": "test"}], FULL, lease_id=lease)
        self.workspace.release_refresh_lease("Devices", "test-owner", lease, "completed")

    def test_expired_worker_cannot_activate_or_release_replacement(self):
        old = self.workspace.acquire_refresh_lease("Devices", "old", FULL)
        self.workspace._lease_stops[old].set()
        with self.workspace.connection() as db:
            db.execute("UPDATE refresh_leases SET expires_at='2000-01-01T00:00:00Z'")
        new = self.workspace.acquire_refresh_lease("Devices", "new", FULL)
        with self.assertRaises(RefreshLeaseConflict):
            self.workspace.activate_snapshot("Devices", [{"id": "stale"}], FULL, lease_id=old)
        self.workspace.release_refresh_lease("Devices", "old", old, "failed")
        self.assertEqual(self.workspace.lease_status()[0]["refresh_id"], new)
        self.assertIsNone(self.workspace.active_snapshot("Devices"))
        self.workspace.release_refresh_lease("Devices", "new", new, "canceled")

    def test_tenant_binding_requires_explicit_legacy_confirmation(self):
        snapshot = self.workspace.activate_snapshot("Users", [{"id": "TEST"}], FULL)
        revision = self.workspace.revision()
        with self.assertRaises(ValueError):
            self.workspace.bind_tenant("https://test-agency.evidence.com")
        with self.assertRaises(RevisionConflict):
            self.workspace.bind_tenant("https://test-agency.evidence.com", confirm_legacy=True, expected_revision=revision-1)
        self.workspace.bind_tenant("https://test-agency.evidence.com", confirm_legacy=True, expected_revision=revision)
        self.workspace.bind_tenant("https://TEST-AGENCY.evidence.com/")
        with self.assertRaises(ValueError):
            self.workspace.bind_tenant("https://your-agency.evidence.com")
        self.assertEqual(self.workspace.active_snapshot("Users")["snapshotId"], snapshot["snapshotId"])
        self.assertTrue(self.workspace.verify_audit_chain()["valid"])

    def test_diagnostics_are_bounded_and_payload_free(self):
        diagnostics = LocalDiagnostics()
        for index in range(220):
            diagnostics.record(str(index), "GET", 200, 3.456)
        report = diagnostics.snapshot()
        self.assertEqual(report["count"], 200)
        self.assertEqual(set(report["requests"][0]), {"requestId", "method", "status", "durationMs", "at"})
        self.assertNotIn("email", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
