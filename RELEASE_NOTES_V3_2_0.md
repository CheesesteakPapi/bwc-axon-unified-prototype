# BWC Axon Unified Prototype V3.2.0
Release candidate for operator testing — 2026-09-04.
Prototype — Python/PowerShell source execution. Not a signed production desktop release.

## What changed
- Task-focused Home in both applications, using the Task Home and Guided Tasks design direction. Administration no longer dominates the landing page.
- Geographic navigation uses Home, People, Devices, Locations, Reports and Help. Specialized pages remain reachable through secondary navigation.
- Thirteen competing setup tabs become one grouped, plainly labeled selector. Underlying field names, CSV schemas and governance history are preserved.
- Personnel location matching has three steps: choose a location, confirm its area, review and save. Leaving a location unmatched remains non-blocking for user import. Saving uses the existing Approved status and stale-value conflict checks.
- Preview uses a searchable, 25-person paged list and a selected-person assignment editor. Identity stays read-only; details and optional mapping warnings expand on demand.
- Approved-role suggestions come from the same catalog used by validation and update with shared workspace revisions.
- Excel/CSV clipboard parsing supports headers, reordered aliases, BOM and quoted values. Replacing populated intake requires confirmation.
- Unsaved assignment edits disable approval and block task navigation and export. Saving regenerates dependent records and invalidates old approval.
- Bulk edits show a before/after confirmation and require a shared reason.
- Submit distinguishes missing approval, current approval and prior submission history. Approval is not an Axon write. A final enabled, credentialed and confirmed action remains necessary.
- Connection-save errors are visible rather than silently failing.
- Both applications use shared white/navy/blue design tokens, larger actions, labeled controls and responsive layouts.
- Includes the previously developed saved-device filters, exact-ID assignment drilldowns, scoped all-matching CSV exports and provenance.
- Adds macOS source launchers alongside Windows Python/PowerShell launchers. Neither requires a native executable build.

## Unchanged controls
Email and UPN remain distinct; External ID uses UPN. Default proposed status is Active. Supervisor email and UPN remain separate. Optional AOR and job-category mappings do not block user import. Blank Group selection produces no Group relationship. Device locations never determine personnel organization. Evidence Groups stay unused.

Confirmed snapshots, pending overlays, resource scopes, credentials-in-memory, 500-row chunks, revision-bound approval and no automatic ambiguous-write retries remain in place. No new Axon writes, Graph permissions or database schema migration were added. Suite version is 3.2.0; compatible component directory names and SQLite schema version are retained.

## Delivery and limitations
The ZIP contains source, compiled browser assets, synthetic starters, launchers, tests and documentation. No Node installation is required to run it. Old releases and operational workspaces are not overwritten.

This is not completion of every future reporting idea. Power BI, leadership-specific privacy projections, historical R/Tableau recovery, native signing and production acceptance are tracked separately in PRODUCT_ROADMAP.md.

Read TESTING_APPROVAL_V3_2_0.md and QA_V3_2_0.md before approval.
