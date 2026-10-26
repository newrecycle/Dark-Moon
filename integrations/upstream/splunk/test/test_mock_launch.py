#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integration test of the offensive-validation loop against a MOCK Darkmoon.

Imports the alert-action module and exercises its real outbound HTTP path
(darkmoon_call) against test/mock_darkmoon.py, then asserts the mock recorded
a well-formed, authenticated launch. No real Darkmoon is contacted.
"""
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "darkmoon", "bin", "darkmoon_campaign.py")
CALLS = "/tmp/mock_darkmoon_calls_test.json"
PORT = 8477


def load_module():
    spec = importlib.util.spec_from_file_location("darkmoon_campaign", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    env = dict(os.environ, MOCK_CALLS_FILE=CALLS)
    proc = subprocess.Popen([sys.executable, os.path.join(HERE, "mock_darkmoon.py"), str(PORT)],
                            env=env)
    try:
        # wait for mock
        base = "http://127.0.0.1:%d" % PORT
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/api/v1/system/info", timeout=1).read()
                break
            except Exception:
                time.sleep(0.2)

        mod = load_module()
        fails = 0

        # retest launch (http mock -> verify_tls must be False to allow non-https)
        ok, msg = mod.darkmoon_call(base, "TESTTOKEN", False, "retest",
                                    "demo-shop.local", "non-destructive")
        print(("PASS" if ok else "FAIL"), "retest launch ok:", msg); fails += 0 if ok else 1

        # campaign launch
        ok2, msg2 = mod.darkmoon_call(base, "TESTTOKEN", False, "campaign",
                                      "demo-shop.local", "non-destructive")
        print(("PASS" if ok2 else "FAIL"), "campaign launch ok:", msg2); fails += 0 if ok2 else 1

        # verify recorded calls
        calls = json.loads(urllib.request.urlopen(base + "/_calls").read().decode())
        paths = [c["path"] for c in calls]
        ok3 = "/api/v1/retest" in paths and "/api/v1/run/campaign" in paths
        print(("PASS" if ok3 else "FAIL"), "mock recorded both endpoints:", paths); fails += 0 if ok3 else 1

        ok4 = all(c["has_auth"] for c in calls)
        print(("PASS" if ok4 else "FAIL"), "all launches carried Authorization header"); fails += 0 if ok4 else 1

        ok5 = calls[0]["payload"].get("target") == "demo-shop.local" or \
              calls[0]["payload"].get("target_id") == "demo-shop.local"
        print(("PASS" if ok5 else "FAIL"), "target propagated to Darkmoon payload"); fails += 0 if ok5 else 1

        # https guard: with verify on, non-https must be refused
        ok6, msg6 = mod.darkmoon_call(base, "T", True, "retest", "demo-shop.local", "non-destructive")
        ok6 = (ok6 is False)
        print(("PASS" if ok6 else "FAIL"), "non-HTTPS refused when TLS verify on:", msg6); fails += 0 if ok6 else 1

        print("\n%s" % ("ALL PASS" if fails == 0 else "%d FAILURE(S)" % fails))
        sys.exit(1 if fails else 0)
    finally:
        proc.terminate()
        try:
            os.remove(CALLS)
        except Exception:
            pass


if __name__ == "__main__":
    main()
