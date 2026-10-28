"""
Darkmoon Dashboard — JSON Storage Layer

Reads/writes all data from filesystem JSON files.
No database. Pure JSON file storage.

Directory layout:
    data/
    ├── projects.json
    ├── targets.json
    ├── campaigns/
    │   └── camp_XXXX.json
    ├── infrastructure/
    │   └── camp_XXXX.json
    ├── vulnerabilities/
    │   └── camp_XXXX.json
    └── reports/
        └── *.md
"""

import fcntl
import json
import tempfile
import threading
from contextlib import contextmanager
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Resolve data directory — use opencode's standard data dir so it lands in the
# volume-mounted path (e.g. ./darkmoon-settings or ./reports on the host).
_OPENDATA_DIR = Path.home() / ".local" / "share" / "opencode"
DATA_DIR = Path(os.environ.get("DARKMOON_DATA_DIR", str(_OPENDATA_DIR))).resolve()

PROJECTS_FILE = DATA_DIR / "projects.json"
TARGETS_FILE = DATA_DIR / "targets.json"
CAMPAIGNS_DIR = DATA_DIR / "campaigns"
INFRASTRUCTURE_DIR = DATA_DIR / "infrastructure"
VULNERABILITIES_DIR = DATA_DIR / "vulnerabilities"
REPORTS_DIR = DATA_DIR / "reports"

