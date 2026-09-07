# Local and Axon API Contract — V3.2.1 testing candidate

## Opt-in local testing credential profile — 2026-09-07

Normal source entry points may read one private local Axon testing profile.
Session construction in tests/library use does not auto-load it. The
`--no-test-credentials` flag disables loading; frozen/native entry points do not
enable it. Loading validates structure/access/target only, not Axon credentials.
No new credential download or file-writing HTTP endpoint exists.

Session metadata adds `credentialSource` (`session` or `local-test-file`),
`testCredentialsLoaded`, `testCredentialTarget` (canonical HTTPS origin),
`credentialWarning` (redacted actionable message), and `credentialValidation`
(`not-verified`: loading does not verify remote authentication). No Client ID,
Client Secret or full Partner ID is exposed by these additions.

For a file-loaded Provisioning session, a write request can replace
`confirmAgency` with `confirmTarget: true` and `targetOrigin` equal to the exact
loaded canonical origin. The configured tenant must still match; the server
supplies the held Partner ID to the existing CLI internally. Manual sessions
continue requiring `confirmAgency`. This does not bypass `confirmWrite`, run
approval/revision, write enablement, tenant binding or eligible-chunk checks.
Clear-session endpoints remove in-memory credentials only, not the on-disk file.

## Bulk governance review

Authenticated Geographic endpoint: `POST /api/crosswalks/{key}/bulk`.
The existing local session/CSRF boundary applies. Request fields:

- `mode`: `preview` or `apply`.
- `expectedRevision`: table revision returned by the crosswalk list endpoint.
- `rowNumbers`: explicit unique 1-based table row numbers; alternatively
  `allMatching: true` with `search` uses the identical trimmed listing predicate.
- `changes`: shared field/value object restricted to returned `bulkEditableFields`.
- `reason`: required 1–1,000 characters; formula/control-character protections apply.
- `previewHash`: required for apply, binding table, revision, exact selection,
  fields and reason to a previously reviewed preview.

Returns selected/changed/unchanged counts and per-row before/after differences.
The limit is 1,500 selected rows; identity/key fields and direct note replacement
are prohibited. Apply revalidates the entire batch and uniqueness before one
revision-protected SQLite commit, then regenerates its CSV projection. Conflicts
return 409; invalid inputs return the existing validation error response. No Axon
API is invoked. Projection warnings distinguish a committed database change from
an export failure. Preview hashes detect stale/tampered intent; they are not an
authorization credential or a replacement for the local authenticated session.

Provisioning bulk review uses the existing run-edit endpoint with explicit row
IDs and assignment-only edits. Its client preview is a proposed difference list,
not a claim of successful validation; save recalculates the whole run and may
return Needs Review. A new revision invalidates previous submission approval.

## V3.2.1 contract additions

- Both authenticated services expose `GET /api/support/diagnostics`. It returns
  the last 200 local requests in the current process: request ID, method, UTC time,
  HTTP status, and duration only. No routes, URLs, payloads, credentials, or personnel
  values are retained. Responses carry `X-BWC-Request-ID`. Diagnostics never trigger
  Axon calls; storage is volatile and failures cannot fail a business operation.
- Public configuration includes `tenantHost`, `legacyBindingRequired`, and
  `workspaceRevision`. Configuration saves accept `confirmLegacyTenant: true`
  and `expectedWorkspaceRevision` to bind existing unbound snapshots/runs once.
  Missing confirmation or another tenant is rejected; stale revision returns 409.
  There is no rebind operation. A different tenant requires a separate workspace.
- Geographic `POST /api/review/relationships` accepts `key` (device-homes or
  axon-groups), `targetRowNumber`, `expectedRevision`, and `values`. It creates
  an additional reviewed relationship to an existing site, with locked site
  metadata, the current field validation, identity uniqueness, audit, and revision
  conflict checks. It changes local governance only, never Axon.
- Geographic dashboard `resourceFreshness` describes each selected resource's
  snapshot ID, activation time, and scope. A latest-activity timestamp must not
  be interpreted as the age of every resource. Review rows include `isReviewed`;
  the reviewed queue includes completed decisions rather than filtering them out
  before the operator chooses a filter.
- Run responses include `confirmationSummary`; pending overlay payloads may
  include `confirmation` with mismatched/unobservable field names. A completed
  user job is not itself confirmed Axon state. Confirmation requires a full Users
  snapshot, unique matching Email AND External ID, and matching observable
  submitted values. Missing fields remain unverified. Group job completion is
  tracked separately and is never inferred from a Users snapshot.
- Refresh acquisition starts a renewable heartbeat (normally every 30 seconds).
  Activation validates the unique lease token and expiry inside the same SQLite
  transaction. An expired/replaced worker cannot activate or release its successor.
  All application refresh callers pass their lease token. No Axon delta feed,
  automatic write retry, or faster vendor response time is claimed.

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
| `GET` | `/api/assignments` | Feature branch: search and page the saved Users snapshot by role and scoped device count |
| `GET` | `/api/assignments/devices` | Feature branch: page exact device records for one unique `userId`; requires current `expectedRevision` |
| `GET` | `/api/assignments/export` | Feature branch: export all matching user assignment summaries with Users/Devices provenance; requires current `expectedRevision` |
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

## V3.2.0 additive interface
Authenticated loopback GET `/api/catalogs/roles` returns `{"roles": ["approved display name"]}`.
Read-only; uses the same active/approved catalog predicate as provisioning validation. Preserves display casing and updates after workspace revisions. No tenant call, credentials or write permission is required.
Personnel mapping continues to use the existing crosswalk row endpoint, `changes` plus `expected` prior values. The guided UI writes review status `Approved`, not `Reviewed`. Existing conflict responses and audit behavior are unchanged.
