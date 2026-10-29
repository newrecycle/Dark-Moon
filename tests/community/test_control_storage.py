"""Migration, transactional crash recovery and indexed control-state I/O."""
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import tracemalloc
import unittest
from unittest.mock import patch

from community.store import Store


class ControlStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_is_exact_idempotent_and_preserves_legacy(self):
        source = {"jobs": {"j": {"id": "j", "status": "running", "spec": {"target": "fixture"}}},
                  "credentials": {"c": {"id": "c", "sealed": "ciphertext"}}, "event_seq": 12,
                  "sessions": {"s": {"user_id": "u"}}, "observation_checkpoint": {"campaign:c": "running"}}
        legacy = self.root / "state.json"
        raw = json.dumps(source)
        legacy.write_text(raw)
        store = Store(self.root)
        self.assertEqual(store.read(), source)
        self.assertEqual(Store(self.root).read(), source)
        self.assertEqual(legacy.read_text(), raw)
        self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        store.save("jobs", {"id": "j2", "status": "queued"})
        self.assertIn("j2", Store(self.root).read()["jobs"])
        legacy.write_text('{"jobs":{}}')
        for action in (store.read, lambda: Store(self.root)):
            with self.assertRaisesRegex(ValueError, "changed after migration"):
                action()

    def test_bad_legacy_is_not_silently_replaced_or_partly_imported(self):
        for raw in ('[]', '{bad', '{"jobs":{},"jobs":{}}', '{"value":NaN}', '{"jobs":[]}', '{"event_seq":true}'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as root:
                path = Path(root) / "state.json"
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    Store(root)
                self.assertEqual(path.read_text(), raw)
                path.write_text('{"jobs":{}}')
                self.assertEqual(Store(root).read(), {"jobs": {}})

    def test_nested_updates_noop_revision_and_callback_rollback(self):
        store = Store(self.root)
        store.save("jobs", {"id": "j", "status": "queued", "spec": {"count": 1}})
        before = store.read()
        revision = store.revision()
        store.update(lambda state: state.__setitem__("jobs", dict(state["jobs"])))
        self.assertEqual(store.revision(), revision)
        def abort(state):
            state["jobs"]["j"]["spec"]["count"] = 2
            state["event_seq"] = 123
            state.jobs(limit=1)  # Exercise rollback after flushed SQL writes.
            raise RuntimeError("abort")
        with self.assertRaises(RuntimeError):
            store.update(abort)
        self.assertEqual(store.read(), before)
        store.update(lambda state: state["jobs"]["j"].update(status="running", cancel_requested=True))
        rows, count = store.jobs(state="cancelling")
        self.assertEqual(count, 1)
        self.assertEqual(rows[0]["id"], "j")

    def test_internal_grants_do_not_refresh_the_view_that_requested_them(self):
        store = Store(self.root)
        before = store.view_revision()
        store.save("evidence_grants", {"id": "grant", "used": False})
        self.assertEqual(store.view_revision(), before)
        store.save("jobs", {"id": "job", "status": "queued"})
        self.assertGreater(store.view_revision(), before)

    def test_missing_and_empty_timestamps_keep_documented_id_tie_break(self):
        store = Store(self.root)
        for item in ({"id": "z", "status": "queued"}, {"id": "a", "status": "queued", "created_at": ""}):
            store.save("jobs", item)
        self.assertEqual([r["id"] for r in store.jobs()[0]], ["z", "a"])

    def test_process_death_before_commit_does_not_leave_half_a_transaction(self):
        store = Store(self.root)
        store.save("jobs", {"id": "j", "status": "queued"})
        source = """from community.store import Store
import os,sys
s=Store(sys.argv[1])
def abort(state):
 state['jobs']['j']['status']='running'
 state['event_seq']=99
 state.jobs(limit=1)
 os._exit(47)
s.update(abort)
"""
        before = store.read()
        result = subprocess.run([sys.executable, "-c", source, str(self.root)], env=os.environ.copy())
        self.assertEqual(result.returncode, 47)
        self.assertEqual(Store(self.root).read(), before)
        with store.connection() as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_concurrent_writers_and_portable_backup_preserve_every_record(self):
        legacy = self.root / "state.json"
        legacy.write_text('{"counter":{"value":0}}')
        store = Store(self.root)
        def increment(_):
            def change(state):
                state["counter"]["value"] += 1
            store.update(change)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(increment, range(80)))
        self.assertEqual(store.read()["counter"]["value"], 80)
        destination = self.root / "backup"
        destination.mkdir()
        shutil.copyfile(legacy, destination / "state.json")
        with store.connection() as db, sqlite3.connect(destination / "control.sqlite3") as backup:
            db.backup(backup)
        self.assertEqual(Store(destination).read(), store.read())

    def test_large_history_page_and_single_mutation_decode_only_selected_rows(self):
        store = Store(self.root)
        store.update(lambda state: state["jobs"].update({f"j{i:06d}": {
            "id": f"j{i:06d}", "status": "queued" if i < 10 else "succeeded",
            "created_at": "2026-10-29T00:00:00Z", "spec": {"private": "x" * 1024}}
            for i in range(8000)}))
        original = json.loads
        tracemalloc.start()
        started = time.monotonic()
        with patch("community.control_state.json.loads", wraps=original) as decode:
            page, total = store.jobs(limit=25, offset=4000)
            self.assertEqual(total, 8000)
            self.assertEqual(len(page), 25)
            self.assertLessEqual(decode.call_count, 25)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(f"CONTROL_SQLITE_PAGE rows=8000 offset=4000 limit=25 decoded=25 peak={peak}B elapsed={time.monotonic()-started:.4f}s", flush=True)
        self.assertLess(peak, 2 * 1024 * 1024)
        with patch("community.control_state.json.loads", wraps=original) as decode:
            store.update(lambda state: state["jobs"]["j000001"].update(status="running"))
            self.assertLessEqual(decode.call_count, 1)
        with patch("community.control_state.json.loads", wraps=original) as decode:
            self.assertEqual(store.jobs(statuses={"queued", "running"}, limit=0)[1], 10)
            decode.assert_not_called()
        with store.connection() as db:
            plan = db.execute("EXPLAIN QUERY PLAN SELECT count(*) FROM records WHERE collection='jobs' AND status='queued'").fetchall()
            self.assertIn("records_status", str(plan))


class RevisionHints(unittest.TestCase):
    def test_public_snapshot_hints_match_and_grants_do_not_invalidate_them(self):
        import test_community as fixtures
        from community.evidence_access import public_projection
        fixture = fixtures.Fixture()
        fixture.setUp()
        try:
            fixture.campaign()
            service = fixture.service
            snapshot = service.snapshot()
            self.assertEqual(public_projection(snapshot)["workspace_revision"], service.revision())
            service.operations.tick()
            self.assertEqual(service.revision(), snapshot["workspace_revision"])
            service.store.save("evidence_grants", {"id": "grant", "used": False})
            self.assertEqual(service.revision(), snapshot["workspace_revision"])
            service.store.save("jobs", {"id": "job", "status": "queued"})
            self.assertNotEqual(service.revision(), snapshot["workspace_revision"])
        finally:
            fixture.tearDown()
