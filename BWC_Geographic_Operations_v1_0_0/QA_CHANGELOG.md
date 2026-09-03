# QA and Change Log — v0.3.0

## V2.3.6 macOS implementation

The V2.3.5 distribution and v0.2.2 UI remain unchanged. This release is a preserved-copy UX and macOS implementation patch.

### Workflow changes

- Replaced very wide editable crosswalk, facility, office-presence, Group, and relationship grids with a master-detail editor: searchable record list on the left, focused governed fields on the right, and source/locked fields in a collapsed disclosure.
- Added multi-record staging and **Save all changes**. The server still performs one validated atomic row save and timestamped backup per record, so a later failure reports how many earlier records were saved.
- Added a reviewed bulk-link helper for co-located Office Presences. It stages an existing Facility ID, `Linked` state, mapping method, confidence, and review notes across selected office records. It does not infer links from name, city, address, component, or geography.
- Moved Crosswalk review state filtering into the Crosswalk page and kept component filtering only on pages where it changes live metrics or inventory.
- Added a dedicated Map page with actionable marker selection, a details panel, explicit provisional status, and routing to mapping or facility review.
- Reworked Exceptions as task-oriented links. Group classification now opens the Tiered Group Master directly.
- Added a scoped report preview containing data mode, component, organizational lens, timestamp, metrics, selected map, priority review list, calculation, and provenance before PDF output.
- Replaced static report sample rows with CSV generated from the currently stated illustrative scope.
- Reduced Settings to the implemented default organizational-view preference and connection entry point; removed no-op preferences.

### Long-pull changes

- Progress remains visible in the application shell after the connection dialog is closed.
- Jobs now report current resource, page, cumulative records for the resource, completed resources, and completed counts.
- Added **Stop after request**. Cancellation is local and checked after authentication and between read-only API requests. A canceled partial pull never replaces the prior dashboard snapshot.

### Responsive, state, and accessibility changes

- Replaced the narrow icon-only navigation strip with a labeled expandable mobile menu.
- Changed governance tabs to a two-column mobile layout and stacked list/detail editors without document-level horizontal overflow.
- Added explicit demo-data banner and stronger scoped export/PDF labels.
- Darkened amber text for improved contrast and retained non-color selected, changed, warning, error, and live-state treatments.
- Preserved skip navigation, visible focus, dialog focus containment, labeled controls, table captions, status regions, and reduced-motion behavior.
- This is accessibility hardening, not a formal WCAG or Section 508 certification.

### macOS implementation

- Added `Launch_Axon_Geographic_UI_macOS.command`, with shared governance paths, Python 3.10 check, production-build check, loopback-only startup, and error guidance.
- Added `MACOS_QUICKSTART.md`, including first-run security guidance, long-pull operation, macOS Save as PDF steps, troubleshooting, and clean shutdown.
- Added occupied-port recovery to the shared backend. Both platform launchers prefer 8798 and automatically select the next available loopback port when an earlier local session is still running.
- Retained the Windows launcher and quick start for cross-platform continuity.

### Verification for v0.3.0

- Production web build: passed.
- Sites compatibility tests: passed, 4 of 4.
- Backend unit tests: passed, 21 of 21, including safe cancellation, progress metadata, and occupied-port recovery.
- Python compilation: passed.
- Final browser and archive verification results are recorded at package level in `QA_VALIDATION.json`.

## V2.3.5 integrated distribution verification

- This copy is embedded in `BWC_Axon_Integration_Distribution_V2_3_5`; the standalone v0.2.2 package remains unchanged.
- The Windows launcher initializes the per-user working area from package-level synthetic `governance_starters`; operational working data is not committed.
- Missing-only initialization and preservation of existing working files are covered by an added backend test.
- Final integrated run: 19 backend tests passed, 4 Sites worker tests passed, production build passed, and loopback health/governance/table smoke checks passed.
- Development dependencies were removed after the production build.

## Release relationship

v0.2.2 is maintained in a separate package folder. The original v0.2.1 folder remains unchanged. Earlier verification is baseline history and does not automatically validate this release.

## Added

