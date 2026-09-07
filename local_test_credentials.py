"""Opt-in, per-user Axon test credentials. Never imported into shared SQLite."""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

MAX_BYTES = 16384
FIELDS = {"version", "testingOnly", "agencyBaseUrl", "partnerId", "clientId", "clientSecret"}


class TestCredentialError(ValueError):
    """Safe error: never include file contents, IDs, or secrets."""


def credential_path() -> Path:
    override = os.environ.get("BWC_TEST_CREDENTIALS_FILE", "").strip()
    if override:
        return Path(override).expanduser().absolute()
    override = os.environ.get("BWC_AXON_DATA_ROOT", "").strip()
    if override:
        root = Path(override).expanduser().absolute()
    elif os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "ICE" / "BWC Axon Operations"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "ICE" / "BWC Axon Operations"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "ice" / "bwc-axon-operations"
    return root / "credentials" / "test-credentials.local.json"


def tenant_origin(value: str) -> str:
    try:
        p = urlsplit(value.strip())
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.path not in ("", "/") or p.query or p.fragment or p.port not in (None, 443):
            raise ValueError()
        return "https://" + p.hostname.lower()
    except (ValueError, AttributeError):
        raise TestCredentialError("Use the exact tenant HTTPS origin without a path, credentials, or custom port.") from None


def validate_profile(data: object) -> dict:
    if not isinstance(data, dict) or set(data) != FIELDS or type(data.get("version")) is not int or data["version"] != 1 or data.get("testingOnly") is not True:
        raise TestCredentialError("Invalid test-credential schema; use the local configuration helper.")
    result = dict(data)
    for field in ("agencyBaseUrl", "partnerId", "clientId", "clientSecret"):
        value = result[field]
        if not isinstance(value, str) or not value.strip() or len(value) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise TestCredentialError("Test credential fields must be nonempty strings without control characters.")
    result["agencyBaseUrl"] = tenant_origin(result["agencyBaseUrl"])
    result["partnerId"] = result["partnerId"].strip()
    result["clientId"] = result["clientId"].strip()
    return result


def _windows_acl(path: Path, *, secure: bool = False) -> None:
    # No secret is passed to PowerShell. No elevation or execution-policy change.
    script = """
    $ErrorActionPreference='Stop'
    $p=$env:BWC_CREDENTIAL_ACL_PATH
    $sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl=Get-Acl -LiteralPath $p
    if ($env:BWC_CREDENTIAL_ACL_SECURE -eq '1') {
      $acl.SetAccessRuleProtection($true,$false)
      foreach($rule in @($acl.Access)) { [void]$acl.RemoveAccessRuleAll($rule) }
      $rule=New-Object System.Security.AccessControl.FileSystemAccessRule($sid,'FullControl','Allow')
      $acl.AddAccessRule($rule)
      $acl.SetOwner($sid)
      Set-Acl -LiteralPath $p -AclObject $acl
      $acl=Get-Acl -LiteralPath $p
    }
    if ($acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -ne $sid.Value) { exit 2 }
    foreach($rule in $acl.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier])) {
      if ($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -ne $sid.Value) { exit 3 }
    }
    """
    env = {**os.environ, "BWC_CREDENTIAL_ACL_PATH": str(path), "BWC_CREDENTIAL_ACL_SECURE": "1" if secure else "0"}
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                env=env, capture_output=True, timeout=15, check=False)
        if result.returncode:
            raise TestCredentialError("Test credential file must be owned by and accessible only to this Windows user. Run the configuration helper.")
    except (OSError, subprocess.TimeoutExpired):
        raise TestCredentialError("Unable to verify private file access; test credentials were not loaded.") from None


def _check_file(path: Path) -> None:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or getattr(info, "st_file_attributes", 0) & 0x400:
            raise TestCredentialError("Test credentials must be a regular local file, not a link.")
        if info.st_size > MAX_BYTES:
            raise TestCredentialError("Test credential file exceeds the size limit.")
        if os.name == "nt":
            _windows_acl(path)
        elif info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise TestCredentialError("Test credential file must be owned by you with mode 600. Run the configuration helper.")
    except OSError:
        raise TestCredentialError("Unable to read the local test credential file.") from None


def read_profile(path: Path | None = None) -> dict | None:
    path = path or credential_path()
    _check_location(path)
    if not path.exists() and not path.is_symlink():
        if os.environ.get("BWC_TEST_CREDENTIALS_FILE") and path == credential_path():
            raise TestCredentialError("The explicitly configured test credential file was not found.")
        return None
    _check_file(path)
    try:
        before = path.lstat()
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            current = os.fstat(handle.fileno())
            if (before.st_dev, before.st_ino, before.st_mode) != (current.st_dev, current.st_ino, current.st_mode):
                raise TestCredentialError("Test credential file changed during loading. Restart after configuration is complete.")
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise TestCredentialError("Test credential file exceeds the size limit.")
        def unique_pairs(pairs):
            data = {}
            for key, value in pairs:
                if key in data:
                    raise TestCredentialError("Duplicate fields in test credential file.")
                data[key] = value
            return data
        return validate_profile(json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_pairs))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        raise TestCredentialError("Unable to parse the local test credential file. Contents were not logged.") from None


