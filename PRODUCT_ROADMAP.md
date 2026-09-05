# Product ownership and remaining releases
V3.2.0 is the next controlled-testing candidate, not a promise that all future ideas are finished. Development, QA, documentation and backlog prioritization are owned together. Version numbers beyond V3.2 are provisional and depend on accepted scope.

## Release gates
1. Build and regression tests pass; source/data safety scan passes.
2. Package extracts at a short path and includes launchers and compiled assets.
3. Nontechnical operator testing validates clarity and confirms saved/approved/submitted distinctions.
4. Authorized tenant testing validates live permissions, mappings, API jobs and actual source data.
5. User approval records acceptance or sends defects back to development.

No background work or publishing is scheduled by this document. Live changes, agency policy choices and public/private repository mutations require their applicable authorization.

## Ordered backlog
| Priority / proposed release | Outcome | Exit criteria / dependency |
|---|---|---|
| P0 / V3.2 patch | Resolve acceptance defects | No unresolved data-loss, wrong-target, stale-approval or submission ambiguity defects; user retest |
| P1 / V3.3 | Finish guided setup and exception resolution | New operators can manage roles, Groups, refresh scope and mappings without file handoffs; reviewed recommendations remain distinct from confirmed values |
| P1 / V3.3 | Consistent geographic/report context | Component, AOR, site and snapshot selections retained across relevant screens; territories and non-site Groups represented without invented hierarchy |
| P1 / V3.4 | Restore program reporting inputs | Inventory historical R/Tableau extracts, transformations and schedules; source owners validate sample outputs; broken dependencies replaced with approved connectors or file contracts |
| P2 / V3.4 | Leadership reporting projection | Define approved aggregate metrics, suppression and provenance; explicitly separate personnel-level operational exports from leadership data |
| P2 / later | Power BI / SharePoint integration | Approved destination, refresh identity, data contract and access controls; privately tested presentation first. Historical brainstorms are not an existing Axon connector |
| Deferred | Native desktop production release | Only after stable workflow: build/signing credentials, endpoint security, platform acceptance and support ownership |

State boundaries: OCIO, HSI Domestic, ERO and HSI International are separate organizational lenses. Co-located offices share physical facilities but not inferred command ownership. State boundaries are candidate mapping evidence, never automatic authority for every personnel AOR.

## Definition of finished for testing
A reproducible package, tested code, known-limitations list, current manual, change log and acceptance checklist. Finished for production additionally requires platform, security, agency and live-tenant acceptance; those cannot be inferred from local synthetic tests.
