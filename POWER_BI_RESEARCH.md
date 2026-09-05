# Leadership reporting workstream — discovery

Status: research only; separate from operator UI implementation. Suggested future branch: research/powerbi-leadership. No Power BI service, tenant, gateway, or connector was configured.

User clarification, 2026-09-04: there is no existing Axon connector. The Power BI integration material is historical requirements and experimentation. The former reporting workflow used R extracts and transformations to feed Tableau and is now nonoperational; it was not a fielded R-dashboard replacement. Treat historical documentation, executable source, and proposed improvements as separate evidence classes.

## Material found and inspected

| Artifact | What it contributes | Limit |
|---|---|---|
| BWC-Automation R starter, README and source inspection | QA gates, normalized output, export manifest/hash pattern | Data pipeline scaffold, not a demonstrated R dashboard |
| Original Trends R Markdown source | File-based evidence/user imports, deployment/training and incident-summary dependencies, category breakout, historical CSVs and PowerPoint generation | Static source inspection only; not run or accepted as current business policy |
| Nine legacy report-analysis Markdown documents | Deployment, trends, uncategorized evidence, device management/utilization, risk, audit, incident reporting and archive requirements | Narratives with excerpts and hypothetical examples; not nine verified executable scripts; some are incomplete |
| Power BI & Axon Evidence API Integration guide, two pages | Historical token/query/pagination discussion | ChatGPT-assisted reference, not verified Axon documentation or a validated connector |
| Axon Partner API (Dataverse Integration), Swagger 2.0 JSON | Historical proposed user/device read operations and import-job structure | Draft API design artifact only; no existing or deployed connector; includes a proposed user-import write |
| Deployment Control Hub Power BI dashboard-layout and semantic-model docs | Leadership questions, dimensions/facts, drillthrough, ranked-location fallback, restricted-detail separation | Earlier Dataverse-first design, not the current SQLite prototype or evidence that all metrics are available |

Original files remain unchanged. No raw source rows, credentials, PBIX model content, or agency artifact copies are included in this repository.

## Recommended initial boundary

Approved source adapters (existing shared Axon snapshots plus separately approved program feeds) → staged validation and normalization → versioned reporting datasets → local program reports and approved aggregate Power BI export.

Evidence metadata, training records, and incident data are additional source domains, not fields assumed to exist in the current Users/Groups/Devices baseline. Reuse existing snapshots where sufficient; establish new extraction contracts only for missing approved sources. Keep restricted evidence/incident processing separate from the general operator workspace, exposing only reviewed minimum-necessary outputs.

Start with a synthetic export/import proof of concept. The operational app remains the editable source. Do not create a second uncontrolled Axon pull merely to display a report, expose the tokenized localhost endpoint, or add account/device writes to reporting. Service refresh needs an approved reachable storage or gateway path; the local per-user SQLite file is not automatically accessible to Power BI service.

Use separate confirmed, pending, and planning datasets with explicit provenance. Exclude pending values from confirmed metrics. Preserve snapshot IDs, per-resource times, complete/filtered scope, metric definitions, and denominators in reporting metadata. Historical charts require historical observations; do not manufacture trends from one snapshot.

## Leadership questions and model

Candidate first questions, awaiting user priorities: Where is deployment progressing? Where is inventory available or constrained? Which sites need intervention?

Begin with an executive report page, a deployment/location comparison page, and a data-freshness/definitions page. Prefer rankings and comparison bars before maps. Component, organizational lens, area, and phase filters must keep their distinct meanings. Training, connectivity, costs, milestones, and readiness need approved sources before becoming reported measures.

Use dimensions for the chosen organizational/geographic grain, dates, and deployment phase, with separate inventory, deployment, and exception facts. Validate co-located office versus physical-site grain before counting sites or joining assignments. One user may have multiple devices; organizational Groups may have no geographic relationship.

Leadership data should exclude names, email/UPN, badge numbers, device serials, and free-text notes by default. Aggregate results can still be sensitive: classification, suppression thresholds, permitted geography, audience, export rights, and workspace controls require owner review. Hiding a column or hashing identifiers alone is not a privacy boundary.

## Reuse cautions and verified platform considerations

- The older guide suggests turning off privacy levels. Do not adopt that workaround; resolve source/privacy configuration appropriately. Revalidate endpoints, authentication, pagination, throttling, and failure behavior against the current approved Axon contract.
- Keep user-import operations described in the draft API artifact outside the read-only reporting design.
- Microsoft documents star-schema modeling for usable Power BI models: [Model guidance](https://learn.microsoft.com/en-us/power-bi/guidance/star-schema).
- A custom connector working in Desktop is not sufficient for gateway refresh; Microsoft documents additional requirements including TestConnection: [Gateway custom connectors](https://learn.microsoft.com/en-us/power-bi/connect-data/service-gateway-custom-connectors).
- Government clouds have different endpoints and feature availability. The current comparison lists Azure Maps unavailable in GCC, GCC High, and DoD, so do not commit to that map visual before tenant verification: [Government-cloud guidance](https://learn.microsoft.com/en-us/fabric/enterprise/powerbi/service-government-us-overview).

## Discovery gates before integration

Confirm the three leadership questions, available original scripts/Tableau workbook or screenshots, source owners and schemas, tenant/cloud, approved service and workspace, audience/licensing, refresh cadence/owner, gateway or storage availability, geographic source permissions, data classification, and export policy. Compare approved file-based ingestion with any newly authorized source adapters; do not plan around an existing connector. No publish-to-web or public sharing is proposed.

## Legacy research findings

- Most reusable: source contracts, separate inventory/assignment measures, age-based review queues, explicit reporting periods, geographic comparison and reproducible report packages.
- Trends source directly shows unconditional final-row removal; Group-name-derived geography; repeated history append without a uniqueness guard; original history timestamps replaced with the current run date; and a weekly label applied to aggregates without an explicit matching date filter.
- Training percentages use camera counts as their denominator. Retain this only as a clearly labeled historical ratio unless the program owner approves that definition; do not represent it as personnel training completion.
- Device-usage analysis describes no-recording matches as non-active devices. A missing recording match is not proof of non-use or noncompliance; reporting scope, assignment dates, inventory state and delayed uploads matter.
- Audit/risk and incident narratives contain historical policy assumptions and possible defects. They require original source and owner verification, not automatic adoption.
- The R starter's output targets do not reference its QA-gate target. If reused, make validation an explicit dependency of publication and test failure behavior. Hashing identifiers does not make a dataset anonymous.

Recommended sequence: inventory and deployment reporting first; recording activity and categorization next after approved metadata access; restricted incident/audit reporting later. Reuse the logic selectively behind source-independent tests; do not execute the legacy monolith inside the operator UI.

Research deliverables remain local and uncommitted. Source artifacts were not changed or copied into this repository. No live extracts, legacy R execution, API calls to agency systems, or Power BI publishing occurred.
