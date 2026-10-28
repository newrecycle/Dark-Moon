"""Offline finding lifecycle contract and persistence verification.

All fixtures are local files and loopback HTTP. No assessment, native vendor
runtime, source publication or external repository traffic is performed.
The original vendor response schema remains unverified.
"""
import concurrent.futures
import json
import os
import threading
from pathlib import Path
from unittest.mock import patch

import test_community as fixtures
from api import json_storage as data
from api import live_push
from community.server import HTTPServer, handler_for


class FindingLifecycleTests(fixtures.Fixture):
    request = fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(self.service, {"127.0.0.1"}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def get(self, path, **kwargs):
        status, body, _ = self.request(path, **kwargs)
        return status, json.loads(body)

    def record(self, identifier, campaign_id, finding_id, status="confirmed", **extra):
        row = {"id": identifier, "campaign_id": campaign_id, "finding_id": finding_id,
               "status": status, "title": "Local remediation", "published": False, **extra}
        data._write_json(self.service.store.root / "remediation" / identifier / "result.json", row)
        return row

    def test_target_evolution_is_current_retained_campaign_projection_not_backfilled_history(self):
        data.save_target({"id": "target_exact", "host": "owned.invalid"})
        data.save_target({"id": "target_other", "host": "owned.invalid"})
        for ident, started in (("c_late", "2026-10-03T10:00:00Z"),
                               ("c_early", "2026-10-01T10:00:00Z"),
                               ("c_early_b", "2026-10-01T10:00:00Z"),
                               ("c_undated", "not a date")):
            data.save_campaign({"id": ident, "target_id": "target_exact",
                                "project_id": "proj_explicit", "date": started, "status": "completed"})
        data.save_campaign({"id": "c_other", "target_id": "target_other", "date": "2026-10-01T09:00:00Z"})
        data.save_vulnerabilities("c_early", [
            {"id": "f1", "campaign_id": "c_early", "target_id": "target_exact",
             "severity": "high", "status": "confirmed", "evidence": {"raw": "SECRET"}},
            {"id": "f_foreign", "campaign_id": "c_early", "target_id": "target_other",
             "severity": "critical", "status": "exploited"},
        ])
        status, body = self.get("/api/v1/targets/target_exact/evolution")
        self.assertEqual(status, 200)
        self.assertEqual(body["projection"], "retained_campaign_current_snapshots_v1")
        self.assertFalse(body["historical_transitions_available"])
        self.assertEqual([r["campaign_id"] for r in body["data"]],
                         ["c_early", "c_early_b", "c_late", "c_undated"])
        self.assertEqual(body["data"][0]["findings"], 1)
        self.assertEqual(body["data"][0]["risk"], "high")
        self.assertIsNone(body["data"][-1]["started_at"])
        self.assertNotIn("SECRET", json.dumps(body))
        self.assertEqual(self.get("/api/v1/vulnerabilities/history")[1]["total"], 0)

    def test_target_evolution_unknown_invalid_and_empty_target(self):
        data.save_target({"id": "idle"})
        status, body = self.get("/api/v1/targets/idle/evolution")
        self.assertEqual(status, 200)
        self.assertEqual(body["data"], [])
        self.assertEqual(body["total"], 0)
        self.assertEqual(self.get("/api/v1/targets/missing/evolution")[0], 404)
        self.assertEqual(self.get("/api/v1/targets/%2e%2e/evolution")[0], 400)
        self.assertEqual(self.get("/api/v1/projects/idle/evolution")[0], 404)

    def test_journal_activation_live_push_and_operator_triage_are_real_events(self):
        journal = data.load_finding_history()
        self.assertIsNotNone(journal["recording_started_at"])
        self.assertEqual(journal["events"], [])
        cid = self.campaign()
        campaign = data.load_campaign(cid)
        status, created = self.get("/api/v1/vulnerabilities/history?target_id=" + campaign["target_id"])
        self.assertEqual(status, 200)
        self.assertEqual(created["total"], 1)
        self.assertEqual(created["data"][0]["event"], "finding.created")
        self.assertEqual(created["data"][0]["finding_id"], "vuln_fixture")
        self.assertEqual(created["data"][0]["campaign_id"], cid)
        self.assertIsNone(created["data"][0]["previous_status"])
        self.assertEqual(created["data"][0]["source"], "live_finding_push")
        self.assertFalse(created["history_complete"])
        path = "/api/v1/campaigns/" + cid + "/findings/vuln_fixture"
        self.assertEqual(self.request(path, "PATCH", {"status": "resolved"})[0], 200)
        self.assertEqual(self.request(path, "PATCH", {"status": "resolved"})[0], 200)
        status, history = self.get("/api/v1/vulnerabilities/history")
        self.assertEqual(status, 200)
        self.assertEqual([e["event"] for e in history["data"]],
                         ["finding.created", "finding.status_changed"])
        self.assertEqual(history["data"][1]["previous_status"], "confirmed")
        self.assertEqual(history["data"][1]["status"], "resolved")
        self.assertEqual(history["data"][1]["source"], "operator_triage")
        self.assertNotIn("PRIVATE-EVIDENCE", json.dumps(history))
        self.assertNotIn("Unsafe query", json.dumps(history))
        self.assertEqual(data.load_vulnerability("vuln_fixture")["status"], "resolved")

    def test_history_pagination_filtering_and_tie_break_are_deterministic(self):
        data.save_target({"id": "t1"})
        data.save_target({"id": "t2"})
        c1 = {"id": "c1", "target_id": "t1", "project_id": "p1"}
        c2 = {"id": "c2", "target_id": "t2", "project_id": "p2"}
        data.save_campaign(c1)
        data.save_campaign(c2)
        for i in range(6):
            data.record_finding_event(c1 if i < 5 else c2,
                                      {"id": "f_" + str(i), "status": "confirmed"}, "finding.created")
        with patch.object(data, "load_finding_history", wraps=data.load_finding_history) as wrapped:
            status, a = self.get("/api/v1/vulnerabilities/history?target_id=t1&limit=2&offset=0")
            self.assertEqual(status, 200)
            self.assertEqual(wrapped.call_count, 1)
        self.assertEqual((a["total"], a["limit"], a["offset"]), (5, 2, 0))
        self.assertTrue(a["has_more"])
        self.assertEqual(a["next_offset"], 2)
        b = self.get("/api/v1/vulnerabilities/history?target_id=t1&limit=2&offset=2")[1]
        c = self.get("/api/v1/vulnerabilities/history?target_id=t1&limit=2&offset=4")[1]
        self.assertFalse(c["has_more"])
        self.assertIsNone(c["next_offset"])
        ids = [e["id"] for page in (a, b, c) for e in page["data"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, [e["id"] for e in self.get("/api/v1/vulnerabilities/history?target_id=t1&limit=500")[1]["data"]])
        empty = self.get("/api/v1/vulnerabilities/history?target_id=t1&offset=99")[1]
        self.assertEqual(empty["total"], 5)
        self.assertEqual(empty["data"], [])
        self.assertEqual(empty["next_offset"], None)

    def test_history_rejects_unknown_duplicate_blank_and_nondecimal_queries(self):
        data.save_target({"id": "t1"})
        for suffix in ("?target_id=missing",):
            self.assertEqual(self.get("/api/v1/vulnerabilities/history" + suffix)[0], 404)
        for suffix in ("?target_id=", "?target_id=t1&target_id=t1", "?unknown=1",
                       "?limit=0", "?limit=501", "?limit=-1", "?limit=1.0",
                       "?limit=1&limit=2", "?offset=-1", "?offset=1.2",
                       "?offset=1000000001", "?offset=", "?limit="):
            self.assertEqual(self.get("/api/v1/vulnerabilities/history" + suffix)[0], 400, suffix)
        self.assertEqual(self.get("/api/v1/vulnerabilities/history")[0], 200)
        self.assertEqual(self.get("/api/v1/vulnerabilities/history/evidence-meta")[0], 404)

    def test_journal_has_no_backfill_and_survives_reinitialization(self):
        data.save_target({"id": "t1"})
        data.save_campaign({"id": "c1", "target_id": "t1"})
        data.save_vulnerabilities("c1", [{"id": "preexisting", "campaign_id": "c1",
                                         "target_id": "t1", "status": "confirmed"}])
        before = data.load_finding_history()
        self.assertEqual(before["events"], [])
        data.init_finding_history()
        self.assertEqual(data.load_finding_history()["recording_started_at"], before["recording_started_at"])
        self.assertEqual(self.get("/api/v1/vulnerabilities/history")[1]["data"], [])
        data.record_finding_event({"id": "c1", "target_id": "t1"},
                                  {"id": "new", "status": "confirmed"}, "finding.created")
        data.init_finding_history()
        self.assertEqual(self.get("/api/v1/vulnerabilities/history")[1]["total"], 1)

    def test_journal_parallel_appends_and_corruption_fail_explicitly(self):
        campaign = {"id": "c1", "target_id": "t1"}
        def write(i):
            data.record_finding_event(campaign, {"id": "f" + str(i), "status": "confirmed"}, "finding.created")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write, range(24)))
        status, history = self.get("/api/v1/vulnerabilities/history?limit=50")
        self.assertEqual(status, 200)
        self.assertEqual(history["total"], 24)
        self.assertEqual(len({e["id"] for e in history["data"]}), 24)
        self.assertEqual([e["recorded_at"] for e in history["data"]],
                         sorted(e["recorded_at"] for e in history["data"]))
        with data._file_lock(data.FINDING_HISTORY_FILE):
            with data.FINDING_HISTORY_FILE.open("a") as stream:
                stream.write("{ invalid json\n")
        self.assertEqual(self.get("/api/v1/vulnerabilities/history")[0], 500)

    def test_finding_lookup_keeps_exact_campaign_links_and_many_to_many_records(self):
        data.save_target({"id": "t1"})
        data.save_target({"id": "t2"})
        for cid, tid in (("c1", "t1"), ("c2", "t2")):
            data.save_campaign({"id": cid, "target_id": tid})
            data.save_vulnerabilities(cid, [
                {"id": "shared", "campaign_id": cid, "target_id": tid, "status": "confirmed"},
                {"id": "other", "campaign_id": cid, "target_id": tid, "status": "confirmed"},
            ])
        self.record("rem_one", "c1", "other", finding_ids=["shared", "other"],
                    validation={"before": [{"name": "unit", "passed": True, "output": "SENSITIVE-PROBE"}]},
                    patch_path="/secret/source/fix.patch", credential_ref="SENSITIVE-CREDENTIAL",
                    worktree="/secret/source/worktree", evidence="SENSITIVE-EVIDENCE")
        self.record("rem_two", "c1", "shared")
        self.record("rem_three", "c2", "shared")
        self.record("rem_near", "c2", "shared_truncated")
        status, result = self.get("/api/v1/pull-requests/finding/shared?campaign_id=c1")
        self.assertEqual(status, 200)
        self.assertEqual(result["campaign_ids"], ["c1"])
        self.assertEqual([p["id"] for p in result["data"]], ["rem_one", "rem_two"])
        self.assertEqual(result["data"][0]["finding_ids"], ["other", "shared"])
        self.assertEqual([p["id"] for p in self.get("/api/v1/pull-requests/finding/shared")[1]["data"]],
                         ["rem_one", "rem_three", "rem_two"])
        self.assertEqual(self.get("/api/v1/pull-requests/finding/other?campaign_id=c2")[1]["data"], [])
        self.assertEqual(self.get("/api/v1/pull-requests/finding/shared?campaign_id=c2")[1]["total"], 1)
        self.assertEqual(self.get("/api/v1/pull-requests/finding/missing")[0], 404)
        self.assertEqual(self.get("/api/v1/pull-requests/finding/shared?campaign_id=missing")[0], 404)
        self.assertEqual(self.get("/api/v1/pull-requests/finding/shared?campaign_id=c1&campaign_id=c2")[0], 400)
        self.assertEqual(self.get("/api/v1/pull-requests/finding/shared?unexpected=1")[0], 400)
        self.assertEqual(self.get("/api/v1/pull-requests/finding/%2e%2e")[0], 400)

    def test_published_and_local_proposal_projection_is_shared_and_redacted(self):
        cid = self.campaign()
        record = {"finding_id": "vuln_fixture"}
        self.record("rem_local", cid, "vuln_fixture", status="validated", title="Safe title",
                    source="SENSITIVE-SOURCE", attempts=[{"output": "SENSITIVE-OUTPUT"}],
                    validation={"before": [{"name": "run", "kind": "unit", "passed": True,
                                            "exit_code": 0, "output": "SENSITIVE-OUTPUT"}]})
        self.record("rem_published", cid, "vuln_fixture", published=True, status="validated",
                    publication={"url": "https://github.com/example/repo/pull/8?token=SENSITIVE-TOKEN#SENSITIVE-FRAGMENT",
                                 "id": 8, "state": "open", "completed_at": "2026-10-28T00:00:00Z"})
        self.record("rem_incomplete", cid, "vuln_fixture", published=True, publication={"id": 9})
        status, found = self.get("/api/v1/pull-requests/finding/vuln_fixture?campaign_id=" + cid)
        self.assertEqual(status, 200)
        self.assertEqual(found["total"], 3)
        by_id = {r["id"]: r for r in found["data"]}
        self.assertEqual(by_id["rem_local"]["record_type"], "local_proposal")
        self.assertIsNone(by_id["rem_local"]["url"])
        self.assertEqual(by_id["rem_published"]["record_type"], "published_pr")
        self.assertEqual(by_id["rem_published"]["url"], "https://github.com/example/repo/pull/8")
        self.assertEqual(by_id["rem_published"]["pr_id"], 8)
        self.assertEqual(by_id["rem_incomplete"]["record_type"], "local_proposal")
        self.assertTrue(by_id["rem_incomplete"]["publication_recorded"])
        self.assertFalse(by_id["rem_incomplete"]["published"])
        collection = self.get("/api/v1/pull-requests")[1]["data"]
        self.assertEqual({r["id"]: r for r in collection}, by_id)
        for row in collection:
            detail = self.get("/api/v1/pull-requests/" + row["id"])[1]["data"]
            self.assertEqual(row, detail)
        for secret in ("SENSITIVE-SOURCE", "SENSITIVE-TOKEN", "SENSITIVE-FRAGMENT",
                       "SENSITIVE-OUTPUT", "SENSITIVE-CREDENTIAL", "patch_path", "worktree", "evidence"):
            self.assertNotIn(secret, json.dumps(found) + json.dumps(collection))
        self.assertEqual(self.get("/api/v1/pull-requests/not-found")[0], 404)

    def test_lifecycle_read_auth_for_viewer_and_anonymous(self):
        cid = self.campaign()
        tid = data.load_campaign(cid)["target_id"]
        paths = ("/api/v1/targets/" + tid + "/evolution",
                 "/api/v1/vulnerabilities/history",
                 "/api/v1/pull-requests/finding/vuln_fixture?campaign_id=" + cid)
        self.service.accounts.create("readonly", "strong-viewer-password", "viewer")
        token = self.service.accounts.login("readonly", "strong-viewer-password", "127.0.0.1")["token"]
        for path in paths:
            self.assertEqual(self.get(path, auth=False)[0], 401)
            self.assertEqual(self.get(path, headers={"Authorization": "Bearer " + token})[0], 200)
