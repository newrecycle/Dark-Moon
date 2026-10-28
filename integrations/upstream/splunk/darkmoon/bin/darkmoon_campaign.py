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
import ipaddress
import math
import tempfile
from contextlib import contextmanager
import json
import os
import re
import sys
import time
import ssl
import stat
from urllib.parse import urlsplit
import urllib.request
import urllib.parse
import urllib.error

APP = "darkmoon"
HARD_MAX_PER_HOUR = 12          # absolute ceiling regardless of param
DEFAULT_MAX_PER_HOUR = 6
OUTBOUND_TIMEOUT = 20
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_ALERT_BYTES = 1024 * 1024
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}\Z")

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


def connection_url(value, verify=True):
    """Validate the configured destination before constructing auth headers."""
    if (not isinstance(value, str) or not value or len(value) > 8192
            or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value)
            or any(ch in value for ch in ("\\", "?", "#"))):
        raise ValueError("Invalid service URL")
    try:
        parts = urlsplit(value)
        port = parts.port
        if (parts.scheme not in {"https", "http"} or not parts.hostname
                or parts.username is not None or parts.password is not None
                or port == 0 or verify and parts.scheme != "https"):
            raise ValueError("Invalid service URL")
    except ValueError:
        raise ValueError("Configure a valid service URL with verified HTTPS by default") from None
    return value.rstrip("/")


def auth_value(value):
    return (isinstance(value, str) and bool(value) and len(value) <= 16384
            and value == value.strip()
            and not any(ord(ch) < 32 or ord(ch) == 127 for ch in value))


def _splunk_get(server_uri, session_key, path, verify=True):
    base = connection_url(server_uri, verify=True)
    parsed = urlsplit(base)
    if parsed.path or not auth_value(session_key):
        raise ValueError("Invalid management connection")
    allowed = {
        "/servicesNS/nobody/%s/configs/conf-darkmoon/settings?output_mode=json" % APP,
        "/servicesNS/nobody/%s/storage/passwords?output_mode=json&count=0" % APP,
    }
    if path not in allowed:
        raise ValueError("Unsupported management read")
    url = base + path
    req = urllib.request.Request(url, headers={"Authorization": "Splunk " + session_key})
    ctx = ssl.create_default_context()
    try:
        literal_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        literal_loopback = False
    # Splunk commonly supplies its self-signed literal loopback management
    # endpoint. Remote/named hosts always retain certificate verification.
    if not verify and literal_loopback:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    with open_request(req, ctx, OUTBOUND_TIMEOUT) as r:
        raw = r.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("Management response exceeds the size limit")
        result = json.loads(raw.decode("utf-8"))
        if not isinstance(result, dict):
            raise ValueError("Invalid management response")
        return result


def get_settings(server_uri, session_key, with_binding=False):
    """Read connection settings, optionally including the credential reference.

    Literal HTTPS loopback may use its self-signed certificate; remote
    management hosts always require a valid certificate."""
    base_url, verify_tls = "", True
    try:
        data = _splunk_get(
            server_uri, session_key,
            "/servicesNS/nobody/%s/configs/conf-darkmoon/settings?output_mode=json" % APP,
            verify=False)
        entries = data.get("entry")
        if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
            raise ValueError("Expected one settings record")
        content = entries[0].get("content")
        if not isinstance(content, dict):
            raise ValueError("Invalid settings record")
        verify_tls = flag(content.get("verify_tls", "1"))
        base_url = connection_url(content.get("base_url"), verify_tls)
        realm = content.get("credential_realm", "")
        if not isinstance(realm, str) or realm and not re.fullmatch(r"darkmoon-[0-9a-f]{32}", realm):
            raise ValueError("Invalid credential binding")
    except Exception:
        log("could not read valid Darkmoon connection settings")
        return ("", True, "") if with_binding else ("", True)
    return (base_url, verify_tls, realm) if with_binding else (base_url, verify_tls)


