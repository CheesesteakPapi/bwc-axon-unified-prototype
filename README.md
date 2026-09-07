# BWC Axon Unified Prototype V3.2.1 — testing candidate

Optional testing convenience: run `Configure-Test-Credentials.cmd` on Windows,
or `bash Configure-Test-Credentials-macOS.command` on macOS, to save a private
**plaintext** local Axon test profile outside the source package and `.venv`.
Both normal source launchers load it on startup; no automatic API request or
approval occurs. See [LOCAL_TEST_CREDENTIALS.md](LOCAL_TEST_CREDENTIALS.md) for
setup, safeguards, rotation and removal. Entra delegated tokens remain separate.

## Bulk review

- Geographic Operations: **Review → Review mode → Bulk review: [mapping table]**.
  Bulk controls also appear in the full governance table under Setup & rules.
- Provisioning: **People → Review Exceptions** or **Preview Changes**.
  Filter by blocked, warnings, or ready; search by name, email, role, or issue.
- Select individual records, **Select this page**, or **Select all matching**.
  All matching includes other pages (maximum 1,500 records). Changing a user
  search/filter clears selection; crosswalk page changes clear page selections.
- Expand **Bulk update**, choose one or more shared fields, and add a reason.
  **Preview bulk changes** lists before/after values and no-op counts. Page through
  the preview, then **Confirm N record updates**. Nothing saves before confirmation.
- Source identities cannot be bulk-edited. Crosswalk batches validate and commit
  atomically; stale revisions or invalid relationships save nothing. Review notes
  are appended, not replaced. New source relationships use single-source review.
- User batches regenerate validation and import records, clear old approval, and
  return to Preview or Review Exceptions. Existing blockers remain visible.
  No bulk action approves a run or submits to Axon.

The known-location mapping workbook is a separate local collection artifact, not
part of this repository. Its dropdowns reflect saved reference lists, not live
snapshot refreshes. A one-click reviewed workbook import is not implemented; do
not replace the database or runtime CSVs with a completed template.

> **Prototype — Python/PowerShell source execution**
> **Not a signed production desktop release**

V3.2.1 is a local source testing candidate, not a published or repackaged release.
It adds stricter submission reconciliation, renewable refresh ownership, one-tenant
workspace binding, per-resource freshness, a focused Review workspace, inline
relationship creation, explicit device scopes, and privacy-safe local diagnostics.
Read [FORGEFLOW_REVIEW_V3_2_1.md](FORGEFLOW_REVIEW_V3_2_1.md) for verification,
remaining acceptance gates, and safe upgrade instructions. Existing V3.2.0 release
archives and operational data are unchanged.

V3.2.0 combines Provisioning Center and Geographic Operations around one authoritative, per-user SQLite workspace. Operators can paste or upload a minimal roster, enrich it, resolve exceptions, edit assignments in Preview, approve existing-account changes, submit deliberately, and track jobs without downloading and re-uploading intermediate files.

V3.2.0 adds a task-focused Home, guided location matching, plain-language setup labels, approved-role suggestions, and a paged person-review editor. The previous saved-inventory and assignment enhancements are included. Begin with `TESTING_APPROVAL_V3_2_0.md`; see `RELEASE_NOTES_V3_2_0.md` for scope and `PRODUCT_ROADMAP.md` for follow-on work.

## Repository data boundary

This private source repository contains code, documentation, and small synthetic fixtures only. It intentionally excludes tenant snapshots, deployment workbooks, working crosswalks, organizational map images, generated databases, raw API responses, exports, credentials, and tenant-specific configuration. Every bundled record uses `DEMO`, `TEST`, `Example`, or reserved placeholder values.

Before each commit or release, run:

```powershell
python scripts\check_publish_safety.py
```

This check is a release guard, not a substitute for agency review or GitHub access governance. Do not add operational data to the repository even though it is private.

## Start on Windows 11

1. Extract the ZIP to a short path such as `C:\BWC32`.
2. Install an organization-approved 64-bit Python 3.11 or newer for the current user if it is not already installed.
3. Double-click `Setup-BWC-Prototype.cmd` once. It creates `C:\BWC32\.venv`; it does not require elevation.
4. Start either application:
   - `Start-Provisioning-Prototype.cmd`
   - `Start-Geographic-Prototype.cmd`
5. Keep the PowerShell window open while using the local browser application. Use the app's Exit control or close the PowerShell window when finished.

Both launchers bind to `127.0.0.1`, select an available port, and open a one-time tokenized URL. The applications do not depend on port 8798 and can run at the same time.

