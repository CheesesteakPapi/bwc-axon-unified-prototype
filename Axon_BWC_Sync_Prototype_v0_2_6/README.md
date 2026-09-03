# Axon Evidence → BWC Reporting Prototype v0.2.6

This read-only utility now participates in the V3.1 shared-workspace refresh lease and snapshot model. A completed resource pull is atomically activated in the same SQLite workspace used by Provisioning Center and Geographic Operations. A filtered Devices pull is stored as a filtered scope and never replaces or masquerades as the complete Devices baseline.

This package is the read-only ingestion companion for the modernized BWC Deployment Plan.

## What changed after reviewing the program's Axon API documentation

The prototype now uses the actual documented contracts:

- **OAuth token** — `POST /api/oauth2/token`
- **Users** — `GET /api/v4/agencies/{agencyId}/users` (`users.read`, limit up to 500)
- **Devices** — `GET /api/v1/agencies/{agencyId}/devices` (`device.any.read`, limit up to 100)
- **Groups** — `GET /api/v1/agencies/{agencyId}/groups`
- **Device Homes** — `GET /api/v1/agencies/{agencyId}/devices/homes/list`
- **Group hierarchy (on demand)** — `GET /api/v1/agencies/{agencyId}/hierarchy/{groupId}/children` (`groups.read`)

The **Partner ID is the Agency ID used in resource paths. It is not sent in the OAuth token request body.**

## Command hierarchy, Axon Groups, and Device Homes

Axon operational device placement is represented by **Device Home**. BWC organizational reporting uses the reviewed **command hierarchy** and **Axon Groups** and does not derive site mappings from Users.

For BWC deployment reporting:

- `Normalized Device Home Name → BWC Site ID` is the current device/site bridge. It requires duplicate/rename review because a stable Device Home ID was not observed in the current Device Homes list payload.
- `Reviewed Axon Group ID → BWC Site ID` is the organizational bridge, governed by the command hierarchy. Users are account/profile data only.

Do not use Users to infer a site. Use reviewed command-hierarchy and Axon Group mappings for organization, and Device Homes for equipment location.

## Security defaults

- There are **no Axon write methods** in `axon_sync.py`.
- Resource operations are GET-only.
- The only POST is OAuth token acquisition.
- Secrets are read from environment variables.
- Raw JSON retention is **off by default**, because Users/Devices responses can contain PII.
- HTTP 429 follows `Retry-After`; when absent the code waits the Axon-documented minimum of 5 minutes.
- 5XX errors use exponential backoff.
- Device-list requests are paced at **one request every five seconds** by default, reflecting the current Device Search throttling documentation.

### Required environment variables

```text
AXON_PARTNER_ID
AXON_CLIENT_ID
AXON_CLIENT_SECRET
```

Set them using an agency-approved secret store or execution environment. Do not save credentials in Excel, `config.json`, Git, email, tickets, or chat.

## Configure

Copy:

```text
config.example.json -> config.json
```

Change only:

```json
"agency_base_url": "https://YOUR_AGENCY.evidence.com"
```

The documented endpoint paths, page limits, and field mappings are already populated.

## Validate without contacting Axon

```bash
python axon_sync.py validate --config config.json
```

## Safe schema probes

Probe a few records without retaining raw response values:

```bash
python axon_sync.py probe --config config.json --resource Users
python axon_sync.py probe --config config.json --resource Devices
```

Schema summaries are written to `data/schemas/`. Raw JSON is not saved unless `keep_raw_json` is explicitly set to `true`.

## Shared governance files

Inside this sanitized source repository, `config.example.json` points to package-level synthetic `governance_starters/`. Relative paths are resolved from the configuration file's folder, so validation and synchronization do not depend on the shell's starting directory. Copy reviewed values into the per-user runtime workspace; never commit operational data.

Populate these working files after the first authorized sync and review:

- `device_home_crosswalk_starter.csv`
- `axon_group_crosswalk_starter.csv`
- `axon_non_site_group_register_starter.csv`
- `device_status_map.csv`

The adjacent UI is the primary editor for the working files. The CSV copies retained in this component folder are compatibility fallbacks only and are not used by the packaged configuration.

Use stable Axon Group IDs for command-hierarchy/site joins; do not use Users as a site-mapping source. For Device Homes, use the reviewed normalized-name key until Axon confirms that the current Device Homes list exposes an immutable identifier. Names are therefore an exception path that requires duplicate/rename review.

### Groups that are not sites

Not every Axon Group should map to a BWC Site ID. Keep direct office/site mappings in `axon_group_crosswalk_starter.csv`. Add reviewed enterprise, component, role, training, supervisory, administrative, or other non-site groups to `axon_non_site_group_register_starter.csv` instead. The Groups output preserves both categories:

