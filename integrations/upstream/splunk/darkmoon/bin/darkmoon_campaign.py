#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Custom alert action: "Send to Darkmoon".

Triggers a Darkmoon retest/campaign against an ALLOWLISTED target from a Splunk
correlation search (the offensive-validation loop).

Security model (all enforced here, fail-closed):
  * target allowlist   -- only hosts in lookups/darkmoon_targets.csv are accepted
  * safe_harbor        -- non-destructive profile unless the target row opts in
  * auth               -- Darkmoon token read at runtime from storage/passwords
  * rate limiting      -- token bucket, hard-capped per rolling hour
  * TLS verification    -- on by default; result rows treated as untrusted input

Dependency-free: uses only the Python 3 standard library (Splunk ships it), so
nothing is bundled and nothing reaches the network except the two documented
hosts (this Splunk instance's REST API and the configured Darkmoon base URL).

Nothing sensitive is ever printed: tokens/session keys are scrubbed from logs.
"""

import csv
import json
import os
import re
import sys
import time
import ssl
import urllib.request
import urllib.parse
import urllib.error

APP = "darkmoon"
HARD_MAX_PER_HOUR = 12          # absolute ceiling regardless of param
DEFAULT_MAX_PER_HOUR = 6
OUTBOUND_TIMEOUT = 20

# Strict host/IP validation for any target derived from (untrusted) result rows.
_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-zA-Z0-9_](?:[a-zA-Z0-9_-]{0,61}[a-zA-Z0-9])?)"
                      r"(\.[a-zA-Z0-9_](?:[a-zA-Z0-9_-]{0,61}[a-zA-Z0-9])?)*$")
_IPV4_RE = re.compile(r"^(\d{1,3})(\.\d{1,3}){3}$")
_SECRET_RE = re.compile(r"(?i)(bearer\s+|(?:token|secret|password|session[_-]?key|authorization)"
                        r"\"?\s*[:=]\s*\"?)([A-Za-z0-9._\-]{6,})")


def log(msg):
    """Write a scrubbed line to stderr (captured in splunkd/python.log)."""
    scrubbed = _SECRET_RE.sub(lambda m: m.group(1) + "[REDACTED]", str(msg))
    sys.stderr.write("darkmoon_campaign - %s\n" % scrubbed)


def app_dir():
    # .../etc/apps/darkmoon/bin/darkmoon_campaign.py -> .../etc/apps/darkmoon
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _splunk_get(server_uri, session_key, path, verify=True):
    url = server_uri.rstrip("/") + path
    req = urllib.request.Request(url, headers={"Authorization": "Splunk " + session_key})
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=OUTBOUND_TIMEOUT, context=ctx) as r:
        return json.loads(r.read().decode("utf-8"))


def get_settings(server_uri, session_key):
    """Return (base_url, verify_tls) from this app's darkmoon.conf. Splunk's own
    REST is on loopback with a self-signed cert, so we don't verify localhost."""
    base_url, verify_tls = "", True
    try:
        data = _splunk_get(
            server_uri, session_key,
            "/servicesNS/nobody/%s/configs/conf-darkmoon/settings?output_mode=json" % APP,
            verify=False)
        content = data.get("entry", [{}])[0].get("content", {})
        base_url = (content.get("base_url") or "").strip()
        vt = str(content.get("verify_tls", "1")).strip().lower()
        verify_tls = vt not in ("0", "false", "no", "")
    except Exception as e:
        log("could not read darkmoon.conf settings: %s" % e)
    return base_url, verify_tls


def get_token(server_uri, session_key):
    """Read the Darkmoon API token from storage/passwords (encrypted at rest)."""
    try:
        data = _splunk_get(
            server_uri, session_key,
            "/servicesNS/nobody/%s/storage/passwords?output_mode=json&count=0" % APP,
            verify=False)
        for entry in data.get("entry", []):
            content = entry.get("content", {})
            username = (content.get("username") or "").lower()
            if username in ("darkmoon", "token", "api_token"):
                return content.get("clear_password") or ""
        # fall back to the first credential in the app context
        for entry in data.get("entry", []):
            cp = entry.get("content", {}).get("clear_password")
            if cp:
                return cp
    except Exception as e:
        log("could not read storage/passwords: %s" % e)
    return ""


def load_allowlist():
    """Return {host_lower: {allow_destructive: bool}} from the shipped lookup."""
    allow = {}
    path = os.path.join(app_dir(), "lookups", "darkmoon_targets.csv")
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                host = (row.get("target") or "").strip().lower()
                if not host:
                    continue
                dest = str(row.get("allow_destructive", "")).strip().lower()
                allow[host] = {"allow_destructive": dest in ("1", "true", "yes")}
    except Exception as e:
        log("could not read allowlist: %s" % e)
    return allow


def normalize_host(raw):
    """Extract a bare host from a host or URL; return None if it is not valid."""
    if not raw:
        return None
    raw = raw.strip()
    if "://" in raw:
        try:
            raw = urllib.parse.urlparse(raw).hostname or ""
        except Exception:
            return None
    raw = raw.split("/")[0].split(":")[0].strip().lower()
    if not raw:
        return None
    if _IPV4_RE.match(raw):
        if all(0 <= int(o) <= 255 for o in raw.split(".")):
            return raw
        return None
    if _HOST_RE.match(raw):
        return raw
    return None


def rate_limit_ok(max_per_hour):
    """Token bucket persisted under SPLUNK_HOME/var/run (writable, outside app)."""
    cap = min(int(max_per_hour or DEFAULT_MAX_PER_HOUR), HARD_MAX_PER_HOUR)
    state_dir = os.path.join(os.environ.get("SPLUNK_HOME", "/tmp"), "var", "run", "darkmoon")
    state_file = os.path.join(state_dir, "ratelimit.json")
    now = time.time()
    window = 3600.0
    try:
        os.makedirs(state_dir, exist_ok=True)
        hits = []
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as fh:
                hits = [t for t in json.load(fh) if now - t < window]
        if len(hits) >= cap:
            return False, cap, len(hits)
        hits.append(now)
        with open(state_file, "w", encoding="utf-8") as fh:
            json.dump(hits, fh)
        return True, cap, len(hits)
    except Exception as e:
        log("rate-limit state error (failing closed): %s" % e)
        return False, cap, -1


def darkmoon_call(base_url, token, verify_tls, action_kind, host, scope_profile):
    """POST to the Darkmoon Pro REST API. Returns (ok, message)."""
    if action_kind == "campaign":
        path = "/api/v1/run/campaign"
        payload = {"target": host, "safe_harbor": scope_profile}
    else:
        path = "/api/v1/retest"
        payload = {"target_id": host, "safe_harbor": scope_profile}

    url = base_url.rstrip("/") + path
    if not url.lower().startswith("https://") and verify_tls:
        return False, "refusing non-HTTPS Darkmoon URL while TLS verification is on"

    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    ctx = ssl.create_default_context()
    if not verify_tls:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=OUTBOUND_TIMEOUT, context=ctx) as r:
            data = json.loads(r.read().decode("utf-8"))
            ref = data.get("run_id") or data.get("retest_id") or "ok"
            return True, "launched %s (ref=%s)" % (action_kind, ref)
    except urllib.error.HTTPError as e:
        return False, "Darkmoon HTTP %s" % e.code
    except Exception as e:
        return False, "Darkmoon call failed: %s" % e


