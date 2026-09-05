# Feature enhancements

Branch: `feature/future-enhancements` · Base: `ad45d05` · Started: 2026-09-04

This backlog follows the supplied UX evaluation and the later provisioning corrections. Completed work below is a development increment; the runtime remains the Python/PowerShell prototype.

## 1. Complete inventory filtering and matching export — implemented

- Combine search, model, disposition, assignment state, Device Home, component, mapped AOR, and review flags.
- Page through the entire selected Devices snapshot, including records beyond the dashboard's 500-row preview.
- Preserve filters while navigating inside the app; removable filter chips and Reset filters explain the current view.
- Export every matching record across all pages with UTC timestamp, filter context, workspace revision, Devices snapshot ID/hash/time, and full/filtered scope.
- Export from persisted snapshots after restart without session credentials or a new Axon request.
- Reject a stale export revision and preserve unavailable-versus-zero and full-versus-filtered distinctions.
- CSV is UTF-8 without BOM and formula-safe. It is a review export, not a provisioning import file.

Verification uses 605 synthetic devices, combined filters, page 11, full matching exports, scope selection, restart, revision conflicts, concurrent governance edits, CSV injection protection, and authenticated HTTP routes. Browser checks cover navigation persistence, combined filters, paging, export confirmation, and empty results. See `FEATURE_QA.md` for actual results and limits.

## 2. Assignment investigation — next

Support full-snapshot paging; filters for role and zero, one, two, and three-or-more assigned devices; drill down from a user to exact serial numbers and disposition. Keep one Axon Role per user, allow multiple devices, and preserve unavailable counts when Devices are absent. An unusual count should become an exception only when a governed role expectation exists.

## 3. Record-level exception queue — planned

Add actionable records for lost/relinquished-but-assigned devices, unmapped Device Homes, and unclassified Groups. Include reason, source snapshot, next action, and governed local review history. Dashboard cards should open the appropriate filtered queue. Persist review ownership/status with revision protection; do not mark an Axon condition resolved just because it was locally acknowledged.

## 4. Guided connection and refresh — planned

Separate tenant settings, access testing, and resource selection. Default a first pull to a smaller scope, show applied filters before execution, and summarize per-resource results. Permission outcomes must come from actual resource responses rather than authentication alone.

## 5. Geographic drilldowns and composed reports — planned

Preserve selected component, AOR, site, and snapshot context from map to details and export. Add reviewed facility/office links, territory navigation, and composed dashboard PDF sections. Keep OCIO, HSI Domestic, ERO, and HSI International as separate lenses. State boundaries may suggest mappings only where an authoritative, dated source establishes that relationship; imported candidates require review.

## 6. Further workflow polish and pilot acceptance — planned

Add reusable saved views, snapshot differences, non-site Group classification pickers, and focused keyboard/Narrator/200% zoom acceptance. Validate authorized Entra and Axon operations on receiving Windows/macOS machines. Native executables, signing, Power BI, and SharePoint migration remain later work.

## Constraints carried forward

Personnel Location/AOR and Job Title/category mappings are optional for user import. Directory values still populate crosswalk candidates. Group selection is optional, with friendly names resolved to exact Axon IDs; recommendation rules need not have reviewed status. Email and UPN stay distinct, proposed status stays Active, supervisor Email and UPN stay separate, and Evidence Groups remain unused. Geographic Operations continues to make read-only operational Axon calls.
