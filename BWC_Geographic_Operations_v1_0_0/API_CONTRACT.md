# Axon and Local API Contract — Unified Prototype V3.1.0

## Release boundary

V3.1.0 preserves the read-only Axon contract, governed-table controls, progress metadata, and safe local cancellation. Completed normalized snapshots, governance rows, and pending provisioning overlays use the signed-in user's shared SQLite workspace.

No Geographic Operations Axon write, credential store, automatic organizational inference, or automatic approval is added. Governed changes are revision-aware SQLite transactions with CSV projections.

## Axon method boundary

- OAuth token acquisition: `POST /api/oauth2/token`.
- Operational resources: `GET` only.
- Excluded: user import, device mutation, Group mutation, assignment change, and every other Axon write.

## Local UI routes

The browser connects only to the packaged backend on `127.0.0.1`.

| Route | Method | Purpose |
|---|---|---|
| `/api/health` | `GET` | Runtime, build, and read-only readiness |
| `/api/session` | `GET` | Non-secret session state and masked Partner / Agency ID |
| `/api/config` | `GET`, `POST` | Tenant URL and timeout only |
| `/api/session/credentials` | `POST`, `DELETE` | Set or clear memory-only credentials |
| `/api/live/sync` | `POST` | Start a background GET-only pull |
| `/api/live/sync/{jobId}` | `GET` | Read pull status and counts |
| `/api/live/sync/{jobId}/cancel` | `POST` | Request a local stop between read-only resource requests; does not send a write to Axon |
| `/api/live/dashboard` | `GET` | Confirmed full baseline or explicitly labeled filtered/partial payload read with its matching workspace revision, snapshot metadata, and pending overlays in one SQLite transaction |
| `/api/inventory` | `GET` | Full saved inventory filtering, facets, counts, and paging beyond the 500-row dashboard preview |
| `/api/inventory/export` | `GET` | CSV of all matching saved devices, requiring the viewed `expectedRevision` |
| `/api/live/export/{resource}` | `GET` | Download a temporary current-session export |
| `/api/governance/summary` | `GET` | Read local facility, office, Group, and relationship totals |
| `/api/crosswalks/{key}` | `GET` | Search and page one allowlisted local table |
| `/api/crosswalks/{key}/rows/{rowNumber}` | `POST` | Update allowlisted fields with expected-value checks |
| `/api/crosswalks/{key}/rows` | `POST` | Add a row only when the table's `allowCreate` is true |
| `/api/crosswalks/{key}/export` | `GET` | Generate the full governed CSV projection from authoritative SQLite at request time |

Configuration validation is structural and intentionally does not authenticate. Credentials are checked only when Axon processes a live request.

Live-job responses include `status`, `phase`, `resources`, `completedResources`, `resourceCounts`, `currentResource`, `currentPage`, `receivedRecords`, `cancelRequested`, timestamps, and a bounded error message. A cancel request changes only local job state. The backend checks it after authentication and between resource-page requests; a completed prior dashboard snapshot is not replaced by a canceled partial pull.

## Local governed-table contract

Inventory query keys are `search`, `model`, `disposition`, `assignmentState`, `deviceHome`, `component`, `regionAor`, `exceptionsOnly`, `page`, `pageSize`, and `expectedRevision`. Selection filters use exact values from returned facets; search is case-insensitive. Filters combine with AND. Page size is 1–200 (default 50). Duplicate or unsupported keys return 400. The response includes full/filtered/unavailable `mode`, `deviceSnapshot`, `workspaceRevision`, `filters`, `scopeTotal`, `total`, `page`, `totalPages`, and `rows`. No Devices snapshot yields unavailable scope and a null scope count.

Inventory export uses the same filter selection over every matching row, regardless of page. It generates UTF-8 without BOM with formula-safe cells and per-row scope, snapshot identity/hash/time, workspace revision, filters, and export UTC. An absent expected revision returns 400; a stale revision or concurrent governance/snapshot change returns 409. A full Devices baseline is preferred over newer filtered scopes; when no full baseline exists the filtered snapshot is explicitly identified. Both routes read locally persisted snapshots without credentials or Axon calls. Temporary session exports at `/api/live/export/*` retain their existing behavior.

