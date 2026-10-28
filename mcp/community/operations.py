"""Assessment analytics, comparative retests and signed webhook delivery."""
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import re
import secrets
import socket
import ssl
import threading
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlsplit

from api import json_storage as data
from .store import identifier, now

WEBHOOK_RECEIPT_TTL = 86400
MAX_WEBHOOK_RECEIPTS = 5000
WEBHOOK_TEST_COOLDOWN = 60
MAX_PENDING_TESTS_PER_HOOK = 3
MAX_PENDING_DELIVERIES = 1000


class WebhookReceiptCapacityError(Exception):
    def __init__(self, retry_after):
        super().__init__("Webhook receipt journal is full; retry after existing receipts expire")
        self.retry_after = max(1, int(retry_after))


class WebhookTestConflictError(Exception):
    pass


class WebhookTestRateLimitError(Exception):
    def __init__(self, retry_after=60):
        self.retry_after = max(1, min(3600, int(retry_after)))


SAFE_FINDING_FIELDS = ("id", "campaign_id", "project_id", "target_id", "severity", "status", "category", "cve",
                       "mitre_attack_id", "iso27001_control", "discovered_at", "discovered_by_agent", "node_id", "cvss_score")


def safe_finding(finding):
    return {key: finding[key] for key in SAFE_FINDING_FIELDS if key in finding}


def evidence_meta(finding):
    evidence = finding.get("evidence") or {}
    evidence = evidence if isinstance(evidence, dict) else {"logs": [evidence]}
    counts = {key: len(evidence.get(key) or []) for key in ("commands", "payloads", "screenshots", "logs")}
    counts["requests"] = int(bool(evidence.get("raw_request")))
    return {"vuln_id": finding.get("id"), "has_evidence": any(bool(v) for v in evidence.values()), "counts": counts,
            "command_names": [], "has_screenshot": bool(evidence.get("screenshots")),
            "has_extracted_data": bool(evidence.get("extracted_data")), "redacted": True}


def overview(campaigns=None):
    campaigns = data.load_campaigns() if campaigns is None else campaigns
    ids = {c["id"] for c in campaigns}
    findings = [v for v in data.load_all_vulnerabilities() if v.get("campaign_id") in ids]
    severity = Counter(str(v.get("severity", "info")).lower() for v in findings)
    status = Counter(str(v.get("status", "unconfirmed")).lower() for v in findings)
    return {"projects_count": len({c.get("project_id") for c in campaigns}),
            "targets_count": len({c.get("target_id") for c in campaigns}), "campaigns_count": len(campaigns),
            "total_vulnerabilities": len(findings), "severity_distribution": dict(severity),
            "status_distribution": dict(status), "category_distribution": dict(Counter(v.get("category", "unknown") for v in findings))}


