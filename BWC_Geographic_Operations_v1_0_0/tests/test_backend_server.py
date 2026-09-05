from __future__ import annotations

import atexit
import csv
import http.client
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

_MODULE_RUNTIME = tempfile.mkdtemp(prefix="bwc-geo-test-runtime-")
atexit.register(shutil.rmtree, _MODULE_RUNTIME, ignore_errors=True)
os.environ["BWC_AXON_DATA_ROOT"] = _MODULE_RUNTIME

import backend_server


class FakeAxonClient:
    instances = []

    def __init__(self, agency_base_url, client_id, client_secret, timeout_seconds=90):
        self.agency_base_url = agency_base_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout_seconds = timeout_seconds
        self.access_token = None
        self.token_expires_in = 14400
        self.http_429_count = 0
        self.http_5xx_retry_count = 0
        self.calls = []
        FakeAxonClient.instances.append(self)

    def authenticate(self):
        self.access_token = "test-token"

    def get_json(self, url, params=None, minimum_interval_seconds=0, max_retries=6):
        self.calls.append((url, dict(params or {}), minimum_interval_seconds))
        if url.endswith("/devices/homes/list"):
            return {"data": [
                {"attributes": {"name": "Example Home Alpha", "pointOfContactId": "u-1"}},
                {"attributes": {"name": "Guam", "pointOfContactId": "u-2"}},
            ]}
        if url.endswith("/groups"):
            return {"data": [
                {"id": "g-1", "attributes": {"externalId": "GROUP-TEST-001", "name": "TEST Prototype Users", "status": "ACTIVE"}},
                {"id": "g-2", "attributes": {"externalId": "TRAINING", "name": "Training", "status": "ACTIVE"}},
            ]}
        if url.endswith("/users"):
            return {"data": [
                {"id": "u-1", "attributes": {"externalId": "OFF-1", "firstName": "Alex", "lastName": "Rivera", "status": "ACTIVE", "role": "Officer"}},
                {"id": "u-2", "attributes": {"externalId": "OFF-2", "firstName": "Jordan", "lastName": "Lee", "status": "ACTIVE", "role": "Supervisor"}},
                {"id": "u-3", "attributes": {"externalId": "REV-1", "firstName": "Sam", "lastName": "Patel", "status": "ACTIVE", "role": "Evidence Reviewer"}},
            ]}
        if url.endswith("/devices"):
            devices = [
                {"id": "d-1", "attributes": {"serial": "DEMO-SN-1", "model": "Body 4", "status2": "ASSIGNED"}, "relationships": {"owner": {"data": {"id": "u-1"}}, "deviceHome": {"data": {"attributes": {"name": "Example Home Alpha"}}}}},
                {"id": "d-2", "attributes": {"serial": "DEMO-SN-2", "model": "Body 4", "status2": "IN_STOCK", "deviceHome": "Example Home Alpha"}, "relationships": {"owner": {"data": {}}, "deviceHome": {"data": {"attributes": {"name": "Example Home Alpha"}}}}},
                {"id": "d-3", "attributes": {"serial": "SN-3", "model": "Fleet 3", "status2": "LOST"}, "relationships": {"owner": {"data": {"id": "u-2"}}, "deviceHome": {"data": {"attributes": {"name": "Guam"}}}}},
            ]
            if (params or {}).get("status2"):
                devices = [item for item in devices if item["attributes"]["status2"] == params["status2"]]
            if (params or {}).get("model"):
                models = {value.strip() for value in params["model"].split(",")}
                devices = [item for item in devices if item["attributes"]["model"] in models]
            return {"data": devices}
        raise AssertionError(f"Unexpected URL: {url}")


class SlowAuthenticateAxonClient(FakeAxonClient):
    def authenticate(self):
        time.sleep(0.08)
        super().authenticate()


