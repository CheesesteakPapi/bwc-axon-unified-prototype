# V3.2.0 testing and approval
Status: ready for controlled user acceptance testing, not production approval.

## Safe installation
Preserve the prior package. Extract this ZIP to a short directory such as C:\BWC32. Install only an organization-approved per-user Python 3.11+ runtime.
For an isolated Windows test, open PowerShell in the extracted folder and run:

```powershell
$env:BWC_AXON_DATA_ROOT = Join-Path $env:LOCALAPPDATA 'BWC32-UAT'
$env:BWC_SHARED_WORKSPACE_PATH = Join-Path $env:BWC_AXON_DATA_ROOT 'shared\shared_workspace.sqlite3'
.\Setup-BWC-Prototype.ps1
.\Start-Provisioning-Prototype.ps1
```

Use the same two environment settings in a second PowerShell window before starting Geographic Operations. These variables select local test storage, not API endpoints. Do not relax machine policy if scripts are blocked; use approved execution procedures.

On macOS, from the extracted folder:

```bash
export BWC_AXON_DATA_ROOT="$HOME/Library/Application Support/BWC32-UAT"
export BWC_SHARED_WORKSPACE_PATH="$BWC_AXON_DATA_ROOT/shared/shared_workspace.sqlite3"
bash Setup-BWC-Prototype-macOS.command
bash Start-Provisioning-Prototype-macOS.command
```

Repeat the exports in a second Terminal before running Start-Geographic-Prototype-macOS.command. HOME is read, not reassigned.

## Acceptance checklist
Record Pass, Fail or Not tested, tester, date and evidence for every item.
1. Standard-user setup and both launches succeed; launch URLs are tokenized and different occupied ports are handled.
2. Home makes the next task clear without administrator assistance.
3. Paste two synthetic emails with Prototype User role and no Group; use synthetic enrichment. Optional mapping warnings do not block Preview.
4. Search, page and select a person; identity cannot be edited. Supervisor email and UPN remain separate.
5. Edit an assignment, add a reason and save. Revision and generated records update; approval is invalidated.
6. Unsaved edits cannot be approved or silently lost during task navigation.
7. Existing-account field differences are reviewed before update approval. Approval moves to Submit but sends nothing.
8. With no configured credentials/writes, submission is disabled. Test real submission only in a separately authorized tenant window.
9. Setup & rules labels are understandable. Approve a synthetic personnel mapping and verify it when reopened. Leaving an optional mapping unmatched does not block import.
10. Saved Users, Devices and Groups are reused across the two apps. Verify actual full vs filtered scope and pending vs confirmed labels.
11. Inventory, assignment drilldowns and CSV exports agree with filters; PDF output is readable and retains context.
12. Close/reopen apps; saved snapshots and runs remain. Verify keyboard navigation, focus visibility, 200% zoom and your usual display size.

## Approval record
Release/version: V3.2.0
Tester: [name]
Windows 11 version / macOS version: [version]
Python and browser versions: [versions]
Workspace: [isolated or approved operational test]
Decision: [Approve prototype / Approve with conditions / Return for correction]
Conditions / defects: [list]
Authorization for tenant writes: [separate reference, or none]

Success target for a five-person nontechnical pilot: at least four find the right task in 30 seconds and complete a review without assistance; every participant can distinguish saved, approved and submitted. These are targets, not completed results.
