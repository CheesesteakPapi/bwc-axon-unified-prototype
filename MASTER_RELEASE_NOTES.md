# Master Release Notes — BWC Axon Unified Prototype V3.1.0

Release date: 2026-09-02
Correction update: 2026-09-04
Runtime: Windows 11, Python 3.11+, Windows PowerShell 5.1+
Distribution: source ZIP; standard-user setup; no native executable or signature

## Release outcome

V3.1.0 replaces the file-handoff prototype with a unified local operating model. Provisioning Center and Geographic Operations now use one revision-aware SQLite workspace. Completed Axon snapshots, governed mappings, pending provisioning changes, run history, and job state are available to both applications without a second API call or intermediate roster download/re-upload.

## Provisioning changes

- Added the operator workflow `Add Users → Enrich → Review Exceptions → Preview → Submit → Track`.
- Added paste intake with Email, Role, and optional Group Name.
- Added flexible CSV and XLSX intake with alias-based header detection and an explicit mapper when uncertain.
- Added safe XLSX value extraction without running macros, formulas, links, or embedded content.
- Added directory-provider boundary for live delegated Entra, SharePoint/Power Automate exports, supplied directory rows, and synthetic test rows.
- Removed Entra Group membership from enrichment and Axon Group logic.
- Added automatic normalization, global email deduplication, exact lookup, metadata enrichment, default `Active` proposal, Location/AOR resolution, exact-title classification, Group recommendation/resolution, generation, and validation.
- Kept Supervisor Email and Supervisor UPN separate; only Supervisor Email is generated for Axon.
- Kept Rank separate, optional, blank by default, and excluded it from assignment logic.
- Preserved directory account status separately and blocklisted disabled accounts for review.
- Changed missing reviewed Location/AOR and exact-title/category mappings from blockers to warnings because those fields are optional for user import.
- Added automatic, deduplicated `Needs review` crosswalk candidates for new directory Location/Component and Job Title values, with provider provenance and without storing user identities in crosswalk audit events.
- Allowed non-inactive Component/AOR/category Group rules to supply recommendations without a separate reviewed status.
- Added current-Group drop-downs for intake, Preview, and bulk editing. Operators may select an exact Group or intentionally leave Group assignment blank; blank or unresolved optional Groups omit the Group relationship row without blocking the user row.
- Added assignment-only row editing and governed bulk editing with before/after review and a required reason.
- Made identity fields read-only in Preview.
- Replaced the ambiguous existing-account checkbox with field-level differences and **Approve N account updates and continue**.
- Added the explicit submit warning: `Updates approved for submission. Nothing has been submitted to Axon yet.`
- Added automatic downstream regeneration and stale-approval invalidation after every edit.
- Added internal 500-row user and Group chunking, dependency order, restart/resume state, and deliberate next-chunk submission.
- Added strict UTF-8 without BOM outputs; `EVIDENCE_GROUP_EXT_ID` remains blank.
- Added revision export as one ZIP containing enriched roster, review report, chunks, validation, and a hash/count/encoding manifest.

## Shared data and synchronization changes

- Added the authoritative `%LOCALAPPDATA%\ICE\BWC Axon Operations\shared\shared_workspace.sqlite3` store.
- Added independent full and filtered snapshot scopes for Users, Groups, Devices, and Device Homes.
- Added shared resource refresh leases to prevent duplicate pulls across processes.
- Added staging, validation, and atomic multi-resource activation in one SQLite transaction and one workspace revision; failed/canceled refreshes activate none of the pending batch and preserve every prior baseline.
- Prevented a filtered Devices pull from replacing or being labeled as the full baseline. A first filtered-only pull is presented as a clearly scoped, non-confirmed result rather than a false zero-device baseline.
- Added workspace and run revision counters with `409 Conflict` protection.
- Added persistent pending overlays with Confirmed, Proposed creation/update, Submitted—awaiting confirmation, Failed, and Superseded states.
- Added Geographic Operations baseline-versus-projected metrics and pending filters.
- Required an explicit governed `Mapped` status before a Site ID contributes to confirmed mapping totals, and preserved reviewed AOR labels in geographic summaries.
- Added cross-application polling of the lightweight workspace revision.
- Added hash-chained audit events without credential or raw-row storage.
- Added one-time governed CSV migration with original path and SHA-256 provenance; SQLite is authoritative after migration.

## Governance and organizational changes

- Added editable tables for approved Axon Roles, directory attributes, personnel Location/AOR, exact title/category, and Component/AOR/category Group rules.
- Added prior-value history, reviewer, review notes, mapping method, confidence, timestamp, revision conflict protection, and formula-injection rejection.
- Retained command hierarchy and Axon Groups as the organizational model; Evidence Groups are not used.
- Prevented device assignment, Device Home, Respond location, similar names, or co-location from automatically changing a user's organizational Group.
- Preserved facilities and component office presences separately for co-located, other-agency, and non-ICE-networked sites.

## Geographic and sync changes

- Geographic Operations loads confirmed shared snapshots at startup instead of triggering a new call.
- Pending provisioning rows are visible but excluded from confirmed metrics.
- New governed tables are editable in the existing crosswalk interface.
- Read-only sync prototype updated to v0.2.6 and now uses the same refresh lease, scoped snapshot, and atomic activation model.
- Model, device status, and Device Home filters remain supported; filtered device results remain scoped.

## Packaging changes

- Added per-user `Setup-BWC-Prototype.ps1/.cmd`.
- Added dedicated Provisioning and Geographic PowerShell/CMD launchers.
- Launchers resolve paths containing spaces and use `--open --auto-port` to avoid fixed-port failures.
- Added a hash-only empty runtime lock because V3.1.0 uses the Python standard library.
- Added prebuilt UI assets so Node.js is not required to run the prototype.
- Added a short internal package root (`BWC31`) and path-length acceptance check for `C:\BWC31` extraction.

## Private GitHub source release

- Prepared a separate synthetic-only repository derivative; the local distribution and originals remain unchanged.
- Excluded operational workbooks, governed working crosswalks, organizational maps, screenshots, snapshots, raw API material, databases, credentials, exports, and tenant configuration.
- Added small schema-preserving synthetic governance fixtures and a generic non-geographic map placeholder.
- Added automated publication-boundary checks and Windows/Linux continuous integration.
- Updated the frontend build dependency tree and added a zero-high-severity `npm audit` gate to continuous integration.
- Published as a prototype prerelease; native executable, signing, and production acceptance remain deferred.

## Deferred and unverified

- No native EXE, PyInstaller, Authenticode, RFC 3161, SmartScreen, or production endpoint acceptance is included.
- No live tenant credentials were used in development-host QA.
- Live Entra behavior and Axon read/write behavior require separately authorized receiving-environment tests.
- The existing deployment workbook is retained as a reference artifact; V3.1.0 changes the application/shared-governance layer and does not claim a new workbook repair or Excel-open validation.
