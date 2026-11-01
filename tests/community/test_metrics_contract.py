"""Real HTTP metric bounds, missing dates and protected-label checks."""
import json
import threading

import test_community as fixtures
from api import json_storage as data
from community.server import HTTPServer, handler_for


class MetricsContractTests(fixtures.Fixture):
    request = fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(self.service, {"127.0.0.1"}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        super().tearDown()

    def get(self, query=""):
        status, body, _ = self.request("/api/v1/metrics/timeseries" + query)
        return status, json.loads(body)

    def save(self, cid, date, **fields):
        data.save_campaign({"id": cid, "date": date, "target_id": "t1", "project_id": "p1"})
        data.save_vulnerabilities(cid, [{"id": "f1", "campaign_id": cid, "severity": "high",
                                      "status": "confirmed", "category": "sqli", **fields}])

    def test_offsets_and_date_only_records_use_utc_and_missing_dates_are_skipped(self):
        for cid, date in [("offset", "2026-11-01T00:30:00+02:00"), ("calendar", "2026-10-31"),
                          ("missing", None), ("invalid", "not a date"), ("ambiguous", "2026-10-31T10:00:00")]:
            self.save(cid, date)
        status, body = self.get()
        self.assertEqual(status, 200)
        self.assertEqual(body["series"], [{"key": "high", "points": [{"t": "2026-10-31", "value": 2}]}])

    def test_campaign_group_and_day_buckets_align_zero_counts_without_evidence(self):
        self.save("first", "2026-10-30T12:00:00Z", evidence={"output": "PRIVATE-METRIC"})
        self.save("second", "2026-10-31T12:00:00Z", severity="low")
        data.save_campaign({"id": "empty", "date": "2026-11-01T12:00:00Z"})
        status, body = self.get("?group=campaign")
        self.assertEqual(status, 200)
        self.assertEqual(body["series"], [
            {"key": "high", "points": [{"t": "first", "value": 1}, {"t": "second", "value": 0}, {"t": "empty", "value": 0}]},
            {"key": "low", "points": [{"t": "first", "value": 0}, {"t": "second", "value": 1}, {"t": "empty", "value": 0}]}])
        self.assertNotIn("PRIVATE-METRIC", json.dumps(body))
        day = self.get()[1]
        self.assertEqual([p["t"] for p in day["series"][0]["points"]], ["2026-10-30", "2026-10-31", "2026-11-01"])
        self.assertEqual([p["value"] for p in day["series"][0]["points"]], [1, 0, 0])
        campaigns = self.get("?group=campaign&metric=campaigns")[1]
        self.assertEqual([p["value"] for p in campaigns["series"][0]["points"]], [1, 1, 1])

    def test_undated_campaign_group_does_not_invent_a_timestamp(self):
        self.save("undated", None)
        self.assertEqual(self.get("?group=campaign")[1]["series"][0]["points"], [{"t": "undated", "value": 1}])
        self.assertEqual(self.get("?group=campaign&from=2026-01-01T00:00:00Z")[1]["series"], [])

    def test_timestamp_bounds_keep_existing_inclusive_end_and_exact_target_filter(self):
        self.save("before", "2026-10-30T23:59:59Z")
        self.save("start", "2026-10-31T00:00:00Z")
        self.save("end", "2026-10-31T01:00:00Z")
        self.save("after", "2026-10-31T01:00:01Z")
        status, body = self.get("?from=2026-10-31T00:00:00Z&to=2026-10-31T01:00:00Z&target_id=t1&group=hour")
        self.assertEqual(status, 200)
        self.assertEqual(body["series"][0]["points"], [
            {"t": "2026-10-31T00:00:00Z", "value": 1}, {"t": "2026-10-31T01:00:00Z", "value": 1}])
        self.assertEqual(self.get("?target_id=missing")[1]["series"], [])
        status, exact = self.get("?from=2026-10-31T01:00:00Z&to=2026-10-31T01:00:00Z&group=hour")
        self.assertEqual(status, 200)
        self.assertEqual(exact["series"][0]["points"], [{"t": "2026-10-31T01:00:00Z", "value": 1}])

    def test_free_form_metric_labels_cannot_disclose_evidence(self):
        self.save("labels", "2026-10-31T00:00:00Z", category="PRIVATE-METRIC-CATEGORY",
                  severity="PRIVATE-METRIC-SEVERITY", status="PRIVATE-METRIC-STATUS",
                  evidence={"output": "PRIVATE-METRIC-EVIDENCE"})
        for metric in ("category", "severity", "status"):
            with self.subTest(metric=metric):
                status, body = self.get("?metric=" + metric)
                self.assertEqual(status, 200)
                self.assertNotIn("PRIVATE-METRIC", json.dumps(body))
                self.assertEqual(body["series"][0]["key"], "unknown")

    def test_blank_repeated_unknown_and_naive_bound_parameters_are_rejected(self):
        for query in ("?metric=", "?group=day&group=week", "?unknown=1", "?target_id=",
                      "?from=bad", "?from=2026-10-31", "?from=2026-10-31T10:00:00",
                      "?from=2026-10-31T10:00:00Z&to=2026-10-31T09:00:00Z"):
            with self.subTest(query=query): self.assertEqual(self.get(query)[0], 400)
        self.assertEqual(self.request("/api/v1/metrics/timeseries", auth=False)[0], 401)