- Facilities navigation and workspace.
- Header-only Facility Master with reviewed physical-location, host, occupancy, geocoding, and validation fields.
- Office Presence register containing 481 preserved Office Location IDs, with Facility link, presence type, network environment, operational state, method, confidence, and notes.
- Users & Access navigation and workspace.
- One-role-per-user review with tiered Group fields and zero/one/many device summary.
- Header-only Tiered Group Master with exact observed IDs/names, purpose, tier, parent, command level, organizational lens, area, site relationship, and review fields.
- Header-only many-to-many Site-to-Group relationship register.
- Local governance summary route and metric cards.
- Current-view access CSV export.
- `FACILITY_GROUP_MODEL_GUIDE.md`.

## Changed

- Existing Site IDs are relabeled Office Location IDs in the new facility model without changing their values.
- Physical Facility, organizational Office Presence, network environment, and Group relationship are now independent concepts.
- Navigation renames Assignments to Device Assignments and adds Facilities and Users & Access.
- User records expose one role field. Missing/multi-value role text is reported as an exception.
- Live tiered Group membership fields remain blank and explicitly Not observed until an approved source supplies them.
- Non-site classification uses `Role-related` rather than treating a role-related Group as the user's single role.
- Documentation now explains co-location, another-agency hosting, non-ICE network states, tiered Groups, and many-to-many relationships.

## Validation and write controls

- Facility coordinates require a valid pair and range.
- Externally hosted facilities require Host Organization.
- Office Presence links require an existing Facility ID and reviewed evidence.
- Parent Group IDs must exist and cannot self-reference.
- Site-to-Group references must exist; composite relationships must be unique.
- Final workflow states require reviewed method, rated confidence, and notes.
- Existing local-host, expected-value conflict, timestamped backup, atomic replacement, encoding, controlled-value, and formula-prefix safeguards remain.
- Every local write remains `axonWrite: false`.

## Verification recorded for v0.2.2

- Production web build: passed.
- Sites compatibility tests: passed, 4 of 4.
- Python compilation: passed.
- Backend unit tests: passed, 18 of 18, including local allowlists, atomic backup/write, formula-prefix rejection, facility/office reference validation, tiered Group parent rules, composite relationship uniqueness, exact IDs, read-only sync, and credential non-exposure.
- Structural configuration validation: passed and correctly stated that credentials are intentionally not checked.
- Browser interaction review: desktop and 390-by-844 phone layouts passed for Facilities, Office Presence, User access, Tiered Group Master, Site-to-Group relationships, role filtering, row selection, and form controls.
- Browser console errors: none in the reviewed v0.2.2 session.
- CSV integrity: passed for UTF-8 BOM, CRLF, governed headers, 481 unique Office Location IDs, unlinked starter defaults, network/scope pending states, operational validation state, no HSI office-type prefix in Region / AOR, and header-only Facility/Group/relationship masters.
- Package hygiene: passed with no credentials, `config.json`, backups, logs, cache directories, `node_modules`, or prohibited terminology in the distribution.
- Archive integrity: passed with no compressed-data errors.
- Extracted-package smoke: passed for versioned health, static UI, local governance summary, 481-row Office Presence route, and `axonWrite: false`.
- SHA-256 checksum: generated beside the final ZIP.

## Retained operational guardrails

- Standalone local Windows 11 prototype bound to `127.0.0.1`.
- Axon operational resources remain GET-only; token acquisition is the only Axon POST.
- Credentials and token remain process-memory only.
- Raw JSON retention remains disabled.
- Device model, exact `status2`, and exact `homeId` filters are sent before pagination.
- Device pacing, retry handling, cross-host pagination rejection, and exact-identifier rules remain.
- CSV and Microsoft Print to PDF workflows remain available.
- Four organizational map lenses remain separate, illustrative, and provisional.

## Known limitations

- No live tenant pull or tenant data is bundled.
- Facility Master, Tiered Group Master, and Site-to-Group relationship starters are intentionally empty until reviewed source records are entered.
- Current live Users data does not populate tiered Group memberships.
- No in-app row deletion or backup restore/retention workflow.
- No Windows 11 launcher, Microsoft Print to PDF, or live Axon tenant test was run in the macOS development environment.
- No multi-user authentication, centralized audit, durable approval workflow, Power BI, or SharePoint deployment.
- Accessibility improvements are not a formal WCAG conformance certification.
