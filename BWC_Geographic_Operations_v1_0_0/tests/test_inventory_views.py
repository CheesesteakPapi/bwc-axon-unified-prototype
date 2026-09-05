from __future__ import annotations

import csv
import http.client
import io
import json
import threading
import unittest
from unittest.mock import patch

from tests import test_backend_server as support
import backend_server


class InventoryViewsTests(unittest.TestCase):
    setUp = support.BackendServerTests.setUp
    tearDown = support.BackendServerTests.tearDown

    def fixture(self, count=605, scope=None):
        state = backend_server.SessionState(client_factory=support.FakeAxonClient)
        self.addCleanup(state.close)
        dataset = state.workspace.governance_dataset("device_home_crosswalk_starter")
        mapping = dict(dataset["rows"][0])
        mapping.update({"Device Home Name (API)": "Example Home Alpha", "Normalized Device Home Key": "example home alpha", "Mapping Status": "Mapped"})
        state.workspace.replace_governance_rows(dataset["dataset"], [mapping], dataset["revision"], "test-mapping", "test")
        devices = [{
            "Axon Device ID": f"TEST-DEVICE-{index:04d}", "Serial Number": f"TEST-SERIAL-{index:04d}",
            "Device Model": "Body 4" if index % 2 == 0 else "Fleet 3",
            "Device Status": "LOST" if index % 3 == 0 else "IN_STOCK",
            "Assigned User ID": "test-user" if index % 2 == 0 else "",
            "Assigned User Name": "Example User" if index % 2 == 0 else "",
            "Device Home Name (API)": "Example Home Alpha",
            "Normalized Device Home Key": "example home alpha",
        } for index in range(count)]
        state.workspace.activate_snapshot("Devices", devices, scope or {"type": "full", "filters": {}})
        return state

    def test_paging_and_search_use_devices_beyond_dashboard_preview_limit(self):
        state = self.fixture()
        self.assertEqual(len(state.dashboard()["inventory"]), 500)
        result = state.inventory_view({"page": ["11"], "pageSize": ["50"]})
        self.assertEqual(result["total"], 605)
        self.assertEqual(result["scopeTotal"], 605)
        self.assertEqual(result["totalPages"], 13)
        self.assertEqual(result["rows"][0]["serialNumber"], "TEST-SERIAL-0500")
        found = state.inventory_view({"search": ["test-serial-0604"]})
        self.assertEqual(found["total"], 1)
        self.assertEqual(found["rows"][0]["deviceId"], "TEST-DEVICE-0604")
        self.assertEqual(state.inventory_view({"page": ["999"]})["page"], 13)
        self.assertEqual(support.FakeAxonClient.instances, [])

    def test_combined_filters_and_export_match_across_all_pages_after_restart(self):
        state = self.fixture()
        state.close()
        restarted = backend_server.SessionState(client_factory=support.FakeAxonClient)
        self.addCleanup(restarted.close)
        query = {"model": ["Body 4"], "disposition": ["Lost"], "assignmentState": ["Assigned"],
                 "deviceHome": ["Example Home Alpha"], "component": ["TEST"], "regionAor": ["Area Alpha"],
                 "exceptionsOnly": ["true"], "pageSize": ["25"], "page": ["2"]}
        result = restarted.inventory_view(query)
        self.assertEqual(result["total"], 101)
        self.assertEqual(len(result["rows"]), 25)
        query["expectedRevision"] = [str(result["workspaceRevision"])]
        exported = restarted.inventory_view(query, export=True)
        rows = list(csv.DictReader(io.StringIO(exported["content"].decode("utf-8"))))
        self.assertEqual(len(rows), 101)
        self.assertEqual(rows[0]["Serial Number"], "TEST-SERIAL-0000")
        self.assertEqual(rows[-1]["Serial Number"], "TEST-SERIAL-0600")
        self.assertTrue(all(row["Mapped AOR"] == "Area Alpha" and row["Data Scope"] == "full" for row in rows))
        self.assertEqual(rows[0]["Devices Snapshot ID"], result["deviceSnapshot"]["snapshotId"])
        self.assertEqual(json.loads(rows[0]["View Filters"])["model"], "Body 4")
        self.assertFalse(exported["content"].startswith(b"\xef\xbb\xbf"))
        self.assertTrue(exported["filename"].endswith("Z.csv"))
        self.assertEqual(restarted.dashboard()["availableDownloads"], [])
        self.assertEqual(support.FakeAxonClient.instances, [])

    def test_full_baseline_remains_selected_after_newer_filtered_snapshot(self):
        state = self.fixture(2, {"type": "filtered", "filters": {"model": "Body 4,Fleet 3"}})
        filtered = state.inventory_view({})
        self.assertEqual(filtered["mode"], "filtered")
        self.assertEqual(filtered["total"], 2)
        full = state.workspace.activate_snapshot("Devices", [{"Axon Device ID": "TEST-FULL", "Serial Number": "TEST-FULL"}])
        state.workspace.activate_snapshot("Devices", [{"Axon Device ID": "TEST-FILTERED"}], {"type": "filtered", "filters": {"model": "Body 4"}})
        result = state.inventory_view({})
        self.assertEqual(result["mode"], "full")
        self.assertEqual(result["deviceSnapshot"]["snapshotId"], full["snapshotId"])
        self.assertEqual(result["rows"][0]["deviceId"], "TEST-FULL")

    def test_export_rejects_stale_revision_and_escapes_spreadsheet_formulas(self):
        state = self.fixture(1)
        old_revision = state.workspace.revision()
        state.workspace.activate_snapshot("Devices", [{"Axon Device ID": "TEST-ID", "Serial Number": '=HYPERLINK("example")', "Assigned User Name": "\t+TEST"}])
        with self.assertRaises(backend_server.RevisionConflict):
            state.inventory_view({"expectedRevision": [str(old_revision)]}, export=True)
        exported = state.inventory_view({"expectedRevision": [str(state.workspace.revision())]}, export=True)
        rows = list(csv.DictReader(io.StringIO(exported["content"].decode("utf-8"))))
        self.assertTrue(rows[0]["Serial Number"].startswith("'="))
        self.assertTrue(rows[0]["Assigned User"].startswith("'\t+"))
        for query in ({"unknown": ["x"]}, {"pageSize": ["201"]}, {"model": ["a", "b"]}, {"exceptionsOnly": ["yes"]}):
            with self.subTest(query=query), self.assertRaises(backend_server.UserInputError):
                state.inventory_view(query)
        with self.assertRaises(backend_server.UserInputError):
            state.inventory_view({}, export=True)

    def test_unavailable_devices_and_concurrent_governance_change(self):
        state = backend_server.SessionState(client_factory=support.FakeAxonClient)
        self.addCleanup(state.close)
        state.workspace.activate_snapshot("Users", [{"Email": "example@example.test"}])
        result = state.inventory_view({})
        self.assertEqual(result["mode"], "unavailable")
        self.assertIsNone(result["scopeTotal"])
        with self.assertRaises(backend_server.UserInputError):
            state.inventory_view({"expectedRevision": [str(result["workspaceRevision"])]}, export=True)
        state.workspace.activate_snapshot("Devices", [{"Axon Device ID": "TEST-ID"}])
        original = backend_server.build_dashboard_payload

        def change_during_mapping(*args, **kwargs):
            result = original(*args, **kwargs)
            dataset = state.workspace.governance_dataset("device_home_crosswalk_starter")
            state.workspace.replace_governance_rows(dataset["dataset"], dataset["rows"], dataset["revision"], "test-change", "test")
            return result

        with patch.object(backend_server, "build_dashboard_payload", side_effect=change_during_mapping):
            with self.assertRaises(backend_server.RevisionConflict):
                state.inventory_view({})

    def test_inventory_http_routes_require_session_and_bind_export_revision(self):
        state = self.fixture(2)
        server = backend_server.make_server(0, state)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            connection.request("GET", "/api/inventory")
            response = connection.getresponse(); response.read()
            self.assertEqual(response.status, 401)
            connection.request("GET", f"/?launch={state.local_token}")
            response = connection.getresponse(); response.read()
            headers = {"Cookie": response.getheader("Set-Cookie").split(";", 1)[0]}
            connection.request("GET", "/api/inventory?model=Body%204", headers=headers)
            response = connection.getresponse(); payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["total"], 1)
            connection.request("GET", f"/api/inventory/export?model=Body%204&expectedRevision={payload['workspaceRevision']}", headers=headers)
            response = connection.getresponse(); content = response.read()
            self.assertEqual(response.status, 200)
            self.assertIn("attachment;", response.getheader("Content-Disposition"))
            self.assertEqual(len(list(csv.DictReader(io.StringIO(content.decode("utf-8"))))), 1)
            connection.request("GET", "/api/inventory/export?expectedRevision=0", headers=headers)
            response = connection.getresponse(); response.read()
            self.assertEqual(response.status, 409)
        finally:
            connection.close(); server.shutdown(); server.server_close(); worker.join(5)
