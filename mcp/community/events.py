"""Atomic metadata event journal and explicit bounded replay contract."""
import re
import time
import uuid

from .store import now

MAX_EVENTS = 1000


class ReplayGap(ValueError):
    """The client must refresh its snapshot before starting a new live stream."""


def append(state, event, payload):
    if not isinstance(event, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,99}", event):
        raise ValueError("Invalid event name")
    if not isinstance(payload, dict):
        raise ValueError("Event metadata must be an object")
    safe = {k: payload[k] for k in ("campaign_id", "run_id", "finding_id", "severity", "status", "retest_id", "pr_id", "state", "provider")
            if isinstance(payload.get(k), str) and 0 < len(payload[k]) <= 200}
    state["event_seq"] = state.get("event_seq", 0) + 1
    stamp = now()
    item = {"id": "evt_" + uuid.uuid4().hex, "event": event, "timestamp": stamp,
            "ts": stamp, "seq": state["event_seq"], "contract_version": "1", "data": safe}
    events = state.setdefault("events", {})
    events[item["id"]] = item
    while len(events) > MAX_EVENTS:
        events.pop(min(events, key=lambda key: events[key]["seq"]))
    for hook in state.get("webhooks", {}).values():
        if hook.get("enabled") and (not hook.get("events") or event in hook["events"] or "*" in hook["events"]):
            delivery = {"id": "delivery_" + uuid.uuid4().hex, "webhook_id": hook["id"], "event": item,
                        "attempts": 0, "next_attempt": time.time(), "status": "pending"}
            state.setdefault("deliveries", {})[delivery["id"]] = delivery
    return item


def replay(store, cursor=None):
    state = store.inspect(lambda state: {"events": dict(state.get("events", {})), "event_seq": state.get("event_seq", 0)})
    rows = sorted(state.get("events", {}).values(), key=lambda row: row["seq"])
    high = state.get("event_seq", 0)
    if cursor is None:
        return [], high
    value = str(cursor)
    if re.fullmatch(r"[0-9]{1,20}", value):
        seq = int(value)
    else:
        matches = [row for row in rows if row["id"] == value]
        if not matches:
            raise ReplayGap("Event cursor is unknown; refresh the workspace snapshot")
        seq = matches[0]["seq"]
    oldest = rows[0]["seq"] if rows else high + 1
    if seq > high or seq < oldest - 1:
        raise ReplayGap("Event cursor is outside retained history; refresh the workspace snapshot")
    return [row for row in rows if row["seq"] > seq], high
