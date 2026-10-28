"""Isolation with a populated OpenCode DB, overlapping roots and real child IDs."""
import sqlite3
from unittest.mock import patch

import test_community as fixtures
from api import json_storage as data, live_push


class CampaignIdentityTests(fixtures.Fixture):
    def setUp(self):
        super().setUp()
        self.db = self.root / "opencode-dev.db"
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE session(id TEXT PRIMARY KEY, parent_id TEXT, time_created INTEGER)")
        self.db_patch = patch.object(live_push, "_OPENCODE_DB", self.db)
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        super().tearDown()

    def session(self, sid, parent=None, created=1000):
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO session VALUES (?,?,?)", (sid, parent, created))

    def init(self, sid="MCPCONST", run=None, host="alpha.example"):
        return live_push.init_live_campaign(sid, host, "", opencode_session_id=run)

    def test_web_launches_keep_distinct_campaigns_with_existing_root(self):
        self.session("ses_EXISTINGroot123")
        a = self.service.launch({"target": "alpha.example", "name": "Alpha"})
        live_push.push_finding(a["campaign_id"], {"title": "Alpha only", "severity": "high"})
        b = self.service.launch({"target": "beta.example", "name": "Beta"})
        self.assertNotEqual(a["campaign_id"], b["campaign_id"])
        for job, host, count in ((a, "alpha.example", 1), (b, "beta.example", 0)):
            campaign = data.load_campaign(job["campaign_id"])
            self.assertEqual(data.load_target(campaign["target_id"])["host"], host)
            self.assertEqual(campaign["stats"]["total_findings"], count)

    def test_overlapping_roots_do_not_change_caller_or_truncate_identity(self):
        roots = ["ses_SAMEPRE1tailA", "ses_SAMEPRE1tailB"]
        self.session(roots[0])
        a = self.init(run=roots[0])
        self.session(roots[1], created=2000)
        b = self.init(run=roots[1], host="beta.example")
        self.assertNotEqual(a["campaign_id"], b["campaign_id"])
        self.assertEqual(a["campaign_id"], self.init(run=roots[0])["campaign_id"])
        self.assertEqual(data.load_campaign(a["campaign_id"])["session_id"], "MCPCONST")

    def test_child_and_grandchild_join_own_root_and_preserve_report(self):
        self.session("ses_rootA")
        self.session("ses_childA", "ses_rootA", 1100)
        self.session("ses_grandchildA", "ses_childA", 1200)
        a = self.init(run="ses_rootA")
        live_push.push_finding(a["campaign_id"], {"title": "Keep me", "severity": "high"})
        campaign = data.load_campaign(a["campaign_id"])
        campaign.update(status="completed", report_path="existing.md")
        data.save_campaign(campaign)
        self.session("ses_unrelatedRoot", created=3000)
        self.init(run="ses_unrelatedRoot", host="beta.example")
        for child in ("ses_childA", "ses_grandchildA"):
            result = self.init(sid="child-privacy", run=child)
            self.assertEqual(result["campaign_id"], a["campaign_id"])
            self.assertEqual(result["status"], "subagent_merged_into_parent")
        preserved = data.load_campaign(a["campaign_id"])
        self.assertEqual(preserved["session_id"], "MCPCONST")
        self.assertEqual(preserved["status"], "completed")
        self.assertEqual(preserved["report_path"], "existing.md")
        self.assertEqual(preserved["stats"]["total_findings"], 1)

    def test_child_first_initialization_is_reused_by_root(self):
        self.session("ses_rootA")
        self.session("ses_childA", "ses_rootA")
        child = self.init(run="ses_childA")
        self.assertEqual(child["campaign_id"], self.init(run="ses_rootA")["campaign_id"])

    def test_root_binding_survives_midnight(self):
        self.session("ses_rootA")
        with patch.object(live_push, "_today_compact", return_value="20261027"):
            first = self.init(run="ses_rootA")
        with patch.object(live_push, "_today_compact", return_value="20261028"):
            self.assertEqual(first["campaign_id"], self.init(run="ses_rootA")["campaign_id"])

    def test_missing_database_preserves_explicit_root_and_web_identity(self):
        self.db.unlink()
        self.assertEqual(live_push._run_campaign_frag("privacy", "ses_rootA"), "ses_rootA")
        self.assertEqual(live_push._run_campaign_frag("web_unique"), "web_unique")
        self.init(run="ses_rootA")
        self.assertFalse(self.db.exists())

    def test_schema_migration_does_not_borrow_another_run(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("DROP TABLE session")
        self.assertEqual(live_push._run_campaign_frag("privacy", "ses_rootA"), "ses_rootA")

    def test_legacy_privacy_fragments_are_never_used_as_database_selectors(self):
        self.session("ses_PREFIX12tailA")
        self.assertEqual(live_push._run_campaign_frag("PREFIX12"), "PREFIX12")
        self.assertEqual(live_push._run_campaign_frag("web_unique"), "web_unique")

    def test_cyclic_ancestry_and_unsafe_ids_reject_before_writing(self):
        self.session("ses_a", "ses_b")
        self.session("ses_b", "ses_a")
        for identity in ("ses_a", "../../bad", "ses_bad/path"):
            with self.assertRaises(ValueError):
                self.init(run=identity)
        self.assertEqual(data.load_campaigns(), [])
