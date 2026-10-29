"""Replay gaps, restart checkpoints and producer-backed graph observations."""
import copy
from unittest.mock import patch

import test_community as fixtures
from api import json_storage as data
from api.live_push import push_observed_connection
from community.events import append, replay, ReplayGap
from community.operations import Operations
from community.store import Store


class DurableEvents(fixtures.Fixture):
    def test_restart_detects_offline_transition_without_repeating_events(self):
        snapshot = {"campaigns": [{"id": "c", "status": "running"}], "findings": [], "remediations": []}
        with patch.object(self.service, "snapshot", return_value=snapshot):
            self.service.operations.tick()
            snapshot["campaigns"][0]["status"] = "completed"
            restarted = Operations(self.service)
            restarted.tick()
            events = self.service.store.items("events")
            self.assertEqual([e["event"] for e in events], ["campaign.updated", "campaign.completed"])
            Operations(self.service).tick()
            self.assertEqual(self.service.store.items("events"), events)
        self.assertEqual(replay(Store(self.service.store.root), events[0]["id"])[0], events[1:])

    def test_checkpoint_and_webhook_admission_roll_back_together(self):
        self.service.store.save("webhooks", {"id": "hook", "enabled": True, "events": ["*"]})
        before = self.service.store.read()
        def interrupted(state):
            append(state, "campaign.completed", {"campaign_id": "c", "evidence": "PRIVATE"})
            state["observation_checkpoint"] = {"campaign:c": "completed"}
            raise RuntimeError("interrupted before commit")
        with self.assertRaises(RuntimeError):
            self.service.store.update(interrupted)
        self.assertEqual(self.service.store.read(), before)
        event = self.service.operations.emit("campaign.completed", {"campaign_id": "c", "evidence": "PRIVATE"})
        self.assertEqual(self.service.store.items("deliveries")[0]["event"], event)
        self.assertNotIn("PRIVATE", str(self.service.store.read()))

    def test_evicted_unknown_and_future_cursors_require_resync(self):
        self.service.store.update(lambda state: [append(state, "campaign.updated", {"campaign_id": "c"}) for _ in range(1002)])
        rows = self.service.store.items("events")
        self.assertEqual(len(rows), 1000)
        for cursor in ("0", "1", "1003", "evt_unknown", "-1", "9" * 100):
            with self.subTest(cursor=cursor), self.assertRaises(ReplayGap):
                replay(self.service.store, cursor)
        self.assertEqual(len(replay(self.service.store, "2")[0]), 1000)
        self.assertEqual(replay(self.service.store, "1002"), ([], 1002))


class ProducerObservations(fixtures.Fixture):
    def test_observation_is_idempotent_evidence_bound_and_not_containment(self):
        cid = self.campaign()
        path = data.INFRASTRUCTURE_DIR / (cid + ".json")
        data._write_json(path, [{"id": "a"}, {"id": "b", "parent_id": "a"}])
        findings = data.load_vulnerabilities(cid)
        findings[0]["node_id"] = "b"
        data.save_vulnerabilities(cid, findings)
        self.assertFalse([e for e in self.service.graph(cid)["edges"] if e["kind"] == "observed"])
        args = (cid, "a", "b", findings[0]["id"])
        first = push_observed_connection(*args)
        self.assertEqual(push_observed_connection(*args)["observation_id"], first["observation_id"])
        edge = next(e for e in self.service.graph(cid)["edges"] if e["kind"] == "observed")
        self.assertEqual(edge["basis"], "producer_assertion_with_current_evidence")
        self.assertNotIn("PRIVATE", str(data._read_json(path)))
        findings[0]["evidence"] = {"output": "changed"}
        data.save_vulnerabilities(cid, findings)
        self.assertFalse([e for e in self.service.graph(cid)["edges"] if e["kind"] == "observed"])
        for bad in ((cid, "a", "missing", findings[0]["id"]), (cid, "a", "a", findings[0]["id"]),
                    (cid, "a", "b", "foreign")):
            with self.assertRaises(ValueError):
                push_observed_connection(*bad)
        findings[0]["status"] = "unconfirmed"
        data.save_vulnerabilities(cid, findings)
        with self.assertRaises(ValueError):
            push_observed_connection(*args)
