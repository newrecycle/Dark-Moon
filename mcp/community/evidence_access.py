"""Server-enforced evidence minimization and session-scoped one-use grants.

Projections operate on response copies only. The assessment JSON store, agents,
retest comparison and remediation implementation retain their original data.
"""
import hashlib
import hmac
import os
import re
import secrets
import stat
import time
from pathlib import Path

from api import json_storage as data
from .store import identifier

GRANT_TTL = 45
GRANT_LIMIT = 24
KINDS = frozenset({"finding", "campaign", "graph", "report", "report_pdf", "remediation", "patch", "run", "stream"})

# Deliberately explicit. Unrecognized fields, arbitrary nested free text, raw
# evidence/probe/patch/source content and network identifiers are not public.
FIELDS = frozenset({
    "id", "run_id", "campaign_id", "target_id", "project_id", "finding_id",
    "current_finding_id", "base_campaign_id", "new_campaign_id", "retest_id",
    "proposal_id", "schedule_id", "pr_id", "webhook_id", "job_id", "edge_id",
    "parent_id", "parent_node_id", "node_id", "source_id", "target_node_id",
    "status", "state", "severity", "risk_level", "verdict", "kind", "type",
    "record_type", "provider", "category", "format", "role", "published", "valid",
    "mitre_attack_id", "iso27001_control", "cve",
    "enabled", "has_more", "paging_limit_reached", "raw", "truncated",
    "cancel_requested", "synthetic", "complete", "validated", "passed",
    "total", "limit", "offset", "next_offset", "count", "total_findings",
    "campaigns_count", "projects_count", "targets_count",
    "total_vulnerabilities", "critical", "high", "medium", "low", "info",
    "confirmed", "exploited", "unconfirmed", "cvss_score",
    "version", "seq", "exit_code", "log_bytes", "http_status", "attempts",
    "created_at", "started_at", "finished_at", "discovered_at",
    "recorded_at", "triaged_at", "due_at", "next_run", "last_run",
    "timestamp", "ts", "contract_version", "log_status", "content_policy",
    "ordering", "page_consistency", "has_evidence", "has_screenshot",
    "has_extracted_data", "redacted", "log_truncated",
    "active_states", "active_count", "pending_count", "completed_count",
    "is_complete", "is_active", "risk_score", "overall_risk", "date",
    "message", "event", "disposition", "status_code", "finding_count",
    "affected_findings", "duration_seconds", "score",
})
CONTAINERS = frozenset({
    "data", "items", "rows", "projects", "targets", "campaigns", "findings",
    "vulnerabilities", "infrastructure", "nodes", "edges", "paths",
    "campaign_ids", "target_ids", "finding_ids", "before_ids",
    "jobs", "schedules", "remediations", "retests", "history", "events", "steps",
    "stats", "summary", "overview", "timeseries", "series", "points",
    "counts", "severity_distribution", "status_distribution",
    "category_distribution", "by_severity", "by_status",
    "verdicts", "verdicts_summary", "active_states", "result",
    "log", "target", "destination", "metadata",
    "scope", "graph", "links", "timeline", "analytics",
})
WORKSPACE_ROUTES = frozenset({
    "projects", "targets", "campaigns", "findings", "vulnerabilities",
    "dashboard", "overview", "run", "jobs", "remediations",
    "pull-requests", "retest", "events",
    "options", "source-files", "integrations",
})
STATUS_VALUES = frozenset({
    "queued", "running", "completed", "succeeded", "failed", "cancelled",
    "cancelling", "stopped", "interrupted", "timed_out", "unknown",
    "unconfirmed", "confirmed", "exploited", "remediated", "resolved",
    "accepted_risk", "false_positive", "open", "closed", "draft",
    "proposed", "validated", "incomplete", "pending", "delivered",
    "available", "missing", "unavailable", "not_observed", "still_present",
    "new", "fixed", "info", "low", "medium", "high", "critical", "assessment",
    "remediation", "published_pr", "local_proposal", "review", "positive",
})
OPAQUE = frozenset({
    "id", "run_id", "campaign_id", "target_id", "project_id", "finding_id",
    "current_finding_id", "base_campaign_id", "new_campaign_id", "retest_id",
    "proposal_id", "schedule_id", "pr_id", "webhook_id", "job_id", "node_id",
    "parent_id", "parent_node_id", "source_id", "target_node_id",
})


