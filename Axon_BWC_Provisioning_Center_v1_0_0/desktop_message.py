"""Minimal native error dialog without elevated privileges or third-party runtime dependencies."""

from __future__ import annotations

import ctypes
import subprocess
import sys


def show_error(title: str, message: str) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
        return
    if sys.platform == "darwin":
        escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')
        escaped_message = message.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(
            [
                "/usr/bin/osascript",
                "-e",
                f'display alert "{escaped_title}" message "{escaped_message}" as critical',
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    print(f"{title}: {message}", file=sys.stderr)
