# QA Changelog — v0.4.2

## v0.4.2 cross-platform integration

- Integrated the Provisioning Center into the BWC Axon Integration V2.3.7 cross-platform distribution while preserving standalone v0.4.1 unchanged.
- Added `Launch_Axon_Provisioning_Center_macOS.command` and renamed the packaged Windows launcher for a clear application identity.
- Both launchers prefer port 8797 and automatically try the next ten loopback ports when the preferred address is already occupied.
- Connected Group, Device Home, and device-status paths to the synthetic package-level `governance_starters` set. Runtime-reviewed values remain in the per-user workspace and are excluded from source control.
- Kept credentials, non-secret connection settings, and execution state isolated from Geographic Operations. No credential store is shared between the applications.
- Generated user-import CSVs now use UTF-8 without BOM. User validation explicitly blocks a BOM-bearing file before submission.
- The included PowerShell builder now uses an explicit no-BOM UTF-8 encoder, including on Windows PowerShell 5.1.
- Added a safe `404` diagnostic: list jobs and verify the exact returned job ID; never infer that a resubmission is required.
- Clarified that `EVIDENCE_GROUP_EXT_ID` is a blank Axon user-import compatibility column; organizational relationships use separate Axon Group entity rows.

## v0.4.2 validation

- Python functional and local-bridge tests: 27 passed.
- Sites routing/package tests: 4 passed.
- Production React build: passed.
- Python compilation and structural configuration validation: passed.
- macOS launcher syntax and executable-bit checks: passed.
- Runtime loopback health and occupied-port fallback: passed; the fallback smoke selected port 8800 because 8797 through 8799 were occupied.
- No live Axon tenant request or write was performed.

## v0.4.1 account-decision workflow

- Preview user accounts now identifies eligible new accounts, existing-account matches, and blocked rows as separate review categories.
- Each user preview automatically creates downloadable new-account and matched-account CSVs while preserving the selected source headers, values, and row order.
- Added Create clean copy. The default cleanup selections remove blocked rows and existing matches, produce a separate create-only CSV, select it for the current session, and rerun the preview.
- The uploaded source CSV is never edited or overwritten. The cleanup response verifies that its source SHA-256 hash remains unchanged.
- Duplicate external IDs, emails, badge numbers, and usernames block every participating duplicate row so cleanup never chooses an arbitrary row to keep.
- Structural file errors are not silently cleaned. The operator must repair the source structure and preview it again.
- Added the explicit **Allow updates to these _N_ reviewed accounts** option. It becomes available only after the matched-account view is opened and all preview blockers are resolved.

## v0.4.1 approval safeguards

- Update approval is bound to the latest preview token, exact user CSV, exact Users snapshot, both file hashes, and the displayed existing-account match count.
- Selecting a different user CSV or Users snapshot, running a replacement preview, or selecting a cleaned copy clears the prior update approval.
- The local backend independently rejects stale preview tokens, changed paths or hashes, count mismatches, and any remaining row or structural blocker.
- Allowing reviewed updates does not submit anything. Final submission still requires write enablement, the full matching Partner / Agency ID, confirmation of the preview scope, and a second confirmation for the exact reviewed update count.
- Preview downloads and cleanup are local-only operations and do not contact Axon.

## v0.4.1 release validation

- Python functional and local-bridge tests: 25 passed.
- Python compilation for the bridge and supporting provisioning modules: PASS.
- Static/Sites routing tests: 4 passed.
- React production build and Sites bundle preparation: PASS.
- Rendered page identity, nonblank-content, framework-overlay, and console warning/error checks: PASS.
- Synthetic 37-row browser workflow: 24 new accounts, 13 existing matches, and both split-file downloads rendered with their actual file row counts.
- Matched-account review enabled the exact 13-account update option; the submission screen retained that scope and required the second 13-account confirmation.
- Changing the selected user CSV cleared the preview and update approval; submission returned to Preview required and did not open the write modal.
- Cleanup selected a new 24-row session file and refreshed to 24 new, 0 matched, and 0 blocked rows while keeping the original 13-row matched-account review download.
- Mobile 390 x 844 layout: PASS with no document-level horizontal overflow; preview actions stacked at full width and the mobile notice no longer covered the Run button.
- Final ZIP listing and compressed-data integrity check: PASS; no credentials file, cache, or development-only AGENTS.md was included.
- Clean extracted-package retest: 25 Python tests and 4 JavaScript routing tests passed; the launcher backend help and v0.4.1 metadata were readable.
- No live Axon tenant request or write was made during these local QA checks.

## v0.4.0 functional integration baseline

- Added a localhost-only Python bridge that serves the production React application and invokes the existing Axon sync and provisioning commands.
- Connected all 17 dropdown functions to local, read-only, write, or job operations.
- Replaced mock credential status with a real session state.
- Added the Axon tenant URL and credential dialog. The URL and non-secret configuration may be saved; Partner ID, Client ID, and Client Secret remain only in process memory.
- Connected file selection to session-scoped uploads with CSV/JSON type and 20 MB size limits.
- Replaced the 128-row demonstration preview with actual user CSV validation and create-versus-existing classification.
- Preserved working Previous, Next, numbered-page, matched-only, and row-range behavior for actual preview results.
- Added controlled job-ID fields and actual function output/result cards.
- Added generated-file and job-result download links.
- Added an editable session-copy table for user and group CSVs. Saving downloads a new file and leaves the selected original unchanged.
- Added a 500-row editor guard so a larger CSV cannot be truncated by the integrated grid.
- Added a Windows launcher that runs the built UI without Node.js or administrator privileges.

## Baseline safety and security

- The service binds only to 127.0.0.1 and rejects non-local Host headers.
- POST and DELETE routes require the local UI request header.
- Added restrictive Content Security Policy, no-store API caching, frame denial, referrer suppression, and content-type protection.
- Credentials are excluded from config files, HTTP responses, child command arguments, and request logs.
- Credentials are cleared and the temporary session folder is removed when the server exits.
- Existing Python safeguards remain authoritative: writes disabled by default, explicit execute gate, exact Agency-ID confirmation, preview expectations, nonsynchronized user import, and no automatic POST retries.
- Group submission remains blocked until the agency-authorized multipart file field is confirmed.

## v0.4.0 baseline validation results

- React production build: PASS.
- Static/Sites routing tests: 4 passed.
- Python functional and local-bridge tests: 20 passed.
- Python compilation for the bridge, sync, provisioning, and UI-support modules: PASS.
- Rendered desktop page identity, nonblank content, missing-overlay check, and console warning/error check: PASS.
- Connection dialog open/close interaction: PASS.
- Function selector to Check user job status, with the correct job-ID input: PASS.
- Mobile 390 × 844 layout: PASS; document width remained 390 pixels with no horizontal overflow.
- Actual CSV upload-to-preview integration was exercised in-process: 1 selected row correctly classified as an existing account match.
- Credential response test confirmed that full Partner ID, Client ID, and Client Secret are not returned.
- Write confirmation test confirmed that a mismatched Agency ID is rejected before any child process can submit.

## Validation boundary

No live Axon tenant request or write was made during package QA. Live authentication, agency-specific permissions, current endpoint behavior, and the provisional group multipart field still require a controlled sandbox/approved-tenant test. This Codex workspace prevented launching the custom loopback bridge for browser automation, so rendered interaction tests used the application with synthetic local API fixtures; the complete functional bridge was tested directly in process.

Previous v0.4.0, v0.3.3, and functional v0.3.1 originals remain unchanged.