def write_profile(path: Path, data: dict, *, replace: bool = False) -> None:
    _check_location(path)
    data = validate_profile(data)
    if path.exists() or path.is_symlink():
        if not replace:
            raise TestCredentialError("A file already exists. Stop both apps and use --replace to rotate it.")
        _check_file(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".bwc-credentials-", suffix=".local.json", dir=path.parent)
    temporary = Path(temp)
    try:
        os.close(fd)
        if os.name == "nt":
            _windows_acl(temporary, secure=True)
        else:
            temporary.chmod(0o600)
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        _check_file(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _check_location(path: Path) -> None:
    resolved = path.resolve()
    if Path(__file__).resolve().parent in resolved.parents or ".venv" in resolved.parts:
        raise TestCredentialError("Keep test credentials outside the source package and virtual environment.")


class TestCredentialSession:
    """Each app independently loads an opt-in file; never serializes the profile."""
    def init_test_credentials(self) -> None:
        self._test_credential_origin = ""
        self._test_credential_warning = ""

    def load_test_credentials(self, configured_url: str) -> None:
        try:
            data = read_profile()
            if data is None:
                return
            if data["agencyBaseUrl"] != tenant_origin(configured_url):
                raise TestCredentialError("Local test credentials target a different URL. Set the matching tenant in connection settings, then restart.")
            bound = self.workspace.tenant_status().get("tenantHost")
            if bound and bound != urlsplit(data["agencyBaseUrl"]).hostname:
                raise TestCredentialError("Local test credentials do not match this workspace's tenant.")
            self.set_credentials(data["partnerId"], data["clientId"], data["clientSecret"])
            self._test_credential_origin = data["agencyBaseUrl"]
        except TestCredentialError as exc:
            self._test_credential_warning = str(exc)

    def test_credential_status(self) -> dict:
        return {"credentialSource": "local-test-file" if self._test_credential_origin else "session",
                "testCredentialsLoaded": bool(self._test_credential_origin),
                "testCredentialTarget": self._test_credential_origin,
                "credentialWarning": self._test_credential_warning,
                "credentialValidation": "not-verified"}

    def assert_credential_target(self, configured_url: str) -> None:
        if self._test_credential_origin and tenant_origin(configured_url) != self._test_credential_origin:
            raise TestCredentialError("The configured tenant changed. Local test credentials cannot be sent there; restart with matching settings.")

    def redact_credentials(self, text: str) -> str:
        for value in sorted(set(getattr(self, "_credentials", {}).values()) - {""}, key=len, reverse=True):
            text = text.replace(value, "[redacted]")
        return text

    def confirm_submission_target(self, body: dict, configured_url: str) -> str:
        self.assert_credential_target(configured_url)
        if self._test_credential_origin and body.get("confirmTarget") is True and body.get("targetOrigin") == self._test_credential_origin:
            return self.partner_id()
        confirmation = str(body.get("confirmAgency") or "").strip()
        if not confirmation or confirmation != self.partner_id():
            raise TestCredentialError("The confirmation Agency ID does not match this credential session. Confirm the displayed test target or enter the matching ID.")
        return confirmation


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure an opt-in local Axon testing credential file.")
    parser.add_argument("--configure", action="store_true", help="Prompt locally; credentials are never command arguments.")
    parser.add_argument("--replace", action="store_true", help="Replace an existing private profile after stopping both apps.")
    parser.add_argument("--path", action="store_true", help="Print the expected path, not its contents.")
    args = parser.parse_args()
    if args.path:
        print(credential_path())
        return 0
    if not args.configure:
        parser.print_help()
        return 0
    print("TESTING ONLY: this is a plaintext local file, NOT an encrypted credential vault.")
    print("Only continue if local storage is approved. Use restricted test credentials; never commit or share the file.")
    if input("Type STORE LOCALLY to opt in: ").strip() != "STORE LOCALLY":
        print("Canceled. No credential file written.")
        return 0
    try:
        data = {"version": 1, "testingOnly": True,
                "agencyBaseUrl": input("Configured Axon tenant HTTPS URL: ").strip(),
                "partnerId": getpass.getpass("Partner / Agency ID (hidden): "),
                "clientId": getpass.getpass("Client ID (hidden): "),
                "clientSecret": getpass.getpass("Client secret (hidden): ")}
        write_profile(credential_path(), data, replace=args.replace)
        print("Private test credential file saved. Start/restart both apps. Authentication has not been tested.")
        return 0
    except (TestCredentialError, OSError):
        print("Configuration failed. Check the path, private file permissions and required fields. Existing file was not intentionally overwritten unless --replace was used.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
