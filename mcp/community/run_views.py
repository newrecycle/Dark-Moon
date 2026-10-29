"""Public run discovery and deliberately bounded, privileged launcher-log reads.

Raw process output is untrusted and may contain credentials. It is never included
in collection endpoints, default detail responses or viewer responses.
"""
import heapq
import os
import stat
from urllib.parse import parse_qs, urlsplit

from .jobs import ACTIVE
from .store import identifier

RUN_STATUSES = frozenset({"queued", "running", "succeeded", "failed", "cancelled", "timed_out", "interrupted"})
FILTER_STATES = RUN_STATUSES | {"cancelling"}
MAX_PAGE = 100
MAX_OFFSET = 100000
MAX_TAIL_BYTES = 65536
MAX_LINE_CHARS = 512
MAX_TAIL_LINES = 200


def public_run(job):
    """Only documented lifecycle metadata: never spread persisted queue records."""
    status = job.get("status")
    if status not in RUN_STATUSES:
        status = "unknown"
    result = {
        "id": identifier(job["id"]),
        "run_id": identifier(job["id"]),
        "campaign_id": job.get("campaign_id") if isinstance(job.get("campaign_id"), str) else None,
        "status": status,
        "state": "cancelling" if status == "running" and job.get("cancel_requested") else status,
        "cancel_requested": bool(job.get("cancel_requested")),
        "kind": "remediation" if job.get("kind") == "remediation" else "assessment",
    }
    for key in ("created_at", "started_at", "finished_at", "schedule_id", "proposal_id"):
        value = job.get(key)
        if isinstance(value, str) and len(value) <= 200:
            result[key] = value
    if type(job.get("exit_code")) is int:
        result["exit_code"] = job["exit_code"]
    return result


def _parameters(handler, allowed):
    params = parse_qs(urlsplit(handler.path).query, keep_blank_values=True)
    if set(params) - set(allowed) or any(len(v) != 1 for v in params.values()):
        raise ValueError("Unsupported or repeated run query parameter")
    return {key: values[0] for key, values in params.items()}


def _positive(params, key, default, ceiling, minimum=0):
    value = params.get(key, str(default))
    if not value.isascii() or not value.isdecimal() or len(value) > 8:
        raise ValueError(key + " must be a decimal integer")
    number = int(value)
    if not minimum <= number <= ceiling:
        raise ValueError(key + " is out of range")
    return number


def _identity_filter(params, key):
    if key not in params:
        return None
    return identifier(params[key])


def _page(jobs, offset, limit):
    """Count matches while retaining at most offset+limit queue references.

    Retained for in-memory compatibility fixtures. Production endpoints use
    indexed Store.jobs queries with count/page reads in one transaction.
    """
    total = 0
    def counted():
        nonlocal total
        for job in jobs:
            total += 1
            yield job
    selected = heapq.nlargest(offset + limit, counted(),
                             key=lambda j: (str(j.get("created_at") or ""), str(j.get("id") or "")))
    return selected[offset:], total


def _pagination(total, offset, limit, count):
    end = offset + count
    remaining = end < total
    has_more = remaining and end <= MAX_OFFSET
    return {"total": total, "limit": limit, "offset": offset,
            "has_more": has_more, "next_offset": end if has_more else None,
            "paging_limit_reached": remaining and not has_more,
            "ordering": "created_at_desc,id_desc", "page_consistency": "live_offset"}


def active_runs(store, handler=None):
    params = _parameters(handler, ("limit", "offset")) if handler is not None else {}
    limit = _positive(params, "limit", 50, MAX_PAGE, 1)
    offset = _positive(params, "offset", 0, MAX_OFFSET)
    page, total = store.jobs(statuses=ACTIVE, offset=offset, limit=limit)
    rows = [public_run(job) for job in page]
    return {"data": rows, **_pagination(total, offset, limit, len(rows)),
            "active_states": ["queued", "running", "cancelling"]}


