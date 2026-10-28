"""Offline credential discovery contract, authorization and consumer verification.

No vendor calls, external Git network requests, Docker execution or publishing.
Run: PYTHONPATH=mcp python -m unittest discover -s tests/community -p 'test_credential_discovery.py' -v
"""
import http.client
import json
import subprocess
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from community.credential_catalog import CAPABILITIES
from community.credential_launch import prepare
from community.configuration import apply, profile
from community.provider_checks import endpoint_models
from community.server import HTTPServer, handler_for
from community.source_checkout import checkout
from test_community import Fixture


class CredentialDiscoveryTests(Fixture):
    SECRET = "OFFLINE-TEST-CREDENTIAL-SHOULD-NEVER-BE-RETURNED"
    PUBLIC_FIELDS = {
        "id", "name", "provider", "username", "created_at", "hint", "set",
        "capabilities",
    }

    def setUp(self):
        super().setUp()
        self.httpd = HTTPServer(("127.0.0.1", 0), handler_for(self.service, {"127.0.0.1"}))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        super().tearDown()

    def request(self, path, method="GET", body=None, token=None):
        if token is None:
            token = self.service.token
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=5)
        try:
            conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=headers)
            res = conn.getresponse()
            status, payload = res.status, res.read()
        finally:
            conn.close()
        return status, json.loads(payload)

    def credential(self, credential_id="cred_test", username="", provider="generic"):
        return self.service.vault.save({
            "name": credential_id, "provider": provider, "username": username,
            "secret": self.SECRET,
        }, credential_id)

    def internal(self, credential_id="cred_internal"):
        saved = self.credential(credential_id, "signer", "webhook")
        raw = self.service.store.get("credentials", credential_id)
        raw.update({"internal": True, "private_extra": self.SECRET})
        self.service.store.save("credentials", raw)
        return saved["id"]

    def role_token(self, role):
        username = "credential_" + role
        self.service.accounts.create(username, "fixture-password-12-chars!", role)
        return self.service.accounts.issue(self.service.store.get("users", username))["access_token"]

    def assert_masked(self, body):
        serialized = json.dumps(body)
        self.assertNotIn(self.SECRET, serialized)
        self.assertNotIn("sealed", serialized)
        self.assertNotIn("private_extra", serialized)
        for item in body.get("data", []):
            self.assertEqual(set(item), self.PUBLIC_FIELDS)
            self.assertEqual(item["hint"], "********")
        self.assertEqual(body.get("total"), len(body.get("data", [])))

    def test_provider_catalog_is_fork_native_and_route_precedes_identifier(self):
        status, catalog = self.request("/api/v1/credentials/providers")
        self.assertEqual(status, 200)
        self.assertEqual(catalog["total"], 5)
        self.assertEqual([row["id"] for row in catalog["data"]],
                         ["generic", "target-login", "target-token", "scm", "api-key"])
        self.assertEqual({row["id"] for row in catalog["capabilities"]}, set(CAPABILITIES))
        self.assertNotIn("aws", [row["id"] for row in catalog["data"]])
        self.credential("providers")
        self.assertEqual(self.request("/api/v1/credentials/providers")[1], catalog)

    def test_create_detail_list_and_update_return_only_explicit_public_fields(self):
        status, result = self.request("/api/v1/credentials", "POST", {
            "name": "Legacy label", "provider": "gitlab", "username": "robot",
            "secret": self.SECRET, "extra": self.SECRET,
        })
        self.assertEqual(status, 201)
        cid = result["data"]["id"]
        raw = self.service.store.get("credentials", cid)
        self.assertNotEqual(raw["sealed"], self.SECRET)
        self.assertEqual(self.service.vault.resolve(cid), self.SECRET)
        raw["private_extra"] = self.SECRET
        raw["hint"] = self.SECRET
        self.service.store.save("credentials", raw)
        for path in ("/api/v1/credentials", "/api/v1/credentials/" + cid):
            status, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertNotIn(self.SECRET, json.dumps(body))
            item = body["data"][0] if isinstance(body["data"], list) else body["data"]
            self.assertEqual(set(item), self.PUBLIC_FIELDS)
            self.assertEqual(item["hint"], "********")
            self.assertEqual(item["provider"], "gitlab")
            self.assertEqual(item["username"], "robot")
        status, result = self.request("/api/v1/credentials/" + cid, "PATCH", {
            "name": "updated", "provider": "custom", "secret": "new-secret-opaque",
        })
        self.assertEqual(status, 200)
        self.assertEqual(self.service.vault.resolve(cid), "new-secret-opaque")
        self.assertEqual(result["data"]["id"], cid)
        self.assertEqual(set(result["data"]), self.PUBLIC_FIELDS)

    def test_capability_filters_are_stable_and_not_provider_label_based(self):
        self.credential("cred_z", "tester", "aws")
        self.credential("cred_a", "", "completely-custom")
        for capability in CAPABILITIES:
            status, result = self.request("/api/v1/credentials?capability=" + capability)
            self.assertEqual(status, 200)
            expected = ["cred_z"] if capability == "assessment_login" else ["cred_a", "cred_z"]
            self.assertEqual([item["id"] for item in result["data"]], expected)
            self.assert_masked(result)
        self.assertEqual([item["id"] for item in self.request("/api/v1/credentials")[1]["data"]],
                         ["cred_a", "cred_z"])
        detail = self.request("/api/v1/credentials/cred_a")[1]["data"]
        self.assertNotIn("assessment_login", detail["capabilities"])
        self.assertIn("provider_api_key", detail["capabilities"])
        self.assertEqual(detail["provider"], "completely-custom")

    def test_unsupported_blank_and_duplicate_capabilities_are_400(self):
        self.credential()
        for query in ("capability=", "capability=unknown", "capability=ASSESSMENT_TOKEN",
                      "capability=assessment_token&capability=assessment_login",
                      "capability=&capability=assessment_token"):
            with self.subTest(query=query):
                status, body = self.request("/api/v1/credentials?" + query)
                self.assertEqual(status, 400)
                self.assertNotIn(self.SECRET, json.dumps(body))
        self.assertEqual(self.request("/api/v1/credentials?capability=source_checkout")[0], 200)

    def test_internal_webhook_and_extension_metadata_never_visible_or_selectable(self):
        self.credential("cred_visible", "", "generic")
        hidden = self.internal()
        raw = self.service.store.get("credentials", "cred_visible")
        raw["private_extra"] = self.SECRET
        raw["internal_webhook_key"] = self.SECRET
        self.service.store.save("credentials", raw)
        for path in ("/api/v1/credentials", "/api/v1/credentials?capability=provider_api_key"):
            status, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertEqual([r["id"] for r in body["data"]], ["cred_visible"])
            self.assert_masked(body)
        for method in ("GET", "PATCH", "DELETE"):
            body = {"secret": "replacement"} if method == "PATCH" else None
            status, response = self.request("/api/v1/credentials/" + hidden, method, body)
            self.assertEqual(status, 404)
            self.assertNotIn(self.SECRET, json.dumps(response))
        self.assertIsNotNone(self.service.store.get("credentials", hidden))
        with self.assertRaises(KeyError):
            self.service.vault.require(hidden, "provider_api_key")

    def test_missing_sealed_legacy_record_is_masked_and_unusable(self):
        self.service.store.save("credentials", {
            "id": "cred_legacy", "name": "old", "provider": "legacy",
            "username": "tester", "private_extra": self.SECRET,
        })
        status, detail = self.request("/api/v1/credentials/cred_legacy")
        self.assertEqual(status, 200)
        self.assertEqual(set(detail["data"]), self.PUBLIC_FIELDS)
        self.assertFalse(detail["data"]["set"])
        self.assertEqual(detail["data"]["capabilities"], [])
        self.assertNotIn(self.SECRET, json.dumps(detail))
        self.assertEqual(self.request("/api/v1/credentials?capability=assessment_login")[1]["total"], 0)
        with self.assertRaises(KeyError):
            self.service.vault.require("cred_legacy", "source_checkout")

    def test_authentication_admin_only_routes_and_analyst_options(self):
        cid = self.credential("cred_visible", "tester")["id"]
        urls = ["/api/v1/credentials", "/api/v1/credentials/providers",
                "/api/v1/credentials/" + cid,
                "/api/v1/credentials?capability=assessment_login"]
        for path in urls:
            self.assertEqual(self.request(path, token="")[0], 401)
        analyst, viewer = self.role_token("analyst"), self.role_token("viewer")
        for token in (analyst, viewer):
            for path in urls:
                self.assertEqual(self.request(path, token=token)[0], 403)
            self.assertEqual(self.request("/api/v1/credentials", "POST", {
                "secret": self.SECRET,
            }, token=token)[0], 403)
            self.assertEqual(self.request("/api/v1/credentials/" + cid, "DELETE", token=token)[0], 403)
        for token, expected in ((analyst, True), (viewer, False)):
            status, choices = self.request("/api/v1/options", token=token)
            self.assertEqual(status, 200)
            self.assertEqual(bool(choices["credentials"]), expected)
            self.assertEqual(bool(choices["credential_choices"]), expected)
            self.assertNotIn(self.SECRET, json.dumps(choices))
            if expected:
                self.assertEqual(set(choices["credential_choices"]), set(CAPABILITIES))
                self.assertEqual(choices["credential_choices"]["assessment_login"][0]["id"], cid)

    def test_logout_revokes_credential_detail_session(self):
        self.credential("cred_visible")
        token = self.role_token("admin")
        self.assertEqual(self.request("/api/v1/credentials/cred_visible", token=token)[0], 200)
        self.assertEqual(self.request("/api/v1/auth/logout", "POST", {}, token=token)[0], 200)
        self.assertEqual(self.request("/api/v1/credentials/cred_visible", token=token)[0], 401)
        self.assertEqual(self.request("/api/v1/credentials/cred_visible", token="")[0], 401)

    def test_missing_invalid_and_internal_ids_do_not_disclose_secret(self):
        self.internal()
        for path in ("/api/v1/credentials/missing", "/api/v1/credentials/cred_internal",
                     "/api/v1/credentials/%2e%2e%2fprivate"):
            status, response = self.request(path)
            self.assertIn(status, (400, 404))
            self.assertNotIn(self.SECRET, json.dumps(response))

    def test_selectors_only_include_valid_capability_options(self):
        self.credential("cred_login", "alice", "target-login")
        self.credential("cred_token", "", "github")
        self.internal()
        status, options = self.request("/api/v1/options")
        self.assertEqual(status, 200)
        self.assertEqual([x["id"] for x in options["credential_choices"]["assessment_login"]],
                         ["cred_login"])
        for cap in ("assessment_token", "source_checkout", "provider_api_key"):
            self.assertEqual([x["id"] for x in options["credential_choices"][cap]],
                             ["cred_login", "cred_token"])
        self.assertEqual([x["id"] for x in options["credentials"]], ["cred_login", "cred_token"])
        self.assertNotIn(self.SECRET, json.dumps(options))

    def test_launch_rejects_missing_username_and_hidden_keys_before_queueing(self):
        self.credential("cred_token", "")
        self.internal()
        for key, reference in (("assessment_credential_id", "cred_token"),
                               ("assessment_token_id", "cred_internal"),
                               ("credential_id", "cred_internal")):
            with self.subTest(key=key), self.assertRaises(ValueError) as error:
                self.service.launch({"target": "example.invalid", key: reference})
            self.assertNotIn(self.SECRET, str(error.exception))
            self.assertEqual(self.service.store.items("jobs"), [])

    def test_valid_saved_references_launch_without_executing_worker(self):
        self.credential("cred_login", "alice")
        self.credential("cred_token", "")
        job = self.service.launch({
            "target": "example.invalid", "assessment_credential_id": "cred_login",
            "assessment_token_id": "cred_token", "credential_id": "cred_token",
        })
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["spec"]["assessment_credential_id"], "cred_login")
        self.assertEqual(job["spec"]["assessment_token_id"], "cred_token")
        self.assertEqual(job["spec"]["credential_id"], "cred_token")

    def test_privacy_tokenization_uses_pipe_and_never_passes_plaintext_as_argv(self):
        self.credential("cred_login", "alice")
        self.credential("cred_token", "")
        calls = []

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            if argv[:3] == ["docker", "compose", "version"]:
                return subprocess.CompletedProcess(argv, 0)
            return subprocess.CompletedProcess(argv, 0, '{"tokenized":"CREDS=CRED_1 TOKEN=CRED_2"}')

        output = prepare(self.root, self.service.store, "Target: example.invalid", {
            "assessment_credential_id": "cred_login", "assessment_token_id": "cred_token",
        }, run=fake_run)
        self.assertEqual(output, "CREDS=CRED_1 TOKEN=CRED_2")
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(self.SECRET not in " ".join(argv) for argv, _ in calls))
        payload = json.loads(calls[1][1]["input"])["text"]
        self.assertIn("CREDS=alice:" + self.SECRET, payload)
        self.assertIn("TOKEN=" + self.SECRET, payload)
        self.assertNotIn(self.SECRET, output)

    def test_privacy_tokenization_rejects_unmasked_reply_and_internal_reference(self):
        self.credential("cred_login", "alice")
        hidden = self.internal()

        def bad_run(argv, **kwargs):
            if argv[:3] == ["docker", "compose", "version"]:
                return subprocess.CompletedProcess(argv, 0)
            return subprocess.CompletedProcess(argv, 0,
                json.dumps({"tokenized": "CREDS=alice:" + self.SECRET}))
        with self.assertRaises(ValueError):
            prepare(self.root, self.service.store, "scope", {
                "assessment_credential_id": "cred_login",
            }, run=bad_run)
        with patch("community.credential_launch.subprocess.run") as forbidden:
            with self.assertRaises(ValueError):
                prepare(self.root, self.service.store, "scope", {
                    "assessment_token_id": hidden,
                })
            forbidden.assert_not_called()

    def test_https_checkout_uses_injected_askpass_only_without_real_git(self):
        self.credential("cred_source", "", "github")
        calls = []

        def fake_git(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0)

        result = checkout(self.service, "https://example.invalid/org/repo.git",
                          "campaign_fixture", "cred_source", run=fake_git)
        self.assertTrue(str(result).endswith("checkouts/campaign_fixture"))
        self.assertEqual(len(calls), 1)
        argv, kwargs = calls[0]
        self.assertEqual(argv[0], "git")
        self.assertIn("--no-recurse-submodules", argv)
        self.assertNotIn(self.SECRET, " ".join(argv))
        self.assertEqual(kwargs["env"]["DM_CHECKOUT_SECRET"], self.SECRET)
        self.assertEqual(kwargs["env"]["DM_CHECKOUT_USER"], "x-access-token")
        self.assertEqual(kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")

    def test_checkout_refuses_internal_key_before_invoking_git(self):
        hidden = self.internal()
        runner = Mock()
        with self.assertRaises(ValueError) as error:
            checkout(self.service, "https://example.invalid/owned.git",
                     "campaign_fixture", hidden, run=runner)
        runner.assert_not_called()
        self.assertNotIn(self.SECRET, str(error.exception))

    def test_provider_profile_and_model_discovery_reject_internal_keys(self):
        self.credential("cred_provider", "", "api-key")
        hidden = self.internal()
        spec = {"mode": "local", "provider": "fixture-provider",
                "model": "fixture-model", "base_url": "http://127.0.0.1:9000/v1"}
        created = profile(self.service, {**spec, "credential_id": "cred_provider"})
        self.assertEqual(created["credential_id"], "cred_provider")
        with self.assertRaises(ValueError):
            profile(self.service, {**spec, "credential_id": hidden})
        with patch("urllib.request.build_opener") as network:
            with self.assertRaises(ValueError):
                endpoint_models(self.service, {**spec, "credential_id": hidden})
            network.assert_not_called()

    def test_existing_provider_profile_fails_closed_when_key_becomes_internal(self):
        self.credential("cred_provider")
        config = {"mode": "local", "provider": "fixture-provider",
                  "model": "fixture-model", "base_url": "http://127.0.0.1:9000/v1",
                  "credential_id": "cred_provider"}
        saved = profile(self.service, config)
        stored = self.service.store.get("credentials", "cred_provider")
        stored["internal"] = True
        self.service.store.save("credentials", stored)
        with patch("community.opencode.paths") as no_native:
            with self.assertRaises(ValueError):
                apply(self.service, saved["id"])
            no_native.assert_not_called()

    def test_opencode_connection_rejects_internal_key_before_native_interaction(self):
        self.internal()
        from community.opencode import connect
        with patch("community.opencode.paths") as no_native:
            with self.assertRaises(ValueError):
                connect(self.service, {"provider": "fixture-provider", "credential_id": "cred_internal"})
            no_native.assert_not_called()

    def test_credential_id_delete_preserves_other_records_and_vault_encryption(self):
        self.credential("cred_a", "a")
        self.credential("cred_b", "b")
        status, result = self.request("/api/v1/credentials/cred_a", "DELETE")
        self.assertEqual(status, 200)
        self.assertEqual(result, {"deleted": "cred_a"})
        self.assertEqual(self.request("/api/v1/credentials/cred_a")[0], 404)
        self.assertEqual(self.service.vault.resolve("cred_b"), self.SECRET)
