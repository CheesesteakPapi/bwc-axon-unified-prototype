"""Serve a temporary synthetic assignment workspace; Ctrl-C cleans up.

From this component: python3 -m tests.serve_assignment_fixture
"""

from tests.test_assignment_views import AssignmentViewsTests
import backend_server


def main():
    fixture = AssignmentViewsTests()
    fixture.setUp()
    backend_server.initialize_governance_working_files()
    state = fixture.fixture()
    state.workspace.activate_snapshot("DeviceHomes", [{
        "Device Home Name (API)": "Synthetic Review Home",
        "Normalized Device Home Key": "synthetic review home",
    }])
    state.workspace.activate_snapshot("Groups", [{
        "Axon Group ID": "synthetic-review-group",
        "External Group ID": "SYNTHETIC-REVIEW",
        "Group Name": "Synthetic Review Group",
    }])
    server = backend_server.make_server(0, state)
    print(f"http://127.0.0.1:{server.server_address[1]}/?launch={state.local_token}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        fixture.doCleanups()
        fixture.tearDown()


if __name__ == "__main__":
    main()
