"""Server-enforced evidence confidentiality and one-use reveal contracts.

Only disposable local HTTP and storage fixtures; no live assessment or delivery.
"""
import concurrent.futures
import json
import threading
import time
from unittest.mock import patch

import test_community as fixtures
from api import json_storage as data
from community.server import HTTPServer, handler_for

EVIDENCE_CANARY = "PRIVATE-EVIDENCE-CANARY-DM-73823"
SOURCE_CANARY = "PRIVATE-SOURCE-PATCH-CANARY-DM-73823"


class EvidenceHTTPTests(fixtures.Fixture):
    request = fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(self.service, {"127.0.0.1"}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cid = self.campaign()
        findings = data.load_vulnerabilities(self.cid)
        findings[0].update(title=SOURCE_CANARY, description=EVIDENCE_CANARY,
                           evidence={"raw_response": EVIDENCE_CANARY},
                           endpoint="https://" + EVIDENCE_CANARY + ".invalid",
                           remediation=SOURCE_CANARY)
        data.save_vulnerabilities(self.cid, findings)
        self.fid = findings[0]["id"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def role(self, role, username):
        self.service.accounts.create(username, "a-long-evidence-access-password", role)
        token = self.service.accounts.login(username, "a-long-evidence-access-password", "127.0.0.1")["token"]
        return {"Authorization": "Bearer " + token}

    def grant(self, kind, item, headers=None, campaign_id=None):
        body = {"kind": kind, "id": item}
        if campaign_id is not None:
            body["campaign_id"] = campaign_id
        status, content, _ = self.request("/api/v1/evidence/grants", "POST", body, headers=headers)
        return status, json.loads(content)

    def reveal(self, kind, item, secret, headers=None):
        return self.request(f"/api/v1/evidence/{kind}/{item}/reveal", headers={
            **(headers or {}), "X-Darkmoon-Evidence-Grant": secret})

    def test_default_workspace_routes_withhold_canaries_for_every_role(self):
        routes = [
            "/api/v1/overview", "/api/v1/campaigns", f"/api/v1/campaigns/{self.cid}",
            f"/api/v1/campaigns/{self.cid}/findings", f"/api/v1/campaigns/{self.cid}/graph",
            f"/api/v1/campaigns/{self.cid}/report.json",
            f"/api/v1/campaigns/{self.cid}/report.md", f"/api/v1/campaigns/{self.cid}/report",
            "/api/v1/findings", "/api/v1/vulnerabilities",
            f"/api/v1/vulnerabilities/{self.fid}", "/api/v1/targets",
            "/api/v1/options", "/api/v1/events/history", "/api/v1/retest",
            "/api/v1/pull-requests",
        ]
        roles = [None, self.role("viewer", "evidence_viewer"),
                 self.role("analyst", "evidence_analyst"), self.role("admin", "evidence_admin")]
        for headers in roles:
            for route in routes:
                status, body, _ = self.request(route, headers=headers) if headers else self.request(route, auth=False)
                if headers is None:
                    self.assertEqual(status, 401, route)
                    continue
                self.assertNotIn(EVIDENCE_CANARY, body.decode("utf-8", "replace"), route)
                self.assertNotIn(SOURCE_CANARY, body.decode("utf-8", "replace"), route)
                self.assertEqual(status, 200, route)
        status, content, _ = self.request(f"/api/v1/campaigns/{self.cid}")
        self.assertEqual(status, 200)
        record = json.loads(content)
        self.assertEqual(record["id"], self.cid)
        self.assertEqual(record["findings"][0]["id"], self.fid)
        self.assertNotIn("evidence", record["findings"][0])

    def test_analyst_viewer_anonymous_and_wrong_scopes_are_denied(self):
        viewer = self.role("viewer", "grant_viewer")
        analyst = self.role("analyst", "grant_analyst")
        for headers in (viewer, analyst):
            self.assertEqual(self.grant("finding", self.fid, headers)[0], 403)
        self.assertEqual(self.request("/api/v1/evidence/grants", "POST",
                                      {"kind": "finding", "id": self.fid}, auth=False)[0], 401)
        self.assertEqual(self.grant("finding", self.fid, campaign_id="other_campaign")[0], 403)
        self.assertEqual(self.grant("finding", "no_such_finding")[0], 404)
        self.assertEqual(self.grant("unbounded", self.fid)[0], 400)
        self.assertEqual(self.reveal("finding", self.fid, "forged-arbitrary-random-secret-value")[0], 403)

    def test_single_use_reveal_and_safe_default_afterwards(self):
        status, issued = self.grant("finding", self.fid, campaign_id=self.cid)
        self.assertEqual(status, 201)
        self.assertEqual(issued["resource"]["campaign_id"], self.cid)
        self.assertLessEqual(issued["expires_in"], 60)
        status, body, _ = self.reveal("finding", self.fid, issued["grant"])
        self.assertEqual(status, 200)
        self.assertIn(EVIDENCE_CANARY, body.decode())
        self.assertEqual(json.loads(body)["data"]["id"], self.fid)
        self.assertEqual(self.reveal("finding", self.fid, issued["grant"])[0], 403)
        default = self.request(f"/api/v1/vulnerabilities/{self.fid}")[1]
        self.assertNotIn(EVIDENCE_CANARY, default.decode())
        self.assertNotIn(SOURCE_CANARY, default.decode())

    def test_wrong_kind_id_campaign_and_cross_session_substitution(self):
        second = "separate_campaign"
        data.save_target({"id": "separate_target"})
        data.save_campaign({"id": second, "target_id": "separate_target"})
        data.save_vulnerabilities(second, [{"id": "unique_second_finding",
                                            "campaign_id": second, "target_id": "separate_target"}])
        token = self.grant("finding", self.fid)[1]["grant"]
        self.assertEqual(self.reveal("finding", "other_finding", token)[0], 404)
        self.assertEqual(self.reveal("campaign", self.cid, token)[0], 403)
        admin = self.role("admin", "other_evidence_admin")
        self.assertEqual(self.reveal("finding", self.fid, token, admin)[0], 403)
        # A failed attempt cannot rewrite the token's original scope.
        self.assertEqual(self.reveal("finding", self.fid, token)[0], 200)
        other_finding = data.load_vulnerabilities(second)[0]["id"]
        self.assertEqual(self.grant("finding", other_finding, campaign_id=self.cid)[0], 403)

    def test_revocation_expiry_logout_and_parallel_claims(self):
        admin = self.role("admin", "ephemeral_evidence_admin")
        status, issued = self.grant("finding", self.fid, admin)
        self.assertEqual(status, 201)
        self.assertEqual(self.request(f"/api/v1/evidence/grants/{issued['grant_id']}/revoke",
                                      "POST", {}, headers=admin)[0], 200)
        self.assertEqual(self.reveal("finding", self.fid, issued["grant"], admin)[0], 403)
        token = self.grant("finding", self.fid, admin)[1]["grant"]
        with patch("community.evidence_access.time.time", return_value=time.time() + 120):
            self.assertEqual(self.reveal("finding", self.fid, token, admin)[0], 403)
        issued = self.grant("finding", self.fid, admin)[1]
        self.assertEqual(self.request("/api/v1/auth/logout", "POST", {}, headers=admin)[0], 200)
        self.assertEqual(self.reveal("finding", self.fid, issued["grant"], admin)[0], 401)
        secret = self.grant("finding", self.fid)[1]["grant"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            statuses = list(pool.map(lambda _: self.reveal("finding", self.fid, secret)[0], range(6)))
        self.assertEqual(statuses.count(200), 1)
        self.assertEqual(statuses.count(403), 5)

    def test_reports_log_stream_and_export_paths_deny_ungranted_content(self):
        job = self.service.launch({"target": "owned-local.invalid"})
        logfile = self.service.store.job_path(job["id"])
        logfile.parent.mkdir(parents=True, exist_ok=True)
        logfile.write_text(EVIDENCE_CANARY)
        paths = [
            f"/api/v1/campaigns/{self.cid}/report.pdf",
            f"/api/v1/run/logs/{job['id']}?raw=true",
            f"/api/v1/run/{job['id']}/stream?raw=true",
            f"/api/v1/jobs/{job['id']}/log?raw=true",
        ]
        for route in paths:
            status, body, _ = self.request(route)
            self.assertEqual(status, 403, route)
            self.assertNotIn(EVIDENCE_CANARY, body.decode("utf-8", "replace"))
        self.assertEqual(self.request(f"/api/v1/campaigns/{self.cid}/report/pdf",
                                      "POST", {"password":"long-strong-report-password"})[0], 403)
        for path in (f"/api/v1/run/logs/{job['id']}", f"/api/v1/jobs/{job['id']}/log"):
            status, content, _ = self.request(path)
            self.assertEqual(status, 200)
            self.assertNotIn(EVIDENCE_CANARY, content.decode())
        token = self.grant("run", job["id"])[1]["grant"]
        status, body, _ = self.reveal("run", job["id"], token)
        self.assertEqual(status, 200)
        self.assertIn(EVIDENCE_CANARY, body.decode())
        self.assertNotIn(EVIDENCE_CANARY, self.request(f"/api/v1/run/logs/{job['id']}")[1].decode())
    def test_public_events_proposal_and_error_never_reflect_evidence_canaries(self):
        self.service.store.save("remediations", {
            "id": "rem_canary", "campaign_id": self.cid, "finding_id": self.fid,
            "status": "proposed", "title": SOURCE_CANARY,
            "validation": {"before": [{"name": EVIDENCE_CANARY, "passed": False,
                                      "output": SOURCE_CANARY}]}})
        self.service.store.save("events", {
            "id": "evt_canary", "event": "finding.created", "timestamp": "2026-10-28T00:00:00Z",
            "data": {"title": SOURCE_CANARY, "evidence": EVIDENCE_CANARY}})
        for path in ("/api/v1/pull-requests", "/api/v1/pull-requests/rem_canary",
                     "/api/v1/events/history"):
            status, body, _ = self.request(path)
            self.assertEqual(status, 200, path)
            self.assertNotIn(SOURCE_CANARY, body.decode(), path)
            self.assertNotIn(EVIDENCE_CANARY, body.decode(), path)
        response = self.request(f"/api/v1/campaigns/{self.cid}/findings/{self.fid}",
                                "PATCH", {"status": EVIDENCE_CANARY})
        self.assertIn(response[0], (400, 403))
        self.assertNotIn(EVIDENCE_CANARY, response[1].decode())

    def test_password_rotation_revokes_session_grant_across_relogin(self):
        admin = self.role("admin", "evidence_rotating_admin")
        issued = self.grant("finding", self.fid, headers=admin)[1]
        status, body, _ = self.request("/api/v1/auth/password", "POST", {
            "old_password": "a-long-evidence-access-password",
            "new_password": "a-new-long-evidence-password"
        }, headers=admin)
        self.assertEqual(status, 200, body)
        self.assertEqual(self.reveal("finding", self.fid, issued["grant"], admin)[0], 401)
        new_token = self.service.accounts.login("evidence_rotating_admin",
                                               "a-new-long-evidence-password", "127.0.0.1")["token"]
        self.assertEqual(self.reveal("finding", self.fid, issued["grant"],
                          {"Authorization": "Bearer " + new_token})[0], 403)

    def test_source_file_enumeration_is_denied_before_running_git(self):
        with patch("subprocess.run", side_effect=AssertionError("must not invoke git")) as shell:
            response = self.request("/api/v1/source-files?repo=/tmp/evidence-canary")
        self.assertEqual(response[0], 403)
        self.assertNotIn(EVIDENCE_CANARY, response[1].decode())
        shell.assert_not_called()