def _safe_value(key, value):
    if value is None or type(value) in (int, float, bool):
        return value
    if not isinstance(value, str):
        return None
    if key == "message":
        return value if value in ("Run queued", "Run started", "Run finished", "Cancellation requested") else None
    if key == "event":
        return value if re.fullmatch(r"(campaign|finding|pr|remediation|retest|webhook)\.[a-z_]{1,32}", value) else None
    if key == "mitre_attack_id":
        return value if re.fullmatch(r"T[0-9]{4}(?:\.[0-9]{3})?", value) else None
    if key == "iso27001_control":
        return value if re.fullmatch(r"A\.[0-9]{1,2}(?:\.[0-9]{1,2})?", value) else None
    if key == "cve":
        return value if re.fullmatch(r"CVE-[0-9]{4}-[0-9]{4,10}", value) else None
    if key in ("status", "state", "severity", "verdict", "risk_level", "disposition"):
        return value if value in STATUS_VALUES else "unknown"
    if key in OPAQUE:
        return value[:200] if len(value) <= 200 else None
    if key in ("date", "created_at", "started_at", "finished_at", "discovered_at",
               "recorded_at", "triaged_at", "due_at", "next_run", "last_run",
               "timestamp", "ts"):
        # Timestamps must be shaped as dates rather than arbitrary free text.
        return value[:40] if len(value) <= 40 and value[:4].isdigit() else None
    if key in ("category", "provider", "kind", "type", "record_type", "format", "role",
               "log_status", "content_policy", "ordering", "page_consistency"):
        return value if len(value) <= 40 and all(c.isalnum() or c in "_.:-" for c in value) else None
    return None


def _counts(raw, keys):
    return {k: v for k, v in raw.items() if k in keys and type(v) in (int, float)} if isinstance(raw, dict) else {}


def _posture(raw):
    """Typed posture analytics retain numeric summaries and stable IDs only."""
    if not isinstance(raw, dict):
        return {}
    totals = {"projects", "targets", "campaigns", "findings", "active", "excluded",
              "running_campaigns", "recorded_campaigns", "total_campaigns", "mean_seconds",
              "proposals", "validated", "validated_share", "findings_with_proposals",
              "unlinked_proposals", "findings_without_registered_target", "findings_without_campaign"}
    severity = {"critical", "high", "medium", "low", "info", "unknown"}
    def rows(items):
        result = []
        for obj in items[:10000] if isinstance(items, list) else []:
            if not isinstance(obj, dict):
                continue
            row = {k: v for k, v in obj.items()
                   if k in ("id", "project_id", "target_id", "latest_campaign_id",
                            "status", "started_at", "risk", "findings", "active",
                            "excluded", "campaigns", "duration_seconds")
                   and (type(v) in (int, float) or isinstance(v, str) and len(v) <= 200)}
            row["active_severity"] = _counts(obj.get("active_severity"), severity)
            result.append(row)
        return result
    rem = raw.get("remediation") if isinstance(raw.get("remediation"), dict) else {}
    raw_totals = raw.get("totals") if isinstance(raw.get("totals"), dict) else {}
    risk = raw_totals.get("risk")
    return {
        "totals": {**_counts(raw_totals, totals),
                   "risk": risk if risk in severity | {"none"} else "unknown"},
        "severity_distribution": _counts(raw.get("severity_distribution"), severity),
        "status_distribution": _counts(raw.get("status_distribution"), STATUS_VALUES),
        "mitre_distribution": _counts(raw.get("mitre_distribution"),
                                      {key for key in (raw.get("mitre_distribution") or {})
                                       if isinstance(key, str) and
                                       re.fullmatch(r"T[0-9]{4}(?:\\.[0-9]{3})?", key)}),
        "mitre_unmapped": raw.get("mitre_unmapped", 0),
        "target_risk": rows(raw.get("target_risk")),
        "campaign_history": rows(raw.get("campaign_history")),
        "duration": _counts(raw.get("duration"), totals),
        "remediation": {**_counts(rem, totals),
                        "status_distribution": _counts(rem.get("status_distribution"), STATUS_VALUES)},
        "coverage": _counts(raw.get("coverage"), totals)
    }


