# Axon API Contract — BWC Reporting

This file records the API facts validated from the program documentation supplied in Google Drive.

| Resource | Method / endpoint | Read permission / control | Pagination / limit | Primary reporting use |
|---|---|---|---|---|
| OAuth token | `POST /api/oauth2/token` | API client ID + secret | Token response includes expiration | Authenticate integration |
| Users | `GET /api/v4/agencies/{agencyId}/users` | `users.read` | `limit` 1–500; `offset`; response pagination link may be present | User/account facts only; no site mapping |
| Devices | `GET /api/v1/agencies/{agencyId}/devices` | `device.any.read` | `limit` 1–100; `offset`; documented `model` accepts one model or a comma-separated list; filters also include `status2`, `ownerId`, `homeId`, last upload window | Device inventory, assignment, status, firmware, home |
| Device hierarchy | `GET /api/v1/agencies/{agencyId}/hierarchy/{groupId}/children` | `groups.read` | On-demand only; device/group API traffic is paced at five seconds where documented | Validate reviewed command hierarchy; never infer a site from a User |
| Groups | `GET /api/v1/agencies/{agencyId}/groups` | Read access to Groups; exact current UI label should be verified | Optional `externalId`; older guide does not document list pagination | Axon Group master / command-hierarchy crosswalk and non-site register |
| Device Homes | `GET /api/v1/agencies/{agencyId}/devices/homes/list` | 2023 access table maps this GET to Partner `any.read`; verify current UI | No URL parameters documented | Device Home master/crosswalk |

## Documented field highlights

### Users v4
The Partner API guide describes user records with fields including internal ID, status, first/last name, email, badge number, external ID, updated date, last login, and relationships to Role; user relationships are not used for BWC site mapping.

### Devices v1
The Partner API guide describes device fields including internal ID, `serial`, `model`, `friendlyName`, `status2`, `errorStatus`, `firmwareVersion`, `lastUploadDateTime`, `dateAssigned`, `homeId`, `dateCreated`, `dateModified`, and an owner relationship.

`status2` is the current device-status filter/attribute in the supplied All Devices documentation; the older `status` parameter is deprecated.

The current Device Search documentation states that client requests are throttled by IP to one request every five seconds. The prototype therefore paces Device-list pagination at five seconds by default. This does not bypass or replace a `429` response; `Retry-After` handling remains in place.

### Groups v1
The guide describes internal group ID plus `externalId`, `name`, `status`, `shareAccess`, `is_coaching_group`, `createdOn`, and `updatedOn`.

The Group Hierarchy endpoint is a read-only review mechanism. It is only invoked for explicit Group IDs supplied by the operator, because bulk hierarchy traversal would create avoidable API volume and requires a distinct `groups.read` permission.

### User roles and device assignments

User records provide the assigned role/profile field. A user can have zero, one, or many devices. The prototype preserves that one-to-many relationship in `reports.user_device_assignment_summary_YYYY-MM-DD.csv`; it does not derive a BWC site from the user record.

### Device disposition and reporting states

Raw Axon device status remains preserved in `axon_devices.csv`. The operator maps each reviewed raw status in `device_status_map.csv` to a reporting state, such as `Assigned`, `Unassigned`, `In Stock`, `Lost`, or `Relinquished`. The output reports separately show raw status, reporting state, and whether an owner is present; no status is inferred from the other two values.

### Device Homes
The supplied guide describes Device Home ID, name, and point-of-contact ID. However, the current observed Device Homes list payload must be treated as name-only until an authorized tenant probe confirms that an immutable ID is present.

## Error behavior

Axon's API response/error guide specifies:

- 5XX: exponential-backoff retry.
- 429: follow `Retry-After`.
- If 429 has no usable `Retry-After`, wait at least 5 minutes.
- Device Search: one request every five seconds per IP, according to the supplied current documentation.

## Security / administration

Axon's API Settings documentation says:

