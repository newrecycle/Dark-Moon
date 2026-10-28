"""Offline webhook inspection, synthetic admission and signed transport verification.

No network calls leave loopback: HTTPSConnection, DNS and socket connection
are replaced in transport tests. Assessment queues are not started.
"""
import concurrent.futures
import http.client
import json
import os
import re
import ssl
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_community as fixtures
from community.operations import (
    Operations, WebhookTestRateLimitError, deliver_https, signed_headers,
    verify_delivery, WEBHOOK_TEST_COOLDOWN,
)
from community.server import HTTPServer, handler_for
from community.store import Store


SECRET = "fixture-webhook-private-signing-secret-123456"
URL = "https://receiver.example.invalid/private/TOKEN-IN-PATH?access_token=URL-SECRET"


class WebhookInspectionHTTPTests(fixtures.Fixture):
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

    def register(self, **overrides):
        raw = {"url": URL, "events": ["finding.exploited"], "secret": SECRET}
        raw.update(overrides)
        status, body, _ = self.request("/api/v1/webhooks", "POST", raw)
        self.assertEqual(status, 201, body)
        return json.loads(body)["data"]

    def other_role(self, role):
        username = "webhook_" + role
        self.service.accounts.create(username, "a-long-webhook-role-password", role)
        token = self.service.accounts.login(username, "a-long-webhook-role-password", "127.0.0.1")["token"]
        return {"Authorization": "Bearer " + token}

    def test_admin_only_detail_listing_and_registration_do_not_leak_secrets(self):
        hook = self.register()
        hook_id = hook["id"]
        self.assertEqual(hook["url"], "https://receiver.example.invalid")
        self.assertTrue(hook["url_redacted"])
        self.assertNotIn("credential_ref", hook)
        self.assertNotIn("secret", hook)
        for path in ("/api/v1/webhooks", "/api/v1/webhooks/" + hook_id):
            self.assertEqual(self.request(path, auth=False)[0], 401)
            for role in ("viewer", "analyst"):
                self.assertEqual(self.request(path, headers=self.other_role(role))[0], 403)
            status, body, _ = self.request(path)
            self.assertEqual(status, 200)
            payload = json.loads(body)
            item = payload["data"][0] if isinstance(payload["data"], list) else payload["data"]
            self.assertEqual(item, hook)
            for disallowed in ("credential_ref", "sealed", SECRET, "TOKEN-IN-PATH", "URL-SECRET", "private"):
                self.assertNotIn(disallowed, body.decode())
        self.assertEqual(self.request("/api/v1/webhooks/missing")[0], 404)
        stored = self.service.store.get("webhooks", hook_id)
        self.assertIn("credential_ref", stored)
        self.assertEqual(self.service.vault.resolve(stored["credential_ref"]), SECRET)
        self.assertNotIn(SECRET, self.service.store.path.read_text())

    def test_generated_signing_secret_is_one_time_only_and_rejects_insecure_urls(self):
        status, body, _ = self.request("/api/v1/webhooks", "POST", {"url": "https://fresh.example.invalid/secret"})
        self.assertEqual(status, 201)
        registered = json.loads(body)["data"]
        self.assertGreaterEqual(len(registered["secret"]), 24)
        for path in ("/api/v1/webhooks", "/api/v1/webhooks/" + registered["id"]):
            self.assertNotIn(registered["secret"], self.request(path)[1].decode())
        for invalid in ("http://receiver.example.invalid/a", "https://user:pass@receiver.example.invalid",
                        "https://receiver.example.invalid/a#secret", "https://receiver.example.invalid:99999/x"):
            self.assertEqual(self.request("/api/v1/webhooks", "POST", {"url": invalid})[0], 400)
        self.assertEqual(self.request("/api/v1/webhooks", "POST",
                                      {"url": URL, "format": "splunk_hec"})[0], 400)

    def test_explicit_test_is_admin_only_body_constrained_and_targeted(self):
        primary, other = self.register(), self.register()
        endpoint = "/api/v1/webhooks/" + primary["id"] + "/test"
        self.assertEqual(self.request(endpoint, "POST", auth=False)[0], 401)
        for role in ("viewer", "analyst"):
            self.assertEqual(self.request(endpoint, "POST", headers=self.other_role(role))[0], 403)
        for override in ({"url": "https://another.example.invalid"}, {"headers": {"X-Test": "override"}},
                         {"secret": SECRET}, {"event": "campaign.completed"}, {"data": {"finding_id": "fake"}}):
            self.assertEqual(self.request(endpoint, "POST", override)[0], 400)
        self.assertEqual(self.service.store.items("deliveries"), [])
        status, body, headers = self.request(endpoint, "POST")
        self.assertEqual(status, 202, body)
        self.assertEqual(headers["Cache-Control"], "no-store")
        accepted = json.loads(body)["data"]
        self.assertEqual(accepted["status"], "pending")
        self.assertTrue(accepted["accepted"])
        self.assertRegex(accepted["event_id"], r"^evt_test_[a-f0-9]{32}$")
        self.assertRegex(accepted["delivery_id"], r"^delivery_[a-f0-9]{32}$")
        delivery = self.service.store.get("deliveries", accepted["delivery_id"])
        self.assertEqual(delivery["webhook_id"], primary["id"])
        self.assertEqual(delivery["event"]["event"], "webhook.test")
        self.assertTrue(delivery["event"]["synthetic"])
        self.assertEqual(delivery["event"]["data"], {"synthetic": True, "purpose": "delivery_validation"})
        self.assertEqual(self.service.store.items("events"), [])
        self.assertEqual(len(self.service.store.items("deliveries")), 1)
        self.assertEqual(self.request("/api/v1/webhooks/" + other["id"] + "/deliveries")[0], 200)
        status, body, _ = self.request("/api/v1/webhooks/" + primary["id"] + "/deliveries")
        self.assertEqual(status, 200)
        detail = json.loads(body)["data"][0]
        self.assertEqual(detail["id"], accepted["delivery_id"])
        self.assertTrue(detail["synthetic"])
        self.assertNotIn("data", detail)
        self.assertNotIn("event", json.dumps(detail.get("data", {})))
        self.assertEqual(self.request(endpoint, "POST", {})[0], 429)
        self.assertEqual(self.request("/api/v1/webhooks/unknown/test", "POST")[0], 404)
        self.assertEqual(self.request("/api/v1/webhooks/unknown/deliveries")[0], 404)
        # Bodyless and explicitly empty JSON are both accepted on distinct hooks.
        self.assertEqual(self.request("/api/v1/webhooks/" + other["id"] + "/test", "POST", {})[0], 202)

    def test_disabled_deleted_and_missing_signer_fail_closed_without_queue_pressure(self):
        hook = self.register()
        endpoint = "/api/v1/webhooks/" + hook["id"] + "/test"
        record = self.service.store.get("webhooks", hook["id"])
        record["enabled"] = False
        self.service.store.save("webhooks", record)
        self.assertEqual(self.request(endpoint, "POST")[0], 409)
        record["enabled"] = True
        self.service.store.save("webhooks", record)
        cred = self.service.store.get("credentials", record["credential_ref"])
        def remove_signer(state):
            state["credentials"].pop(cred["id"])
        self.service.store.update(remove_signer)
        self.assertEqual(self.request(endpoint, "POST")[0], 409)
        self.service.store.save("credentials", cred)
        status, body, _ = self.request(endpoint, "POST")
        self.assertEqual(status, 202, body)
        delivery_id = json.loads(body)["data"]["delivery_id"]
        self.assertEqual(self.request("/api/v1/webhooks/" + hook["id"], "DELETE")[0], 200)
        self.assertEqual(self.service.store.get("deliveries", delivery_id)["status"], "cancelled")
        self.assertNotIn(hook["id"], self.service.store.read().get("webhook_test_last", {}))
        self.assertNotIn(hook["id"], self.service.store.read().get("webhook_receipts", {}))
        self.assertEqual(self.request(endpoint, "POST")[0], 404)

    def test_delivery_inspection_returns_only_generic_error_metadata(self):
        hook = self.register()
        delivery = self.service.operations._delivery(hook["id"], {
            "id": "evt_error", "event": "webhook.test", "data": {"secret": SECRET}})
        delivery.update(status="failed", error="REMOTE-BODY-PRIVATE", response_body="PRIVATE", url=URL)
        self.service.store.save("deliveries", delivery)
        status, body, _ = self.request("/api/v1/webhooks/" + hook["id"] + "/deliveries")
        self.assertEqual(status, 200)
        safe = body.decode()
        for private in (SECRET, "REMOTE-BODY-PRIVATE", "PRIVATE", "TOKEN-IN-PATH", "URL-SECRET"):
            self.assertNotIn(private, safe)
        self.assertEqual(json.loads(body)["data"][0]["error"],
                         "Delivery failed; destination or network unavailable")