def public_projection(value, depth=0):
    """Fail closed on unknown response fields. Never modify persisted records."""
    if depth > 9:
        return None
    if isinstance(value, list):
        return [public_projection(item, depth + 1) for item in value[:10000]]
    if not isinstance(value, dict):
        return None
    projected = {}
    for key, item in value.items():
        if key == "active_states" and isinstance(item, list):
            projected[key] = [x for x in item if isinstance(x, str) and x in STATUS_VALUES]
        elif key == "posture":
            projected[key] = _posture(item)
        elif key == "content":
            projected[key] = "Recorded evidence is withheld by default."
        elif key in ("campaign_ids", "target_ids", "finding_ids", "before_ids") and isinstance(item, list):
            projected[key] = [x for x in item[:10000] if isinstance(x, str) and len(x) <= 200]
        elif key in ("source", "target") and isinstance(item, str):
            # Graph edges have stable vertex identities. These fields on
            # remediation records are paths, not safe graph references.
            if "kind" in value and "target" in value and "source" in value and len(item) <= 200:
                projected[key] = item
        elif key in CONTAINERS:
            if isinstance(item, (dict, list)):
                projected[key] = public_projection(item, depth + 1)
            # An opaque string in a structural field is never safe.
        elif key in FIELDS:
            if isinstance(item, list) and key == "active_states":
                projected[key] = [x for x in item if x in STATUS_VALUES]
            else:
                safe = _safe_value(key, item)
                if safe is not None:
                    projected[key] = safe
    return projected


def _safe_opencode(raw):
    """Preserve nonsecret provider selection metadata without URLs or tokens."""
    if not isinstance(raw, dict):
        raw = {}
    providers = []
    for p in raw.get("providers", [])[:500] if isinstance(raw.get("providers"), list) else []:
        if not isinstance(p, dict):
            continue
        providers.append({
            "id": str(p.get("id", ""))[:100],
            "name": str(p.get("name", ""))[:100],
            "connected": p.get("connected") is True,
            "auth_type": str(p.get("auth_type", "none"))[:40],
            "base_url": "",
            "models": [{"id": str(m.get("id", ""))[:100], "name": str(m.get("name", ""))[:100]}
                       for m in p.get("models", [])[:1000] if isinstance(m, dict)],
            "methods": [{"index": m.get("index", 0), "type": str(m.get("type", ""))[:40],
                         "label": str(m.get("label", ""))[:60]}
                        for m in p.get("methods", [])[:100] if isinstance(m, dict)]
        })
    return {"providers": providers, "active_model": str(raw.get("active_model", ""))[:100],
            "live": raw.get("live") is True, "warning": "",
            "source": "metadata_only", "oauth_available": raw.get("oauth_available") is True,
            "restart_required": raw.get("restart_required") is True}


def _paths(items):
    if not isinstance(items, list):
        return []
    result = []
    for path in items[:100]:
        if not isinstance(path, dict):
            continue
        result.append({
            "id": path.get("id"), "campaign_id": path.get("campaign_id"),
            "created_at": path.get("created_at"),
            "version": path.get("version", 1) if type(path.get("version", 1)) is int else None,
            "title": "Reviewed path (evidence withheld)",
            "valid": path.get("valid") is True,
            "basis": "operator_review_of_recorded_evidence",
            "steps": [{"edge_id": step.get("edge_id"), "finding_id": step.get("finding_id"),
                       "evidence_sha256": step.get("evidence_sha256")}
                      for step in path.get("steps", [])[:32] if isinstance(step, dict)],
            "issues": ["Review is stale or unavailable"] if path.get("issues") else []
        })
    return result


def _safe_pr_response(body):
    """Preserve the PR/proposal identity projection but not editable free text."""
    def record(p):
        if not isinstance(p, dict):
            return {}
        result = {key: p.get(key) for key in (
            "id", "campaign_id", "status", "state", "record_type",
            "published", "publication_recorded", "provider", "pr_id",
            "published_at", "confidence")}
        result["finding_ids"] = [x for x in p.get("finding_ids", [])[:1000]
                                 if isinstance(x, str) and len(x) <= 200]
        # Only the finding_lifecycle._public_url validation makes publication
        # links safe: no credentials, fragments or query and a PR detail path.
        from .finding_lifecycle import _public_url
        result["url"] = _public_url(p.get("url"))
        validation = p.get("validation")
        if isinstance(validation, dict):
            result["validation"] = {
                stage: [{key: v.get(key) for key in ("kind", "passed", "exit_code", "timed_out")
                          if type(v.get(key)) in (str, int, bool)}
                         for v in validation.get(stage, [])[:100] if isinstance(v, dict)]
                for stage in ("before", "after") if isinstance(validation.get(stage), list)}
        return result
    if isinstance(body, dict) and isinstance(body.get("data"), list):
        return {**{key: body[key] for key in ("finding_id", "campaign_ids", "total") if key in body},
                "data": [record(p) for p in body["data"][:10000]]}
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return {"data": record(body["data"])}
    return body


