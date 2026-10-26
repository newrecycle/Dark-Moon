"""Profile lifecycle and real local HTTP model discovery contracts."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
import test_community as fixtures
from community import configuration, provider_checks, opencode


class ProviderManagementTests(fixtures.Fixture):
    def profile(self, **extra):
        return configuration.profile(
            self.service,
            {
                "name": "Local model",
                "provider": "local-test",
                "mode": "local",
                "model": "one",
                "base_url": "http://127.0.0.1:8081/v1",
                **extra,
            },
        )

    def test_named_profiles_keep_same_provider_without_overwriting(self):
        one = self.profile()
        two = self.profile(name="Second model", model="two")
        self.assertNotEqual(one["id"], two["id"])
        self.assertEqual(len(self.service.store.items("providers")), 2)
        updated = configuration.profile(
            self.service, one | {"name": "Edited", "model": "three"}, one["id"]
        )
        self.assertEqual(updated["id"], one["id"])
        self.assertEqual(updated["created_at"], one["created_at"])
        self.assertEqual(self.service.store.get("providers", two["id"])["model"], "two")

    def test_delete_saved_profile_preserves_running_configuration_and_logins(self):
        profile = self.profile()
        configuration.apply(self.service, profile["id"])
        paths = opencode.paths(self.service)
        before = [p.read_bytes() for p in paths]
        configuration.remove(self.service, profile["id"])
        self.assertEqual(before, [p.read_bytes() for p in paths])
        self.assertFalse(self.service.store.get("providers", profile["id"]))

    def test_discovered_models_are_registered_when_applied(self):
        profile = self.profile(
            models=[{"id": "one", "name": "First"}, {"id": "two", "name": "Second"}]
        )
        configuration.apply(self.service, profile["id"])
        config = json.loads(opencode.paths(self.service)[0].read_text())
        self.assertEqual(
            set(config["provider"]["local-test"]["models"]), {"one", "two"}
        )

    def test_discovery_requires_compatible_url_and_safe_header(self):
        for url in (
            "file:///tmp/token",
            "https://user:password@example.test/v1",
            "https://example.test/v1?key=secret",
            "https://example.test/v1#fragment",
        ):
            with self.assertRaises(ValueError):
                provider_checks.endpoint_models(
                    self.service, {"mode": "local", "base_url": url}
                )
        key = self.service.vault.save({"name": "Bad", "secret": "private\nsecret"})
        with self.assertRaises(ValueError) as caught:
            provider_checks.endpoint_models(
                self.service,
                {
                    "mode": "local",
                    "base_url": "https://example.test/v1",
                    "credential_id": key["id"],
                },
            )
        self.assertNotIn("private", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))

    def test_endpoint_model_checks_use_real_http_and_hide_error_bodies(self):
        observed = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                observed.append(
                    {
                        "path": self.path,
                        "auth": self.headers.get("Authorization"),
                        "anthropic": self.headers.get("x-api-key"),
                    }
                )
                if self.path.startswith("/reject"):
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b"NEVER-ECHO-PROVIDER-SECRET")
                    return
                if self.path.startswith("/redirect"):
                    self.send_response(302)
                    self.send_header("Location", "https://example.invalid/secret")
                    self.end_headers()
                    return
                content = json.dumps(
                    {
                        "data": [
                            {"id": "one", "name": "First"},
                            {"id": "two"},
                            {"id": "one"},
                        ]
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = "http://127.0.0.1:" + str(server.server_port)
            key = self.service.vault.save(
                {"name": "Endpoint", "secret": "local-test-secret"}
            )
            args = {
                "mode": "local",
                "base_url": base + "/v1",
                "credential_id": key["id"],
            }
            found = provider_checks.endpoint_models(self.service, args)
            self.assertEqual(len(found["models"]), 2)
            self.assertTrue(found["credential_sent"])
            self.assertFalse(found["inference_performed"])
            self.assertEqual(observed[0]["auth"], "Bearer local-test-secret")
            provider_checks.endpoint_models(
                self.service, args | {"mode": "anthropic", "base_url": base}
            )
            self.assertEqual(observed[1]["path"], "/v1/models")
            self.assertEqual(observed[1]["anthropic"], "local-test-secret")
            for path in ("/reject", "/redirect"):
                with self.assertRaises(ValueError) as caught:
                    provider_checks.endpoint_models(
                        self.service, args | {"base_url": base + path}
                    )
                self.assertNotIn("NEVER-ECHO", str(caught.exception))
            profile = self.profile(base_url=base + "/v1", credential_id=key["id"])
            checked = provider_checks.check_profile(self.service, profile["id"])
            self.assertEqual(checked["status"], "model_listed")
            self.assertNotIn("local-test-secret", json.dumps(checked))
            self.assertEqual(
                self.service.store.get("providers", profile["id"])["last_check"],
                checked,
            )
            missing = self.profile(model="not-available", base_url=base + "/v1")
            self.assertEqual(
                provider_checks.check_profile(self.service, missing["id"])["status"],
                "model_not_listed",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_bridge_health_does_not_claim_missing_server_is_ready(self):
        with patch.dict("os.environ", {"DARKMOON_OPENCODE_URL": ""}):
            self.assertEqual(
                provider_checks.bridge_health()["status"], "not_configured"
            )
        with (
            patch.dict(
                "os.environ", {"DARKMOON_OPENCODE_URL": "http://127.0.0.1:4096"}
            ),
            patch.object(
                opencode, "native", return_value={"healthy": True, "version": "1.2.3"}
            ),
        ):
            self.assertTrue(provider_checks.bridge_health()["healthy"])
        with (
            patch.dict(
                "os.environ", {"DARKMOON_OPENCODE_URL": "http://127.0.0.1:4096"}
            ),
            patch.object(opencode, "native", side_effect=ValueError("Unavailable")),
        ):
            self.assertFalse(provider_checks.bridge_health()["healthy"])

    def test_apply_does_not_claim_live_success_when_server_readback_is_stale(self):
        profile = self.profile()

        def native(method, path, body=None):
            return (
                {"model": "old/model", "small_model": "old/model"}
                if method == "GET"
                else {"model": "local-test/one"}
            )

        with (
            patch.dict(
                "os.environ", {"DARKMOON_OPENCODE_URL": "http://127.0.0.1:4096"}
            ),
            patch.object(opencode, "native", side_effect=native),
        ):
            result = configuration.apply(self.service, profile["id"])
        self.assertTrue(result["restart_required"])
        self.assertIn("readback", result["warning"])


class ManagementAPITests(fixtures.Fixture):
    request = fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        from community.server import HTTPServer, handler_for

        self.server = HTTPServer(
            ("127.0.0.1", 0), handler_for(self.service, {"127.0.0.1"})
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def test_http_profile_lifecycle(self):
        raw = {
            "name": "HTTP profile",
            "provider": "local-test",
            "mode": "local",
            "model": "one",
            "base_url": "http://127.0.0.1:8081/v1",
        }
        code, body, _ = self.request("/api/v1/system/providers", "POST", raw)
        self.assertEqual(code, 201)
        pid = json.loads(body)["data"]["id"]
        code, body, _ = self.request(
            "/api/v1/system/providers/" + pid, "PATCH", {"name": "Edited HTTP profile"}
        )
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["data"]["name"], "Edited HTTP profile")
        self.assertEqual(self.request("/api/v1/system/providers/" + pid)[0], 200)
        self.assertEqual(
            self.request("/api/v1/system/providers/" + pid, "DELETE")[0], 200
        )
        self.assertEqual(self.request("/api/v1/system/providers/" + pid)[0], 404)

    def test_non_admin_cannot_probe_edit_or_delete_providers(self):
        self.service.accounts.create("reader", "a-long-reader-password", "viewer")
        token = self.service.accounts.login("reader", "a-long-reader-password", "test")[
            "token"
        ]
        headers = {"Authorization": "Bearer " + token}
        for method, path in [
            ("GET", "/api/v1/system/opencode-health"),
            ("POST", "/api/v1/system/provider-models"),
            ("PATCH", "/api/v1/system/providers/not-found"),
            ("DELETE", "/api/v1/system/providers/not-found"),
            ("POST", "/api/v1/system/providers/not-found/check"),
        ]:
            self.assertEqual(self.request(path, method, {}, headers=headers)[0], 403)