- API clients are deny-by-default.
- Administrators explicitly allow operations per resource.
- IP/CIDR allowlisting is available.
- Client Secret, Client ID, and Partner ID are shown when the client is created; the secret must be retained securely.
- API credentials must not be shared with unapproved third parties.

## BWC-specific implementation findings

The existing ICE BWC Device Management script uses the manual Device Summary export and derives component from **Device Home**. Its key reporting fields include:

- Device Model
- Device Name
- Serial Number
- Device Status
- Assigned user's First Name / Last Name / Badge ID
- Last Connected Dock
- Device Home

The program's current observed Device Homes list does not establish a stable Device Home ID, so the provisional bridge is **reviewed normalized Device Home name ↔ Site ID**. Duplicate and rename exceptions must be reviewed; switch to an immutable ID only after an authorized tenant probe confirms it is exposed.

The existing API review also concluded that Partner API pulls can replace the manual Evidence Created, User Summary, and Device Summary extraction steps over time. Axon Performance/Metrics exports were not identified as Partner API resources and should remain a separate process unless newer Axon documentation establishes otherwise.

## Source files

- Authentication and authorization.pdf
  https://drive.google.com/file/d/1Gce0pC0SKKv5a6StMgM-ZttmblIpYtKn/view
- All users.pdf
  https://drive.google.com/file/d/1d88gTob0I5m9wtYCZvxT7AvhqQJkFJV7/view
- All devices.pdf
  https://drive.google.com/file/d/1bIOx4oyMp-q2SxY1OP2iolIxrEXak6zm/view
- Axon Evidence Partner API Guide_Rev A 2023_Jan.pdf
  https://drive.google.com/file/d/1qJbRIIJDojlCukOtbEgc0Tuagn0AkmZn/view
- API Responses and Error Handling.pdf
  https://drive.google.com/file/d/1GxX67jgvCM5DZoiGQUN-pRPNs8ryOoD_/view
- API Settings.pdf
  https://drive.google.com/file/d/1OFMbRn90JDC7-5QKelIOJ2Ah2bMy0rfa/view
- Axon_Evidence_API_PowerBI_Integration_Guide.pdf
  https://drive.google.com/file/d/11VCrw0gseONVHp6iU9ndIZzX0toOVFNT/view
- Synchronize Axon and Dataverse.md
  https://drive.google.com/file/d/1Gv8gC6eemGW1p4DfBFpup4We8HGJO5kh/view
- Axon API review.md
  https://drive.google.com/file/d/1X9vhyaIHpgmiKqHz2VrIVVy4qtc1WsoG/view
- ICE BWC Device Management Report Script.md
  https://drive.google.com/file/d/1lrGUUifDUS8tKcW1jxIRzKixowFQ-j4h/view

## Command hierarchy and Axon Groups

BWC organizational/site mapping is governed by the reviewed command hierarchy and Axon Group IDs. User records are not a site-mapping source. A Group that does not represent a BWC office belongs in the non-site Group register rather than being forced into an Office Location ID.

## Explicitly excluded write operations

The supplied User Import, import-job status, and import-job result documents were reviewed. They are deliberately excluded from this prototype. User import is a write operation, and `synchronize=true` can deactivate active users absent from the submitted CSV. As of the supplied documentation's July 30, 2026 permission change, user-import operations require `users.import` (or legacy grandfathered access). No write permission is requested or exercised by this package.

## Shared local governance contract — V2.3.5

In this sanitized source repository, configured crosswalk and status paths resolve from `config.example.json` to package-level synthetic `governance_starters/`. Relative paths resolve from the configuration file's folder instead of the caller's current directory. Runtime-reviewed data belongs in the per-user application workspace and must not be committed.

The synchronization prototype reads governed mappings but never writes Axon records. The local Geographic Operations UI remains the primary editor for the shared working files.

## Additional current documentation reviewed for V2.3.5

- All devices
- Device search
- Device details and Device details by serial number
- All users and User details
- Get group hierarchy
- Request a new token
- Overview and best practices
- Manage users, import-job status, job results, and job queue (reviewed only; excluded from runtime)