def log_metadata(store, job):
    """Report only size/availability, never a file path or raw line contents."""
    path = store.job_path(identifier(job["id"]))
    try:
        item = path.lstat()
    except FileNotFoundError:
        return {"log_status": "missing", "log_bytes": 0}
    except OSError:
        return {"log_status": "unavailable", "log_bytes": None}
    if not stat.S_ISREG(item.st_mode) or item.st_nlink != 1:
        return {"log_status": "unavailable", "log_bytes": None}
    return {"log_status": "available", "log_bytes": item.st_size}


def log_collection(store, handler):
    params = _parameters(handler, ("limit", "offset", "status", "campaign_id", "run_id"))
    limit = _positive(params, "limit", 25, MAX_PAGE, 1)
    offset = _positive(params, "offset", 0, MAX_OFFSET)
    status = params.get("status")
    if status is not None and status not in FILTER_STATES:
        raise ValueError("Unsupported run status")
    campaign_id = _identity_filter(params, "campaign_id")
    run_id = _identity_filter(params, "run_id")
    page, total = store.jobs(state=status, campaign_id=campaign_id, run_id=run_id, offset=offset, limit=limit)
    return {"data": [public_run(job) | log_metadata(store, job) for job in page],
            **_pagination(total, offset, limit, len(page)), "content_policy": "metadata_only"}


def _read_chunk(store, job_id, offset=0, count=MAX_TAIL_BYTES, tail=False):
    """No traversal or symlink following; always bounded binary reads."""
    path = store.job_path(identifier(job_id))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return b"", offset, "missing", False
    except OSError:
        return b"", offset, "unavailable", False
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            return b"", offset, "unavailable", False
        size = info.st_size
        start = max(0, size - count) if tail else min(offset, size)
        os.lseek(fd, start, os.SEEK_SET)
        chunk = os.read(fd, min(count, max(0, size - start)))
        return chunk, start + len(chunk), "available", start > 0
    except OSError:
        return b"", offset, "unavailable", False
    finally:
        os.close(fd)


def stream_chunk(store, job_id, offset):
    return _read_chunk(store, job_id, offset=offset, count=8192)


def _lifecycle(job):
    public = public_run(job)
    rows = [{"type": "lifecycle", "message": "Run queued", "timestamp": public.get("created_at"), "status": "queued"}]
    if public.get("started_at"):
        rows.append({"type": "lifecycle", "message": "Run started", "timestamp": public["started_at"], "status": "running"})
    if public["state"] == "cancelling":
        rows.append({"type": "lifecycle", "message": "Cancellation requested", "status": "cancelling"})
    if public.get("finished_at"):
        rows.append({"type": "lifecycle", "message": "Run finished", "timestamp": public["finished_at"], "status": public["status"]})
    return rows


def log_detail(store, handler, job, admin=False):
    params = _parameters(handler, ("lines", "raw"))
    lines = _positive(params, "lines", 100, MAX_TAIL_LINES, 1)
    if params.get("raw", "false") not in ("true", "false"):
        raise ValueError("raw must be true or false")
    raw = params.get("raw") == "true"
    if raw and not admin:
        raise PermissionError("Administrator access is required for raw launcher output")
    public = public_run(job)
    meta = log_metadata(store, job)
    records = _lifecycle(job)
    truncated = False
    if raw:
        chunk, _, state, truncated = _read_chunk(store, job["id"], tail=True)
        meta["log_status"] = state
        if state == "available":
            raw_lines = chunk.decode("utf-8", errors="replace").splitlines()
            if truncated and raw_lines:
                raw_lines = raw_lines[1:]  # The first line may be incomplete.
            truncated = truncated or len(raw_lines) > lines
            records = [{"type": "untrusted_raw", "message": line[:MAX_LINE_CHARS]} for line in raw_lines[-lines:]]
    return {"data": records, "run_id": public["run_id"], "campaign_id": public["campaign_id"],
            "status": public["status"], "state": public["state"],
            **meta, "raw": raw, "truncated": truncated,
            "content_policy": "untrusted_admin_opt_in" if raw else "structured_lifecycle_only"}
