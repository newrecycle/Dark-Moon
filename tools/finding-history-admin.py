#!/usr/bin/env python3
"""Offline finding-history maintenance. Stop writers before rollback/restore.

Examples:
  python tools/finding-history-admin.py --verify
  python tools/finding-history-admin.py --recover
  python tools/finding-history-admin.py --backup /secure/backup/history.sqlite3
  python tools/finding-history-admin.py --archive /secure/archives/older.json --before 2026-10-28T00:00:00Z
  python tools/finding-history-admin.py --export-jsonl /secure/rollback/history.jsonl
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))
from api import json_storage as data
from api import finding_history_sqlite as indexed


def backup(dest):
    dest = Path(dest)
    if dest.exists() or dest.with_suffix(dest.suffix + ".legacy.jsonl").exists():
        raise FileExistsError("Refusing to overwrite a previous backup")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with data._file_lock(data.FINDING_HISTORY_FILE):
        with sqlite3.connect(str(indexed.database_path())) as source:
            with sqlite3.connect(str(dest)) as target:
                source.backup(target)
        legacy = dest.with_suffix(dest.suffix + ".legacy.jsonl")
        try:
            shutil.copyfile(data.FINDING_HISTORY_FILE, legacy)
        except Exception:
            dest.unlink(missing_ok=True)
            legacy.unlink(missing_ok=True)
            raise
    return {"sqlite": str(dest), "legacy": str(legacy)}


def export_jsonl(dest):
    dest = Path(dest)
    indexed.verify()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(indexed.database_path())) as db:
        db.execute("BEGIN")
        try:
            started = db.execute("SELECT value FROM meta WHERE key='recording_started_at'").fetchone()[0]
            head = {"kind": "journal_started", "recorded_at": started, "version": 1}
            count = 0
            with dest.open("xb") as out:
                try:
                    out.write((json.dumps(head, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
                    for (wire,) in db.execute("SELECT payload FROM events ORDER BY seq"):
                        out.write(wire.encode("utf-8") + b"\n")
                        count += 1
                    out.flush()
                    os.fsync(out.fileno())
                except Exception:
                    dest.unlink(missing_ok=True)
                    raise
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    return {"path": str(dest), "events": count, "source_deleted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--verify", action="store_true")
    commands.add_argument("--recover", action="store_true")
    commands.add_argument("--backup", metavar="FILE")
    commands.add_argument("--export-jsonl", metavar="FILE")
    commands.add_argument("--archive", metavar="FILE")
    parser.add_argument("--before", help="exclusive timezone-aware ISO-8601 bound for --archive")
    args = parser.parse_args()
    if args.before and not args.archive:
        parser.error("--before requires --archive")
    if args.verify:
        result = indexed.verify()
    elif args.recover:
        data.init_finding_history()
        result = {"recovered": True, **indexed.verify()}
    elif args.backup:
        data.init_finding_history()
        result = backup(args.backup)
    elif args.export_jsonl:
        result = export_jsonl(args.export_jsonl)
    else:
        result = indexed.archive(args.archive, before=args.before)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
