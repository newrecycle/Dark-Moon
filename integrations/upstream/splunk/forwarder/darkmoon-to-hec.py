#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
darkmoon-to-hec — ship SAFE Darkmoon events to a Splunk HTTP Event Collector.

This is the sender side for users who are NOT on the Darkmoon Pro webhook system.
This fork does not implement direct splunk_hec webhook delivery; use the
authenticated forwarder for HEC admission.

Two input modes:
  --rest-url URL --token TOK   poll the Darkmoon Pro REST API
  --export FILE                read a JSON export {campaigns, vulnerabilities,
                               pull_requests, retests} (same shape as REST `data`)

Two output modes:
  --hec-url URL --hec-token T  POST to Splunk HEC /services/collector/event
  --stdout                     print the exact HEC envelopes (dry run / testing)

SAFETY (non-negotiable):
  * Only allowlisted fields per event type are emitted (SAFE_FIELDS below).
  * Evidence, secrets, credentials, tokens, descriptions, remediation text and
    request/response bodies are dropped by construction.
  * Every emitted string value is scrubbed for token-like patterns as a second
    line of defense.
  * HTTPS and TLS certificate verification are required by default. Plaintext
    HTTP and unverified HTTPS require explicit --insecure (trusted lab only).

Standard library only. Python 3.8+.
"""

import argparse
import math
import hashlib
from urllib.parse import urlsplit, urlunsplit
import json
import os
import re
import ssl
import sys
import time
import uuid
import urllib.request
import urllib.error

# --- SAFE-FIELD ALLOWLISTS (the contract) ----------------------------------
SAFE_FIELDS = {
    "darkmoon:campaign": [
        "campaign_id", "project_id", "target_id", "target", "status",
        "overall_risk", "duration_seconds", "contract_version", "event", "ts",
    ],
    "darkmoon:finding": [
        "finding_id", "campaign_id", "project_id", "target_id", "target",
        "title", "severity", "status", "category", "cve", "cvss_score",
        "cvss_vector", "mitre_attack_id", "mitre_attack_name", "iso27001_control",
        "endpoint", "technology", "plugin_or_component", "discovered_by_agent",
        "has_evidence", "contract_version", "event", "ts",
    ],
    "darkmoon:retest": [
        "retest_id", "base_campaign_id", "new_campaign_id", "finding_id",
        "title", "severity", "target", "base_status", "new_status", "verdict",
        "contract_version", "event", "ts",
    ],
    "darkmoon:pr": [
        "pr_id", "campaign_id", "provider", "repo", "number", "state",
        "confidence", "url", "contract_version", "event", "ts",
    ],
}
# Stats sub-object emitted as flat, safe numeric fields for campaigns.
CAMPAIGN_STAT_KEYS = ["total_findings", "critical", "high", "medium", "low",
                      "info", "exploited", "confirmed", "unconfirmed"]

# Fields promoted to HEC indexed fields for fast filtering (no secrets).
INDEX_FIELDS = ["campaign_id", "project_id", "target_id", "severity", "status",
                "verdict", "state", "event"]

SAFE_FIELDS["darkmoon:remediation"] = ["proposal_id", "campaign_id", "finding_id", "status", "confidence", "validated", "published", "event", "ts", "contract_version"]
BOOL_FIELDS = {"has_evidence", "validated", "published"}
NUMBER_FIELDS = {"duration_seconds", "cvss_score", "confidence", "number"}
CONTRACT_VERSION = "1"

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None

def open_request(request, context, timeout):
    return urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context)).open(request, timeout=timeout)

def checked_url(value, verify=True):
    """Reject unsafe URLs before attaching REST/HEC authorization headers.

    --insecure is an explicit lab-only escape hatch for plaintext HTTP as well
    as unverified HTTPS. TLS verification must never silently imply that an
    HTTP endpoint is acceptable.
    """
    if (not isinstance(value, str) or not value or len(value) > 8192
            or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise ValueError("Configure a URL without whitespace or control characters")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        # Accessing .port also rejects invalid numeric port declarations.
        parsed.port
    except ValueError:
        raise ValueError("Configure a valid HTTP(S) URL") from None
    if (parsed.scheme not in {"https", "http"} or not hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ValueError("Configure an HTTP(S) URL without credentials, query or fragment")
    if verify and parsed.scheme != "https":
        raise ValueError("HTTPS is required for authenticated REST/HEC requests; --insecure is lab-only")
    return value.rstrip("/")
_SECRET_RE = re.compile(
    r"(?i)(bearer\s+|(?:token|secret|password|api[_-]?key|authorization)"
    r"\"?\s*[:=]\s*\"?)([A-Za-z0-9._\-]{6,})")


def scrub(value):
    if isinstance(value, str):
        return _SECRET_RE.sub(lambda m: m.group(1) + "[REDACTED]", value)
    return value


def to_epoch(ts):
    if isinstance(ts, (int, float)) and not isinstance(ts, bool) and math.isfinite(ts):
        return float(ts)
    if isinstance(ts, str) and ts:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                import datetime
                return datetime.datetime.strptime(ts.replace("Z", "+0000"), fmt).timestamp()
            except Exception:
                continue
    return time.time()


def pick_safe(sourcetype, obj):
    """Return only allowlisted, scrubbed fields for the given sourcetype."""
    allowed = SAFE_FIELDS[sourcetype]
    out = {}
    for k in allowed:
        value = obj.get(k)
        if k in BOOL_FIELDS:
            if isinstance(value, bool): out[k] = value
        elif k in NUMBER_FIELDS:
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0: out[k] = value
        elif isinstance(value, str):
            if k in {"endpoint", "url", "target", "repo"}:
                method, separator, remainder = value.partition(" ")
                if separator and method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}: value = remainder.strip()
                value = value.split("?", 1)[0].split("#", 1)[0]
                try:
                    parsed = urlsplit(value)
                    if parsed.scheme in {"http", "https"}: value = urlunsplit((parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], parsed.path, "", ""))
                except ValueError: continue
            out[k] = scrub(value)
    out["contract_version"] = CONTRACT_VERSION
    return out


def campaign_event(c):
    status = str(c.get("status", "")).lower()
    ev = {"running": "campaign.started", "completed": "campaign.completed",
          "stopped": "campaign.stopped", "aborted": "campaign.aborted"}.get(status, "campaign.updated")
    obj = dict(c)
    obj["campaign_id"] = c.get("campaign_id") or c.get("id")
    obj["event"] = ev
    obj["ts"] = c.get("ts") or c.get("date") or c.get("finished_at") or ""
    safe = pick_safe("darkmoon:campaign", obj)
    stats = c.get("stats") if isinstance(c.get("stats"), dict) else {}
    for k in CAMPAIGN_STAT_KEYS:
        value = stats.get(k)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 and float(value).is_integer(): safe[k] = value
    return _envelope("darkmoon:campaign", safe, obj.get("ts"),
                     host=c.get("target") or "darkmoon")


def finding_event(f):
    status = str(f.get("status", "unconfirmed")).lower()
    ev = {"exploited": "finding.exploited", "confirmed": "finding.confirmed",
          "remediated": "finding.remediated"}.get(status, "finding.discovered")
    obj = dict(f)
    obj["finding_id"] = f.get("finding_id") or f.get("id")
    obj["event"] = ev
    obj["ts"] = f.get("ts") or f.get("discovered_at") or ""
    ev_obj = f.get("evidence")
    obj["has_evidence"] = bool(ev_obj) if not isinstance(ev_obj, bool) else ev_obj
    safe = pick_safe("darkmoon:finding", obj)
    return _envelope("darkmoon:finding", safe, obj.get("ts"),
                     host=f.get("target") or f.get("target_id") or "darkmoon")


def retest_event(r):
    obj = dict(r)
    obj["retest_id"] = r.get("retest_id") or r.get("id")
    obj["event"] = "retest.completed" if r.get("status") == "completed" else "retest.updated"
    obj["ts"] = r.get("ts") or ""
    safe = pick_safe("darkmoon:retest", obj)
    return _envelope("darkmoon:retest", safe, obj.get("ts"),
                     host=r.get("target") or "darkmoon")


def pr_event(p):
    obj = dict(p)
    published = p.get("published")
    number = p.get("number")
    actual_pr = published is True or published is None and isinstance(p.get("provider"), str) and bool(p["provider"]) and isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number) and number > 0
    if not actual_pr:
        obj["proposal_id"] = p.get("proposal_id") or p.get("id")
        linked = p.get("finding_ids")
        if isinstance(linked, list) and len(linked) == 1 and isinstance(linked[0], str): obj["finding_id"] = linked[0]
        obj["event"] = "remediation.updated"
        safe = pick_safe("darkmoon:remediation", obj)
        return _envelope("darkmoon:remediation", safe, p.get("ts"))
    obj["pr_id"] = p.get("pr_id") or p.get("id")
    obj["event"] = "pr.updated"
    obj["ts"] = p.get("ts") or ""
    safe = pick_safe("darkmoon:pr", obj)
    return _envelope("darkmoon:pr", safe, obj.get("ts"),
                     host=p.get("repo") or "darkmoon")


def _envelope(sourcetype, safe_event, ts, host="darkmoon"):
    # NOTE: we deliberately do NOT populate the HEC "fields" (indexed fields)
    # object. Every safe field already lives in the JSON "event" and is
    # extracted at search time via KV_MODE=json (props.conf). Promoting the same
    # keys to indexed fields would make them multivalued (indexed + extracted),
    # which breaks table/stats rendering. Search-time extraction is sufficient
    # for this app; INDEX_FIELDS is kept only for documentation.
    safe_event["event_id"] = hashlib.sha256(json.dumps([sourcetype, safe_event], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "time": to_epoch(ts),
        "host": scrub(host) if isinstance(host, str) else "darkmoon",
        "source": "darkmoon",
        "sourcetype": sourcetype,
        "event": safe_event,
    }


def build_events(data):
    if not isinstance(data, dict): raise ValueError("Export must be an object of typed record arrays")
    if not any(key in data for key in ("campaigns", "vulnerabilities", "retests", "pull_requests")): raise ValueError("Export has no recognized record arrays")
    events = []
    for key, convert in (("campaigns", campaign_event), ("vulnerabilities", finding_event), ("retests", retest_event), ("pull_requests", pr_event)):
        values = data.get(key, [])
        if not isinstance(values, list) or any(not isinstance(value, dict) for value in values): raise ValueError("Export contains an invalid record array")
        events.extend(convert(value) for value in values)
    return events


# --- input: REST poll -------------------------------------------------------
def _get_json(url, headers, verify, timeout=20):
    checked_url(url, verify)
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    with open_request(req, ctx, timeout) as r:
        body = r.read(32 * 1024 * 1024 + 1)
        if len(body) > 32 * 1024 * 1024: raise ValueError("REST response exceeds the size limit")
        return json.loads(body.decode("utf-8"))


def poll_rest(base_url, token, verify):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = {}
    base = checked_url(base_url, verify)
    if base.endswith("/api/v1"): base = base[:-7]
    for key, path in (("campaigns", "/api/v1/campaigns"),
                      ("vulnerabilities", "/api/v1/vulnerabilities"),
                      ("pull_requests", "/api/v1/pull-requests")):
        resp = _get_json(base + path, headers, verify)
        if not isinstance(resp, dict) or not isinstance(resp.get("data"), list): raise ValueError("REST response needs a data array")
        if any(not isinstance(row, dict) for row in resp["data"]): raise ValueError("REST response contains invalid records")
        data[key] = resp["data"]
    return data


# --- output: HEC ------------------------------------------------------------
def send_hec(hec_url, hec_token, events, verify, batch_size=100,
             max_retries=4, use_ack=False):
    checked_url(hec_url, verify)
    if batch_size < 1 or batch_size > 1000: raise ValueError("Batch size must be between 1 and 1000")
    if use_ack: raise ValueError("Indexer acknowledgment is not implemented; do not request it")
    channel = str(uuid.uuid4())
    headers = {"Authorization": "Splunk " + hec_token,
               "Content-Type": "application/json",
               "X-Splunk-Request-Channel": channel}
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    sent = 0
    for i in range(0, len(events), batch_size):
        batch = events[i:i + batch_size]
        body = "\n".join(json.dumps(e) for e in batch).encode("utf-8")
        delay = 1.0
        for attempt in range(max_retries + 1):
            try:
                req = urllib.request.Request(hec_url, data=body, headers=headers, method="POST")
                with open_request(req, ctx, 30) as r:
                    result = json.loads(r.read(1024 * 1024).decode("utf-8"))
                    if not isinstance(result, dict) or type(result.get("code")) is not int or result["code"] != 0: raise ValueError("HEC did not acknowledge successful admission")
                sent += len(batch)
                break
            except urllib.error.HTTPError as e:
                if 300 <= e.code < 500 and e.code != 429:
                    raise RuntimeError("HEC rejected the batch (HTTP %s)" % e.code) from None
                if attempt == max_retries:
                    raise
                time.sleep(delay); delay = min(delay * 2, 16) + (0.1 * attempt)
            except Exception:
                if attempt == max_retries:
                    raise
                time.sleep(delay); delay = min(delay * 2, 16)
    return sent


def main():
    ap = argparse.ArgumentParser(description="Ship SAFE Darkmoon events to Splunk HEC.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--rest-url", help="Darkmoon Pro base URL to poll")
    src.add_argument("--export", help="JSON export file {campaigns,vulnerabilities,...}")
    ap.add_argument("--token", default=os.environ.get("DARKMOON_TOKEN", ""),
                    help="Darkmoon API token (or env DARKMOON_TOKEN)")
    out = ap.add_mutually_exclusive_group(required=True)
    out.add_argument("--hec-url", help="Splunk HEC event endpoint URL")
    out.add_argument("--stdout", action="store_true", help="print envelopes, do not send")
    ap.add_argument("--hec-token", default=os.environ.get("SPLUNK_HEC_TOKEN", ""),
                    help="HEC token (or env SPLUNK_HEC_TOKEN)")
    ap.add_argument("--batch-size", type=int, default=100)
    ap.add_argument("--insecure", action="store_true",
                    help="allow HTTP and disable TLS verification (LAB ONLY)")
    args = ap.parse_args()
    verify = not args.insecure

    if args.export:
        with open(args.export, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data = poll_rest(args.rest_url, args.token, verify)

    events = build_events(data)

    if args.stdout:
        for e in events:
            print(json.dumps(e))
        sys.stderr.write("built %d safe events\n" % len(events))
        return

    if not args.hec_token:
        ap.error("--hec-token (or SPLUNK_HEC_TOKEN) is required with --hec-url")
    sent = send_hec(args.hec_url, args.hec_token, events, verify,
                    batch_size=args.batch_size)
    sys.stderr.write("sent %d/%d events to HEC\n" % (sent, len(events)))


if __name__ == "__main__":
    try: main()
    except Exception:
        sys.stderr.write("Darkmoon forwarding failed; no successful delivery is claimed. Check source access, format and HEC admission.\n")
        sys.exit(1)
