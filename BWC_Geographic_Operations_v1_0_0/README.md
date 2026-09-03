# BWC Geographic Operations — Unified Prototype V3.1.0

This component provides the shared dashboard, mapping, metrics, inventory, assignment, export, and governed-table interface. It consumes confirmed snapshots and visibly separate provisioning overlays from the common V3.1 SQLite workspace.

The source prototype binds only to `127.0.0.1`, opens a tokenized URL on an available port, stores working data under the signed-in user's application-data folder, and does not require administrator privileges.

Axon operational calls are read-only GET requests. OAuth token acquisition is the only POST. Credentials remain only in process memory and are cleared through **Exit app**. Completed normalized snapshots persist so the second application does not repeat the same Axon pull.

Organizational mapping is based on reviewed command hierarchy and Axon Groups. Users, roles, device assignments, similar names, and geography are not treated as proof of a site relationship. Co-located components and non-ICE or non-networked facilities remain distinct in the governed facility and office-presence model.

See the package-level `README.md`, `SECURITY_MODEL.md`, and `OPERATIONS_RUNBOOK.md` for end-user and operating instructions.
