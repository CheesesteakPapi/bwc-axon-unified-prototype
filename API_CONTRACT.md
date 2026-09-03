# Local and Axon API Contract — V3.1.0

## Local-service boundary

Each browser UI talks only to its Python service on `127.0.0.1`. The launch token establishes a same-process session cookie. API credentials are submitted to process memory and are never returned to the browser after storage or written to the shared database.

Every state-changing provisioning or governance request carries the expected run or workspace revision. A stale revision returns `409 Conflict`; the operator must reload before applying a new change.

### Shared and provisioning routes

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/workspace/status` | Workspace revision, active snapshots, leases, pending summary, and audit-chain status |
| `POST` | `/api/workspace/refresh` | Start a leased Users, Groups, Devices, or Device Homes refresh from Provisioning Center |
| `GET` | `/api/workspace/refresh/{jobId}` | Read Provisioning Center refresh status |
| `POST` | `/api/workspace/refresh/{jobId}/cancel` | Terminate the local refresh process and preserve the prior baseline |
| `GET` | `/api/runs/latest` | Reopen the most recently changed run |
| `GET` | `/api/runs/{runId}` | Canonical rows, validation, generated chunks, approval, and history |
| `POST` | `/api/runs/intake/detect` | Inspect pasted, CSV, or XLSX intake and suggest column mappings |
| `POST` | `/api/runs` | Create, enrich, map, generate, validate, and persist a run |
| `POST` | `/api/runs/{runId}/edit` | Apply governed assignment edits and regenerate as a new revision |
| `POST` | `/api/runs/{runId}/approve` | Bind Preview approval to the current run revision and hashes |
| `POST` | `/api/runs/{runId}/submit-next` | Explicitly submit only the next dependency-eligible chunk |
| `POST` | `/api/runs/{runId}/track` | Poll stored Axon job IDs and record row/job results |
| `POST` | `/api/runs/{runId}/export` | Create one immutable ZIP for the current run revision |
| `POST` | `/api/runs/{runId}/purge` | Purge exactly one confirmed local run while retaining a redacted hash/count audit event |

### Geographic routes

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/live/dashboard` | Confirmed dashboard plus separately labeled pending/projected summaries |
| `GET` | `/api/workspace/pending-users` | Pending user overlays and status filters |
| `POST` | `/api/live/sync` | Start a resource-scoped, leased, read-only Axon refresh |
| `GET` | `/api/live/sync/{jobId}` | Refresh progress and counts |
| `POST` | `/api/live/sync/{jobId}/cancel` | Cooperative cancellation; prior baseline remains active |
| `GET/POST` | `/api/governance/crosswalk/{table}` | Revision-aware list, validation, governed edit, and CSV projection |

The existing health, configuration, session, memory-only credential, shutdown, download, and export routes remain supported in each component's API contract.

## Entra delegated-read contract

- The intake identifier is Email and resolves only against an exact Entra `mail` value. Email and UPN are not interchangeable.
- The user search requests only the properties needed for provisioning enrichment. The manager read uses the returned Entra object ID rather than the intake email or UPN.
- `mail` supplies Email; `userPrincipalName` supplies UPN and External ID; `mailNickname` supplies UserName and Badge Number; `givenName` and `surname` supply names; `department` supplies Component; `officeLocation` supplies Directory Location; and `jobTitle` supplies Job Title.
- Proposed Axon Status is always `Active`. Entra `accountEnabled` is retained separately as Directory Account Status and can block a disabled account for review without changing proposed Status.
- A missing required identity value is a review blocker. The provider does not replace a missing Email with UPN.
- The delegated token remains process-memory-only. No Graph write or Entra group-membership endpoint is used.

## Snapshot rules

- A resource refresh obtains a shared lease before any resource call.
- Incoming normalized rows are staged and counted before atomic activation.
- Failure or cancellation does not supersede the prior active snapshot.
- The snapshot stores source, scope, row count, content SHA-256, and activation timestamp.
- `Devices` with `model`, `status2`, or `homeId` filters uses a `filtered` scope. It cannot replace the active `full` Devices baseline.
- Opening the second application reads the active snapshot and does not trigger another Axon call.

## Axon boundary

Read operations use the documented Users, Groups, Devices, Device Homes, hierarchy, and job-status/results endpoints configured in the included components. Provisioning writes are limited to the configured user-import and Group-entity import contracts and remain behind explicit write enablement, a current Preview approval, Agency ID confirmation, chunk dependencies, and a final submission action.

No automatic write retry is permitted. A response without an unambiguous Axon job ID is recorded for reconciliation and must not be resubmitted until the external state is verified.

## Strict generated CSVs

User import header:

```text
EXTERNAL_ID,EMAIL,BADGE_NUMBER,FIRST_NAME,LAST_NAME,STATUS,USERNAME,ROLE,SUPERVISOR_EMAIL,LOCATION,EVIDENCE_GROUP_EXT_ID,PHONE
```

Group relationship header:

```text
EXTERNAL_ID,MEMBERSHIP_TYPE,ENTITY_TYPE,ENTITY_ID
```

User and Group files are UTF-8 without BOM. `EVIDENCE_GROUP_EXT_ID` remains blank. `SUPERVISOR_EMAIL` is sent; Supervisor UPN is retained for roster/review provenance and is not sent in the user import. Group display names are resolved to exact external Group IDs before generation.

Maximum chunk size is 500 records. User chunks preserve intake order and must complete before Group chunks are unlocked.
