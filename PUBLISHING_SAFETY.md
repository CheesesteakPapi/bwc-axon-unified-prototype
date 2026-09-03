# GitHub publishing safety record

## V3.1.0 publication boundary

The GitHub source tree was created as a clean derivative. The original local distribution remains unchanged.

Excluded from version control:

- Deployment workbook and office-document exports.
- The 482-row working and starter crosswalk copies from the local distribution.
- Supplied organizational map images and UI/design screenshots.
- OpenAI hosting metadata and deployment-specific build artifacts.
- `node_modules`, Python caches, local virtual environments, generated databases, snapshots, raw/processed API data, logs, exports, and populated configuration.
- Native executable, signing, notarization, and acceptance artifacts, because V3.1.0 is a Python/PowerShell prototype.

Repository fixtures are deliberately small and use `DEMO`, `TEST`, `Example`, `Synthetic`, and reserved placeholder values. The generic SVG does not contain geographic or organizational boundaries.

## Publication checks

Before a commit is eligible to publish:

1. Run `python scripts/check_publish_safety.py`.
2. Run all Python unit tests.
3. Run both JavaScript worker test suites.
4. Build both React clients from the sanitized source.
5. Review `git status --short` and the staged file list.
6. Confirm the GitHub repository visibility is `private` after the push.

## Known boundary

This automated scan detects known prohibited paths and patterns. It does not certify the repository for Controlled Unclassified Information, replace privacy/security review, or authorize use of GitHub for agency data.
