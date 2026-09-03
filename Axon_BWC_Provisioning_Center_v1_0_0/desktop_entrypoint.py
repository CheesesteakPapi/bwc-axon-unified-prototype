"""Frozen executable entry point for Axon BWC Provisioning Center."""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--internal-cli":
        action = sys.argv[2]
        sys.argv = [sys.argv[0], *sys.argv[3:]]
        if action == "sync":
            import axon_sync

            return int(axon_sync.main())
        if action == "provision":
            import axon_provision

            return int(axon_provision.main())
        raise SystemExit("Unknown internal command.")
    import backend_server

    return int(backend_server.main())


if __name__ == "__main__":
    raise SystemExit(main())