# The Pro stack keeps DATA_DIR on a tmpfs (see the compose tmpfs list) and binds a
# separate persistent volume for reports, announced through DARKMOON_REPORTS_DIR.
# Nothing read that variable, so generated reports were written to the tmpfs and
# vanished on the next container restart, while the host-side ./reports directory
# the operator actually looks at stayed empty. Honour it when it is set; Community
# and prod do not set it and keep writing into their volume-mounted data dir
# exactly as before.
_REPORTS_OVERRIDE = os.environ.get("DARKMOON_REPORTS_DIR", "").strip()
if _REPORTS_OVERRIDE:
    REPORTS_DIR = Path(_REPORTS_OVERRIDE)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Any:
    """Read and parse a JSON file. Returns [] if file not found."""
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    """Atomic writes keep the dashboard and concurrent agents on one snapshot."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix="." + path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


_file_locks = {}
_file_locks_guard = threading.Lock()


@contextmanager
def _file_lock(path):
    """Serialize community/agent read-modify-write operations across processes."""
    path = Path(path)
    with _file_locks_guard:
        lock = _file_locks.setdefault(str(path.resolve()), threading.Lock())
    with lock:
        sidecar = path.with_suffix(path.suffix + ".lock")
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        with sidecar.open("a") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def load_projects() -> List[Dict[str, Any]]:
    """Load all projects from projects.json."""
    return _read_json(PROJECTS_FILE)


def load_project(project_id: str) -> Optional[Dict[str, Any]]:
    """Load a single project by ID."""
    for p in load_projects():
        if p.get("id") == project_id:
            return p
    return None


def save_project(project: Dict[str, Any]) -> None:
    """Upsert a project into projects.json."""
    with _file_lock(PROJECTS_FILE):
        projects = load_projects()
        for i, p in enumerate(projects):
            if p.get("id") == project.get("id"):
                projects[i] = project
                _write_json(PROJECTS_FILE, projects)
                return
        projects.append(project)
        _write_json(PROJECTS_FILE, projects)


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

def load_targets() -> List[Dict[str, Any]]:
    """Load all targets from targets.json."""
    return _read_json(TARGETS_FILE)


def load_target(target_id: str) -> Optional[Dict[str, Any]]:
    """Load a single target by ID."""
    for t in load_targets():
        if t.get("id") == target_id:
            return t
    return None


def save_target(target: Dict[str, Any]) -> None:
    """Upsert a target into targets.json."""
    with _file_lock(TARGETS_FILE):
        targets = load_targets()
        for i, t in enumerate(targets):
            if t.get("id") == target.get("id"):
                targets[i] = target
                _write_json(TARGETS_FILE, targets)
                return
        targets.append(target)
        _write_json(TARGETS_FILE, targets)


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

def load_campaigns() -> List[Dict[str, Any]]:
    """Load all campaigns from campaigns/ directory."""
    campaigns = []
    if CAMPAIGNS_DIR.exists():
        for f in sorted(CAMPAIGNS_DIR.glob("*.json")):
            data = _read_json(f)
            if isinstance(data, dict):
                campaigns.append(data)
            elif isinstance(data, list):
                campaigns.extend(data)
    return campaigns


def load_campaign(campaign_id: str) -> Optional[Dict[str, Any]]:
    """Load a single campaign by ID."""
    # Try direct file first
    direct = CAMPAIGNS_DIR / f"{campaign_id}.json"
    if direct.exists():
        data = _read_json(direct)
        if isinstance(data, dict):
            return data
    # Fallback: scan all campaign files
    for c in load_campaigns():
        if c.get("id") == campaign_id:
            return c
    return None


def save_campaign(campaign: Dict[str, Any]) -> None:
    """Save a campaign to campaigns/<campaign_id>.json."""
    campaign_id = campaign.get("id", "unknown")
    path = CAMPAIGNS_DIR / f"{campaign_id}.json"
    _write_json(path, campaign)


# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

def load_infrastructure(campaign_id: str) -> List[Dict[str, Any]]:
    """Load infrastructure nodes for a campaign."""
    path = INFRASTRUCTURE_DIR / f"{campaign_id}.json"
    data = _read_json(path)
    if isinstance(data, list):
        return data
    return []


def save_infrastructure(campaign_id: str, nodes: List[Dict[str, Any]]) -> None:
    """Save infrastructure nodes for a campaign."""
    path = INFRASTRUCTURE_DIR / f"{campaign_id}.json"
    _write_json(path, nodes)


# ---------------------------------------------------------------------------
# Vulnerabilities
# ---------------------------------------------------------------------------

def load_vulnerabilities(campaign_id: str) -> List[Dict[str, Any]]:
    """Load vulnerabilities for a campaign."""
    path = VULNERABILITIES_DIR / f"{campaign_id}.json"
    data = _read_json(path)
    if isinstance(data, list):
        return data
    return []


def load_all_vulnerabilities() -> List[Dict[str, Any]]:
    """Load all vulnerabilities from all campaign files."""
    all_vulns = []
    if VULNERABILITIES_DIR.exists():
        for f in sorted(VULNERABILITIES_DIR.glob("*.json")):
            data = _read_json(f)
            if isinstance(data, list):
                all_vulns.extend(data)
    return all_vulns


def load_vulnerability(vuln_id: str) -> Optional[Dict[str, Any]]:
    """Load a single vulnerability by ID (scans all files)."""
    for v in load_all_vulnerabilities():
        if v.get("id") == vuln_id:
            return v
    return None


def save_vulnerabilities(campaign_id: str, vulns: List[Dict[str, Any]]) -> None:
    """Save vulnerabilities for a campaign."""
    path = VULNERABILITIES_DIR / f"{campaign_id}.json"
    _write_json(path, vulns)


# ---------------------------------------------------------------------------
# Vulnerability helpers
# ---------------------------------------------------------------------------

def _normalize_vulnerability_status(status: Any) -> str:
    return str(status or "unconfirmed").strip().lower()


def _is_open_vulnerability(vuln: Dict[str, Any]) -> bool:
    status = _normalize_vulnerability_status(vuln.get("status"))
    return status not in {"remediated", "resolved", "closed", "fixed"}


def count_open_vulnerabilities_for_campaign(campaign_id: str) -> int:
    return sum(1 for vuln in load_vulnerabilities(campaign_id) if _is_open_vulnerability(vuln))


def count_open_vulnerabilities_for_target(target_id: str) -> int:
    total = 0
    for campaign in load_campaigns():
        if campaign.get("target_id") == target_id:
            total += count_open_vulnerabilities_for_campaign(campaign.get("id", ""))
    return total


# ---------------------------------------------------------------------------
# Reports (Markdown)
# ---------------------------------------------------------------------------

def load_report_content(report_path: str) -> Optional[str]:
    """
    Load a markdown report file.

    report_path can be:
      - An absolute path
      - A relative path like /reports/filename.md (relative to data dir)
      - Just a filename
    """
    # Try as relative to data dir (strip leading /)
    clean = report_path.lstrip("/")
    candidate = DATA_DIR / clean
    if candidate.exists():
        return candidate.read_text(encoding="utf-8")

    # Try in reports dir directly
    fname = Path(report_path).name
    candidate = REPORTS_DIR / fname
    if candidate.exists():
        return candidate.read_text(encoding="utf-8")

    # Try as absolute
    abs_path = Path(report_path)
    if abs_path.exists():
        return abs_path.read_text(encoding="utf-8")

    return None


def list_reports() -> List[str]:
    """List all report filenames."""
    if REPORTS_DIR.exists():
        return [f.name for f in sorted(REPORTS_DIR.glob("*.md"))]
    return []

# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def find_target_by_host_or_ip(host: Optional[str] = None, ip: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Find a target by host or IP.
    Host match is case-insensitive, with subdomain fallback:
    - Exact match wins
    - Then: if queried host is a subdomain of a stored target host, return that target
      (e.g. wp.example.com -> example.com)
    """
    host_norm = (host or "").strip().lower()
    # Strip scheme/path if accidentally included (e.g. https://example.com)
    if "://" in host_norm:
        host_norm = host_norm.split("://", 1)[1].split("/")[0]
    ip_norm = (ip or "").strip()

    subdomain_match = None

    for t in load_targets():
        t_host = str(t.get("host", "")).strip().lower()
        t_ip = str(t.get("ip", "")).strip()

        # Exact match — highest priority
        if host_norm and t_host == host_norm:
            return t
        if ip_norm and t_ip == ip_norm:
            return t

        # Subdomain match — queried host ends with .{stored_host}
        if host_norm and t_host and host_norm.endswith("." + t_host):
            if subdomain_match is None:
                subdomain_match = t

    return subdomain_match


