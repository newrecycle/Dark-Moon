#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
darkmoon-to-hec — ship SAFE Darkmoon events to a Splunk HTTP Event Collector.

This is the sender side for users who are NOT on the Darkmoon Pro webhook system.
Pro users can instead point a Darkmoon webhook (format=splunk_hec) directly at
HEC; see the repository README.

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
  * TLS verification is ON by default (use --insecure only in a trusted lab).

Standard library only. Python 3.8+.
"""

import argparse
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

CONTRACT_VERSION = "1"
_SECRET_RE = re.compile(
    r"(?i)(bearer\s+|(?:token|secret|password|api[_-]?key|authorization)"
    r"\"?\s*[:=]\s*\"?)([A-Za-z0-9._\-]{6,})")


def scrub(value):
    if isinstance(value, str):
        return _SECRET_RE.sub(lambda m: m.group(1) + "[REDACTED]", value)
    return value


def to_epoch(ts):
    if isinstance(ts, (int, float)):
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
        if k in obj and obj[k] is not None:
            out[k] = scrub(obj[k])
    out["contract_version"] = CONTRACT_VERSION
    return out


def campaign_event(c):
    status = str(c.get("status", "")).lower()
    ev = {"running": "campaign.started", "completed": "campaign.completed",
          "stopped": "campaign.stopped", "aborted": "campaign.aborted"}.get(status, "campaign.updated")
    obj = dict(c)
    obj["event"] = ev
    obj["ts"] = c.get("ts") or c.get("date") or c.get("finished_at") or ""
    safe = pick_safe("darkmoon:campaign", obj)
    stats = c.get("stats") or {}
    for k in CAMPAIGN_STAT_KEYS:
        if k in stats and stats[k] is not None:
            safe[k] = stats[k]
    return _envelope("darkmoon:campaign", safe, obj.get("ts"),
                     host=c.get("target") or "darkmoon")


def finding_event(f):
    status = str(f.get("status", "unconfirmed")).lower()
    ev = {"exploited": "finding.exploited", "confirmed": "finding.confirmed",
          "remediated": "finding.remediated"}.get(status, "finding.discovered")
    obj = dict(f)
    obj["event"] = ev
    obj["ts"] = f.get("ts") or f.get("discovered_at") or ""
    ev_obj = f.get("evidence")
    obj["has_evidence"] = bool(ev_obj) if not isinstance(ev_obj, bool) else ev_obj
    safe = pick_safe("darkmoon:finding", obj)
    return _envelope("darkmoon:finding", safe, obj.get("ts"),
                     host=f.get("target") or f.get("target_id") or "darkmoon")


def retest_event(r):
    obj = dict(r)
    obj["event"] = obj.get("event") or "retest.completed"
    obj["ts"] = r.get("ts") or ""
    safe = pick_safe("darkmoon:retest", obj)
    return _envelope("darkmoon:retest", safe, obj.get("ts"),
                     host=r.get("target") or "darkmoon")


def pr_event(p):
    obj = dict(p)
    obj["event"] = obj.get("event") or "pr.updated"
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
    return {
        "time": to_epoch(ts),
        "host": scrub(str(host)),
        "source": "darkmoon",
        "sourcetype": sourcetype,
        "event": safe_event,
    }


def build_events(data):
    events = []
    for c in data.get("campaigns", []) or []:
        events.append(campaign_event(c))
    for f in data.get("vulnerabilities", []) or []:
        events.append(finding_event(f))
    for r in data.get("retests", []) or []:
        events.append(retest_event(r))
    for p in data.get("pull_requests", []) or []:
        events.append(pr_event(p))
    return events


# --- input: REST poll -------------------------------------------------------
def _get_json(url, headers, verify, timeout=20):
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode("utf-8"))


def poll_rest(base_url, token, verify):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = {}
    base = base_url.rstrip("/")
    for key, path in (("campaigns", "/api/v1/campaigns"),
                      ("vulnerabilities", "/api/v1/vulnerabilities"),
                      ("pull_requests", "/api/v1/pull-requests")):
        try:
            resp = _get_json(base + path, headers, verify)
            data[key] = resp.get("data", []) if isinstance(resp, dict) else []
        except Exception as e:
            sys.stderr.write("poll %s failed: %s\n" % (path, e))
            data[key] = []
    return data


# --- output: HEC ------------------------------------------------------------
def send_hec(hec_url, hec_token, events, verify, batch_size=100,
             max_retries=4, use_ack=False):
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
                with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                    r.read()
                sent += len(batch)
                break
            except urllib.error.HTTPError as e:
                if e.code in (400, 403):   # non-retryable
                    sys.stderr.write("HEC rejected batch (HTTP %s), not retrying\n" % e.code)
                    break
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
                    help="disable TLS verification (LAB ONLY)")
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
    main()
