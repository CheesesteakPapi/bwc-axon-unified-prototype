#!/bin/bash
set -euo pipefail
BWC_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$BWC_ROOT"
echo "BWC Axon V3.2.0 — source prototype, not a signed desktop release"
python3 -c "import sys; assert sys.version_info >= (3,11), 'Approved Python 3.11+ is required'"
if [ ! -x "$BWC_ROOT/.venv/bin/python" ]; then
  python3 -m venv "$BWC_ROOT/.venv"
fi
"$BWC_ROOT/.venv/bin/python" -m pip install --no-index --disable-pip-version-check --require-hashes -r "$BWC_ROOT/requirements.lock"
"$BWC_ROOT/.venv/bin/python" -m py_compile "$BWC_ROOT/shared_workspace.py" "$BWC_ROOT/provisioning_workflow.py" "$BWC_ROOT/Axon_BWC_Provisioning_Center_v1_0_0/backend_server.py" "$BWC_ROOT/BWC_Geographic_Operations_v1_0_0/backend_server.py"
echo "Setup complete. Use either Start-*-macOS.command launcher."
