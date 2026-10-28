"""Bounded finding journal verification with disposable synthetic JSONL only.

PYTHONPATH=mcp python -m pytest tests/community/test_finding_history_bounded.py -v -s
No assessment, external traffic, vendor runtime or deployment.
"""
import concurrent.futures
import json
import os
import subprocess
import sys
import threading
import time
import tracemalloc
from pathlib import Path
from unittest.mock import patch

import test_community as fixtures
from api import json_storage as data
from community.server import HTTPServer, handler_for


FIELDS = {"id", "event", "recorded_at", "campaign_id", "target_id",
          "project_id", "finding_id", "previous_status", "status", "source"}
DATE = "2026-10-28T12:00:00+00:00"


class BoundedFindingHistoryTests(fixtures.Fixture):
    request = fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        for tid in ("t1", "t2"):
            data.save_target({"id": tid})
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(self.service, {"127.0.0.1"}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        super().tearDown()

    def get(self, suffix=""):
        status, content, _ = self.request("/api/v1/vulnerabilities/history" + suffix)
        return status, json.loads(content)

    def event(self, ident, target="t1", stamp=DATE, **extra):
        return {
            "kind": "finding_event", "id": ident, "event": "finding.created",
            "recorded_at": stamp, "campaign_id": "camp_" + target,
            "target_id": target, "finding_id": "finding_" + ident,
            "project_id": None, "previous_status": None,
            "status": "confirmed", "source": "fixture", **extra,
        }

    def rewrite(self, rows, *, header=None, raw_tail=b""):
        if header is None:
            header = {"kind": "journal_started", "recorded_at": DATE, "version": 1}
        def wire(row):
            if isinstance(row, bytes):
                return row
            return (json.dumps(row, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")
        content = wire(header) + b"".join(wire(row) for row in rows) + raw_tail
        with data._file_lock(data.FINDING_HISTORY_FILE):
            with data.FINDING_HISTORY_FILE.open("wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        return len(content)

    def assert_corrupt(self, rows, *, header=None, raw_tail=b""):
        self.rewrite(rows, header=header, raw_tail=raw_tail)
        with self.assertRaises(data.FindingHistoryUnavailable):
            data.load_finding_history(target_id="t1", limit=1, offset=0)
        for suffix in ("?target_id=t1&limit=1",
                       "?target_id=t2&limit=1&offset=10",
                       "?limit=1&offset=100"):
            status, body = self.get(suffix)
            self.assertEqual(status, 500, suffix)
            self.assertNotIn("data", body)

    def test_reference_fullsort_order_with_interleaving_ties_and_out_of_order_appends(self):
        rows = [
            self.event("z", "t1", "2026-10-28T12:00:05+00:00", private_field="SECRET"),
            self.event("c", "t2", "2026-10-28T12:00:01+00:00"),
            self.event("b", "t1", DATE),
            self.event("a", "t1", DATE),
            self.event("m", "t2", DATE),
            self.event("x", "t1", "2026-10-28T12:00:02+00:00"),
            self.event("b2", "t2", "2026-10-28T12:00:03+00:00"),
        ]
        self.rewrite(rows)
        # The internal full/unpaged contract remains append order and full records.
        unpaged = data.load_finding_history()
        self.assertEqual([e["id"] for e in unpaged["events"]], [r["id"] for r in rows])
        self.assertEqual(unpaged["events"][0]["private_field"], "SECRET")
        for target in (None, "t1", "t2"):
            selected = [r for r in rows if target is None or r["target_id"] == target]
            expected = sorted(selected, key=lambda row: (row["recorded_at"], row["id"]))
            suffix = "" if target is None else "?target_id=" + target
            gathered = []
            for offset in range(0, len(selected) + 3, 2):
                joiner = "&" if suffix else "?"
                status, body = self.get(suffix + joiner + "limit=2&offset=" + str(offset))
                self.assertEqual(status, 200)
                self.assertEqual(body["total"], len(selected))
                self.assertEqual((body["offset"], body["limit"]), (offset, 2))
                self.assertEqual(body["has_more"], offset + len(body["data"]) < len(selected))
                self.assertEqual(body["next_offset"], offset + len(body["data"]) if body["has_more"] else None)
                for value in body["data"]:
                    self.assertEqual(set(value), FIELDS)
                    self.assertNotIn("SECRET", json.dumps(value))
                gathered.extend(body["data"])
            self.assertEqual([e["id"] for e in gathered], [e["id"] for e in expected])
        self.assertEqual([r["id"] for r in data.load_finding_history(limit=2, offset=1)["events"]],
                         [r["id"] for r in sorted(rows, key=lambda x: (x["recorded_at"], x["id"]))[1:3]])

    def test_empty_pages_defaults_ceilings_and_exact_metadata(self):
        self.rewrite([self.event("a"), self.event("b")])
        status, doc = self.get()
        self.assertEqual(status, 200)
        self.assertEqual((doc["limit"], doc["offset"], doc["total"], doc["max_offset"]), (100, 0, 2, 100000))
        self.assertEqual(doc["order"], "recorded_at_asc,id_asc")
        self.assertEqual(doc["page_consistency"], "live_offset")
        self.assertFalse(doc["history_complete"])
        self.assertFalse(doc["has_more"])
        self.assertFalse(doc["paging_limit_reached"])
        self.assertEqual(doc["recording_started_at"], DATE)
        for suffix in ("?limit=500&offset=100000", "?limit=1&offset=3", "?target_id=t2&offset=0"):
            status, row = self.get(suffix)
            self.assertEqual(status, 200)
            self.assertEqual(row["data"], [])
            self.assertFalse(row["has_more"])
            self.assertIsNone(row["next_offset"])
            self.assertFalse(row["paging_limit_reached"])
            self.assertEqual(row["total"], 0 if "target_id=t2" in suffix else 2)
        for suffix in ("?offset=100001", "?offset=9999999999", "?limit=501", "?limit=0",
                       "?limit=", "?offset=", "?limit=1&limit=1"):
            self.assertEqual(self.get(suffix)[0], 400, suffix)
        self.assertEqual(data.load_finding_history(limit=500, offset=100000)["events"], [])
        for invalid in (100001, -1, 1.0, True):
            with self.assertRaises(ValueError):
                data.load_finding_history(limit=1, offset=invalid)
        for invalid in (0, 501, -1, True, 1.5):
            with self.assertRaises(ValueError):
                data.load_finding_history(limit=invalid)

    def test_paging_limit_reached_metadata_without_large_memory_fixture(self):
        from community.finding_lifecycle import history_page
        with patch.object(data, "load_finding_history", return_value={
            "recording_started_at": DATE, "events": [self.event("x")], "total": 100005
        }):
            row = history_page({"offset": ["100000"], "limit": ["1"]})
        self.assertFalse(row["has_more"])
        self.assertTrue(row["paging_limit_reached"])
        self.assertIsNone(row["next_offset"])
        self.assertEqual(row["max_offset"], 100000)

    def test_corruption_on_unselected_target_or_out_of_page_is_storage_failure(self):
        good = self.event("a")
        bad = self.event("z", "t2")
        bad["project_id"] = {"cannot": "be serialized"}
        self.assert_corrupt([good, bad])
        self.assert_corrupt([self.event("a"), self.event("b"), b"{not-json}\n"])
        self.assert_corrupt([good], raw_tail=b'{"kind":"finding_event"')
        self.assert_corrupt([good, self.event("x", "t2", status=["wrong"])])

    def test_invalid_headers_and_header_versions_rejected(self):
        good = self.event("x")
        for header in (
            b"not json\n", b"[]\n", b"null\n", b"\n",
            {"kind": "wrong", "recorded_at": DATE, "version": 1},
            {"kind": "journal_started", "recorded_at": DATE, "version": 2},
            {"kind": "journal_started", "recorded_at": DATE, "version": True},
            {"kind": "journal_started", "recorded_at": DATE, "version": "1"},
            {"kind": "journal_started", "version": 1},
            {"kind": "journal_started", "recorded_at": "2026-10-28T12:00:00", "version": 1},
        ):
            with self.subTest(header=header):
                self.assert_corrupt([good], header=header)

    def test_corrupt_rows_types_json_depth_numbers_utf8_and_missing_fields(self):
        good = self.event("first")
        invalid = [
            b"null\n", b"[]\n", b"1\n", b"\n", b"{}\n",
            b'{"kind":"finding_event","id":NaN}\n',
            b'{"kind":"finding_event","id":Infinity}\n',
            b"{\"nest\":" + b"[" * 1200 + b"1" + b"]" * 1200 + b"}\n",
            b'{"kind":"finding_event","id":' + b"9" * 5000 + b"}\n",
            b"\xff\xfe\x80\n", b'{"broken":true}', b'{"broken":true}\r',
        ]
        for wire in invalid:
            with self.subTest(wire=wire[:35]):
                self.assert_corrupt([good, wire])
        for variant in (
            {"kind": "unexpected"}, {"event": "nonexistent"},
            {"id": ""}, {"finding_id": None}, {"campaign_id": []}, {"target_id": 1},
            {"recorded_at": "2026-10-28T12:00:00"}, {"recorded_at": "bad"},
            {"project_id": []}, {"previous_status": 12}, {"status": {"a": 1}},
            {"source": "x" * 201}, {"finding_id": "\ud800"},
            {"private_extension": {"bad_unicode": "\ud800"}},
        ):
            with self.subTest(variant=variant):
                self.assert_corrupt([good, self.event("bad", "t2", **variant)])

    def test_65536_byte_boundary_counts_newline_and_rejects_65537(self):
        row = self.event("exact", padding="")
        base = json.dumps(row, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"
        self.assertLess(len(base), 65536)
        row["padding"] = "x" * (65536 - len(base))
        exact = json.dumps(row, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"
        self.assertEqual(len(exact), 65536)
        self.rewrite([exact])
        self.assertEqual(self.get("?limit=1")[0], 200)
        self.assertEqual(self.get("?limit=1")[1]["data"][0]["id"], "exact")
        self.assertEqual(data.load_finding_history()["events"][0]["padding"], row["padding"])
        self.assert_corrupt([exact + b"x"])
        self.assert_corrupt([exact[:-1]])  # same-sized prefix but no LF
        self.assert_corrupt([b"x" * 65536 + b"\n"])

    def test_writer_rejects_bad_metadata_without_any_append(self):
        campaign = {"id": "camp", "target_id": "t1"}
        after = data.FINDING_HISTORY_FILE.read_bytes()
        samples = [
            ({"id": "f", "status": "confirmed"}, {"source": ["not", "string"]}),
            ({"id": "f", "status": "confirmed"}, {"source": "\ud800"}),
            ({"id": "f", "status": "confirmed"}, {"source": "x" * 201}),
            ({"id": "f", "status": {"invalid": True}}, {}),
            ({"id": "\ud800", "status": "confirmed"}, {}),
            ({"id": "f", "status": "confirmed"}, {"previous_status": [1], "event": "finding.status_changed"}),
            ({"id": "f", "status": "confirmed"}, {"source": "x" * 65536}),
        ]
        for finding, fields in samples:
            event = fields.pop("event", "finding.created")
            with self.subTest(finding=finding, fields=fields):
                with self.assertRaises(ValueError):
                    data.record_finding_event(campaign, finding, event, **fields)
                self.assertEqual(data.FINDING_HISTORY_FILE.read_bytes(), after)
        for bad_campaign in ({"id": "", "target_id": "t1"}, {"id": "camp", "target_id": None},
                             {"id": "camp", "target_id": "t1", "project_id": ["bad"]}):
            with self.assertRaises(ValueError):
                data.record_finding_event(bad_campaign, {"id": "f", "status": "confirmed"}, "finding.created")
            self.assertEqual(data.FINDING_HISTORY_FILE.read_bytes(), after)

    def test_valid_unicode_fsync_and_restart_without_backfill(self):
        campaign = {"id": "camp", "target_id": "t1", "project_id": "é-東京"}
        finding = {"id": "issue_é", "status": "已確認"}
        with patch.object(data.os, "fsync", wraps=os.fsync) as synced:
            created = data.record_finding_event(campaign, finding, "finding.created", source="手動")
            self.assertGreaterEqual(synced.call_count, 1)
        self.assertEqual(created["project_id"], "é-東京")
        self.assertEqual(self.get("?target_id=t1")[1]["data"][0]["status"], "已確認")
        before = data.FINDING_HISTORY_FILE.read_bytes()
        data.init_finding_history()
        self.assertEqual(data.FINDING_HISTORY_FILE.read_bytes(), before)
        self.assertEqual(data.load_finding_history()["total"], 1)
        data.save_vulnerabilities("camp", [{"id": "older-unrecorded"}])
        self.assertEqual(data.load_finding_history()["total"], 1)
        self.assertEqual(data.load_finding_history()["events"][0]["id"], created["id"])

    def test_threads_and_processes_append_without_lost_or_partial_rows(self):
        campaign = {"id": "camp", "target_id": "t1"}
        def thread_write(i):
            data.record_finding_event(campaign, {"id": "th_" + str(i)}, "finding.created")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(thread_write, range(32)))
        script = (
            "from pathlib import Path\n"
            "import sys\n"
            "from api import json_storage as data\n"
            "data.FINDING_HISTORY_FILE=Path(sys.argv[1])\n"
            "for i in range(12):\n"
            " data.record_finding_event({'id':'c','target_id':'t2'},"
            "{'id':'p'+sys.argv[2]+'_'+str(i)},'finding.created')\n"
        )
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "mcp"))
        workers = [subprocess.Popen([sys.executable, "-c", script, str(data.FINDING_HISTORY_FILE), str(i)],
                                    env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                   for i in range(3)]
        for worker in workers:
            stdout, stderr = worker.communicate(timeout=20)
            self.assertEqual(worker.returncode, 0, stderr.decode("utf-8", "replace"))
        result = data.load_finding_history()
        self.assertEqual(result["total"], 68)
        self.assertEqual(len({r["id"] for r in result["events"]}), 68)
        self.assertEqual(self.get("?target_id=t1")[1]["total"], 32)
        self.assertEqual(self.get("?target_id=t2")[1]["total"], 36)
        data.init_finding_history()
        self.assertEqual(data.load_finding_history()["total"], 68)

    def test_reader_scan_blocks_on_writer_lock_and_unblocks_after_release(self):
        self.rewrite([self.event("a")])
        started, finished = threading.Event(), threading.Event()
        elapsed = []
        def reader():
            started.set()
            begin = time.perf_counter()
            try:
                self.assertEqual(data.load_finding_history(limit=1)["total"], 1)
            finally:
                elapsed.append(time.perf_counter() - begin)
                finished.set()
        with data._file_lock(data.FINDING_HISTORY_FILE):
            thread = threading.Thread(target=reader)
            thread.start()
            self.assertTrue(started.wait(2))
            self.assertFalse(finished.wait(0.15))
        self.assertTrue(finished.wait(2))
        thread.join(2)
        self.assertGreaterEqual(elapsed[0], 0.12)
        print("journal_lock_wait_seconds=%.4f" % elapsed[0], flush=True)

    def test_large_journal_retains_bounded_memory_and_scans_under_lock(self):
        # Large enough to reveal a full-materialization regression without making
        # an ordinary CI gate a benchmark of the runner's disk throughput.
        count = 25000
        with data._file_lock(data.FINDING_HISTORY_FILE):
            with data.FINDING_HISTORY_FILE.open("wb") as out:
                out.write((json.dumps({"kind":"journal_started", "recorded_at":DATE, "version":1})+"\n").encode())
                for i in range(count):
                    row = self.event("event_%06d" % (count - i), "t1" if i % 3 else "t2",
                                     "2026-10-28T12:%02d:%02d+00:00" % (i % 60, i % 59))
                    out.write((json.dumps(row, separators=(",", ":"))+"\n").encode())
                out.flush()
                os.fsync(out.fileno())
        size = data.FINDING_HISTORY_FILE.stat().st_size
        tracemalloc.start()
        begin = time.perf_counter()
        try:
            result = data.load_finding_history(target_id="t1", limit=50, offset=400)
            elapsed = time.perf_counter() - begin
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(result["total"], count - (count + 2)//3)
        self.assertEqual(len(result["events"]), 50)
        self.assertEqual(result["events"], sorted(result["events"], key=lambda r: (r["recorded_at"], r["id"])))
        self.assertLess(peak, 20 * 1024 * 1024, "Bounded page must not load whole journal")
        self.assertLess(elapsed, 30, "Full scan exceeded offline CI budget")
        print("history_benchmark rows=%d bytes=%d elapsed_seconds=%.3f peak_traced_bytes=%d"
              % (count, size, elapsed, peak), flush=True)
