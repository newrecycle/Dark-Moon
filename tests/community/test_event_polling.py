"""HTTP polling must preserve safe metadata and lossless bounded replay."""
import json
import threading

import test_community as fixtures
from community.events import append
from community.server import HTTPServer, handler_for
from community.store import Store


class EventPollingTests(fixtures.Fixture):
    request = fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(self.service, {"127.0.0.1"}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def poll(self, query="", **options):
        status, body, headers = self.request("/api/v1/events/stream?poll=1" + query, **options)
        return status, json.loads(body), headers

    def test_poll_is_authenticated_json_with_safe_contract_and_restart_cursor(self):
        self.assertEqual(self.poll(auth=False)[0], 401)
        event = self.service.operations.emit("finding.discovered", {
            "finding_id": "finding_one", "campaign_id": "campaign_one", "evidence": "PRIVATE-EVENT"})
        for role in ("viewer", "analyst", "admin"):
            self.service.accounts.create(role, "a-long-fixture-password", role)
            token = self.service.accounts.login(role, "a-long-fixture-password", "127.0.0.1")["token"]
            status, body, headers = self.poll(headers={"Authorization": "Bearer " + token})
            self.assertEqual(status, 200)
            self.assertIn("application/json", headers["Content-Type"])
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(body["cursor"], event["seq"])
            self.assertEqual(body["count"], 1)
            self.assertEqual(body["contract_version"], "1")
            self.assertIn("finding.discovered", body["event_types"])
            self.assertEqual(body["data"][0]["data"]["finding_id"], "finding_one")
            self.assertNotIn("PRIVATE-EVENT", json.dumps(body))
        # The next request uses a new Store connection to persisted state.
        self.assertEqual(Store(self.service.store.root).read()["event_seq"], body["cursor"])
        self.assertEqual(self.poll("&since=" + str(body["cursor"]))[1]["data"], [])

    def test_bounded_filtered_pages_do_not_skip_matching_events(self):
        events = [self.service.operations.emit(name, {"campaign_id": "campaign_one"}) for name in (
            "campaign.started", "finding.discovered", "campaign.updated", "finding.discovered", "campaign.completed")]
        first = self.poll("&events=finding.discovered&limit=1")[1]
        self.assertEqual([row["seq"] for row in first["data"]], [events[1]["seq"]])
        self.assertEqual(first["cursor"], events[1]["seq"])
        second = self.poll("&events=finding.discovered&limit=1&since=" + str(first["cursor"]))[1]
        self.assertEqual([row["seq"] for row in second["data"]], [events[3]["seq"]])
        self.assertEqual(second["cursor"], events[4]["seq"])
        empty = self.poll("&events=pr.opened")[1]
        self.assertEqual((empty["data"], empty["count"], empty["cursor"]), ([], 0, events[-1]["seq"]))

    def test_event_id_header_and_explicit_resync_are_preserved(self):
        first = self.service.operations.emit("campaign.started", {"campaign_id": "c"})
        second = self.service.operations.emit("campaign.completed", {"campaign_id": "c"})
        body = self.poll("&since=0", headers={"Last-Event-ID": first["id"]})[1]
        self.assertEqual([row["seq"] for row in body["data"]], [second["seq"]])
        for query in ("&since=evt_missing", "&since=3", "&since=-1"):
            status, _, headers = self.poll(query)
            self.assertEqual(status, 409)
            self.assertEqual(headers["X-Darkmoon-Resync"], "required")
        self.service.store.update(lambda state: [append(state, "campaign.updated", {}) for _ in range(1000)])
        self.assertEqual(self.poll()[0], 409)
        self.assertEqual(self.poll("&since=2")[1]["count"], 1000)

    def test_poll_query_bounds_are_explicit(self):
        for query in ("&limit=0", "&limit=-1", "&limit=1001", "&limit=bad", "&limit=", "&limit=1&limit=2", "&since=0&since=1", "&unknown=1"):
            with self.subTest(query=query):
                self.assertEqual(self.poll(query)[0], 400)
