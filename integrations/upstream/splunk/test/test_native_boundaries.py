"""Fail-closed native-host prerequisite and published app-source regression tests.

These are intentionally OFFLINE. Passing them is *not* native acceptance.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "test"))
import native_acceptance as native


class NativeBoundaries(unittest.TestCase):
    def test_missing_operator_approval_is_explicitly_unavailable(self):
        env = {k:v for k,v in os.environ.items() if not k.startswith("SPLUNK_NATIVE_")}
        run = subprocess.run([sys.executable, str(ROOT / "test/native_acceptance.py"), "--native"],
                             env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 3)
        self.assertIn("NATIVE UNAVAILABLE", run.stderr)
        self.assertNotIn("NATIVE SPL/HEC PASS", run.stdout)

    def test_only_literal_loopback_management_and_hec_allowed(self):
        for raw in ("https://splunk.internal:8089", "http://127.0.0.1:8089",
                    "https://user:password@127.0.0.1:8089",
                    "https://127.0.0.1:0", "https://127.0.0.1:8089/?token=secret",
                    "https://127.0.0.1:8089/../secret",
                    "https://127.0.0.1.evil.net:8089"):
            with self.subTest(raw=raw):
                with mock.patch.dict(os.environ, {"SPLUNK_NATIVE_MGMT":raw}):
                    with self.assertRaises(native.Unavailable):
                        native.local_url("SPLUNK_NATIVE_MGMT","")
        with unittest.mock.patch.dict(os.environ, {"SPLUNK_NATIVE_HEC":
                "https://127.0.0.1:8088/services/collector/event"}):
            self.assertEqual(native.local_url("SPLUNK_NATIVE_HEC",""),
                             "https://127.0.0.1:8088/services/collector/event")
        with unittest.mock.patch.dict(os.environ, {"SPLUNK_NATIVE_HEC":
                "https://127.0.0.1:8088/other"}):
            with self.assertRaises(native.Unavailable):
                native.local_url("SPLUNK_NATIVE_HEC","")

    def test_installed_macro_scopes_both_indexes_to_darkmoon_sourcetype(self):
        text = (ROOT / "darkmoon/default/macros.conf").read_text()
        self.assertIn("definition = (index=darkmoon OR index=main) sourcetype=darkmoon:*", text)
        self.assertNotIn("definition = index=darkmoon OR index=main sourcetype=darkmoon:*", text)

    def test_remediation_defense_in_depth_redaction_is_not_missing(self):
        import configparser
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read(ROOT / "darkmoon/default/props.conf")
        for field in ("SEDCMD-dm_redact_bearer", "SEDCMD-dm_redact_token"):
            self.assertIn(field.lower(), cfg["darkmoon:remediation"])
            self.assertEqual(cfg["darkmoon:remediation"][field],
                             cfg["darkmoon:finding"][field])

    def test_fixture_is_actual_bounded_loopback_server_and_refuses_foreign_scope(self):
        import subprocess, select
        proc = subprocess.Popen([sys.executable, str(ROOT / "test/native_fixture.py")],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            line = proc.stdout.readline()
            config = json.loads(line)
            self.assertTrue(config["base_url"].startswith("http://127.0.0.1:"))
            host = config["base_url"]
            def read(path, payload=None, token=True):
                headers = {"Authorization": "Bearer fixture-darkmoon-token"} if token else {}
                data = json.dumps(payload).encode() if payload is not None else None
                if data: headers["Content-Type"] = "application/json"
                request = urllib.request.Request(host + path, data=data, headers=headers)
                try:
                    with urllib.request.urlopen(request, timeout=3) as response:
                        return response.status, json.loads(response.read(16384))
                except urllib.error.HTTPError as err:
                    return err.code, json.loads(err.read(16384))
            self.assertEqual(read("/api/v1/targets")[1]["data"][0]["host"], "demo-shop.local")
            self.assertEqual(read("/api/v1/vulnerabilities?target_id=fixture_target"
                                  "&campaign_id=fixture_campaign&q=fixture_finding")[1]["total"], 1)
            invalid = {"target_id":"fixture_target","campaign_id":"wrong",
                       "finding_ids":["fixture_finding"],"safe_harbor":"non-destructive"}
            self.assertEqual(read("/api/v1/retest", invalid)[0], 400)
            self.assertEqual(read("/__fixture__/state",token=False)[1]["posts"], [])
            self.assertEqual(read("/__fixture__/mode", {"mode": "malformed"}, token=False)[0], 200)
            self.assertIsInstance(read("/api/v1/targets")[1]["data"], str)
            self.assertEqual(read("/__fixture__/mode", {"mode": "valid"}, token=False)[0], 200)
            valid = invalid | {"campaign_id":"fixture_campaign"}
            self.assertEqual(read("/api/v1/retest", valid)[0], 200)
            self.assertEqual(len(read("/__fixture__/state",token=False)[1]["posts"]), 1)
        finally:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)

    def test_native_program_syntax_and_no_license_bootstrap(self):
        src = "\n".join((ROOT / "test" / name).read_text() for name in
                        ("native_acceptance.py", "native_fixture.py", "native_action.py"))
        self.assertNotIn("--accept-license", src)
        self.assertNotIn("splunk/splunk:latest", src)
        for name in ("native_acceptance.py", "native_fixture.py", "native_action.py"):
            compile((ROOT / "test" / name).read_text(),
                    str(ROOT / "test" / name), "exec")


if __name__ == "__main__":
    unittest.main()
