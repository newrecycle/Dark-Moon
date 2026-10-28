"""Combined fork snapshot contracts. All network seams are mocked closed."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("forwarder_combined", ROOT / "forwarder/darkmoon-to-hec.py")
forwarder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(forwarder)


class CombinedContracts(unittest.TestCase):
    def setUp(self):
        self.network = patch("socket.create_connection", side_effect=AssertionError("External network disabled"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def retest(self, **extra):
        return {"id": "retest_one", "retest_id": "retest_one", "status": "completed",
                "base_campaign_id": "base", "new_campaign_id": "next", "campaign_id": "next",
                "target_id": "target_one", "run_id": "run_one", "findings": [], **extra}

    def test_lifecycle_survives_empty_and_missing_pending_comparisons(self):
        for status in ("running", "incomplete", "completed"):
            record = self.retest(status=status)
            if status != "completed":
                record.pop("findings")
                record["verdicts"] = []
            with self.subTest(status=status):
                rows = forwarder.build_events({"retests": [record]})
                self.assertEqual(len(rows), 1)
                event = rows[0]["event"]
                self.assertEqual(event["record_type"], "lifecycle")
                for key in ("retest_id", "base_campaign_id", "new_campaign_id", "target_id", "run_id", "status"):
                    self.assertEqual(event[key], record[key])
                self.assertNotIn("verdict", event)

    def test_aggregate_comparisons_preserve_scoped_new_and_current_ids(self):
        comparisons = [{"finding_id": "same", "current_finding_id": "current", "verdict": "still_present"},
                       {"finding_id": "same", "verdict": "new"},
                       {"finding_id": "absent", "verdict": "not_observed", "evidence": "PRIVATE-BODY"}]
        record = self.retest(findings=comparisons, verdicts=copy.deepcopy(comparisons))
        rows = forwarder.build_events({"retests": [record]})
        self.assertEqual(len(rows), 4)
        events = [row["event"] for row in rows]
        self.assertEqual([e.get("finding_key") for e in events[1:]], ["base::same", "next::same", "base::absent"])
        self.assertEqual(events[1]["current_finding_id"], "current")
        self.assertEqual(events[-1]["verdict"], "not_observed")
        self.assertNotIn("PRIVATE-BODY", json.dumps(rows))
        self.assertEqual(len({e["event_id"] for e in events}), 4)

    def test_aggregate_parent_cannot_supply_comparison_metadata(self):
        record = self.retest(verdict="fixed", title="PARENT-TITLE", severity="critical",
                             current_finding_id="parent-current", findings=[{"finding_id": "f", "verdict": "not_observed"}])
        lifecycle, comparison = [e["event"] for e in forwarder.build_events({"retests": [record]})]
        for key in ("verdict", "title", "severity", "current_finding_id"):
            self.assertNotIn(key, lifecycle)
        for key in ("title", "severity", "current_finding_id"):
            self.assertNotIn(key, comparison)
        self.assertEqual(comparison["verdict"], "not_observed")

    def test_invalid_retest_shapes_and_references_fail_whole_preparation(self):
        bad = [self.retest(findings=None), self.retest(findings=[None]),
               self.retest(findings=[{"finding_id": "x"}]),
               self.retest(findings=[{"finding_id": "x", "verdict": 1}]),
               self.retest(findings=[{"finding_id": "x", "verdict": "new", "run_id": "foreign"}]),
               self.retest(findings=[{"finding_id": "x", "verdict": "new", "retest_id": "foreign"}]),
               self.retest(findings=[{"finding_id": "x", "verdict": "new", "current_finding_id": []}]),
               self.retest(findings=[{"finding_id": "x", "verdict": "new"}] * 2),
               self.retest(findings=[], verdicts=[{"finding_id": "x", "verdict": "new"}]),
               self.retest(retest_id="foreign"), self.retest(campaign_id="foreign"),
               self.retest(status=[]), self.retest(status=" completed")]
        no_array = self.retest()
        no_array.pop("findings")
        bad.append(no_array)
        for record in bad:
            with self.subTest(record=record), self.assertRaises(ValueError):
                forwarder.build_events({"campaigns": [{"id": "valid"}], "retests": [record]})

    def test_flat_retests_and_record_identity_failures(self):
        record = {"retest_id": "legacy", "finding_id": "f", "verdict": "fixed"}
        rows = forwarder.build_events({"retests": [record]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event"]["finding_key"], "legacy::f")
        for data in ({"campaigns": [{"id": 1}]}, {"campaigns": [{"id": "one", "campaign_id": "two"}]},
                     {"vulnerabilities": [{"id": "f", "campaign_id": []}]},
                     {"retests": [{**record, "findings": []}]}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                forwarder.build_events(data)

    def test_target_join_is_exact_unique_and_does_not_mutate_input(self):
        data = {"targets": [{"id": "t", "host": "https://user:PRIVATE@owned.invalid/p?q=PRIVATE#PRIVATE"}],
                "campaigns": [{"id": "c", "target_id": "t"}],
                "vulnerabilities": [{"id": "f", "campaign_id": "c", "target_id": "t"},
                                    {"id": "f", "campaign_id": "other", "target_id": "missing"}],
                "retests": [self.retest(target_id="t")]}
        original = copy.deepcopy(data)
        rows = forwarder.build_events(data)
        self.assertEqual(data, original)
        self.assertEqual(rows[0]["event"]["target"], "https://owned.invalid/p")
        self.assertEqual(rows[1]["event"]["finding_key"], "c::f")
        self.assertEqual(rows[2]["event"]["finding_key"], "other::f")
        self.assertNotIn("target", rows[2]["event"])
        self.assertNotIn("PRIVATE", json.dumps(rows))
        data["targets"].append({"id": "t", "host": "foreign.invalid"})
        with self.assertRaises(ValueError):
            forwarder.build_events(data)

    def test_links_numeric_scm_and_numeric_bounds(self):
        rows = forwarder.build_events({"pull_requests": [
            {"id": "local", "published": False, "finding_ids": ["b", "a", "a"], "confidence": 0},
            {"id": "record", "pr_id": 17, "published": True, "finding_ids": ["a", "b"], "number": 2.5}]})
        self.assertEqual(rows[0]["event"]["finding_ids"], ["a", "b"])
        self.assertEqual(rows[0]["sourcetype"], "darkmoon:remediation")
        self.assertEqual(rows[1]["event"]["pr_id"], "record")
        self.assertNotIn("number", rows[1]["event"])
        for value in (True, -1, 10.1, float("inf"), "0", {}, []):
            self.assertNotIn("cvss_score", forwarder.finding_event({"id": "f", "cvss_score": value})["event"])
        self.assertEqual(forwarder.finding_event({"id": "f", "cvss_score": 0})["event"]["cvss_score"], 0)
        for links in (["ok", {}], ["../escape"], ["f"] * 1001):
            with self.subTest(links=str(links)[:60]), self.assertRaises(ValueError):
                forwarder.pr_event({"id": "p", "finding_ids": links})

    def test_locators_and_configuration_edge_cases(self):
        for location in ("//u:PRIVATE@owned.invalid/x?PRIVATE#PRIVATE", "https://u:PRIVATE@[::1]:443/x?PRIVATE", "ssh://u:PRIVATE@owned.invalid/x"):
            result = forwarder.finding_event({"id": "f", "target": location, "endpoint": location})
            self.assertNotIn("PRIVATE", json.dumps(result))
        for url in ("https://owned.invalid/?", "https://owned.invalid/#", "https://owned.invalid\\x", "https://owned.invalid:0"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                forwarder.checked_url(url)

    def test_hec_oversized_admission_and_ambiguous_failure_do_not_leak(self):
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *args): self.close()
        with patch.object(forwarder, "open_request", return_value=Response(b" " * (1024 * 1024 + 1))) as request, patch.object(forwarder.time, "sleep") as sleep:
            with self.assertRaises(ValueError):
                forwarder.send_hec("https://hec.invalid/collector", "fixture-token", [{"event": {}}], True)
            self.assertEqual(request.call_count, 1)
            sleep.assert_not_called()
        with patch.object(forwarder, "open_request", side_effect=OSError("PRIVATE")), patch.object(forwarder.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "earlier batches") as error:
                forwarder.send_hec("https://hec.invalid/collector", "fixture-token", [{}], True, max_retries=1)
            self.assertNotIn("PRIVATE", str(error.exception))


if __name__ == "__main__":
    unittest.main()
