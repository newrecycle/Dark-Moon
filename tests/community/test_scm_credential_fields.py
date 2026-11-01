"""SCM field contracts, atomic mutations and existing ownership boundaries."""
import json
import subprocess
import threading

import test_community as fixtures
from community.auth import CredentialVault
from community.server import HTTPServer, handler_for
from community.source_checkout import checkout


SECRET = "SCM-TEST-SECRET-THAT-MUST-STAY-ENCRYPTED"


class SCMCredentialFieldsTests(fixtures.Fixture):
    request = fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(self.service, {"127.0.0.1"}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        for name, role in (("owner", "admin"), ("other", "analyst"), ("reader", "viewer")):
            self.service.accounts.create(name, "a-long-scm-fixture-password", role)
        self.headers = {"Authorization": "Bearer " + self.service.accounts.issue(self.service.store.get("users", "owner"))["token"]}
        self.actor = self.service.identity(self.headers["Authorization"])

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def save(self, provider="gitea", **extra):
        fields = {"endpoint_url": "https://scm.example.invalid/api", "token": SECRET}
        if provider in {"github", "gitea", "gogs", "bitbucket", "generic_git"}:
            fields["username"] = "checkout-user"
        if provider == "azure_devops":
            fields["project"] = "owned-project"
        status, body, _ = self.request("/api/v1/credentials", "POST", {
            "provider": provider, "name": "Owned SCM test", "fields": fields, **extra}, headers=self.headers)
        self.assertEqual(status, 201, body)
        return json.loads(body)["data"]

    def test_all_seven_field_forms_have_only_checkout_capability_and_private_ownership(self):
        for provider in ("github", "gitlab", "gitea", "gogs", "bitbucket", "azure_devops", "generic_git"):
            with self.subTest(provider=provider):
                row = self.save(provider)
                self.assertEqual((row["adapter"], row["scope"], row["owner_id"]), ("scm_token", "private", "owner"))
                self.assertEqual(row["capabilities"], ["source_checkout"])
                self.assertEqual(row["endpoint_url"], "https://scm.example.invalid/api")
                self.assertEqual(row["fields"]["token"], "********")
                self.assertEqual(self.service.vault.resolve(row["id"]), SECRET)
                self.assertNotIn(SECRET, json.dumps(self.service.store.read()))
                self.assertNotIn(SECRET, json.dumps(row))
                self.assertEqual(CredentialVault(self.service.store).get(row["id"]), row)
                self.service.vault.require(row["id"], "source_checkout", actor=self.actor)
                for capability in ("assessment_login", "assessment_token", "provider_api_key"):
                    with self.assertRaises(KeyError):
                        self.service.vault.require(row["id"], capability, actor=self.actor)
                other = self.service.accounts.public(self.service.store.get("users", "other"))
                with self.assertRaises(KeyError):
                    self.service.vault.require(row["id"], "source_checkout", actor=other)

    def test_rename_metadata_and_token_rotation_preserve_each_other_and_policy(self):
        row = self.save("azure_devops", scope="shared", grants=["other"])
        path = "/api/v1/credentials/" + row["id"]
        sealed = self.service.store.get("credentials", row["id"])["sealed"]
        for change in ({"name": "Renamed"}, {"fields": {"project": "new-project"}},
                       {"fields": {"endpoint_url": "https://second.example.invalid/api"}}):
            status, body, _ = self.request(path, "PUT", change, headers=self.headers)
            self.assertEqual(status, 200, body)
            self.assertEqual(self.service.store.get("credentials", row["id"])["sealed"], sealed)
        status, body, _ = self.request(path, "PUT", {"fields": {"token": SECRET + "-rotated"}}, headers=self.headers)
        self.assertEqual(status, 200, body)
        after = json.loads(body)["data"]
        self.assertEqual(after["name"], "Renamed")
        self.assertEqual(after["fields"]["project"], "new-project")
        self.assertEqual(after["endpoint_url"], "https://second.example.invalid/api")
        self.assertEqual((after["scope"], after["owner_id"], after["grants"]), ("shared", "owner", ["other"]))
        self.assertEqual(self.service.vault.resolve(row["id"]), SECRET + "-rotated")
        self.service.vault.save({"revoked": True}, row["id"], actor=self.actor)
        self.service.vault.save({"fields": {"token": SECRET}}, row["id"], actor=self.actor)
        self.assertEqual(self.service.vault.get(row["id"])["capabilities"], [])
        with self.assertRaises(ValueError):
            self.service.vault.save({"revoked": False}, row["id"], actor=self.actor)

    def test_required_provider_fields_and_provider_switch_are_atomic(self):
        row = self.save("bitbucket")
        invalid = [{"username": ""}, {"fields": {"username": ""}}, {"provider": "gitlab"},
                   {"provider": "gitlab", "fields": {"token": SECRET}},
                   {"fields": {"username": "inconsistent"}, "username": "different"},
                   {"fields": {"token": SECRET}, "secret": "different"},
                   {"fields": {"project": "not-a-bitbucket-field"}},
                   {"fields": {"endpoint_url": None}}, {"fields": {"username": "bad\nuser"}},
                   {"adapter": "target_token"}]
        for change in invalid:
            before = self.service.store.read()["credentials"]
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.service.vault.save(change, row["id"], actor=self.actor)
            self.assertEqual(self.service.store.read()["credentials"], before)
        for provider in ("gitea", "gogs", "azure_devops", "bitbucket"):
            with self.subTest(provider=provider), self.assertRaises(ValueError):
                self.service.vault.save({"provider": provider, "fields": {"token": SECRET}}, actor=self.actor)

    def test_invalid_or_sensitive_endpoints_are_not_saved_or_echoed(self):
        for url in ("http://host.invalid", "https://user:password@host.invalid", "https://@host.invalid",
                    "https://host.invalid?token=" + SECRET, "https://host.invalid/#" + SECRET,
                    "https://host.invalid:99999", "https://host.invalid\\other", "https://bad host.invalid", "https://host.invalid\n"):
            with self.subTest(url=url):
                status, body, _ = self.request("/api/v1/credentials", "POST", {"provider": "gitlab", "fields": {
                    "token": SECRET, "endpoint_url": url}}, headers=self.headers)
                self.assertEqual(status, 400, body)
                self.assertNotIn(SECRET, body.decode())
        self.assertEqual(self.service.store.items("credentials"), [])

    def test_legacy_field_update_keeps_scope_ciphertext_and_identity_until_explicit_migration(self):
        row = self.service.vault.save({"provider": "github", "secret": SECRET}, "cred_legacy")
        sealed = self.service.store.get("credentials", row["id"])["sealed"]
        updated = self.service.vault.save({"fields": {"username": "git-user", "endpoint_url": "https://owned.invalid"}}, row["id"], actor=self.actor)
        self.assertNotIn("model_version", updated)
        self.assertEqual(self.service.store.get("credentials", row["id"])["sealed"], sealed)
        migrated = self.service.vault.save({"model_version": 1, "adapter": "scm_token"}, row["id"], actor=self.actor)
        self.assertEqual((migrated["scope"], migrated["owner_id"], migrated["grants"]), ("private", "owner", []))
        self.assertEqual(migrated["fields"]["username"], "git-user")

    def test_checkout_uses_field_username_without_putting_secrets_in_argv(self):
        row = self.save("gitea")
        calls = []
        def git(argv, **options):
            calls.append((argv, options))
            return subprocess.CompletedProcess(argv, 0)
        checkout(self.service, "https://scm.example.invalid/owned/repo.git", "campaign_scm", row["id"], run=git, actor=self.actor)
        self.assertEqual(len(calls), 1)
        argv, options = calls[0]
        self.assertEqual(options["env"]["DM_CHECKOUT_USER"], "checkout-user")
        self.assertEqual(options["env"]["DM_CHECKOUT_SECRET"], SECRET)
        self.assertNotIn(SECRET, " ".join(argv))
        self.assertNotIn("api", argv[-2])  # Endpoint metadata does not replace the requested repository.

    def test_fields_do_not_bypass_admin_crud_or_allow_internal_record_access(self):
        raw = {"provider": "gitlab", "fields": {"token": SECRET}}
        for user in ("other", "reader"):
            token = self.service.accounts.issue(self.service.store.get("users", user))["token"]
            self.assertEqual(self.request("/api/v1/credentials", "POST", raw,
                headers={"Authorization": "Bearer " + token})[0], 403)
        self.assertEqual(self.request("/api/v1/credentials", "POST", raw, auth=False)[0], 401)
        hidden = self.service.vault.save({"secret": SECRET}, internal=True)
        with self.assertRaises(KeyError):
            self.service.vault.save(raw, hidden["id"], actor=self.actor)
        self.assertEqual(self.service.vault.list(), [])
