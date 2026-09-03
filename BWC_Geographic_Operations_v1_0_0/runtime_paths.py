"""Per-user runtime paths for the standalone BWC Axon desktop applications."""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path


SUITE_FOLDER = "BWC Axon Operations"


def bundle_root(module_file: str) -> Path:
    """Return the read-only resource root for source and frozen execution."""
    frozen_root = getattr(sys, "_MEIPASS", "")
    if frozen_root:
        return Path(frozen_root).resolve()
    module_root = Path(module_file).resolve().parent
    return module_root


def application_data_root() -> Path:
    override = os.environ.get("BWC_AXON_DATA_ROOT", "").strip()
    if override:
        root = Path(override).expanduser().resolve()
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home())
        root = base / "ICE" / SUITE_FOLDER
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "ICE" / SUITE_FOLDER
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
        root = base / "ice" / "bwc-axon-operations"
    ensure_private_directory(root)
    return root


def component_root(component: str) -> Path:
    root = application_data_root() / component
    ensure_private_directory(root)
    return root


def governance_root() -> Path:
    root = application_data_root() / "governance" / "working"
    ensure_private_directory(root)
    return root


def governance_backup_root() -> Path:
    root = application_data_root() / "governance" / "backups" / "crosswalks"
    ensure_private_directory(root)
    return root


def audit_database_path() -> Path:
    root = application_data_root() / "audit"
    ensure_private_directory(root)
    return root / "operations_audit.sqlite3"


def packaged_governance_starters(module_file: str) -> Path:
    module_root = Path(module_file).resolve().parent
    candidates = [
        bundle_root(module_file) / "governance_starters",
        module_root.parent / "governance_starters",
        module_root,
    ]
    for candidate in candidates:
        if (candidate / "office_presence_starter.csv").is_file():
            return candidate.resolve()
    return candidates[0].resolve()


def initialize_governance_files(module_file: str, names: tuple[str, ...] | list[str]) -> list[str]:
    source_root = packaged_governance_starters(module_file)
    destination_root = governance_root()
    created: list[str] = []
    for name in names:
        destination = destination_root / name
        if destination.exists():
            continue
        source = source_root / name
        if not source.is_file():
            raise RuntimeError(f"Required packaged governance starter is missing: {name}")
        shutil.copy2(source, destination)
        ensure_private_file(destination)
        created.append(name)
    return created


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(stat.S_IRWXU)


def ensure_private_file(path: Path) -> None:
    if path.exists() and os.name != "nt":
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
