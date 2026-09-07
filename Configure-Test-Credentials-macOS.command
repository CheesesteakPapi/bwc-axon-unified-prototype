#!/bin/bash
set -euo pipefail
BWC_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BWC_PYTHON="$BWC_ROOT/.venv/bin/python"
if [ ! -x "$BWC_PYTHON" ]; then
  echo "Run Setup-BWC-Prototype-macOS.command first."
  exit 1
fi
exec "$BWC_PYTHON" "$BWC_ROOT/local_test_credentials.py" --configure "$@"
