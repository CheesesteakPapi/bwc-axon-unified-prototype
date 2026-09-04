# Data Handling and Security Boundary

## Axon operations

- OAuth token acquisition: `POST /api/oauth2/token`.
- Operational resources: read-only `GET` requests.
- No user import, device update, Group update, assignment change, or other Axon write is implemented.

## Credential handling

- Partner / Agency ID, Client ID, Client Secret, and OAuth token are held only in the local Python process.
- They are not placed in URL parameters, browser storage, `config.json`, CSV exports, or application logs.
- The session can be cleared from the connection dialog and is cleared when the backend exits.
- Structural configuration validation intentionally does not authenticate credentials.

## Live-row handling

- Mapped live rows and generated session exports use a temporary operating-system folder.
- The temporary folder is deleted at normal backend shutdown.
- Raw Axon JSON retention is forced off for the UI workflow.
- Explicitly downloaded files are outside cleanup and must be stored in an approved location.

## Persistent local governance data

- The repository contains only synthetic Device Home, Group, Facility, Office Presence, relationship, and status starter CSVs. Reviewed working values are created in the per-user runtime workspace and must remain outside version control.
- Each successful in-app update/create commits the authoritative shared SQLite revision first, then attempts to copy and refresh the CSV review/export projection. A projection or backup failure is reported as a warning and does not falsely roll back the committed SQLite change.
- Local writes use allowlisted fields, controlled values, expected-value conflict checks, reference validation, and spreadsheet-formula-prefix rejection.
- The backups are on the same local disk and have no built-in retention or restore workflow.
- Governed-table requests and CSV projection exports always report `axonWrite: false` and never call Axon. Exports are generated from authoritative SQLite at request time; the file-governed device-status map is read directly from its current reviewed file.

## Local exposure controls

- The application binds only to `127.0.0.1`.
- State-changing routes require the local-host boundary and a dedicated local-UI request header. The header is not authentication.
- Host-header checks reject non-local hosts.
- Browser security headers restrict framing, referrers, scripts, images, and network connections.
- Absolute pagination links are accepted only on the configured tenant host.

## Mapping and tenant-truth boundary

- Existing Site IDs are preserved as Office Location IDs; no physical Facility ID is inferred.
- Facility, co-location, host organization, occupancy, geocoding, network environment, and operational state remain pending until reviewed.
- Device Home names are normalized only for review; no immutable Device Home ID is inferred.
- Axon Groups may be primary, secondary, organizational-area, additional, command, role-related, training, administrative, enterprise, or other. Non-site Groups remain explicitly non-site.
- Group parent, tier, membership, and site relationship are not inferred from User records, names, or map placement.
- The current live Users pull does not observe tiered Group memberships; blank live membership fields are intentional.
- Organizational boundaries and suggested geographic relationships remain illustrative and provisional until governed approval.

## Prototype boundary

This is a private, short-lived, single-operator local sandbox. It does not provide multi-user authentication, role-based administration, centralized audit, records retention automation, or agency approval. Power BI/SharePoint migration requires a separate architecture, privacy, security, and governance review.
