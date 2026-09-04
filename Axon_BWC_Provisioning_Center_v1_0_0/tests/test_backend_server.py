import atexit
import csv
import http.client
import json
import os
import shutil
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

_MODULE_RUNTIME = tempfile.mkdtemp(prefix="bwc-provision-test-runtime-")
atexit.register(shutil.rmtree, _MODULE_RUNTIME, ignore_errors=True)
os.environ["BWC_AXON_DATA_ROOT"] = _MODULE_RUNTIME

import backend_server
from backend_server import SessionState, UserInputError, execute_operation


USER_CSV = (
    "EXTERNAL_ID,EMAIL,BADGE_NUMBER,FIRST_NAME,LAST_NAME,STATUS,USERNAME,ROLE,"
    "SUPERVISOR_EMAIL,LOCATION,EVIDENCE_GROUP_EXT_ID,PHONE,RANK\r\n"
    "EMP-001,alex@example.gov,B-001,Alex,Example,Active,alex@example.gov,Axon User,"
    ",HQ,GRP-HQ,,Officer\r\n"
)

NEW_USER_ROW = (
    "EMP-002,new.user@example.gov,B-002,New,User,Active,new.user@example.gov,Axon User,"
    ",HQ,GRP-HQ,,Officer\r\n"
)

INVALID_USER_ROW = (
    "EMP-003,not-an-email,B-003,Bad,Email,Active,not-an-email,Axon User,"
    ",HQ,GRP-HQ,,Officer\r\n"
)

SNAPSHOT_CSV = (
    "Axon User ID,External ID,Badge ID,First Name,Last Name,Email,User Status,Role,"
    "Last Activity,Source Updated At,Last Sync At,Sync Status\r\n"
    "AX-1,EMP-001,B-001,Alex,Example,alex@example.gov,Active,Axon User,,,,Synced\r\n"
)


