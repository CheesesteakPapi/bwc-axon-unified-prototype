# V3.2.0 role-based operator guide
Prototype — Python/PowerShell source execution. Not a signed production desktop release.

## Start here
Extract to a short, user-writable directory. Do not put operational files into this source package.
Windows: run Setup-BWC-Prototype.cmd once, then Start-Provisioning-Prototype.cmd or Start-Geographic-Prototype.cmd.
macOS: use Setup-BWC-Prototype-macOS.command once, then the corresponding Start-*-macOS.command. An approved Python 3.11+ is required.
If macOS prevents an unsigned script from opening, obtain the required local approval; an authorized operator can run it with bash from Terminal. Do not disable endpoint protections.
Keep the launch terminal open. Stop with Control-C. Reuse the URL opened by the launcher; a manually typed port URL does not carry the one-time launch token.

Both applications use the same per-user workspace but have separate in-memory credentials and launchers. Start both when needed. Opening either application reuses saved data; an explicit refresh pulls current Axon data.

## Operator — read-only operations
1. Open Geographic Operations. Home offers Find a device, Review matches, Reports and Setup.
2. Use People for saved users and device assignments. This page does not create accounts.
3. Use Devices to search and filter by model, disposition, assignment, Device Home and available mapped organizational fields.
4. Open an exact user or device detail. Unknown/duplicate identifiers must not be treated as confirmed links.
5. Use Reports to choose a geographic view or saved inventory/assignment export. Read resource scope and freshness. Pending proposals are not confirmed metrics.
6. Use the existing PDF/print workflow for geographic briefs and scoped CSV export for underlying records. CSV exports may contain personnel or device information; store them only in approved locations. They are not automatically leadership-redacted.

## Provisioning Administrator — restricted local edits and Axon writes
### Add users
Open Provisioning Center, select Start a user list. Paste Email and Role, with optional Group Name, into the intake grid or select CSV/XLSX. Include headers when columns are reordered. Unrelated columns are ignored unless mapped.
Role suggestions come from the approved local Axon role catalog. Synthetic roles are test examples, not tenant authorization.
Select the directory source. Synthetic test records require no credentials. Directory exports must be approved minimum-necessary data. Live Entra uses the existing delegated read provider; it does not request group membership.
Select Enrich and continue. Clean rows proceed directly to Preview; missing optional mapping values may produce warnings without blocking user import.

### Review and edit
Search for a person or page through the list, 25 at a time. Select a person to edit assignments. Expand Source identity for email, UPN and other original values.
Identity corrections require reconciliation/enrichment, not a Preview override. Role is required; Group, personnel location/AOR, category and supervisor fields follow their existing optional rules.
Provide a reason and select Save revision. The app regenerates and validates internally. No download/re-upload is needed.
Unsaved changes prevent approval. Save or discard before leaving. Bulk editing is available in Review Exceptions with a before/after confirmation.

### Approve, submit, track
Open the existing-account review when updates are present. Compare current and proposed fields, then select Approve N account updates and continue.
Submit explicitly says whether the current revision is approved and whether anything has been submitted. Approval alone performs no Axon write.
Only an authorized administrator should enable writes and configure the process connection. Confirm the target Partner/Agency ID. Submit the next eligible chunk deliberately.
Use Track Results for job status. User chunks must complete before applicable Group chunks. Do not retry an ambiguous result; reconcile it with Axon first.
Successful jobs remain pending confirmation until a later snapshot supports confirmation. Group success does not independently prove membership from a Users snapshot.

### Setup & rules
In Geographic Operations, select Setup & rules, then choose:
- Allowed Axon roles: maintain tenant-approved roles and their approval status.
- Personnel location to area: choose a location, enter area/reviewer/reason, review before/after, then save. Leave unmatched if uncertain. The saved status is Approved.
- Job title categories: classify exact directory titles when useful.
- Recommended Axon Groups: maintain organizational recommendations; blank Group assignment is allowed.
- Directory field setup: administrator-controlled Entra/source mappings.
Physical sites, offices at sites, Device Homes and non-site Groups remain separate. Do not map by state alone without reviewed jurisdiction evidence.
The table editor remains available for new rules and advanced edits. Stale writes are rejected; reload and compare before reapplying.

## Support — local operation and troubleshooting
No administrator installation, Node runtime, native executable, signature or fixed port is required. Python 3.11+ and a writable extracted folder are required. Windows policy may still restrict PowerShell; follow agency approval procedures.
A role still blocked after catalog correction: ensure its status is Approved, wait for the shared revision update, then save/revalidate the current run. Restarting is not a substitute for validation.
A mapping save rejected: use the allowed review statuses and inspect required fields. A conflict means another revision changed; do not overwrite blindly.
A connection save error appears in its panel. Credentials remain in process memory; restart requires re-entering them. Never attach secrets to a defect report.
For UI updates, stop the old servers and launch the new package. Browser reload alone cannot update running Python code.
Before testing against existing local data, close both applications and back up the entire runtime data folder, including SQLite sidecars. Test in a separate workspace first. Do not copy only an open database file.
Use the earlier USER_MANUAL_V3_1_0.md as historical detail; this guide supersedes its navigation labels. See TESTING_APPROVAL_V3_2_0.md for acceptance.