def get_token(server_uri, session_key, realm=""):
    """Select the configured immutable credential generation or named legacy key."""
    try:
        if not isinstance(realm, str) or realm and not re.fullmatch(r"darkmoon-[0-9a-f]{32}", realm):
            raise ValueError("Invalid credential binding")
        data = _splunk_get(
            server_uri, session_key,
            "/servicesNS/nobody/%s/storage/passwords?output_mode=json&count=0" % APP,
            verify=False)
        entries = data.get("entry")
        if not isinstance(entries, list):
            raise ValueError("Invalid credential response")
        primary, legacy = [], []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("content"), dict):
                raise ValueError("Invalid credential record")
            content = entry["content"]
            stored_realm = content.get("realm")
            if stored_realm is not None and not isinstance(stored_realm, str):
                raise ValueError("Invalid credential realm")
            if (stored_realm or "") != realm:
                continue
            username = content.get("username")
            if username == "darkmoon":
                primary.append(content.get("clear_password"))
            elif not realm and username in ("token", "api_token"):
                legacy.append(content.get("clear_password"))
        candidates = primary or legacy
        if len(candidates) != 1 or not auth_value(candidates[0]):
            raise ValueError("Named credential is unavailable or ambiguous")
        return candidates[0]
    except Exception:
        log("named Darkmoon credential unavailable or ambiguous")
    return ""


def load_allowlist():
    """Return {host_lower: {allow_destructive: bool}} from the shipped lookup."""
    allow = {}
    path = os.path.join(app_dir(), "lookups", "darkmoon_targets.csv")
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames or "target" not in reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError("Missing or duplicate allowlist column")
            for row in reader:
                if not row.get("target"):
                    continue
                host = normalize_host(row["target"])
                if host is None or host in allow:
                    raise ValueError("Invalid or duplicate allowlisted host")
                allow[host] = {"allow_destructive": flag(row.get("allow_destructive") or "0")}
    except Exception:
        log("allowlist unavailable or invalid; no targets authorized")
        return {}
    return allow


def normalize_host(raw):
    """Extract a bare host from a host or URL; return None if it is not valid."""
    if not isinstance(raw, str) or not raw:
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        return None
    raw = raw.strip()
    if not raw or len(raw) > 8192 or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in raw) or any(ch in raw for ch in ("\\", "?", "#")):
        return None
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        pass
    try:
        parsed = urlsplit(raw if "://" in raw else "//" + raw)
        if "://" in raw and parsed.scheme not in {"https", "http"}:
            return None
        if parsed.username is not None or parsed.password is not None or parsed.port == 0:
            return None
        host = (parsed.hostname or "").lower()
    except ValueError:
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        if _IPV4_RE.fullmatch(host):
            return None
    if _HOST_RE.fullmatch(host):
        return host
    return None


def flag(value):
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.lower() in ("0", "1", "true", "false", "yes", "no"):
        return value.lower() in ("1", "true", "yes")
    raise ValueError("Expected a boolean setting")


