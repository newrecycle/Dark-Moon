#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline unit tests for the alert action security guards (no Splunk needed)."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "darkmoon", "bin", "darkmoon_campaign.py")


def run(cfg, result=None, splunk_home=None):
    payload = {"configuration": cfg, "result": result or {},
               "session_key": "SESSIONKEY_shouldnotleak", "server_uri": "https://127.0.0.1:8089"}
    env = dict(os.environ)
    if splunk_home:
        env["SPLUNK_HOME"] = splunk_home
    p = subprocess.run([sys.executable, SCRIPT, "--execute"],
                       input=json.dumps(payload).encode(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    return p.returncode, p.stderr.decode()


def main():
    fails = 0
    tmp = tempfile.mkdtemp()

    # 1. allowlisted + dry_run -> 0
    rc, err = run({"target": "demo-shop.local", "dry_run": "1", "max_per_hour": "9"}, splunk_home=tmp)
    ok = rc == 0 and "DRY-RUN" in err
    print(("PASS" if ok else "FAIL"), "allowlisted dry-run -> exit 0 (got %d)" % rc); fails += 0 if ok else 1

    # 2. not on allowlist -> 4
    rc, _ = run({"target": "evil.example.com", "dry_run": "1"}, splunk_home=tempfile.mkdtemp())
    ok = rc == 4
    print(("PASS" if ok else "FAIL"), "out-of-scope target refused -> exit 4 (got %d)" % rc); fails += 0 if ok else 1

    # 3. garbage/invalid host -> 3
    rc, _ = run({"target": "not a host!! ; rm -rf", "dry_run": "1"}, splunk_home=tempfile.mkdtemp())
    ok = rc == 3
    print(("PASS" if ok else "FAIL"), "invalid host rejected -> exit 3 (got %d)" % rc); fails += 0 if ok else 1

    # 4. destructive profile on non-destructive-only target -> forced (still exit 0), logged
    rc, err = run({"target": "demo-shop.local", "scope_profile": "authorized", "dry_run": "1"},
                  splunk_home=tempfile.mkdtemp())
    ok = rc == 0 and "forcing non-destructive" in err
    print(("PASS" if ok else "FAIL"), "destructive forced to non-destructive (got %d)" % rc); fails += 0 if ok else 1

    # 5. rate limit: cap 2, third call -> 5
    sh = tempfile.mkdtemp()
    r1, _ = run({"target": "demo-shop.local", "dry_run": "1", "max_per_hour": "2"}, splunk_home=sh)
    r2, _ = run({"target": "demo-shop.local", "dry_run": "1", "max_per_hour": "2"}, splunk_home=sh)
    r3, _ = run({"target": "demo-shop.local", "dry_run": "1", "max_per_hour": "2"}, splunk_home=sh)
    ok = r1 == 0 and r2 == 0 and r3 == 5
    print(("PASS" if ok else "FAIL"), "rate limit enforced (2 ok, 3rd dropped): %d,%d,%d" % (r1, r2, r3)); fails += 0 if ok else 1

    # 6. target from untrusted result row, allowlisted
    rc, err = run({"dry_run": "1"}, result={"dest": "demo-shop.local"}, splunk_home=tempfile.mkdtemp())
    ok = rc == 0
    print(("PASS" if ok else "FAIL"), "target from result row (dest) accepted (got %d)" % rc); fails += 0 if ok else 1

    # 7. session key never leaked to stderr
    rc, err = run({"target": "demo-shop.local", "dry_run": "1"}, splunk_home=tempfile.mkdtemp())
    ok = "SESSIONKEY_shouldnotleak" not in err
    print(("PASS" if ok else "FAIL"), "session key not leaked in logs"); fails += 0 if ok else 1

    print("\n%s" % ("ALL PASS" if fails == 0 else "%d FAILURE(S)" % fails))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
