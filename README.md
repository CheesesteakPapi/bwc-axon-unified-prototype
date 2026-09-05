# BWC Axon Unified Prototype V3.1.0

> **Prototype — Python/PowerShell source execution**
> **Not a signed production desktop release**

V3.1.0 combines Provisioning Center and Geographic Operations around one authoritative, per-user SQLite workspace. Operators can paste or upload a minimal roster, enrich it, resolve exceptions, edit assignments in Preview, approve existing-account changes, submit deliberately, and track jobs without downloading and re-uploading intermediate files.

Development on `feature/future-enhancements` begins with full-snapshot inventory filtering and matching CSV export. See [Feature enhancements](FEATURE_ENHANCEMENTS.md) for the implemented increment and prioritized follow-on work, and [Feature QA](FEATURE_QA.md) for verification.

## Repository data boundary

This private source repository contains code, documentation, and small synthetic fixtures only. It intentionally excludes tenant snapshots, deployment workbooks, working crosswalks, organizational map images, generated databases, raw API responses, exports, credentials, and tenant-specific configuration. Every bundled record uses `DEMO`, `TEST`, `Example`, or reserved placeholder values.

Before each commit or release, run:

```powershell
python scripts\check_publish_safety.py
```

This check is a release guard, not a substitute for agency review or GitHub access governance. Do not add operational data to the repository even though it is private.

## Start on Windows 11

1. Extract the ZIP to a short path such as `C:\BWC31`.
2. Install an organization-approved 64-bit Python 3.11 or newer for the current user if it is not already installed.
3. Double-click `Setup-BWC-Prototype.cmd` once. It creates `C:\BWC31\.venv`; it does not require elevation.
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

- `Axon_BWC_Provisioning_Center_v1_0_0` — V3.1 workflow UI and local service.
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