- `Site-Mapped` — a reviewed Group ID ↔ BWC Site ID relationship.
- `Non-Site` — a legitimate organizational group with no site mapping; classify its hierarchy level and reporting inclusion.
- `Unclassified` — requires review; do not force it into a site.

This keeps command hierarchy intact without using user membership to invent a location.

## Full read-only sync

```bash
python axon_sync.py sync --config config.json
```

The default dependency order is:

```text
Device Homes → Groups → Users → Devices
```

Processed outputs land in `data/processed/`.

### Targeted Device syncs

The Devices endpoint accepts a model string, including a comma-separated model list. Use the exact Axon strings.

```bash
python axon_sync.py sync --config config.json --resource Devices --device-model "MODEL_A,MODEL_B"
```

You can combine the documented model filter with one exact `status2` value or one exact `homeId` value:

```bash
python axon_sync.py sync --config config.json --resource Devices --device-model "MODEL_A" --device-status "STATUS_VALUE"
python axon_sync.py sync --config config.json --resource Devices --device-home-id "HOME_ID"
```

The filter changes only the read request; it does not modify Axon records. Device pages remain paced at five seconds to avoid the documented per-IP throttle.

### On-demand hierarchy validation

Do not request hierarchy for every group by default. It is an explicit, rate-paced verification step for the group IDs under review:

```bash
python axon_sync.py hierarchy --config config.json --group-id "GROUP_ID"
```

Repeat `--group-id` for additional reviewed roots. The result is written to `data/processed/axon_group_hierarchy_YYYY-MM-DD.csv`.

The sync also creates transition files using the naming/columns expected by the existing BWC analytics workflow:

- `reports.devicesSummary_API_YYYY-MM-DD.csv`
- `reports.userSummary_for_All_users_API_YYYY-MM-DD.csv`
- `reports.user_device_assignment_summary_YYYY-MM-DD.csv` — users, roles, and zero/one/many assigned-device counts.
- `reports.device_status_summary_YYYY-MM-DD.csv` — model/status/assignment-state counts for filtering and reconciliation.
- `reports.device_assignment_and_status_exceptions_YYYY-MM-DD.csv` — unassigned, in-stock, lost, relinquished, unmapped, or site-unmapped device rows requiring review.

### Device state control

Maintain the exact Axon raw status in `device_status_map.csv` and map it to one approved reporting state. Do not infer a status from assignment alone. The recommended reporting-state vocabulary is `Assigned`, `Unassigned`, `In Stock`, `Lost`, `Relinquished`, `Inactive`, `Retired`, `Repair / Maintenance`, `Other`, or `Needs Review`. Only enter a mapping after confirming the raw Axon status definition for the tenant.

### Known parity gap

The supplied Partner API documentation does not establish that the **All Devices** response exposes the same **Last Connected Dock** field used by the manual Device Summary export. The compatibility export therefore leaves that field blank unless a tenant probe proves an API field exists.

Do not remove the manual Device Summary path solely for that field until parity is validated.

## Recommended production architecture

```text
Axon Evidence Partner API
          ↓
Approved scheduled runtime
(Azure Function / automation service)
          ↓
Dataverse / SQL / Fabric landing tables
          ↓
Power BI + SharePoint portfolio site
          ↓
Excel operational planning as needed
```

A direct Power BI-to-Axon connection is technically possible, but a server-side integration is preferable for credential governance, retry handling, auditing, and reuse across reports.

## Source documents used

See `API_CONTRACT.md` for the exact source documents from the BWC Google Drive folder.

## V0.2.1 patch

- Aligns Device Home processing and its starter crosswalk with the observed name-only Device Homes list.
- Keeps the name-based bridge explicitly provisional; do not treat a normalized name as an immutable Axon identifier.

## V0.2.2 correction

- Removes obsolete group fields and user-to-site enrichment.
- Uses reviewed command hierarchy and Axon Group IDs for organizational/site mapping.

## V0.2.3 AOR correction

Operational AOR values are governed local data. The published source contains only synthetic examples and does not infer or distribute office-to-AOR mappings.

## V0.2.4 API and reporting patch

- Adds explicit `--device-model`, `--device-status`, and `--device-home-id` read-only filters.
- Adds five-second pacing for Device-list pagination and hierarchy validation.
- Adds on-demand Group Hierarchy retrieval; it is not run automatically for all groups.
- Separates valid non-site groups from site mappings through a dedicated review register.
- Adds user-role/device-assignment, device-status, and exception reports, preserving one user ↔ many devices.
- Keeps all User Import and job endpoints out of the prototype; no Axon write behavior has been added.

## V0.2.5 distribution integration

- Resolves configured file paths from the configuration file's folder.
- Uses the V2.3.5 package-level shared governance working files.
- Retains the cross-host pagination guard before forwarding the access token.
- Keeps validation structural; credentials are intentionally tested only during an authorized live operation.
