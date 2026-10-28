"""Durable, indexed finding history with explicit JSONL migration.

SQLite is authoritative after activation. The original JSONL is retained as
immutable migration evidence. No automatic pruning or synthetic backfill.
"""
import copy
import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

PUBLIC = ("id", "event", "recorded_at", "campaign_id", "target_id",
          "project_id", "finding_id", "previous_status", "status", "source")


def _data():
    from api import json_storage
    return json_storage


def database_path():
    return _data().FINDING_HISTORY_FILE.with_suffix(".sqlite3")


def _checkpoint(name):
    """Test-only process kill at an actual persistence boundary."""
    if os.environ.get("DARKMOON_HISTORY_FAIL_AT") == name:
        os._exit(97)


@contextmanager
def _connect():
    p = database_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(p), timeout=30, isolation_level=None)
    db.execute("PRAGMA busy_timeout=30000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA foreign_keys=ON")
    if db.execute("PRAGMA user_version").fetchone()[0] == 0:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT NOT NULL UNIQUE,
            recorded_at TEXT NOT NULL,
            target_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            payload_sha TEXT NOT NULL,
            origin TEXT NOT NULL,
            event_key TEXT UNIQUE
        );
        CREATE INDEX IF NOT EXISTS events_by_time ON events(recorded_at, id);
        CREATE INDEX IF NOT EXISTS events_by_target_time
            ON events(target_id, recorded_at, id);
        CREATE TABLE IF NOT EXISTS pending(
            op_id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            applied INTEGER NOT NULL DEFAULT 0 CHECK(applied IN (0,1))
        );
        CREATE INDEX IF NOT EXISTS pending_unapplied ON pending(applied);
    """)
        db.execute("PRAGMA user_version=1")
    try:
        yield db
    finally:
        db.close()


def _meta(db, key):
    result = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return result[0] if result else None


def _put(db, key, value):
    db.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, str(value)))


def _fingerprint(path):
    try:
        stat = path.stat()
    except FileNotFoundError:
        return "missing"
    return json.dumps([stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns])


def _import_source(db):
    """Validate every legacy line before committing any imported events."""
    d = _data()
    path = d.FINDING_HISTORY_FILE
    with path.open("rb") as stream:
        header = d._finding_history_row(stream)
        if (header is None or header.get("kind") != "journal_started"
                or type(header.get("version")) is not int or header["version"] != 1):
            raise d.FindingHistoryUnavailable("Legacy finding history header invalid")
        d._finding_history_timestamp(header.get("recorded_at"))
        _put(db, "recording_started_at", header["recorded_at"])
        while True:
            row = d._finding_history_row(stream)
            if row is None:
                break
            d._validate_finding_history_event(row)
            payload = json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            db.execute("INSERT INTO events(id,recorded_at,target_id,payload,payload_sha,origin) VALUES(?,?,?,?,?,?)",
                       (row["id"], row["recorded_at"], row["target_id"], payload,
                        hashlib.sha256(payload.encode("utf-8")).hexdigest(), "legacy"))
    _put(db, "legacy_fingerprint", _fingerprint(path))


def _ensure_locked(db):
    """Caller holds journal sidecar lock; never silently discard changed JSONL."""
    d = _data()
    baseline = _meta(db, "legacy_fingerprint")
    current = _fingerprint(d.FINDING_HISTORY_FILE)
    if baseline is None:
        db.execute("BEGIN IMMEDIATE")
        try:
            if current != "missing":
                _import_source(db)
            else:
                _put(db, "recording_started_at",
                     datetime.now(timezone.utc).isoformat(timespec="microseconds"))
                _put(db, "legacy_fingerprint", current)
            _put(db, "schema_version", 1)
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    elif current != baseline:
        # This opt-in is solely for legacy JSONL rewrite regression fixtures.
        # It is never on in production; no native events may be lost.
        can_reimport = (os.environ.get("DARKMOON_TEST_ALLOW_HISTORY_REIMPORT") == "1"
                        and db.execute("SELECT 1 FROM events WHERE origin='native' LIMIT 1").fetchone() is None
                        and db.execute("SELECT 1 FROM pending LIMIT 1").fetchone() is None)
        if not can_reimport:
            raise d.FindingHistoryUnavailable("Legacy source changed since indexed migration; restore or reconcile explicitly")
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("DELETE FROM events")
            _import_source(db)
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    if _meta(db, "schema_version") != "1":
        raise d.FindingHistoryUnavailable("Unsupported finding history schema")


def _recover_locked(db):
    d = _data()
    for op, cid, before, after in db.execute(
            "SELECT op_id,campaign_id,before_json,after_json FROM pending WHERE applied=0 ORDER BY rowid").fetchall():
        if not isinstance(cid, str) or not cid or cid in (".", "..") or "/" in cid or "\\" in cid:
            raise d.FindingHistoryUnavailable("Pending finding snapshot has an unsafe identity")
        path = d.VULNERABILITIES_DIR / (cid + ".json")
        actual = d._read_json(path)
        old, new = json.loads(before), json.loads(after)
        if actual != new:
            if actual != old:
                raise d.FindingHistoryUnavailable("Finding snapshot diverged from committed history intent")
            _checkpoint("before_snapshot_replace")
            d._write_json(path, new)
        _checkpoint("after_snapshot_replace")
        db.execute("BEGIN IMMEDIATE")
        try:
            _checkpoint("before_apply_mark")
            db.execute("UPDATE pending SET applied=1 WHERE op_id=?", (op,))
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
        _checkpoint("after_apply_mark")


def _check(db):
    d = _data()
    stored = _meta(db, "legacy_fingerprint")
    if stored is not None and stored != _fingerprint(d.FINDING_HISTORY_FILE):
        raise d.FindingHistoryUnavailable("Legacy/index source disagreement")


def initialize():
    d = _data()
    try:
        with d._file_lock(d.FINDING_HISTORY_FILE):
            with _connect() as db:
                _ensure_locked(db)
                _check(db)
                _recover_locked(db)
    except (sqlite3.Error, OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise d.FindingHistoryUnavailable("Finding history initialization failed") from exc


def _prepare_event(campaign, finding, kind, previous, source, *, event_key=None):
    d = _data()
    if kind not in ("finding.created", "finding.status_changed"):
        raise ValueError("Unsupported finding history event")
    row = {"kind": "finding_event", "id": "fh_" + uuid.uuid4().hex,
           "recorded_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
           "event": kind, "campaign_id": campaign.get("id"),
           "target_id": campaign.get("target_id"), "project_id": campaign.get("project_id"),
           "finding_id": finding.get("id"),
           "previous_status": previous if kind == "finding.status_changed" else None,
           "status": finding.get("status"), "source": source}
    try:
        d._validate_finding_history_event(row)
        payload = json.dumps(row, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        if len(payload.encode("utf-8")) + 1 > d.FINDING_HISTORY_MAX_LINE_BYTES:
            raise ValueError("Event metadata exceeds journal limit")
    except (d.FindingHistoryUnavailable, ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("Finding lifecycle metadata is invalid") from exc
    return row, payload, event_key


def _insert(db, item, origin="native"):
    row, payload, event_key = item
    # A stable creation identity prevents replay/duplicate push creating a
    # second creation event. Status changes get distinct operation IDs.
    db.execute("INSERT OR IGNORE INTO events(id,recorded_at,target_id,payload,payload_sha,origin,event_key) VALUES(?,?,?,?,?,?,?)",
               (row["id"], row["recorded_at"], row["target_id"], payload,
                hashlib.sha256(payload.encode("utf-8")).hexdigest(), origin, event_key))
    if db.execute("SELECT changes()").fetchone()[0] == 0:
        if event_key is None:
            raise _data().FindingHistoryUnavailable("Duplicate finding event identity")
        existing = db.execute("SELECT payload FROM events WHERE event_key=?", (event_key,)).fetchone()
        if existing is None:
            raise _data().FindingHistoryUnavailable("Finding event ID collision")
        return json.loads(existing[0])
    return row


def append(campaign, finding, kind, previous=None, source="assessment"):
    d = _data()
    d.init_finding_history()
    item = _prepare_event(campaign, finding, kind, previous, source,
                          event_key=("created:" + campaign["id"] + ":" + finding["id"])
                          if kind == "finding.created" else None)
    try:
        with d._file_lock(d.FINDING_HISTORY_FILE):
            with _connect() as db:
                _ensure_locked(db)
                _recover_locked(db)
                db.execute("BEGIN IMMEDIATE")
                try:
                    inserted = _insert(db, item)
                    db.execute("COMMIT")
                except Exception:
                    db.execute("ROLLBACK")
                    raise
        return inserted
    except (sqlite3.Error, OSError) as exc:
        raise d.FindingHistoryUnavailable("Finding event append failed") from exc


def mutate(campaign, updater):
    """Commit event + pending snapshot atomically; replay JSON mirror on crash.

    updater(current) -> (new_rows, selected_finding, event_kind_or_None,
                         previous_status, source). Called under global lock.
    """
    d = _data()
    cid = campaign["id"]
    if (not isinstance(cid, str) or not cid or cid in (".", "..")
            or "/" in cid or "\\" in cid):
        raise ValueError("Invalid campaign ID for pending snapshot")
    d.init_finding_history()
    try:
        with d._file_lock(d.FINDING_HISTORY_FILE):
            with _connect() as db:
                _ensure_locked(db)
                _recover_locked(db)
                before = d.load_vulnerabilities(cid)
                after, finding, kind, previous, source = updater(copy.deepcopy(before))
                if not isinstance(after, list):
                    raise ValueError("Finding snapshot must be a list")
                if before == after and kind is None:
                    return after, finding
                item = _prepare_event(campaign, finding, kind, previous, source,
                      event_key=("created:" + cid + ":" + finding["id"])
                      if kind == "finding.created" else None) if kind else None
                op_id = uuid.uuid4().hex
                before_wire = json.dumps(before, ensure_ascii=False, allow_nan=False)
                after_wire = json.dumps(after, ensure_ascii=False, allow_nan=False)
                db.execute("BEGIN IMMEDIATE")
                try:
                    if item:
                        _insert(db, item)
                    db.execute("INSERT INTO pending(op_id,campaign_id,before_json,after_json) VALUES(?,?,?,?)",
                               (op_id, cid, before_wire, after_wire))
                    _checkpoint("before_intent_commit")
                    db.execute("COMMIT")
                except Exception:
                    db.execute("ROLLBACK")
                    raise
                _checkpoint("after_intent_commit")
                _recover_locked(db)
                return after, finding
    except (sqlite3.Error, OSError) as exc:
        raise d.FindingHistoryUnavailable("Finding mutation could not be committed") from exc


def read(*, target_id=None, limit=None, offset=0, snapshot_seq=None):
    d = _data()
    if type(offset) is not int or not 0 <= offset <= d.FINDING_HISTORY_MAX_OFFSET:
        raise ValueError("Finding history offset is outside the supported range")
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 500):
        raise ValueError("Finding history limit must be 1 to 500")
    if snapshot_seq is not None and (type(snapshot_seq) is not int or snapshot_seq < 0 or snapshot_seq > 9223372036854775807):
        raise ValueError("Invalid snapshot_seq")
    if not database_path().exists():
        d.init_finding_history()
    try:
        with _connect() as db:
            # No shared journal lock or JSONL rescan on normal indexed pages.
            if _meta(db, "legacy_fingerprint") is None or (
                    _meta(db, "legacy_fingerprint") != _fingerprint(d.FINDING_HISTORY_FILE)) or (
                    db.execute("SELECT 1 FROM pending WHERE applied=0 LIMIT 1").fetchone()):
                initialize()
            _check(db)
            db.execute("BEGIN")
            try:
                high = db.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]
                bound = min(high, snapshot_seq) if snapshot_seq is not None else high
                where = "seq<=?"
                args = [bound]
                if target_id is not None:
                    where += " AND target_id=?"
                    args.append(target_id)
                total = db.execute("SELECT COUNT(*) FROM events WHERE " + where, args).fetchone()[0]
                if limit is None:
                    result = db.execute("SELECT id,target_id,recorded_at,payload,payload_sha FROM events WHERE " + where +
                                        " ORDER BY seq", args).fetchall()
                else:
                    result = db.execute("SELECT id,target_id,recorded_at,payload,payload_sha FROM events WHERE " + where +
                                        " ORDER BY recorded_at,id LIMIT ? OFFSET ?",
                                        args + [limit, offset]).fetchall()
                events = []
                for item_id, target, stamp, payload, digest in result:
                    if hashlib.sha256(payload.encode("utf-8")).hexdigest() != digest:
                        raise d.FindingHistoryUnavailable("Finding index payload checksum mismatch")
                    row = json.loads(payload)
                    d._validate_finding_history_event(row)
                    if row["id"] != item_id or row["target_id"] != target or row["recorded_at"] != stamp:
                        raise d.FindingHistoryUnavailable("Finding index identity disagrees with stored payload")
                    events.append(row)
                if limit is not None:
                    events = [{key: row.get(key) for key in PUBLIC} for row in events]
                started = _meta(db, "recording_started_at")
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return {"recording_started_at": started, "events": events,
                "total": total, "snapshot_seq": bound}
    except (sqlite3.Error, OSError, UnicodeError, TypeError, RecursionError) as exc:
        raise d.FindingHistoryUnavailable("Finding index read failed") from exc


def verify():
    """Explicit operator verification: DB integrity, origin marker, pending replay."""
    initialize()
    with _connect() as db:
        _check(db)
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise _data().FindingHistoryUnavailable("Finding database integrity check failed")
        verified = 0
        for item_id, target, stamp, payload, digest in db.execute(
                "SELECT id,target_id,recorded_at,payload,payload_sha FROM events"):
            if hashlib.sha256(payload.encode("utf-8")).hexdigest() != digest:
                raise _data().FindingHistoryUnavailable("Finding index checksum mismatch")
            row = json.loads(payload)
            _data()._validate_finding_history_event(row)
            if (item_id, target, stamp) != (row["id"], row["target_id"], row["recorded_at"]):
                raise _data().FindingHistoryUnavailable("Finding index identity mismatch")
            verified += 1
        return {"integrity": "ok", "events": verified,
                "pending": db.execute("SELECT COUNT(*) FROM pending WHERE applied=0").fetchone()[0],
                "legacy_fingerprint": _meta(db, "legacy_fingerprint")}


def archive(destination, *, before=None):
    """Lossless operator export; never delete live rows or overwrite an archive."""
    if before is not None:
        _data()._finding_history_timestamp(before)
    initialize()
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as db:
        db.execute("BEGIN")
        try:
            query = "SELECT payload FROM events"
            args = []
            if before:
                query += " WHERE recorded_at<?"
                args.append(before)
            query += " ORDER BY seq"
            rows = [json.loads(row[0]) for row in db.execute(query, args)]
            started = _meta(db, "recording_started_at")
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    document = {"format": "darkmoon-finding-history-archive-v1",
                "recording_started_at": started, "before_exclusive": before,
                "count": len(rows), "events": rows}
    payload = json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")
    document["sha256"] = hashlib.sha256(payload).hexdigest()
    wire = (json.dumps(document, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    with destination.open("xb") as file:
        file.write(wire)
        file.flush()
        os.fsync(file.fileno())
    return {"path": str(destination), "count": len(rows),
            "sha256": document["sha256"], "deleted": 0}
