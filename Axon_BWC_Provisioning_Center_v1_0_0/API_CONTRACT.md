# API Contract — Axon BWC Provisioning Center v1.0.0

The v1.0.0 local web UI invokes these endpoint contracts through the packaged local service. Browser code never calls Axon directly and never receives API credentials.

## Implemented endpoints

| Purpose | Method and endpoint | Permission | Prototype behavior |
|---|---|---|---|
| Submit user import | `POST /api/v4/agencies/{agencyId}/users/import` | `users.import` after 30 July 2026 | Multipart CSV; always `synchronize=false` and `synchronizeEvidenceGroups=false`; existing-account updates are allowed only through the reviewed exact-preview gate |
| List user jobs | `GET /api/v4/agencies/{agencyId}/users/import/status` | `users.import` | Read-only job summary |
| User job status | `GET /api/v4/agencies/{agencyId}/users/import/{jobId}/status` | `users.import` | Read-only status check |
| User job results | `GET /api/v4/agencies/{agencyId}/users/import/{jobId}/results` | `users.import` | Up to 500 results per page; summary by action/error |
| Submit group entities | `POST /api/v2/agencies/{agencyId}/groups/import/entities` | `groups.modify` | Adds members/monitors for referenced groups |
| List group jobs | `GET /api/v2/agencies/{agencyId}/groups/import` | `groups.modify` | Read-only job summary |
| Group job status | `GET /api/v2/agencies/{agencyId}/groups/import/{jobId}` | `groups.modify` | Read-only status check |
| Group job results | `GET /api/v2/agencies/{agencyId}/groups/import/{jobId}/results` | `groups.modify` | Up to 500 results per page |
| Current users | `GET /api/v4/agencies/{agencyId}/users` | `users.read` | Existing read-only sync provides before/after snapshots |
| Current groups | `GET /api/v1/agencies/{agencyId}/groups` | `groups.read` | Existing read-only sync validates external group IDs |

## CSV contracts

User import requires these headers in any order:

```text
EXTERNAL_ID,EMAIL,BADGE_NUMBER,FIRST_NAME,LAST_NAME,STATUS,USERNAME,ROLE,SUPERVISOR_EMAIL,LOCATION,EVIDENCE_GROUP_EXT_ID,PHONE
```

`RANK`, `LOCATION`, and `SUPERVISOR_EMAIL` may be blank. Job Title and Job Category are review metadata and are not user-import columns. `EMAIL`, `USERNAME`, and `BADGE_NUMBER` must be unique, and `ROLE` must resolve to the approved Role catalog. Populated reference values should retain their source/review basis. The compatibility column `EVIDENCE_GROUP_EXT_ID` remains blank in generated files because BWC organizational assignments are handled separately through optional Axon Group entity rows.

The user-import CSV must be UTF-8 without a byte-order mark. V0.4.2 generates plain UTF-8 user files and treats a BOM as a validation error before submission. The Group entity encoding contract remains subject to confirmation with the authorized API documentation.

Group entity import requires exactly these logical fields:

```text
EXTERNAL_ID,MEMBERSHIP_TYPE,ENTITY_TYPE,ENTITY_ID
```

- `EXTERNAL_ID`: target group's existing external ID, maximum 255 characters.
- `MEMBERSHIP_TYPE`: `MEMBER` or `MONITOR`.
- `ENTITY_TYPE`: `USER` or `GROUP`.
- `ENTITY_ID`: user email for `USER`; external group ID for `GROUP`.

Each row creates one relationship. A user assigned to two groups requires two rows.

## Preview downloads and cleanup contract

Preview user accounts analyzes the selected user CSV against the selected current Users snapshot without contacting Axon. It creates two temporary local downloads:

- `<source name>_new_accounts.csv` includes create candidates that have no row blocker.
- `<source name>_matched_accounts.csv` includes rows matched to existing accounts so the proposed updates can be reviewed separately.

Both files retain the selected source file's headers, header order, row order, and source values. Internal preview fields are not inserted into either CSV.

Create clean copy is also a local-only operation. By default, the cleanup window selects all applicable blocked rows and existing-account matches for removal. It writes a separate `<source name>_clean_create_only.csv`, selects that generated session copy, and previews it again against the same Users snapshot. It never edits or overwrites the uploaded source CSV. Rows involved in duplicate unique identifiers are all treated as blockers; the cleanup does not choose an arbitrary duplicate to keep.

Files created by preview or cleanup are temporary session artifacts. The operator must download any file that needs to be retained before the local application exits.

## Existing-account update approval contract

Existing-account updates are off by default. The UI exposes **Allow updates to these _N_ reviewed accounts** only after the matched-account view has been opened and the preview has no blockers.

The approval is bound to the latest preview record, including:

- The selected user CSV path and SHA-256 hash.
- The selected Users snapshot path and SHA-256 hash.
- The exact displayed existing-account match count.
- The preview's blocker and structural-error state.

The UI clears the approval when either selected file changes or a replacement preview is run. At submission, the local backend independently rejects a missing or stale preview, changed file hash, changed snapshot hash, match-count mismatch, or any remaining row or file-level blocker.

Passing that gate only permits the guarded command to include its allow-updates option. The final write still requires Axon-changing functions to be enabled, the full Partner / Agency ID to match the credential session, confirmation of the displayed preview scope, and a second UI confirmation for the exact number of existing accounts that may be updated.

## Job-state model

```text
queued → processing → success
                    ↘ error
```

User result actions documented by Axon include `Created`, `Removed`, `Updated`, and `Skipped`. A successful overall job may still contain row-level errors, so results must be reviewed before group assignment.

A `404` from a job status or results lookup is not evidence that the original submission failed. Run the corresponding list-jobs function, compare the exact returned job ID, and retry only the read-only lookup. Do not resubmit a file solely because a status/results URL returned 404.

## Documented safeguards

- User `synchronize=true` can deactivate active users absent from the CSV. The application does not expose this mode.
- `synchronizeEvidenceGroups` is also fixed to `false`; group membership is handled separately through the group-entity job.
- Existing-account updates require the latest exact-preview approval and exact reviewed match count; a general or reusable update permission is not accepted.
- Group entity import affects only the target groups referenced in column A and adds the supplied relationships.
- A write is submitted once and is not automatically retried after an ambiguous failure.
- User-import CSVs are generated and validated as UTF-8 without BOM.
- External IDs are treated as stable source identifiers. Changing a user's external ID can cause Axon to create a separate account.

## Documentation gaps and discrepancies

1. The clipped group-entity reference omits the multipart Body Params field name. `entities_file` is provisional and must be confirmed in the authorized Axon API Explorer before executing that POST.
2. The user job-results page source URL and endpoint are v4, but one paragraph refers to a v2 submit operation. This application consistently uses the v4 user-import family shown by the current source URLs and status/result endpoints.
3. Some supplied documentation describes group entity enum values as case-insensitive. Templates use uppercase values for portability and reviewability.

## Permissions boundary

Use a separate provisioning API client with only:

```text
users.read
users.import
groups.read
groups.modify
```

Do not add unrelated Evidence, Cases, Devices, Reports, or administrative write permissions.
