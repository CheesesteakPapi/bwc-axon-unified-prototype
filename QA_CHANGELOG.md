# QA and Change Log — V3.1.0

## Unreleased Geographic Operations corrections — 2026-09-05

- Independent startup requests prevent a failed summary or slow dashboard from
  disabling healthy local table editors. Read requests time out with retry guidance;
  write requests are not automatically timed out or retried.
- Directory fields, roles, locations and job titles use recognizable record labels
  and their governed review status in the editor.
- Crosswalk review includes an inline mapping editor. Site targets are selected
  explicitly; partial existing records are never offered as vacant slots. Axon
  source identity is locked in this editor. Non-site Groups can be classified
  without assigning a site. Existing validation, prior-value conflict checks,
  backups and shared-workspace saves are reused. Dirty edits block navigation.
- Devices no longer silently adds Users and Device Homes to the pull. Existing
  shared snapshots provide context; absent context remains unavailable until
  explicitly refreshed. Background pull progress remains visible after closing
  connection settings.
- The connection panel initially selects Device Homes only. Devices requires a
  scope filter or explicit unfiltered-inventory selection. The six operator-supplied
  exact model values are the default, editable, locally saved model filter:
  axon_body_4_dock_8_bay, axon_body_4_dock_1_bay, taser_etm_flex_2,
  axon_body_cam_4, taser_body_cam_3, taser_cew_10_handle.
- Models are sent to Axon as a request filter, not just hidden after download.
  Filtered snapshots remain separate from the full baseline. Existing full
  snapshots are not deleted. Device page pacing remains unchanged.
- A lightweight workspace revision check replaces unconditional four-second
  dashboard reconstruction. This is local change detection, not an Axon delta feed.
- Verification: 18 shared Python tests, 31 provisioning Python tests, 53 geographic
  Python tests, 10 provisioning UI tests and 4 geographic UI tests passed (116).
  Geographic assets rebuilt. Synthetic browser checks passed for inline Device
  Home and non-site Group saves, automatic queue updates, dirty-navigation
  protection and source-field editor save. No browser console errors observed.
- Limits: the operator's precise Windows table failure has not been reproduced.
  Windows 11 and real-tenant throughput acceptance remain pending. No live Axon
  writes or agency-record imports were performed. Existing release ZIPs unchanged.
- Incremental Axon refresh is NOT implemented or claimed: supplied clippings do
  not establish a change-feed contract. Verify endpoint-specific change filters,
  deletion signals and cursor semantics before merging deltas into saved baselines.
  Local hashing alone cannot reduce the API records downloaded.

## Implemented verification

| Area | Result | Evidence |
|---|---|---|
| Shared workspace/workflow unit tests | PASS | 17 tests, including optional mapping warnings, deduplicated crosswalk candidate creation, non-reviewed active Group rules, exact Group selection, atomic snapshot batches, bounded atomic dashboard reads, and shared mapping-status enforcement across all three sync components, plus prior enrichment, Entra, chunking, revision, XLSX, overlay, purge, and audit checks |
| Provisioning backend regression | PASS | 31 tests |
| Geographic backend regression | PASS | 33 tests, including unavailable partial-scope projections and device-count handling |
| Provisioning UI production build | PASS | Vite build completed |
| Geographic UI production build | PASS | Vite build completed |
| Python compilation | PASS | Shared modules, three backends/utilities, and test modules compiled |
| Tokenized loopback/API smoke | PASS | Both services started with auto-port, exchanged launch token for session cookie, and returned health/workspace payloads |
| Source ZIP integrity | NOT RERUN | The preserved prior package passed SHA-256, reopen, forbidden-path, and path-length checks; this source commit was not regenerated as a ZIP |

Distribution-package counts and archive hashes remain with the preserved local package. This source repository uses `scripts/check_publish_safety.py` and GitHub Actions to enforce its separate synthetic-only publication boundary.

## Private GitHub source preparation

- Created a clean source derivative without modifying the local V3.1.0 distribution.
- Excluded the deployment workbook, governed working data, 482-row crosswalk copies, organizational map images, screenshots, document exports, hosting metadata, runtime databases, caches, logs, and credentials.
- Replaced demonstration records with small `DEMO`/`TEST` fixtures and a non-geographic synthetic SVG.
- Removed name-based geographic bucketing; operational AOR values must come from a reviewed governed crosswalk.
- Bound the Vite development servers to `127.0.0.1` and retained the one-time-token local service boundary.
- Added a publishing safety scanner, restrictive `.gitignore`, least-privilege GitHub Actions workflow, Dependabot configuration, CODEOWNERS, and a pull-request safety checklist.
- Corrected clean-runner test working directories and pinned the current GitHub-maintained checkout/runtime setup actions to verified commit SHAs.
- Corrected Windows automatic-port fallback to request a safe OS-selected loopback port instead of incrementing into a potentially excluded Windows port range.
- Updated Vite from 6.4.2 to 6.4.3 and refreshed affected transitive dependencies; `npm audit --audit-level=high` reports zero known vulnerabilities for both client trees and now runs in CI.
- Revalidated 15 shared tests, 31 Provisioning tests, 32 Geographic tests, both React builds, both standalone UI build checks, and zero high-severity npm audit findings.

