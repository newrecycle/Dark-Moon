"""Exercise the fork's exact retest references without starting its launcher."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "mcp"))
from community.operations import Operations
from community.store import Store


class RetestBackendReferences(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.service = SimpleNamespace(store=Store(root.name), launch=Mock(return_value={"id": "run", "campaign_id": "new"}))
        self.operations = Operations(self.service)

    def test_missing_explicit_base_does_not_fall_back_to_latest_target_campaign(self):
        with patch("community.operations.data.load_campaign", return_value=None), patch("community.operations.data.load_targets") as targets:
            with self.assertRaises(KeyError):
                self.operations.launch_retest({"campaign_id": "missing", "target_id": "target"})
            targets.assert_not_called()
            self.service.launch.assert_not_called()

    def test_explicit_base_target_mismatch_stops_before_launch(self):
        with patch("community.operations.data.load_campaign", return_value={"id": "base", "target_id": "foreign"}):
            with self.assertRaises(ValueError):
                self.operations.launch_retest({"campaign_id": "base", "target_id": "target", "finding_ids": ["selected"]})
            self.service.launch.assert_not_called()

    def test_exact_base_selects_only_requested_comparison_and_retains_scope(self):
        campaign = {"id": "base", "target_id": "target", "scope": {"out_of_scope": ["excluded.invalid"], "safe_harbor": "Original terms"}}
        findings = [{"id": "selected", "category": "sqli"}, {"id": "other", "category": "xss"}]
        with patch("community.operations.data.load_campaign", return_value=campaign), patch("community.operations.data.load_target", return_value={"id": "target", "host": "owned.invalid"}), patch("community.operations.data.load_vulnerabilities", return_value=findings):
            record = self.operations.launch_retest({"campaign_id": "base", "target_id": "target", "finding_ids": ["selected"], "safe_harbor": "non-destructive"})
        self.assertEqual(record["before_ids"], ["selected"])
        self.assertEqual(record["base_campaign_id"], "base")
        self.assertEqual(self.service.store.get("retests", record["id"]), record)
        spec = self.service.launch.call_args.args[0]
        self.assertEqual(spec["focus"], "sqli")
        self.assertEqual(spec["out_of_scope"], ["excluded.invalid"])
        self.assertIn("Original terms", spec["safe_harbor"])


if __name__ == "__main__":
    unittest.main()
