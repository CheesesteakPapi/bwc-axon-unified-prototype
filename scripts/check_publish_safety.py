#!/usr/bin/env python3
"""Fail when a proposed repository contains operational data or common secrets."""

from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = {
    ".db", ".docx", ".heic", ".key", ".p12", ".pdf", ".pem", ".pfx",
    ".png", ".shm", ".sqlite", ".sqlite3", ".wal", ".xls", ".xlsm",
    ".xlsx", ".zip",
}
FORBIDDEN_PATHS = (
    ".openai/",
    "data/processed/",
    "data/raw/",
    "data/schemas/",
    "exports/",
    "governance_data/working/",
    "state/",
    "uploads/",
)
TEXT_PATTERNS = {
    "agency email address": re.compile(r"[A-Z0-9._%+-]+@(?:ice\.)?dhs\.gov", re.I),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b"),
    "static UUID or tenant identifier": re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I),
    "local macOS home path": re.compile(r"/Users/[^/\s]+/(?:Desktop|Documents|Downloads|Library|Movies|Music|Pictures)/", re.I),
    "local Windows home path": re.compile(r"[A-Z]:\\Users\\[^\\\s]+\\(?:Desktop|Documents|Downloads|Pictures)\\", re.I),
}
ALLOWED_EVIDENCE_SUBDOMAINS = {"agency", "test-agency", "your-agency", "your_agency", "your-tenant"}
SYNTHETIC_MARKERS = ("demo", "test", "example", "synthetic", "placeholder")


def candidate_files() -> list[Path]:
    """Use Git's exclude rules when available so ignored local artifacts are not scanned as release inputs."""
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
        )
        candidates = (ROOT / item.decode("utf-8") for item in output.split(b"\0") if item)
        return sorted(path for path in candidates if path.is_file())
    except (FileNotFoundError, subprocess.CalledProcessError):
        return sorted(path for path in ROOT.rglob("*") if path.is_file() and ".git" not in path.parts)


def check_text(relative: str, text: str) -> list[str]:
    findings: list[str] = []
    for label, pattern in TEXT_PATTERNS.items():
        if pattern.search(text):
            findings.append(f"{relative}: contains {label}")
    for match in re.finditer(r"https://([a-z0-9_-]+)\.evidence\.com", text, re.I):
        if match.group(1).lower() not in ALLOWED_EVIDENCE_SUBDOMAINS:
            findings.append(f"{relative}: contains a non-placeholder Axon tenant hostname")
            break
    return findings


def check_csv(path: Path, relative: str) -> list[str]:
    findings: list[str] = []
    if not relative.startswith("governance_starters/"):
        findings.append(f"{relative}: CSV is outside the approved synthetic starter directory")
        return findings
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        findings.append(f"{relative}: contains a UTF-8 BOM")
    rows = list(csv.reader(raw.decode("utf-8").splitlines()))
    if len(rows) > 26:
        findings.append(f"{relative}: contains more than 25 fixture rows")
    for row_number, row in enumerate(rows[1:], 2):
        joined = " ".join(row).lower()
        if row and not any(marker in joined for marker in SYNTHETIC_MARKERS):
            findings.append(f"{relative}:{row_number}: fixture is not clearly marked synthetic")
    return findings


def main() -> int:
    findings: list[str] = []
    files = candidate_files()
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        lowered = relative.lower()
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            findings.append(f"{relative}: prohibited file type")
            continue
        if any(part in lowered for part in FORBIDDEN_PATHS):
            findings.append(f"{relative}: prohibited operational-data path")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            findings.append(f"{relative}: unreadable or unexpected binary content")
            continue
        findings.extend(check_text(relative, text))
        if path.suffix.lower() == ".csv":
            findings.extend(check_csv(path, relative))

    if findings:
        print("PUBLISH SAFETY CHECK: FAIL", file=sys.stderr)
        for finding in sorted(set(findings)):
            print(f"- {finding}", file=sys.stderr)
        return 1
    print(f"PUBLISH SAFETY CHECK: PASS ({len(files)} candidate files; synthetic source boundary)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