class WebhookQueueVerificationTests(fixtures.Fixture):
    def register(self, events=None):
        return self.service.operations.register({"url": URL, "events": events if events is not None else [],
                                                 "secret": SECRET})["id"]

    def test_atomic_rate_limit_survives_restart_and_uses_unique_event_ids(self):
        hook = self.register()
        def submit(_):
            try:
                return self.service.operations.test_webhook(hook)
            except WebhookTestRateLimitError:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(submit, range(8)))
        accepted = [r for r in results if r]
        self.assertEqual(len(accepted), 1)
        second = Operations(SimpleNamespace(store=Store(self.service.store.root)))
        with self.assertRaises(WebhookTestRateLimitError):
            second.test_webhook(hook)
        self.service.store.update(lambda state: state["webhook_test_last"].update({hook: 0}))
        again = second.test_webhook(hook)
        self.assertNotEqual(again["event_id"], accepted[0]["event_id"])
        self.assertNotEqual(again["delivery_id"], accepted[0]["delivery_id"])

    def test_pending_queue_global_and_per_hook_caps_fail_without_eviction(self):
        hook = self.register()
        with patch("community.operations.MAX_PENDING_DELIVERIES", 0):
            with self.assertRaises(WebhookTestRateLimitError):
                self.service.operations.test_webhook(hook)
        self.assertFalse(self.service.store.items("deliveries"))
        with patch("community.operations.MAX_PENDING_TESTS_PER_HOOK", 2):
            for _ in range(2):
                self.service.store.update(lambda state: state.setdefault("webhook_test_last", {}).update({hook: 0}))
                self.service.operations.test_webhook(hook)
            self.service.store.update(lambda state: state["webhook_test_last"].update({hook: 0}))
            with self.assertRaises(WebhookTestRateLimitError):
                self.service.operations.test_webhook(hook)
        self.assertEqual(len(self.service.store.items("deliveries")), 2)

    def test_signed_delivery_uses_only_selected_hook_and_correct_queue_outcome(self):
        selected = self.register(events=["campaign.completed"])
        other = self.register(events=["*"])
        accepted = self.service.operations.test_webhook(selected)
        captured = []
        def transport(url, body, headers):
            captured.append((url, body, headers))
            return 204
        operations = self.service.operations
        operations.transport = transport
        operations.initialized = True
        with patch.object(self.service, "snapshot", return_value={
            "campaigns": [], "findings": [], "remediations": []}):
            operations.tick()
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][0], URL)
        self.assertTrue(verify_delivery(SECRET, captured[0][1], captured[0][2], set(),
                                        clock=int(captured[0][2]["X-Darkmoon-Timestamp"])))
        payload = json.loads(captured[0][1])
        self.assertEqual(payload["id"], accepted["event_id"])
        self.assertEqual(payload["delivery_id"], accepted["delivery_id"])
        self.assertEqual(payload["event"], "webhook.test")
        self.assertEqual(payload["data"], {"synthetic": True, "purpose": "delivery_validation"})
        self.assertEqual(self.service.store.get("deliveries", accepted["delivery_id"])["status"], "delivered")
        self.assertEqual(self.service.store.items("events"), [])
        self.assertFalse([d for d in self.service.store.items("deliveries") if d["webhook_id"] == other])

    def test_retries_are_bounded_and_errors_remain_generic(self):
        hook = self.register()
        accepted = self.service.operations.test_webhook(hook)
        operations = self.service.operations
        operations.initialized = True
        def failing(*args):
            raise RuntimeError("REMOTE-PRIVATE-ERROR-BODY")
        operations.transport = failing
        with patch.object(self.service, "snapshot", return_value={
            "campaigns": [], "findings": [], "remediations": []}):
            for attempt in range(1, 6):
                self.service.store.update(lambda state: state["deliveries"][accepted["delivery_id"]].update(
                    {"next_attempt": 0}))
                operations.tick()
                d = self.service.store.get("deliveries", accepted["delivery_id"])
                self.assertEqual(d["attempts"], attempt)
                self.assertEqual(d["status"], "failed" if attempt == 5 else "pending")
                self.assertNotIn("REMOTE-PRIVATE", json.dumps(d))
            operations.tick()
        self.assertEqual(self.service.store.get("deliveries", accepted["delivery_id"])["attempts"], 5)

    def test_disabled_before_dispatch_cancels_without_transport(self):
        hook = self.register()
        accepted = self.service.operations.test_webhook(hook)
        record = self.service.store.get("webhooks", hook)
        record["enabled"] = False
        self.service.store.save("webhooks", record)
        transport = Mock(side_effect=AssertionError("must not send"))
        operations = self.service.operations
        operations.transport = transport
        operations.initialized = True
        with patch.object(self.service, "snapshot", return_value={
            "campaigns": [], "findings": [], "remediations": []}):
            operations.tick()
        transport.assert_not_called()
        self.assertEqual(self.service.store.get("deliveries", accepted["delivery_id"])["status"], "cancelled")


