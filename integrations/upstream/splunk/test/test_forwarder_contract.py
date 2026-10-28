#!/usr/bin/env python3
"""Offline Splunk forwarder contract checks. Never contacts Splunk or Darkmoon.

Run: python -m unittest discover -s integrations/upstream/splunk/test
     -p test_forwarder_contract.py -v
"""
import importlib.util
import io
import json
import math
import pathlib
import urllib.error
import urllib.request
import unittest
from unittest.mock import patch


PATH = pathlib.Path(__file__).resolve().parents[1] / "forwarder" / "darkmoon-to-hec.py"
spec = importlib.util.spec_from_file_location("darkmoon_to_hec_isolated", PATH)
forwarder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(forwarder)


class Response:
    def __init__(self, data):
        self.stream = io.BytesIO(json.dumps(data).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, amount=None):
        return self.stream.read(amount)


class ForwarderContracts(unittest.TestCase):
    def test_all_event_types_allowlist_unknown_fields_and_scrub_secret_markers(self):
        payload = {
            "campaigns": [{"id": "camp_1", "status": "completed", "target": "https://u:pass@owned.invalid/a?token=URL_SECRET", "secret": "KEEP_OUT", "stats": {"high": 2, "private": "KEEP_OUT"}}],
            "vulnerabilities": [{"id": "vuln_1", "campaign_id": "camp_1", "severity": "high", "status": "confirmed", "title": "bearer abc123secret", "evidence": {"output": "KEEP_OUT"}}],
            "retests": [{"id": "retest_1", "status": "running", "new_status": "unconfirmed", "secret": "KEEP_OUT"}],
            "pull_requests": [{"id": "rem_1", "published": False, "status": "proposed", "secret": "KEEP_OUT"},
                              {"id": "pr_1", "published": True, "number": 5, "provider": "github", "secret": "KEEP_OUT"}],
        }
        rows = forwarder.build_events(payload)
        self.assertEqual([e["sourcetype"] for e in rows],
                         ["darkmoon:campaign", "darkmoon:finding", "darkmoon:retest", "darkmoon:remediation", "darkmoon:pr"])
        for row in rows:
            self.assertEqual(row["source"], "darkmoon")
            self.assertIn("event_id", row["event"])
            self.assertNotIn("fields", row)
            self.assertTrue(set(row["event"]) <= set(forwarder.SAFE_FIELDS[row["sourcetype"]]) | {"event_id", "high"})
            self.assertNotIn("KEEP_OUT", json.dumps(row))
            self.assertNotIn("abc123secret", json.dumps(row))
        self.assertEqual(rows[0]["event"]["campaign_id"], "camp_1")
        self.assertEqual(rows[1]["event"]["finding_id"], "vuln_1")
        self.assertEqual(rows[2]["event"]["event"], "retest.updated")
        self.assertEqual(rows[3]["event"]["proposal_id"], "rem_1")
        self.assertEqual(rows[4]["event"]["pr_id"], "pr_1")

    def test_hec_host_and_location_fields_drop_url_userinfo_query_and_fragment(self):
        raw = "https://alice:password-SUPERSECRET@owned.invalid/path?api_key=URLSECRET#FRAGMENTSECRET"
        campaign = forwarder.campaign_event({"id": "camp_1", "target": raw})
        finding = forwarder.finding_event({"id": "vuln_1", "target": raw, "endpoint": "GET " + raw})
        pr = forwarder.pr_event({"id": "pr_1", "published": True, "repo": raw, "url": raw})
        for row in (campaign, finding, pr):
            data = json.dumps(row)
            for secret in ("password-SUPERSECRET", "URLSECRET", "FRAGMENTSECRET", "alice:"):
                self.assertNotIn(secret, data)
            self.assertIn("owned.invalid", data)
        self.assertEqual(finding["event"]["endpoint"], "https://owned.invalid/path")

    def test_finite_typed_metadata_does_not_emit_nested_or_boolean_numbers(self):
        row = forwarder.campaign_event({"id": "camp_test", "duration_seconds": float("inf"),
            "stats": {"high": True, "low": -1, "critical": 2.25, "medium": 3, "private": [1, 2]}})
        self.assertNotIn("duration_seconds", row["event"])
        self.assertNotIn("high", row["event"])
        self.assertNotIn("critical", row["event"])
        self.assertNotIn("low", row["event"])
        self.assertEqual(row["event"]["medium"], 3)
        self.assertNotIn("private", row["event"])

    def test_snapshots_use_stable_content_event_identity(self):
        same = {"id": "vuln_one", "status": "confirmed", "severity": "high"}
        self.assertEqual(forwarder.finding_event(same)["event"]["event_id"],
                         forwarder.finding_event(same)["event"]["event_id"])
        changed = {**same, "severity": "critical"}
        self.assertNotEqual(forwarder.finding_event(same)["event"]["event_id"],
                            forwarder.finding_event(changed)["event"]["event_id"])

    def test_export_requires_typed_arrays(self):
        for item in ({}, [], {"campaigns": {}}, {"campaigns": ["bad"]},
                     {"campaigns": [], "vulnerabilities": [None]}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                forwarder.build_events(item)
        self.assertEqual(forwarder.build_events({"campaigns": []}), [])

    def test_http_urls_require_explicit_insecure_lab_mode(self):
        with patch.object(forwarder, "_get_json") as read:
            with self.assertRaises(ValueError):
                forwarder.poll_rest("http://127.0.0.1:9999", "PRIVATE-TOKEN", True)
            read.assert_not_called()
        with patch.object(forwarder, "open_request") as send:
            with self.assertRaises(ValueError):
                forwarder.send_hec("http://127.0.0.1:8088/services/collector/event",
                                   "PRIVATE-HEC-TOKEN", [{"event": {}}], True)
            send.assert_not_called()
        with patch.object(forwarder, "_get_json", return_value={"data": []}) as get:
            forwarder.poll_rest("http://127.0.0.1:9999", "token", False)
            self.assertEqual(get.call_count, 3)

    def test_url_credentials_query_fragment_always_refused(self):
        for url in ("https://u:p@host.invalid", "https://host.invalid/?token=x",
                    "https://host.invalid/path#frag", "file:///etc/passwd"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                forwarder.checked_url(url)

    def test_rest_poll_preserves_exact_arrays_and_authorization(self):
        observed = []
        def fake_get(url, headers, verify):
            observed.append((url, dict(headers), verify))
            return {"data": [{"id": "exact_id"}]}
        with patch.object(forwarder, "_get_json", side_effect=fake_get):
            result = forwarder.poll_rest("https://fork.invalid/api/v1", "FIXTURE-BEARER", True)
        self.assertEqual(set(result), {"campaigns", "vulnerabilities", "pull_requests"})
        self.assertEqual(len(observed), 3)
        self.assertTrue(all(url.startswith("https://fork.invalid/api/v1/") for url, _, _ in observed))
        self.assertTrue(all(headers["Authorization"] == "Bearer FIXTURE-BEARER" for _, headers, _ in observed))

    def test_rest_malformed_or_missing_arrays_fail_not_empty(self):
        for malformed in ({"unexpected": []}, {"data": {}}, {"data": [0]}, ["bad"]):
            with self.subTest(malformed=malformed):
                with patch.object(forwarder, "_get_json", return_value=malformed):
                    with self.assertRaises(ValueError):
                        forwarder.poll_rest("https://fork.invalid", "token", True)

    def test_hec_requires_http_success_and_typed_code_zero(self):
        events = [{"sourcetype": "darkmoon:campaign", "event": {"campaign_id": "camp_one"}}]
        for payload in ({"code": 1, "text": "invalid token"},
                        {"code": True}, {"code": "0"}, {}, []):
            calls = []
            def fake_open(req, context, timeout):
                calls.append(req)
                return Response(payload)
            with self.subTest(payload=payload), patch.object(forwarder, "open_request", side_effect=fake_open), \
                    patch.object(forwarder.time, "sleep") as sleep:
                with self.assertRaises(ValueError):
                    forwarder.send_hec("https://hec.invalid/services/collector/event",
                                       "PRIVATE-HEC", events, True, max_retries=3)
                self.assertEqual(len(calls), 1, "Explicit HEC application rejection must not replay the batch")
                sleep.assert_not_called()

    def test_hec_valid_ack_batches_and_sets_token_only_in_header(self):
        requests = []
        def fake_open(req, ctx, timeout):
            requests.append(req)
            return Response({"code": 0, "text": "Success"})
        events = [{"source": "darkmoon", "event": {"id": i}} for i in range(3)]
        with patch.object(forwarder, "open_request", side_effect=fake_open):
            sent = forwarder.send_hec("https://hec.invalid/services/collector/event",
                                      "PRIVATE-HEC", events, True, batch_size=2)
        self.assertEqual(sent, 3)
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(r.get_header("Authorization") == "Splunk PRIVATE-HEC" for r in requests))
        self.assertTrue(all(r.get_method() == "POST" for r in requests))
        self.assertTrue(all(b"PRIVATE-HEC" not in r.data for r in requests))
        self.assertEqual([len(r.data.decode().splitlines()) for r in requests], [2, 1])

    def test_redirects_and_permanent_4xx_are_not_retried(self):
        for code in (301, 302, 307, 400, 401, 403):
            def reject(req, context, timeout):
                raise urllib.error.HTTPError(req.full_url, code, "stop", {}, io.BytesIO(b"token=NEVERLOG"))
            with self.subTest(code=code), patch.object(forwarder, "open_request", side_effect=reject) as network, \
                    patch.object(forwarder.time, "sleep") as sleep:
                with self.assertRaises(RuntimeError):
                    forwarder.send_hec("https://hec.invalid/collector", "SECRET-HEC",
                                       [{"event": {}}], True, max_retries=3)
                self.assertEqual(network.call_count, 1)
                sleep.assert_not_called()

    def test_transient_http_failure_retries_boundedly(self):
        def respond(req, ctx, timeout):
            if respond.calls == 0:
                respond.calls += 1
                raise urllib.error.HTTPError(req.full_url, 503, "busy", {}, io.BytesIO())
            return Response({"code": 0})
        respond.calls = 0
        with patch.object(forwarder, "open_request", side_effect=respond) as requests, \
                patch.object(forwarder.time, "sleep") as sleep:
            sent = forwarder.send_hec("https://hec.invalid/collector", "TOKEN", [{"event": {}}], True, max_retries=2)
        self.assertEqual(sent, 1)
        self.assertEqual(requests.call_count, 2)
        sleep.assert_called_once()

    def test_no_ack_mode_and_invalid_batch_config(self):
        for kw in ({"batch_size": 0}, {"batch_size": 1001},
                   {"batch_size": True}, {"max_retries": -1},
                   {"max_retries": "bad"}, {"use_ack": True}):
            with self.subTest(kw=kw), patch.object(forwarder, "open_request") as network:
                with self.assertRaises(ValueError):
                    forwarder.send_hec("https://hec.invalid/collector", "TOKEN", [{"event": {}}], True, **kw)
                network.assert_not_called()

    def test_timestamp_naive_values_use_utc_not_host_local_timezone(self):
        from datetime import datetime, timezone
        want = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc).timestamp()
        self.assertEqual(forwarder.to_epoch("2026-10-28T12:00:00"), want)
        self.assertEqual(forwarder.to_epoch("2026-10-28T12:00:00Z"), want)
        self.assertTrue(math.isfinite(forwarder.to_epoch("")))


if __name__ == "__main__":
    unittest.main()
