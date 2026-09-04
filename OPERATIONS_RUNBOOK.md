# Operations Runbook — V3.1.0

## Install and launch

1. Extract to `C:\BWC31`; do not run inside the ZIP.
2. Run `Setup-BWC-Prototype.cmd` once as the signed-in standard user.
3. Run either or both application launchers. Leave each PowerShell window open.
4. Use the URL opened by the launcher. If a browser shows an authorization error at a manually typed loopback URL, close it and relaunch; the one-time token is required.

The launchers select available ports automatically, so an existing process on 8798 is not a blocker.

## Provision a roster

1. Open Provisioning Center and choose Paste or Upload.
2. Supply Email and Role; Group Name is optional.
3. Choose an approved directory provider. Synthetic is test-only.
4. Resolve blocking missing/duplicate/disabled users and Role problems. Location/AOR, title/category, and optional Group gaps appear as warnings and do not block an otherwise eligible user import.
5. In Preview, edit assignment fields only. Use the Group drop-down to choose an exact current Group or select **No Group assignment**. Provide a reason for row or bulk changes.
6. Open the existing-account review when existing accounts are present.
7. Select **Approve N account updates and continue**. Verify the screen states that nothing has been submitted.
8. Enable and confirm writes only in an authorized test window. Submit the next eligible chunk deliberately.
9. Track stored job IDs. Resolve ambiguous/missing-job-ID outcomes externally before any retry.
10. Export the current run revision only when a review package is needed. Do not re-import that package into the same run.

## Refresh shared data

Use either application to request Users, Groups, Devices, or Device Homes. A lease prevents the same resource from being pulled simultaneously. Geographic multi-resource pulls stage all requested resources and activate them together in one SQLite transaction and one workspace revision. Cancellation is cooperative between requests; cancellation or failure before commit activates none of the pending batch, so every prior baseline remains usable.

Use Devices filters for targeted analysis. The UI labels these snapshots filtered; confirmed complete-Devices metrics continue to use the most recent full snapshot. If no full Devices baseline exists yet, the filtered result is shown only as a non-confirmed scoped result and never as zero-device confirmed truth.

## Governance

Edit governed tables in Geographic Operations. Enrichment automatically adds distinct observed Location/Component and Job Title values as `Needs review` candidates without copying user identity into the crosswalk. Reviewing a candidate requires the current revision, reviewer, mapping method, confidence, and notes. The database is authoritative after migration; do not edit the generated CSV projection separately and expect it to update SQLite.

Organizational logic uses command hierarchy and Axon Groups. Do not infer a user's Group from Entra membership, device owner/home, similar names, geography alone, or co-location. Model a facility once and record each component office presence independently, including non-ICE and non-networked sites.

## Recovery

- Port already in use: use the packaged launcher; it selects another loopback port.
- Stale edit/409: reload the run/table and reapply against the current revision.
- Refresh failure: inspect the resource history; the previous baseline remains active.
- Ambiguous Axon write: do not retry. Verify the job list/status in Axon using the exact request time and stored payload hash.
- Damaged local workspace: preserve the database and `-wal`/`-shm` sidecars before support analysis. Restore only from an approved backup.

## Backup and purge

Close both applications before a filesystem-level backup. Preserve the SQLite database and any sidecars as one set. Exports contain normalized personnel data and must use the approved handling location. Purge operations should be authorized, logged, and limited to the intended run/export; they do not delete Axon records.
