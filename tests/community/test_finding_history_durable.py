"""SQLite WAL durability, migration and deep-page regression suite.

Never starts an external scan or a commercial vendor. Child processes only
write to the temporary fixture's local SQLite and finding snapshot files.
"""
import concurrent.futures
import json
import os
import sqlite3
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path
from unittest.mock import patch

import test_community as fixtures
from api import json_storage as data
from api import finding_history_sqlite as indexed
from community.finding_lifecycle import history_page

STAMP = "2026-10-28T12:00:00+00:00"


class DurableFindingHistoryTests(fixtures.Fixture):
    def setUp(self):
        super().setUp()
        data.save_target({"id": "t1"})
        data.save_campaign({"id": "c1", "target_id": "t1"})
        self.campaign = {"id": "c1", "target_id": "t1"}

    def event(self, ident, stamp=STAMP, **extra):
        return {"kind": "finding_event", "id": ident, "event": "finding.created",
                "recorded_at": stamp, "campaign_id": "c1", "target_id": "t1",
                "finding_id": ident, "project_id": None, "previous_status": None,
                "status": "confirmed", "source": "fixture", **extra}

    def write_legacy(self, events):
        head = {"kind": "journal_started", "version": 1, "recorded_at": STAMP}
        with data.FINDING_HISTORY_FILE.open("wb") as stream:
            for row in [head, *events]:
                stream.write(json.dumps(row, separators=(",", ":")).encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def test_migrate_preserves_id_extensions_and_repeat_restart(self):
        self.write_legacy([self.event("z", stamp="2026-10-28T12:00:03+00:00",
                                      original_extra={"opaque": "preserved"}),
                           self.event("a"), self.event("b")])
        with patch.dict(os.environ, {"DARKMOON_TEST_ALLOW_HISTORY_REIMPORT": "1"}):
            data.init_finding_history()
        initial = data.load_finding_history()
        self.assertEqual([e["id"] for e in initial["events"]], ["z", "a", "b"])
        self.assertEqual(initial["events"][0]["original_extra"], {"opaque": "preserved"})
        page = data.load_finding_history(target_id="t1", limit=3)
        self.assertEqual([e["id"] for e in page["events"]], ["a", "b", "z"])
        self.assertEqual(page["recording_started_at"], STAMP)
        data.init_finding_history()
        data.init_finding_history()
        self.assertEqual([e["id"] for e in data.load_finding_history()["events"]], ["z", "a", "b"])
        self.assertEqual(indexed.verify()["events"], 3)

    def test_bad_migration_rolls_back_and_exposes_no_partial_index(self):
        self.write_legacy([self.event("okay"), {"kind": "finding_event", "id": "bad"}])
        with patch.dict(os.environ, {"DARKMOON_TEST_ALLOW_HISTORY_REIMPORT": "1"}):
            with self.assertRaises(data.FindingHistoryUnavailable):
                data.init_finding_history()
        with sqlite3.connect(indexed.database_path()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
        self.write_legacy([self.event("restored")])
        with patch.dict(os.environ, {"DARKMOON_TEST_ALLOW_HISTORY_REIMPORT": "1"}):
            data.init_finding_history()
        self.assertEqual(data.load_finding_history(limit=10)["events"][0]["id"], "restored")

    def test_source_disagreement_after_native_write_fails_closed(self):
        event = data.record_finding_event(self.campaign, {"id": "native"}, "finding.created")
        self.assertEqual(data.load_finding_history(limit=2)["events"][0]["id"], event["id"])
        self.write_legacy([self.event("unexpected")])
        with self.assertRaises(data.FindingHistoryUnavailable):
            data.load_finding_history(limit=1)
        with self.assertRaises(data.FindingHistoryUnavailable):
            indexed.verify()
        with sqlite3.connect(indexed.database_path()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)

    def test_selected_index_disagreement_and_explicit_full_verification(self):
        data.record_finding_event(self.campaign, {"id": "one"}, "finding.created")
        data.record_finding_event(self.campaign, {"id": "two"}, "finding.created")
        with sqlite3.connect(indexed.database_path()) as db:
            db.execute("UPDATE events SET payload=? WHERE seq=(SELECT MAX(seq) FROM events)",
                       ('{"kind":"finding_event","id":"changed"}',))
        # A selected row is checked before any public projection is returned.
        with self.assertRaises(data.FindingHistoryUnavailable):
            data.load_finding_history(limit=10)
        with self.assertRaises(data.FindingHistoryUnavailable):
            indexed.verify()

    def test_process_crash_boundaries_recover_or_rollback_without_duplicate_creation(self):
        # A different campaign for each boundary avoids history overlap.
        boundaries = ("before_intent_commit", "after_intent_commit",
                      "before_snapshot_replace", "after_snapshot_replace",
                      "before_apply_mark", "after_apply_mark")
        script = (
            "import sys\n"
            "from pathlib import Path\n"
            "from api import json_storage as d\n"
            "d.FINDING_HISTORY_FILE=Path(sys.argv[1])\n"
            "d.VULNERABILITIES_DIR=Path(sys.argv[2])\n"
            "cid=sys.argv[3]\n"
            "campaign={'id':cid,'target_id':'t1'}\n"
            "def change(rows):\n"
            " if any(r.get('id')==cid for r in rows): return rows,next(r for r in rows if r.get('id')==cid),None,None,'fixture'\n"
            " record={'id':cid,'campaign_id':cid,'target_id':'t1','status':'confirmed'}\n"
            " rows.append(record)\n"
            " return rows,record,'finding.created',None,'fixture'\n"
            "d.mutate_finding_snapshot(campaign,change)\n"
        )
        base_env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "mcp"))
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                cid = "crash_" + boundary
                data.save_campaign({"id": cid, "target_id": "t1"})
                env = dict(base_env, DARKMOON_HISTORY_FAIL_AT=boundary)
                proc = subprocess.run([sys.executable, "-c", script,
                                       str(data.FINDING_HISTORY_FILE),
                                       str(data.VULNERABILITIES_DIR), cid],
                                      env=env, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, timeout=15)
                self.assertEqual(proc.returncode, 97, proc.stderr.decode(errors="replace"))
                # A new process/restart-style init replays pending intents.
                data.init_finding_history()
                snapshot = data.load_vulnerabilities(cid)
                events = [x for x in data.load_finding_history()["events"]
                          if x["finding_id"] == cid]
                committed = boundary != "before_intent_commit"
                self.assertEqual(len(events), int(committed))
                self.assertEqual(len(snapshot), int(committed))
                if committed:
                    # Repeated delivery of the identical creation has no new event.
                    replay = subprocess.run([sys.executable, "-c", script,
                                             str(data.FINDING_HISTORY_FILE),
                                             str(data.VULNERABILITIES_DIR), cid],
                                            env=base_env, capture_output=True, timeout=15)
                    self.assertEqual(replay.returncode, 0, replay.stderr.decode(errors="replace"))
                    self.assertEqual(sum(e["finding_id"] == cid for e in
                                         data.load_finding_history()["events"]), 1)
        self.assertEqual(indexed.verify()["pending"], 0)

    def test_concurrent_snapshot_writers_and_readers_are_consistent(self):
        campaign = self.campaign
        def write(i):
            fid = "parallel_%03d" % i
            def mutate(rows):
                row = {"id": fid, "campaign_id": "c1", "target_id": "t1",
                       "status": "confirmed"}
                rows.append(row)
                return rows, row, "finding.created", None, "fixture"
            data.mutate_finding_snapshot(campaign, mutate)
        errors = []
        def read():
            try:
                for _ in range(16):
                    result = data.load_finding_history(limit=20)
                    self.assertEqual(len(result["events"]), min(result["total"], 20))
            except Exception as exc:
                errors.append(str(exc))
        with concurrent.futures.ThreadPoolExecutor(max_workers=9) as pool:
            futures = [pool.submit(write, i) for i in range(36)]
            futures += [pool.submit(read) for _ in range(3)]
            for f in futures: f.result(timeout=45)
        self.assertEqual(errors, [])
        self.assertEqual(len(data.load_vulnerabilities("c1")), 36)
        self.assertEqual(data.load_finding_history()["total"], 36)
        self.assertEqual(indexed.verify()["pending"], 0)

    def test_stable_snapshot_pages_across_new_backdated_append(self):
        for fid in ("b", "c", "d"):
            data.record_finding_event(self.campaign, {"id": fid}, "finding.created")
        initial = history_page({"limit": ["2"], "offset": ["0"]})
        seq = initial["snapshot_seq"]
        self.assertIsInstance(seq, int)
        # This append can change sorted offsets in the live view.
        data.record_finding_event(self.campaign, {"id": "a"}, "finding.created")
        second = history_page({"limit": ["2"], "offset": ["2"],
                               "snapshot_seq": [str(seq)]})
        self.assertEqual(second["page_consistency"], "snapshot_seq")
        self.assertEqual(second["snapshot_seq"], seq)
        self.assertEqual(second["total"], initial["total"])
        self.assertEqual(len(initial["data"] + second["data"]), 3)
        self.assertEqual(len({e["id"] for e in initial["data"] + second["data"]}), 3)
        self.assertEqual(history_page({"limit": ["10"]})["total"], 4)
        for raw in ("", "-1", "1.5", "9223372036854775808"):
            with self.assertRaises(ValueError):
                history_page({"snapshot_seq": [raw]})

    def test_archive_before_exclusive_is_lossless_without_pruning(self):
        self.write_legacy([self.event("a", stamp="2026-10-27T01:00:00+00:00"),
                           self.event("b", stamp=STAMP)])
        with patch.dict(os.environ, {"DARKMOON_TEST_ALLOW_HISTORY_REIMPORT": "1"}):
            data.init_finding_history()
        out = self.root / "archives" / "archive.json"
        result = indexed.archive(out, before=STAMP)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["deleted"], 0)
        payload = json.loads(out.read_text())
        self.assertEqual([r["id"] for r in payload["events"]], ["a"])
        self.assertEqual(data.load_finding_history(limit=10)["total"], 2)
        with self.assertRaises(FileExistsError):
            indexed.archive(out, before=STAMP)
        self.assertEqual(indexed.verify()["events"], 2)

    def test_deep_page_index_benchmark_vs_memory_not_universal_bound(self):
        # 24k records, many deep pages, and resident allocations of one reader.
        # This test measures the index path, not initial JSONL migration.
        with sqlite3.connect(indexed.database_path()) as db:
            rows = []
            for i in range(24000):
                row = self.event("id_%06d" % i)
                payload = json.dumps(row, separators=(",", ":"))
                import hashlib
                rows.append((row["id"], STAMP, "t1", payload,
                             hashlib.sha256(payload.encode()).hexdigest(), "legacy"))
            db.executemany("INSERT INTO events(id,recorded_at,target_id,payload,payload_sha,origin) VALUES(?,?,?,?,?,?)", rows)
        elapsed = []
        tracemalloc.start()
        try:
            for offset in (0, 4000, 16000, 23000):
                begin = time.perf_counter()
                page = data.load_finding_history(limit=50, offset=offset)
                elapsed.append(round(time.perf_counter() - begin, 5))
                self.assertEqual(page["total"], 24000)
                self.assertEqual(len(page["events"]), 50)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 20 * 1024 * 1024)
        self.assertLess(max(elapsed), 15)
        print("sqlite_indexed_page_seconds offsets=0,4000,16000,23000 values=%s peak_traced_bytes=%d" %
              (elapsed, peak), flush=True)