## Operator workflow

```text
Add Users → Enrich → Review Exceptions → Preview → Submit → Track
```

- Start with `Email`, `Role`, and optional `Group Name` by paste, CSV, or XLSX.
- The intake file does not need Axon headers. Formula cells, macros, links, and embedded XLSX content are not executed.
- Directory enrichment supports a supplied directory export, a SharePoint/Power Automate export, synthetic test data, or a delegated Entra provider.
- Entra lookup uses read-only delegated `User.Read.All`. Intake Email is resolved against an exact Entra `mail` value; the returned UPN is preserved separately and used as External ID. Entra membership is not requested and is never correlated to Axon Groups.
- The confirmed directory projection is `mail` → Email, `userPrincipalName` → UPN and External ID, `mailNickname` → UserName and Badge Number, `givenName`/`surname` → names, `department` → Component, `officeLocation` → Directory Location, and `jobTitle` → Job Title.
- Status defaults to `Active`. Directory status remains separate; a disabled account is a blocker until reviewed.
- Personnel Location/AOR and Job Title/Category enrichment gaps are warnings, not user-import blockers. Newly observed directory values are added once to the governed crosswalks as `Needs review` candidates with their provider provenance.
- Group recommendations use `Component + Personnel AOR + exact-title Job Category` when those optional values are available. Active/non-inactive Group rules may populate the recommendation without a separate reviewed status.
- The Group picker is populated from the current Groups snapshot (or local Group master). An operator may select an exact Group or leave the assignment blank; blank Group assignments generate no Group relationship row and do not block the user import.
- Preview identity fields are read-only. Assignment fields support governed row and bulk edits with reasons.
- Existing-account changes require a dedicated review and approval step. Approval does not submit anything.
- User chunks complete before Group relationship chunks become eligible. No Axon write is retried automatically when its result is ambiguous.

## Shared workspace

The default database is:

```text
%LOCALAPPDATA%\ICE\BWC Axon Operations\shared\shared_workspace.sqlite3
```

It persists normalized Users, Groups, Devices, Device Homes, facilities, office presences, governed mappings, provisioning revisions, pending overlays, refresh metadata, and a hash-chained audit log. Raw API responses and credentials are not retained by default.

Confirmed snapshots and pending proposals are separate. Geographic Operations excludes pending users from confirmed metrics and shows `Baseline + Pending` only as a separate projected measure. Filtered Devices snapshots never replace the complete Devices baseline.

Geographic mapping totals include only crosswalk relationships with a nonblank Site ID and an explicit governed `Mapped` status. Candidate and needs-review rows remain visible without being counted as confirmed mappings.

Governed CSVs are imported once with their original paths and SHA-256 values recorded. SQLite becomes the editable source; CSV files are projections for export and workbook review, not a second editable truth.

## Included components

- `Axon_BWC_Provisioning_Center_v1_0_0` — V3.2 workflow UI and local service.
- `BWC_Geographic_Operations_v1_0_0` — shared dashboards, snapshots, facilities, mappings, and pending overlays.
- `Axon_BWC_Sync_Prototype_v0_2_6` — read-only command-line sync that uses the same refresh leases and scoped snapshots.
- `shared_workspace.py` — shared schema, revision, snapshot, governance, audit, overlay, and chunk store.
- `provisioning_workflow.py` — intake, enrichment, mapping, validation, strict record generation, and export.
- `governance_starters` — synthetic schema examples copied into the per-user runtime workspace on first launch.

## Important boundaries

- No native EXE, PyInstaller runtime, Authenticode signature, RFC 3161 timestamp, SmartScreen acceptance, or production endpoint approval is claimed.
- Axon writes remain disabled until explicitly enabled in Provisioning Center and separately confirmed at final submission.
- Geographic Operations and the sync utility make read-only Axon resource calls; OAuth token acquisition is their only POST.
- Credentials remain in each process's memory and are not shared through SQLite.
- Device Home and Respond/device location are comparison signals only; they never reassign a user's organizational Group.
- Evidence Groups are not used. `EVIDENCE_GROUP_EXT_ID` is emitted blank only for import compatibility.

Read `START_HERE.txt`, `OPERATIONS_RUNBOOK.md`, `API_CONTRACT.md`, `DATA_MODEL.md`, `SECURITY_MODEL.md`, and `QA_CHANGELOG.md` before controlled testing.

Axon, Axon Evidence, Microsoft, Windows, PowerShell, and related marks belong to their respective owners. This repository is an integration prototype and is not an Axon product.
