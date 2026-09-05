"""Isolated, synthetic UI testing server. Never configure tenant credentials."""
import os
import tempfile


def main():
    with tempfile.TemporaryDirectory(prefix="bwc-ux-test-") as folder:
        os.environ["BWC_AXON_DATA_ROOT"] = folder
        os.environ["BWC_SHARED_WORKSPACE_PATH"] = os.path.join(folder, "shared.sqlite3")
        import backend_server
        state = backend_server.SessionState()
        state.workspace.migrate_governance_csvs(backend_server.SUITE_ROOT / "governance_starters")
        backend_server.provisioning_run_payload(state, {
            "title": "Synthetic UX review",
            "provider": "synthetic-test",
            "rows": [{"Email": f"test.person{i}@example.test", "Role": "Prototype User", "Group Name": ""} for i in range(30)],
        })
        server = backend_server.make_server(0, state)
        print(f"http://127.0.0.1:{server.server_address[1]}/?launch={state.local_token}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            state.close()


if __name__ == "__main__":
    main()
