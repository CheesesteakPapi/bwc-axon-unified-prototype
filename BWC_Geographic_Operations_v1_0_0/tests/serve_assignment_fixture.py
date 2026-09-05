"""Serve a temporary synthetic assignment workspace; Ctrl-C cleans up.

From this component: python3 -m tests.serve_assignment_fixture
"""

from tests.test_assignment_views import AssignmentViewsTests
import backend_server


def main():
    fixture = AssignmentViewsTests()
    fixture.setUp()
    state = fixture.fixture()
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
