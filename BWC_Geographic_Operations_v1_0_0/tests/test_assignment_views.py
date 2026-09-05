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


class AssignmentViewsTests(unittest.TestCase):
    setUp = support.BackendServerTests.setUp
    tearDown = support.BackendServerTests.tearDown

    def fixture(self, count=605, devices=True, filtered=False):
        state = backend_server.SessionState(client_factory=support.FakeAxonClient)
        self.addCleanup(state.close)
        users = [{"Axon User ID": f"TEST-USER-{index:04d}", "External ID": f"test-{index:04d}@example.test",
                  "First Name": "Example", "Last Name": f"User {index:04d}",
                  "Role": "Prototype User" if index % 2 == 0 else "Prototype Supervisor"} for index in range(count)]
        records = [{"Axon Device ID": f"TEST-DEVICE-{index:04d}-{slot}", "Serial Number": f"TEST-SERIAL-{index:04d}-{slot}",
                    "Device Model": "Body 4" if slot == 0 else "Fleet 3", "Device Status": "LOST" if slot == 0 else "ASSIGNED",
                    "Assigned User ID": f"TEST-USER-{index:04d}", "Assigned User Name": "Same display name",
                    "Device Home Name (API)": "Example Home Alpha"}
                   for index in range(count) for slot in range(index % 4)]
        state.workspace.activate_snapshot("Users", users)
        if devices:
            state.workspace.activate_snapshot("Devices", records,
                {"type": "filtered", "filters": {"model": "Body 4,Fleet 3"}} if filtered else {"type": "full", "filters": {}})
        return state

    def detail_query(self, state, user="TEST-USER-0003", **extra):
        return {"userId": [user], "expectedRevision": [str(state.workspace.revision())], **extra}

    def test_complete_user_paging_and_count_filters_keep_zero_separate(self):
        state = self.fixture()
        self.assertEqual(len(state.dashboard()["assignments"]), 500)
        page = state.assignment_view({"page": ["11"]})
        self.assertEqual(page["total"], 605)
        self.assertEqual(page["rows"][0]["userId"], "TEST-USER-0500")
        for choice, total in [("0", 152), ("1", 151), ("2", 151), ("3+", 151), ("unavailable", 0)]:
            self.assertEqual(state.assignment_view({"deviceCount": [choice]})["total"], total)
        found = state.assignment_view({"search": ["user 0604"]})
        self.assertEqual(found["total"], 1)
        self.assertEqual(found["rows"][0]["deviceCount"], 0)
        self.assertEqual(support.FakeAxonClient.instances, [])

    def test_details_join_exact_user_id_and_page_exact_serials(self):
        state = self.fixture(4)
        detail = state.assignment_view(self.detail_query(state, pageSize=["2"], page=["2"]), detail=True)
        self.assertEqual(detail["total"], 3)
        self.assertEqual(detail["totalPages"], 2)
        self.assertEqual([row["serialNumber"] for row in detail["rows"]], ["TEST-SERIAL-0003-2"])
        first = state.assignment_view(self.detail_query(state), detail=True)
        self.assertEqual(first["rows"][0]["disposition"], "Lost")
        self.assertTrue(all(row["assignedUserId"] == "TEST-USER-0003" for row in first["rows"]))
        self.assertNotIn("TEST-SERIAL-0001-0", json.dumps(first))
        zero = state.assignment_view(self.detail_query(state, "TEST-USER-0000"), detail=True)
        self.assertEqual(zero["total"], 0)
        self.assertEqual(zero["rows"], [])

    def test_users_only_export_and_detail_preserve_unavailable_counts(self):
        state = self.fixture(4, devices=False)
        view = state.assignment_view({})
        self.assertEqual(view["deviceScope"], "unavailable")
        self.assertTrue(all(row["deviceCount"] is None for row in view["rows"]))
        self.assertEqual(state.assignment_view({"deviceCount": ["0"]})["total"], 0)
        self.assertEqual(state.assignment_view({"deviceCount": ["unavailable"]})["total"], 4)
        self.assertIsNone(state.assignment_view(self.detail_query(state), detail=True)["total"])
        exported = state.assignment_view({"expectedRevision": [str(view["workspaceRevision"])]}, export=True)
        records = list(csv.DictReader(io.StringIO(exported["content"].decode())))
        self.assertEqual(records[0]["Device Count"], "Unavailable")
        self.assertEqual(records[0]["Devices Snapshot ID"], "")

    def test_filtered_scope_and_full_precedence_apply_to_counts_and_details(self):
        state = self.fixture(4, filtered=True)
        result = state.assignment_view(self.detail_query(state), detail=True)
        self.assertEqual(result["deviceScope"], "filtered")
        self.assertEqual(result["total"], 3)
        full = state.workspace.activate_snapshot("Devices", [])
        state.workspace.activate_snapshot("Devices", [{"Assigned User ID": "TEST-USER-0003"}], {"type": "filtered", "filters": {"model": "Body 4"}})
        result = state.assignment_view(self.detail_query(state), detail=True)
        self.assertEqual(result["deviceScope"], "full")
        self.assertEqual(result["deviceSnapshot"]["snapshotId"], full["snapshotId"])
        self.assertEqual(result["total"], 0)

    def test_missing_users_are_unavailable_but_empty_users_are_a_valid_snapshot(self):
        state = backend_server.SessionState(client_factory=support.FakeAxonClient)
        self.addCleanup(state.close)
        state.workspace.activate_snapshot("Devices", [])
        result = state.assignment_view({})
        self.assertIsNone(result["userSnapshot"])
        self.assertIsNone(result["scopeTotal"])
        with self.assertRaises(backend_server.UserInputError):
            state.assignment_view({"expectedRevision": [str(result["workspaceRevision"])]}, export=True)
        state.workspace.activate_snapshot("Users", [])
        result = state.assignment_view({})
        self.assertEqual(result["scopeTotal"], 0)
        exported = state.assignment_view({"expectedRevision": [str(result["workspaceRevision"])]}, export=True)
        self.assertEqual(list(csv.DictReader(io.StringIO(exported["content"].decode()))), [])
        self.assertEqual(support.FakeAxonClient.instances, [])

    def test_role_count_export_covers_all_pages_after_restart_with_provenance(self):
        state = self.fixture()
        state.close()
        state = backend_server.SessionState(client_factory=support.FakeAxonClient)
        self.addCleanup(state.close)
        query = {"role": ["Prototype Supervisor"], "deviceCount": ["3+"], "page": ["2"], "pageSize": ["25"]}
        view = state.assignment_view(query)
        self.assertEqual(view["total"], 151)
        self.assertEqual(len(view["rows"]), 25)
        result = state.assignment_view({**query, "expectedRevision": [str(view["workspaceRevision"])]}, export=True)
        records = list(csv.DictReader(io.StringIO(result["content"].decode())))
        self.assertEqual(len(records), 151)
        self.assertEqual(records[-1]["User ID"], "TEST-USER-0603")
        self.assertEqual(records[0]["Users Snapshot ID"], view["userSnapshot"]["snapshotId"])
        self.assertEqual(records[0]["Devices Snapshot ID"], view["deviceSnapshot"]["snapshotId"])
        self.assertEqual(json.loads(records[0]["View Filters"])["deviceCount"], "3+")
        self.assertFalse(result["content"].startswith(b"\xef\xbb\xbf"))
        self.assertRegex(result["filename"], r"^BWC_assignments_full_R\d+_\d+T\d+Z.csv$")
        self.assertEqual(support.FakeAxonClient.instances, [])

    def test_invalid_identity_never_generates_zero_or_ambiguous_device_links(self):
        state = self.fixture(4)
        users = [{"Axon User ID": "", "First Name": "=TEST()"},
                 {"Axon User ID": "TEST-USER-0003", "First Name": "Example duplicate A"},
                 {"Axon User ID": "TEST-USER-0003", "First Name": "Example duplicate B"}]
        state.workspace.activate_snapshot("Users", users)
        result = state.assignment_view({})
        self.assertTrue(all(row["deviceCount"] is None for row in result["rows"]))
        with self.assertRaises(backend_server.UserInputError):
            state.assignment_view(self.detail_query(state), detail=True)
        exported = state.assignment_view({"expectedRevision": [str(result["workspaceRevision"])]}, export=True)
        self.assertIn("'=TEST()", exported["content"].decode())

    def test_stale_revisions_and_concurrent_governance_changes_are_rejected(self):
        state = self.fixture(4)
        stale = self.detail_query(state)
        state.workspace.activate_snapshot("Devices", [])
        with self.assertRaises(backend_server.RevisionConflict):
            state.assignment_view(stale, detail=True)
        with self.assertRaises(backend_server.RevisionConflict):
            state.assignment_view({"expectedRevision": stale["expectedRevision"]}, export=True)
        original = backend_server.build_dashboard_payload
        def change_during_mapping(*args, **kwargs):
            result = original(*args, **kwargs)
            state.workspace.activate_snapshot("Devices", [])
            return result
        with patch.object(backend_server, "build_dashboard_payload", side_effect=change_during_mapping):
            with self.assertRaises(backend_server.RevisionConflict):
                state.assignment_view({})

    def test_assignment_http_routes_require_session_and_validate_queries(self):
        state = self.fixture(4)
        server = backend_server.make_server(0, state)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            for route in ("/api/assignments", "/api/assignments/devices", "/api/assignments/export"):
                connection.request("GET", route)
                response = connection.getresponse(); response.read()
                self.assertEqual(response.status, 401)
            connection.request("GET", f"/?launch={state.local_token}")
            response = connection.getresponse(); response.read()
            headers = {"Cookie": response.getheader("Set-Cookie").split(";", 1)[0]}
            for route, status in [("/api/assignments?deviceCount=3%2B", 200), ("/api/assignments?deviceCount=4", 400),
                                  ("/api/assignments?role=x&role=y", 400), ("/api/assignments?unknown=x", 400),
                                  ("/api/assignments/export", 400), ("/api/assignments/devices?userId=TEST-USER-0003", 400),
                                  ("/api/assignments/devices?userId=TEST-USER-0003&expectedRevision=0", 409),
                                  (f"/api/assignments/devices?userId=TEST-USER-0003&expectedRevision={state.workspace.revision()}", 200),
                                  (f"/api/assignments/export?expectedRevision={state.workspace.revision()}", 200)]:
                connection.request("GET", route, headers=headers)
                response = connection.getresponse(); content = response.read()
                self.assertEqual(response.status, status, content)
        finally:
            connection.close(); server.shutdown(); server.server_close(); worker.join(5)
