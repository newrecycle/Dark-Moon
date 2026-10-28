"""Offline alert admission, credentials and management transport contracts."""
import concurrent.futures
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "darkmoon/bin/darkmoon_campaign.py"
spec = importlib.util.spec_from_file_location("alert_verified", SCRIPT)
alert = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alert)
REALM = "darkmoon-" + "a" * 32


class Response(io.BytesIO):
    def __init__(self, value):
        super().__init__(value if isinstance(value, bytes) else json.dumps(value).encode())
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class AlertContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.lookups = self.home / "lookups"
        self.lookups.mkdir()
        (self.lookups / "darkmoon_targets.csv").write_text("target,allow_destructive\nowned.invalid,0\n")
        for manager in (patch.dict(os.environ, {"SPLUNK_HOME": str(self.home)}),
                        patch.object(alert, "app_dir", return_value=str(self.home)),
                        patch("socket.create_connection", side_effect=AssertionError("External network disabled"))):
            manager.start()
            self.addCleanup(manager.stop)

    def credential(self, username="darkmoon", realm=REALM, secret="PRIVATE-fixture"):
        return {"content": {"username": username, "realm": realm, "clear_password": secret}}

    def test_exact_generation_never_falls_back(self):
        rows = [self.credential(realm=""), self.credential(realm="darkmoon-" + "b" * 32), self.credential(secret="selected")]
        with patch.object(alert, "_splunk_get", return_value={"entry": rows}):
            self.assertEqual(alert.get_token("https://127.0.0.1:8089", "session", REALM), "selected")
        for entries in (rows[:2], [rows[-1], rows[-1]], [self.credential(secret="")], [self.credential(username="other")]):
            with self.subTest(entries=entries), patch.object(alert, "_splunk_get", return_value={"entry": entries}), contextlib.redirect_stderr(io.StringIO()) as log:
                self.assertEqual(alert.get_token("https://127.0.0.1:8089", "session", REALM), "")
                self.assertNotIn("PRIVATE", log.getvalue())

    def test_legacy_names_precedence_ambiguity_and_invalid_headers(self):
        cases = [([self.credential("other", "")], ""),
                 ([self.credential("token", "", "legacy")], "legacy"),
                 ([self.credential("api_token", "", "legacy")], "legacy"),
                 ([self.credential("token", ""), self.credential("api_token", "")], ""),
                 ([self.credential("darkmoon", "", "primary"), self.credential("token", "")], "primary"),
                 ([self.credential("darkmoon", "", "bad\nheader")], ""),
                 ([self.credential("darkmoon", "", " padded ")], "")]
        for entries, expected in cases:
            with self.subTest(entries=entries), patch.object(alert, "_splunk_get", return_value={"entry": entries}), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(alert.get_token("https://127.0.0.1:8089", "session"), expected)

    def test_settings_binding_is_typed_and_errors_do_not_echo(self):
        content = {"base_url": "https://owned.invalid/api/v1/", "verify_tls": "1", "credential_realm": REALM}
        with patch.object(alert, "_splunk_get", return_value={"entry": [{"content": content}]}):
            self.assertEqual(alert.get_settings("https://127.0.0.1:8089", "session", True), ("https://owned.invalid/api/v1", True, REALM))
        for value in ({"entry": []}, {"entry": [{}]}, {"entry": [{"content": {**content, "verify_tls": "maybe"}}]},
                      {"entry": [{"content": {**content, "credential_realm": "foreign"}}]}):
            with self.subTest(value=value), patch.object(alert, "_splunk_get", return_value=value), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(alert.get_settings("https://127.0.0.1:8089", "session", True), ("", True, ""))
        with patch.object(alert, "_splunk_get", side_effect=OSError("PRIVATE-response")), contextlib.redirect_stderr(io.StringIO()) as log:
            self.assertEqual(alert.get_token("https://127.0.0.1:8089", "PRIVATE-session"), "")
            self.assertNotIn("PRIVATE", log.getvalue())

    def test_management_tls_contexts_and_exact_headers(self):
        path = "/servicesNS/nobody/darkmoon/configs/conf-darkmoon/settings?output_mode=json"
        for base, insecure in (("https://127.0.0.1:8089", True), ("https://[::1]:8089", True),
                               ("https://localhost:8089", False), ("https://remote.invalid:8089", False)):
            captured = []
            def fake(request, context, timeout):
                captured.append((request, context, timeout))
                return Response({"entry": []})
            with self.subTest(base=base), patch.object(alert, "open_request", side_effect=fake):
                alert._splunk_get(base, "fixture-session", path, verify=False)
                request, context, timeout = captured[0]
                self.assertEqual(request.get_header("Authorization"), "Splunk fixture-session")
                self.assertEqual(context.verify_mode, ssl.CERT_NONE if insecure else ssl.CERT_REQUIRED)
                self.assertEqual(context.check_hostname, not insecure)
                self.assertEqual(timeout, alert.OUTBOUND_TIMEOUT)

    def test_invalid_management_connections_paths_headers_and_response_bounds(self):
        path = "/servicesNS/nobody/darkmoon/configs/conf-darkmoon/settings?output_mode=json"
        for base in ("http://127.0.0.1:8089", "https://u:p@owned.invalid", "https://owned.invalid/other",
                     "https://owned.invalid/?", "https://owned.invalid/#", "https://owned.invalid:0", "https://owned.invalid:bad", "https://owned.invalid\\x"):
            with self.subTest(base=base), patch.object(alert, "open_request") as network, self.assertRaises(ValueError):
                alert._splunk_get(base, "session", path, verify=False)
            network.assert_not_called()
        for key, target in (("x\nINJECT", path), ("session", "/services/server/info")):
            with patch.object(alert, "open_request") as network, self.assertRaises(ValueError):
                alert._splunk_get("https://127.0.0.1:8089", key, target)
            network.assert_not_called()
        with patch.object(alert, "open_request", return_value=Response(b" " * (alert.MAX_RESPONSE_BYTES + 1))), self.assertRaises(ValueError):
            alert._splunk_get("https://127.0.0.1:8089", "session", path)

    def test_host_normalization_and_invalid_allowlists_fail_completely(self):
        for raw, expected in (("OWNED.invalid:443", "owned.invalid"), ("https://[::1]:443/x", "::1"),
                              ("2001:0db8::1", "2001:db8::1"), ("127.0.0.1", "127.0.0.1")):
            self.assertEqual(alert.normalize_host(raw), expected)
        for raw in (None, [], "999.2.3.4", "https://u:p@owned.invalid", "owned.invalid?q=secret", "\nowned.invalid", "owned.invalid:bad"):
            self.assertIsNone(alert.normalize_host(raw))
        for text in ("target,allow_destructive\nowned.invalid,0\nOWNED.invalid,1\n",
                     "target,allow_destructive\nowned.invalid,0\nbad host,1\n",
                     "target,target,allow_destructive\nowned.invalid,other.invalid,1\n",
                     "target,allow_destructive\nowned.invalid,maybe\n"):
            (self.lookups / "darkmoon_targets.csv").write_text(text)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(alert.load_allowlist(), {})

    def test_quota_types_corrupt_future_and_oversized_state_fail_closed(self):
        for value in (True, False, 0, -1, 1.5, "1.5", "bad", [], {}):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()):
                self.assertFalse(alert.rate_limit_ok(value)[0])
        self.assertTrue(alert.rate_limit_ok(2)[0])
        self.assertTrue(alert.rate_limit_ok(2)[0])
        self.assertFalse(alert.rate_limit_ok(2)[0])
        state = self.home / "var/run/darkmoon/ratelimit.json"
        for contents in ("broken", json.dumps([time.time() + 3600]), json.dumps([True]), json.dumps([time.time()] * 13), " " * 65537):
            state.write_text(contents)
            with self.subTest(contents=contents[:60]), contextlib.redirect_stderr(io.StringIO()):
                self.assertFalse(alert.rate_limit_ok(2)[0])

    @unittest.skipIf(os.name == "nt", "POSIX special-file behavior; Windows lock tested by concurrent admissions")
    def test_unsafe_quota_files_are_refused_without_blocking(self):
        directory = self.home / "var/run/darkmoon"
        directory.mkdir(parents=True)
        state = directory / "ratelimit.json"
        other = self.home / "other"
        other.write_text("[]")
        for kind in ("symlink", "hardlink", "fifo", "directory"):
            if kind == "symlink": state.symlink_to(other)
            elif kind == "hardlink": os.link(other, state)
            elif kind == "fifo": os.mkfifo(state)
            else: state.mkdir()
            with self.subTest(kind=kind), contextlib.redirect_stderr(io.StringIO()):
                self.assertFalse(alert.rate_limit_ok(2)[0])
            if kind == "directory": state.rmdir()
            else: state.unlink()

    def test_process_serialized_quota_has_exact_admission_ceiling(self):
        code = ("import importlib.util,json; "
                f"s=importlib.util.spec_from_file_location('action',{str(SCRIPT)!r}); "
                "m=importlib.util.module_from_spec(s);s.loader.exec_module(m); "
                "print(json.dumps(m.rate_limit_ok(3)))")
        def run(_):
            result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(run, range(8)))
        self.assertEqual(sum(results), 3)

    def main(self, payload):
        with patch.object(sys, "argv", ["action", "--execute"]), patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), contextlib.redirect_stderr(io.StringIO()) as log, self.assertRaises(SystemExit) as result:
            alert.main()
        return result.exception.code, log.getvalue()

    def test_strict_payload_and_dry_run_never_request_credentials(self):
        for payload in ([], {"configuration": []}, {"result": []},
                        {"configuration": {"action_kind": "other"}}, {"configuration": {"scope_profile": {}}},
                        {"configuration": {"dry_run": "maybe"}}):
            with self.subTest(payload=payload), patch.object(alert, "open_request") as network:
                self.assertEqual(self.main(payload)[0], 2)
                network.assert_not_called()
        payload = {"configuration": {"target": "owned.invalid", "dry_run": "1"}, "session_key": "PRIVATE-session"}
        with patch.object(alert, "get_settings") as settings, patch.object(alert, "darkmoon_call") as launch:
            code, log = self.main(payload)
            self.assertEqual(code, 0)
            self.assertIn("DRY-RUN", log)
            self.assertNotIn("PRIVATE", log)
            settings.assert_not_called()
            launch.assert_not_called()

    def test_live_main_keeps_url_and_generation_from_same_snapshot(self):
        payload = {"configuration": {"target": "owned.invalid", "dry_run": "0"}, "session_key": "fixture-session"}
        with patch.object(alert, "get_settings", return_value=("https://owned.invalid", True, REALM)), patch.object(alert, "get_token", return_value="fixture-token") as token, patch.object(alert, "darkmoon_call", return_value=(True, "accepted; completion unverified")) as launch:
            self.assertEqual(self.main(payload)[0], 0)
            self.assertEqual(token.call_args.kwargs["realm"], REALM)
            self.assertEqual(launch.call_args.args[:3], ("https://owned.invalid", "fixture-token", True))

    def test_saved_target_and_launch_identity_errors_are_not_success(self):
        target = {"data": [{"id": "target.one", "host": "owned.invalid"}]}
        for launch in ({"id": "r", "retest_id": "r", "target_id": "target.one", "status": "running"},
                       {"id": "foreign", "retest_id": "r"}, {"retest_id": "r", "target_id": "foreign"},
                       {"retest_id": "r", "run_id": []}, {"retest_id": "r", "status": "FAILED"}):
            with self.subTest(launch=launch), patch.object(alert, "open_request", side_effect=[Response(target), Response(launch)]):
                ok, message = alert.darkmoon_call("https://owned.invalid", "fixture-token", True, "retest", "owned.invalid", "non-destructive")
                self.assertEqual(ok, launch == {"id": "r", "retest_id": "r", "target_id": "target.one", "status": "running"})
                self.assertNotIn("PRIVATE", message)
        for rows in ([], target["data"] * 2, [{"id": "t", "host": "foreign.invalid"}]):
            with patch.object(alert, "open_request", return_value=Response({"data": rows})) as network:
                self.assertFalse(alert.darkmoon_call("https://owned.invalid", "fixture-token", True, "retest", "owned.invalid", "non-destructive")[0])
                self.assertEqual(network.call_count, 1)


if __name__ == "__main__":
    unittest.main()
