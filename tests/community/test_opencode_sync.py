"""Shared configuration, native API contracts and permission regressions."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch
import test_community as fixtures
import test_pro_features as pro_tests
from community import opencode, configuration


class SharedStateTests(fixtures.Fixture):
    def seed(self):
        config, auth, env = opencode.paths(self.service)
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(
            json.dumps(
                {
                    "model": "openai/model-one",
                    "mcp": {"darkmoon": {"enabled": True}},
                    "provider": {
                        "openai": {"models": {"model-one": {"name": "Model one"}}},
                        "another": {"models": {"unchanged": {}}},
                    },
                }
            )
        )
        auth.write_text(
            json.dumps(
                {
                    "openai": {
                        "type": "oauth",
                        "access": "ACCESS-SECRET",
                        "refresh": "REFRESH-SECRET",
                        "expires": 9999999999999,
                    },
                    "another": {"type": "api", "key": "OTHER-SECRET"},
                }
            )
        )
        env.write_text(
            "# Preserve this comment\nDARKMOON_MCP_PORT=9999\nOPENCODE_LOCAL_MODE=true\nOPENCODE_LOCAL_PROVIDER_ID=old\nOPENCODE_LOCAL_BASE_URL=http://old/v1\nOPENCODE_LOCAL_MODEL=old\n"
        )
        return config, auth, env

    def test_catalog_lists_actual_models_and_login_types_without_secrets(self):
        self.seed()
        result = opencode.catalog(self.service)
        p = next(p for p in result["providers"] if p["id"] == "openai")
        self.assertTrue(p["connected"])
        self.assertEqual(p["auth_type"], "oauth")
        self.assertIn("model-one", [m["id"] for m in p["models"]])
        for secret in ("ACCESS-SECRET", "REFRESH-SECRET", "OTHER-SECRET"):
            self.assertNotIn(secret, json.dumps(result))

    def test_sync_imports_keys_once_without_copying_oauth(self):
        self.seed()
        first = opencode.sync(self.service)
        second = opencode.sync(self.service)
        self.assertEqual(first["imported"], second["imported"])
        self.assertEqual(first["imported"], ["opencode_another"])
        self.assertNotIn("OTHER-SECRET", self.service.store.path.read_text())
        self.assertNotIn("REFRESH-SECRET", self.service.store.path.read_text())
        self.assertEqual(self.service.vault.resolve("opencode_another"), "OTHER-SECRET")

    def test_apply_uses_saved_oauth_and_preserves_other_state(self):
        config, auth, env = self.seed()
        p = configuration.profile(
            self.service,
            {"provider": "openai", "mode": "cloud", "model": "openai/model-one"},
        )
        result = configuration.apply(self.service, p["id"])
        self.assertTrue(result["restart_required"])
        self.assertEqual(json.loads(config.read_text())["model"], "openai/model-one")
        self.assertIn("another", json.loads(config.read_text())["provider"])
        self.assertTrue(json.loads(config.read_text())["mcp"]["darkmoon"]["enabled"])
        self.assertEqual(
            json.loads(auth.read_text())["openai"]["refresh"], "REFRESH-SECRET"
        )
        self.assertIn("# Preserve this comment", env.read_text())
        self.assertIn("DARKMOON_MCP_PORT=9999", env.read_text())
        self.assertNotIn("OPENCODE_LOCAL_MODE=", env.read_text())
        self.assertIn("OPENCODE_USE_SAVED_AUTH=true", env.read_text())
        for path in (config, auth, env):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_connect_and_disconnect_only_touch_selected_provider(self):
        _, auth, env = self.seed()
        key = self.service.vault.save(
            {"name": "New", "provider": "new", "secret": "NEW-KEY"}
        )
        opencode.connect(self.service, {"provider": "new", "credential_id": key["id"]})
        self.assertEqual(json.loads(auth.read_text())["new"]["key"], "NEW-KEY")
        opencode.disconnect(self.service, {"provider": "new"})
        self.assertNotIn("new", json.loads(auth.read_text()))
        self.assertIn("another", json.loads(auth.read_text()))
        self.assertEqual(
            json.loads(auth.read_text())["openai"]["refresh"], "REFRESH-SECRET"
        )

    def test_bad_json_fails_without_destroying_login_file(self):
        config, auth, _ = self.seed()
        auth.write_text("{invalid")
        key = self.service.vault.save({"name": "Key", "secret": "safe-test-key"})
        with self.assertRaises(ValueError):
            opencode.connect(
                self.service, {"provider": "new", "credential_id": key["id"]}
            )
        self.assertEqual(auth.read_text(), "{invalid")

    def test_unsafe_env_value_does_not_partially_apply(self):
        config, auth, env = self.seed()
        before = [p.read_bytes() for p in (config, auth, env)]
        key = self.service.vault.save({"name": "Bad key", "secret": "bad$key"})
        profile = configuration.profile(
            self.service,
            {
                "provider": "openai",
                "mode": "cloud",
                "model": "model",
                "credential_id": key["id"],
            },
        )
        with self.assertRaises(ValueError):
            configuration.apply(self.service, profile["id"])
        self.assertEqual(before, [p.read_bytes() for p in (config, auth, env)])

    def test_installer_environment_rejects_shell_metacharacters(self):
        _, _, env = self.seed()
        before = env.read_bytes()
        for value in (
            "key;command",
            "key&command",
            "key|command",
            "key>file",
            "key<file",
            "key(command)",
            "~root",
        ):
            with self.assertRaises(ValueError):
                opencode.write_environment(env, {"OPENROUTER_API_KEY": value})
            self.assertEqual(env.read_bytes(), before)

    def test_native_catalog_oauth_and_live_apply_contract(self):
        self.seed()
        calls = []
        native_config = {}

        def native(method, path, body=None):
            calls.append((method, path, body))
            if path in {"/config", "/global/config"}:
                if method == "PATCH":
                    native_config.update(body)
                return dict(native_config)
            if path == "/provider":
                return {
                    "all": [
                        {
                            "id": "openai",
                            "name": "OpenAI",
                            "models": {"native-only": {"name": "Native model"}},
                        }
                    ],
                    "connected": ["openai"],
                }
            if path == "/provider/auth":
                return {"openai": [{"type": "oauth", "label": "Native sign-in"}]}
            if path.endswith("/authorize"):
                return {
                    "url": "https://provider.example/authorize",
                    "instructions": "Continue",
                    "method": "auto",
                }
            return True

        with (
            patch.dict(os.environ, {"DARKMOON_OPENCODE_URL": "http://127.0.0.1:4096"}),
            patch.object(opencode, "native", side_effect=native),
        ):
            catalog = opencode.catalog(self.service)
            self.assertTrue(catalog["live"])
            self.assertEqual(
                next(p for p in catalog["providers"] if p["id"] == "openai")["models"][
                    0
                ]["id"],
                "native-only",
            )
            self.assertTrue(
                opencode.oauth(self.service, {"provider": "openai", "method": 0})[
                    "url"
                ].startswith("https://")
            )
            self.assertTrue(
                opencode.oauth(
                    self.service, {"provider": "openai", "method": 0}, finish=True
                )["connected"]
            )
            with self.assertRaises(ValueError):
                opencode.oauth(self.service, {"provider": "openai", "method": 99})
            profile = configuration.profile(
                self.service,
                {"provider": "openai", "model": "native-only", "mode": "cloud"},
            )
            self.assertFalse(
                configuration.apply(self.service, profile["id"])["restart_required"]
            )
        self.assertIn(
            (
                "PATCH",
                "/global/config",
                {"model": "openai/native-only", "small_model": "openai/native-only"},
            ),
            calls,
        )

    def test_native_failure_is_honest_and_preserves_saved_state(self):
        config, _, _ = self.seed()
        profile = configuration.profile(
            self.service, {"provider": "openai", "model": "model-one", "mode": "cloud"}
        )
        with (
            patch.dict(os.environ, {"DARKMOON_OPENCODE_URL": "http://127.0.0.1:4096"}),
            patch.object(
                opencode, "native", side_effect=ValueError("Server unavailable")
            ),
        ):
            result = configuration.apply(self.service, profile["id"])
        self.assertTrue(result["restart_required"])
        self.assertIn("unavailable", result["warning"])
        self.assertEqual(json.loads(config.read_text())["model"], "openai/model-one")

    def test_runtime_boot_preserves_oauth_across_cloud_and_fallback(self):
        _, auth, _ = self.seed()
        root = Path(__file__).resolve().parents[2]
        env = {k: v for k, v in os.environ.items() if k not in opencode.MANAGED}
        env.update(
            OPENCODE_CONFIG_DIR=str(self.root / "generated"),
            OPENCODE_AUTH_DIR=str(auth.parent),
            DARKMOON_SKIP_TUI_BOOTSTRAP="1",
            OPENROUTER_PROVIDER="new",
            OPENROUTER_API_KEY="FRESH-KEY",
            OPENCODE_MODEL="model",
        )
        subprocess.run(
            ["bash", str(root / "conf/apply-settings.sh")],
            env=env,
            check=True,
            capture_output=True,
        )
        self.assertEqual(
            json.loads(auth.read_text())["openai"]["refresh"], "REFRESH-SECRET"
        )
        self.assertEqual(json.loads(auth.read_text())["new"]["key"], "FRESH-KEY")
        env.pop("OPENROUTER_API_KEY")
        env["OPENROUTER_PROVIDER"] = "openai"
        env["OPENCODE_USE_SAVED_AUTH"] = "true"
        subprocess.run(
            ["bash", str(root / "conf/apply-settings.sh")],
            env=env,
            check=True,
            capture_output=True,
        )
        self.assertEqual(
            json.loads((self.root / "generated/opencode.json").read_text())["model"],
            "openai/model",
        )
        env.pop("OPENCODE_USE_SAVED_AUTH")
        env.pop("OPENROUTER_PROVIDER")
        env.pop("OPENCODE_MODEL")
        subprocess.run(
            ["bash", str(root / "conf/apply-settings.sh")],
            env=env,
            check=True,
            capture_output=True,
        )
        self.assertIn("openai", json.loads(auth.read_text()))

    def test_refresh_rotated_api_key_also_updates_selected_installer_env(self):
        _, auth, env = self.seed()
        env.write_text(
            "OPENROUTER_PROVIDER=another\nOPENCODE_MODEL=some-model\nOPENROUTER_API_KEY=OLD-KEY\n"
        )
        key = self.service.vault.save({"name": "Rotated", "secret": "ROTATED-KEY"})
        opencode.connect(
            self.service, {"provider": "another", "credential_id": key["id"]}
        )
        self.assertIn("OPENROUTER_API_KEY=ROTATED-KEY", env.read_text())
        self.assertEqual(json.loads(auth.read_text())["another"]["key"], "ROTATED-KEY")
        opencode.disconnect(self.service, {"provider": "another"})
        self.assertNotIn("OPENROUTER_API_KEY=", env.read_text())
        self.assertIn("openai", json.loads(auth.read_text()))

    def test_oauth_finish_removes_stale_api_key_before_next_boot(self):
        _, _, env = self.seed()
        env.write_text(
            "OPENROUTER_PROVIDER=openai\nOPENCODE_MODEL=model-one\nOPENROUTER_API_KEY=STALE-KEY\n"
        )

        def native(method, path, body=None):
            if path == "/provider":
                return {
                    "all": [{"id": "openai", "models": {}}],
                    "connected": ["openai"],
                }
            if path == "/provider/auth":
                return {"openai": [{"type": "oauth", "label": "Sign in"}]}
            return True

        with (
            patch.dict(os.environ, {"DARKMOON_OPENCODE_URL": "http://127.0.0.1:4096"}),
            patch.object(opencode, "native", side_effect=native),
        ):
            opencode.oauth(
                self.service, {"provider": "openai", "method": 0}, finish=True
            )
        self.assertNotIn("STALE-KEY", env.read_text())
        self.assertIn("OPENCODE_USE_SAVED_AUTH=true", env.read_text())

    def test_native_default_model_overrides_stale_installer_selection(self):
        self.seed()

        def native(method, path, body=None):
            return (
                {"all": [], "connected": []}
                if path == "/provider"
                else {"model": "openai/changed-in-opencode"}
                if path == "/config"
                else {}
            )

        with (
            patch.dict(os.environ, {"DARKMOON_OPENCODE_URL": "http://127.0.0.1:4096"}),
            patch.object(opencode, "native", side_effect=native),
        ):
            self.assertEqual(
                opencode.catalog(self.service)["active_model"],
                "openai/changed-in-opencode",
            )


class OptionsAPITests(fixtures.Fixture):
    request = pro_tests.APITests.request
    login = pro_tests.APITests.login

    def setUp(self):
        super().setUp()
        import threading
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

    # Inherit the fixture lifecycle, not the whole existing regression suite.
    def test_provider_endpoints_require_admin_and_options_never_return_secrets(self):
        token = self.login("viewer")
        headers = {"Authorization": "Bearer " + token}
        self.assertEqual(
            self.request("/api/v1/system/opencode", headers=headers)[0], 403
        )
        self.assertEqual(
            self.request("/api/v1/system/opencode/sync", "POST", {}, headers=headers)[
                0
            ],
            403,
        )
        result = json.loads(self.request("/api/v1/options", headers=headers)[1])
        self.assertIsNone(result["opencode"])
        self.assertEqual(result["credentials"], [])
