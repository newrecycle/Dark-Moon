"""Overview counts, exact navigation identities and metadata-only responses."""
import json
import threading

import test_community as fixtures
from api import json_storage as data
from community.server import HTTPServer, handler_for


class OverviewHTTPTests(fixtures.Fixture):
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

    def overview(self, path="/api/v1/dashboard/overview"):
        status, body, _ = self.request(path)
        self.assertEqual(status, 200, body)
        self.assertNotIn(b"PROTECTED-OVERVIEW-TEXT", body)
        return json.loads(body)

    def populate(self):
        for suffix in ("a", "b"):
            data.save_project({"id": "proj_" + suffix, "name": "PROTECTED-OVERVIEW-TEXT"})
            data.save_target({"id": "tgt_" + suffix, "host": "PROTECTED-OVERVIEW-TEXT.invalid"})
        cases = [
            ("camp_0", "a", "2026-10-01T12:00:00Z", [("critical", "remediated"), ("high", "confirmed"), ("low", "false_positive")]),
            ("camp_1", "a", "2026-10-03T12:00:00Z", [("high", "confirmed")]),
            ("camp_2", "b", "2026-10-03T12:00:00Z", [("low", "exploited"), ("unknown", "confirmed")]),
            ("camp_3", "b", None, [("medium", "resolved")]),
        ]
        for cid, suffix, date, findings in cases:
            data.save_campaign({"id": cid, "project_id": "proj_" + suffix, "target_id": "tgt_" + suffix,
                                "date": date, "status": "completed", "target": "PROTECTED-OVERVIEW-TEXT.invalid"})
            data.save_vulnerabilities(cid, [
                {"id": "finding_" + str(index), "campaign_id": cid, "target_id": "tgt_" + suffix,
                 "severity": severity, "status": status, "category": "sqli", "title": "PROTECTED-OVERVIEW-TEXT",
                 "evidence": {"output": "PROTECTED-OVERVIEW-TEXT"}}
                for index, (severity, status) in enumerate(findings)])

    def test_empty_overview_and_idle_registered_records(self):
        empty = self.overview()
        self.assertEqual(empty["total_vulnerabilities"], 0)
        self.assertEqual(empty["severity_distribution"], {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0})
        self.assertEqual(empty["status_distribution"], {"exploited": 0, "confirmed": 0, "unconfirmed": 0, "remediated": 0})
        self.assertEqual(empty["category_distribution"], {})
        self.assertEqual(empty["recent_campaigns"], [])
        self.assertEqual(empty["targets_at_risk"], [])
        data.save_project({"id": "proj_idle", "name": "PROTECTED-OVERVIEW-TEXT"})
        data.save_target({"id": "tgt_idle", "host": "PROTECTED-OVERVIEW-TEXT.invalid"})
        idle = self.overview()
        self.assertEqual((idle["projects_count"], idle["targets_count"], idle["campaigns_count"]), (1, 1, 0))
        self.assertEqual(idle["recent_campaigns"], [])
        self.assertEqual(self.request("/api/v1/dashboard/overview", auth=False)[0], 401)

    def test_recent_campaigns_and_risk_rows_keep_exact_identity_and_cohorts(self):
        self.populate()
        result = self.overview()
        self.assertEqual(result["total_vulnerabilities"], 7)
        self.assertEqual(result["category_distribution"], {"sqli": 7})
        self.assertEqual(result["severity_distribution"]["critical"], 1)
        self.assertEqual(result["severity_distribution"]["unknown"], 1)
        recent = result["recent_campaigns"]
        self.assertEqual([r["campaign_id"] for r in recent], ["camp_1", "camp_2", "camp_0", "camp_3"])
        self.assertEqual([r["findings"] for r in recent], [1, 2, 3, 1])
        self.assertEqual([r["risk"] for r in recent], ["high", "low", "high", "none"])
        self.assertEqual(result["targets_at_risk"], [
            {"target_id": "tgt_a", "risk_level": "high", "open_vulns": 2},
            {"target_id": "tgt_b", "risk_level": "low", "open_vulns": 2}])

    def test_project_analytics_stays_within_the_selected_campaign_cohort(self):
        self.populate()
        result = self.overview("/api/v1/projects/proj_a/analytics")["data"]
        self.assertEqual((result["projects_count"], result["targets_count"], result["campaigns_count"]), (1, 1, 2))
        self.assertEqual(result["total_vulnerabilities"], 4)
        self.assertEqual({r["campaign_id"] for r in result["recent_campaigns"]}, {"camp_0", "camp_1"})
        self.assertEqual(result["targets_at_risk"], [{"target_id": "tgt_a", "risk_level": "high", "open_vulns": 2}])

    def test_recent_campaigns_are_bounded_without_losing_total_counts(self):
        for index in range(8):
            data.save_campaign({"id": "camp_" + str(index), "date": f"2026-10-{index+1:02}T12:00:00Z", "status": "completed"})
        result = self.overview()
        self.assertEqual(result["campaigns_count"], 8)
        self.assertEqual(len(result["recent_campaigns"]), 5)
        self.assertEqual([r["campaign_id"] for r in result["recent_campaigns"]], ["camp_7", "camp_6", "camp_5", "camp_4", "camp_3"])

    def test_producer_calendar_dates_sort_by_date_without_rewriting_records(self):
        original = [
            {"id": "camp_old", "date": "2026-01-01"},
            {"id": "camp_latest", "date": "2026-10-31"},
            {"id": "camp_middle", "date": "2026-10-30T23:30:00Z"},
            {"id": "camp_invalid", "date": "2026-99-99"},
        ]
        for campaign in original:
            data.save_campaign(campaign)
        result = self.overview()
        self.assertEqual([r["campaign_id"] for r in result["recent_campaigns"]],
                         ["camp_latest", "camp_middle", "camp_old", "camp_invalid"])
        self.assertEqual([data.load_campaign(c["id"])["date"] for c in original], [c["date"] for c in original])
