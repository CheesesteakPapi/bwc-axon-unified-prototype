import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import local_test_credentials as credentials


PROFILE = {"version": 1, "testingOnly": True, "agencyBaseUrl": "https://test-agency.evidence.com/",
           "partnerId": "SYNTHETIC-PARTNER", "clientId": "synthetic-client", "clientSecret": "synthetic-secret"}


class FakeWorkspace:
    def tenant_status(self):
        return {"tenantHost": "test-agency.evidence.com"}


class Session(credentials.TestCredentialSession):
    def __init__(self):
        self.init_test_credentials()
        self.workspace = FakeWorkspace()
        self.values = ()

    def set_credentials(self, *values):
        self.init_test_credentials()
        self.values = values

    def partner_id(self):
        return self.values[0] if self.values else ""


class LocalTestCredentialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "credentials" / "test-credentials.local.json"
        self.env = patch.dict(os.environ, {"BWC_AXON_DATA_ROOT": self.temp.name, "BWC_TEST_CREDENTIALS_FILE": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_missing_default_is_not_an_error_and_does_not_create_file(self):
        self.assertIsNone(credentials.read_profile())
        self.assertFalse(self.path.exists())

    def test_private_roundtrip_and_rotation_does_not_create_backup(self):
        credentials.write_profile(self.path, PROFILE)
        self.assertEqual(credentials.read_profile()["clientSecret"], "synthetic-secret")
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(credentials.TestCredentialError):
            credentials.write_profile(self.path, {**PROFILE, "clientSecret": "replacement"})
        credentials.write_profile(self.path, {**PROFILE, "clientSecret": "replacement"}, replace=True)
        self.assertEqual(credentials.read_profile()["clientSecret"], "replacement")
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_missing_explicit_profile_is_actionable(self):
        with patch.dict(os.environ, {"BWC_TEST_CREDENTIALS_FILE": str(self.path)}):
            with self.assertRaisesRegex(credentials.TestCredentialError, "not found"):
                credentials.read_profile()

    @unittest.skipIf(os.name == "nt", "POSIX access-mode test")
    def test_world_readable_and_linked_profiles_rejected(self):
        credentials.write_profile(self.path, PROFILE)
        self.path.chmod(0o644)
        with self.assertRaisesRegex(credentials.TestCredentialError, "mode 600"):
            credentials.read_profile()
        self.path.chmod(0o600)
        linked = self.path.parent / "linked.local.json"
        linked.symlink_to(self.path)
        with self.assertRaises(credentials.TestCredentialError):
            credentials.read_profile(linked)

    def test_invalid_json_and_schema_never_echo_contents(self):
        credentials.write_profile(self.path, PROFILE)
        for content in ['{"clientSecret":"secret-sentinel",bad}', json.dumps({**PROFILE, "testingOnly": False}),
                        json.dumps({**PROFILE, "extra": "secret-sentinel"}), '{"version":1,"version":2}',
                        "secret-sentinel" * 2000]:
            self.path.write_text(content, encoding="utf-8")
            with self.assertRaises(credentials.TestCredentialError) as found:
                credentials.read_profile()
            self.assertNotIn("secret-sentinel", str(found.exception))

    def test_control_characters_empty_and_nonstring_fields_rejected(self):
        for value in ["", "  ", "bad\nvalue", "bad\x00value", 123]:
            with self.assertRaises(credentials.TestCredentialError):
                credentials.validate_profile({**PROFILE, "clientSecret": value})

    def test_url_validation_and_normalization(self):
        self.assertEqual(credentials.tenant_origin("https://TEST-agency.evidence.com:443/"), "https://test-agency.evidence.com")
        for value in ["http://example.test", "https://a:b@example.test", "https://example.test/path",
                      "https://example.test?token=secret", "https://example.test:bad"]:
            with self.assertRaises(credentials.TestCredentialError):
                credentials.tenant_origin(value)

    def test_source_package_and_venv_locations_rejected(self):
        for path in [Path(credentials.__file__).parent / "test-credentials.local.json", Path(self.temp.name) / ".venv" / "test-credentials.local.json"]:
            with self.assertRaises(credentials.TestCredentialError):
                credentials.write_profile(path, PROFILE)

    def test_file_load_is_not_authentication_or_workspace_mutation(self):
        credentials.write_profile(self.path, PROFILE)
        session = Session()
        session.load_test_credentials("https://test-agency.evidence.com")
        status = session.test_credential_status()
        self.assertTrue(status["testCredentialsLoaded"])
        self.assertEqual(status["credentialValidation"], "not-verified")
        self.assertNotIn("synthetic-secret", json.dumps(status))
        self.assertNotIn("synthetic-client", json.dumps(status))

    def test_tenant_mismatch_never_loads_and_changed_target_is_rejected(self):
        credentials.write_profile(self.path, PROFILE)
        session = Session()
        session.load_test_credentials("https://other.example.test")
        self.assertFalse(session.values)
        self.assertTrue(session.test_credential_status()["credentialWarning"])
        session.load_test_credentials("https://test-agency.evidence.com")
        with self.assertRaises(credentials.TestCredentialError):
            session.assert_credential_target("https://other.example.test")

    def test_target_confirmation_requires_test_profile_and_exact_target(self):
        credentials.write_profile(self.path, PROFILE)
        session = Session()
        body = {"confirmTarget": True, "targetOrigin": "https://test-agency.evidence.com"}
        with self.assertRaises(credentials.TestCredentialError):
            session.confirm_submission_target(body, body["targetOrigin"])
        session.load_test_credentials(body["targetOrigin"])
        self.assertEqual(session.confirm_submission_target(body, body["targetOrigin"]), PROFILE["partnerId"])
        for changed in [{**body, "confirmTarget": False}, {**body, "targetOrigin": "https://other.example.test"}]:
            with self.assertRaises(credentials.TestCredentialError):
                session.confirm_submission_target(changed, body["targetOrigin"])

    def test_manual_override_resets_file_mode(self):
        credentials.write_profile(self.path, PROFILE)
        session = Session()
        session.load_test_credentials(PROFILE["agencyBaseUrl"])
        session.set_credentials("other-partner", "other-client", "other-secret")
        self.assertFalse(session.test_credential_status()["testCredentialsLoaded"])

    def test_credentials_are_removed_from_command_or_error_text(self):
        session = Session()
        session._credentials = {"partner_id": "synthetic-partner", "client_id": "synthetic-client", "client_secret": "synthetic-secret"}
        self.assertEqual(session.redact_credentials("synthetic-partner synthetic-client synthetic-secret"), "[redacted] [redacted] [redacted]")

    def test_windows_acl_command_contains_no_secrets_or_elevation(self):
        with patch.object(credentials.subprocess, "run") as run:
            run.return_value.returncode = 0
            credentials._windows_acl(self.path, secure=True)
            args, kwargs = run.call_args
            self.assertNotIn("synthetic-secret", repr(args))
            self.assertNotIn("-ExecutionPolicy", args[0])
            self.assertTrue(kwargs["capture_output"])
            self.assertEqual(kwargs["env"]["BWC_CREDENTIAL_ACL_SECURE"], "1")

    def test_windows_acl_failures_fail_closed_and_redact_stderr(self):
        with patch.object(credentials.subprocess, "run") as run:
            run.return_value.returncode = 3
            run.return_value.stderr = b"secret-sentinel"
            with self.assertRaises(credentials.TestCredentialError) as found:
                credentials._windows_acl(self.path)
            self.assertNotIn("secret-sentinel", str(found.exception))


if __name__ == "__main__":
    unittest.main()
