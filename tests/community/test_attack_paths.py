"""Evidence paths cannot manufacture connectivity, cross campaign boundaries or go stale silently."""
import copy
import json
import threading

import test_community as fixtures
from api import json_storage as data
from community.attack_paths import create_path, delete_path, list_paths
from community.server import HTTPServer, handler_for
from community.store import Store


class PathFixture(fixtures.Fixture):
    def setUp(self):
        super().setUp()
        self.cid = self.campaign()
        self.nodes = [
            {"id": "a", "label": "Entry", "connections": ["b"]},
            {"id": "b", "label": "Service", "parent_id": "a", "connections": [{"target": "c"}]},
            {"id": "c", "label": "Database"}, {"id": "orphan"},
        ]
        data._write_json(data.INFRASTRUCTURE_DIR / (self.cid + ".json"), self.nodes)
        self.findings = [{"id": "f1", "node_id": "b", "campaign_id": self.cid, "status": "confirmed",
                          "evidence": {"output": "PRIVATE-PATH-EVIDENCE"}},
                         {"id": "f2", "node_id": "c", "campaign_id": self.cid, "status": "exploited",
                          "evidence": {"response": "Recorded DB access"}}]
        self.save_findings()
        graph = self.service.graph(self.cid)
        edges = {(e["source"], e["target"], e["kind"]): e["id"] for e in graph["edges"]}
        self.body = {"title": "Reviewed <script>path</script>", "reviewed": True, "steps": [
            {"edge_id": edges[("a", "b", "observed")], "finding_id": "f1", "rationale": "Response supports entry-to-service connection."},
            {"edge_id": edges[("b", "c", "observed")], "finding_id": "f2", "rationale": "DB response supports service-to-database connection."}]}
        self.identity = {"id": "operator", "role": "operator"}

    def save_findings(self):
        data.save_vulnerabilities(self.cid, self.findings)

    def create(self, body=None):
        return create_path(self.service, self.cid, body or self.body, self.identity)


class AttackPathTests(PathFixture):
    def test_persistence_without_copying_raw_evidence(self):
        result = self.create()
        self.assertTrue(result["valid"])
        self.assertEqual(result["basis"], "operator_review_of_recorded_evidence")
        self.assertEqual(result["recorded_by"], "operator")
        self.assertNotIn("PRIVATE-PATH-EVIDENCE", self.service.store.path.read_text())
        restarted = Store(self.service.store.root)
        paths = list_paths(restarted, self.cid, self.service.graph(self.cid))
        self.assertEqual(paths[0]["id"], result["id"])
        self.assertTrue(paths[0]["valid"])
        self.assertEqual(len(paths[0]["steps"]), 2)

    def test_containment_and_unknown_connections_are_rejected(self):
        graph = self.service.graph(self.cid)
        contains = next(e["id"] for e in graph["edges"] if e["kind"] == "contains")
        self.assertEqual(len([e for e in graph["edges"] if e["source"] == "a" and e["target"] == "b"]), 2)
        for edge_id in (contains, "missing"):
            body = copy.deepcopy(self.body); body["steps"][0]["edge_id"] = edge_id
            with self.assertRaises(ValueError): self.create(body)

    def test_disconnected_and_repeated_edges_are_rejected(self):
        for steps in (list(reversed(self.body["steps"])), self.body["steps"] + self.body["steps"][:1]):
            with self.assertRaisesRegex(ValueError, "contiguous"):
                self.create(self.body | {"steps": steps})

    def test_finding_must_belong_to_current_campaign_and_selected_asset(self):
        for field, value in (("campaign_id", "other_campaign"), ("node_id", "orphan")):
            with self.subTest(field=field):
                original = self.findings[0][field]
                self.findings[0][field] = value; self.save_findings()
                with self.assertRaises(ValueError): self.create()
                self.findings[0][field] = original; self.save_findings()

    def test_unconfirmed_or_empty_evidence_cannot_support_paths(self):
        for update in ({"status": "unconfirmed"}, {"evidence": {}}, {"evidence": {"output": [" ", {}]}}):
            original = copy.deepcopy(self.findings[0]); self.findings[0].update(update); self.save_findings()
            with self.assertRaises(ValueError): self.create()
            self.findings[0] = original; self.save_findings()

    def test_evidence_mutation_disables_persisted_path(self):
        result = self.create()
        self.findings[0]["evidence"]["output"] = "Changed evidence"; self.save_findings()
        record = self.service.graph(self.cid)["paths"][0]
        self.assertEqual(record["id"], result["id"])
        self.assertFalse(record["valid"])
        self.assertIn("evidence changed", record["issues"][0])

    def test_deleted_connection_or_finding_disables_path(self):
        self.create()
        self.nodes[0]["connections"] = []; data._write_json(data.INFRASTRUCTURE_DIR/(self.cid+".json"), self.nodes)
        self.assertFalse(self.service.graph(self.cid)["paths"][0]["valid"])
        self.findings.pop(); self.save_findings()
        self.assertFalse(self.service.graph(self.cid)["paths"][0]["valid"])

    def test_explicit_review_and_bounded_schema(self):
        for update in ({"reviewed": False}, {"title": ""}, {"steps": []}, {"steps": self.body["steps"] * 17}, {"verified": True}):
            with self.assertRaises(ValueError): self.create(self.body | update)
        self.assertEqual(self.service.store.items("attack_paths"), [])

    def test_paths_and_deletion_are_scoped_to_campaign(self):
        path = self.create()
        self.assertEqual(list_paths(self.service.store, "another", self.service.graph(self.cid)), [])
        with self.assertRaises(KeyError): delete_path(self.service, "another", path["id"])
        self.assertTrue(self.service.graph(self.cid)["paths"])
        self.assertEqual(delete_path(self.service, self.cid, path["id"])["deleted"], path["id"])
        self.assertEqual(self.service.graph(self.cid)["paths"], [])