def find_project_by_target_id(target_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Find the unique project linked to a target_id."""
    if not target_id:
        return None

    for p in load_projects():
        if p.get("target_id") == target_id:
            return p

    return None


# ---------------------------------------------------------------------------
# Finding lifecycle journal (events actually recorded since activation only)
# ---------------------------------------------------------------------------
# Keep outside VULNERABILITIES_DIR, which contains campaign snapshots only.
FINDING_HISTORY_FILE = DATA_DIR / "finding-history.jsonl"
FINDING_HISTORY_MAX_LINE_BYTES = 65536
FINDING_HISTORY_MAX_OFFSET = 100000


def _finding_journal_start():
    from datetime import datetime, timezone
    return {"kind": "journal_started", "recorded_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            "version": 1}


def init_finding_history():
    """Create a journal activation marker; do not backfill retained findings."""
    with _file_lock(FINDING_HISTORY_FILE):
        FINDING_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with FINDING_HISTORY_FILE.open("a+", encoding="utf-8") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(json.dumps(_finding_journal_start(), separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())


def record_finding_event(campaign, finding, event, previous_status=None, source="assessment"):
    """Append only an actual finding creation or status mutation."""
    import uuid
    from datetime import datetime, timezone
    if event not in {"finding.created", "finding.status_changed"}:
        raise ValueError("Unsupported finding lifecycle event")
    if not all(isinstance(v, str) and v for v in (campaign.get("id"), finding.get("id"), campaign.get("target_id"))):
        raise ValueError("Finding history requires exact campaign, target and finding IDs")
    row = {"kind": "finding_event", "id": "fh_" + uuid.uuid4().hex,
           "recorded_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
           "event": event, "campaign_id": campaign["id"], "target_id": campaign["target_id"],
           "project_id": campaign.get("project_id"), "finding_id": finding["id"],
           "previous_status": previous_status if event == "finding.status_changed" else None,
           "status": finding.get("status"), "source": source}
    try:
        _validate_finding_history_event(row)
    except FindingHistoryUnavailable as exc:
        raise ValueError("Finding lifecycle metadata is invalid") from exc
    encoded = json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n"
    if len(encoded.encode("utf-8")) > FINDING_HISTORY_MAX_LINE_BYTES:
        raise ValueError("Finding lifecycle metadata exceeds the journal row limit")
    init_finding_history()
    with _file_lock(FINDING_HISTORY_FILE):
        with FINDING_HISTORY_FILE.open("a", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    return row


class FindingHistoryUnavailable(RuntimeError):
    """The persisted finding journal is unreadable or structurally invalid."""


def _finding_history_row(stream):
    """Bound even a malformed, unterminated journal line before decoding it."""
    while True:
        line = stream.readline(FINDING_HISTORY_MAX_LINE_BYTES + 1)
        if not line:
            return None
        if len(line) > FINDING_HISTORY_MAX_LINE_BYTES or not line.endswith(b"\n"):
            raise FindingHistoryUnavailable("Finding history journal has an oversized or incomplete row")
        if not line.strip():
            continue
        row = json.loads(line.decode("utf-8"))
        if not isinstance(row, dict):
            raise FindingHistoryUnavailable("Finding history journal needs object rows")
        return row


def _finding_history_timestamp(value):
    from datetime import datetime
    if not isinstance(value, str) or len(value) > 64:
        raise FindingHistoryUnavailable("Finding history timestamp is unavailable")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("missing timezone")
    except (ValueError, OverflowError) as exc:
        raise FindingHistoryUnavailable("Finding history timestamp is invalid") from exc


def _validate_finding_history_event(row):
    """Validate every row, including rows outside the requested target/page."""
    if row.get("kind") != "finding_event" or row.get("event") not in ("finding.created", "finding.status_changed"):
        raise FindingHistoryUnavailable("Finding history journal contains unexpected data")
    _finding_history_timestamp(row.get("recorded_at"))
    for key in ("id", "campaign_id", "target_id", "finding_id"):
        if not isinstance(row.get(key), str) or not row[key] or len(row[key]) > 200:
            raise FindingHistoryUnavailable("Finding history event identity is unavailable")
    for key in ("project_id", "previous_status", "status", "source"):
        value = row.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > 200):
            raise FindingHistoryUnavailable("Finding history event metadata is invalid")


def load_finding_history(*, target_id=None, limit=None, offset=0):
    """Read validated events, optionally retaining only one bounded sorted page.

    Unpaged callers retain the legacy append-order list. HTTP callers supply a
    limit: the reader scans all lines under the journal lock for an exact total
    and corruption checking, but retains at most offset+limit projected events.
    """
    import heapq
    if type(offset) is not int or not 0 <= offset <= FINDING_HISTORY_MAX_OFFSET:
        raise ValueError("Finding history offset is outside the supported range")
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 500):
        raise ValueError("Finding history limit must be 1 to 500")
    try:
        with _file_lock(FINDING_HISTORY_FILE):
            if not FINDING_HISTORY_FILE.exists():
                return {"recording_started_at": None, "events": [], "total": 0}
            with FINDING_HISTORY_FILE.open("rb") as stream:
                header = _finding_history_row(stream)
                if header is None or header.get("kind") != "journal_started" or type(header.get("version")) is not int or header["version"] != 1:
                    raise FindingHistoryUnavailable("Finding history journal header unavailable")
                _finding_history_timestamp(header.get("recorded_at"))
                total = 0
                safe = ("id", "event", "recorded_at", "campaign_id", "target_id", "project_id",
                        "finding_id", "previous_status", "status", "source")
                def selected():
                    nonlocal total
                    while True:
                        row = _finding_history_row(stream)
                        if row is None:
                            return
                        _validate_finding_history_event(row)
                        if target_id is None or row["target_id"] == target_id:
                            total += 1
                            yield {key: row.get(key) for key in safe} if limit is not None else row
                if limit is None:
                    events = list(selected())
                else:
                    events = heapq.nsmallest(offset + limit, selected(), key=lambda row: (row["recorded_at"], row["id"]))[offset:]
                return {"recording_started_at": header["recorded_at"], "events": events, "total": total}
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise FindingHistoryUnavailable("Finding history journal is unavailable") from exc
