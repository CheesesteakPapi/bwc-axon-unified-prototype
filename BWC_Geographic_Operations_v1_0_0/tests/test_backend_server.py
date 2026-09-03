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
            return {"data": [
                {"id": "d-1", "attributes": {"serial": "DEMO-SN-1", "model": "Body 4", "status2": "ASSIGNED"}, "relationships": {"owner": {"data": {"id": "u-1"}}, "deviceHome": {"data": {"attributes": {"name": "Example Home Alpha"}}}}},
                {"id": "d-2", "attributes": {"serial": "DEMO-SN-2", "model": "Body 4", "status2": "IN_STOCK", "deviceHome": "Example Home Alpha"}, "relationships": {"owner": {"data": {}}, "deviceHome": {"data": {"attributes": {"name": "Example Home Alpha"}}}}},
                {"id": "d-3", "attributes": {"serial": "SN-3", "model": "Fleet 3", "status2": "LOST"}, "relationships": {"owner": {"data": {"id": "u-2"}}, "deviceHome": {"data": {"attributes": {"name": "Guam"}}}}},
            ]}
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
            self.assertEqual(result["receivedRecords"], 3)
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
            self.assertIsNotNone(state.resolve_download("devices"))
            self.assertIsNotNone(state.resolve_download("summary"))
            self.assertIsNotNone(state.resolve_download("assignments"))
            self.assertIsNotNone(state.resolve_download("device-status"))
            self.assertIsNotNone(state.resolve_download("exceptions"))
        finally:
            state.close()

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

            handler = CapturingHandler("/api/crosswalks/device-homes/export")
            handler.do_GET()
            status, file_name, exported = handler.captured
            self.assertEqual(status, 200)
            self.assertEqual(file_name, "device_home_crosswalk_starter.csv")
            self.assertEqual(exported, (self.crosswalk_root / "device_home_crosswalk_starter.csv").read_bytes())
            self.assertNotIn(b"client-secret-sentinel", exported)
        finally:
            state.close()


if __name__ == "__main__":
    unittest.main()
