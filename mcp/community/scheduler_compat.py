"""Conservative flat scheduler request adapter; canonical rules remain authoritative.

Only the original typed field declarations and readable recurrence labels are
used here. This module does not implement vendor scheduling semantics.
"""
from datetime import datetime, timezone

from .calendar_rules import normalize_rule, zone_for


# Original ScheduledCampaignCreate/Update fields in the pinned static audit.
SPEC_FIELDS = frozenset({
    "target", "program", "targets", "out_of_scope", "exclude", "focus",
    "credentials", "tokens", "git_repo", "credential_id", "create_repo",
    "remediate", "noise", "severity", "format", "rules", "safe_harbor",
})
TIMING_FIELDS = frozenset({"scheduled_at", "recurrence", "recurrence_interval"})
FLAT_FIELDS = SPEC_FIELDS | TIMING_FIELDS | {"name"}
_CANONICAL_FIELDS = frozenset({"spec", "rule", "display_name", "enabled", "version"})
_RECURRENCES = frozenset({"once", "daily", "weekly", "monthly"})
_LIST_FIELDS = frozenset({"targets", "out_of_scope", "exclude", "focus", "rules"})
_BOOL_FIELDS = frozenset({"remediate", "create_repo"})


def is_flat_create(raw):
    return isinstance(raw, dict) and (
        bool(TIMING_FIELDS.intersection(raw))
        or ("spec" in raw and bool((SPEC_FIELDS | {"name"}).intersection(raw)))
    )


def is_flat_update(raw):
    return isinstance(raw, dict) and bool(FLAT_FIELDS.intersection(raw))


def _explicit_fields(raw):
    if not isinstance(raw, dict):
        raise ValueError("Schedule body must be an object")
    extra = set(raw) - FLAT_FIELDS - _CANONICAL_FIELDS
    if extra:
        raise ValueError("Unsupported flat schedule fields: " + ", ".join(sorted(extra)))
    for field in FLAT_FIELDS.intersection(raw):
        if raw[field] is None:
            raise ValueError(f"{field} cannot be null; omit it to retain the current value")


def _flat_spec(raw):
    """Convert only evidence-backed launch fields, with no raw secret fallback."""
    converted = {}
    for field in SPEC_FIELDS.intersection(raw):
        value = raw[field]
        if field in {"credentials", "tokens"}:
            raise ValueError(f"{field} cannot be supplied to scheduled launches; use credential_id")
        if field in _LIST_FIELDS:
            if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
                raise ValueError(f"{field} must be an array of nonempty strings")
            if field == "rules":
                if any(";" in v or "\n" in v for v in value):
                    raise ValueError("rules entries must not contain embedded delimiters")
                value = "; ".join(v.strip() for v in value)
        elif field in _BOOL_FIELDS:
            if type(value) is not bool:
                raise ValueError(f"{field} must be boolean")
        elif not isinstance(value, str):
            raise ValueError(f"{field} must be a string")
        if field in {"program", "format"} and not value.strip():
            raise ValueError(f"{field} must not be empty")
        converted["name" if field == "program" else field] = value
    if "name" in raw and (not isinstance(raw["name"], str) or not raw["name"].strip()):
        raise ValueError("name must be a nonempty string")
    return converted


def _spec(raw, validate_spec, existing=None):
    flat = _flat_spec(raw)
    if "spec" in raw:
        canonical = validate_spec(raw["spec"])
        if flat:
            # Compare in the canonical launch vocabulary, not raw aliases.
            merged = validate_spec({**canonical, **flat})
            if merged != canonical:
                raise ValueError("Flat assessment fields contradict the canonical spec")
        return canonical
    if existing is not None:
        return validate_spec({**existing, **flat}) if flat else None
    if "name" in raw and "program" not in raw:
        flat["name"] = raw["name"]
    return validate_spec(flat)