class AttackPathHTTPTests(PathFixture):
    request = fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(self.service, {"127.0.0.1"}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        super().tearDown()

    def test_authorized_create_read_delete_and_graph_contract(self):
        url = f"/api/v1/campaigns/{self.cid}/paths"
        self.assertEqual(self.request(url, auth=False)[0], 401)
        self.assertEqual(self.request(url, "POST", self.body, auth=False)[0], 401)
        status, body, _ = self.request(url, "POST", self.body)
        self.assertEqual(status, 201); path = json.loads(body)["data"]
        self.assertEqual(json.loads(self.request(url)[1])["data"][0]["id"], path["id"])
        graph = json.loads(self.request(f"/api/v1/campaigns/{self.cid}/graph")[1])
        self.assertTrue(graph["paths"][0]["valid"])
        self.assertEqual(self.request(url+"/"+path["id"], "DELETE")[0], 200)
        self.assertEqual(json.loads(self.request(url)[1])["total"], 0)

    def test_viewer_cannot_create_or_delete_paths(self):
        user = self.service.accounts.create("path-viewer", "a-long-viewer-password", "viewer")
        auth = self.service.accounts.issue(self.service.store.get("users", user["id"]))["token"]
        headers = {"Authorization": "Bearer " + auth}
        url = f"/api/v1/campaigns/{self.cid}/paths"
        path = self.create()
        self.assertEqual(self.request(url, headers=headers)[0], 200)
        self.assertEqual(self.request(url, "POST", self.body, headers=headers)[0], 403)
        self.assertEqual(self.request(url+"/"+path["id"], "DELETE", headers=headers)[0], 403)

    def test_invalid_path_returns_actionable_400_without_persistence(self):
        status, body, _ = self.request(f"/api/v1/campaigns/{self.cid}/paths", "POST", self.body | {"reviewed": False})
        self.assertEqual(status, 400); self.assertIn("reviewed", json.loads(body)["error"])
        self.assertEqual(self.service.store.items("attack_paths"), [])
