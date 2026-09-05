import tempfile
import unittest
from pathlib import Path
from shared_workspace import SharedWorkspace
from provisioning_workflow import role_options, _approved_roles


class RoleOptionsTests(unittest.TestCase):
    def test_picker_tracks_reviewed_catalog_and_preserves_case(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = SharedWorkspace(Path(folder) / "shared.sqlite3")
            workspace.migrate_governance_csvs(Path(__file__).resolve().parents[1] / "governance_starters")
            self.assertEqual(role_options(workspace), ["Prototype Supervisor", "Prototype User"])
            dataset = workspace.governance_dataset("approved_axon_role_catalog")
            rows = [dict(row) for row in dataset["rows"]]
            rows[0]["Review Status"] = "Needs review"
            workspace.replace_governance_rows("approved_axon_role_catalog", rows, dataset["revision"], "test-review", "test")
            self.assertEqual(role_options(workspace), ["Prototype Supervisor"])
            self.assertEqual({role.casefold() for role in role_options(workspace)}, _approved_roles(workspace))
