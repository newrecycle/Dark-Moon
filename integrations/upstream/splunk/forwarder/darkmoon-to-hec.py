#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
darkmoon-to-hec — ship SAFE Darkmoon events to a Splunk HTTP Event Collector.

This is the authenticated HEC sender for the independent fork.
Direct format=splunk_hec delivery from its signed-webhook dispatcher is not
supported. The vendor's direct HEC behavior remains unverified.

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
        "finding_id", "finding_key", "campaign_id", "project_id", "target_id", "target",
        "title", "severity", "status", "category", "cve", "cvss_score",
        "cvss_vector", "mitre_attack_id", "mitre_attack_name", "iso27001_control",
        "endpoint", "technology", "plugin_or_component", "discovered_by_agent",
        "has_evidence", "contract_version", "event", "ts",
    ],
    "darkmoon:retest": [
        "retest_id", "base_campaign_id", "new_campaign_id", "finding_id",
        "campaign_id", "target_id", "run_id", "status", "record_type",
        "current_finding_id", "finding_campaign_id", "finding_key",
        "title", "severity", "target", "base_status", "new_status", "verdict",
        "contract_version", "event", "ts",
    ],
    "darkmoon:pr": [
        "pr_id", "campaign_id", "provider", "repo", "number", "state",
        "confidence", "url", "finding_ids", "contract_version", "event", "ts",
    ],
}
# Stats sub-object emitted as flat, safe numeric fields for campaigns.
CAMPAIGN_STAT_KEYS = ["total_findings", "critical", "high", "medium", "low",
                      "info", "exploited", "confirmed", "unconfirmed"]

# Fields promoted to HEC indexed fields for fast filtering (no secrets).
INDEX_FIELDS = ["campaign_id", "project_id", "target_id", "severity", "status",
                "verdict", "state", "event"]

SAFE_FIELDS["darkmoon:remediation"] = ["proposal_id", "campaign_id", "finding_id", "finding_ids", "status", "confidence", "validated", "published", "event", "ts", "contract_version"]
BOOL_FIELDS = {"has_evidence", "validated", "published"}
NUMBER_FIELDS = {"duration_seconds", "cvss_score", "confidence", "number"}
CONTRACT_VERSION = "1"
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}\Z")


def record_id(row, key, alias="id"):
    values = [row[field] for field in (key, alias) if row.get(field) is not None]
    if not values or any(not isinstance(value, str) or not _ID_RE.fullmatch(value) for value in values):
        raise ValueError("Record needs a valid string identity")
    if any(value != values[0] for value in values):
        raise ValueError("Record identity aliases disagree")
    return values[0]


def linked_ids(value):
    if not isinstance(value, list) or len(value) > 1000 or any(not isinstance(v, str) or not _ID_RE.fullmatch(v) for v in value):
        raise ValueError("Finding links must be a bounded string-ID array")
    return sorted(set(value))

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
            or "\\" in value or "?" in value or "#" in value
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


def safe_locator(value):
    """Strip URL credentials, query and fragment before using a location as an event field or host."""
    if not isinstance(value, str):
        return ""
    method, separator, remainder = value.partition(" ")
    if separator and method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        value = remainder.strip()
    value = value.split("?", 1)[0].split("#", 1)[0]
    try:
        parsed = urlsplit(value)
        if parsed.scheme and parsed.scheme not in {"http", "https"} and "://" in value:
            return ""
        if parsed.netloc:
            if not parsed.hostname:
                return ""
            hostname = parsed.hostname
            if ":" in hostname and not hostname.startswith("["):
                hostname = "[" + hostname + "]"
            netloc = hostname + ((":" + str(parsed.port)) if parsed.port is not None else "")
            value = urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
        elif "@" in value:
            return ""
    except ValueError:
        return ""
    return scrub(value)