def minimize_response(path, content, kind):
    """Default read/write projection for both canonical and legacy workspace routes."""
    parts = path.split("?", 1)[0].strip("/").split("/")
    if len(parts) < 3 or parts[:2] != ["api", "v1"] or parts[2] not in WORKSPACE_ROUTES:
        return content
    # These handlers already construct bounded typed metadata, rather than
    # spreading persisted assessment records. Keep their published contracts.
    if parts[2] == "vulnerabilities" and parts[3:4] == ["history"]:
        return content
    if parts[2] == "targets" and len(parts) == 5 and parts[4] == "evolution":
        return content
    if parts[2] == "campaigns" and len(parts) >= 5 and parts[4] == "paths":
        if isinstance(content, dict) and isinstance(content.get("data"), dict):
            projected = _paths([content["data"]])
            return {"data": projected[0] if projected else {}}
        if isinstance(content, dict) and isinstance(content.get("data"), list):
            result = {"data": _paths(content["data"]), "total": content.get("total", 0)}
            if "current_version" in content:
                value = content["current_version"]
                result["current_version"] = value if type(value) is int else None
                result["deleted"] = content.get("deleted") is True
            return result
        if isinstance(content, dict) and "deleted" in content:
            return {"deleted": content["deleted"]}
        return {"data": _paths([content])[0]} if isinstance(content, dict) else {"data": []}
    if parts[2] == "pull-requests":
        return _safe_pr_response(content)
    if parts[2] == "run":
        return content  # run_views uses explicit safe serializers; raw access requires a grant
    if parts[2] == "dashboard" and parts[3:] == ["posture"]:
        return _posture(content)
    # These endpoints are projected by the dedicated lifecycle API functions:
    # target_evolution() contains only current campaign counts/IDs;
    # history_page() contains only the validated ten-field event metadata;
    # remediation_records()/for_finding() contain allowlisted proposal metadata.
    # Preserve these explicit public contracts without enabling evidence reveal
    # for unrelated workspace routes or exposing raw finding/patch bodies.
    if ((parts[2] == "targets" and len(parts) == 5 and parts[4] == "evolution")
            or (parts[2] == "vulnerabilities" and parts[3:] == ["history"])
            or parts[2] == "pull-requests"):
        return content
    if parts[2] == "source-files":
        return {"files": [], "truncated": True, "evidence_reveal_required": True}
    if parts[2] == "options" and isinstance(content, dict):
        # Static launch-form catalogs and vault's existing masked credentials
        # remain useful; never echo arbitrary source paths or raw records.
        return {
            "assessment": content.get("assessment", {}),
            "opencode": _safe_opencode(content["opencode"]) if isinstance(content.get("opencode"), dict) else None,
            "repositories": [],
            "targets": public_projection(content.get("targets", [])),
            "campaigns": public_projection(content.get("campaigns", [])),
            "findings": public_projection(content.get("findings", [])),
            "credentials": public_projection(content.get("credentials", [])),
            "credential_choices": {k: public_projection(v) for k, v in content.get("credential_choices", {}).items()
                                   if k in ("assessment_login", "assessment_token", "source_checkout", "provider_api_key")},
        }
    if isinstance(content, (dict, list)):
        return public_projection(content)
    if isinstance(content, str) and (kind.startswith("text/") or kind == "text/markdown"):
        return "Evidence content withheld by default. Request a scoped evidence reveal."
    return content


def _subject(identity):
    return identity.get("session_id") or ("workspace:" + identity["id"] if identity.get("authentication") == "workspace-token" else "")


def _resource(service, kind, resource_id):
    resource_id = identifier(resource_id)
    if kind in ("campaign", "graph", "report", "report_pdf"):
        campaign = service.campaign(resource_id)
        return campaign["id"]
    if kind == "finding":
        finding = data.load_vulnerability(resource_id)
        if not finding:
            raise KeyError(resource_id)
        return identifier(finding["campaign_id"])
    if kind in ("run", "stream"):
        job = service.store.get("jobs", resource_id)
        if not job:
            raise KeyError(resource_id)
        return identifier(job["campaign_id"])
    if kind in ("remediation", "patch"):
        proposal = next((p for p in service.snapshot()["remediations"] if p.get("id") == resource_id), None)
        if not proposal:
            raise KeyError(resource_id)
        return identifier(proposal["campaign_id"])
    raise ValueError("Unsupported reveal resource")


