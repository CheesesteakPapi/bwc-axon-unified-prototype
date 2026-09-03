from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from audit_store import append_event, verify_chain


class AuditStoreTests(unittest.TestCase):
    def test_hash_chain_verifies_and_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "audit.sqlite3"
            append_event("test", "launch", "success", {"version": "1.0.0"}, path=path)
            append_event("test", "change", "success", {"record": "A-1"}, path=path)
            self.assertEqual(
                {"valid": True, "events": 2, "firstInvalidSequence": None},
                verify_chain(path=path),
            )
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "UPDATE audit_events SET outcome = 'changed' WHERE sequence = 1"
                )
                connection.commit()
            finally:
                connection.close()
            result = verify_chain(path=path)
            self.assertFalse(result["valid"])
            self.assertEqual(1, result["firstInvalidSequence"])


if __name__ == "__main__":
    unittest.main()