## Correctness checks represented in tests/code

- Intake alias detection, paste/CSV/XLSX paths, exact email normalization, and deduplication.
- Status proposed as Active while directory status remains separate.
- Supervisor Email and UPN separation; blank Evidence Group compatibility column.
- Standard, first-line, and senior/second-line membership rules through governed Group records.
- Friendly Group name resolution and duplicate disambiguation requirements.
- Assignment-only Preview changes, revision changes, regenerated outputs, and approval invalidation.
- User/Group chunk maxima at 500, including 500/501/1,000/1,500 boundaries.
- Shared baseline persistence, resource lease conflict, atomic multi-resource activation, canceled-batch rollback, and filtered Devices isolation.
- Governed editing, read-captured compare-and-swap revisions, review evidence, CSV BOM projection compatibility, source hashes, and formula-prefix rejection.
- Tokenized local session, loopback-only binding, credential redaction/clearing, and automatic port selection.

## Entra delegated-read mapping correction

- Replaced the incorrect `/users/{email}` assumption with an exact Entra `mail` query so organizational Email and UPN can remain different.
- Manager reads now use the returned Entra object ID.
- Added `mailNickname` and `department` to the minimum-necessary Graph projection.
- Mapped UPN and External ID to `userPrincipalName`; mapped UserName and Badge Number to `mailNickname`; retained Email from `mail` without UPN substitution.
- Confirmed `givenName`, `surname`, `jobTitle`, and `officeLocation` mappings; mapped Component from `department`.
- Kept proposed Axon Status fixed at `Active` while retaining `accountEnabled` as separate directory state.
- Added explicit blockers when UPN, External ID, Badge Number, names, or UserName are missing.
- Added a mocked delegated-read regression test proving the lookup URL, requested properties, manager-object-ID call, mapped roster row, generated Axon record, and business-phone fallback without transmitting credentials.

## Optional mapping and Group-selection correction

- Personnel Location without one reviewed AOR mapping is now a warning, not a blocker; `LOCATION` remains usable and Personnel AOR may stay blank.
- Job Title is optional for user import. A returned but unmapped Job Title is now a warning, not a blocker.
- Distinct Location/Component and Job Title values observed through enrichment are appended once to their governed crosswalks with `Needs review`, provider-specific provenance, and no user identity in the audit event.
- Component/AOR/job-category Group rules no longer require a reviewed status; only explicitly inactive rules are excluded.
- The UI now retrieves the current Group pool and provides friendly drop-downs with Component, AOR, and tier context.
- An operator may clear Group assignment. The user record remains eligible and the Group relationship row is omitted.
- Optional mapping and Group warnings are visible separately from blockers, and Preview remains available when no true blocker exists.

## Geographic mapping-metric correction

- A populated Site ID is no longer sufficient to count a Device Home, device, or Axon Group as geographically mapped. The governed crosswalk row must also be explicitly `Mapped`.
- Candidate and needs-review rows remain in review queues without contributing to confirmed mapping-completion totals.
- Reviewed Region/AOR values remain visible as their governed labels instead of being collapsed into a generic `Needs review` bucket.
- All three sync components enforce the same mapping-status rule before normalized Site, Component, or AOR values enter a shared snapshot.
- Geographic governance responses and interface copy now identify SQLite as authoritative. SQLite commits first; CSV backup/projection failure is reported as a warning without falsely rolling back the committed change.
- Runtime syncs and crosswalk exports materialize current SQLite governance instead of reading a potentially stale CSV projection. The separately file-governed device-status map remains live and status matching is case-insensitive.
- Geographic multi-resource refreshes activate in one SQLite transaction and one workspace revision only after every resource completes. Cancellation or failure activates none of the pending snapshots.
- Full-device metrics remain confirmed baseline values. A first filtered-only pull is clearly labeled as a filtered result rather than a complete baseline or a false zero-device snapshot.
- Users-only or other partial views mark device metrics and assignment counts unavailable and suppress device-derived exports until a full or explicitly filtered Devices scope exists.

## Changes from V3.0.1

The full list is in `MASTER_RELEASE_NOTES.md`. The central change is architectural: files are no longer the workflow state. A canonical provisioning run and shared database now drive enrichment, Preview, generated Axon records, approval, job state, Geographic overlays, and optional export.

## Open acceptance items

- Windows 11 standard-user execution must be recorded on the receiving workstation.
- Live Entra and Axon calls were not performed without approved credentials and change authority.
- Axon source owners must review production Roles before user writes. Optional Location/AOR, title/category, and Group-rule candidates may remain pending without blocking eligible user rows, but must be reviewed before they are relied on for automatic organizational assignment or confirmed geographic metrics.
- Native executable/signing acceptance remains intentionally deferred.

## Change control

The preserved V3.0.1 source and prior distribution artifacts were not overwritten. V3.1.0 is generated as a separate derivative and package. Prototype seed rows are labeled test-only and are not tenant truth.
