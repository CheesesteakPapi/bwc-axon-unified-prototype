# Security and Privacy Model — V3.1.0

- Services bind only to `127.0.0.1` and start with `--open --auto-port`.
- A per-launch token is exchanged for a local session cookie. A bare loopback URL is not an authenticated application session.
- Credentials remain in the owning process's memory. The shared SQLite workspace, configuration, browser response payloads, audit log, and exports do not contain API secrets.
- Entra access is delegated read-only `User.Read.All`; no Graph write, Group-membership, daemon, or application permission is part of the prototype.
- Geographic resource operations and the sync utility are GET-only after OAuth token acquisition.
- Provisioning writes require enabled write mode, current Preview approval, exact Agency ID confirmation, eligible chunk state, and a separate final action.
- The system never automatically retries an ambiguous write.
- Imported XLSX files are read as ZIP/XML values. Macros, formulas, external links, and embedded objects are not executed.
- CSV/XLSX text is normalized and spreadsheet-formula prefixes are rejected from governed projections.
- Raw API responses are not retained by default. Normalized, minimum-necessary baseline and provisioning data persist locally.
- Hash-chained audit events record actor, action, outcome, revision, IDs, and counts without credentials or complete personnel rows.
- Confirmed and pending data are separate. Pending proposals cannot become confirmed merely through local approval or successful submission; a subsequent validated Axon snapshot is required.
- Refresh leases prevent duplicate local pulls of the same resource. Staging and atomic activation preserve a prior baseline after failure or cancellation.
- The package is not a signed production desktop application. Local source integrity is checked through the included SHA-256 manifest.
