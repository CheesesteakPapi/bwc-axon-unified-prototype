#!/usr/bin/env python3
"""Package only safety-checked source candidates, never the operational workspace."""
import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from check_publish_safety import ROOT, candidate_files, main as safety_main


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    if destination == ROOT or ROOT in destination.parents:
        raise SystemExit("Release output must be outside the source repository.")
    if safety_main():
        raise SystemExit("Release blocked by source safety check.")
    paths = candidate_files()
    for component in ("Axon_BWC_Provisioning_Center_v1_0_0", "BWC_Geographic_Operations_v1_0_0"):
        if not (ROOT / component / "dist/client/index.html").is_file():
            raise SystemExit("Build both browser clients first.")
    records = []
    contents = []
    for path in paths:
        if path.is_symlink() or ROOT not in path.resolve().parents:
            raise SystemExit("Symlinks or out-of-repository inputs are not allowed.")
        relative = path.relative_to(ROOT).as_posix()
        archive_name = "BWC32/" + relative
        if len(archive_name) > 160:
            raise SystemExit("Archive member exceeds the short-path budget: " + relative)
        data = path.read_bytes()
        records.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        contents.append((archive_name, data, relative.endswith(".command")))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = {
        "version": "3.2.0", "createdAtUTC": stamp,
        "classification": "Prototype source execution; not a signed production desktop release",
        "baseCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "sourceHasUncommittedChanges": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
        "files": records,
        "maximumMemberPathLength": max(len(name) for name, _, _ in contents),
    }
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / f"BWC32_V3_2_0_{stamp}.zip"
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data, executable in contents:
            entry = zipfile.ZipInfo(name)
            entry.create_system = 3
            entry.external_attr = (0o100755 if executable else 0o100644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
        archive.writestr("BWC32/RELEASE_MANIFEST.json", json.dumps(manifest, indent=2))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():
            raise SystemExit("Archive CRC verification failed.")
        for record in records:
            digest = hashlib.sha256(archive.read("BWC32/" + record["path"])).hexdigest()
            if digest != record["sha256"]:
                raise SystemExit("Archive content hash mismatch.")
    print(json.dumps({"archive": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                      "sourceFiles": len(records), "maximumMemberPathLength": manifest["maximumMemberPathLength"]}, indent=2))


if __name__ == "__main__":
    main()
