"""Evidence paths cannot manufacture connectivity, cross campaign boundaries or go stale silently."""
import copy
import json
import threading
import concurrent.futures
from unittest.mock import patch

import test_community as fixtures
from api import json_storage as data
from community.attack_paths import create_path, delete_path, list_paths, update_path, path_history, PathConflictError
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
    def test_edit_retains_immutable_revisions_and_original_reviewer_after_restart(self):
        first = self.create()
        updated = update_path(self.service, self.cid, first["id"], self.body | {
            "version": 1, "title": "Second review"}, {"id": "reviewer-two"})
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["recorded_by"], "operator")
        self.assertEqual(updated["reviewed_by"], "reviewer-two")
        self.service.store = Store(self.service.store.root)
        history = path_history(self.service, self.cid, first["id"])
        self.assertEqual([row["version"] for row in history["data"]], [1, 2])
        self.assertEqual(history["data"][0]["title"], first["title"])
        self.assertEqual(history["data"][1]["title"], "Second review")
        history["data"][0]["steps"][0]["rationale"] = "tampered response"
        self.assertNotEqual(path_history(self.service, self.cid, first["id"])["data"][0]["steps"][0]["rationale"], "tampered response")
        self.assertNotIn("PRIVATE-PATH-EVIDENCE", self.service.store.path.read_text())

    def test_simultaneous_same_version_edits_have_one_winner(self):
        first = self.create()
        def edit(number):
            try:
                return update_path(self.service, self.cid, first["id"], self.body | {
                    "version": 1, "title": str(number)}, self.identity)["version"]
            except PathConflictError:
                return "conflict"
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(edit, range(6)))
        self.assertEqual(results.count(2), 1)
        self.assertEqual(results.count("conflict"), 5)
        self.assertEqual(path_history(self.service, self.cid, first["id"])["total"], 2)

    def test_edit_requires_strict_version_and_fresh_review(self):
        first = self.create()
        for update in ({}, {"version": True}, {"version": 0}, {"version": "1"},
                       {"version": 1, "reviewed": False}, {"version": 1, "recorded_by": "forged"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                update_path(self.service, self.cid, first["id"], self.body | update, self.identity)
        self.assertEqual(path_history(self.service, self.cid, first["id"])["total"], 1)

    def test_edit_rechecks_current_evidence_and_connections(self):
        first = self.create()
        self.findings[0]["evidence"]["output"] = "Changed evidence"; self.save_findings()
        self.assertFalse(self.service.graph(self.cid)["paths"][0]["valid"])
        reviewed = update_path(self.service, self.cid, first["id"], self.body | {"version": 1}, self.identity)
        self.assertNotEqual(reviewed["steps"][0]["evidence_sha256"], first["steps"][0]["evidence_sha256"])
        self.assertFalse(path_history(self.service, self.cid, first["id"])["deleted"])
        self.findings[0]["campaign_id"] = "foreign"; self.save_findings()
        with self.assertRaises(ValueError):
            update_path(self.service, self.cid, first["id"], self.body | {"version": 2}, self.identity)
        self.assertEqual(path_history(self.service, self.cid, first["id"])["total"], 2)

    def test_legacy_path_is_lazily_versioned_and_deletion_keeps_history(self):
        first = self.create()
        def legacy(state):
            state["attack_paths"][first["id"]].pop("version")
            state.pop("attack_path_revisions")
        self.service.store.update(legacy)
        self.assertEqual(self.service.graph(self.cid)["paths"][0]["version"], 1)
        self.assertEqual(path_history(self.service, self.cid, first["id"])["total"], 1)
        update_path(self.service, self.cid, first["id"], self.body | {"version": 1}, self.identity)
        delete_path(self.service, self.cid, first["id"])
        history = path_history(self.service, self.cid, first["id"])
        self.assertEqual(history["total"], 2)
        self.assertTrue(history["deleted"])
        self.assertIsNone(history["current_version"])
        self.assertEqual(self.service.graph(self.cid)["paths"], [])
        with self.assertRaises(KeyError): path_history(self.service, "wrong_campaign", first["id"])
        with self.assertRaises(KeyError):
            update_path(self.service, self.cid, first["id"], self.body | {"version": 2}, self.identity)

    def test_revision_limit_rejects_without_mutating_history(self):
        first = self.create()
        self.service.store.update(lambda state: state["attack_paths"][first["id"]].update(version=100))
        before = self.service.store.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "100 immutable"):
            update_path(self.service, self.cid, first["id"], self.body | {"version": 100}, self.identity)
        self.assertEqual(self.service.store.path.read_bytes(), before)

    def test_retained_review_byte_budget_rejects_atomically_without_eviction(self):
        first = self.create()
        before = self.service.store.path.read_bytes()
        with patch("community.attack_paths.MAX_REVIEW_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "8 MiB review payload"):
                update_path(self.service, self.cid, first["id"], self.body | {"version": 1}, self.identity)
            # Deleting a version already retained needs no additional budget.
            self.assertEqual(self.service.store.path.read_bytes(), before)
            delete_path(self.service, self.cid, first["id"])
        self.assertTrue(path_history(self.service, self.cid, first["id"])["deleted"])
        self.assertEqual(path_history(self.service, self.cid, first["id"])["total"], 1)

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

    def granted(self, path):
        status, body, _ = self.request("/api/v1/evidence/grants", "POST",
            {"kind": "graph", "id": self.cid, "campaign_id": self.cid})
        self.assertEqual(status, 201)
        return self.request(path, headers={"X-Darkmoon-Evidence-Grant": json.loads(body)["grant"]})

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
        graph = json.loads(self.granted(f"/api/v1/evidence/graph/{self.cid}/reveal")[1])["data"]
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
        self.assertEqual(status, 400); self.assertEqual(json.loads(body)["error"], "Provide title, steps and explicit reviewed: true")
        self.assertEqual(self.service.store.items("attack_paths"), [])

    def test_versioned_edit_history_conflict_and_role_guards(self):
        first = self.create()
        url = f"/api/v1/campaigns/{self.cid}/paths/{first['id']}"
        body = self.body | {"version": 1, "title": "HTTP review"}
        self.assertEqual(self.request(url, "PUT", body, auth=False)[0], 401)
        self.assertEqual(self.request(url + "/revisions", auth=False)[0], 401)
        self.service.accounts.create("history-viewer", "a-long-viewer-password", "viewer")
        auth = self.service.accounts.issue(self.service.store.get("users", "history-viewer"))["token"]
        headers = {"Authorization": "Bearer " + auth}
        self.assertEqual(self.request(url, "PUT", body, headers=headers)[0], 403)
        self.assertEqual(self.request(url + "/revisions", headers=headers)[0], 200)
        status, response, _ = self.request(url, "PUT", body)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(response)["data"]["version"], 2)
        self.assertEqual(self.request(url, "PUT", body)[0], 409)
        self.assertEqual(self.request(url, "PUT", body | {"version": True})[0], 400)
        self.assertEqual(self.request(url + "/revisions/extra")[0], 404)
        history = json.loads(self.granted(url + "/revisions")[1])
        self.assertEqual(history["current_version"], 2)
        self.assertEqual(history["total"], 2)
        self.assertEqual(self.request(url, "DELETE")[0], 200)
        self.assertTrue(json.loads(self.granted(url + "/revisions")[1])["deleted"])

    def test_history_content_needs_exact_one_use_graph_grant(self):
        first = self.create()
        url = f"/api/v1/campaigns/{self.cid}/paths/{first['id']}/revisions"
        minimal = self.request(url)[1].decode()
        self.assertNotIn("Response supports", minimal)
        self.assertNotIn("rationale", minimal)
        self.assertEqual(self.request(url + "?version=1")[0], 400)
        status, body, _ = self.request("/api/v1/evidence/grants", "POST", {"kind": "graph", "id": self.cid})
        self.assertEqual(status, 201)
        headers = {"X-Darkmoon-Evidence-Grant": json.loads(body)["grant"]}
        status, body, _ = self.request(url, headers=headers)
        self.assertEqual(status, 200)
        self.assertIn("Response supports", body.decode())
        self.assertNotIn("PRIVATE-PATH-EVIDENCE", body.decode())
        self.assertEqual(self.request(url, headers=headers)[0], 403)
