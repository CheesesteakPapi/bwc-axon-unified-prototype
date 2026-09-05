# Local and Axon API Contract — V3.1.0

## Local-service boundary

Each browser UI talks only to its Python service on `127.0.0.1`. The launch token establishes a same-process session cookie. API credentials are submitted to process memory and are never returned to the browser after storage or written to the shared database.

Revision-sensitive provisioning requests carry the expected run revision. Governance updates carry expected row values; the server captures the dataset revision during the same read and uses SQLite compare-and-swap. A stale row or cross-process revision race returns `409 Conflict`, and the operator must reload before applying a new change.

### Shared and provisioning routes

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/workspace/status` | Workspace revision, active snapshots, leases, pending summary, and audit-chain status |
| `GET` | `/api/catalogs/groups` | Current friendly Group choices from the active Groups snapshot or local Group master |
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
| `GET` | `/api/live/dashboard` | Confirmed full baseline, or an explicitly labeled filtered/partial view, plus separate pending/projected summaries |
| `GET` | `/api/inventory` | Feature branch: filter and page every device in the saved full baseline or explicitly scoped filtered fallback |
| `GET` | `/api/inventory/export` | Feature branch: export all matching devices with snapshot/filter provenance and a required current `expectedRevision` |
| `GET` | `/api/workspace/pending-users` | Pending user overlays and status filters |
| `POST` | `/api/live/sync` | Start a resource-scoped, leased, read-only Axon refresh |
| `GET` | `/api/live/sync/{jobId}` | Refresh progress and counts |
| `POST` | `/api/live/sync/{jobId}/cancel` | Cooperative cancellation; prior baseline remains active |
| `GET` | `/api/crosswalks/{key}` | Revision-aware search and paging for one governed table |
| `POST` | `/api/crosswalks/{key}/rows/{rowNumber}` | Validate and update one governed row |
| `POST` | `/api/crosswalks/{key}/rows` | Add a row when the governed table permits creation |
| `GET` | `/api/crosswalks/{key}/export` | Generate and export the complete governed CSV projection from authoritative SQLite at request time |

The existing health, configuration, session, memory-only credential, shutdown, download, and export routes remain supported in each component's API contract.

## Entra delegated-read contract

- The intake identifier is Email and resolves only against an exact Entra `mail` value. Email and UPN are not interchangeable.
- The user search requests only the properties needed for provisioning enrichment. The manager read uses the returned Entra object ID rather than the intake email or UPN.
- `mail` supplies Email; `userPrincipalName` supplies UPN and External ID; `mailNickname` supplies UserName and Badge Number; `givenName` and `surname` supply names; `department` supplies Component; `officeLocation` supplies Directory Location; and `jobTitle` supplies Job Title.
- Proposed Axon Status is always `Active`. Entra `accountEnabled` is retained separately as Directory Account Status and can block a disabled account for review without changing proposed Status.
- A missing required identity value is a review blocker. The provider does not replace a missing Email with UPN.
- Directory Location and Job Title are enrichment inputs, not user-import requirements. A missing reviewed Location/AOR or title/category mapping creates a non-blocking warning and queues each distinct observed value in the governed crosswalk as `Needs review`, with the directory provider recorded as provenance.
- The delegated token remains process-memory-only. No Graph write or Entra group-membership endpoint is used.

## Snapshot rules

- A resource refresh obtains a shared lease before any resource call.
- Incoming normalized rows are staged and counted before atomic activation. A Geographic multi-resource refresh activates every requested snapshot in one SQLite transaction and one workspace revision only after all resources validate. Dashboard snapshot rows, metadata, pending overlays, and that revision are read in one SQLite transaction so a response cannot mix pre- and post-refresh generations; only the selected full baselines or filtered Devices fallback have row payloads loaded.
- Failure or cancellation before that commit activates none of the pending snapshots and does not supersede any prior active baseline.
- The snapshot stores source, scope, row count, content SHA-256, and activation timestamp.
- `Devices` with `model`, `status2`, or `homeId` filters uses a `filtered` scope. It cannot replace the active `full` Devices baseline. If no full baseline exists, its dashboard view is explicitly labeled `FILTERED RESULT` and is not represented as confirmed metrics.
- A partial view without any Devices scope reports device metrics and user-device counts as unavailable and does not offer device-derived CSV exports; unknown relationships are never converted to zero.
- Opening the second application reads the active snapshot and does not trigger another Axon call.

## Axon boundary

Read operations use the documented Users, Groups, Devices, Device Homes, hierarchy, and job-status/results endpoints configured in the included components. Provisioning writes are limited to the configured user-import and Group-entity import contracts and remain behind explicit write enablement, a current Preview approval, Agency ID confirmation, chunk dependencies, and a final submission action.

No automatic write retry is permitted. A response without an unambiguous Axon job ID is recorded for reconciliation and must not be resubmitted until the external state is verified.

## Strict generated CSVs

User import header:

```text
EXTERNAL_ID,EMAIL,BADGE_NUMBER,FIRST_NAME,LAST_NAME,STATUS,USERNAME,ROLE,SUPERVISOR_EMAIL,LOCATION,EVIDENCE_GROUP_EXT_ID,PHONE,RANK
```

Group relationship header:

```text
EXTERNAL_ID,MEMBERSHIP_TYPE,ENTITY_TYPE,ENTITY_ID
```

User and Group files are UTF-8 without BOM. `EVIDENCE_GROUP_EXT_ID` remains blank. `SUPERVISOR_EMAIL` is sent; Supervisor UPN is retained for roster/review provenance and is not sent in the user import. `LOCATION` may be blank. Job Title and Job Category are not user-import columns. A selected Group display name is resolved to an exact external Group ID before generation; a blank or unresolved optional Group produces no Group relationship row while the eligible user row remains available.

Maximum chunk size is 500 records. User chunks preserve intake order and must complete before Group chunks are unlocked.
