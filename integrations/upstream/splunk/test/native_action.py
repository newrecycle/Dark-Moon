#!/usr/bin/env python3
"""Installed Splunk Python alert-action acceptance against a local Dark Moon fixture.

Requires native_browser.cjs to configure the fixture realm/token through real
SplunkJS. Invokes Splunk's OWN Python runtime via 'splunk cmd python3', not an
offline mock. Never runs Dark Moon; only a strict localhost metadata HTTP stub.
On missing Splunk executable/host/operator attestation exit 3 (unavailable).
"""
import base64
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from native_acceptance import Unavailable, local_url, preflight, open_local


def request(url, data, context, headers=None):
    payload = (json.dumps(data).encode() if (headers or {}).get("Content-Type") == "application/json"
               else urllib.parse.urlencode(data).encode()) if isinstance(data, dict) else json.dumps(data).encode()
    req = urllib.request.Request(url, data=payload, headers=(headers or {}), method="POST")
    with open_local(req, context, 15) as response:
        return response.read(64 * 1024)


def fixture_status(base, context):
    req = urllib.request.Request(base + "/__fixture__/state")
    with open_local(req, context, 5) as response:
        return json.loads(response.read(4096))


def main():
    try:
        mgmt, _, _, _, ctx = preflight()
        fixture = local_url("SPLUNK_NATIVE_DARKMOON", "", required_scheme="http")
        splunk_home = Path(os.environ.get("SPLUNK_NATIVE_SPLUNK_HOME", ""))
        if not splunk_home.is_absolute():
            raise Unavailable("SPLUNK_NATIVE_SPLUNK_HOME must be the real host's installed Splunk directory")
        cli = splunk_home / "bin" / "splunk"
        action = splunk_home / "etc" / "apps" / "darkmoon" / "bin" / "darkmoon_campaign.py"
        if not cli.is_file() or not action.is_file():
            raise Unavailable("native Splunk CLI and installed app alert action are required")
        if fixture_status(fixture, ctx)["posts"]:
            raise Unavailable("fixture must be freshly started with no prior launch records")
        quota = splunk_home / "var" / "run" / "darkmoon" / "ratelimit.json"
        if quota.exists():
            raise Unavailable("disposable Splunk host must have fresh, unused alert quota")
    except (Unavailable, OSError, urllib.error.URLError) as err:
        print("NATIVE ACTION UNAVAILABLE: " + str(err).split("\n")[0][:140], file=sys.stderr)
        return 3

    auth_xml = None
    try:
        auth_xml = request(mgmt + "/services/auth/login",
                           {"username": os.environ["SPLUNK_NATIVE_USER"],
                            "password": os.environ["SPLUNK_NATIVE_PASSWORD"]},
                           ctx)
        session = ET.fromstring(auth_xml).findtext(".//sessionKey")
        if not session or len(session) > 16384:
            raise ValueError("no native Splunk session key")
    except (ET.ParseError, ValueError, urllib.error.URLError):
        print("NATIVE ACTION FAIL: could not obtain native Splunk session", file=sys.stderr)
        return 1

    # Fixture's synthetic token is the value installed by the successful
    # native browser test. Never include it in subprocess diagnostics.
    config = {"target": "demo-shop.local", "action_kind": "retest", "retest_scope": "finding",
              "scope_profile": "non-destructive", "dry_run": "0", "max_per_hour": "8",
              "campaign_id": "fixture_campaign", "finding_id": "fixture_finding"}
    payload = {"configuration": config, "result": {"target": "demo-shop.local"},
               "session_key": session, "server_uri": mgmt}
    cmd = [str(cli), "cmd", "python3", str(action), "--execute"]
    env = {**os.environ, "SPLUNK_HOME": str(splunk_home)}

    def invoke():
        try:
            run = subprocess.run(cmd, input=json.dumps(payload).encode(), capture_output=True,
                                 cwd=str(action.parent), env=env, timeout=45)
        except (OSError, subprocess.TimeoutExpired):
            raise AssertionError("native Splunk Python action could not execute")
        output = (run.stdout + run.stderr).decode("utf-8", "replace")
        for secret in (session, os.environ["SPLUNK_NATIVE_PASSWORD"], "fixture-darkmoon-token"):
            if secret in output:
                raise AssertionError("sensitive authentication material appeared in action diagnostics")
        return run.returncode, output

    def mode(mode):
        request(fixture + "/__fixture__/mode", {"mode": mode}, ctx,
                {"Content-Type": "application/json"})

    try:
        # A failed/partial GET must not be confused with a valid empty set.
        for refused in ("malformed", "unavailable", "empty", "foreign"):
            mode(refused)
            before = len(fixture_status(fixture, ctx)["posts"])
            code, out = invoke()
            if code == 0 or len(fixture_status(fixture, ctx)["posts"]) != before:
                raise AssertionError("bad scope metadata triggered a native retest")
        # Authenticated, well-scoped metadata can reach the local fixture.
        # A malformed launch acknowledgement must NOT be reported successful.
        mode("bad_launch")
        code, out = invoke()
        if code == 0 or len(fixture_status(fixture, ctx)["posts"]) != 1:
            raise AssertionError("malformed native launch identity accepted")
        mode("valid")
        for allowed in range(3):
            code, out = invoke()
            if code != 0:
                raise AssertionError("native scoped retest was not accepted")
        posts = fixture_status(fixture, ctx)["posts"]
        exact = {"target_id": "fixture_target", "campaign_id": "fixture_campaign",
                 "finding_ids": ["fixture_finding"]}
        if len(posts) != 4 or any(row != exact for row in posts):
            raise AssertionError("native action changed exact campaign/finding/target selection")
        # 8 consumed attempts (including rejected/uncertain ones); the ninth
        # must be rejected before any metadata or POST, not silently admitted.
        code, out = invoke()
        if code == 0 or len(fixture_status(fixture, ctx)["posts"]) != 4:
            raise AssertionError("native quota did not block excess attempts")
        print("PASS native installed alert preflight, exact scope, rejection and quota")
        return 0
    except (AssertionError, urllib.error.URLError, ValueError):
        print("NATIVE ACTION FAIL: scoped alert or quota assertion failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