def to_epoch(ts):
    if isinstance(ts, (int, float)) and not isinstance(ts, bool) and math.isfinite(ts):
        return float(ts)
    if isinstance(ts, str) and ts:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                import datetime
                parsed = datetime.datetime.strptime(ts.replace("Z", "+0000"), fmt)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=datetime.timezone.utc)
                return parsed.timestamp()
            except Exception:
                continue
    return time.time()


def pick_safe(sourcetype, obj):
    """Return only allowlisted, scrubbed fields for the given sourcetype."""
    allowed = SAFE_FIELDS[sourcetype]
    out = {}
    for k in allowed:
        value = obj.get(k)
        if k == "finding_ids" and value is not None:
            out[k] = linked_ids(value)
        elif k in BOOL_FIELDS:
            if isinstance(value, bool): out[k] = value
        elif k in NUMBER_FIELDS:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
                continue
            if k == "cvss_score" and value > 10 or k == "confidence" and value > 1:
                continue
            if k == "number" and (value <= 0 or not float(value).is_integer()):
                continue
            out[k] = value
        elif isinstance(value, str):
            if k in {"endpoint", "url", "target", "repo"}:
                out[k] = safe_locator(value)
            else:
                out[k] = scrub(value)
    out["contract_version"] = CONTRACT_VERSION
    return out


def campaign_event(c):
    status = str(c.get("status", "")).lower()
    ev = {"running": "campaign.started", "completed": "campaign.completed",
          "stopped": "campaign.stopped", "aborted": "campaign.aborted"}.get(status, "campaign.updated")
    obj = dict(c)
    obj["campaign_id"] = record_id(c, "campaign_id")
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
    for key in ("severity", "status"):
        if not isinstance(obj.get(key), str) or not obj[key]:
            obj[key] = "unknown"
    obj["finding_id"] = record_id(f, "finding_id")
    campaign = f.get("campaign_id")
    if campaign is not None and (not isinstance(campaign, str) or not _ID_RE.fullmatch(campaign)):
        raise ValueError("Finding campaign reference must be a string identity")
    obj["finding_key"] = (campaign or "legacy") + "::" + obj["finding_id"]
    obj["event"] = ev
    obj["ts"] = f.get("ts") or f.get("discovered_at") or ""
    ev_obj = f.get("evidence")
    obj["has_evidence"] = bool(ev_obj) if not isinstance(ev_obj, bool) else ev_obj
    safe = pick_safe("darkmoon:finding", obj)
    return _envelope("darkmoon:finding", safe, obj.get("ts"),
                     host=f.get("target") or f.get("target_id") or "darkmoon")


def retest_event(r):
    obj = dict(r)
    obj["retest_id"] = record_id(r, "retest_id")
    for key in ("base_campaign_id", "new_campaign_id", "campaign_id", "target_id", "run_id"):
        value = r.get(key)
        if value is not None and (not isinstance(value, str) or not _ID_RE.fullmatch(value)):
            raise ValueError("Retest needs exact string references")
    if r.get("campaign_id") and r.get("new_campaign_id") and r["campaign_id"] != r["new_campaign_id"]:
        raise ValueError("Retest campaign aliases disagree")
    obj["new_campaign_id"] = r.get("new_campaign_id") or r.get("campaign_id")
    status = r.get("status", "unknown")
    if not isinstance(status, str) or not status or status != status.strip() or len(status) > 80:
        raise ValueError("Retest needs a lifecycle state")
    obj["status"] = status
    obj["record_type"] = "comparison" if r.get("finding_id") is not None else "lifecycle"
    if obj["record_type"] == "comparison":
        obj["finding_id"] = record_id(r, "finding_id", "finding_id")
        if not isinstance(r.get("verdict"), str) or not r["verdict"] or len(r["verdict"]) > 80:
            raise ValueError("Retest comparison needs a verdict")
        current = r.get("current_finding_id")
        if current is not None and (not isinstance(current, str) or not _ID_RE.fullmatch(current)):
            raise ValueError("Retest current finding reference is invalid")
        finding_campaign = obj["new_campaign_id"] if r["verdict"] == "new" else r.get("base_campaign_id")
        obj["finding_campaign_id"] = finding_campaign
        obj["finding_key"] = (finding_campaign or "legacy") + "::" + obj["finding_id"]
    obj["event"] = "retest.completed" if r.get("status") == "completed" else "retest.updated"
    obj["ts"] = r.get("ts") or r.get("finished_at") or r.get("created_at") or ""
    safe = pick_safe("darkmoon:retest", obj)
    return _envelope("darkmoon:retest", safe, obj.get("ts"),
                     host=r.get("target") or "darkmoon")