@contextmanager
def rate_lock(path):
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), 0o600)
    with os.fdopen(fd, "a+b") as handle:
        item = os.fstat(handle.fileno())
        if not stat.S_ISREG(item.st_mode) or item.st_nlink != 1:
            raise ValueError("Invalid quota lock")
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
        if max_per_hour is None or max_per_hour == "":
            max_per_hour = DEFAULT_MAX_PER_HOUR
        if type(max_per_hour) is not int and (not isinstance(max_per_hour, str) or not re.fullmatch(r"[0-9]{1,6}", max_per_hour)):
            return False, cap, -1
        cap = min(int(max_per_hour), HARD_MAX_PER_HOUR)
        if cap < 1: return False, cap, -1
        state_dir = os.path.join(os.environ.get("SPLUNK_HOME", "/tmp"), "var", "run", "darkmoon")
        os.makedirs(state_dir, mode=0o700, exist_ok=True)
        state_file = os.path.join(state_dir, "ratelimit.json")
        with rate_lock(os.path.join(state_dir, "ratelimit.lock")):
            now = time.time()
            hits = []
            if os.path.lexists(state_file):
                fd = os.open(state_file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
                with os.fdopen(fd, "r", encoding="utf-8") as source:
                    item = os.fstat(source.fileno())
                    if not stat.S_ISREG(item.st_mode) or item.st_nlink != 1 or item.st_size > 65536:
                        raise ValueError("Invalid quota state file")
                    raw = source.read(65537)
                    if len(raw.encode("utf-8")) > 65536:
                        raise ValueError("Quota state exceeds size limit")
                    values = json.loads(raw)
                if not isinstance(values, list) or len(values) > HARD_MAX_PER_HOUR or any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 or value > now + 60 for value in values): raise ValueError("Invalid quota state")
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
    if (type(verify_tls) is not bool or not auth_value(token)
            or action_kind not in ("retest", "campaign")
            or scope_profile not in ("non-destructive", "authorized")
            or not isinstance(host, str) or not host or normalize_host(host) != host):
        return False, "invalid authenticated launch configuration"
    try:
        base = connection_url(base_url, verify_tls)
    except ValueError:
        return False, "invalid Darkmoon base URL; verified HTTPS is required by default"
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
            if len(matches) != 1 or not isinstance(matches[0].get("id"), str) or not _ID_RE.fullmatch(matches[0]["id"]): return False, "allowlisted host needs one unambiguous saved target"
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
            if "status" in data and (not isinstance(data["status"], str) or not data["status"] or data["status"] != data["status"].strip()):
                return False, "launch returned an invalid lifecycle state"
            for key in ("run_id", "campaign_id", "retest_id"):
                if key in data and data[key] is not None and (not isinstance(data[key], str) or not _ID_RE.fullmatch(data[key])):
                    return False, "launch returned an invalid reference"
            if str(data.get("status", "")).lower() in ("failed", "stopped", "cancelled", "timed_out", "interrupted", "incomplete"):
                return False, "launch did not return an accepted lifecycle state"
            ref = data.get("retest_id") if action_kind == "retest" else data.get("campaign_id") or data.get("run_id")
            if not isinstance(ref, str) or not _ID_RE.fullmatch(ref): return False, "launch returned no valid identity"
            if action_kind == "retest" and data.get("id") is not None and data["id"] != ref:
                return False, "launch returned conflicting retest references"
            if action_kind == "retest" and data.get("target_id") is not None and data["target_id"] != payload["target_id"]:
                return False, "launch returned a different saved target"
            return True, "accepted %s launch (ref=%s); completion is not yet established" % (action_kind, ref)
    except urllib.error.HTTPError as e:
        return False, "Darkmoon HTTP %s" % e.code
    except Exception:
        return False, "Darkmoon launch transport or response failed; completion is unverified"


def main():
    if len(sys.argv) < 2 or sys.argv[1] != "--execute":
        log("expected --execute as first argument")
        sys.exit(1)

    try:
        raw = sys.stdin.read(MAX_ALERT_BYTES + 1)
        if len(raw.encode("utf-8")) > MAX_ALERT_BYTES:
            raise ValueError("Oversized alert")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Expected alert object")
        cfg = payload.get("configuration", {})
        result = payload.get("result", {})
        if not isinstance(cfg, dict) or not isinstance(result, dict):
            raise ValueError("Expected typed alert objects")
        action_kind = cfg.get("action_kind", "retest")
        scope_profile = cfg.get("scope_profile", "non-destructive")
        if not isinstance(action_kind, str) or action_kind not in ("retest", "campaign"):
            raise ValueError("Unsupported action kind")
        if not isinstance(scope_profile, str) or scope_profile not in ("non-destructive", "authorized"):
            raise ValueError("Unsupported scope profile")
        dry_run = flag(cfg.get("dry_run", "1"))
    except Exception:
        log("alert payload or configuration is invalid")
        sys.exit(2)

    session_key = payload.get("session_key", "")
    server_uri = payload.get("server_uri", "https://127.0.0.1:8089")

    max_per_hour = cfg.get("max_per_hour", DEFAULT_MAX_PER_HOUR)

    # Target: explicit param, else from the (untrusted) triggering result.
    raw_target = ""
    for candidate in (cfg.get("target"), result.get("target"), result.get("dest"), result.get("host")):
        if candidate is None or candidate == "":
            continue
        raw_target = candidate
        break
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

    base_url, verify_tls, realm = get_settings(server_uri, session_key, with_binding=True)
    if not base_url:
        log("no Darkmoon base URL configured (run app Set up); aborting")
        sys.exit(6)
    token = get_token(server_uri, session_key, realm=realm)
    if not token:
        log("no Darkmoon API token in storage/passwords (run app Set up); aborting")
        sys.exit(7)

    ok, msg = darkmoon_call(base_url, token, verify_tls, action_kind, host, scope_profile)
    log(("%s for host='%s' profile='%s'" % (msg, host, scope_profile)))
    sys.exit(0 if ok else 8)


if __name__ == "__main__":
    main()
