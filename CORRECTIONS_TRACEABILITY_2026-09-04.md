# Corrections Traceability — 2026-09-04

This checklist records the user-confirmed corrections represented in the current V3.1.0 source update. It contains no tenant data.

| Confirmed correction | Implemented behavior | Primary verification |
|---|---|---|
| Email and UPN are different organizational fields | Entra intake resolves exact `mail`; `userPrincipalName` remains a separate UPN and supplies External ID | `test_entra_delegated_read_resolves_exact_mail_and_maps_distinct_upn` |
| UserName and Badge Number use the directory alias | Both map from `mailNickname` | Entra delegated-read test |
| First and last names use Given Name and Surname | `givenName` maps to First Name; `surname` maps to Last Name | Entra delegated-read test |
| Proposed account status defaults to Active | Generated user records always propose `Active`; directory account status remains separate | Entra and synthetic workflow tests |
| Supervisor Email and Supervisor UPN are separate | Both remain distinct in the canonical row; only Supervisor Email is sent in the user import | Workflow generation tests and API contract |
| Entra membership does not establish Axon Group membership | No Graph group-membership endpoint is called; organizational membership uses optional Axon Group relationship rows | Entra provider implementation and API contract |
| Evidence Groups are not used | `EVIDENCE_GROUP_EXT_ID` is always blank for compatibility | Synthetic workflow test |
| Role remains required | Intake requires Email and Role, and Role must exist in the approved Axon Role catalog | Header detection and validation tests |
| Personnel Location/AOR is optional for user import | A missing reviewed Location-to-AOR mapping creates a warning, not a blocker; the directory Location may still be generated | Optional-mapping workflow test |
| New Location/Component values should reach the crosswalk | Distinct observed values are added once to the shared Personnel Location-to-AOR dataset as `Needs review` candidates | Candidate creation and deduplication test |
| Job Title is not required for user import | Blank Job Title has no blocker; a returned but unmapped title creates a warning | Optional-mapping workflow test |
| New Job Titles should reach the crosswalk | Distinct returned titles are added once to the shared exact-title/category dataset as `Needs review` candidates | Candidate creation and deduplication test |
| Component/AOR/category Group rules do not require reviewed status | Any matching rule except one explicitly marked `Inactive` may produce a recommendation | Non-reviewed Group-rule test |
| Group assignment is optional | Recommendations are displayed separately. Only a deliberate Group selection generates a Group relationship row; blank or unresolved Group does not block the user row | Group select/clear workflow test |
| Group selection should use a drop-down | Intake, Preview, and bulk editing use the current Groups snapshot or local Group master, with Component/AOR/tier context | Provisioning UI build and `/api/catalogs/groups` backend test |
| Crosswalk changes should be visible in both apps | Candidate rows are committed to the shared SQLite governance datasets and increment the shared workspace revision | Shared-workspace audit/revision test and Geographic crosswalk reader |
| Concurrent crosswalk edits must not overwrite newer work | Each update compares expected row values and the dataset revision captured during the same read; a cross-process race returns `409 Conflict` | Cross-process revision-conflict regression test |
| Runtime syncs and exports must use current governed values | Application-initiated sync/export projections are generated from authoritative SQLite at request time; the separately file-governed status map always uses its current file | SQLite-authority, export, and current-status-map regression tests |
| Multi-resource refreshes must not partially replace baselines | Geographic resources activate together in one SQLite transaction and one workspace revision only after every requested resource validates; dashboard rows, metadata, overlays, and revision are also read in one bounded transaction; cancellation/failure activates none | Atomic batch, forced-interleaving read, bounded-scope read, and canceled-pull regression tests |
| Filtered Devices results are not a complete baseline | An existing full baseline remains the confirmed dashboard; without one, the result is explicitly labeled filtered and its metrics are scoped, never presented as confirmed zero-device truth | Full-then-filtered and first-filtered-pull regression tests |
| Confirmed mapping metrics must use reviewed relationships | A Site ID contributes only when the governed Device Home or Group crosswalk row is explicitly `Mapped`; candidate and needs-review rows remain review-only | Geographic mapping-metric regression tests |
| Reviewed AOR labels should remain usable | Geographic summaries preserve the governed Region/AOR label after an explicit mapped relationship | Geographic mapping-metric regression test |

## Blocker boundary after correction

The correction does not remove genuine user-import safeguards. Examples that remain blockers include invalid or duplicate Email, missing exact directory match, disabled directory account pending explicit review, missing required identity output, missing Role, empty approved Role catalog, and a Role not present in that catalog.

Optional mapping and Group findings remain visible as warnings so they can be reviewed without stopping an otherwise valid user import.
