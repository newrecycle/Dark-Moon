#!/usr/bin/env python3
"""Offline authenticated-transport checks for the Splunk HEC forwarder.

All I/O is replaced with local response doubles. No Splunk host, Darkmoon
target, network request, subscription/license or native vendor executable is
needed. Run: python -m unittest discover -s integrations/upstream/splunk/test
-p 'test_forwarder_transport.py' -v
"""
import importlib.util
import json
import ssl
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "forwarder" / "darkmoon-to-hec.py"
spec = importlib.util.spec_from_file_location("darkmoon_to_hec_transport", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size=-1):
        return self.payload[:size]


class TransportContractTests(unittest.TestCase):
    def test_verified_mode_accepts_https_and_rejects_http(self):
        self.assertEqual(mod.checked_url("https://splunk.example.invalid:8088/services/collector/event"),
                         "https://splunk.example.invalid:8088/services/collector/event")
        with self.assertRaisesRegex(ValueError, "HTTPS is required"):
            mod.checked_url("http://splunk.example.invalid:8088/services/collector/event")
        self.assertEqual(mod.checked_url("http://127.0.0.1:8088/services/collector/event", verify=False),
                         "http://127.0.0.1:8088/services/collector/event")
        self.assertEqual(mod.checked_url("https://splunk.example.invalid/", verify=False),
                         "https://splunk.example.invalid")

    def test_rejects_credentials_query_fragment_bad_ports_controls_and_schemes(self):
        invalid = (
            "https://user:pass@splunk.example.invalid/path",
            "https://splunk.example.invalid/path?token=hidden",
            "https://splunk.example.invalid/path#token",
            "https://splunk.example.invalid:bad/path",
            "https://splunk.example.invalid:65536/path",
            "https://splunk.example.invalid/path\nX-Injected: 1",
            " https://splunk.example.invalid/path",
            "https://splunk.example.invalid/path ",
            "file:///etc/passwd",
            "ftp://splunk.example.invalid",
            "//splunk.example.invalid/path",
            "https:///missing-host",
            "",
            None,
        )
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                mod.checked_url(url, verify=False)

    def test_plaintext_rest_refused_before_fetch_or_authorization(self):
        with patch.object(mod, "_get_json", side_effect=AssertionError("should not request")):
            with self.assertRaisesRegex(ValueError, "HTTPS is required"):
                mod.poll_rest("http://127.0.0.1:4040", "sensitive-rest-token", verify=True)

    def test_get_json_rechecks_transport_at_request_boundary(self):
        with patch.object(mod, "open_request", side_effect=AssertionError("should not open")):
            with self.assertRaisesRegex(ValueError, "HTTPS is required"):
                mod._get_json("http://127.0.0.1/api/v1/campaigns",
                              {"Authorization": "Bearer sensitive-token"}, verify=True)

    def test_verified_rest_uses_bearer_header_and_exact_allowlisted_paths(self):
        calls = []
        def get_json(url, headers, verify):
            calls.append((url, dict(headers), verify))
            return {"data": [{"id": "safe_id"}]}
        with patch.object(mod, "_get_json", side_effect=get_json):
            records = mod.poll_rest("https://darkmoon.example.invalid/api/v1", "test-token", verify=True)
        self.assertEqual(set(records), {"campaigns", "vulnerabilities", "pull_requests", "retests", "targets"})
        self.assertEqual([url for url, _, _ in calls], [
            "https://darkmoon.example.invalid/api/v1/campaigns",
            "https://darkmoon.example.invalid/api/v1/vulnerabilities",
            "https://darkmoon.example.invalid/api/v1/pull-requests",
            "https://darkmoon.example.invalid/api/v1/retest",
            "https://darkmoon.example.invalid/api/v1/targets",
        ])
        self.assertTrue(all(headers["Authorization"] == "Bearer test-token"
                            and headers["Accept"] == "application/json" and verify
                            for _, headers, verify in calls))

    def test_plaintext_hec_refused_before_network_or_token_transmission(self):
        with patch.object(mod, "open_request", side_effect=AssertionError("should not request")):
            with self.assertRaisesRegex(ValueError, "HTTPS is required"):
                mod.send_hec("http://splunk.example.invalid/services/collector/event",
                             "sensitive-hec-token", [{"event": {"status": "ok"}}], verify=True,
                             max_retries=0)

    def test_verified_https_posts_correct_hec_headers_and_payload(self):
        messages = []
        event = {"time": 1000, "sourcetype": "darkmoon:finding", "event": {"finding_id": "x"}}
        def open_fake(request, context, timeout):
            messages.append((request, context, timeout))
            return Response(b'{"code":0,"text":"Success"}')
        with patch.object(mod, "open_request", side_effect=open_fake):
            sent = mod.send_hec("https://splunk.example.invalid:8088/services/collector/event",
                                "hec-token", [event], verify=True, max_retries=0)
        self.assertEqual(sent, 1)
        self.assertEqual(len(messages), 1)
        request, context, timeout = messages[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Splunk hec-token")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertIsInstance(request.get_header("X-splunk-request-channel"), str)
        self.assertEqual(json.loads(request.data), event)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(timeout, 30)

    def test_lab_http_requires_explicit_insecure_and_sets_context(self):
        contexts = []
        def fake(request, context, timeout):
            contexts.append(context)
            return Response(b'{"code":0}')
        with patch.object(mod, "open_request", side_effect=fake):
            self.assertEqual(mod.send_hec("http://127.0.0.1:8088/services/collector/event",
                                          "lab-token", [{"event": 1}], verify=False,
                                          max_retries=0), 1)
        self.assertFalse(contexts[0].check_hostname)
        self.assertEqual(contexts[0].verify_mode, ssl.CERT_NONE)

    def test_redirects_and_nonretryable_http_errors_fail_closed(self):
        self.assertIsNone(mod.NoRedirect().redirect_request(
            None, None, 302, "Location", {}, "https://untrusted.example.invalid"))
        for code in (301, 302, 307, 400, 401, 403, 404):
            calls = []
            def reject(*args):
                calls.append(args)
                raise urllib.error.HTTPError("https://splunk.example.invalid", code,
                                             "Rejected", {}, None)
            with self.subTest(code=code), patch.object(mod, "open_request", side_effect=reject):
                with self.assertRaisesRegex(RuntimeError, "HEC rejected"):
                    mod.send_hec("https://splunk.example.invalid/services/collector/event",
                                 "no-leak-token", [{"event": 1}], verify=True, max_retries=4)
            self.assertEqual(len(calls), 1)

    def test_retriable_429_then_success(self):
        requests = []
        def retry(request, context, timeout):
            requests.append(request)
            if len(requests) == 1:
                raise urllib.error.HTTPError(request.full_url, 429, "Rate limited", {}, None)
            return Response(b'{"code":0}')
        with patch.object(mod, "open_request", side_effect=retry), patch.object(mod.time, "sleep") as sleep:
            sent = mod.send_hec("https://splunk.example.invalid/services/collector/event",
                                "token", [{"event": 1}, {"event": 2}], verify=True,
                                max_retries=1, batch_size=2)
        self.assertEqual(sent, 2)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].data, requests[1].data)
        sleep.assert_called_once()

    def test_hec_response_code_is_strict_integer_zero(self):
        bad = (b'{"code":false}', b'{"code":"0"}', b'{"code":1}',
               b'{"error":"unauthorized"}', b'[]', b'not-json')
        for payload in bad:
            with self.subTest(payload=payload), patch.object(mod, "open_request",
                    return_value=Response(payload)):
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    mod.send_hec("https://splunk.example.invalid/services/collector/event",
                                 "token", [{"event": 1}], verify=True, max_retries=0)

    def test_untrusted_rest_response_shape_does_not_turn_into_empty_batches(self):
        with patch.object(mod, "_get_json", return_value={"error": "unavailable"}):
            with self.assertRaisesRegex(ValueError, "data array"):
                mod.poll_rest("https://darkmoon.example.invalid", "token", True)


if __name__ == "__main__":
    unittest.main()
