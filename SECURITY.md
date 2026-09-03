# Security and data-handling policy

## Repository classification

This repository is intended to remain private. It contains application source, documentation, and synthetic fixtures only. Repository privacy is an access control, not authorization to store agency operational data.

Never commit:

- Axon or Microsoft access tokens, client secrets, Partner/Agency IDs, private keys, or populated `.env` files.
- Tenant URLs, tenant-specific identifiers, user rosters, email addresses, badge numbers, supervisor data, or directory exports.
- Axon Users, Groups, Devices, or Device Homes snapshots, including filtered snapshots.
- Deployment workbooks, working crosswalks, facilities, office presences, coordinates, organizational maps, raw API responses, schemas derived from live responses, job results, or exported provisioning packages.
- SQLite databases, WAL/SHM files, logs, screenshots, PDFs, or other operational artifacts.

Runtime credentials must remain in process memory. Runtime records belong only in the approved per-user workspace and remain outside version control.

## Required pre-publish check

Run from the repository root:

```powershell
python scripts\check_publish_safety.py
```

The same check runs in GitHub Actions. It blocks prohibited file types and common credential, tenant, identity, and absolute-path patterns. It cannot determine classification or replace human review.

## Reporting a problem

Do not open a public issue containing security details or operational data. Notify the repository owner through an approved private channel. If sensitive material is ever committed, revoke affected credentials, restrict access, preserve the incident record, and follow the organization's incident-response and repository-history-remediation process.
