# User Manual — BWC Axon Unified Prototype V3.1.0

## Scope and release label

This role-based manual covers the Windows 11 Python/PowerShell prototype. It is not a signed production desktop release. Restricted provisioning actions are separated from read-only operations.

## Operator

### Start the applications

Run setup once, then use the Provisioning or Geographic CMD launcher. The launcher opens a tokenized browser URL on an available local port. Keep its PowerShell window open.

### Create a provisioning run

1. Paste rows or upload CSV/XLSX. Email and Role are required; Group Name is optional.
2. Confirm detected columns when the mapper appears.
3. Select the approved directory provider and start enrichment.
4. Review blockers: no directory match, duplicate email, disabled directory account, invalid Role, missing Location/AOR, unmapped job title, or unresolved/duplicate Group.
5. Continue to Preview when blockers are cleared.

### Edit Preview

You may edit Role, Group, Location, Personnel AOR, Job Category, Supervisor Email, and Supervisor UPN. Identity fields must be corrected at enrichment/reconciliation. Every row or bulk change needs a reason and creates a new revision.

For existing users, open the account-update review, compare current and proposed fields, and select **Approve N account updates and continue**. Confirm the Submit page says nothing has been submitted yet.

### Read Geographic Operations

Confirmed metrics reflect active Axon snapshots only. Pending cards and the Baseline + Pending projection are separate. Filter pending rows by proposed, submitted-awaiting-confirmation, failed, or superseded status. Device filters do not alter the full Devices baseline.

### Export

Export creates one timestamped run ZIP for review. Do not upload it back into the same workflow. Store it only in an approved location because it can contain normalized personnel data.

## Provisioning Administrator — restricted

### Configure session credentials

Use separate least-privilege Axon clients for reads and writes. Enter credentials only in the session UI. The applications do not persist them. For Entra enrichment, use a delegated token with approved `User.Read.All`; do not grant Group or write permissions for this prototype.

### Govern mappings

Review the Role catalog, directory attributes, Location/AOR, exact title/category, Group rules, Axon Group master/hierarchy, facilities, office presences, and Device Home/geographic tables. Provide mapping method, confidence, reviewer, and review notes. Resolve a conflict by reloading before resaving.

### Submit to Axon

Before submission, verify the exact run ID/revision, blocker count, existing-account approval, active snapshot IDs, user and Group hashes, and Agency ID. Enable writes only for the authorized window. Submit the next eligible user chunk; monitor it to an unambiguous result before Group chunks. Never automatically retry an uncertain response.

### Confirm completion

A successful user job remains pending until a later complete Users snapshot confirms it. Group job success is recorded separately because a Users snapshot is not independent proof of Group membership.

## Support

### First checks

- Setup failure: confirm approved Python 3.11+ is available to the current user and the ZIP was extracted.
- Browser authorization error: relaunch through the CMD file; do not type the bare loopback URL.
- Address already in use: use the launcher with auto-port and close orphaned earlier windows if necessary.
- `409 Conflict`: reload the current run/table; another process committed a revision.
- Missing data in the second app: compare workspace revision and active snapshot metadata; do not trigger a duplicate pull just because a view is stale.
- Failed/canceled refresh: verify the previous baseline is still active, then inspect refresh history.
- Ambiguous Axon job: preserve run ID, revision, chunk hash, timestamp, and response; verify Axon externally before considering retry.

### Data and log handling

Preserve the SQLite database with its `-wal` and `-shm` files before repair. Do not copy only the main database while either application is running. Never ask users to send credentials or raw API response bodies in support tickets.

### Escalation placeholders

- Application support: `[TEAM / CONTACT]`
- Axon API owner: `[TEAM / CONTACT]`
- Entra administrator: `[TEAM / CONTACT]`
- Data/governance owner: `[TEAM / CONTACT]`
- Security incident channel: `[TEAM / CONTACT]`

## Change log

- V3.1.0: unified workspace, streamlined run flow, safe Preview edits, explicit existing-account approval, shared dashboards/snapshots, governed mappings, restartable chunks, auto-port launch, and source-only Windows packaging.
