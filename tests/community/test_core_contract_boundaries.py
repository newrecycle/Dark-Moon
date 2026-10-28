"""Owned-fixture event identities and conservative local remediation gates.

No provider, scanner, container daemon or vendor runtime is contacted.
"""
import copy
import json
import threading
from unittest.mock import patch

import test_community as fixtures
from api import json_storage as data
from community import remediation
from community.server import HTTPServer, handler_for


class CoreContractTests(fixtures.Fixture):
    def test_same_finding_id_in_two_campaigns_has_independent_event_lifecycle(self):
        first = self.campaign()
        self.service.operations.tick()
        second = "camp_second"
        data.save_campaign({"id": second, "status": "completed"})
        data.save_vulnerabilities(second, [{"id": "vuln_fixture", "campaign_id": second,
                                            "status": "unconfirmed", "severity": "low"}])
        self.service.operations.tick()
        created = [e for e in self.service.store.items("events") if e["event"] == "finding.created"]
        self.assertEqual([e["data"]["campaign_id"] for e in created], [second])
        self.service.operations.tick()
        self.assertEqual(len([e for e in self.service.store.items("events") if e["event"] == "finding.created"]), 1)
        for cid, status in ((first, "remediated"), (second, "confirmed")):
            findings = data.load_vulnerabilities(cid)
            findings[0]["status"] = status
            data.save_vulnerabilities(cid, findings)
            self.service.operations.tick()
            event = [e for e in self.service.store.items("events") if e["event"] == "finding." + status][-1]
            self.assertEqual(event["data"]["campaign_id"], cid)
        events = self.service.store.items("events")
        self.assertEqual([e["seq"] for e in events], sorted({e["seq"] for e in events}))

    def test_event_projection_rejects_nested_or_oversized_metadata(self):
        event = self.service.operations.emit("finding.created", {
            "campaign_id": "camp_exact", "finding_id": "finding_exact", "severity": "high",
            "status": {"evidence": "PRIVATE-NESTED"}, "run_id": ["PRIVATE-RUN"],
            "provider": "x" * 201, "evidence": "PRIVATE-EVIDENCE"})
        self.assertEqual(event["data"], {"campaign_id": "camp_exact", "finding_id": "finding_exact", "severity": "high"})
        self.assertNotIn("PRIVATE-", self.service.store.path.read_text())
        for name in ("finding.created\ndata: injected", "", None):
            with self.assertRaises(ValueError): self.service.operations.emit(name, {})

    def test_probe_expectations_are_typed_and_failure_is_never_a_fix(self):
        good = {"exit_code": 0, "timed_out": False, "output": "fixed"}
        self.assertTrue(remediation.expectation(good, {"exit_code": 0, "contains": "fixed"}))
        for bad in ({"exit_code": True}, {"exit_code": -9}, {"exit_code": 256},
                    {"exit_code": 0, "contains": ""}, {"exit_code": 0, "contains": {}},
                    {"exit_code": 0, "not_contains": []}, {"exit_code": 0, "ignore_failure": True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError): remediation.expectation(good, bad)
        for result in (good | {"exit_code": False}, good | {"timed_out": True},
                       good | {"timed_out": "false"}, good | {"infrastructure_error": True},
                       good | {"output": {"body": "fixed"}}, {}):
            self.assertFalse(remediation.expectation(result, {"exit_code": 0}))

    def test_entire_plan_is_validated_before_any_probe_runs(self):
        repo = fixtures.RemediationTests.source_repo(self)
        plan_path = repo / ".darkmoon/repro.json"
        original = json.loads(plan_path.read_text())
        for change in ({"timeout_seconds": True}, {"timeout_seconds": "60"}, {"argv": []},
                       {"argv": ["python", "bad\x00arg"]}, {"name": "exploit"},
                       {"after": {"exit_code": True}}, {"after": {"exit_code": 0, "contains": ""}}):
            plan = copy.deepcopy(original)
            plan["sqli"]["probes"][1].update(change)
            plan_path.write_text(json.dumps(plan))
            with self.subTest(change=change), self.assertRaises(ValueError):
                remediation.load_plan(repo, {"id": "vuln_fixture", "category": "sqli"})
        plan_path.write_text(json.dumps(original))
        self.assertEqual(len(remediation.load_plan(repo, {"id": "vuln_fixture", "category": "sqli"})["probes"]), 2)

    def test_judge_requires_real_bounded_confidence_and_reason(self):
        valid = {"approved": True, "confidence": 0.9, "reason": "Minimal defensive change"}
        for bad in (valid | {"confidence": True}, valid | {"confidence": float("nan")},
                    valid | {"confidence": float("inf")}, valid | {"confidence": -0.1},
                    valid | {"confidence": 10**500}, valid | {"reason": ""}, valid | {"reason": {}},
                    valid | {"approved": "true"}):
            with self.subTest(bad=str(bad)[:100]), patch.object(remediation, "model_json", return_value=bad):
                with self.assertRaises(ValueError): remediation.judge_patch({}, "synthetic diff")
        with patch.object(remediation, "model_json", return_value=valid):
            self.assertEqual(remediation.judge_patch({}, "synthetic diff"), valid)

    def test_local_remediation_state_matrix_preserves_original_and_never_publishes(self):
        cid, repo = self.campaign(), fixtures.RemediationTests.source_repo(self)
        plan_path = repo / ".darkmoon/repro.json"
        plan = json.loads(plan_path.read_text())
        variant = copy.deepcopy(plan["sqli"]["probes"][0])
        variant.update(name="variant", kind="variant")
        plan["sqli"]["probes"].append(variant)
        plan_path.write_text(json.dumps(plan))
        remediation.git(repo, "add", ".darkmoon/repro.json")
        remediation.git(repo, "commit", "-m", "Add owned variant probe")
        original_commit = remediation.git(repo, "rev-parse", "HEAD")
        edits = [{"path": "app.py", "old": "vulnerable", "new": "fixed"}]
        for scenario, expected in (("pass", "validated"), ("normal_failure", "validation_failed"),
                                   ("after_timeout", "validation_failed"), ("unreproduced", "unreproduced"),
                                   ("engine_failure", "unreproduced")):
            class FixtureSandbox:
                def __init__(self, image): pass
                def probe(self, root, probe):
                    changed = "fixed" in (root / "app.py").read_text()
                    output = "42" if probe["kind"] == "normal" else (root / "app.py").read_text()
                    return {"exit_code": 125 if scenario == "engine_failure" else 0,
                            "infrastructure_error": scenario == "engine_failure",
                            "timed_out": changed and scenario == "after_timeout",
                            "output": "unexpected" if (scenario == "unreproduced" or
                                      (changed and scenario == "normal_failure" and probe["kind"] == "normal")) else output}
            with self.subTest(scenario=scenario):
                result = remediation.remediate(repo, cid, "vuln_fixture", edits, True,
                    store=self.service.store, sandbox_factory=FixtureSandbox)
                self.assertEqual(result["status"], expected)
                self.assertFalse(result["published"])
                self.assertEqual(remediation.git(repo, "rev-parse", "HEAD"), original_commit)
                self.assertEqual(remediation.git(repo, "status", "--porcelain"), "")
                self.assertIn("vulnerable", (repo / "app.py").read_text())
        with patch.object(remediation, "generate_edits", return_value={"edits": edits}), \
             patch.object(remediation, "judge_patch", return_value={"approved": False, "confidence": 0.2, "reason": "Rejected"}):
            rejected = remediation.remediate(repo, cid, "vuln_fixture", generate=True, files=["app.py"], store=self.service.store)
        self.assertEqual(rejected["status"], "rejected")
        self.assertFalse(rejected["published"])


class EventStreamContractTests(fixtures.Fixture):
    request = fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(self.service, {"127.0.0.1"}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        super().tearDown()

    def test_known_event_cursor_replays_only_later_safe_events(self):
        first = self.service.operations.emit("finding.created", {"campaign_id": "camp_one", "finding_id": "same"})
        second = self.service.operations.emit("finding.confirmed", {"campaign_id": "camp_two", "finding_id": "same", "evidence": "PRIVATE-STREAM"})
        self.assertEqual(self.request("/api/v1/events", auth=False)[0], 401)
        for cursor in (first["id"], str(first["seq"])):
            with patch("community.server.time.sleep", return_value=None):
                status, body, headers = self.request("/api/v1/events", headers={"Last-Event-ID": cursor})
            self.assertEqual(status, 200)
            self.assertIn("text/event-stream", headers["Content-Type"])
            rows = [json.loads(line[6:]) for line in body.decode().splitlines() if line.startswith("data: {")]
            self.assertEqual([row["id"] for row in rows], [second["id"]])
            self.assertEqual(rows[0]["data"]["campaign_id"], "camp_two")
            self.assertNotIn("PRIVATE-STREAM", body.decode())