class BackendServerTests(unittest.TestCase):
    def setUp(self):
        self.audit_temp = tempfile.TemporaryDirectory()
        self.audit_env = mock.patch.dict(os.environ, {"BWC_AXON_DATA_ROOT": self.audit_temp.name})
        self.audit_env.start()
        self.state = SessionState()

    def tearDown(self):
        self.state.close()
        self.audit_env.stop()
        self.audit_temp.cleanup()

    def upload(self, name, content):
        handle, _ = self.state.save_upload(name, content.encode("utf-8"))
        return handle

    def preview_users(self, user_handle, snapshot_handle):
        return execute_operation(
            self.state,
            {
                "operation": "preview-users",
                "files": {
                    "User import CSV": user_handle,
                    "Current Users snapshot": snapshot_handle,
                },
                "fields": {},
            },
        )

    def download_path(self, download):
        return self.state.resolve_download(download["url"].rsplit("/", 1)[-1])

    def test_session_status_never_returns_secrets(self):
        self.state.set_credentials("AGENCY-1234", "client-sensitive", "secret-sensitive")
        status = self.state.session_status()
        rendered = json.dumps(status)
        self.assertTrue(status["configured"])
        self.assertNotIn("client-sensitive", rendered)
        self.assertNotIn("secret-sensitive", rendered)
        self.assertNotIn("AGENCY-1234", rendered)
        self.assertEqual(status["partnerHint"], "…1234")

    def test_credentials_are_cleared(self):
        self.state.set_credentials("AGENCY-1234", "client", "secret")
        self.state.clear_credentials()
        self.assertFalse(self.state.session_status()["configured"])
        with self.assertRaises(UserInputError):
            self.state.credential_env()

    def test_shared_refresh_requires_process_credentials(self):
        with self.assertRaisesRegex(UserInputError, "session credentials"):
            self.state.start_shared_refresh("Users")

    def test_sync_config_materializes_current_shared_governance_rows(self):
        self.state.workspace.migrate_governance_csvs(backend_server.SUITE_ROOT / "governance_starters")
        dataset = self.state.workspace.governance_dataset("device_home_crosswalk_starter")
        rows = [dict(row) for row in dataset["rows"]]
        rows[0]["Review Notes"] = "SQLite authority marker for provisioning sync."
        self.state.workspace.replace_governance_rows(
            "device_home_crosswalk_starter",
            rows,
            dataset["revision"],
            "test-sync-config",
            "test",
        )
        config, _ = backend_server.load_config()
        status_path = backend_server.governance_root() / "device_status_map.csv"
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(
            "Raw Axon Device Status,Reporting State,Validated By,Validated Date,Notes\n"
            "Assigned,Reviewed Operational,Test,2026-09-04,Current file-governed value.\n",
            encoding="utf-8",
        )

        config_path = backend_server.materialize_sync_config(self.state, config, "test-authority")

        materialized = json.loads(config_path.read_text(encoding="utf-8"))
        projection_path = Path(materialized["device_home_crosswalk_csv"])
        with projection_path.open("r", encoding="utf-8-sig", newline="") as handle:
            projected_rows = list(csv.DictReader(handle))
        self.assertEqual(
            projected_rows[0]["Review Notes"],
            "SQLite authority marker for provisioning sync.",
        )
        self.assertTrue(projection_path.is_relative_to(self.state.root))
        materialized_status_path = Path(materialized["device_status_map_csv"])
        self.assertEqual(materialized_status_path, status_path)
        self.assertIn("Reviewed Operational", materialized_status_path.read_text(encoding="utf-8"))
        self.assertFalse(materialized_status_path.is_relative_to(self.state.root))

    def test_auto_port_uses_next_loopback_port_when_requested_port_is_busy(self):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        requested_port = blocker.getsockname()[1]
        server = None
        try:
            server = backend_server.make_server(requested_port, self.state, auto_port=True)
            self.assertNotEqual(server.server_address[1], requested_port)
            self.assertGreater(server.server_address[1], 0)
        finally:
            if server:
                server.server_close()
            blocker.close()

    def test_loopback_api_requires_per_launch_session_cookie(self):
        server = backend_server.make_server(0, self.state)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = int(server.server_address[1])
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", "/api/health")
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 401)

            connection.request("GET", f"/?launch={self.state.local_token}")
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
            self.assertTrue(payload["productionMode"])

            connection.request("GET", "/api/catalogs/groups", headers={"Cookie": cookie.split(";", 1)[0]})
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertIsInstance(payload["groups"], list)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_actual_user_preview_uses_selected_session_files(self):
        user_handle = self.upload("users.csv", USER_CSV)
        snapshot_handle = self.upload("axon_users.csv", SNAPSHOT_CSV)
        result = self.preview_users(user_handle, snapshot_handle)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["rowCount"], 1)
        self.assertEqual(result["data"]["matchCount"], 1)
        self.assertEqual(result["data"]["rows"][0]["type"], "match")
        self.assertTrue(result["data"]["rows"][0]["existingMatch"])
        self.assertFalse(result["data"]["rows"][0]["blocked"])
        self.assertTrue(result["data"]["previewToken"])

    def test_preview_exports_separate_new_and_matched_csvs(self):
        header = USER_CSV.splitlines(keepends=True)[0]
        existing_row = "".join(USER_CSV.splitlines(keepends=True)[1:])
        user_handle = self.upload("bulk_users.csv", header + existing_row + NEW_USER_ROW)
        snapshot_handle = self.upload("axon_users.csv", SNAPSHOT_CSV)

        result = self.preview_users(user_handle, snapshot_handle)

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["createCount"], 1)
        self.assertEqual(result["data"]["matchCount"], 1)
        self.assertEqual({item["kind"] for item in result["downloads"]}, {"newAccounts", "matchedAccounts"})
        self.assertEqual(
            {item["kind"]: item["rowCount"] for item in result["downloads"]},
            {"newAccounts": 1, "matchedAccounts": 1},
        )
        downloads = {item["kind"]: self.download_path(item) for item in result["downloads"]}
        self.assertIn("new.user@example.gov", downloads["newAccounts"].read_text(encoding="utf-8-sig"))
        self.assertNotIn("alex@example.gov", downloads["newAccounts"].read_text(encoding="utf-8-sig"))
        self.assertIn("alex@example.gov", downloads["matchedAccounts"].read_text(encoding="utf-8-sig"))
        self.assertNotIn("new.user@example.gov", downloads["matchedAccounts"].read_text(encoding="utf-8-sig"))

    def test_every_duplicate_participant_is_a_blocker(self):
        header = USER_CSV.splitlines(keepends=True)[0]
        duplicate_rows = (
            "EMP-010,duplicate@example.gov,B-010,First,Duplicate,Active,first@example.gov,Axon User,,HQ,GRP-HQ,,Officer\r\n"
            "EMP-011,duplicate@example.gov,B-011,Second,Duplicate,Active,second@example.gov,Axon User,,HQ,GRP-HQ,,Officer\r\n"
        )
        user_handle = self.upload("duplicates.csv", header + duplicate_rows)
        snapshot_handle = self.upload("axon_users.csv", SNAPSHOT_CSV)

        result = self.preview_users(user_handle, snapshot_handle)

        self.assertFalse(result["success"])
        self.assertEqual(result["data"]["blockerCount"], 2)
        self.assertTrue(all(row["blocked"] for row in result["data"]["rows"]))
        self.assertTrue(all("Duplicate EMAIL" in " ".join(row["blockers"]) for row in result["data"]["rows"]))
        new_download = next(item for item in result["downloads"] if item["kind"] == "newAccounts")
        with self.download_path(new_download).open("r", newline="", encoding="utf-8-sig") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 0)

    def test_prepare_user_files_removes_blockers_and_matches_without_changing_source(self):
        header = USER_CSV.splitlines(keepends=True)[0]
        existing_row = "".join(USER_CSV.splitlines(keepends=True)[1:])
        source = header + existing_row + NEW_USER_ROW + INVALID_USER_ROW
        user_handle = self.upload("mixed_users.csv", source)
        snapshot_handle = self.upload("axon_users.csv", SNAPSHOT_CSV)
        source_path = self.state.resolve_upload(user_handle)
        before = source_path.read_bytes()
        preview = self.preview_users(user_handle, snapshot_handle)

        result = execute_operation(
            self.state,
            {
                "operation": "prepare-user-files",
                "files": {
                    "User import CSV": user_handle,
                    "Current Users snapshot": snapshot_handle,
                },
                "fields": {},
                "previewToken": preview["data"]["previewToken"],
                "removeBlockers": True,
                "removeMatches": True,
            },
        )

        self.assertTrue(result["success"])
        self.assertEqual(source_path.read_bytes(), before)
        self.assertTrue(result["data"]["originalUnchanged"])
        self.assertEqual(result["data"]["removedRowCount"], 2)
        self.assertEqual(result["data"]["removedBlockerCount"], 1)
        self.assertEqual(result["data"]["removedMatchCount"], 1)
        self.assertEqual(result["data"]["cleanRowCount"], 1)
        clean_preview = result["data"]["preview"]
        self.assertEqual(clean_preview["rowCount"], 1)
        self.assertEqual(clean_preview["matchCount"], 0)
        self.assertEqual(clean_preview["blockerCount"], 0)
        session_path = self.state.resolve_upload(result["data"]["sessionFile"]["handle"])
        clean_text = session_path.read_text(encoding="utf-8-sig")
        self.assertIn("new.user@example.gov", clean_text)
        self.assertNotIn("alex@example.gov", clean_text)
        self.assertNotIn("not-an-email", clean_text)
        self.assertEqual(
            {item["kind"] for item in result["downloads"]},
            {"newAccounts", "matchedAccounts", "cleanCopy"},
        )
        self.assertEqual(
            next(item["rowCount"] for item in result["downloads"] if item["kind"] == "cleanCopy"),
            1,
        )

    def test_prepare_user_files_refuses_structural_header_errors(self):
        broken = "EXTERNAL_ID,EMAIL\r\nEMP-1,user@example.gov\r\n"
        user_handle = self.upload("broken.csv", broken)
        snapshot_handle = self.upload("axon_users.csv", SNAPSHOT_CSV)
        preview = self.preview_users(user_handle, snapshot_handle)
        self.assertTrue(preview["data"]["fileErrors"])

        with self.assertRaisesRegex(UserInputError, "structural errors"):
            execute_operation(
                self.state,
                {
                    "operation": "prepare-user-files",
                    "files": {
                        "User import CSV": user_handle,
                        "Current Users snapshot": snapshot_handle,
                    },
                    "fields": {},
                    "previewToken": preview["data"]["previewToken"],
                },
            )

    def test_allow_updates_requires_latest_preview_and_exact_match_count(self):
        user_handle = self.upload("users.csv", USER_CSV)
        snapshot_handle = self.upload("axon_users.csv", SNAPSHOT_CSV)
        self.state.set_credentials("AGENCY-1234", "client", "secret")
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config = json.loads(backend_server.CONFIG_EXAMPLE_PATH.read_text(encoding="utf-8"))
            config["agency_base_url"] = "https://agency.example.gov"
            config["provisioning"]["write_operations_enabled"] = True
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with mock.patch.object(backend_server, "CONFIG_PATH", config_path):
                first_preview = self.preview_users(user_handle, snapshot_handle)
                latest_preview = self.preview_users(user_handle, snapshot_handle)
                base_body = {
                    "operation": "submit-users",
                    "files": {
                        "User import CSV": user_handle,
                        "Current Users snapshot": snapshot_handle,
                    },
                    "fields": {},
                    "allowUpdates": True,
                    "approvedMatchCount": 1,
                    "confirmWrite": True,
                    "confirmAgency": "AGENCY-1234",
                }
                with self.assertRaisesRegex(UserInputError, "Preview Users again"):
                    execute_operation(
                        self.state,
                        {**base_body, "previewToken": first_preview["data"]["previewToken"]},
                    )
                with self.assertRaisesRegex(UserInputError, "does not match"):
                    execute_operation(
                        self.state,
                        {
                            **base_body,
                            "previewToken": latest_preview["data"]["previewToken"],
                            "approvedMatchCount": 2,
                        },
                    )
                completed = mock.Mock(returncode=0, stdout="Submitted")
                with mock.patch.object(backend_server.subprocess, "run", return_value=completed) as run:
                    result = execute_operation(
                        self.state,
                        {**base_body, "previewToken": latest_preview["data"]["previewToken"]},
                    )
                self.assertTrue(result["success"])
                self.assertIn("--allow-updates", run.call_args.args[0])

    def test_write_confirmation_must_match_credential_agency_before_subprocess(self):
        user_handle = self.upload("users.csv", USER_CSV)
        snapshot_handle = self.upload("axon_users.csv", SNAPSHOT_CSV)
        self.state.set_credentials("AGENCY-1234", "client", "secret")
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config = json.loads(backend_server.CONFIG_EXAMPLE_PATH.read_text(encoding="utf-8"))
            config["agency_base_url"] = "https://agency.example.gov"
            config["provisioning"]["write_operations_enabled"] = True
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with mock.patch.object(backend_server, "CONFIG_PATH", config_path):
                with self.assertRaisesRegex(UserInputError, "does not match"):
                    execute_operation(
                        self.state,
                        {
                            "operation": "submit-users",
                            "files": {
                                "User import CSV": user_handle,
                                "Current Users snapshot": snapshot_handle,
                            },
                            "fields": {},
                            "confirmWrite": True,
                            "confirmAgency": "WRONG-AGENCY",
                        },
                    )

    def test_unknown_upload_handle_is_rejected(self):
        with self.assertRaisesRegex(UserInputError, "missing"):
            self.state.resolve_upload("not-a-real-handle")


if __name__ == "__main__":
    unittest.main()
