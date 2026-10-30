"""Composed finding filters and stable pages for the existing SDK list contract."""
from functools import cmp_to_key
import math

from .posture import active, timestamp, window_bounds

FILTERS = ("severity", "status", "category", "campaign_id", "project_id", "target_id", "mitre_attack_id")
FIELDS = {"severity", "cvss", "title", "status", "campaign", "target"}
SEVERITY = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}


def finding_page(items, query, campaigns=None):
    bounds = window_bounds({k:[query['campaign_'+k]] for k in ('from','to') if 'campaign_'+k in query})
    campaign_ids = None
    if bounds:
        if campaigns is None:
            raise ValueError("Campaign dates are required for a window filter")
        campaign_ids = {c['id'] for c in campaigns if timestamp(c.get('date')) is not None
                        and ('from' not in bounds or timestamp(c['date']) >= bounds['from'])
                        and ('to' not in bounds or timestamp(c['date']) < bounds['to'])}
    search = query.get("q", "")
    if len(search) > 500:
        raise ValueError("Finding search is limited to 500 characters")
    sort = query.get("sort", "severity_desc")
    field, _, direction = sort.rpartition("_")
    if field not in FIELDS or direction not in {"asc", "desc"}:
        raise ValueError("Choose a supported finding sort field and asc/desc direction")
    triage = query.get("triage", "")
    if triage not in {"", "active", "excluded"}:
        raise ValueError("Choose active or excluded triage")
    selected = [f for f in items if (campaign_ids is None or f.get("campaign_id") in campaign_ids) and (not triage or active(f) == (triage == "active")) and all(not query.get(k) or str(f.get(k) or {"severity": "unknown", "status": "unconfirmed"}.get(k, "")) == query[k] for k in FILTERS)
                and (not search.strip() or search.strip().lower() in " ".join(
                    str(f.get(k) or "") for k in ("id", "title", "endpoint", "category", "campaign_id", "target_id")
                ).lower())]
    def key(f):
        if field == "severity": return SEVERITY.get(str(f.get("severity", "")).lower(), 0)
        if field == "cvss":
            try:
                value = float(f.get("cvss_score"))
                return value if math.isfinite(value) else None
            except (TypeError, ValueError): return None
        return str(f.get({"campaign": "campaign_id", "target": "target_id"}.get(field, field)) or "").lower()
    # Keep tie ordering ascending even when the primary sort is descending.
    def stable_compare(a, b):
        x, y = key(a), key(b)
        order = ((x is None) - (y is None)) if x is None or y is None else ((x > y) - (x < y)) * (-1 if direction == "desc" else 1)
        if order: return order
        ta = tuple(str(a.get(k) or "") for k in ("campaign_id", "id"))
        tb = tuple(str(b.get(k) or "") for k in ("campaign_id", "id"))
        return (ta > tb) - (ta < tb)
    selected.sort(key=cmp_to_key(stable_compare))
    try:
        offset = int(query.get("offset", "0"))
        limit = int(query["limit"]) if "limit" in query else None
    except (TypeError, ValueError):
        raise ValueError("Finding limit and offset must be integers") from None
    if offset < 0 or (limit is not None and not 1 <= limit <= 500):
        raise ValueError("Finding offset must be nonnegative and limit must be 1 to 500")
    return {"data": selected[offset:offset + limit if limit is not None else None],
            "total": len(selected), "offset": offset, "limit": limit, "sort": sort}