def retest_events(record):
    """Preserve lifecycle even with zero comparisons; flatten only typed rows."""
    arrays = [record[key] for key in ("findings", "verdicts") if key in record]
    if any(not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows) for rows in arrays):
        raise ValueError("Retest comparisons need typed arrays")
    if len(arrays) == 2 and arrays[0] != arrays[1]:
        raise ValueError("Retest comparison aliases disagree")
    if record.get("finding_id") is not None:
        if arrays:
            raise ValueError("Do not mix flat and aggregate retest shapes")
        return [retest_event(record)]
    if not arrays and record.get("status") == "completed":
        raise ValueError("Completed retest is missing comparison results")
    events = [retest_event(record)]
    seen = set()
    for comparison in arrays[0] if arrays else []:
        for key in ("retest_id", "base_campaign_id", "new_campaign_id", "target_id", "run_id"):
            if comparison.get(key) is not None and comparison[key] != record.get(key):
                raise ValueError("Retest comparison has a conflicting parent reference")
        row = {key: value for key, value in record.items() if key not in {"findings", "verdicts"}}
        for key in ("finding_id", "current_finding_id", "title", "severity", "base_status", "new_status", "verdict"):
            if key in comparison:
                value = comparison[key]
                if value is not None and not isinstance(value, str):
                    raise ValueError("Retest comparison metadata must be strings")
                row[key] = value
        if not comparison.get("finding_id") or not comparison.get("verdict"):
            raise ValueError("Retest comparison is missing identity or verdict")
        event = retest_event(row)
        key = event["event"]["finding_key"]
        if key in seen:
            raise ValueError("Retest contains duplicate comparison identities")
        seen.add(key)
        events.append(event)
    return events


def pr_event(p):
    obj = dict(p)
    published = p.get("published")
    number = p.get("number")
    actual_pr = published is True or published is None and isinstance(p.get("provider"), str) and bool(p["provider"]) and isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number) and number > 0
    if not actual_pr:
        obj["proposal_id"] = record_id(p, "proposal_id")
        linked = p.get("finding_ids")
        if isinstance(linked, list) and len(linked) == 1 and isinstance(linked[0], str): obj["finding_id"] = linked[0]
        obj["event"] = "remediation.updated"
        safe = pick_safe("darkmoon:remediation", obj)
        return _envelope("darkmoon:remediation", safe, p.get("ts"))
    # Fork records use id for the local record; pr_id can be the numeric SCM
    # number. Never drop that record's identity or join different repositories.
    obj["pr_id"] = record_id({"id": p.get("id") or p.get("pr_id")}, "id")
    if not isinstance(obj.get("state"), str) or not obj["state"]:
        obj["state"] = "unknown"
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
        "host": safe_locator(host) or "darkmoon",
        "source": "darkmoon",
        "sourcetype": sourcetype,
        "event": safe_event,
    }


