"""Current-state posture over retained records; no cached risk or evidence bodies."""
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone

SEVERITIES = ("critical", "high", "medium", "low", "info")
EXCLUDED_STATUSES = frozenset({"false_positive", "remediated", "resolved", "closed", "fixed"})


def active(finding):
    # Accepted risk is still exposure. Unknown/legacy states remain visible.
    return str(finding.get("status") or "unconfirmed").strip().lower() not in EXCLUDED_STATUSES


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).timestamp() if parsed.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def duration(campaign):
    value = campaign.get("duration_seconds")
    # Running/default zero values are not recorded completion durations.
    if campaign.get("status") in {"running", "queued"} or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def distribution(findings, key, default):
    return dict(sorted(Counter(str(f.get(key) or default) for f in findings).items()))


def counts(findings):
    current = [f for f in findings if active(f)]
    severity = Counter(str(f.get("severity") or "unknown").lower() for f in current)
    return {"findings": len(findings), "active": len(current), "excluded": len(findings) - len(current),
            "active_severity": dict(severity),
            "risk": next((s for s in SEVERITIES if severity[s]), "unknown" if current else "none")}


def posture(snapshot):
    findings, campaigns = snapshot["findings"], snapshot["campaigns"]
    projects, targets = snapshot["projects"], snapshot["targets"]
    campaign_ids, target_ids = {c["id"] for c in campaigns}, {t["id"] for t in targets}
    by_target, by_campaign = defaultdict(list), defaultdict(list)
    for finding in findings:
        by_target[finding.get("target_id")].append(finding)
        by_campaign[finding.get("campaign_id")].append(finding)
    campaign_rows = [{"id": c["id"], "target_id": c.get("target_id"), "project_id": c.get("project_id"),
                      "started_at": c.get("date"), "status": c.get("status"), "duration_seconds": duration(c),
                      **counts(by_campaign[c["id"]])} for c in campaigns]
    # Undated records sort last; identity breaks timestamp ties, independent of file order.
    def recent_key(c):
        started = timestamp(c["started_at"])
        return (started is None, -started if started is not None else 0, c["id"])
    campaign_rows.sort(key=recent_key)
    campaign_counts = Counter(c.get("target_id") for c in campaigns)
    latest = {}
    for c in campaign_rows:
        if timestamp(c["started_at"]) is not None:
            latest.setdefault(c["target_id"], c["id"])
    target_rows = [{"id": t["id"], **counts(by_target[t["id"]]),
                    "campaigns": campaign_counts[t["id"]], "latest_campaign_id": latest.get(t["id"])}
                   for t in targets]
    target_rows.sort(key=lambda t: (*(-t["active_severity"].get(s, 0) for s in SEVERITIES), -t["active"], t["id"]))
    linked_findings = {(f.get("campaign_id"), f.get("id")) for f in findings
                       if f.get("id") and f.get("campaign_id") in campaign_ids}
    proposals = [p for p in snapshot["remediations"] if (p.get("campaign_id"), p.get("finding_id")) in linked_findings]
    statuses = distribution(proposals, "status", "unknown")
    durations = [c["duration_seconds"] for c in campaign_rows if c["duration_seconds"] is not None]
    return {"cohort": "all_retained_records_current_state", "totals": {
                "projects": len(projects), "targets": len(targets), "campaigns": len(campaigns),
                **counts(findings), "running_campaigns": sum(c.get("status") == "running" for c in campaigns)},
            "severity_distribution": {**dict.fromkeys(SEVERITIES, 0), **distribution(findings, "severity", "unknown")},
            "status_distribution": {"confirmed": 0, "exploited": 0, **distribution(findings, "status", "unconfirmed")},
            "mitre_distribution": distribution([f for f in findings if f.get("mitre_attack_id")], "mitre_attack_id", "unknown"),
            "mitre_unmapped": sum(not f.get("mitre_attack_id") for f in findings),
            "target_risk": target_rows, "campaign_history": campaign_rows,
            "duration": {"recorded_campaigns": len(durations), "total_campaigns": len(campaigns),
                         "mean_seconds": sum(durations) / len(durations) if durations else None},
            "remediation": {"proposals": len(proposals), "status_distribution": statuses,
                "validated": statuses.get("validated", 0),
                "validated_share": statuses.get("validated", 0) / len(proposals) if proposals else None,
                "findings_with_proposals": len({(p["campaign_id"], p["finding_id"]) for p in proposals}),
                "unlinked_proposals": len(snapshot["remediations"]) - len(proposals)},
            "coverage": {"findings_without_registered_target": sum(f.get("target_id") not in target_ids for f in findings),
                         "findings_without_campaign": sum(f.get("campaign_id") not in campaign_ids for f in findings)}}


def windowed_posture(snapshot, parameters):
    """Current triage in a campaign-start cohort, never historical reconstruction."""
    if set(parameters) - {'from', 'to'} or any(len(v) != 1 or not v[0] for v in parameters.values()):
        raise ValueError('Use one nonblank from/to timestamp')
    bounds = {}
    for key, values in parameters.items():
        value = values[0]
        # Require full, timezone-aware timestamps; no locale/date-only guessing.
        if not isinstance(value, str) or 'T' not in value or timestamp(value) is None:
            raise ValueError('Use timezone-aware from/to timestamps')
        bounds[key] = timestamp(value)
    if 'from' in bounds and 'to' in bounds and bounds['from'] >= bounds['to']:
        raise ValueError('from must precede to')
    if not bounds:
        return posture(snapshot)
    campaigns = [c for c in snapshot['campaigns'] if timestamp(c.get('date')) is not None
                 and ('from' not in bounds or timestamp(c['date']) >= bounds['from'])
                 and ('to' not in bounds or timestamp(c['date']) < bounds['to'])]
    ids = {c['id'] for c in campaigns}
    findings = [f for f in snapshot['findings'] if f.get('campaign_id') in ids]
    target_ids = {c.get('target_id') for c in campaigns} | {f.get('target_id') for f in findings}
    project_ids = {c.get('project_id') for c in campaigns} | {f.get('project_id') for f in findings}
    cohort = dict(snapshot, campaigns=campaigns, findings=findings,
                  targets=[t for t in snapshot['targets'] if t['id'] in target_ids],
                  projects=[p for p in snapshot['projects'] if p['id'] in project_ids],
                  remediations=[r for r in snapshot['remediations'] if r.get('campaign_id') in ids])
    result = posture(cohort)
    result['cohort'] = 'campaign_start_window_current_state'
    result['window'] = {key: datetime.fromtimestamp(value, timezone.utc).isoformat()
                        for key, value in bounds.items()}
    result['window']['excluded_undated_campaigns'] = sum(
        timestamp(c.get('date')) is None for c in snapshot['campaigns'])
    return result
