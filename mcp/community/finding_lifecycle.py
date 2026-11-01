"""Metadata-only finding lifecycle reads for the independent fork.

Campaign rows are retained CURRENT snapshots, not historic finding states.
The journal contains only recorded events after activation.
"""
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from api import json_storage as data
from .posture import counts, timestamp
from .finding_stats import finding_stats, public_histogram
from .posture import SEVERITIES
from .store import identifier

HISTORY_FINDINGS_LIMIT = 500


def _campaign_key(campaign):
    value = campaign.get("date")
    started = timestamp(value)
    if started is None and isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            # Display order only; do not invent an exact assessment start time.
            started = datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            pass
    return (started is None, started or 0, str(campaign.get("id") or ""))


def _campaign_date(campaign):
    value = campaign.get("date")
    return value if isinstance(value, str) and not _campaign_key(campaign)[0] else None


def target_evolution(target_id):
    target_id = identifier(target_id)
    if not data.load_target(target_id):
        raise KeyError(target_id)
    campaigns = [c for c in data.load_campaigns() if c.get("target_id") == target_id]
    campaigns.sort(key=_campaign_key)
    records, series = [], []
    for c in campaigns:
        findings = [f for f in data.load_vulnerabilities(c["id"])
                    if f.get("campaign_id") == c["id"] and f.get("target_id") in (None, target_id)]
        record = {"campaign_id": c["id"], "target_id": target_id, "project_id": c.get("project_id"),
                        "started_at": c.get("date") if timestamp(c.get("date")) is not None else None,
                        "status": c.get("status"), **counts(findings)}
        records.append(record)
        series.append({"campaign_id": record["campaign_id"], "date": _campaign_date(c),
                       "stats": {**dict.fromkeys(SEVERITIES, 0),
                                 **public_histogram(finding_stats(findings)["by_severity"], set(SEVERITIES))},
                       "total_vulns": record["findings"], "overall_risk": record["risk"]})
    return {"target_id": target_id, "projection": "retained_campaign_current_snapshots_v1",
            "historical_transitions_available": False,
            "note": "Campaign start dates are recorded; finding counts and statuses are current retained snapshots, not as-of-start history.",
            "data": records, "campaigns": series, "total": len(records)}


def _campaign_history(target_id, limit, offset):
    """A bounded current-state series, separate from the recorded event journal."""
    from .evidence_access import public_projection
    campaigns = [c for c in data.load_campaigns() if target_id is None or c.get("target_id") == target_id]
    campaigns.sort(key=_campaign_key)
    history = []
    for campaign in campaigns[offset:offset + limit]:
        findings = [f for f in data.load_vulnerabilities(campaign["id"])
                    if f.get("campaign_id") == campaign["id"]
                    and f.get("target_id") in (None, campaign.get("target_id"))]
        rows = []
        for finding in findings[:HISTORY_FINDINGS_LIMIT]:
            row = public_projection({key: finding.get(key) for key in ("id", "severity", "status", "cve")})
            row.setdefault("cve", None)
            rows.append(row)
        date = _campaign_date(campaign)
        history.append({"campaign_id": campaign["id"], "date": date[:10] if date else None,
                        "vulnerabilities": rows, "vulnerabilities_total": len(findings),
                        "vulnerabilities_truncated": len(findings) > HISTORY_FINDINGS_LIMIT})
    total = len(campaigns)
    end = offset + len(history)
    more = end < total and end <= data.FINDING_HISTORY_MAX_OFFSET
    return {"history": history, "history_total": total, "history_limit": limit, "history_offset": offset,
            "history_has_more": more, "history_next_offset": end if more else None,
            "history_projection": "retained_campaign_current_snapshots_v1",
            "history_page_consistency": "live_offset", "history_vulnerabilities_limit": HISTORY_FINDINGS_LIMIT}


def history_page(params):
    allowed = {"target_id", "limit", "offset", "snapshot_seq"}
    if set(params) - allowed or any(len(values) != 1 for values in params.values()):
        raise ValueError("History permits only one target_id, limit, offset and snapshot_seq each")
    target = params.get("target_id", [None])[0]
    if target is not None:
        identifier(target)
        if not data.load_target(target):
            raise KeyError(target)
    def number(key, default, maximum):
        raw = params.get(key, [str(default)])[0]
        if not re.fullmatch(r"[0-9]{1,19}" if key == "snapshot_seq" else r"[0-9]{1,10}", raw):
            raise ValueError(key + " must be a nonnegative decimal integer")
        value = int(raw)
        if value > maximum or (key == "limit" and value == 0):
            raise ValueError(key + " is outside the supported range")
        return value
    limit, offset = number("limit", 100, 500), number("offset", 0, data.FINDING_HISTORY_MAX_OFFSET)
    snapshot_seq = number("snapshot_seq", 0, 9223372036854775807) if "snapshot_seq" in params else None
    journal = data.load_finding_history(target_id=target, limit=limit, offset=offset, snapshot_seq=snapshot_seq)
    page, total = journal["events"], journal["total"]
    end = offset + len(page)
    has_more = end < total and end <= data.FINDING_HISTORY_MAX_OFFSET
    return {"data": page, "total": total, "offset": offset, "limit": limit,
            "has_more": has_more, "next_offset": end if has_more else None,
            "paging_limit_reached": end < total and not has_more,
            "target_id": target, "order": "recorded_at_asc,id_asc",
            "recording_started_at": journal["recording_started_at"],
            "max_offset": data.FINDING_HISTORY_MAX_OFFSET,
            "snapshot_seq": journal.get("snapshot_seq"),
            "page_consistency": "snapshot_seq" if snapshot_seq is not None else "live_offset",
            "history_complete": False, "projection": "recorded_finding_mutations_v1",
            **_campaign_history(target, limit, offset)}


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
        # The publication flag plus an arbitrary HTTPS URL is insufficient
        # proof of a PR. Only recognizable PR/MR detail paths are exposed.
        # This also excludes opaque token-bearing paths and encoded segments.
        if len(parts.path) > 512 or not re.fullmatch(
            r"/(?:[A-Za-z0-9._~-]+/){2,}(?:pull|pulls|pull-requests|-/merge_requests)/[1-9][0-9]*",
            parts.path,
        ):
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