| Key | File | Locked fields | Creation |
|---|---|---|---|
| `approved-roles` | `approved_axon_role_catalog.csv` | None | Yes |
| `personnel-aor` | `personnel_location_aor_crosswalk.csv` | None | Yes |
| `job-categories` | `job_title_category_mapping.csv` | None | Yes |
| `group-rules` | `component_aor_group_rules.csv` | None | Yes |
| `directory-attributes` | `directory_attribute_mapping.csv` | Canonical Field | No |
| `device-homes` | `device_home_crosswalk_starter.csv` | Office/site and geography fields | No |
| `axon-groups` | `axon_group_crosswalk_starter.csv` | Office/site and geography fields | No |
| `non-site-groups` | `axon_non_site_group_register_starter.csv` | None | Yes |
| `facility-master` | `facility_master_starter.csv` | None | Yes |
| `office-presences` | `office_presence_starter.csv` | Office Location ID, Component, Region / AOR, Office Name, City, State, Site Code / DCO | No |
| `group-master` | `axon_group_master_starter.csv` | None | Yes |
| `site-group-relationships` | `site_group_relationship_starter.csv` | None | Yes |

`GET /api/crosswalks/{key}` accepts `page`, `pageSize`, and case-insensitive `search`. The UI uses 25 rows per page; the API caps a page at 200. The response includes `allowCreate`, `storage: shared-sqlite`, and `axonWrite: false`.

Only a Device Home or Axon Group crosswalk row with a nonblank Site ID and an explicit `Mapping Status` of `Mapped` participates in confirmed geographic metrics. Candidate, needs-review, and other unapproved rows remain visible for review but do not count as mapped.

The export route generates the complete current CSV projection from authoritative SQLite, not from the visible page, search result, or an older disk projection. `device_status_map.csv` remains a governed file without an in-app route until exact raw tenant `status2` values are observed and reviewed; runtime syncs read its current file and match statuses case-insensitively.

## Local write safeguards

- Every state-changing request must pass the valid local-host boundary and `X-BWC-Local-UI: 1` request guard. The header is not authentication or authorization.
- Updates include `changes` and the full `expected` row. Any mismatch returns `409 Conflict` before writing.
- Submitted editable values are trimmed. A value beginning with `=`, `+`, `-`, or `@` is rejected before backup creation or file replacement.
- Exact IDs and table-specific uniqueness are validated.
- Each successful update or creation commits a revision-aware SQLite transaction first, using the dataset revision captured during the same read. The application then attempts a timestamped backup and CSV projection refresh with the header and encoding preserved. If that secondary operation fails, the authoritative SQLite commit remains and the response reports a projection warning.

Geographic multi-resource pulls stage every requested snapshot and activate the complete batch in one SQLite transaction and one workspace revision. Cancellation or failure before commit activates none of the pending batch. Filtered Devices snapshots never replace confirmed full-device metrics; a first filtered-only result is labeled as filtered rather than as a complete baseline.

### V3.1.0 storage roots

- The per-user shared SQLite workspace is authoritative after initial migration.
- `BWC_GOVERNANCE_ROOT` identifies the governed CSV projection and backup workspace.
- `BWC_GOVERNANCE_STARTER_ROOT` identifies the pristine starter directory.
- Missing working files are copied from starters at startup; existing files are never overwritten by initialization.
- The macOS and Windows source launchers resolve both values under the signed-in user's application-data root.
- There is no delete route.
- Local writes never call Axon.

## Table-specific validation

### Facility Master

- Creation requires Facility ID and Facility Name.
- Latitude and Longitude must be supplied together, be numeric, and fall in valid ranges.
- Externally hosted occupancy requires Host Organization.
- `Validated` requires reviewed mapping method, rated confidence, and review notes.

### Office Presence

