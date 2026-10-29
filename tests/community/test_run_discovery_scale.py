"""High-cardinality bounded run discovery and live-offset verification.

Synthetic queue rows and local temp dirs only; no queue worker, assessment,
provider, network target, notifications, or vendor binaries. Queries exercise the production indexed Store; storage I/O and memory
bounds are measured in test_control_storage.py.
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import test_community as fixtures
from community.run_views import MAX_OFFSET, active_runs, log_collection
from community.server import HTTPServer, handler_for
import threading


STATES = ("queued", "running", "succeeded", "failed", "cancelled",
          "timed_out", "interrupted")
PRIVATE = "SECRET-DO-NOT-PROJECT"


def job(i, state=None, campaign=None, date=None):
    return {
        "id": f"job_{i:06d}",
        "campaign_id": campaign or f"camp_{i:06d}",
        "created_at": date if date is not None else f"2026-10-{1 + i % 28:02d}T09:00:00Z",
        "status": state or STATES[i % len(STATES)],
        "cancel_requested": i % 11 == 0,
        "spec": {"api_key": PRIVATE, "target": PRIVATE},
        "argv": ["--secret", PRIVATE],
        "env": {"SECRET": PRIVATE},
        "error": PRIVATE,
        "local_path": "/private/path/" + PRIVATE,
        "stdout": PRIVATE,
    }


def handler(path):
    return SimpleNamespace(path=path)


class LargeRunDiscoveryTests(fixtures.Fixture):
    def bulk(self, rows):
        self.service.store.update(lambda state: state["jobs"].update(
            {row["id"]: row for row in rows}))

    def test_keyset_pages_survive_newer_inserts_and_deleted_anchor(self):
        from urllib.parse import urlencode
        records = [job(i, state="queued", date="2026-10-01T00:00:00Z") for i in range(12)]
        self.bulk(records)
        first = active_runs(self.service.store, handler('/api/v1/run/active?pagination=cursor&limit=3'))
        self.assertEqual(first['page_consistency'], 'live_keyset')
        found = [row['id'] for row in first['data']]
        self.bulk([job(99, state="queued", date="2026-10-02T00:00:00Z")])
        self.service.store.update(lambda state: state['jobs'].pop(found[-1]))
        cursor = first['next_cursor']
        while cursor:
            response = active_runs(self.service.store, handler('/api/v1/run/active?' + urlencode({'cursor':cursor, 'limit':3})))
            found.extend(row['id'] for row in response['data'])
            cursor = response['next_cursor']
        self.assertEqual(found, [r['id'] for r in reversed(records)])
        self.assertEqual(len(found), len(set(found)))
        for query in ({'cursor':first['next_cursor'],'offset':1},
                      {'cursor':first['next_cursor'],'pagination':'offset'},
                      {'cursor':'!not-base64!'}, {'pagination':'snapshot'}):
            with self.subTest(query=query), self.assertRaises(ValueError):
                active_runs(self.service.store, handler('/api/v1/run/active?'+urlencode(query)))
        # A token from active discovery cannot be reused for a different filter family.
        with self.assertRaises(ValueError):
            log_collection(self.service.store, handler('/api/v1/run/logs?'+urlencode({'cursor':first['next_cursor']})))

    def test_more_than_one_hundred_mixed_active_and_every_terminal_state(self):
        records = [job(i) for i in range(560)]
        self.bulk(records)
        expected = sorted((r for r in records if r["status"] in ("queued", "running")),
                          key=lambda r: (r["created_at"], r["id"]), reverse=True)
        all_ids = []
        for offset, limit in ((0, 50), (50, 50), (100, 50), (150, 100),
                              (250, 100), (350, 100)):
            with self.subTest(offset=offset, limit=limit):
                page = active_runs(self.service.store,
                    handler(f"/api/v1/run/active?offset={offset}&limit={limit}"))
                want = expected[offset:offset + limit]
                self.assertEqual(page["total"], len(expected))
                self.assertEqual([r["run_id"] for r in page["data"]],
                                 [r["id"] for r in want])
                self.assertEqual(page["limit"], limit)
                self.assertEqual(page["offset"], offset)
                self.assertEqual(page["ordering"], "created_at_desc,id_desc")
                self.assertEqual(page["page_consistency"], "live_offset")
                self.assertEqual(page["has_more"], offset + len(want) < len(expected)
                                 and offset + len(want) <= MAX_OFFSET)
                self.assertEqual(page["next_offset"],
                                 offset + len(want) if page["has_more"] else None)
                self.assertEqual(page["paging_limit_reached"],
                    offset + len(want) < len(expected) and not page["has_more"])
                self.assertNotIn(PRIVATE, json.dumps(page))
                self.assertEqual({r["campaign_id"] for r in page["data"]},
                                 {r["campaign_id"] for r in want})
                all_ids += [r["run_id"] for r in page["data"]]
        self.assertGreater(len(expected), 100)
        self.assertEqual(len(set(all_ids)), len(all_ids))
        self.assertEqual(active_runs(self.service.store)["limit"], 50)
        self.assertEqual(len(active_runs(self.service.store)["data"]), 50)
        self.assertEqual(active_runs(self.service.store,
                         handler("/api/v1/run/active?offset=100000"))["data"], [])
        self.assertEqual(active_runs(self.service.store,
                         handler("/api/v1/run/active?limit=100"))["limit"], 100)
        self.assertEqual(active_runs(self.service.store,
                         handler("/api/v1/run/active?limit=1"))["limit"], 1)
        active = active_runs(self.service.store)
        self.assertTrue(any(r["state"] == "cancelling" for r in active["data"]))
        self.assertTrue(all(r["run_id"] != r["campaign_id"] for r in active["data"]))
        self.assertTrue(all(r["status"] in ("queued", "running") for r in active["data"]))

    def test_indexed_selection_matches_full_sort_over_filters_and_ties(self):
        records = [job(i, date="2026-10-28T09:00:00Z" if i % 3 == 0 else
                       "2026-10-27T09:00:00Z") for i in range(353)]
        records[200]["campaign_id"] = "camp_shared"
        records[201]["campaign_id"] = "camp_shared"
        records[202]["campaign_id"] = "camp_shared"
        self.bulk(records)
        store = self.service.store
        for status in (None, "queued", "running", "cancelling", "failed"):
            for campaign in (None, "camp_shared"):
                for offset, limit in ((0, 1), (0, 50), (25, 40), (50, 100),
                                      (300, 2), (353, 1)):
                    with self.subTest(status=status, campaign=campaign,
                                      offset=offset, limit=limit):
                        params = f"?limit={limit}&offset={offset}"
                        if status: params += "&status=" + status
                        if campaign: params += "&campaign_id=" + campaign
                        subset = [r for r in records
                                  if (status is None or ("cancelling" if
                                      r["status"] == "running" and r["cancel_requested"]
                                      else r["status"]) == status)
                                  and (campaign is None or r["campaign_id"] == campaign)]
                        want = sorted(subset, key=lambda r: (r["created_at"], r["id"]),
                                      reverse=True)[offset:offset + limit]
                        with patch("community.run_views.log_metadata",
                                   return_value={"log_status": "missing", "log_bytes": 0}) as probe:
                            result = log_collection(store, handler("/api/v1/run/logs" + params))
                        self.assertEqual(result["total"], len(subset))
                        self.assertEqual([r["run_id"] for r in result["data"]],
                                         [r["id"] for r in want])
                        self.assertEqual(probe.call_count, len(want))
                        self.assertNotIn(PRIVATE, json.dumps(result))
                        self.assertEqual(result["has_more"],
                                         offset + len(want) < len(subset)
                                         and offset + len(want) <= MAX_OFFSET)
        with patch("community.run_views.log_metadata",
                   return_value={"log_status": "missing", "log_bytes": 0}) as probe:
            selected = log_collection(store, handler("/api/v1/run/logs?run_id=job_000202"))
        self.assertEqual(selected["total"], 1)
        self.assertEqual(selected["data"][0]["campaign_id"], "camp_shared")
        probe.assert_called_once()

    def test_empty_page_and_last_partial_page_are_not_treated_as_empty_total(self):
        records = [job(i, state="queued") for i in range(125)]
        self.bulk(records)
        store = self.service.store
        for offset, expected in ((0, 50), (50, 50), (100, 25), (125, 0), (99999, 0)):
            page = active_runs(store, handler(f"/api/v1/run/active?offset={offset}"))
            self.assertEqual(page["total"], 125)
            self.assertEqual(len(page["data"]), expected)
            self.assertEqual(page["has_more"], offset < 100)
            self.assertEqual(page["next_offset"], offset + expected if offset < 100 else None)

        with patch("community.run_views.MAX_OFFSET", 100):
            ceiling = active_runs(store, handler("/api/v1/run/active?offset=100&limit=10"))
        self.assertFalse(ceiling["has_more"])
        self.assertTrue(ceiling["paging_limit_reached"])
        self.assertIsNone(ceiling["next_offset"])


class LargeRunHTTPTests(fixtures.Fixture):
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

    def test_strict_active_and_history_query_matrix_without_state_mutation(self):
        rows = [job(i) for i in range(165)]
        self.service.store.update(lambda state: state["jobs"].update(
            {row["id"]: row for row in rows}))
        baseline = self.service.store.items("jobs")
        for prefix in ("/api/v1/run/active", "/api/v1/run/logs"):
            for query in ("limit=", "offset=", "limit=0", "limit=101",
                          "limit=-1", "offset=-1", "offset=100001",
                          "limit=1.0", "offset=NaN", "limit=1e2",
                          "limit=%20", "offset=true", "limit=1&limit=2",
                          "offset=0&offset=0", "unknown=1", "unknown=",
                          "status=queued&status=queued" if prefix.endswith("logs") else "other=x"):
                with self.subTest(route=prefix, query=query):
                    status, _, _ = self.request(prefix + "?" + query)
                    self.assertEqual(status, 400)
            self.assertEqual(self.request(prefix, auth=False)[0], 401)
            status, body, _ = self.request(prefix)
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertLessEqual(len(data["data"]), data["limit"])
            self.assertNotIn(PRIVATE.encode(), body)
        self.assertEqual(self.service.store.items("jobs"), baseline)


if __name__ == "__main__":
    import unittest
    unittest.main()
