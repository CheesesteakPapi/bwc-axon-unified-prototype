"""Cross-platform per-user single-instance lock for standalone desktop components."""

from __future__ import annotations

import atexit
import os
from pathlib import Path
from typing import BinaryIO

from runtime_paths import component_root


class SingleInstanceLock:
    def __init__(self, component: str) -> None:
        self.path = component_root(component) / "application.lock"
        self.handle: BinaryIO | None = None

    def acquire(self) -> bool:
        handle = self.path.open("a+b")
        handle.seek(0)
        if handle.read(1) == b"":
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            handle.close()
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()).encode("ascii"))
        handle.flush()
        self.handle = handle
        atexit.register(self.release)
        return True

    def release(self) -> None:
        handle = self.handle
        if not handle:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self.handle = None
