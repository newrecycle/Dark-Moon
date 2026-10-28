"""Calendar rules in named zones, anchored to local civil time rather than ticks.

Gap times are skipped; ambiguous times run once using the selected fold. Months
without the anchor's day are skipped. Existing elapsed intervals stay elapsed.
"""
import calendar
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib.resources import files
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@lru_cache(maxsize=128)
def zone_for(name):
    # Use our declared timezone package consistently instead of whichever
    # distribution database happened to ship on the host. Updates take effect
    # after the application restarts, just like ZoneInfo's normal cache.
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_+./-]+",name) or any(p in {"", ".", ".."} for p in name.split("/")):
        raise ZoneInfoNotFoundError(name)
    try:
        with files("tzdata.zoneinfo").joinpath(*name.split("/")).open("rb") as stream:
            return ZoneInfo.from_file(stream, key=name)
    except ModuleNotFoundError:
        raise ValueError("Calendar timezone data is missing; install the community requirements (tzdata)") from None
    except (OSError, ValueError):
        raise ZoneInfoNotFoundError(name) from None


def local_time(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?", value):
        raise ValueError("Start time must be a local YYYY-MM-DDTHH:MM value without an offset")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid local start date/time") from None


def resolve_local(value, zone, fold):
    candidates = []
    for candidate_fold in (0, 1):
        try:
            utc = value.replace(tzinfo=zone, fold=candidate_fold).astimezone(timezone.utc)
            if utc.astimezone(zone).replace(tzinfo=None) == value and utc not in candidates:
                candidates.append(utc)
        except OverflowError:
            continue
    return sorted(candidates)[min(fold, len(candidates)-1)] if candidates else None


def normalize_rule(raw):
    if not isinstance(raw, dict) or set(raw) - {"kind", "timezone", "start_local", "every", "fold", "seconds"}:
        raise ValueError("Unsupported calendar rule fields")
    kind = raw.get("kind")
    if kind not in {"once", "interval", "daily", "weekly", "monthly"}:
        raise ValueError("Choose once, interval, daily, weekly or monthly")
    name = raw.get("timezone", "UTC")
    if not isinstance(name, str) or len(name) > 100:
        raise ValueError("Choose a named IANA timezone")
    try:
        zone = zone_for(name)
    except ZoneInfoNotFoundError:
        raise ValueError("Unknown IANA timezone") from None
    start = local_time(raw.get("start_local"))
    every, fold = raw.get("every", 1), raw.get("fold", 0)
    if type(every) is not int or not 1 <= every <= 366 or type(fold) is not int or fold not in (0, 1):
        raise ValueError("Every must be an integer from 1 to 366; fold must be 0 or 1")
    result = {"kind": kind, "timezone": name, "start_local": start.isoformat(timespec="seconds"),
              "every": every, "fold": fold}
    if kind in {"once", "interval"} and every != 1:
        raise ValueError("Every applies only to daily, weekly and monthly rules")
    if kind != "interval" and "seconds" in raw:
        raise ValueError("Seconds applies only to elapsed interval rules")
    if kind == "interval":
        seconds = raw.get("seconds")
        if type(seconds) is not int or not 60 <= seconds <= 366*86400:
            raise ValueError("Elapsed interval must be 60 seconds to 366 days")
        result["seconds"] = seconds
    if kind in {"once", "interval"} and resolve_local(start, zone, fold) is None:
        raise ValueError("Start time does not exist in this timezone; choose another time")
    return result


def next_occurrence(rule, after=None):
    start, zone = local_time(rule["start_local"]), zone_for(rule["timezone"])
    kind, every = rule["kind"], rule["every"]
    if after is not None and (after.tzinfo is None or after.utcoffset() is None):
        raise ValueError("Occurrence boundary must have a timezone")
    if kind in {"once", "interval"}:
        first = resolve_local(start, zone, rule["fold"])
        if after is None or first > after:
            return first
        return None if kind == "once" else after + timedelta(seconds=rule["seconds"])
    index = 0
    if after is not None:
        local = after.astimezone(zone).replace(tzinfo=None)
        distance = (local.year-start.year)*12 + local.month-start.month if kind == "monthly" else (local.date()-start.date()).days
        period = every if kind != "weekly" else 7*every
        index = max(0, distance//period - 1)
    for _ in range(5000):
        try:
            if kind == "monthly":
                month = start.year*12 + start.month-1 + index*every
                year, month_index = divmod(month, 12)
                if year > 9999:
                    return None
                value = start.replace(year=year, month=month_index+1) if start.day <= calendar.monthrange(year,month_index+1)[1] else None
            else:
                value = start + timedelta(days=index*every*(7 if kind == "weekly" else 1))
        except (OverflowError, ValueError):
            return None
        index += 1
        utc = resolve_local(value, zone, rule["fold"]) if value else None
        if utc is not None and (after is None or utc > after):
            return utc
    raise ValueError("No valid occurrence found within calendar search bounds")