class BackendServerTests(unittest.TestCase):
    def setUp(self):
        FakeAxonClient.instances.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp.name)
        self.audit_env = patch.dict(os.environ, {"BWC_AXON_DATA_ROOT": str(self.temp_path / "runtime")})
        self.audit_env.start()
        self.config_example = json.loads(backend_server.CONFIG_EXAMPLE_PATH.read_text(encoding="utf-8"))
        self.config_example["agency_base_url"] = "https://test-agency.evidence.com"
        self.config_example["device_home_crosswalk_csv"] = str(backend_server.BASE_DIR / "device_home_crosswalk_starter.csv")
        self.config_example["device_status_map_csv"] = str(backend_server.BASE_DIR / "device_status_map.csv")
        self.config_example["axon_group_crosswalk_csv"] = str(backend_server.BASE_DIR / "axon_group_crosswalk_starter.csv")
        self.config_example["non_site_group_register_csv"] = str(backend_server.BASE_DIR / "axon_non_site_group_register_starter.csv")
        self.config_path = self.temp_path / "config.json"
        self.example_path = self.temp_path / "config.example.json"
        self.example_path.write_text(json.dumps(self.config_example), encoding="utf-8")
        self.config_path.write_text(json.dumps(self.config_example), encoding="utf-8")
        self.crosswalk_root = self.temp_path / "crosswalks"
        self.crosswalk_root.mkdir()
        for name in [
            "device_home_crosswalk_starter.csv",
            "axon_group_crosswalk_starter.csv",
            "axon_non_site_group_register_starter.csv",
            "facility_master_starter.csv",
            "office_presence_starter.csv",
            "axon_group_master_starter.csv",
            "site_group_relationship_starter.csv",
            "device_status_map.csv",
        ]:
            shutil.copy2(backend_server.SUITE_ROOT / "governance_starters" / name, self.crosswalk_root / name)
        self.crosswalk_backup_dir = self.temp_path / "backups" / "crosswalks"
        self.patchers = [
            patch.object(backend_server, "CONFIG_PATH", self.config_path),
            patch.object(backend_server, "CONFIG_EXAMPLE_PATH", self.example_path),
            patch.object(backend_server, "CROSSWALK_ROOT", self.crosswalk_root),
            patch.object(backend_server, "GOVERNANCE_STARTER_ROOT", backend_server.SUITE_ROOT / "governance_starters"),
            patch.object(backend_server, "CROSSWALK_BACKUP_DIR", self.crosswalk_backup_dir),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.audit_env.stop()
        self.temp.cleanup()

    def test_public_config_never_contains_credentials(self):
        saved = backend_server.save_public_config({
            "agencyBaseUrl": "https://test-agency.evidence.com/",
            "timeoutSeconds": 120,
            "clientSecret": "must-not-save",
        })
        stored = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["agencyBaseUrl"], "https://test-agency.evidence.com")
        self.assertFalse(saved["rawJsonEnabled"])
        self.assertNotIn("clientSecret", stored)
        self.assertNotIn("must-not-save", self.config_path.read_text(encoding="utf-8"))

    def test_tracked_models_persist_without_credentials(self):
        self.assertEqual(backend_server.public_config()["deviceModel"].split(","), [
            "axon_body_4_dock_8_bay", "axon_body_4_dock_1_bay", "taser_etm_flex_2",
            "axon_body_cam_4", "taser_body_cam_3", "taser_cew_10_handle",
        ])
        value = backend_server.save_public_config({
            "agencyBaseUrl": "https://test-agency.evidence.com",
            "deviceModel": "Synthetic A,Synthetic B",
        })
        self.assertEqual(value["deviceModel"], "Synthetic A,Synthetic B")
        self.assertEqual(backend_server.public_config()["deviceModel"], value["deviceModel"])
        with self.assertRaises(backend_server.UserInputError):
            backend_server.save_public_config({
                "agencyBaseUrl": "https://test-agency.evidence.com",
                "deviceModel": ",".join(str(n) for n in range(26)),
            })

    def test_all_local_tables_load_independently(self):
        backend_server.initialize_governance_working_files()
        for key in backend_server.CROSSWALK_SPECS:
            with self.subTest(table=key):
                payload = backend_server.list_crosswalk(key)
                self.assertTrue(payload["columns"])
                self.assertTrue(payload["editableFields"])

    def test_review_targets_are_explicit_and_preserve_partial_records(self):
        initial = backend_server.review_targets("device-homes", "synthetic home")
        self.assertFalse(initial["matches"])
        self.assertGreater(len(initial["targets"]), 0)
        target = initial["targets"][0]
        backend_server.update_crosswalk_row("device-homes", target["rowNumber"], {
            "changes": {"Device Home Name (API)": "Partial observed name"},
            "expected": target["values"],
        })
        vacant = backend_server.review_targets("device-homes", "synthetic home")
        self.assertNotIn(target["rowNumber"], [r["rowNumber"] for r in vacant["targets"]])
        backend_server.update_crosswalk_row("device-homes", target["rowNumber"], {
            "changes": {"Normalized Device Home Key": "synthetic home"},
        })
        exact = backend_server.review_targets("device-homes", " SYNTHETIC HOME ")
        self.assertEqual([r["rowNumber"] for r in exact["matches"]], [target["rowNumber"]])
        self.assertEqual(exact["targets"], exact["matches"])
        non_site = backend_server.review_targets("non-site-groups", "synthetic group")
        self.assertTrue(non_site["allowCreate"])
        self.assertFalse(non_site["targets"])
        with self.assertRaises(backend_server.UserInputError):
            backend_server.review_targets("directory-attributes", "mail")

    def test_device_only_model_pull_does_not_pull_other_resources(self):
        state = backend_server.SessionState(client_factory=FakeAxonClient)
        self.addCleanup(state.close)
        state.set_credentials("fixture-partner", "fixture-client", "fixture-secret")
        job = state.start_sync({"resources": ["Devices"], "deviceModel": "Body 4"})
        deadline = time.time() + 5
        result = state.job(job["jobId"])
        while result["status"] in {"queued", "running"} and time.time() < deadline:
            time.sleep(0.02)
            result = state.job(job["jobId"])
        self.assertEqual(result["status"], "complete", result.get("error"))
        calls = FakeAxonClient.instances[-1].calls
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0].endswith("/devices"))
        self.assertEqual(calls[0][1]["model"], "Body 4")
        self.assertEqual(result["receivedRecords"], 2)

    def test_shared_governance_initialization_is_missing_only(self):
        shared_root = self.temp_path / "shared" / "working"
        with patch.object(backend_server, "CROSSWALK_ROOT", shared_root):
            created = backend_server.initialize_governance_working_files()
            self.assertEqual(set(created), set(backend_server.GOVERNANCE_FILE_NAMES))
            sentinel = shared_root / "facility_master_starter.csv"
            original = sentinel.read_bytes()
            sentinel.write_bytes(original + b"\r\n")
            self.assertEqual(backend_server.initialize_governance_working_files(), [])
            self.assertEqual(sentinel.read_bytes(), original + b"\r\n")

    def test_tenant_url_is_restricted_to_https_evidence_host(self):
        with self.assertRaises(backend_server.UserInputError):
            backend_server.validate_tenant_url("http://agency.evidence.com")
        with self.assertRaises(backend_server.UserInputError):
            backend_server.validate_tenant_url("https://example.com")
        self.assertEqual(
            backend_server.validate_tenant_url("https://agency.evidence.com/"),
            "https://agency.evidence.com",
        )

    def test_pagination_url_cannot_move_token_to_another_host(self):
        self.assertEqual(
            backend_server.resolve_url(
                "https://agency.evidence.com",
                "https://agency.evidence.com/api/v1/agencies/a/devices?offset=100",
            ),
            "https://agency.evidence.com/api/v1/agencies/a/devices?offset=100",
        )
        with self.assertRaises(RuntimeError):
            backend_server.resolve_url(
                "https://agency.evidence.com",
                "https://example.com/collect-token",
            )

    def test_read_only_sync_builds_live_dashboard_and_applies_device_filters(self):
        state = backend_server.SessionState(client_factory=FakeAxonClient)
        try:
            state.set_credentials("agency-1234", "client-id", "client-secret")
            full_job = state.start_sync({"resources": ["DeviceHomes", "Users", "Devices", "Groups"]})
            deadline = time.time() + 5
            full_result = state.job(full_job["jobId"])
            while full_result["status"] in {"queued", "running"} and time.time() < deadline:
                time.sleep(0.02)
                full_result = state.job(full_job["jobId"])
            self.assertEqual(full_result["status"], "complete", full_result.get("error"))
            self.assertEqual(state.dashboard()["resourceCounts"]["Devices"], 3)

            job = state.start_sync({
                "resources": ["Devices", "Groups"],
                "deviceModel": "Body 4,Fleet 3",
                "deviceStatus": "ASSIGNED",
                "deviceHomeId": "home-1",
            })
            deadline = time.time() + 5
            result = state.job(job["jobId"])
            while result["status"] in {"queued", "running"} and time.time() < deadline:
                time.sleep(0.02)
                result = state.job(job["jobId"])
            self.assertEqual(result["status"], "complete", result.get("error"))
            self.assertEqual(result["currentResource"], "Devices")
            self.assertEqual(result["currentPage"], 1)
            self.assertEqual(result["receivedRecords"], 1)
            dashboard = state.dashboard()
            self.assertEqual(dashboard["mode"], "live")
            self.assertEqual(dashboard["resourceCounts"]["Devices"], 3)
            self.assertEqual(dashboard["summary"]["assignedDevices"], 2)
            self.assertEqual(dashboard["summary"]["unassignedDevices"], 1)
            self.assertEqual(dashboard["summary"]["totalUsers"], 3)
            self.assertEqual(len(dashboard["assignments"]), 3)
            self.assertIn("componentSummaries", dashboard)
            device_calls = [call for call in FakeAxonClient.instances[-1].calls if call[0].endswith("/devices")]
            self.assertEqual(len(device_calls), 1)
            self.assertEqual(device_calls[0][1]["model"], "Body 4,Fleet 3")
            self.assertEqual(device_calls[0][1]["status2"], "ASSIGNED")
            self.assertEqual(device_calls[0][1]["homeId"], "home-1")
            self.assertEqual(device_calls[0][2], 5)
            filtered_download = state.resolve_download("devices")
            self.assertIsNotNone(filtered_download)
            with filtered_download.open("r", encoding="utf-8-sig", newline="") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 1)
            self.assertEqual(state.workspace.active_snapshot("Devices", prefer_full=True)["rowCount"], 3)
            self.assertEqual(state.workspace.active_snapshot("Devices", prefer_full=False)["rowCount"], 1)
            self.assertIsNotNone(state.resolve_download("summary"))
            self.assertIsNotNone(state.resolve_download("assignments"))
            self.assertIsNotNone(state.resolve_download("device-status"))
            self.assertIsNotNone(state.resolve_download("exceptions"))
        finally:
            state.close()

    def test_live_sync_maps_from_shared_sqlite_not_a_stale_csv_projection(self):
        state = backend_server.SessionState(client_factory=FakeAxonClient)
        try:
            dataset = state.workspace.governance_dataset("device_home_crosswalk_starter")
            rows = [dict(row) for row in dataset["rows"]]
            rows[0].update({
                "Device Home Name (API)": "Example Home Alpha",
                "Normalized Device Home Key": "example home alpha",
                "Mapping Status": "Mapped",
                "Mapping Method": "Exact name",
                "Confidence": "High",
                "Review Notes": "Authoritative SQLite mapping for sync test.",
            })
            state.workspace.replace_governance_rows(
                "device_home_crosswalk_starter",
                rows,
                dataset["revision"],
                "test-sync-authority",
                "test",
            )
            with (self.crosswalk_root / "device_home_crosswalk_starter.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as handle:
                stale_rows = list(csv.DictReader(handle))
            self.assertNotEqual(stale_rows[0]["Mapping Status"], "Mapped")

            state.set_credentials("agency-1234", "client-id", "client-secret")
            job = state.start_sync({"resources": ["DeviceHomes"]})
            deadline = time.time() + 5
            result = state.job(job["jobId"])
            while result["status"] in {"queued", "running"} and time.time() < deadline:
                time.sleep(0.02)
                result = state.job(job["jobId"])
            self.assertEqual(result["status"], "complete", result.get("error"))
            snapshot = state.workspace.active_snapshot("DeviceHomes")
            mapped_home = next(
                row for row in snapshot["rows"] if row["Normalized Device Home Key"] == "example home alpha"
            )
            self.assertEqual(mapped_home["Mapped Site ID"], rows[0]["Site ID"])
        finally:
            state.close()

    def test_live_sync_uses_current_file_governed_device_status_map(self):
        state = backend_server.SessionState(client_factory=FakeAxonClient)
        try:
            status_path = self.crosswalk_root / "device_status_map.csv"
            with status_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                headers = list(reader.fieldnames or [])
                rows = list(reader)
            for row in rows:
                if row["Raw Axon Device Status"] == "Assigned":
                    row["Reporting State"] = "Reviewed Operational"
            backend_server.write_csv(rows, headers, status_path)

            state.set_credentials("agency-1234", "client-id", "client-secret")
            job = state.start_sync({"resources": ["Devices"]})
            deadline = time.time() + 5
            result = state.job(job["jobId"])
            while result["status"] in {"queued", "running"} and time.time() < deadline:
                time.sleep(0.02)
                result = state.job(job["jobId"])

            self.assertEqual(result["status"], "complete", result.get("error"))
            devices = state.workspace.active_snapshot("Devices", prefer_full=True)["rows"]
            assigned = next(row for row in devices if row["Axon Device ID"] == "d-1")
            self.assertEqual(assigned["Reporting Device State"], "Reviewed Operational")
        finally:
            state.close()

    def test_confirmed_mapping_metrics_require_explicit_mapped_status(self):
        target = self.crosswalk_root / "device_home_crosswalk_starter.csv"
        with target.open("r", encoding="utf-8-sig", newline="") as handle:
            headers = list(csv.DictReader(handle).fieldnames or [])
        candidate = {header: "" for header in headers}
        candidate.update({
            "Site ID": "TEST-SITE-CANDIDATE",
            "Component": "TEST",
            "Region / AOR": "Candidate AOR",
            "Device Home Name (API)": "Candidate Home",
            "Normalized Device Home Key": "candidate home",
            "Mapping Status": "Candidate",
        })
        mapped = {header: "" for header in headers}
        mapped.update({
            "Site ID": "TEST-SITE-MAPPED",
            "Component": "TEST",
            "Region / AOR": "Mapped AOR",
            "Device Home Name (API)": "Mapped Home",
            "Normalized Device Home Key": "mapped home",
            "Mapping Status": "Mapped",
        })
        backend_server.write_csv([candidate, mapped], headers, target)
        workspace = backend_server.governance_workspace()
        workspace.migrate_governance_csvs(self.crosswalk_root)
        group_dataset = workspace.governance_dataset("axon_group_crosswalk_starter")
        group_rows = [dict(row) for row in group_dataset["rows"]]
        group_rows[0].update({
            "Axon Group ID": "group-candidate",
            "Axon Group Name": "Candidate Group",
            "Mapping Status": "Candidate",
            "Review Notes": "Candidate relationship still requires review.",
        })
        group_rows[1].update({
            "Axon Group ID": "group-mapped",
            "Axon Group Name": "Mapped Group",
            "Mapping Status": "Mapped",
            "Review Notes": "Reviewed site relationship.",
        })
        workspace.replace_governance_rows(
            "axon_group_crosswalk_starter",
            group_rows,
            group_dataset["revision"],
            "test-group-crosswalk",
            "test",
        )

        stale_projection = dict(mapped)
        stale_projection["Mapping Status"] = "Candidate"
        stale_projection["Region / AOR"] = "Stale CSV AOR"
        backend_server.write_csv([candidate, stale_projection], headers, target)

        payload = backend_server.build_dashboard_payload(
            {
                "Devices": [
                    {
                        "Axon Device ID": "device-candidate",
                        "Serial Number": "TEST-CANDIDATE",
                        "Device Model": "Body 4",
                        "Device Status": "ASSIGNED",
                        "Reporting Device State": "Assigned",
                        "Assigned User ID": "user-1",
                        "Device Home Name (API)": "Candidate Home",
                        "Normalized Device Home Key": "candidate home",
                        "Mapped Site ID": "STALE-SITE-ID",
                    },
                    {
                        "Axon Device ID": "device-mapped",
                        "Serial Number": "TEST-MAPPED",
                        "Device Model": "Body 4",
                        "Device Status": "ASSIGNED",
                        "Reporting Device State": "Assigned",
                        "Assigned User ID": "user-2",
                        "Device Home Name (API)": "Mapped Home",
                        "Normalized Device Home Key": "mapped home",
                    },
                ],
                "DeviceHomes": [
                    {
                        "Device Home Name (API)": "Candidate Home",
                        "Normalized Device Home Key": "candidate home",
                        "Mapped Site ID": "STALE-SITE-ID",
                    },
                    {
                        "Device Home Name (API)": "Mapped Home",
                        "Normalized Device Home Key": "mapped home",
                    },
                ],
                "Users": [],
                "Groups": [
                    {
                        "Axon Group ID": "group-candidate",
                        "Group Name": "Candidate Group",
                        "Group Classification": "Site-Mapped",
                        "Mapped Site ID": "STALE-GROUP-SITE",
                        "Mapping Status": "Mapped",
                    },
                    {
                        "Axon Group ID": "group-mapped",
                        "Group Name": "Mapped Group",
                        "Group Classification": "Unclassified",
                        "Mapping Status": "Unmapped",
                    },
                ],
            },
            "2026-09-04T12:00:00Z",
            {},
            ["Devices", "DeviceHomes"],
        )

        self.assertEqual(payload["summary"]["mappedDevices"], 1)
        self.assertEqual(payload["summary"]["mappingCompletion"], 50.0)
        self.assertEqual(payload["summary"]["unmappedDeviceHomes"], 1)
        self.assertEqual(payload["summary"]["regionCounts"], {"Unassigned": 1, "Mapped AOR": 1})
        inventory = {row["serialNumber"]: row for row in payload["inventory"]}
        self.assertEqual(inventory["TEST-CANDIDATE"]["mappedSiteId"], "")
        self.assertEqual(inventory["TEST-CANDIDATE"]["component"], "")
        self.assertEqual(inventory["TEST-MAPPED"]["mappedSiteId"], "TEST-SITE-MAPPED")
        self.assertEqual(inventory["TEST-MAPPED"]["regionAor"], "Mapped AOR")
        self.assertEqual(
            [row["sourceId"] for row in payload["crosswalkReview"]],
            ["Candidate Home", "Candidate Group"],
        )
        groups = {row["groupId"]: row for row in payload["groups"]}
        self.assertEqual(groups["group-candidate"]["classification"], "Unclassified")
        self.assertEqual(groups["group-candidate"]["mappedSiteId"], "")
        self.assertEqual(groups["group-candidate"]["mappingStatus"], "Candidate")
        self.assertEqual(groups["group-mapped"]["classification"], "Site-Mapped")
        self.assertTrue(groups["group-mapped"]["mappedSiteId"])
        self.assertEqual(payload["summary"]["groupClassificationCounts"], {"Unclassified": 1, "Site-Mapped": 1})

    def test_running_pull_can_stop_safely_without_replacing_dashboard(self):
        state = backend_server.SessionState(client_factory=SlowAuthenticateAxonClient)
        try:
            state.set_credentials("agency-1234", "client-id", "client-secret")
            job = state.start_sync({"resources": ["Devices"]})
            cancel_result = state.request_cancel(job["jobId"])
            self.assertTrue(cancel_result["cancelRequested"])
            self.assertEqual(cancel_result["status"], "cancel-requested")
            deadline = time.time() + 5
            result = state.job(job["jobId"])
            while result["status"] in {"queued", "running", "cancel-requested"} and time.time() < deadline:
                time.sleep(0.02)
                result = state.job(job["jobId"])
            self.assertEqual(result["status"], "canceled", result.get("error"))
            self.assertEqual(state.dashboard()["mode"], "illustrative")
        finally:
            state.close()

    def test_canceled_multi_resource_pull_does_not_activate_partial_snapshots(self):
        state = backend_server.SessionState(client_factory=FakeAxonClient)
        prior = state.workspace.activate_snapshot(
            "DeviceHomes",
            [{
                "Device Home Name (API)": "Prior Home",
                "Normalized Device Home Key": "prior home",
                "Mapped Site ID": "",
                "Mapped Component": "",
                "Mapped Region / AOR": "",
                "Mapping Status": "Unmapped",
                "Last Sync At": "2026-09-04T00:00:00Z",
                "Sync Status": "Synced",
            }],
            {"type": "full", "filters": {}},
            "prior test baseline",
        )

        def cancel_after_first_resource(client, config, resource_name, resource_config, partner_id, **kwargs):
            if resource_name == "DeviceHomes":
                return ([{"attributes": {"name": "Replacement Home"}}], 1, "")
            raise backend_server.PullCancelledError("Synthetic cancellation after one fetched resource.")

        try:
            state.set_credentials("agency-1234", "client-id", "client-secret")
            with patch.object(backend_server, "fetch_resource", side_effect=cancel_after_first_resource):
                job = state.start_sync({"resources": ["Devices"]})
                deadline = time.time() + 5
                result = state.job(job["jobId"])
                while result["status"] in {"queued", "running", "cancel-requested"} and time.time() < deadline:
                    time.sleep(0.02)
                    result = state.job(job["jobId"])
            self.assertEqual(result["status"], "canceled", result.get("error"))
            active = state.workspace.active_snapshot("DeviceHomes")
            self.assertEqual(active["snapshotId"], prior["snapshotId"])
            self.assertEqual(active["rows"][0]["Device Home Name (API)"], "Prior Home")
            self.assertIsNone(state.workspace.active_snapshot("Users"))
            self.assertIsNone(state.workspace.active_snapshot("Devices"))
        finally:
            state.close()

    def test_filtered_devices_without_a_full_snapshot_are_not_confirmed_metrics(self):
        state = backend_server.SessionState(client_factory=FakeAxonClient)
        try:
            state.set_credentials("agency-1234", "client-id", "client-secret")
            job = state.start_sync({
                "resources": ["Devices"],
                "deviceModel": "Body 4",
                "deviceStatus": "ASSIGNED",
            })
            deadline = time.time() + 5
            result = state.job(job["jobId"])
            while result["status"] in {"queued", "running"} and time.time() < deadline:
                time.sleep(0.02)
                result = state.job(job["jobId"])
            self.assertEqual(result["status"], "complete", result.get("error"))

            dashboard = state.dashboard()

            self.assertEqual(dashboard["mode"], "filtered")
            self.assertFalse(dashboard["confirmedDeviceBaseline"])
            self.assertEqual(dashboard["deviceMetricsScope"], "filtered")
            self.assertEqual(dashboard["summary"]["totalDevices"], 1)
            self.assertEqual(dashboard["baselineScopes"]["Devices"]["type"], "filtered")
            preferred = state.workspace.active_snapshot("Devices", prefer_full=True)
            self.assertEqual(preferred["scope"]["type"], "filtered")
            self.assertNotIn("Devices", state._active_baseline()[0])
            self.assertEqual(state.workspace.active_snapshot("Devices", prefer_full=False)["rowCount"], 1)
        finally:
            state.close()

    def test_users_only_refresh_does_not_export_unknown_device_counts_as_zero(self):
        state = backend_server.SessionState(client_factory=FakeAxonClient)
        try:
            state.set_credentials("agency-1234", "client-id", "client-secret")
            job = state.start_sync({"resources": ["Users"]})
            deadline = time.time() + 5
            result = state.job(job["jobId"])
            while result["status"] in {"queued", "running"} and time.time() < deadline:
                time.sleep(0.02)
                result = state.job(job["jobId"])
            self.assertEqual(result["status"], "complete", result.get("error"))

            dashboard = state.dashboard()
            self.assertEqual(dashboard["mode"], "partial")
            self.assertEqual(dashboard["deviceMetricsScope"], "unavailable")
            self.assertIsNone(dashboard["summary"]["totalDevices"])
            self.assertIsNone(dashboard["summary"]["unmappedDeviceHomes"])
            self.assertIsNone(dashboard["summary"]["totalGroups"])
            self.assertEqual(dashboard["projectedSummary"]["confirmedUsers"], 3)
            self.assertTrue(all(row["deviceCount"] is None for row in dashboard["assignments"]))
            self.assertNotIn("Devices", dashboard["resources"])
            self.assertEqual(dashboard["availableDownloads"], ["summary", "users"])
            self.assertIsNone(state.resolve_download("assignments"))
            self.assertIsNone(state.resolve_download("device-status"))
            self.assertIsNone(state.resolve_download("exceptions"))
        finally:
            state.close()

    def test_pending_users_remain_unprojected_without_confirmed_users_snapshot(self):
        state = backend_server.SessionState(client_factory=FakeAxonClient)
        try:
            state.workspace.activate_snapshot(
                "Groups",
                [{"Axon Group ID": "g-1", "Group Name": "TEST Prototype Users"}],
                {"type": "full", "filters": {}},
            )
            state.workspace.create_run(
                "Pending without Users baseline",
                "synthetic-test",
                [{
                    "rowId": "row-1",
                    "email": "pending.user@example.test",
                    "firstName": "Pending",
                    "lastName": "User",
                    "validationState": "Ready",
                    "existingAccount": False,
                    "groupExternalId": "",
                }],
                {"blockerCount": 0},
                {"userChunks": [], "groupChunks": []},
                "Ready for Preview",
            )

            dashboard = state.dashboard()

            self.assertEqual(dashboard["mode"], "partial")
            self.assertIsNone(dashboard["summary"]["totalUsers"])
            self.assertIsNone(dashboard["projectedSummary"]["confirmedUsers"])
            self.assertIsNone(dashboard["projectedSummary"]["baselinePlusPendingUsers"])
            self.assertEqual(dashboard["pendingSummary"]["proposedCreations"], 1)
        finally:
            state.close()

    def test_persisted_baseline_does_not_advertise_expired_session_downloads(self):
        state = backend_server.SessionState(client_factory=FakeAxonClient)
        state.set_credentials("agency-1234", "client-id", "client-secret")
        job = state.start_sync({"resources": ["Devices"]})
        deadline = time.time() + 5
        result = state.job(job["jobId"])
        while result["status"] in {"queued", "running"} and time.time() < deadline:
            time.sleep(0.02)
            result = state.job(job["jobId"])
        self.assertEqual(result["status"], "complete", result.get("error"))
        self.assertIn("devices", state.dashboard()["availableDownloads"])
        state.close()

        reopened = backend_server.SessionState(client_factory=FakeAxonClient)
        try:
            dashboard = reopened.dashboard()
            self.assertEqual(dashboard["mode"], "live")
            self.assertEqual(dashboard["summary"]["totalDevices"], 3)
            self.assertEqual(dashboard["availableDownloads"], [])
            self.assertEqual(dashboard["downloadScope"], {})
            self.assertIsNone(reopened.resolve_download("devices"))
            self.assertIsNone(reopened.resolve_download("summary"))
        finally:
            reopened.close()

    def test_auto_port_uses_next_loopback_port_when_requested_port_is_busy(self):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        requested_port = blocker.getsockname()[1]
        state = backend_server.SessionState(client_factory=FakeAxonClient)
        server = None
        try:
            server = backend_server.make_server(requested_port, state, auto_port=True)
            self.assertNotEqual(server.server_address[1], requested_port)
            self.assertGreater(server.server_address[1], 0)
        finally:
            if server:
                server.server_close()
            blocker.close()

    def test_loopback_api_requires_per_launch_session_cookie(self):
        state = backend_server.SessionState(client_factory=FakeAxonClient)
        server = backend_server.make_server(0, state)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = int(server.server_address[1])
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", "/api/health")
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 401)

            connection.request("GET", f"/?launch={state.local_token}")
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 303)
            cookie = response.getheader("Set-Cookie")
            self.assertIn(backend_server.LOCAL_SESSION_COOKIE, cookie)
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Strict", cookie)

            connection.request("GET", "/api/health", headers={"Cookie": cookie.split(";", 1)[0]})
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertTrue(payload["readOnly"])
            self.assertTrue(payload["productionMode"])
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            state.close()

    def test_credentials_clear_without_persistence(self):
        state = backend_server.SessionState(client_factory=FakeAxonClient)
        try:
            state.set_credentials("agency-1234", "client-id", "client-secret")
            self.assertTrue(state.session_status()["configured"])
            state.clear_credentials()
            self.assertFalse(state.session_status()["configured"])
            self.assertNotIn("client-secret", self.config_path.read_text(encoding="utf-8"))
        finally:
            state.close()

    def test_session_status_never_returns_full_partner_id(self):
        state = backend_server.SessionState(client_factory=FakeAxonClient)
        try:
            state.set_credentials("abcd", "client-id", "client-secret")
            self.assertEqual(state.session_status()["partnerHint"], "••••")
            state.set_credentials("agency-1234", "client-id", "client-secret")
            self.assertEqual(state.session_status()["partnerHint"], "…1234")
        finally:
            state.close()

    def test_crosswalk_key_and_edit_fields_are_allowlisted(self):
        with self.assertRaises(backend_server.UserInputError):
            backend_server.get_crosswalk_spec("../config")
        with self.assertRaises(backend_server.UserInputError):
            backend_server.update_crosswalk_row(
                "device-homes",
                1,
                {"changes": {"Site ID": "BWC-CHANGED"}},
            )
        with self.assertRaises(backend_server.UserInputError):
            backend_server.update_crosswalk_row(
                "axon-groups",
                1,
                {"changes": {"Region / AOR": "Changed"}},
            )

    def test_crosswalk_list_supports_search_pagination_and_edit_metadata(self):
        payload = backend_server.list_crosswalk(
            "device-homes",
            page=1,
            page_size=2,
            search="Example",
        )
        self.assertEqual(payload["key"], "device-homes")
        self.assertEqual(payload["pageSize"], 2)
        self.assertGreaterEqual(payload["total"], 1)
        self.assertLessEqual(len(payload["rows"]), 2)
        columns = {column["key"]: column for column in payload["columns"]}
        self.assertFalse(columns["Site ID"]["editable"])
        self.assertFalse(columns["Region / AOR"]["editable"])
        self.assertTrue(columns["Device Home Name (API)"]["editable"])
        self.assertEqual(
            columns["Mapping Status"]["options"],
            ["Unmapped", "Candidate", "Needs review", "Mapped", "No match"],
        )
        self.assertEqual(payload["fieldOptions"]["Confidence"], ["Not rated", "Low", "Medium", "High"])
        self.assertNotIn("Observed ID", payload["fieldOptions"]["Mapping Method"])
        self.assertFalse(payload["axonWrite"])
        self.assertNotIn("client-secret-sentinel", json.dumps(payload))
        with self.assertRaises(backend_server.UserInputError):
            backend_server.list_crosswalk("device-homes", page_size=201)
        with self.assertRaises(backend_server.UserInputError):
            backend_server.update_crosswalk_row(
                "device-homes",
                1,
                {"changes": {"Mapping Status": "Auto matched"}},
            )
        with self.assertRaisesRegex(backend_server.UserInputError, "Mapping Method must be one of"):
            backend_server.update_crosswalk_row(
                "device-homes",
                1,
                {"changes": {"Mapping Method": "Observed ID"}},
            )

    def test_crosswalk_edit_values_reject_spreadsheet_formula_prefixes(self):
        editable_fields = sorted({
            field
            for spec in backend_server.CROSSWALK_SPECS.values()
            for field in spec["editableFields"]
        })
        prefixes = ["=", " +", "\t-", "  @"]
        for index, field in enumerate(editable_fields):
            with self.subTest(field=field):
                value = f"{prefixes[index % len(prefixes)]}FORMULA()"
                with self.assertRaisesRegex(backend_server.UserInputError, "spreadsheet applications may treat it as a formula"):
                    backend_server._clean_crosswalk_value(field, value)

        target = self.crosswalk_root / "axon_non_site_group_register_starter.csv"
        before = target.read_bytes()
        with self.assertRaisesRegex(backend_server.UserInputError, "spreadsheet applications may treat it as a formula"):
            backend_server.create_crosswalk_row(
                "non-site-groups",
                {"values": {"Axon Group ID": "group-1", "Group Name": "  =HYPERLINK()"}},
            )
        self.assertEqual(target.read_bytes(), before)

    def test_crosswalk_update_is_atomic_preserves_bom_and_header_and_creates_backup(self):
        target = self.crosswalk_root / "device_home_crosswalk_starter.csv"
        original = target.read_bytes()
        with target.open("r", encoding="utf-8-sig", newline="") as handle:
            original_headers = list(csv.DictReader(handle).fieldnames or [])

        result = backend_server.update_crosswalk_row(
            "device-homes",
            1,
            {
                "changes": {
                    "Device Home Name (API)": "Example Home Alpha",
                    "Normalized Device Home Key": "example home alpha",
                    "Mapping Status": "Mapped",
                    "Mapping Method": "Exact name",
                    "Confidence": "High",
                    "Review Notes": "Validated locally; no Axon write performed.",
                },
                "expected": {"Site ID": "DEMO-SITE-001", "Mapping Status": "Unmapped"},
            },
        )

        updated = target.read_bytes()
        self.assertTrue(updated.startswith(b"\xef\xbb\xbf"))
        self.assertNotEqual(updated, original)
        with target.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(list(reader.fieldnames or []), original_headers)
            first = next(reader)
        self.assertEqual(first["Normalized Device Home Key"], "example home alpha")
        self.assertEqual(first["Mapping Status"], "Mapped")
        backup = self.crosswalk_backup_dir / result["backupFileName"]
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.read_bytes(), original)
        self.assertFalse(list(self.crosswalk_root.glob("*.tmp")))
        self.assertFalse(result["axonWrite"])

        before_conflict = target.read_bytes()
        backup_count = len(list(self.crosswalk_backup_dir.glob("*.csv")))
        with self.assertRaises(backend_server.CrosswalkConflictError):
            backend_server.update_crosswalk_row(
                "device-homes",
                1,
                {
                    "changes": {"Review Notes": "Stale edit"},
                    "expected": {"Mapping Status": "Unmapped"},
                },
            )
        self.assertEqual(target.read_bytes(), before_conflict)
        self.assertEqual(len(list(self.crosswalk_backup_dir.glob("*.csv"))), backup_count)

    def test_projection_failure_does_not_misreport_the_authoritative_sqlite_commit(self):
        target = self.crosswalk_root / "device_home_crosswalk_starter.csv"
        original = target.read_bytes()
        listed = backend_server.list_crosswalk("device-homes", page=1, page_size=25)
        original_notes = listed["rows"][0]["values"]["Review Notes"]

        with patch.object(backend_server, "_write_crosswalk_atomic", side_effect=OSError("synthetic projection failure")):
            result = backend_server.update_crosswalk_row(
                "device-homes",
                1,
                {
                    "changes": {"Review Notes": "Saved in SQLite while projection refresh is unavailable."},
                    "expected": {"Review Notes": original_notes},
                },
            )

        self.assertEqual(result["projectionStatus"], "warning")
        self.assertIn("shared workspace was saved", result["projectionWarning"])
        self.assertEqual(result["backupFileName"], "")
        self.assertEqual(target.read_bytes(), original)
        persisted = backend_server.governance_workspace().governance_dataset("device_home_crosswalk_starter")
        self.assertEqual(
            persisted["rows"][0]["Review Notes"],
            "Saved in SQLite while projection refresh is unavailable.",
        )
        self.assertTrue(backend_server.governance_workspace().verify_audit_chain()["valid"])

    def test_cross_process_revision_change_blocks_a_stale_governance_overwrite(self):
        target = self.crosswalk_root / "device_home_crosswalk_starter.csv"
        original_projection = target.read_bytes()
        backend_server.list_crosswalk("device-homes", page=1, page_size=25)
        workspace = backend_server.governance_workspace()
        original_replace = workspace.replace_governance_rows
        raced = False

        def replace_after_concurrent_change(dataset_key, rows, expected_revision, event_type, reviewer, details=None):
            nonlocal raced
            if not raced:
                raced = True
                latest = workspace.governance_dataset(dataset_key)
                concurrent_rows = [dict(row) for row in latest["rows"]]
                concurrent_rows[0]["Review Notes"] = "Concurrent shared-workspace decision."
                original_replace(
                    dataset_key,
                    concurrent_rows,
                    latest["revision"],
                    "test-concurrent-change",
                    "other-process",
                )
            return original_replace(dataset_key, rows, expected_revision, event_type, reviewer, details)

        with patch.object(backend_server, "governance_workspace", return_value=workspace), patch.object(
            workspace,
            "replace_governance_rows",
            side_effect=replace_after_concurrent_change,
        ):
            with self.assertRaises(backend_server.CrosswalkConflictError):
                backend_server.update_crosswalk_row(
                    "device-homes",
                    1,
                    {"changes": {"Review Notes": "Stale local edit."}},
                )

        persisted = workspace.governance_dataset("device_home_crosswalk_starter")
        self.assertEqual(persisted["rows"][0]["Review Notes"], "Concurrent shared-workspace decision.")
        self.assertEqual(target.read_bytes(), original_projection)

    def test_crosswalk_unique_ids_are_validated_before_write(self):
        backend_server.update_crosswalk_row(
            "axon-groups",
            1,
            {"changes": {"Axon Group ID": "group-1", "Axon Group Name": "TEST Prototype Users"}},
        )
        before = (self.crosswalk_root / "axon_group_crosswalk_starter.csv").read_bytes()
        with self.assertRaises(backend_server.UserInputError):
            backend_server.update_crosswalk_row(
                "axon-groups",
                2,
                {"changes": {"Axon Group ID": "GROUP-1"}},
            )
        self.assertEqual((self.crosswalk_root / "axon_group_crosswalk_starter.csv").read_bytes(), before)

    def test_guided_personnel_match_uses_approved_status_and_stale_guard(self):
        backend_server.initialize_governance_working_files()
        backend_server.governance_workspace().migrate_governance_csvs(self.crosswalk_root)
        original = backend_server.governance_workspace().governance_dataset("personnel_location_aor_crosswalk")["rows"][0]
        payload = {"changes": {
            "Personnel AOR": "TEST REVIEW AREA", "Review Status": "Approved",
            "Reviewer": "Synthetic reviewer", "Review Notes": "Synthetic UI contract test",
            "Reviewed At UTC": "2026-09-04T00:00:00Z",
        }, "expected": original}
        backend_server.update_crosswalk_row("personnel-aor", 1, payload)
        saved = backend_server.governance_workspace().governance_dataset("personnel_location_aor_crosswalk")["rows"][0]
        self.assertEqual(saved["Personnel AOR"], "TEST REVIEW AREA")
        self.assertEqual(saved["Review Status"], "Approved")
        with self.assertRaises(backend_server.CrosswalkConflictError):
            backend_server.update_crosswalk_row("personnel-aor", 1, payload)

    def test_mapped_site_rows_require_observed_source_and_review_evidence(self):
        device_target = self.crosswalk_root / "device_home_crosswalk_starter.csv"
        device_before = device_target.read_bytes()
        with self.assertRaises(backend_server.UserInputError) as context:
            backend_server.update_crosswalk_row(
                "device-homes",
                1,
                {
                    "changes": {
                        "Mapping Status": "Mapped",
                        "Review Notes": "",
                    }
                },
            )
        for required in [
            "Device Home Name (API)",
            "Normalized Device Home Key",
            "Review Notes",
            "reviewed Mapping Method",
            "rated Confidence",
        ]:
            self.assertIn(required, str(context.exception))
        self.assertEqual(device_target.read_bytes(), device_before)

        group_target = self.crosswalk_root / "axon_group_crosswalk_starter.csv"
        group_before = group_target.read_bytes()
        with self.assertRaisesRegex(backend_server.UserInputError, "Axon Group ID"):
            backend_server.update_crosswalk_row(
                "axon-groups",
                1,
                {
                    "changes": {
                        "Mapping Status": "Mapped",
                        "Mapping Method": "Observed ID",
                        "Confidence": "High",
                        "Review Notes": "Owner approved the observed Group relationship.",
                    }
                },
            )
        self.assertEqual(group_target.read_bytes(), group_before)

    def test_non_site_controlled_values_and_creation_identity_are_enforced(self):
        payload = backend_server.list_crosswalk("non-site-groups")
        self.assertEqual(
            payload["fieldOptions"]["Group Classification"],
            ["Command", "Role-related", "Training", "Enterprise", "Administrative", "Other non-site"],
        )
        self.assertEqual(
            payload["fieldOptions"]["Command Hierarchy Level"],
            ["Enterprise", "Component", "Region / AOR", "Field office", "Suboffice", "Function", "Not applicable"],
        )
        self.assertEqual(
            payload["fieldOptions"]["Reporting Inclusion"],
            ["Include", "Exclude", "Context only", "Pending review"],
        )
        with self.assertRaisesRegex(backend_server.UserInputError, "Axon Group ID"):
            backend_server.create_crosswalk_row(
                "non-site-groups",
                {"values": {"Group Name": "Training Cadre"}},
            )
        with self.assertRaisesRegex(backend_server.UserInputError, "Group Name"):
            backend_server.create_crosswalk_row(
                "non-site-groups",
                {"values": {"Axon Group ID": "training-1"}},
            )
        with self.assertRaisesRegex(backend_server.UserInputError, "Group Classification must be one of"):
            backend_server.create_crosswalk_row(
                "non-site-groups",
                {
                    "values": {
                        "Axon Group ID": "training-1",
                        "Group Name": "Training Cadre",
                        "Group Classification": "Operational",
                    }
                },
            )

    def test_registered_non_site_requires_complete_classification_and_review_evidence(self):
        target = self.crosswalk_root / "axon_non_site_group_register_starter.csv"
        before = target.read_bytes()
        with self.assertRaises(backend_server.UserInputError) as context:
            backend_server.create_crosswalk_row(
                "non-site-groups",
                {
                    "values": {
                        "Axon Group ID": "training-1",
                        "Group Name": "Training Cadre",
                        "Mapping Status": "Registered non-site",
                    }
                },
            )
        for required in [
            "Group Classification",
            "Command Hierarchy Level",
            "Review Notes",
        ]:
            self.assertIn(required, str(context.exception))
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(self.crosswalk_backup_dir.exists())

    def test_non_site_group_register_can_add_then_update_local_rows(self):
        empty = backend_server.list_crosswalk("non-site-groups", page=1, page_size=25)
        self.assertEqual(empty["rowKey"], "rowNumber")
        self.assertEqual(empty["total"], 0)
        self.assertEqual(empty["rows"], [])
        columns = {column["key"]: column for column in empty["columns"]}
        self.assertTrue(columns["Group Classification"]["editable"])

        created = backend_server.create_crosswalk_row(
            "non-site-groups",
            {
                "values": {
                    "Axon Group ID": "training-1",
                    "External Group ID": "TRN-1",
                    "Group Name": "BWC Training Cadre",
                    "Group Classification": "Training",
                    "Command Hierarchy Level": "Enterprise",
                    "Reporting Inclusion": "Exclude",
                    "Mapping Status": "Registered non-site",
                    "Review Notes": "Intentionally not tied to a physical site.",
                }
            },
        )
        self.assertEqual(created["rowNumber"], 1)
        self.assertTrue((self.crosswalk_backup_dir / created["backupFileName"]).is_file())

        updated = backend_server.update_crosswalk_row(
            "non-site-groups",
            1,
            {
                "changes": {"Review Notes": "Confirmed non-site training role."},
                "expected": {"Axon Group ID": "training-1"},
            },
        )
        self.assertEqual(updated["row"]["values"]["Review Notes"], "Confirmed non-site training role.")
        listed = backend_server.list_crosswalk("non-site-groups")
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["rows"][0]["values"]["Group Name"], "BWC Training Cadre")

        before_invalid = (self.crosswalk_root / "axon_non_site_group_register_starter.csv").read_bytes()
        with self.assertRaisesRegex(backend_server.UserInputError, "Review Notes"):
            backend_server.update_crosswalk_row(
                "non-site-groups",
                1,
                {"changes": {"Review Notes": ""}},
            )
        self.assertEqual(
            (self.crosswalk_root / "axon_non_site_group_register_starter.csv").read_bytes(),
            before_invalid,
        )

        with self.assertRaises(backend_server.UserInputError):
            backend_server.create_crosswalk_row(
                "device-homes",
                {"values": {"Device Home Name (API)": "Not allowed"}},
            )

    def test_facility_and_office_presence_model_preserves_site_ids_and_validates_links(self):
        summary = backend_server.local_governance_summary()
        self.assertEqual(summary["facilities"]["total"], 0)
        self.assertEqual(summary["officePresences"]["total"], 1)
        self.assertEqual(summary["officePresences"]["unlinked"], 1)
        self.assertFalse(summary["axonWrite"])

        with self.assertRaisesRegex(backend_server.UserInputError, "Host Organization"):
            backend_server.create_crosswalk_row(
                "facility-master",
                {"values": {
                    "Facility ID": "FAC-001",
                    "Facility Name": "Example Shared Facility",
                    "Ownership / Occupancy Type": "Hosted by another federal agency",
                }},
            )

        created = backend_server.create_crosswalk_row(
            "facility-master",
            {"values": {
                "Facility ID": "FAC-001",
                "Facility Name": "Example Shared Facility",
                "Shared Facility": "Yes - mixed",
                "Host Organization": "Partner agency",
                "Ownership / Occupancy Type": "Hosted by another federal agency",
                "Review Notes": "Illustrative test facility.",
            }},
        )
        self.assertEqual(created["row"]["values"]["Validation Status"], "Draft")

        office = backend_server.list_crosswalk("office-presences", page=1, page_size=1)["rows"][0]
        self.assertTrue(office["values"]["Office Location ID"])
        linked = backend_server.update_crosswalk_row(
            "office-presences",
            office["rowNumber"],
            {"changes": {
                "Facility ID": "FAC-001",
                "Facility Link Status": "Linked",
                "Mapping Method": "Reviewed co-location",
                "Confidence": "High",
                "Review Notes": "Facility relationship reviewed for test.",
            }},
        )
        self.assertEqual(linked["row"]["values"]["Facility ID"], "FAC-001")
        summary = backend_server.local_governance_summary()
        self.assertEqual(summary["officePresences"]["linked"], 1)
        self.assertEqual(summary["facilities"]["externallyHosted"], 1)

    def test_tiered_group_master_and_site_relationships_use_observed_ids(self):
        backend_server.create_crosswalk_row(
            "group-master",
            {"values": {"Axon Group ID": "group-root", "Group Name": "TEST Users"}},
        )
        child = backend_server.create_crosswalk_row(
            "group-master",
            {"values": {
                "Axon Group ID": "group-child",
                "Group Name": "TEST Area Alpha Users",
                "Group Purpose": "User assignment",
                "Group Tier": "Primary",
                "Parent Group ID": "group-root",
                "Command Hierarchy Level": "Field office",
                "Organizational Lens": "Not applicable",
                "Component": "Not applicable",
                "Organizational Area": "Area Alpha",
                "Site Relationship": "Office presence",
                "Group Status": "Active",
                "Mapping Status": "Classified",
                "Confidence": "High",
                "Review Notes": "Observed Group ID and reviewed hierarchy.",
            }},
        )
        self.assertEqual(child["row"]["values"]["Group Tier"], "Primary")
        office_id = backend_server.list_crosswalk("office-presences", page=1, page_size=1)["rows"][0]["values"]["Office Location ID"]
        relationship = backend_server.create_crosswalk_row(
            "site-group-relationships",
            {"values": {
                "Office Location ID": office_id,
                "Axon Group ID": "group-child",
                "Relationship Type": "Primary operational",
                "Group Tier": "Primary",
            }},
        )
        self.assertEqual(relationship["row"]["values"]["Mapping Status"], "Pending review")
        with self.assertRaisesRegex(backend_server.UserInputError, "must be unique"):
            backend_server.create_crosswalk_row(
                "site-group-relationships",
                {"values": {
                    "Office Location ID": office_id,
                    "Axon Group ID": "group-child",
                    "Relationship Type": "Primary operational",
                }},
            )

    def test_crosswalk_http_list_and_full_export_do_not_expose_session_credentials(self):
        state = backend_server.SessionState(client_factory=FakeAxonClient)
        state.set_credentials("partner-secret-sentinel", "client-id-sentinel", "client-secret-sentinel")

        class CapturingHandler(backend_server.LocalAxonGeographicHandler):
            def __init__(self, path):
                self.path = path
                self.state = state
                self.captured = None

            def _valid_host(self):
                return True

            def _authorized(self):
                return True

            def _send_json(self, status, payload):
                self.captured = (status, payload)

            def _send_attachment(self, file_path):
                self.captured = (200, file_path.name, file_path.read_bytes())

            def _error(self, status, message):
                self.captured = (status, {"success": False, "error": message})

        try:
            handler = CapturingHandler("/api/crosswalks/device-homes?page=1&pageSize=1")
            handler.do_GET()
            status, payload = handler.captured
            serialized = json.dumps(payload).encode("utf-8")
            self.assertEqual(status, 200)
            self.assertNotIn(b"client-secret-sentinel", serialized)
            self.assertNotIn(b"partner-secret-sentinel", serialized)

            dataset = state.workspace.governance_dataset("device_home_crosswalk_starter")
            authoritative_rows = [dict(row) for row in dataset["rows"]]
            authoritative_rows[0]["Review Notes"] = "SQLite authority marker for export."
            state.workspace.replace_governance_rows(
                "device_home_crosswalk_starter",
                authoritative_rows,
                dataset["revision"],
                "test-export-authority",
                "test",
            )
            stale_projection = (self.crosswalk_root / "device_home_crosswalk_starter.csv").read_bytes()

            handler = CapturingHandler("/api/crosswalks/device-homes/export")
            handler.do_GET()
            status, file_name, exported = handler.captured
            self.assertEqual(status, 200)
            self.assertEqual(file_name, "device_home_crosswalk_starter.csv")
            self.assertNotEqual(exported, stale_projection)
            exported_rows = list(csv.DictReader(exported.decode("utf-8-sig").splitlines()))
            self.assertEqual(exported_rows[0]["Review Notes"], "SQLite authority marker for export.")
            self.assertNotIn(b"client-secret-sentinel", exported)
        finally:
            state.close()


if __name__ == "__main__":
    unittest.main()
