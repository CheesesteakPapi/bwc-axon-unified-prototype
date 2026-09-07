# Local test credentials

This optional feature reduces repeated Axon credential entry during prototype
testing. It is **not an encrypted vault or production credential-management
solution**. Use it only where local storage is approved, with restricted test
credentials. Do not use agency passwords or store credentials in chat.

## One-time configuration

Keep the existing per-user Python virtual environment. Do not put credentials
inside `.venv`: it can be rebuilt or deleted during setup.

1. Close both applications.
2. In the source package folder, run the helper:

   Windows 11 PowerShell:

   ```powershell
   .\Configure-Test-Credentials.cmd
   ```

   macOS Terminal:

   ```bash
   bash Configure-Test-Credentials-macOS.command
   ```

3. Read the plaintext-storage warning and type `STORE LOCALLY` to opt in.
4. Enter the tenant HTTPS URL, Partner/Agency ID, Client ID and Client Secret.
   Credential input is hidden and is not passed as shell command arguments.
5. Start both applications using their normal launchers. Each backend loads
   the file independently. No credential values are sent back to the browser.

The helper requires the existing `.venv`; if absent, use the normal Setup
launcher first. It does not install dependencies, require elevation, change
PowerShell execution policy, contact Axon, or modify tenant configuration.

## File location and protections

- Windows: `%LOCALAPPDATA%\ICE\BWC Axon Operations\credentials\test-credentials.local.json`
- macOS: `~/Library/Application Support/ICE/BWC Axon Operations/credentials/test-credentials.local.json`
- A custom `BWC_AXON_DATA_ROOT` puts `credentials` under that runtime directory.
- Advanced override: `BWC_TEST_CREDENTIALS_FILE` points at one explicit file;
  set it consistently for configuration and both launchers. Source-package
  and `.venv` locations are rejected.

The helper writes a private file before adding secrets: mode 600 on macOS/Linux;
current-user-only owner/access rules on Windows. Existing permissive files are
rejected on load. Symlink/hardlink/reparse files, duplicate JSON keys, unexpected
fields, invalid URLs, oversized files and control characters are rejected.
Windows ACL behavior needs native Windows acceptance; mocked tests are not that
acceptance. Same-user software and privileged administrators can still access
credentials. Use encrypted device storage and keep this file out of synced or
shared folders and ordinary support backups.

The supported JSON schema is version 1 with `testingOnly: true`,
`agencyBaseUrl`, `partnerId`, `clientId`, and `clientSecret`.
The helper is preferred to hand-editing. UTF-8 with or without BOM is accepted
for this local JSON file; Axon user-import CSV encoding is unchanged.

## Connection and action behavior

- Configure the same tenant URL in each app's connection settings first. A
  mismatch leaves credentials unloaded with a visible warning; save matching
  settings and restart. The file never chooses a different tenant or approves
  an existing unbound workspace.
- Loaded means **available locally**, not validated by Axon. Authentication
  occurs when the operator requests a live call; incorrect or expired credentials
  still fail. Opening an app never initiates a pull or write.
- Local review, validation, crosswalk edits and exports still need no Axon
  credentials. Live Axon operations still require valid authentication.
- With the test file loaded, Submit shows a checkbox confirming the displayed
  tenant instead of requiring the Partner ID to be retyped. The backend checks
  the exact profile target and uses the already-loaded Partner ID internally.
- Preview approval, current revision, write enablement, the final Submit action,
  tenant binding and chunk/dependency checks remain required. No automatic writes,
  implicit approvals or ambiguous-write retries were added.
- Manual credential entry overrides file-loaded credentials for that process
  and returns to the normal manual-session Agency ID confirmation.
- Entra delegated tokens are **not** stored in this file. Delegated sign-in,
  permissions and token expiry are unchanged; no client secret becomes a
  delegated Microsoft Graph token.

## Rotate, disable or remove

Close both apps before changing the file. To replace it:

```powershell
.\Configure-Test-Credentials.cmd -Replace
```

or on macOS:

```bash
bash Configure-Test-Credentials-macOS.command --replace
```

Restart both applications afterward. Rotation replaces the file without creating
secret-bearing backup copies; already-running processes do not hot-reload it.

Clearing credentials in the UI clears that process only. The file remains and
will load at the next normal launch. To disable persistence, remove the exact
`test-credentials.local.json` file from the location above after closing both apps.
Removal is not secure erasure; revoke test credentials when no longer needed.
You may instead launch a backend with `--no-test-credentials` to ignore the file
for that launch. The helper's `--path` option prints its expected path, not contents.

Git ignores `*.local.json` and `credentials/`. The publish checker additionally
rejects these paths even if force-added. The file is never stored in shared
SQLite, application configuration, manifests, exports, diagnostics or audit
records by this feature. Do not manually copy it into a release.
