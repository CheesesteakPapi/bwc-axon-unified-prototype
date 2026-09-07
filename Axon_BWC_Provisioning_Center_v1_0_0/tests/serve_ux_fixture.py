"""Isolated, synthetic UI testing server. Never configure tenant credentials."""
import os
import argparse
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-profile", action="store_true", help="Synthetic local credential-file UI check; never contacts Axon.")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="bwc-ux-test-") as folder:
        os.environ["BWC_AXON_DATA_ROOT"] = folder
        os.environ["BWC_SHARED_WORKSPACE_PATH"] = os.path.join(folder, "shared.sqlite3")
        import backend_server
        state = backend_server.SessionState()
        state.workspace.migrate_governance_csvs(backend_server.SUITE_ROOT / "governance_starters")
        if args.test_profile:
            from local_test_credentials import credential_path, write_profile
            os.environ["BWC_TEST_CREDENTIALS_FILE"] = ""
            backend_server.save_public_config({"agencyBaseUrl": "https://test-agency.evidence.com", "timeoutSeconds": 90})
            write_profile(credential_path(), {"version": 1, "testingOnly": True,
                "agencyBaseUrl": "https://test-agency.evidence.com", "partnerId": "SYNTHETIC-PARTNER",
                "clientId": "synthetic-client", "clientSecret": "synthetic-secret"})
            state.load_test_credentials("https://test-agency.evidence.com")
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
