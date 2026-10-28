"""Versioned credential adapter, ownership and consumer tests.

All credentials are fake; no external providers, assessments or webhooks.
Run: PYTHONPATH=mcp python -m pytest tests/community/test_credential_access.py -q
"""
import concurrent.futures
import json
import threading
from unittest.mock import patch

import test_community as fixtures
from community.auth import CredentialVault
from community.credential_policy import ADAPTERS, VERSION
from community.configuration import profile
from community.provider_checks import endpoint_models
from community.server import HTTPServer, handler_for
from community.store import Store


SECRET = "OFFLINE-PRIVATE-CREDENTIAL-NOT-FOR-OUTPUT"


class CredentialAccessTests(fixtures.Fixture):
    request = fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        for uid, role in (("alice", "analyst"), ("bob", "analyst"),
                          ("operator", "admin"), ("viewer2", "viewer")):
            self.service.accounts.create(uid, "fake-long-password-for-tests", role)
        self.actors = {}
        for uid in ("alice", "bob", "operator", "viewer2"):
            user = self.service.store.get("users", uid)
            token = self.service.accounts.issue(user)["token"]
            self.actors[uid] = self.service.identity("Bearer " + token)
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(self.service, {"127.0.0.1"}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        super().tearDown()

    def authorization(self, uid):
        return {"Authorization": "Bearer " + self.service.accounts.issue(
            self.service.store.get("users", uid))["token"]}

    def typed(self, adapter="target_token", scope="private", owner="alice", grants=None, cid=None):
        raw = {"name": "Safe test key", "provider": "fixture", "secret": SECRET,
               "adapter": adapter, "model_version": VERSION, "scope": scope, "owner_id": owner,
               "grants": grants or []}
        return self.service.vault.save(raw, cid, actor=self.actors["operator"])

    def test_catalog_has_exact_adapters_and_no_vendor_capability_claim(self):
        info = self.service.api
        from community.credential_catalog import catalog
        response = catalog()
        self.assertEqual(response["model_version"], VERSION)
        self.assertEqual({x["id"] for x in response["adapters"]}, set(ADAPTERS))
        self.assertNotIn("aws", {x["id"] for x in response["adapters"]})
        self.assertEqual(set(response["adapters"][0]), {"id", "required_fields", "capabilities"})

    def test_private_owner_choices_are_isolated_and_admin_management_is_masked(self):
        row = self.typed(cid="cred_private")
        self.assertEqual(row["capabilities"], ["assessment_token"])
        self.assertEqual(row["owner_id"], "alice")
        self.assertEqual(row["scope"], "private")
        self.assertNotIn(SECRET, json.dumps(row))
        for uid, visible in (("alice", True), ("bob", False), ("operator", False)):
            status, body, _ = self.request("/api/v1/options", headers=self.authorization(uid))
            self.assertEqual(status, 200)
            options = json.loads(body)
            ids = [r["id"] for r in options["credential_choices"]["assessment_token"]]
            self.assertEqual("cred_private" in ids, visible)
            self.assertNotIn(SECRET, body.decode())
        # Admin management reads are masked; management is not automatic use.
        status, body, _ = self.request("/api/v1/credentials/cred_private")
        self.assertEqual(status, 200)
        self.assertNotIn(SECRET, body.decode())
        self.assertEqual(json.loads(body)["data"]["adapter"], "target_token")
        for uid in ("alice", "bob", "viewer2"):
            hdr = self.authorization(uid)
            for method in ("GET", "PATCH", "DELETE"):
                self.assertEqual(self.request("/api/v1/credentials/cred_private", method,
                                              {"name": "wrong"} if method == "PATCH" else None,
                                              headers=hdr)[0], 403)

    def test_cross_user_launch_and_alternate_launch_path_denied(self):
        self.typed(cid="cred_alice")
        for path in ("/api/v1/run/campaign", "/api/v1/campaigns"):
            status, body, _ = self.request(path, "POST",
                {"target": "owned.invalid", "assessment_token_id": "cred_alice"},
                headers=self.authorization("bob"))
            self.assertEqual(status, 400, (path, body))
        self.assertEqual(self.service.store.items("jobs"), [])
        status, body, _ = self.request("/api/v1/run/campaign", "POST",
            {"target": "owned.invalid", "assessment_token_id": "cred_alice"},
            headers=self.authorization("alice"))
        self.assertEqual(status, 202, body)
        self.assertEqual(len(self.service.store.items("jobs")), 1)
        self.assertNotIn(SECRET, body.decode())
        self.assertNotIn(SECRET, json.dumps(self.service.store.items("events")))

    def test_explicit_shared_grants_revoke_and_reassign_before_queued_execution(self):
        self.typed(scope="shared", owner="alice", grants=["bob"], cid="cred_shared")
        self.service.vault.require("cred_shared", "assessment_token", actor=self.actors["bob"])
        job = self.service.launch({"target": "owned.invalid", "assessment_token_id": "cred_shared"},
                                  actor=self.actors["bob"])
        before = self.service.store.get("credentials", "cred_shared")["sealed"]
        self.service.vault.save({"owner_id": "alice", "grants": []}, "cred_shared",
                                actor=self.actors["operator"])
        self.assertEqual(self.service.store.get("credentials", "cred_shared")["sealed"], before)
        with self.assertRaises(KeyError):
            self.service.vault.require("cred_shared", "assessment_token", actor=self.actors["bob"])
        with patch("community.jobs.subprocess.Popen") as popen:
            self.service.queue.run_one(job)
            popen.assert_not_called()
        record = self.service.store.get("jobs", job["id"])
        self.assertEqual(record["status"], "failed")
        self.assertNotIn(SECRET, json.dumps(record))
        self.service.vault.save({"owner_id": "bob", "scope": "private"}, "cred_shared",
                                actor=self.actors["operator"])
        self.service.vault.require("cred_shared", "assessment_token", actor=self.actors["bob"])
        with self.assertRaises(KeyError):
            self.service.vault.require("cred_shared", "assessment_token", actor=self.actors["alice"])

    def test_delete_or_account_revocation_prevents_stale_queue_secret_use(self):
        for mechanism in ("delete", "account"):
            cid = "cred_" + mechanism
            self.typed(cid=cid)
            job = self.service.launch({"target": "owned.invalid", "assessment_token_id": cid},
                                      actor=self.actors["alice"])
            if mechanism == "delete":
                self.service.vault.delete(cid)
            else:
                self.service.store.update(lambda state: state["users"].pop("alice"))
            with patch("community.jobs.subprocess.Popen") as popen:
                self.service.queue.run_one(job)
                popen.assert_not_called()
            self.assertEqual(self.service.store.get("jobs", job["id"])["status"], "failed")
            if mechanism == "account":
                break  # The deleted actor must not be used in the next case.

    def test_irreversible_revocation_blocks_use_and_keeps_encryption(self):
        self.typed(cid="cred_revoke")
        original = self.service.store.get("credentials", "cred_revoke")["sealed"]
        updated = self.service.vault.save({"revoked": True}, "cred_revoke",
                                          actor=self.actors["operator"])
        self.assertEqual(updated["capabilities"], [])
        self.assertEqual(original, self.service.store.get("credentials", "cred_revoke")["sealed"])
        with self.assertRaises(KeyError):
            self.service.vault.require("cred_revoke", "assessment_token", actor=self.actors["alice"])
        with self.assertRaises(ValueError):
            self.service.vault.save({"revoked": False}, "cred_revoke", actor=self.actors["operator"])

    def test_legacy_record_converts_without_reencrypt_or_wildcard_grant(self):
        legacy = self.service.vault.save({"secret": SECRET, "username": "legacy"}, "cred_old")
        sealed = self.service.store.get("credentials", "cred_old")["sealed"]
        self.assertEqual(legacy["id"], "cred_old")
        self.assertNotIn("scope", legacy)
        self.service.vault.require("cred_old", "source_checkout", actor=self.actors["bob"])
        migrated = self.service.vault.save({"adapter": "username_password", "model_version": 1,
                                           "scope": "private", "owner_id": "alice"},
                                          "cred_old", actor=self.actors["operator"])
        self.assertEqual(migrated["id"], "cred_old")
        self.assertEqual(migrated["capabilities"], ["assessment_login"])
        self.assertEqual(migrated["grants"], [])
        self.assertEqual(self.service.store.get("credentials", "cred_old")["sealed"], sealed)
        with self.assertRaises(KeyError):
            self.service.vault.require("cred_old", "source_checkout", actor=self.actors["bob"])
        self.service.vault.require("cred_old", "assessment_login", actor=self.actors["alice"])
        new_vault = CredentialVault(Store(self.service.store.root))
        self.assertEqual(new_vault.resolve("cred_old"), SECRET)
        self.assertNotIn(SECRET, json.dumps(new_vault.get("cred_old")))

    def test_unknown_required_fields_and_adapter_forgery_fail(self):
        cases = [
            {"adapter": "unimplemented_cloud", "secret": SECRET},
            {"adapter": "target_token", "secret": SECRET, "forged_capabilities": ["source_checkout"]},
            {"adapter": "username_password", "secret": SECRET},
            {"adapter": "scm_token", "secret": SECRET, "model_version": 99},
            {"adapter": "provider_api_key", "secret": SECRET, "grants": ["viewer2"], "scope": "shared"},
            {"adapter": "target_token", "secret": SECRET, "scope": "service", "owner_id": "alice"},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.service.vault.save(case, actor=self.actors["operator"])
        self.assertEqual(self.service.store.items("credentials"), [])

    def test_service_scope_and_scheduler_guard(self):
        row = self.typed(adapter="target_token", scope="service", owner="workspace-owner",
                         cid="cred_svc")
        self.assertEqual(row["scope"], "service")
        self.service.vault.require("cred_svc", "assessment_token")
        for user in ("alice", "operator"):
            with self.assertRaises(KeyError):
                self.service.vault.require("cred_svc", "assessment_token", actor=self.actors[user])
        private = self.typed(cid="cred_human")
        with self.assertRaises(ValueError):
            self.service.scheduler.create({"target": "owned.invalid",
                                           "assessment_token_id": private["id"]})
        schedule = self.service.scheduler.create({"target": "owned.invalid",
                                                   "assessment_token_id": "cred_svc",
                                                   "enabled": False})
        self.assertFalse(schedule["enabled"])

    def test_internal_keys_never_exposed_or_usable(self):
        hook = self.service.operations.register({"url": "https://fixture.example.invalid/webhook",
                                                  "secret": "fake-hook-signing-secret-123456"})
        internal = self.service.store.get("webhooks", hook["id"])["credential_ref"]
        self.assertTrue(self.service.store.get("credentials", internal)["internal"])
        self.assertNotIn(internal, json.dumps(self.service.vault.list()))
        self.assertNotIn(internal, json.dumps(self.service.vault.list(actor=self.actors["alice"], for_use=True)))
        with self.assertRaises(KeyError):
            self.service.vault.require(internal, "provider_api_key")
        self.assertEqual(self.request("/api/v1/credentials/" + internal)[0], 404)
        self.assertNotIn("fake-hook-signing-secret", json.dumps(self.service.store.items("events")))

    def test_provider_adapter_restriction_and_no_network_on_ineligible_actor(self):
        self.typed(adapter="provider_api_key", cid="cred_provider")
        raw = {"mode": "local", "provider": "example", "model": "model",
               "base_url": "http://127.0.0.1:12345/v1", "credential_id": "cred_provider"}
        with patch("urllib.request.build_opener") as network:
            with self.assertRaises(ValueError):
                endpoint_models(self.service, raw, actor=self.actors["bob"])
            network.assert_not_called()
        with self.assertRaises(ValueError):
            profile(self.service, raw, actor=self.actors["bob"])
        item = profile(self.service, raw, actor=self.actors["alice"])
        self.assertEqual(item["credential_id"], "cred_provider")

    def test_retest_inherits_references_only_with_requestor_authorization(self):
        self.typed(cid="cred_retest")
        job = self.service.launch({"target": "owned.invalid", "assessment_token_id": "cred_retest"},
                                  actor=self.actors["alice"])
        before = len(self.service.store.items("jobs"))
        with self.assertRaises(ValueError):
            self.service.operations.launch_retest(
                {"campaign_id": job["campaign_id"]}, actor=self.actors["bob"])
        self.assertEqual(len(self.service.store.items("jobs")), before)

    def test_schedule_creation_does_not_turn_analyst_into_service_identity(self):
        self.typed(adapter="target_token", scope="service", owner="workspace-owner",
                   cid="cred_scheduler_service")
        spec = {"target": "owned.invalid", "assessment_token_id": "cred_scheduler_service",
                "enabled": False}
        status, body, _ = self.request("/api/v1/scheduler", "POST", spec,
                                       headers=self.authorization("alice"))
        self.assertEqual(status, 400, body)
        self.assertFalse(self.service.store.items("schedules"))
        status, body, _ = self.request("/api/v1/scheduler", "POST", spec)
        self.assertEqual(status, 201, body)
        self.assertEqual(len(self.service.store.items("schedules")), 1)

    def test_reserved_workspace_owner_username_cannot_impersonate_service(self):
        with self.assertRaises(ValueError):
            self.service.accounts.create("workspace-owner",
                                         "fake-long-password-for-tests", "admin")
        self.typed(adapter="target_token", scope="service", owner="workspace-owner",
                   cid="cred_service_only")
        forged = {"id": "workspace-owner", "role": "admin", "authentication": "password"}
        with self.assertRaises(KeyError):
            self.service.vault.require("cred_service_only", "assessment_token", actor=forged)
        self.service.vault.require("cred_service_only", "assessment_token")

    def test_job_actor_is_minimal_and_idempotency_does_not_bind_session_id(self):
        self.typed(cid="cred_session")
        job = self.service.launch({"target": "owned.invalid",
                                   "assessment_token_id": "cred_session"},
                                  key="stable_attempt", actor=self.actors["alice"])
        self.assertEqual(job["request_actor"], {"id": "alice", "authentication": "password"})
        self.assertNotIn("session_id", json.dumps(job))
        alternate = dict(self.actors["alice"], session_id="different-session")
        same = self.service.launch({"target": "owned.invalid",
                                    "assessment_token_id": "cred_session"},
                                   key="stable_attempt", actor=alternate)
        self.assertEqual(same["id"], job["id"])

    def test_secrets_are_never_present_in_control_state_exports(self):
        self.typed(adapter="scm_token", cid="cred_scm")
        for item in self.service.vault.list():
            self.assertNotIn(SECRET, json.dumps(item))
        raw = self.service.store.path.read_text()
        self.assertNotIn(SECRET, raw)
        self.assertNotIn(SECRET, json.dumps(self.service.store.items("events")))
