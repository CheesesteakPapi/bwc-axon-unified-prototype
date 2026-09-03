# QA and Change Log — V3.1.0

## Implemented verification

| Area | Result | Evidence |
|---|---|---|
| Shared workspace/workflow unit tests | PASS | 8 tests: enrichment, strict fields, chunk boundaries, filtered/full snapshots, refresh conflict, revision conflict, XLSX formula non-execution, overlay confirmation, guarded purge, and audit-chain checks across combined cases |
| Provisioning backend regression | PASS | 30 tests |
| Geographic backend regression | PASS | 23 tests |
| Provisioning UI production build | PASS | Vite build completed |
| Geographic UI production build | PASS | Vite build completed |
| Python compilation | PASS | Shared modules, three backends/utilities, and test modules compiled |
| Tokenized loopback/API smoke | PASS | Both services started with auto-port, exchanged launch token for session cookie, and returned health/workspace payloads |
| Source ZIP integrity | PASS | SHA-256 manifest, ZIP reopen, forbidden-path scan, and internal path-length validation |

Distribution-package counts and archive hashes remain with the preserved local package. This source repository uses `scripts/check_publish_safety.py` and GitHub Actions to enforce its separate synthetic-only publication boundary.

## Private GitHub source preparation

- Created a clean source derivative without modifying the local V3.1.0 distribution.
- Excluded the deployment workbook, governed working data, 482-row crosswalk copies, organizational map images, screenshots, document exports, hosting metadata, runtime databases, caches, logs, and credentials.
- Replaced demonstration records with small `DEMO`/`TEST` fixtures and a non-geographic synthetic SVG.
- Removed name-based geographic bucketing; operational AOR values must come from a reviewed governed crosswalk.
- Bound the Vite development servers to `127.0.0.1` and retained the one-time-token local service boundary.
- Added a publishing safety scanner, restrictive `.gitignore`, least-privilege GitHub Actions workflow, Dependabot configuration, CODEOWNERS, and a pull-request safety checklist.
- Updated Vite from 6.4.2 to 6.4.3 and refreshed affected transitive dependencies; `npm audit --audit-level=high` reports zero known vulnerabilities for both client trees and now runs in CI.
- Revalidated 8 shared tests, 30 Provisioning tests, 23 Geographic tests, both React builds, and both standalone UI build checks.

## Correctness checks represented in tests/code

- Intake alias detection, paste/CSV/XLSX paths, exact email normalization, and deduplication.
- Status proposed as Active while directory status remains separate.
- Supervisor Email and UPN separation; blank Evidence Group compatibility column.
- Standard, first-line, and senior/second-line membership rules through governed Group records.
- Friendly Group name resolution and duplicate disambiguation requirements.
- Assignment-only Preview changes, revision changes, regenerated outputs, and approval invalidation.
- User/Group chunk maxima at 500, including 500/501/1,000/1,500 boundaries.
- Shared baseline persistence, resource lease conflict, and filtered Devices isolation.
- Governed editing, revision checks, review evidence, CSV BOM projection compatibility, source hashes, and formula-prefix rejection.
- Tokenized local session, loopback-only binding, credential redaction/clearing, and automatic port selection.

## Changes from V3.0.1

The full list is in `MASTER_RELEASE_NOTES.md`. The central change is architectural: files are no longer the workflow state. A canonical provisioning run and shared database now drive enrichment, Preview, generated Axon records, approval, job state, Geographic overlays, and optional export.

## Open acceptance items

- Windows 11 standard-user execution must be recorded on the receiving workstation.
- Live Entra and Axon calls were not performed without approved credentials and change authority.
- Axon source owners must review production Role, Group, Location/AOR, title, facility, and device governance rows before writes.
- Native executable/signing acceptance remains intentionally deferred.

## Change control

The preserved V3.0.1 source and prior distribution artifacts were not overwritten. V3.1.0 is generated as a separate derivative and package. Prototype seed rows are labeled test-only and are not tenant truth.
