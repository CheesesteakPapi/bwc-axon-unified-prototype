# Shared Data Model — V3.2.1 testing candidate

## Opt-in local credential file (outside the data model)

The optional source-testing profile described in LOCAL_TEST_CREDENTIALS.md is
not a shared SQLite dataset. It is a private per-user plaintext file independently
loaded into each process. No profile, Client ID or Client Secret is imported into
snapshots, governance projections, provisioning rows, audit events or exports.
It neither binds a tenant nor changes a workspace revision on load.

## Additive V3.2.1 migration

On opening the database, add `refresh_leases.refresh_id TEXT NOT NULL DEFAULT ''`
if absent. Existing rows, snapshots, governance, and provisioning revisions are
preserved. The original schema family marker remains 3.1.0; column existence is
checked transactionally and the migration is idempotent.

The optional `workspace_meta.tenant_host` binds this workspace to one canonical
HTTPS host. Initial binding increments the workspace revision and appends a
redacted audit event. Existing unbound snapshots/runs require explicit confirmation
at the expected workspace revision. The application cannot safely infer the tenant
of legacy data, and does not automatically relabel it.

Pending User overlay payloads may contain `confirmation` metadata: last check,
completed-job indicator, mismatched field names, and unobservable field names.
These diagnostics do not change the immutable submitted run revision. Only full
Users snapshots can confirm matching submitted records; Groups remain independent.
Reconciliation uses identity indexes and caches completed chunk row IDs per run
revision to avoid rescanning the full user list and requerying chunks for each row.

Support diagnostics use a separate bounded in-memory ring, not another database
or external telemetry service. They disappear when the service closes.

The authoritative local store is SQLite in WAL mode with foreign keys, full synchronization, and a busy timeout. It contains normalized minimum-necessary records; raw API response bodies are not a default dataset.

## Logical layers

| Layer | Main records | Rule |
|---|---|---|
| Confirmed baseline | Resource snapshots and normalized snapshot rows | Only a complete validated activation supersedes the same resource/scope |
| Pending overlay | Proposed, submitted-awaiting-confirmation, failed, and superseded user changes | Visible in both apps but excluded from confirmed metrics |
| Provisioning | Runs, immutable revisions, validation, generation, approvals, chunks, and Axon job results | The run is the workflow source of truth |
| Governance | Current governed rows, prior versions, source-file hashes, review metadata | SQLite is authoritative after one-time CSV migration |
| Control | Workspace revision, refresh leases/history, audit events | Coordinates both processes and detects stale writes |

## Snapshot identity and scope

Each snapshot records a generated snapshot ID, resource, canonical scope JSON, scope hash, row count, content hash, source, pull time, activation time, and status. Snapshot rows preserve order and a stable record key where available.

Devices activation also materializes normalized user-device relationship rows with device/user identifiers, assigned/unassigned state, device status, model, and Device Home. Inventory states such as in stock, lost, or relinquished remain source device-status values available for filtering rather than being conflated with assignment state.

Full and filtered resource scopes are independent. Confirmed dashboard consumers require an active `full` Devices snapshot. A filtered Devices pull is retained as useful scoped data without altering the full baseline; when no full baseline exists, it is displayed only as an explicitly non-confirmed filtered result.

A Geographic multi-resource refresh stages every requested resource and activates the batch in one SQLite transaction with one workspace revision. Cancellation or failure before commit activates none of the batch and preserves every prior baseline.

Confirmed geographic metrics use a crosswalk relationship only when its Site ID is nonblank and its governed Mapping Status is explicitly `Mapped`. Candidate and needs-review relationships remain outside confirmed mapping totals.

## Provisioning run

A run contains run ID, revision, state, timestamps, title, directory provider, canonical rows, validation findings, strict generated records, Preview approval, and the active snapshot IDs used by that revision.

Run states are:

```text
Draft → Enriching → Needs Review → Ready for Preview → Previewed
→ Awaiting Submission → Submitted → Monitoring → Completed / Failed
```

Any Preview edit creates a new revision, recalculates assignment dependencies, regenerates records/chunks, reruns validation, and clears stale approval. A submitted revision is not edited in place; a correction creates a follow-up revision.

## Canonical user row

Identity fields include Email, External ID, badge number, username, first name, and last name. Assignment and review fields include Role, optional friendly Group selection, Component, directory/effective Location, optional Personnel AOR, optional original Job Title, optional governed Job Category, Supervisor Email, Supervisor UPN, Rank, Axon/current state, and validation/provenance metadata. Missing optional AOR/category mappings are warnings and do not remove an otherwise eligible user record. A blank Group external ID means no Group relationship record is generated.

Status is proposed as `Active`. Directory account status is separate. Rank is optional and has no assignment effect. Entra membership is absent by design.

## Governance

Governed datasets cover directory attributes, approved Roles, personnel Location-to-AOR, exact title classification, Component/AOR/category Group rules, Axon Group hierarchy/master, facilities/office presence, Device Homes, device status, and geographic crosswalks.

Each reviewed change records expected revision, prior value, actor/reviewer, UTC time, review notes, mapping method, confidence, and an audit event. Distinct Location/Component and Job Title values observed during directory enrichment may be appended automatically as `Needs review` candidates; candidate audit events contain counts rather than user identities. Text beginning with spreadsheet formula characters is rejected before CSV projection.

## Audit

Audit records form a SHA-256 chain over event ID, timestamp, actor, type, outcome, redacted details, and the previous hash. Events identify operations and counts; they exclude credentials and raw personnel rows.
