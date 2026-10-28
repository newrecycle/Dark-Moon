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
import math
import tempfile
from contextlib import contextmanager
import json
import os
import re
import sys
import time
import ssl
from urllib.parse import urlsplit
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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None

def open_request(request, context, timeout):
    return urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context)).open(request, timeout=timeout)


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
    with open_request(req, ctx, OUTBOUND_TIMEOUT) as r:
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
    if not isinstance(raw, str) or not raw:
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


@contextmanager
def rate_lock(path):
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "a+b") as handle:
        if os.name == "nt":
            import msvcrt
            if os.fstat(handle.fileno()).st_size == 0: handle.write(b"0"); handle.flush()
            handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try: yield
            finally: handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def rate_limit_ok(max_per_hour):
    """Process-serialized rolling quota; atomic replacement prevents lost state."""
    cap = HARD_MAX_PER_HOUR
    temporary = None
    try:
        cap = min(int(max_per_hour or DEFAULT_MAX_PER_HOUR), HARD_MAX_PER_HOUR)
        if cap < 1: return False, cap, -1
        state_dir = os.path.join(os.environ.get("SPLUNK_HOME", "/tmp"), "var", "run", "darkmoon")
        os.makedirs(state_dir, mode=0o700, exist_ok=True)
        state_file = os.path.join(state_dir, "ratelimit.json")
        with rate_lock(os.path.join(state_dir, "ratelimit.lock")):
            now = time.time()
            hits = []
            if os.path.lexists(state_file):
                fd = os.open(state_file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                with os.fdopen(fd, "r", encoding="utf-8") as source: values = json.load(source)
                if not isinstance(values, list) or any(type(value) not in (int, float) or not math.isfinite(value) for value in values): raise ValueError("Invalid quota state")
                hits = [value for value in values if now - value < 3600]
            if len(hits) >= cap: return False, cap, len(hits)
            hits.append(now)
            fd, temporary = tempfile.mkstemp(prefix=".ratelimit-", dir=state_dir)
            with os.fdopen(fd, "w", encoding="utf-8") as destination:
                json.dump(hits, destination); destination.flush(); os.fsync(destination.fileno())
            os.replace(temporary, state_file)
            temporary = None
            return True, cap, len(hits)
    except Exception:
        log("rate-limit state unavailable; failing closed")
        return False, cap, -1
    finally:
        if temporary:
            try: os.unlink(temporary)
            except OSError: pass


def darkmoon_call(base_url, token, verify_tls, action_kind, host, scope_profile):
    """POST to the Darkmoon Pro REST API. Returns (ok, message)."""
    base = base_url.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False, "invalid Darkmoon base URL"
    if verify_tls and parsed.scheme != "https":
        return False, "refusing non-HTTPS Darkmoon URL while TLS verification is on"
    if base.endswith("/api/v1"): base = base[:-7]
    ctx = ssl.create_default_context()
    if not verify_tls:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    if action_kind == "campaign":
        path = "/api/v1/run/campaign"
        payload = {"target": host, "safe_harbor": scope_profile}
    else:
        # The allowlist contains hosts; the REST retest contract needs a saved
        # target ID. Resolve it through authenticated metadata, never a result's
        # untrusted ID or a hostname masquerading as an ID.
        request = urllib.request.Request(base + "/api/v1/targets", headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
        try:
            with open_request(request, ctx, OUTBOUND_TIMEOUT) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024: return False, "target metadata exceeds the size limit"
                records = json.loads(raw.decode("utf-8"))
            rows = records.get("data") if isinstance(records, dict) else None
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows): return False, "invalid target metadata"
            matches = [row for row in rows if normalize_host(row.get("host") or "") == host]
            if len(matches) != 1 or not isinstance(matches[0].get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", matches[0]["id"]): return False, "allowlisted host needs one unambiguous saved target"
            payload = {"target_id": matches[0]["id"], "safe_harbor": scope_profile}
        except Exception:
            return False, "saved target could not be resolved with the current credentials"
        path = "/api/v1/retest"
    url = base + path

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
        with open_request(req, ctx, OUTBOUND_TIMEOUT) as r:
            raw = r.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024: return False, "launch response exceeds the size limit"
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict): return False, "launch returned no valid identity"
            ref = data.get("retest_id") if action_kind == "retest" else data.get("campaign_id") or data.get("run_id")
            if not isinstance(ref, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", ref): return False, "launch returned no valid identity"
            return True, "accepted %s launch (ref=%s); completion is not yet established" % (action_kind, ref)
    except urllib.error.HTTPError as e:
        return False, "Darkmoon HTTP %s" % e.code
    except Exception as e:
        return False, "Darkmoon launch transport or response failed; completion is unverified"


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