def issue(service, identity, kind, resource_id, campaign_id):
    if identity.get("role") != "admin":
        raise PermissionError("Administrator access is required for evidence reveal")
    if kind not in KINDS:
        raise ValueError("Unsupported reveal kind")
    subject = _subject(identity)
    if not subject:
        raise PermissionError("A valid session is required")
    scope = _resource(service, kind, resource_id)
    if campaign_id is not None and identifier(campaign_id) != scope:
        raise PermissionError("Evidence grant scope mismatch")
    stamp = time.time()
    token = secrets.token_urlsafe(32)
    grant_id = "eg_" + secrets.token_hex(16)
    def record(state):
        rows = state.setdefault("evidence_grants", {})
        rows_copy = {k: v for k, v in rows.items()
                     if isinstance(v, dict) and v.get("expires_at", 0) > stamp
                     and not v.get("revoked") and not v.get("used")}
        if sum(v.get("session") == subject for v in rows_copy.values()) >= GRANT_LIMIT:
            raise PermissionError("Too many outstanding evidence grants")
        rows.clear()
        rows.update(rows_copy)
        rows[grant_id] = {
            "session": subject, "user_id": identity["id"], "role": "admin",
            "kind": kind, "id": identifier(resource_id), "campaign_id": scope,
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "expires_at": stamp + GRANT_TTL, "used": False, "revoked": False}
    service.store.update(record)
    return {"grant_id": grant_id, "grant": token, "expires_in": GRANT_TTL,
            "resource": {"kind": kind, "id": resource_id, "campaign_id": scope}}


def consume(service, identity, kind, resource_id, raw_token):
    if identity.get("role") != "admin" or kind not in KINDS:
        raise PermissionError("Evidence reveal is unavailable")
    if not isinstance(raw_token, str) or not 30 <= len(raw_token) <= 256:
        raise PermissionError("An unexpired evidence grant is required")
    subject = _subject(identity)
    resource_id = identifier(resource_id)
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    stamp = time.time()
    scope = _resource(service, kind, resource_id)
    def claim(state):
        for row in state.get("evidence_grants", {}).values():
            if not isinstance(row, dict) or not hmac.compare_digest(str(row.get("token_hash", "")), digest):
                continue
            if row.get("used") or row.get("revoked") or row.get("expires_at", 0) <= stamp:
                break
            if (row.get("session") != subject or row.get("user_id") != identity["id"] or
                    row.get("kind") != kind or row.get("id") != resource_id or
                    row.get("campaign_id") != scope or row.get("role") != "admin"):
                break
            # JWT session revocation and password rotation are checked by
            # Service.identity before this call. Check again in transaction.
            if identity.get("session_id") and identity["session_id"] not in state.get("sessions", {}):
                break
            row["used"] = True
            return row["expires_at"]
        raise PermissionError("Evidence grant is invalid or expired")
    return service.store.update(claim)


def revoke(service, identity, grant_id):
    grant_id = identifier(grant_id)
    subject = _subject(identity)
    def operation(state):
        row = state.get("evidence_grants", {}).get(grant_id)
        if not row or row.get("session") != subject or row.get("user_id") != identity["id"]:
            raise KeyError(grant_id)
        row["revoked"] = True
        return {"revoked": True, "grant_id": grant_id}
    return service.store.update(operation)


def revoke_session(store, identity):
    subject = _subject(identity)
    if not subject:
        return
    def operation(state):
        for row in state.get("evidence_grants", {}).values():
            if isinstance(row, dict) and row.get("session") == subject:
                row["revoked"] = True
    store.update(operation)


def reveal(service, kind, resource_id):
    from . import reports
    if kind == "finding":
        return {"data": data.load_vulnerability(identifier(resource_id))}
    if kind == "campaign":
        return {"data": service.campaign(resource_id)}
    if kind == "graph":
        return {"data": service.graph(resource_id)}
    if kind == "report":
        return {"data": {"campaign_id": resource_id, "content": reports.markdown(service.campaign(resource_id))}}
    if kind == "remediation":
        proposal = next(p for p in service.snapshot()["remediations"] if p.get("id") == resource_id)
        return {"data": proposal}
    if kind == "patch":
        file = service.store.root / "remediation" / identifier(resource_id) / "fix.patch"
        fd = os.open(file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            status = os.fstat(fd)
            if not stat.S_ISREG(status.st_mode) or status.st_size > 262144:
                raise ValueError("Patch content is unavailable")
            with os.fdopen(fd, "rb", closefd=False) as handle:
                patch_bytes = handle.read(262145)
        finally:
            os.close(fd)
        return {"data": {"id": resource_id, "patch": patch_bytes.decode("utf-8", "replace")}}
    if kind == "run":
        from .run_views import _read_chunk
        chunk, _, state, truncated = _read_chunk(service.store, resource_id, tail=True)
        return {"data": {"run_id": resource_id, "log_status": state, "truncated": truncated,
                         "untrusted": True, "content": chunk.decode("utf-8", "replace")}}
    raise ValueError("Use the protected export or stream route for this grant kind")
