"""Run a temporary, synthetic 605-device workspace for browser verification.

From this component: python3 -m tests.serve_inventory_fixture
The printed URL is for this temporary local test session only. Ctrl-C cleans up.
"""

from tests.test_inventory_views import InventoryViewsTests
import backend_server


def main():
    fixture = InventoryViewsTests()
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