def main():
    if len(sys.argv) < 2 or sys.argv[1] != "--execute":
        log("expected --execute as first argument")
        sys.exit(1)

    try:
        payload = json.load(sys.stdin)
    except Exception as e:
        log("could not parse alert payload: %s" % e)
        sys.exit(2)

    cfg = payload.get("configuration", {}) or {}
    result = payload.get("result", {}) or {}
    session_key = payload.get("session_key", "")
    server_uri = payload.get("server_uri", "https://127.0.0.1:8089")

    action_kind = (cfg.get("action_kind") or "retest").strip().lower()
    if action_kind not in ("retest", "campaign"):
        action_kind = "retest"
    scope_profile = (cfg.get("scope_profile") or "non-destructive").strip().lower()
    dry_run = str(cfg.get("dry_run", "1")).strip().lower() not in ("0", "false", "no", "")
    max_per_hour = cfg.get("max_per_hour") or DEFAULT_MAX_PER_HOUR

    # Target: explicit param, else from the (untrusted) triggering result.
    raw_target = (cfg.get("target") or result.get("target")
                  or result.get("dest") or result.get("host") or "")
    host = normalize_host(raw_target)
    if not host:
        log("no valid target host (rejected untrusted/empty value); aborting")
        sys.exit(3)

    allow = load_allowlist()
    if host not in allow:
        log("target '%s' is NOT on the allowlist; refusing (out-of-scope guard)" % host)
        sys.exit(4)

    # safe_harbor: destructive only if the allowlist row opts in.
    if scope_profile != "non-destructive" and not allow[host]["allow_destructive"]:
        log("destructive profile requested for '%s' but not authorized; forcing non-destructive" % host)
        scope_profile = "non-destructive"

    ok, cap, used = rate_limit_ok(max_per_hour)
    if not ok:
        log("rate limit reached (%s/%s this hour) for host '%s'; dropping" % (used, cap, host))
        sys.exit(5)

    if dry_run:
        log("DRY-RUN: would %s host='%s' profile='%s' (allowlisted, %s/%s this hour)"
            % (action_kind, host, scope_profile, used, cap))
        sys.exit(0)

    base_url, verify_tls = get_settings(server_uri, session_key)
    if not base_url:
        log("no Darkmoon base URL configured (run app Set up); aborting")
        sys.exit(6)
    token = get_token(server_uri, session_key)
    if not token:
        log("no Darkmoon API token in storage/passwords (run app Set up); aborting")
        sys.exit(7)

    ok, msg = darkmoon_call(base_url, token, verify_tls, action_kind, host, scope_profile)
    log(("%s for host='%s' profile='%s'" % (msg, host, scope_profile)))
    sys.exit(0 if ok else 8)


if __name__ == "__main__":
    main()