- A populated Facility ID must already exist in Facility Master.
- `Linked` requires Facility ID, reviewed mapping method, rated confidence, and review notes.
- Office Location IDs are preserved and cannot be created or edited in this table.

### Tiered Group Master

- Creation requires exact observed Axon Group ID and Group Name.
- Parent Group ID cannot point to the same Group and must already exist locally.
- `Classified` requires Group Purpose, Group Tier, Command Hierarchy Level, Site Relationship, rated confidence, and review notes.

### Site-to-Group relationships

- Creation requires an existing Office Location ID, existing Axon Group ID, and Relationship Type.
- A populated Facility ID must exist in Facility Master.
- Office Location ID + Axon Group ID + Relationship Type must be unique.
- `Mapped` requires reviewed mapping method, rated confidence, and review notes.

## User, role, Group, and device contract

The user payload contains exactly one `role` field. `roleException` is true when the role is missing or appears to contain multiple semicolon-delimited values.

Users may have zero, one, or multiple devices. The assignment report preserves device count and model summary without deriving a site from the User record.

The payload reserves these membership fields:

- `primaryGroup`
- `secondaryGroup`
- `organizationalAreaGroups`
- `additionalGroupCount`

The current live Users pull contract does not observe those memberships. They remain blank/zero with `groupDataStatus: Not observed in the current Users pull contract`. The backend does not infer membership from a role, name, email, office, device, or geography.

## Axon resource contract

| Resource | Method / endpoint | Primary use |
|---|---|---|
| Users | `GET /api/v4/agencies/{agencyId}/users` | Account facts and one role/profile field; never site inference |
| Devices | `GET /api/v1/agencies/{agencyId}/devices` | Inventory, owner, model, status, firmware, and home |
| Groups | `GET /api/v1/agencies/{agencyId}/groups` | Exact observed Group master values |
| Group hierarchy | `GET /api/v1/agencies/{agencyId}/hierarchy/{groupId}/children` | Explicit operator-supplied hierarchy review only |
| Device Homes | `GET /api/v1/agencies/{agencyId}/devices/homes/list` | Observed Device Home values for reviewed crosswalks |

Device Search is paced at one request every five seconds. `429` follows `Retry-After`; retryable server errors use bounded backoff. An absolute pagination URL must remain on the configured tenant host before a bearer token is forwarded.

### Device filters

| UI filter | Axon parameter | Rule |
|---|---|---|
| Device model | `model` | One exact model or comma-separated exact model strings |
| Exact device status2 | `status2` | Exact value |
| Exact Device Home ID | `homeId` | Exact value |

## Facility and organizational boundary

- Existing Site IDs are relabeled Office Location IDs in the new model; their values do not change.
- Facility IDs are locally governed physical-location keys, not inferred Axon IDs.
- One Facility may host multiple Office Locations and components.
- Network environment is recorded per Office Presence.
- Axon Groups and reviewed command hierarchy support organizational mapping. User records do not establish a site.
- One Group may relate to many offices; one office may relate to many Groups; a Group may also be explicitly non-site.
- OCIO Areas, HSI Domestic AORs, ERO Field Office AORs, and HSI International remain separate lenses.

## Export contract

- Persistent local-table CSV export returns the full current governed projection.
- Live-session CSV exports contain the complete current temporary resource/report rows.
- Illustrative current-view CSVs are created in the browser from the labeled current view.
- PDF uses a dedicated scoped report preview. macOS operators choose PDF > Save as PDF; Windows operators choose Microsoft Print to PDF.
- Export never writes to Axon.

## Credential and data lifetime

Client ID, Client Secret, and token remain only in the running Python process. The application does not persist them to `config.json`, browser storage, logs, or exports. Only tenant URL and timeout may be saved. Live rows and generated server-side session exports use a temporary directory removed at normal shutdown. The shared SQLite workspace, governed CSV projections, their backups, and explicitly downloaded files persist.

## Explicitly excluded operations

User import and import-job operations remain excluded. They are writes and can have consequential tenant effects. No user, device, Group, assignment, facility, or crosswalk change is sent to Axon by this package.