class WebhookHTTPSBoundaryTests(fixtures.Fixture):
    def test_dns_pin_tls_hostname_redirect_refusal_and_bounded_read(self):
        captured = {}
        class Response:
            status = 302
            def read(self, size):
                captured["read_limit"] = size
                return b"location withheld"
        class Connection:
            def __init__(self, hostname, port, context, timeout):
                captured.update(hostname=hostname, port=port, context=context, timeout=timeout)
            def request(self, method, path, body, headers):
                captured.update(method=method, path=path, body=body, headers=headers)
                self._create_connection(("ignored.rebinding.invalid", 443), 10)
            def getresponse(self):
                return Response()
            def close(self):
                captured["closed"] = True
        addr = [(2, 1, 6, "", ("9.9.9.9", 443))]
        with patch("community.operations.socket.getaddrinfo", return_value=addr), \
             patch("community.operations.socket.create_connection", return_value=object()) as connect, \
             patch("community.operations.http.client.HTTPSConnection", Connection):
            result = deliver_https("https://receiver.example.invalid/test?key=opaque", b"{}", {"Content-Type": "application/json"})
        self.assertEqual(result, 302)
        self.assertEqual(captured["hostname"], "receiver.example.invalid")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/test?key=opaque")
        self.assertEqual(captured["read_limit"], 4096)
        self.assertTrue(captured["closed"])
        self.assertTrue(captured["context"].check_hostname)
        self.assertEqual(captured["context"].verify_mode, ssl.CERT_REQUIRED)
        connect.assert_called_once()
        self.assertEqual(connect.call_args.args[0], ("9.9.9.9", 443))

    def test_mixed_private_dns_denied_and_only_exact_host_allowlist_bypasses(self):
        public = (2, 1, 6, "", ("9.9.9.9", 443))
        private = (2, 1, 6, "", ("127.0.0.1", 443))
        with patch("community.operations.socket.getaddrinfo", return_value=[public, private]), \
             patch("community.operations.http.client.HTTPSConnection") as connect:
            with self.assertRaises(ValueError):
                deliver_https("https://receiver.example.invalid/hook", b"{}", {})
            connect.assert_not_called()
        with patch("community.operations.socket.getaddrinfo", return_value=[private]), \
             patch.dict(os.environ, {"DARKMOON_WEBHOOK_ALLOWED_HOSTS": "other.example.invalid"}), \
             patch("community.operations.http.client.HTTPSConnection") as connect:
            with self.assertRaises(ValueError):
                deliver_https("https://receiver.example.invalid/hook", b"{}", {})
            connect.assert_not_called()
        with patch("community.operations.socket.getaddrinfo", return_value=[private]), \
             patch.dict(os.environ, {"DARKMOON_WEBHOOK_ALLOWED_HOSTS": "receiver.example.invalid"}), \
             patch("community.operations.http.client.HTTPSConnection") as connect:
            connect.return_value.getresponse.return_value.status = 202
            self.assertEqual(deliver_https("https://receiver.example.invalid/hook", b"{}", {}), 202)
            connect.assert_called_once()

    def test_rejects_non_https_credential_fragments_and_bad_ports_before_dns(self):
        with patch("community.operations.socket.getaddrinfo") as dns:
            for uri in ("http://receiver.example.invalid", "https://a:b@receiver.example.invalid/a",
                        "https://receiver.example.invalid/#token", "https://receiver.example.invalid:99999/",
                        "https://receiver.example.invalid:0/", "https:///missing-host"):
                with self.assertRaises(ValueError, msg=uri):
                    deliver_https(uri, b"{}", {})
            dns.assert_not_called()