def _date(value):
    if not isinstance(value, str):
        raise ValueError("scheduled_at must be a timezone-aware ISO-8601 timestamp")
    # No implicit local timezone, and no silent loss of subsecond precision.
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("scheduled_at must be a valid ISO-8601 timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("scheduled_at must include a UTC offset")
    if parsed.microsecond:
        raise ValueError("scheduled_at must have whole-second precision")
    return parsed


def _rule(raw, existing=None):
    """Return a calendar rule for supplied flat timing fields only."""
    base = normalize_rule(raw["rule"]) if "rule" in raw else existing
    if not TIMING_FIELDS.intersection(raw):
        return None
    kind = raw.get("recurrence", base["kind"] if base else None)
    if not isinstance(kind, str) or kind not in _RECURRENCES:
        raise ValueError("recurrence must explicitly be once, daily, weekly or monthly; interval is fork-only")
    if "recurrence_interval" in raw:
        every = raw["recurrence_interval"]
        if type(every) is not int or not 1 <= every <= 366:
            raise ValueError("recurrence_interval must be an integer from 1 to 366")
    elif base and base["kind"] == kind:
        every = base["every"]
    elif kind == "once":
        every = 1
    else:
        raise ValueError("recurrence_interval is required for a new daily, weekly or monthly recurrence")
    if kind == "once" and every != 1:
        raise ValueError("recurrence_interval must be 1 or omitted for once")
    if "scheduled_at" in raw:
        supplied = _date(raw["scheduled_at"])
        if not base and kind != "once" and supplied.utcoffset() != timezone.utc.utcoffset(supplied):
            raise ValueError("Recurring flat scheduled_at requires UTC; use a canonical rule for named-zone recurrence")
        zone_name = base["timezone"] if base else "UTC"
        local = supplied.astimezone(zone_for(zone_name))
        start_local = local.replace(tzinfo=None).isoformat(timespec="seconds")
        fold = local.fold
    elif base:
        zone_name = base["timezone"]
        start_local, fold = base["start_local"], base["fold"]
    else:
        raise ValueError("scheduled_at is required when creating a flat schedule")
    result = normalize_rule({"kind": kind, "timezone": zone_name,
                             "start_local": start_local, "every": every, "fold": fold})
    if "rule" in raw and result != base:
        raise ValueError("Flat timing fields contradict the canonical rule")
    return result


def normalize_create(raw, validate_spec):
    """Return a canonical request for creation or preview."""
    if not is_flat_create(raw):
        return raw
    _explicit_fields(raw)
    if "enabled" not in raw or type(raw["enabled"]) is not bool:
        raise ValueError("Flat schedule creation requires an explicit boolean enabled")
    if "rule" not in raw and "scheduled_at" not in raw:
        raise ValueError("Flat schedule creation requires scheduled_at")
    spec = _spec(raw, validate_spec)
    rule = _rule(raw)
    if rule is None:
        rule = normalize_rule(raw["rule"])
    if "display_name" in raw and "name" in raw and raw["display_name"] != raw["name"]:
        raise ValueError("name contradicts display_name")
    name = raw.get("display_name", raw.get("name", spec["name"]))
    return {"spec": spec, "rule": rule, "enabled": raw["enabled"],
            "display_name": name}


def normalize_update(raw, item, validate_spec):
    """Merge a versioned flat edit against the transaction's current record."""
    if not is_flat_update(raw):
        return raw
    _explicit_fields(raw)
    result = {key: raw[key] for key in ("version", "enabled", "display_name") if key in raw}
    if "name" in raw:
        if "display_name" in result and result["display_name"] != raw["name"]:
            raise ValueError("name contradicts display_name")
        result["display_name"] = raw["name"]
    spec = _spec(raw, validate_spec, item["spec"])
    if spec is not None:
        result["spec"] = spec
    if "rule" in raw and not TIMING_FIELDS.intersection(raw):
        result["rule"] = raw["rule"]
    else:
        rule = _rule(raw, item.get("rule"))
        if rule is not None:
            result["rule"] = rule
    return result
