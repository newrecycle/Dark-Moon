"""Indexed control state; assessment files remain in api.json_storage."""
import json
import hashlib
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from api import json_storage as data
from .control_state import State, encode, plain, job_keys


def signature(path):
    if path.is_symlink():
        raise ValueError("Control state cannot be a symlink")
    try:
        item = path.stat()
        return [item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns]
    except FileNotFoundError:
        return None


def legacy_digest(path):
    signature(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key in legacy control state")
        result[key] = value
    return result


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}", value):
        raise ValueError("Invalid identifier")
    return value


class Store:
    def __init__(self, root=None):
        self.root = Path(root or data.DATA_DIR / "community")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.path = self.root / "control.sqlite3"
        self.legacy = self.root / "state.json"
        if self.path.is_symlink():
            raise ValueError("Control database cannot be a symlink")
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.close(fd)
        self.path.chmod(0o600)
        with self.connection(check_legacy=False) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS roots(name TEXT PRIMARY KEY,kind TEXT NOT NULL,value TEXT)")
            db.execute("""CREATE TABLE IF NOT EXISTS records(ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
                collection TEXT NOT NULL,key TEXT NOT NULL,payload TEXT NOT NULL,status TEXT,created_at TEXT,
                campaign_id TEXT,schedule_id TEXT,idempotency_key TEXT,state TEXT,UNIQUE(collection,key))""")
            for field in ("status", "state", "campaign_id", "schedule_id", "idempotency_key"):
                db.execute(f"CREATE INDEX IF NOT EXISTS records_{field} ON records(collection,{field},created_at,key)")
            db.execute("CREATE INDEX IF NOT EXISTS records_order ON records(collection,created_at,key)")
            version = db.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()
            if version is None:
                if db.execute("SELECT count(*) FROM roots").fetchone()[0] or db.execute("SELECT count(*) FROM records").fetchone()[0]:
                    raise ValueError("Unversioned control database contains state; reconcile explicitly")
                previous = legacy_digest(self.legacy)
                source = {"jobs": {}, "schedules": {}}
                if previous is not None:
                    source = json.loads(self.legacy.read_text(), object_pairs_hook=unique)
                    if not isinstance(source, dict):
                        raise ValueError("Legacy control state must be an object")
                    collections = {"jobs", "schedules", "credentials", "users", "sessions", "events", "deliveries",
                                   "webhooks", "retests", "evidence_grants", "observation_checkpoint", "schedule_history",
                                   "attack_paths", "attack_path_revisions", "webhook_receipts", "webhook_test_last"}
                    if any(key in source and not isinstance(source[key], dict) for key in collections):
                        raise ValueError("Legacy control collection must be an object")
                    if "event_seq" in source and (type(source["event_seq"]) is not int or source["event_seq"] < 0):
                        raise ValueError("Legacy event sequence must be a nonnegative integer")
                    self.legacy.chmod(0o600)
                target = State(db)
                for key, value in source.items():
                    target[key] = value
                target.flush()
                db.executemany("INSERT INTO settings(key,value) VALUES(?,?)", (
                    ("schema_version", "1"), ("revision", "0"), ("view_revision", "0"), ("legacy_sha256", encode(previous))))
            elif version[0] != "1":
                raise ValueError("Unsupported control database version")
            self.legacy_sha256 = json.loads(db.execute("SELECT value FROM settings WHERE key='legacy_sha256'").fetchone()[0])
            if legacy_digest(self.legacy) != self.legacy_sha256:
                raise ValueError("Legacy control state changed after migration; reconcile explicitly")
            self.legacy_signature = signature(self.legacy)
            db.commit()

    @contextmanager
    def connection(self, check_legacy=True):
        if check_legacy and signature(self.legacy) != self.legacy_signature:
            if legacy_digest(self.legacy) != self.legacy_sha256:
                raise ValueError("Legacy control state changed after migration; reconcile explicitly")
            self.legacy_signature = signature(self.legacy)
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA busy_timeout=30000")
            yield db
        finally:
            db.close()

    def read(self):
        return self.inspect(lambda state: state)

    def inspect(self, action):
        with self.connection() as db:
            db.execute("BEGIN")
            return plain(action(State(db)))

    def update(self, action):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            state = State(db)
            result = plain(action(state))
            state.flush()
            if state.changed:
                db.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")
                internal = {"evidence_grants", "sessions", "events", "event_seq", "observation_checkpoint",
                            "deliveries", "webhook_receipts", "webhook_test_last"}
                if state.changed_roots - internal:
                    db.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='view_revision'")
            db.commit()
            return result

    def get(self, collection, key):
        with self.connection() as db:
            row = db.execute("SELECT payload FROM records WHERE collection=? AND key=?", (collection, identifier(key))).fetchone()
            return json.loads(row[0]) if row else None

    def items(self, collection):
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM records WHERE collection=? ORDER BY ordinal", (collection,))]

    def jobs(self, **query):
        with self.connection() as db:
            db.execute("BEGIN")
            keys, total = job_keys(db, **query)
            rows = State(db).get("jobs", {})
            return [plain(rows[key]) for key in keys], total

    def revision(self):
        with self.connection() as db:
            return int(db.execute("SELECT value FROM settings WHERE key='revision'").fetchone()[0])

    def view_revision(self):
        with self.connection() as db:
            return int(db.execute("SELECT value FROM settings WHERE key='view_revision'").fetchone()[0])

    def save(self, collection, item):
        identifier(item["id"])
        def change(state):
            state.setdefault(collection, {})[item["id"]] = item
            return item
        return self.update(change)

    def job_path(self, job_id):
        return self.root / "logs" / (identifier(job_id) + ".log")