def timeseries(query):
    metric, group = query.get("metric", "severity"), query.get("group", "day")
    if metric not in {"severity", "status", "category", "findings", "campaigns"} or group not in {"hour", "day", "week", "month"}:
        raise ValueError("Invalid metric/group")
    campaigns = [c for c in data.load_campaigns() if all(not query.get(key) or c.get(key) == query[key] for key in ("project_id", "target_id"))]
    series = defaultdict(lambda: defaultdict(int))
    for campaign in campaigns:
        try:
            timestamp = datetime.fromisoformat(campaign.get("date", "").replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            continue
        if query.get("from") and timestamp < datetime.fromisoformat(query["from"].replace("Z", "+00:00")):
            continue
        if query.get("to") and timestamp > datetime.fromisoformat(query["to"].replace("Z", "+00:00")):
            continue
        key = timestamp.strftime({"hour": "%Y-%m-%dT%H:00:00Z", "day": "%Y-%m-%dT00:00:00Z", "week": "%G-W%V", "month": "%Y-%m-01T00:00:00Z"}[group])
        if metric == "campaigns":
            series["campaigns"][key] += 1
        else:
            for finding in data.load_vulnerabilities(campaign["id"]):
                series[str(finding.get(metric, "unknown")) if metric != "findings" else "findings"][key] += 1
    return {"metric": metric, "group": group, "series": [{"key": key, "points": [{"t": t, "value": n} for t, n in sorted(points.items())]}
                                                             for key, points in sorted(series.items())]}


def fingerprint(finding):
    return tuple(str(finding.get(key, "")).strip().lower() for key in ("category", "endpoint", "plugin_or_component", "title"))


def compare_retest(before, after):
    old, new = {fingerprint(v): v for v in before}, {fingerprint(v): v for v in after}
    rows = []
    for key, finding in old.items():
        rows.append({"finding_id": finding.get("id"), "verdict": "still_present" if key in new else "not_observed",
                     "current_finding_id": new.get(key, {}).get("id"), "severity": finding.get("severity"),
                     "basis": "assessment comparison; absence is not an exploit-retest proof"})
    rows.extend({"finding_id": finding.get("id"), "verdict": "new", "severity": finding.get("severity")}
                for key, finding in new.items() if key not in old)
    return rows


def signed_headers(secret, body, event_id, timestamp=None):
    timestamp = str(int(timestamp or time.time()))
    message = timestamp.encode() + b"." + event_id.encode() + b"." + body
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return {"Content-Type": "application/json", "X-Darkmoon-Event-Id": event_id, "X-Darkmoon-Timestamp": timestamp,
            "X-Darkmoon-Signature": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
            "X-Darkmoon-Signature-V2": "sha256=" + signature}


def verify_delivery(secret, body, headers, seen, clock=None, tolerance=300):
    try:
        timestamp, event_id = headers["X-Darkmoon-Timestamp"], headers["X-Darkmoon-Event-Id"]
        if abs((clock or time.time())-int(timestamp)) > tolerance or event_id in seen:
            return False
        expected = signed_headers(secret, body, event_id, int(timestamp))["X-Darkmoon-Signature-V2"]
        if not hmac.compare_digest(expected, headers.get("X-Darkmoon-Signature-V2", "")):
            return False
        seen.add(event_id)
        return True
    except (KeyError, ValueError, TypeError):
        return False


def webhook_url(url):
    """Validate syntax; DNS and transport security are checked at delivery time."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Webhook requires an HTTPS URL without credentials/fragment")
    if parsed.port == 0:
        raise ValueError("Invalid webhook port")
    return parsed


def safe_webhook(hook):
    """Shared public metadata projection: redact full paths, tokens, and vault references."""
    try:
        parsed = webhook_url(str(hook.get("url", "")))
        host = parsed.hostname
        if ":" in host:
            host = "[" + host + "]"
        origin = "https://" + host + (":" + str(parsed.port) if parsed.port else "")
    except (ValueError, TypeError):
        origin = None
    return {"id": hook.get("id"), "url": origin, "url_redacted": True,
            "events": list(hook.get("events", [])) if isinstance(hook.get("events"), list) else [],
            "enabled": hook.get("enabled") is True, "format": hook.get("format", "darkmoon"),
            "created_at": hook.get("created_at")}


def safe_webhook_delivery(record):
    """No response bodies, raw events, sensitive destinations or stored error text."""
    event = record.get("event") if isinstance(record.get("event"), dict) else {}
    result = {k: record[k] for k in ("id", "webhook_id", "status", "attempts", "next_attempt", "http_status") if k in record}
    result.update(event_id=event.get("id"), event=event.get("event"), synthetic=event.get("synthetic") is True)
    if record.get("error"):
        result["error"] = "Delivery failed; destination or network unavailable"
    return result


def deliver_https(url, body, headers):
    parsed = webhook_url(url)
    allowed = {host.strip().lower() for host in os.environ.get("DARKMOON_WEBHOOK_ALLOWED_HOSTS", "").split(",") if host.strip()}
    addresses = {r[4][0] for r in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
    if not addresses or (parsed.hostname.lower() not in allowed and any(not ipaddress.ip_address(a).is_global for a in addresses)):
        raise ValueError("Webhook resolves to a non-public address; explicitly allow the configured internal hostname")
    address = sorted(addresses)[0]
    connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, context=ssl.create_default_context(), timeout=10)
    # Pin the approved DNS result while retaining the original TLS SNI/hostname.
    connection._create_connection = lambda ignored, timeout, source_address=None: socket.create_connection((address, parsed.port or 443), timeout, source_address)
    try:
        connection.request("POST", parsed.path + ("?"+parsed.query if parsed.query else ""), body, headers)
        response = connection.getresponse()
        response.read(4096)
        return response.status
    finally:
        connection.close()


class Operations:
    def __init__(self, service, transport=deliver_https):
        self.service, self.store, self.transport = service, service.store, transport
        self.stop = threading.Event()
        self.thread = None
        self.observed = {}
        self.initialized = False

    @staticmethod
    def _delivery(hook_id, event):
        return {"id": "delivery_" + uuid.uuid4().hex, "webhook_id": hook_id, "event": event,
                "attempts": 0, "next_attempt": time.time(), "status": "pending"}

    def emit(self, event, payload):
        safe = {k: payload[k] for k in ("campaign_id", "run_id", "finding_id", "severity", "status", "retest_id", "pr_id", "state", "provider") if k in payload}
        item = {"id": "evt_" + uuid.uuid4().hex, "event": event, "timestamp": now(), "data": safe}
        def append(state):
            state["event_seq"] = state.get("event_seq", 0)+1
            item.update(seq=state["event_seq"], ts=item["timestamp"], contract_version="1")
            state.setdefault("events", {})[item["id"]] = item
        self.store.update(append)
        def trim(state):
            events = state.setdefault("events", {})
            while len(events) > 1000:
                events.pop(next(iter(events)))
        self.store.update(trim)
        for hook in self.store.items("webhooks"):
            if hook.get("enabled") and (not hook.get("events") or event in hook["events"] or "*" in hook["events"]):
                delivery = self._delivery(hook["id"], item)
                self.store.save("deliveries", delivery)
        return item

    def register(self, raw):
        if raw.get("format", "darkmoon") != "darkmoon":
            raise ValueError("This producer supports signed darkmoon webhooks only; use the authenticated Splunk HEC forwarder for HEC delivery")
        webhook_url(str(raw.get("url", "")))
        events = raw.get("events", [])
        if not isinstance(events, list) or not all(isinstance(e, str) and len(e) <= 100 for e in events):
            raise ValueError("events must be a string array")
        secret = raw.get("secret") or secrets.token_urlsafe(32)
        if not isinstance(secret, str) or len(secret) < 24:
            raise ValueError("Webhook secret must contain at least 24 characters")
        # Persist the signing key as internal in the same write: concurrent
        # /credentials and /options readers must never see a selectable key.
        key = self.service.vault.save(
            {"name": "Webhook signing", "provider": "webhook", "secret": secret},
            internal=True,
        )
        hook = {"id": "hook_" + uuid.uuid4().hex[:16], "url": raw["url"], "events": events,
                "credential_ref": key["id"], "enabled": True, "created_at": now(), "format": "darkmoon"}
        self.store.save("webhooks", hook)
        # Caller-supplied secrets are never echoed. Generated secrets are
        # returned once to the registering admin so receivers can verify them.
        return safe_webhook(hook) | ({"secret": secret} if not raw.get("secret") else {})

    def test_webhook(self, webhook_id):
        """Atomically enqueue a targeted synthetic event; never contact a destination."""
        webhook_id = identifier(webhook_id)
        clock = time.time()

        def enqueue(state):
            hook = state.get("webhooks", {}).get(webhook_id)
            if not hook:
                raise KeyError(webhook_id)
            if hook.get("enabled") is not True:
                raise WebhookTestConflictError("Webhook is disabled")
            if hook.get("credential_ref") not in state.get("credentials", {}):
                raise WebhookTestConflictError("Signing configuration is unavailable")
            limits = state.setdefault("webhook_test_last", {})
            previous = limits.get(webhook_id)
            if isinstance(previous, (int, float)) and clock - previous < WEBHOOK_TEST_COOLDOWN:
                raise WebhookTestRateLimitError(WEBHOOK_TEST_COOLDOWN - (clock - previous) + 1)
            deliveries = state.setdefault("deliveries", {})
            pending = [d for d in deliveries.values() if d.get("status") == "pending"]
            if len(pending) >= MAX_PENDING_DELIVERIES:
                raise WebhookTestRateLimitError()
            if sum(d.get("webhook_id") == webhook_id and isinstance(d.get("event"), dict) and
                   d["event"].get("synthetic") is True for d in pending) >= MAX_PENDING_TESTS_PER_HOOK:
                raise WebhookTestRateLimitError()
            event_id, timestamp = "evt_test_" + uuid.uuid4().hex, now()
            event = {"id": event_id, "event": "webhook.test", "timestamp": timestamp, "ts": timestamp,
                     "contract_version": "1", "synthetic": True,
                     "data": {"synthetic": True, "purpose": "delivery_validation"}}
            delivery = self._delivery(webhook_id, event)
            deliveries[delivery["id"]] = delivery
            limits[webhook_id] = clock
            return {"accepted": True, "delivery_id": delivery["id"], "event_id": event_id, "status": "pending"}

        return self.store.update(enqueue)

    def claim_webhook_event(self, webhook_id, event_id, clock=None):
        """Durable at-most-once receiver admission; never evict fresh receipts."""
        identifier(webhook_id)
        if not isinstance(event_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", event_id):
            raise ValueError("event_id must contain 1 to 200 letters, digits, underscores or hyphens")
        timestamp = time.time() if clock is None else clock
        def claim(state):
            hook = state.get("webhooks", {}).get(webhook_id)
            if not hook: raise KeyError(webhook_id)
            if not hook.get("enabled"): raise PermissionError("Webhook is disabled")
            journals = state.setdefault("webhook_receipts", {})
            current = {key: value for key, value in journals.get(webhook_id, {}).items()
                       if isinstance(value, (int, float)) and value > timestamp - WEBHOOK_RECEIPT_TTL}
            if event_id in current:
                journals[webhook_id] = current
                return {"webhook_id":webhook_id, "event_id":event_id, "claimed":False}
            if len(current) >= MAX_WEBHOOK_RECEIPTS:
                raise WebhookReceiptCapacityError(min(current.values()) + WEBHOOK_RECEIPT_TTL - timestamp + 1)
            current[event_id] = timestamp
            journals[webhook_id] = current
            return {"webhook_id":webhook_id, "event_id":event_id, "claimed":True}
        return self.store.update(claim)

    def launch_retest(self, raw):
        campaign = data.load_campaign(identifier(raw.get("campaign_id"))) if raw.get("campaign_id") else None
        if raw.get("campaign_id") and not campaign:
            # An exact base must never degrade to another campaign on a target.
            raise KeyError("Base campaign")
        if campaign and raw.get("target_id") and identifier(raw["target_id"]) != campaign.get("target_id"):
            raise ValueError("Base campaign does not belong to the requested target")
        if not campaign and raw.get("target_id"):
            reference = str(raw["target_id"])
            targets = {t["id"] for t in data.load_targets() if reference in (t["id"], t.get("host"), t.get("ip"))}
            campaign = next((c for c in reversed(data.load_campaigns()) if c.get("target_id") in targets), None)
        if not campaign:
            raise KeyError("Base campaign")
        target = data.load_target(campaign["target_id"])
        if not target:
            raise KeyError("Saved target")
        selected = raw.get("finding_ids", [])
        if not isinstance(selected, list) or any(not isinstance(x, str) for x in selected):
            raise ValueError("finding_ids must be a string array")
        findings = data.load_vulnerabilities(campaign["id"])
        before = [v for v in findings if not selected or v.get("id") in selected]
        if selected and set(selected) - {v.get("id") for v in before}:
            raise ValueError("A selected finding is not in the base campaign")
        original = next((j.get("spec", {}) for j in reversed(self.store.items("jobs")) if j.get("campaign_id") == campaign["id"]), {})
        scope = campaign.get("scope") or {}
        spec = {k: original[k] for k in ("assessment_credential_id", "assessment_token_id") if original.get(k)}
        spec.update({k: scope.get(k, original.get(k, [] if k in {"targets", "out_of_scope"} else ""))
                     for k in ("targets", "out_of_scope", "rules", "safe_harbor", "safe_harbor_applies")})
        # Preserve the original engagement boundaries; an integration may add
        # restrictions, but does not erase the earlier safe-harbor terms.
        if raw.get("safe_harbor"):
            if not isinstance(raw["safe_harbor"], str):
                raise ValueError("safe_harbor must be text")
            spec["safe_harbor"] = (spec["safe_harbor"]+"\n"+raw["safe_harbor"]).strip()
        spec.update(target=original.get("target") or target.get("host") or target.get("ip"),
                    name="Retest: " + campaign.get("name", campaign["id"]),
                    focus=",".join(sorted({str(v.get("category", "")) for v in before if v.get("category")})))
        job = self.service.launch(spec)
        record = {"id": "retest_" + uuid.uuid4().hex[:16], "retest_id": "", "base_campaign_id": campaign["id"],
                  "campaign_id": job["campaign_id"], "new_campaign_id": job["campaign_id"], "target_id": campaign["target_id"], "run_id": job["id"],
                  "before_ids": [v.get("id") for v in before], "status": "running", "created_at": now(), "verdicts": []}
        record["retest_id"] = record["id"]
        self.store.save("retests", record)
        return record

    def tick(self):
        snapshot = self.service.snapshot()
        if not self.initialized:
            self.observed = {"campaign:"+c["id"]: c.get("status") for c in snapshot["campaigns"]}
            self.observed.update({"finding:"+str(v.get("id")): v.get("status") for v in snapshot["findings"]})
            self.observed.update({"proposal:"+p["id"]: (p.get("status"), bool(p.get("published"))) for p in snapshot["remediations"]})
            self.initialized = True
        for campaign in snapshot["campaigns"]:
            key, value = "campaign:"+campaign["id"], campaign.get("status")
            if key not in self.observed or self.observed[key] != value:
                self.emit("campaign.updated", {"campaign_id": campaign["id"], "status": value})
                event = {"running": "campaign.started", "completed": "campaign.completed", "failed": "campaign.aborted", "aborted": "campaign.aborted", "stopped": "campaign.stopped"}.get(value)
                if event:
                    self.emit(event, {"campaign_id": campaign["id"], "status": value})
            self.observed[key] = value
        for finding in snapshot["findings"]:
            key = "finding:"+str(finding.get("id"))
            if key not in self.observed:
                self.emit("finding.created", {"finding_id": finding.get("id"), "campaign_id": finding.get("campaign_id"),
                                              "severity": finding.get("severity"), "status": finding.get("status")})
                self.emit("finding.discovered", {"finding_id": finding.get("id"), "campaign_id": finding.get("campaign_id"),
                                                  "severity": finding.get("severity"), "status": finding.get("status")})
            if self.observed.get(key) != finding.get("status") and finding.get("status") in {"confirmed", "exploited", "remediated"}:
                self.emit("finding."+finding["status"], {"finding_id": finding.get("id"), "campaign_id": finding.get("campaign_id"),
                                                        "severity": finding.get("severity"), "status": finding.get("status")})
            self.observed[key] = finding.get("status")
        for proposal in snapshot["remediations"]:
            key = "proposal:"+proposal["id"]
            state = (proposal.get("status"), bool(proposal.get("published")))
            previous = self.observed.get(key)
            if previous != state:
                event = ("pr.opened" if not previous or not previous[1] else "pr.updated") if state[1] else "remediation.updated"
                self.emit(event, {"pr_id": proposal["id"], "campaign_id": proposal.get("campaign_id"), "state": state[0]})
                self.observed[key] = state
        for record in self.store.items("retests"):
            if record["status"] != "running":
                continue
            campaign = data.load_campaign(record["campaign_id"]) or {}
            if campaign.get("status") == "completed":
                before = [v for v in data.load_vulnerabilities(record["base_campaign_id"]) if v.get("id") in record["before_ids"]]
                record.update(status="completed", verdicts=compare_retest(before, data.load_vulnerabilities(record["campaign_id"])), finished_at=now())
                # A validated local worktree is not proof that a patch was
                # deployed to this target. Preserve the comparison verdict;
                # even a same-campaign proposal cannot establish a live fix.
                record["findings"] = record["verdicts"]
                record["verdicts_summary"] = dict(Counter(v["verdict"] for v in record["verdicts"]))
                self.store.save("retests", record)
                self.emit("retest.completed", {"retest_id": record["id"], "campaign_id": record["campaign_id"], "status": "completed"})
            elif campaign.get("status") not in {"running", "queued", None}:
                record.update(status="incomplete", finished_at=now())
                self.store.save("retests", record)
        for delivery in self.store.items("deliveries"):
            if delivery["status"] != "pending" or delivery["next_attempt"] > time.time():
                continue
            hook = self.store.get("webhooks", delivery["webhook_id"])
            if not hook or not hook["enabled"]:
                delivery["status"] = "cancelled"
            else:
                delivery["attempts"] += 1
                try:
                    body = json.dumps(delivery["event"] | {"delivery_id": delivery["id"]}, separators=(",", ":")).encode()
                    headers = signed_headers(self.service.vault.resolve(hook["credential_ref"]), body, delivery["event"]["id"])
                    status = self.transport(hook["url"], body, headers)
                    delivery.update(http_status=status, status="delivered" if 200 <= status < 300 else "pending")
                except Exception:
                    delivery.update(status="pending", error="Delivery failed; destination or network unavailable")
                if delivery["status"] == "pending":
                    delivery["status"] = "failed" if delivery["attempts"] >= 5 else "pending"
                    delivery["next_attempt"] = time.time() + min(3600, 2 ** delivery["attempts"] * 10)
            self.store.save("deliveries", delivery)

    def start(self):
        def loop():
            guard_checked = 0
            while not self.stop.is_set():
                try:
                    self.tick()
                    if os.environ.get("DARKMOON_GUARD_ENFORCE") == "1" and time.monotonic()-guard_checked > 30:
                        from .integrity import verify
                        if not verify(self.service.queue.repo, self.store)["ok"]:
                            self.service.queue.stop_event.set()
                        guard_checked = time.monotonic()
                except Exception:
                    import logging
                    logging.exception("Community event worker failed")
                self.stop.wait(1)
        self.thread = threading.Thread(target=loop, daemon=True, name="community-events")
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=12)
