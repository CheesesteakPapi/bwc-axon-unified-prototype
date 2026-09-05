#!/bin/bash
set -euo pipefail
BWC_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BWC_PYTHON="$BWC_ROOT/.venv/bin/python"
if [ ! -x "$BWC_PYTHON" ]; then
  echo "Run Setup-BWC-Prototype-macOS.command first."
  exit 1
fi
echo "Starting BWC Geographic V3.2.0 source prototype. Keep this terminal open; Control-C stops it."
exec "$BWC_PYTHON" "$BWC_ROOT/BWC_Geographic_Operations_v1_0_0/backend_server.py" --open --auto-port
