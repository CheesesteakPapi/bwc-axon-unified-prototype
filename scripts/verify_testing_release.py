#!/usr/bin/env python3
"""Extract and smoke-test a release using isolated synthetic local storage."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SMOKE = r'''
import http.client, json, os, socket, threading
import backend_server as backend
if hasattr(backend, "initialize_governance_working_files"):
    backend.initialize_governance_working_files()
state = backend.SessionState()
held = socket.socket()
held.bind(("127.0.0.1", 0))
held.listen()
occupied = held.getsockname()[1]
server = backend.make_server(occupied, state, auto_port=True)
assert server.server_address[1] != occupied
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
try:
    connection.request("GET", "/api/health")
    response = connection.getresponse()
    response.read()
    assert response.status == 401
    connection.request("GET", "/?launch=" + state.local_token)
    response = connection.getresponse()
    response.read()
    assert response.status == 303
    cookie = response.getheader("Set-Cookie").split(";", 1)[0]
    connection.request("GET", "/api/health", headers={"Cookie": cookie})
    response = connection.getresponse()
    payload = json.loads(response.read())
    assert response.status == 200 and backend.VERSION == os.environ["BWC_EXPECTED_RELEASE_VERSION"]
    connection.request("GET", "/", headers={"Cookie": cookie})
    response = connection.getresponse()
    html = response.read().decode()
    assert response.status == 200 and "/assets/" in html
    print("PASS: occupied-port fallback, token launch, authenticated health and bundled UI")
finally:
    connection.close()
    server.shutdown()
    server.server_close()
    held.close()
    state.close()
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="bwc32-release-") as folder:
        target = Path(folder).resolve()
        with zipfile.ZipFile(args.archive) as archive:
            assert archive.testzip() is None
            for name in archive.namelist():
                path = target / name
                if not path.resolve().is_relative_to(target) or not name.startswith("BWC32/"):
                    raise SystemExit("Unsafe archive member")
            archive.extractall(target)
            manifest = json.loads(archive.read("BWC32/RELEASE_MANIFEST.json"))
            for row in manifest["files"]:
                data = (target / "BWC32" / row["path"]).read_bytes()
                assert hashlib.sha256(data).hexdigest() == row["sha256"]
        root = target / "BWC32"
        for path in root.rglob("*.py"):
            compile(path.read_bytes(), str(path.relative_to(root)), "exec")
        env = {**os.environ, "BWC_EXPECTED_RELEASE_VERSION": manifest["version"], "BWC_AXON_DATA_ROOT": str(target / "runtime"),
               "BWC_SHARED_WORKSPACE_PATH": str(target / "runtime/shared/shared_workspace.sqlite3")}
        # Source setup only; no tenant calls or browser launch.
        if sys.platform == "darwin":
            subprocess.run(["bash", str(root / "Setup-BWC-Prototype-macOS.command")], cwd=root, env=env, check=True)
        for component in ("Axon_BWC_Provisioning_Center_v1_0_0", "BWC_Geographic_Operations_v1_0_0"):
            subprocess.run([sys.executable, "-c", SMOKE], cwd=root / component, env=env, check=True, timeout=30)
        print("PASS: archive hashes, safe extraction, Python compile and isolated component smoke tests")


if __name__ == "__main__":
    main()
