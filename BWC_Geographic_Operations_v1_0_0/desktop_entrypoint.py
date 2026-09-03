"""Frozen executable entry point for BWC Geographic Operations."""

from __future__ import annotations


def main() -> int:
    import backend_server

    return int(backend_server.main())


if __name__ == "__main__":
    raise SystemExit(main())
