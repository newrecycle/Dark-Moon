"""Offline verification for active-run discovery and bounded log browsing.

No assessment worker is started; all records and log files are local fixtures.
Commercial vendor/runtime parity is deliberately outside this test suite.
"""
import http.client
import json
import os
import threading
import time
from unittest.mock import patch

import test_community as fixtures
from community.jobs import Queue
from community.run_views import (
    MAX_TAIL_BYTES, MAX_TAIL_LINES, active_runs, log_collection, log_detail,
    public_run, stream_chunk,
)
from community.server import HTTPServer, handler_for
from community.store import now


class RunDiscoveryHTTP(fixtures.Fixture):
    request = fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        self.server = HTTPServer(("127.0.0.1", 0),
                                 handler_for(self.service, {"127.0.0.1"}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        super().tearDown()

    def get(self, path, headers=None, auth=True):
        status, body, response_headers = self.request(
            path, headers=headers, auth=auth)
        try:
            return status, json.loads(body), response_headers
        except json.JSONDecodeError:
            return status, body.decode("utf-8"), response_headers

    def role(self, role):
        name = "verify_" + role
        password = "sufficiently-long-passphrase-" + role
        self.service.accounts.create(name, password, role)
        token = self.service.accounts.login(name, password, "127.0.0.1")["token"]
        return {"Authorization": "Bearer " + token}

    def job(self, suffix, status="queued", campaign_id=None, **extra):
        return self.service.store.save("jobs", {
            "id": "job_" + suffix,
            "campaign_id": campaign_id or "campaign_" + suffix,
            "status": status,
            "created_at": "2026-10-28T09:00:00+00:00",
            "spec": {"name": "PRIVATE-NAME", "target": "PRIVATE-TARGET",
                     "api_key": "PRIVATE-KEY", "git_repo": "/private/repo"},
            "error": "PRIVATE-EXCEPTION",
            "remediation": {"repo": "/private/repo", "edits_path": "/private/edits"},
            "env": {"TOKEN": "PRIVATE-ENV"},
            "argv": ["--token", "PRIVATE-ARGV"],
            **extra,
        })

    def test_reserved_routes_empty_and_strict_query(self):
        for path in ("/api/v1/run/active", "/api/v1/run/logs"):
            code, result, headers = self.get(path)
            self.assertEqual(code, 200)
            self.assertEqual(result["data"], [])
            self.assertEqual(result["total"], 0)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(self.get(path, auth=False)[0], 401)
        for path in ("/api/v1/run/active?x=1",
                     "/api/v1/run/active?x=",
                     "/api/v1/run/active?x=1&x=2",
                     "/api/v1/run/logs?missing=1"):
            self.assertEqual(self.get(path)[0], 400, path)
        self.assertEqual(self.get("/api/v1/run/not_present")[0], 404)
        self.assertEqual(self.get("/api/v1/run/logs/not_present")[0], 404)

    def test_queue_lifecycle_active_excludes_every_terminal_state(self):
        statuses = ["queued", "running", "running", "succeeded",
                    "failed", "cancelled", "timed_out", "interrupted"]
        for i, status in enumerate(statuses):
            self.job(str(i), status=status, cancel_requested=i == 2)
        code, result, _ = self.get("/api/v1/run/active")
        self.assertEqual(code, 200)
        self.assertEqual(result["total"], 3)
        self.assertEqual({(r["run_id"], r["state"]) for r in result["data"]},
                         {("job_0", "queued"), ("job_1", "running"),
                          ("job_2", "cancelling")})
        self.assertEqual(result["active_states"], ["queued", "running", "cancelling"])
        self.assertTrue(all(r["id"] == r["run_id"] for r in result["data"]))
        self.assertTrue(all(r["campaign_id"] == "campaign_" + r["id"][4:]
                            for r in result["data"]))
        self.assertNotIn("PRIVATE-", json.dumps(result))

    def test_cancel_transition_and_exact_identity_with_idempotent_stop(self):
        first = self.service.launch({"target": "first.invalid"})
        second = self.service.launch({"target": "second.invalid"})
        self.assertNotEqual(first["id"], first["campaign_id"])
        path = "/api/v1/run/" + first["id"] + "/stop"
        code, stopped, _ = self.get(path)  # GET is not a stop method.
        self.assertNotEqual(code, 200)
        code, body, _ = self.request(path, "DELETE")
        self.assertEqual(code, 200)
        cancelled = json.loads(body)
        self.assertEqual(cancelled["id"], first["id"])
        self.assertEqual(cancelled["run_id"], first["id"])
        self.assertEqual(cancelled["campaign_id"], first["campaign_id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(json.loads(self.request(path, "DELETE")[1]), cancelled)
        self.assertEqual(json.loads(self.request(path, "POST", {})[1]), cancelled)
        self.assertEqual(self.service.store.get("jobs", second["id"])["status"], "queued")
        self.assertEqual(self.get("/api/v1/run/active")[1]["total"], 1)
        self.assertEqual(self.get("/api/v1/run/" + first["id"])[1]["campaign_id"],
                         first["campaign_id"])
        self.assertEqual(self.request(path, "DELETE", auth=False)[0], 401)
        self.assertEqual(self.request("/api/v1/run/missing/stop", "DELETE")[0], 404)

    def test_running_cancellation_state_before_worker_completes(self):
        job = self.job("running", status="running")
        result = self.service.queue.cancel(job["id"])
        self.assertEqual(result["status"], "running")
        code, active, _ = self.get("/api/v1/run/active")
        self.assertEqual(code, 200)
        self.assertEqual(active["data"][0]["state"], "cancelling")
        self.assertTrue(active["data"][0]["cancel_requested"])
        code, matches, _ = self.get("/api/v1/run/logs?status=cancelling")
        self.assertEqual(code, 200)
        self.assertEqual(matches["total"], 1)
        self.service.queue._patch(job["id"], status="cancelled", finished_at=now())
        self.assertEqual(self.get("/api/v1/run/active")[1]["total"], 0)

    def test_log_collection_filters_tie_order_pages_missing_and_empty(self):
        for i, status in enumerate(("running", "failed", "succeeded", "running")):
            self.job(str(i), status=status, campaign_id="campaign_shared")
        self.service.store.job_path("job_1").parent.mkdir(parents=True, exist_ok=True)
        self.service.store.job_path("job_1").write_bytes(b"PRIVATE-LOG\n")
        rows = self.get("/api/v1/run/logs?limit=2&offset=1")[1]
        self.assertEqual(rows["total"], 4)
        self.assertEqual(rows["limit"], 2)
        self.assertEqual(rows["offset"], 1)
        self.assertTrue(rows["has_more"])
        self.assertEqual([r["run_id"] for r in rows["data"]], ["job_2", "job_1"])
        self.assertEqual(rows["data"][1]["log_status"], "available")
        self.assertEqual(rows["data"][1]["log_bytes"], len(b"PRIVATE-LOG\n"))
        self.assertEqual(rows["ordering"], "created_at_desc,id_desc")
        self.assertEqual(rows["content_policy"], "metadata_only")
        self.assertNotIn("PRIVATE-", json.dumps(rows))
        self.assertEqual(self.get("/api/v1/run/logs?status=running")[1]["total"], 2)
        self.assertEqual(self.get("/api/v1/run/logs?campaign_id=campaign_shared")[1]["total"], 4)
        self.assertEqual(self.get("/api/v1/run/logs?run_id=job_0")[1]["total"], 1)
        missing = self.get("/api/v1/run/logs?run_id=job_unknown")[1]
        self.assertEqual(missing["total"], 0)
        self.assertEqual(missing["data"], [])
        self.assertEqual(self.get("/api/v1/run/logs?offset=50")[1]["data"], [])

    def test_malformed_log_queries_and_unknown_status_are_400(self):
        for query in ("limit=0", "limit=101", "limit=-1",
                      "limit=999999999999999999999999", "limit=NaN",
                      "limit=01&limit=02", "limit=", "offset=-1",
                      "offset=100001", "offset=true", "status=unknown",
                      "status=", "status=running&status=failed",
                      "run_id=../../etc", "campaign_id=%2Fetc",
                      "raw=true", "garbage=x"):
            code, _, _ = self.get("/api/v1/run/logs?" + query)
            self.assertEqual(code, 400, query)

    def test_public_serializer_drops_sensitive_fields_in_all_read_paths(self):
        job = self.job("privacy")
        for path in ("/api/v1/run/active", "/api/v1/run/logs",
                     "/api/v1/run/" + job["id"],
                     "/api/v1/jobs/" + job["id"],
                     "/api/v1/jobs", "/api/v1/overview"):
            status, body, _ = self.request(path)
            self.assertEqual(status, 200, path)
            for secret in (b"PRIVATE-NAME", b"PRIVATE-TARGET", b"PRIVATE-KEY",
                           b"PRIVATE-EXCEPTION", b"PRIVATE-ARGV", b"PRIVATE-ENV",
                           b"/private/repo", b"/private/edits"):
                self.assertNotIn(secret, body, (path, secret))
        projected = public_run(job)
        self.assertEqual(projected["run_id"], job["id"])
        self.assertNotIn("spec", projected)
        self.assertNotIn("error", projected)

    def raw_grant(self, job, kind="run"):
        status, body, _ = self.request("/api/v1/evidence/grants", "POST",
                                       {"kind": kind, "id": job["id"]})
        self.assertEqual(status, 201, body)
        return {"X-Darkmoon-Evidence-Grant": json.loads(body)["grant"]}

    def test_log_privacy_roles_and_lifecycle_are_explicit(self):
        job = self.job("secret", status="succeeded",
                       started_at="2026-10-28T09:01:00+00:00",
                       finished_at="2026-10-28T09:02:00+00:00")
        path = self.service.store.job_path(job["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"PRIVATE-SUBPROCESS-OUTPUT\nvisible\n")
        route = "/api/v1/run/logs/" + job["id"]
        status, lifecycle, _ = self.get(route)
        self.assertEqual(status, 200)
        self.assertFalse(lifecycle["raw"])
        self.assertEqual(lifecycle["content_policy"], "structured_lifecycle_only")
        self.assertEqual([x["message"] for x in lifecycle["data"]],
                         ["Run queued", "Run started", "Run finished"])
        self.assertNotIn("PRIVATE-", json.dumps(lifecycle))
        self.assertNotIn("PRIVATE-", self.request("/api/v1/jobs/" + job["id"] + "/log")[1].decode())
        viewer = self.role("viewer")
        analyst = self.role("analyst")
        self.assertEqual(self.get(route, headers=viewer)[0], 200)
        for headers in (viewer, analyst):
            self.assertEqual(self.get(route + "?raw=true", headers=headers)[0], 403)
        self.assertEqual(self.get(route + "?raw=true", auth=False)[0], 401)
        status, raw, _ = self.get(route + "?raw=true", headers=self.raw_grant(job))
        self.assertEqual(status, 200)
        self.assertTrue(raw["raw"])
        self.assertEqual(raw["data"][0]["message"], "PRIVATE-SUBPROCESS-OUTPUT")
        self.assertEqual(raw["content_policy"], "untrusted_admin_opt_in")
        self.assertEqual(self.get(route + "?raw=false")[1]["data"], lifecycle["data"])
        for q in ("?raw=TRUE", "?raw=true&raw=false", "?raw=true&other=1",
                  "?lines=0", "?lines=201", "?lines=1&lines=2"):
            self.assertEqual(self.get(route + q)[0], 400, q)

    def test_bounded_large_files_single_line_and_no_file_traversal(self):
        job = self.job("large")
        path = self.service.store.job_path(job["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"A" * (2 * MAX_TAIL_BYTES) + b"\nshort-last\n")
        with patch("community.run_views.os.read", wraps=os.read) as read:
            status, raw, _ = self.get("/api/v1/run/logs/" + job["id"] + "?raw=true&lines=1", headers=self.raw_grant(job))
        self.assertEqual(status, 200)
        self.assertTrue(raw["truncated"])
        self.assertEqual(raw["data"], [{"type": "untrusted_raw", "message": "short-last"}])
        self.assertTrue(read.called)
        self.assertTrue(all(call.args[1] <= MAX_TAIL_BYTES for call in read.call_args_list))
        path.write_bytes(b"Q" * (2 * MAX_TAIL_BYTES))
        raw = self.get("/api/v1/run/logs/" + job["id"] + "?raw=true", headers=self.raw_grant(job))[1]
        self.assertTrue(all(len(r["message"]) <= 512 for r in raw["data"]))
        self.assertLessEqual(len(raw["data"]), MAX_TAIL_LINES)
        chunk, offset, state, _ = stream_chunk(self.service.store, job["id"], 0)
        self.assertEqual(state, "available")
        self.assertEqual(offset, 8192)
        self.assertEqual(len(chunk), 8192)
        self.assertNotEqual(self.get("/api/v1/run/logs/%2e%2e%2fsecret")[0], 200)

    def test_missing_symlink_directory_and_hardlink_logs_are_not_opened(self):
        job = self.job("unsafe")
        path = self.service.store.job_path(job["id"])
        route = "/api/v1/run/logs/" + job["id"] + "?raw=true"
        self.assertEqual(self.get(route, headers=self.raw_grant(job))[1]["log_status"], "missing")
        self.assertTrue(all(row["type"] == "lifecycle" for row in self.get(route, headers=self.raw_grant(job))[1]["data"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        outside = self.root / "outside-secret.txt"
        outside.write_text("PRIVATE-OUTSIDE")
        path.symlink_to(outside)
        self.assertEqual(self.get(route, headers=self.raw_grant(job))[1]["log_status"], "unavailable")
        self.assertNotIn("PRIVATE-OUTSIDE", json.dumps(self.get(route, headers=self.raw_grant(job))[1]))
        path.unlink()
        path.mkdir()
        self.assertEqual(self.get(route, headers=self.raw_grant(job))[1]["log_status"], "unavailable")
        path.rmdir()
        os.link(outside, path)
        self.assertEqual(self.get(route, headers=self.raw_grant(job))[1]["log_status"], "unavailable")

    def test_sse_terminal_frames_keep_identity_and_hide_output_by_default(self):
        job = self.job("stream", status="succeeded", finished_at=now())
        path = self.service.store.job_path(job["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"PRIVATE-STREAM-OUTPUT\n")
        route = "/api/v1/run/" + job["id"] + "/stream"
        status, body, headers = self.request(route)
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", headers["Content-Type"])
        self.assertIn(b'"type": "run_completed"', body)
        self.assertIn(job["campaign_id"].encode(), body)
        self.assertIn(job["id"].encode(), body)
        self.assertNotIn(b"PRIVATE-STREAM-OUTPUT", body)
        viewer = self.role("viewer")
        self.assertEqual(self.request(route + "?raw=true", headers=viewer)[0], 403)
        self.assertEqual(self.request(route + "?raw=true", auth=False)[0], 401)
        status, untrusted, _ = self.request(route + "?raw=true", headers=self.raw_grant(job, "stream"))
        self.assertEqual(status, 200)
        self.assertIn(b"PRIVATE-STREAM-OUTPUT", untrusted)
        self.assertIn(b'"untrusted": true', untrusted)
        for q in ("?raw=unexpected", "?raw=true&extra=1"):
            self.assertEqual(self.get(route + q)[0], 400)

    def test_sse_rotation_reads_replacement_from_start_and_append_once(self):
        for mode in ("append", "replace_shorter", "replace_longer", "truncate"):
            with self.subTest(mode=mode):
                job = self.job(mode, status="running")
                path = self.service.store.job_path(job["id"])
                path.parent.mkdir(parents=True, exist_ok=True)
                original = b"original-stream-line\n"
                replacement = b"new\n" if mode in {"replace_shorter", "truncate"} else b"replacement-stream-line-longer-than-original\n"
                path.write_bytes(original)
                def change(_seconds):
                    if mode == "append":
                        with path.open("ab") as handle:
                            handle.write(replacement)
                    else:
                        if mode.startswith("replace"):
                            path.rename(path.with_suffix(".old"))
                        path.write_bytes(replacement)
                    self.service.queue._patch(job["id"], status="succeeded", finished_at=now())
                route = "/api/v1/run/" + job["id"] + "/stream?raw=true"
                grant = self.raw_grant(job, "stream")
                with patch("community.server.time.sleep", side_effect=change):
                    status, body, _ = self.request(route, headers=grant)
                self.assertEqual(status, 200)
                frames = [json.loads(line[6:]) for line in body.decode().splitlines() if line.startswith("data: ")]
                self.assertEqual([f["text"] for f in frames if f["type"] == "output"],
                                 [original.decode(), replacement.decode()])
                self.assertEqual(frames[-1]["type"], "run_completed")
                self.assertTrue(all(f["run_id"] == job["id"] and f["campaign_id"] == job["campaign_id"] for f in frames))
                # A reconnect must obtain a fresh one-use grant.
                self.assertEqual(self.request(route, headers=grant)[0], 403)
                status, reconnected, _ = self.request(route, headers=self.raw_grant(job, "stream"))
                self.assertEqual(status, 200)
                outputs = [json.loads(line[6:])["text"] for line in reconnected.decode().splitlines()
                           if line.startswith("data: ") and json.loads(line[6:])["type"] == "output"]
                self.assertEqual(outputs, [(original + replacement if mode == "append" else replacement).decode()])

    def test_sse_rotation_does_not_follow_replacement_symlink(self):
        job = self.job("rotation_link", status="running")
        path = self.service.store.job_path(job["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"original\n")
        outside = self.root / "outside-stream-secret"
        outside.write_bytes(b"PRIVATE-ROTATION-OUTSIDE\n")
        def change(_seconds):
            path.rename(path.with_suffix(".old"))
            path.symlink_to(outside)
            self.service.queue._patch(job["id"], status="succeeded", finished_at=now())
        grant = self.raw_grant(job, "stream")
        with patch("community.server.time.sleep", side_effect=change):
            status, body, _ = self.request("/api/v1/run/" + job["id"] + "/stream?raw=true", headers=grant)
        self.assertEqual(status, 200)
        self.assertIn(b"original", body)
        self.assertNotIn(b"PRIVATE-ROTATION-OUTSIDE", body)
        self.assertIn(b'"type": "run_completed"', body)

    def test_sse_grant_expiry_before_rotated_output_stops_stream(self):
        from community.evidence_access import GRANT_TTL
        job = self.job("rotation_expiry", status="running")
        path = self.service.store.job_path(job["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"before-expiry\n")
        grant = self.raw_grant(job, "stream")
        stamp = time.time()
        with patch("community.server.time.time", return_value=stamp) as clock:
            def expire(_seconds):
                path.rename(path.with_suffix(".old"))
                path.write_bytes(b"PRIVATE-AFTER-GRANT-EXPIRY\n")
                clock.return_value = stamp + GRANT_TTL + 1
            with patch("community.server.time.sleep", side_effect=expire):
                status, body, _ = self.request("/api/v1/run/" + job["id"] + "/stream?raw=true", headers=grant)
        self.assertEqual(status, 200)
        self.assertIn(b"before-expiry", body)
        self.assertIn(b": heartbeat", body)
        self.assertNotIn(b"PRIVATE-AFTER-GRANT-EXPIRY", body)
