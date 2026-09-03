# Axon BWC Provisioning Center — Unified Prototype V3.1.0

This component provides the shared-workspace workflow `Add Users → Enrich → Review Exceptions → Preview → Submit → Track`. A canonical run replaces the former download, rename, and re-upload handoffs.

Live Entra enrichment resolves the intake Email against the exact directory `mail` value. It preserves `userPrincipalName` separately as UPN and External ID, uses `mailNickname` for UserName and Badge Number, maps `department` to Component, and always proposes Axon Status as `Active` while retaining directory account state separately.

The source prototype binds only to `127.0.0.1`, opens a tokenized URL on an available port, stores non-secret working data under the signed-in user's application-data folder, and does not require administrator privileges.

Use a separate least-privilege provisioning API client. Credentials remain only in process memory. Writes are disabled by default and remain gated by a current preview, exact Agency-ID confirmation, explicit approval, and the applicable API-contract confirmation.

Axon user-import CSVs are generated and validated as UTF-8 without BOM. `EVIDENCE_GROUP_EXT_ID` remains a blank compatibility column; organizational membership is managed through separate Axon Group rows. A 404 on job status or results does not authorize resubmission.

See the package-level `README.md`, `SECURITY_MODEL.md`, and `OPERATIONS_RUNBOOK.md` for end-user and operating instructions.