def build_events(data):
    if not isinstance(data, dict): raise ValueError("Export must be an object of typed record arrays")
    if not any(key in data for key in ("campaigns", "vulnerabilities", "retests", "pull_requests")): raise ValueError("Export has no recognized record arrays")
    targets = data.get("targets", [])
    if not isinstance(targets, list) or any(not isinstance(row, dict) for row in targets):
        raise ValueError("Target metadata needs an array of objects")
    hosts = {}
    for row in targets:
        target_id = record_id({"id": row.get("id")}, "id")
        if target_id in hosts:
            raise ValueError("Target metadata contains duplicate identities")
        location = row.get("host") or row.get("ip")
        hosts[target_id] = safe_locator(location)
    def referenced(row):
        row = dict(row)
        target_id = row.get("target_id")
        if isinstance(target_id, str) and hosts.get(target_id):
            row["target"] = hosts[target_id]
        return row
    events = []
    for key, convert in (("campaigns", campaign_event), ("vulnerabilities", finding_event), ("retests", retest_event), ("pull_requests", pr_event)):
        values = data.get(key, [])
        if not isinstance(values, list) or any(not isinstance(value, dict) for value in values): raise ValueError("Export contains an invalid record array")
        if key == "retests":
            for record in values:
                events.extend(retest_events(referenced(record)))
        else:
            events.extend(convert(referenced(value)) for value in values)
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
    base = checked_url(base_url, verify=verify)
    if base.endswith("/api/v1"): base = base[:-7]
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = {}
    for key, path in (("campaigns", "/api/v1/campaigns"),
                      ("vulnerabilities", "/api/v1/vulnerabilities"),
                      ("pull_requests", "/api/v1/pull-requests"),
                      ("retests", "/api/v1/retest"),
                      ("targets", "/api/v1/targets")):
        resp = _get_json(base + path, headers, verify)
        if not isinstance(resp, dict) or not isinstance(resp.get("data"), list): raise ValueError("REST response needs a data array")
        if any(not isinstance(row, dict) for row in resp["data"]): raise ValueError("REST response contains invalid records")
        data[key] = resp["data"]
    return data


# --- output: HEC ------------------------------------------------------------
class HECAdmissionError(ValueError):
    """Explicit HEC response rejection: replaying the batch cannot fix its data."""


def send_hec(hec_url, hec_token, events, verify, batch_size=100,
             max_retries=4, use_ack=False):
    checked_url(hec_url, verify=verify)
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise ValueError("Batch size must be an integer between 1 and 1000")
    if type(max_retries) is not int or not 0 <= max_retries <= 10:
        raise ValueError("max_retries must be an integer between 0 and 10")
    if not isinstance(hec_token, str) or not hec_token or len(hec_token) > 16384 or hec_token != hec_token.strip() or any(ord(ch) < 32 or ord(ch) == 127 for ch in hec_token):
        raise ValueError("HEC authentication is required")
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
                    try:
                        raw = r.read(1024 * 1024 + 1)
                        if len(raw) > 1024 * 1024:
                            raise HECAdmissionError("HEC admission response exceeds the size limit")
                        result = json.loads(raw.decode("utf-8"))
                    except (UnicodeError, ValueError):
                        raise HECAdmissionError("HEC returned an invalid admission response") from None
                    if not isinstance(result, dict) or type(result.get("code")) is not int or result["code"] != 0:
                        raise HECAdmissionError("HEC did not acknowledge successful admission")
                sent += len(batch)
                break
            except HECAdmissionError as exc:
                raise ValueError(str(exc)) from None
            except urllib.error.HTTPError as e:
                if 300 <= e.code < 500 and e.code != 429:
                    raise RuntimeError("HEC rejected the batch (HTTP %s)" % e.code) from None
                if attempt == max_retries:
                    raise RuntimeError("HEC delivery failed; earlier batches or uncertain retries may already have been admitted") from None
                time.sleep(delay); delay = min(delay * 2, 16) + (0.1 * attempt)
            except Exception:
                if attempt == max_retries:
                    raise RuntimeError("HEC delivery failed; earlier batches or uncertain retries may already have been admitted") from None
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
    try: main()
    except Exception:
        sys.stderr.write("Darkmoon forwarding failed; earlier batches or uncertain retries may already have been admitted. Check source access, format and HEC admission.\n")
        sys.exit(1)
