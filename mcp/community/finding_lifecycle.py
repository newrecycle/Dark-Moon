"""Metadata-only finding lifecycle reads for the independent fork.

Campaign rows are retained CURRENT snapshots, not historic finding states.
The journal contains only recorded events after activation.
"""
import math
import re
from urllib.parse import urlsplit, urlunsplit

from api import json_storage as data
from .posture import counts, timestamp
from .store import identifier


def target_evolution(target_id):
    target_id = identifier(target_id)
    if not data.load_target(target_id):
        raise KeyError(target_id)
    campaigns = [c for c in data.load_campaigns() if c.get("target_id") == target_id]
    campaigns.sort(key=lambda c: (timestamp(c.get("date")) is None,
                                  timestamp(c.get("date")) or 0, str(c.get("id") or "")))
    records = []
    for c in campaigns:
        findings = [f for f in data.load_vulnerabilities(c["id"])
                    if f.get("campaign_id") == c["id"] and f.get("target_id") in (None, target_id)]
        records.append({"campaign_id": c["id"], "target_id": target_id, "project_id": c.get("project_id"),
                        "started_at": c.get("date") if timestamp(c.get("date")) is not None else None,
                        "status": c.get("status"), **counts(findings)})
    return {"target_id": target_id, "projection": "retained_campaign_current_snapshots_v1",
            "historical_transitions_available": False,
            "note": "Campaign start dates are recorded; finding counts and statuses are current retained snapshots, not as-of-start history.",
            "data": records, "total": len(records)}


def history_page(params):
    allowed = {"target_id", "limit", "offset"}
    if set(params) - allowed or any(len(values) != 1 for values in params.values()):
        raise ValueError("History permits only one target_id, limit and offset each")
    target = params.get("target_id", [None])[0]
    if target is not None:
        identifier(target)
        if not data.load_target(target):
            raise KeyError(target)
    def number(key, default, maximum):
        raw = params.get(key, [str(default)])[0]
        if not re.fullmatch(r"[0-9]{1,10}", raw):
            raise ValueError(key + " must be a nonnegative decimal integer")
        value = int(raw)
        if value > maximum or (key == "limit" and value == 0):
            raise ValueError(key + " is outside the supported range")
        return value
    limit, offset = number("limit", 100, 500), number("offset", 0, 1000000000)
    journal = data.load_finding_history()
    events = [e for e in journal["events"] if target is None or e.get("target_id") == target]
    events.sort(key=lambda e: (e["recorded_at"], e["id"]))
    total = len(events)
    safe = ("id", "event", "recorded_at", "campaign_id", "target_id", "project_id",
            "finding_id", "previous_status", "status", "source")
    page = [{k: e.get(k) for k in safe} for e in events[offset:offset + limit]]
    end = offset + len(page)
    return {"data": page, "total": total, "offset": offset, "limit": limit,
            "has_more": end < total, "next_offset": end if end < total else None,
            "target_id": target, "order": "recorded_at_asc,id_asc",
            "recording_started_at": journal["recording_started_at"],
            "history_complete": False, "projection": "recorded_finding_mutations_v1"}


def _linked_ids(proposal):
    ids = []
    refs = proposal.get("finding_ids")
    if not isinstance(refs, list):
        refs = []
    for value in [proposal.get("finding_id"), *refs]:
        if isinstance(value, str) and value and value not in ids:
            ids.append(value)
    return ids


def _public_url(value):
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            return None
        return urlunsplit(("https", parts.netloc, parts.path, "", ""))
    except ValueError:
        return None


def remediation_record(proposal):
    pub = proposal.get("publication") if isinstance(proposal.get("publication"), dict) else {}
    pub_url = _public_url(pub.get("url"))
    published = bool(proposal.get("published") and pub_url)
    judge = proposal.get("judge") if isinstance(proposal.get("judge"), dict) else {}
    confidence = judge.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence):
        confidence = None
    validation = proposal.get("validation") if isinstance(proposal.get("validation"), dict) else {}
    def summaries(phase):
        rows = validation.get(phase)
        if not isinstance(rows, list):
            return []
        return [{k: row.get(k) for k in ("name", "kind", "passed", "exit_code", "timed_out")}
                for row in rows if isinstance(row, dict)]
    return {"id": proposal.get("id"), "campaign_id": proposal.get("campaign_id"),
            "finding_ids": _linked_ids(proposal), "status": proposal.get("status"),
            "title": str(proposal.get("title") or "")[:160], "url": pub_url if published else None,
            "state": pub.get("state") if published else None,
            "record_type": "published_pr" if published else "local_proposal",
            "published": published, "publication_recorded": bool(proposal.get("published")),
            "provider": pub.get("provider") if published else None,
            "pr_id": pub.get("id") if published else None,
            "published_at": pub.get("completed_at") if published else None,
            "confidence": confidence, "validation": {phase: summaries(phase) for phase in ("before", "after")}}


def remediation_records(proposals):
    records = [remediation_record(p) for p in proposals if isinstance(p, dict) and p.get("id")]
    return sorted(records, key=lambda p: str(p["id"]))


def for_finding(proposals, finding_id, campaign_id=None):
    finding_id = identifier(finding_id)
    if campaign_id is not None:
        campaign_id = identifier(campaign_id)
        if not data.load_campaign(campaign_id):
            raise KeyError(campaign_id)
    matches = {(f.get("campaign_id"), f.get("id")) for f in data.load_all_vulnerabilities()
               if f.get("id") == finding_id and (campaign_id is None or f.get("campaign_id") == campaign_id)}
    if not matches:
        raise KeyError(finding_id)
    records = [r for r in remediation_records(proposals)
               if (r.get("campaign_id"), finding_id) in matches and finding_id in r["finding_ids"]]
    return {"finding_id": finding_id, "campaign_ids": sorted({c for c, _ in matches if isinstance(c, str)}),
            "data": records, "total": len(records)}
