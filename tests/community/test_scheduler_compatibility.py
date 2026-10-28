"""Offline verification for the audit-backed flat schedule adapter.

No vendor code, external targets, notification delivery, process workers or
scheduled launches. The real HTTP dispatcher/store are exercised with a fake
launcher and explicit, deterministic calendar clocks.
Run: PYTHONPATH=mcp python -m unittest discover -s tests/community \
    -p test_scheduler_compatibility.py -v
"""
import concurrent.futures
import copy
import json
import threading
from datetime import datetime, timezone

import test_community as fixtures
from community.calendar_rules import next_occurrence, normalize_rule
from community.jobs import Scheduler, instant
from community.server import HTTPServer, handler_for


FUTURE = "2099-01-31T16:00:00Z"


def utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def flat(kind="once", **values):
    result = {"target": "owned.invalid", "scheduled_at": FUTURE,
              "recurrence": kind, "enabled": False}
    if kind != "once":
        result["recurrence_interval"] = 1
    return result | values


class FlatAdapterTests(fixtures.Fixture):
    def test_flat_once_preserves_distinct_display_program_and_absolute_instant(self):
        item = self.service.scheduler.create(flat(name="Display title", program="Engagement program",
                          scheduled_at="2099-01-31T09:00:00-07:00",
                          targets=["other.owned.invalid"], out_of_scope=["skip.owned.invalid"],
                          rules=["Permission granted", "Do not follow redirects"],
                          focus=["web", "api"], noise="low", remediate=False))
        self.assertEqual(item["display_name"], "Display title")
        self.assertEqual(item["spec"]["name"], "Engagement program")
        self.assertEqual(item["spec"]["target"], "owned.invalid")
        self.assertEqual(item["spec"]["out_of_scope"], ["skip.owned.invalid"])
        self.assertEqual(item["spec"]["targets"], ["other.owned.invalid"])
        self.assertEqual(item["spec"]["rules"], "Permission granted; Do not follow redirects")
        self.assertEqual(item["spec"]["focus"], "web,api")
        self.assertEqual(item["next_run"], utc(FUTURE).isoformat())
        self.assertEqual(item["rule"]["kind"], "once")
        self.assertEqual(item["rule"]["timezone"], "UTC")
        self.assertTrue(item["one_shot"])
        self.assertFalse(item["enabled"])

    def test_daily_weekly_monthly_map_to_anchored_canonical_rules(self):
        for kind, every in (("daily", 2), ("weekly", 3), ("monthly", 12)):
            with self.subTest(kind=kind):
                item = self.service.scheduler.create(flat(kind, recurrence_interval=every))
                rule = item["rule"]
                self.assertEqual(rule["kind"], kind)
                self.assertEqual(rule["every"], every)
                self.assertEqual(rule["timezone"], "UTC")
                self.assertEqual(rule["start_local"], "2099-01-31T16:00:00")
                self.assertEqual(instant(item["next_run"]), next_occurrence(rule))
                self.assertFalse(item["one_shot"])

    def test_preview_matches_creation_without_creating_or_queuing(self):
        request = flat("weekly", recurrence_interval=2, name="Preview")
        before = copy.deepcopy(self.service.store.read())
        preview = self.service.scheduler.preview(request, clock=utc("2099-01-01T00:00:00Z"))
        self.assertEqual(preview["definition"]["rule"]["kind"], "weekly")
        self.assertEqual(preview["timezone"], "UTC")
        self.assertEqual(len(preview["occurrences"]), 5)
        self.assertEqual(preview["occurrences"][0]["utc"], utc(FUTURE).isoformat())
        self.assertEqual(preview["gap_policy"], "skip")
        self.assertEqual(before, self.service.store.read())
        created = self.service.scheduler.create(request)
        for key in ("spec", "rule", "display_name", "one_shot", "next_run", "enabled"):
            self.assertEqual(created[key], preview["definition"][key])

    def test_partial_flat_edit_merges_current_scope_without_reanchoring(self):
        item = self.service.scheduler.create(flat("daily", recurrence_interval=2,
                    targets=["extra.owned.invalid"], out_of_scope=["excluded.owned.invalid"],
                    focus=["web"], name="Before"))
        existing = copy.deepcopy(item["spec"])
        edited = self.service.scheduler.update(item["id"], {"version": 1, "name": "After", "noise": "low"})
        self.assertEqual(edited["version"], 2)
        self.assertEqual(edited["display_name"], "After")
        self.assertEqual(edited["spec"], {**existing, "noise": "low"})
        self.assertEqual(edited["next_run"], item["next_run"])
        self.assertEqual(edited["rule"], item["rule"])
        self.assertFalse(edited["enabled"])
        self.assertNotIn("last_job_id", edited)

    def test_explicit_empty_lists_clear_only_requested_scope(self):
        item = self.service.scheduler.create(flat("monthly", recurrence_interval=1,
                 targets=["extra.owned.invalid"], out_of_scope=["excluded.owned.invalid"]))
        edited = self.service.scheduler.update(item["id"], {
            "version": 1, "targets": [], "out_of_scope": []})
        self.assertEqual(edited["spec"]["target"], "owned.invalid")
        self.assertEqual(edited["spec"]["targets"], [])
        self.assertEqual(edited["spec"]["out_of_scope"], [])
        self.assertEqual(edited["rule"], item["rule"])

    def test_name_only_edit_does_not_change_program_or_last_run_metadata(self):
        item = self.service.scheduler.create(flat("daily", name="Original", program="Original program"))
        self.service.store.update(lambda state: state["schedules"][item["id"]].update(
            last_job_id="job_prior", last_disposition="queued"))
        before = self.service.store.get("schedules", item["id"])
        edited = self.service.scheduler.update(item["id"], {"version": 1, "name": "Renamed"})
        self.assertEqual(edited["spec"], before["spec"])
        self.assertEqual(edited["next_run"], before["next_run"])
        self.assertEqual(edited["last_job_id"], "job_prior")
        self.assertEqual(edited["last_disposition"], "queued")

    def test_timestamp_only_and_interval_only_edits_preserve_other_rule_fields(self):
        original = self.service.scheduler.create(flat("weekly", recurrence_interval=2))
        later = self.service.scheduler.update(original["id"], {
            "version": 1, "scheduled_at": "2099-02-01T16:00:00Z"})
        self.assertEqual(later["rule"]["kind"], "weekly")
        self.assertEqual(later["rule"]["every"], 2)
        self.assertEqual(later["rule"]["start_local"], "2099-02-01T16:00:00")
        changed = self.service.scheduler.update(original["id"], {
            "version": 2, "recurrence_interval": 3})
        self.assertEqual(changed["rule"]["every"], 3)
        self.assertEqual(changed["rule"]["start_local"], later["rule"]["start_local"])

    def test_canonical_named_zone_fold_can_be_selected_by_absolute_timestamp(self):
        rule = normalize_rule({"kind": "daily", "timezone": "America/Edmonton",
                               "start_local": "2024-11-03T01:30", "fold": 0})
        item = self.service.scheduler.create({"spec": {"target": "owned.invalid"}, "rule": rule, "enabled": False})
        edited = self.service.scheduler.update(item["id"], {
            "version": 1, "scheduled_at": "2024-11-03T08:30:00Z"})
        self.assertEqual(edited["rule"]["timezone"], "America/Edmonton")
        self.assertEqual(edited["rule"]["start_local"], "2024-11-03T01:30:00")
        self.assertEqual(edited["rule"]["fold"], 1)
        self.assertEqual(instant(edited["next_run"]), utc("2024-11-03T08:30:00Z"))
        self.assertEqual(next_occurrence(edited["rule"], utc("2024-11-03T08:30:00Z")),
                         utc("2024-11-04T08:30:00Z"))

    def test_canonical_dst_gap_and_missing_month_day_policies_remain(self):
        gap = normalize_rule({"kind": "daily", "timezone": "America/Edmonton",
                              "start_local": "2024-03-09T02:30"})
        self.assertEqual(next_occurrence(gap, utc("2024-03-09T09:30:00Z")),
                         utc("2024-03-11T08:30:00Z"))
        month = self.service.scheduler.create(flat("monthly", recurrence_interval=1,
                         scheduled_at="2099-01-31T09:00:00Z"))
        self.assertEqual(next_occurrence(month["rule"], utc("2099-01-31T09:00:00Z")),
                         utc("2099-03-31T09:00:00Z"))

    def test_flat_once_is_claimed_once_without_executing_any_assessment(self):
        calls = []
        scheduler = Scheduler(self.service.store, lambda spec, **kw: (
            calls.append((spec, kw)) or {"id": "job_fake"}))
        item = scheduler.create(flat(scheduled_at="2020-01-01T00:00:00Z", enabled=True))
        scheduler.tick(utc("2026-10-28T12:00:00Z"))
        scheduler.tick(utc("2026-10-29T12:00:00Z"))
        saved = self.service.store.get("schedules", item["id"])
        self.assertFalse(saved["enabled"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(scheduler.history(item["id"])), 1)
        self.assertEqual(scheduler.history(item["id"])[0]["disposition"], "queued")

    def test_concurrent_flat_edits_reject_stale_version_atomically(self):
        item = self.service.scheduler.create(flat("daily", recurrence_interval=1,
                     out_of_scope=["excluded.owned.invalid"]))
        def update(index):
            try:
                return self.service.scheduler.update(item["id"], {
                    "version": 1, "noise": "low", "name": f"Edit {index}"})
            except ValueError:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(update, range(6)))
        self.assertEqual(sum(row is not None for row in results), 1)
        saved = self.service.store.get("schedules", item["id"])
        self.assertEqual(saved["version"], 2)
        self.assertEqual(saved["spec"]["out_of_scope"], ["excluded.owned.invalid"])
        self.assertEqual(saved["rule"], item["rule"])

    def test_supported_identical_mixed_fields_are_accepted(self):
        once = normalize_rule({"kind": "once", "timezone": "UTC",
                               "start_local": "2099-01-31T16:00:00"})
        request = flat(spec={"target": "owned.invalid"}, rule=once)
        item = self.service.scheduler.create(request)
        self.assertEqual(item["rule"], once)
        self.assertEqual(item["spec"]["target"], "owned.invalid")

    def test_mixed_canonical_spec_and_rule_conflicts_are_rejected(self):
        good_rule = normalize_rule({"kind": "once", "timezone": "UTC",
                                    "start_local": "2099-01-31T16:00:00"})
        for raw in (
            flat(spec={"target": "different.invalid"}),
            flat(rule=good_rule, scheduled_at="2099-02-01T16:00:00Z"),
            flat(name="Flat", display_name="Canonical"),
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.service.scheduler.create(raw)

    def test_unsupported_recurrence_defaults_and_nulls_do_not_create(self):
        invalid = (
            {"target": "owned.invalid", "scheduled_at": FUTURE, "enabled": False},
            flat("hourly"), flat("interval"), flat("DAILY"),
            flat("daily", recurrence_interval=None), flat("daily", recurrence_interval=True),
            flat("daily", recurrence_interval=0), flat("daily", recurrence_interval=367),
            flat("once", recurrence_interval=2),
            flat("weekly", recurrence_interval=None),
            flat("daily", scheduled_at="2099-01-31T09:00:00-07:00"),
            flat(scheduled_at="2099-01-31T16:00:00"),
            flat(scheduled_at="2099-01-31T16:00:00.1Z"),
            flat(scheduled_at="invalid"),
            flat(target=None), flat(enabled=None), flat(enabled="false"),
            flat(credentials=["inline-secret"]), flat(tokens=[]),
            flat(rules=["allowed; not allowed"]), flat(noise="aggressive"),
            flat(target="a b"), flat(credential_id="unknown_ref"),
        )
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.service.scheduler.create(raw)
        self.assertEqual(self.service.store.items("schedules"), [])

    def test_unknown_defaults_require_explicit_flat_fields(self):
        for raw in (
            {"target": "owned.invalid", "scheduled_at": FUTURE, "recurrence": "once"},
            {"target": "owned.invalid", "scheduled_at": FUTURE, "enabled": False},
            flat("daily", recurrence_interval=0),
            flat("daily", recurrence_interval=1, scheduled_at=None),
            flat("once", unexpected="flag"),
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.service.scheduler.preview(raw)

    def test_invalid_partial_edits_do_not_modify_persistent_record(self):
        item = self.service.scheduler.create(flat("daily", recurrence_interval=1))
        for patch in (
            {"version": 1, "target": None},
            {"version": 1, "recurrence": "interval"},
            {"version": 1, "recurrence_interval": 0},
            {"version": 1, "recurrence": "weekly"},
            {"version": 1, "credentials": ["secret"]},
            {"version": 1, "spec": {"target": "other.invalid"}, "target": "owned.invalid"},
            {"version": 1, "rule": {"kind": "once", "timezone": "UTC",
                                    "start_local": "2099-01-31T16:00:00"},
             "recurrence": "daily"},
        ):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.service.scheduler.update(item["id"], patch)
            self.assertEqual(self.service.store.get("schedules", item["id"]), item)

    def test_canonical_nested_and_legacy_toggle_are_unchanged(self):
        canonical = {"spec": {"target": "owned.invalid"}, "rule":
                     {"kind": "interval", "timezone": "UTC", "start_local": "2099-01-31T16:00:00",
                      "seconds": 3600}, "enabled": False}
        preview = self.service.scheduler.preview(canonical)
        item = self.service.scheduler.create(canonical)
        self.assertEqual(item["rule"], preview["definition"]["rule"])
        updated = self.service.scheduler.update(item["id"], {"enabled": True})
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["rule"], item["rule"])
        self.assertEqual(updated["next_run"], item["next_run"])

    def test_compatibility_credential_references_must_exist(self):
        item = flat(credential_id="cred_fixture")
        with self.assertRaisesRegex(ValueError, "Saved credential reference"):
            self.service.scheduler.preview(item)
        self.service.store.save("credentials", {"id": "cred_fixture", "provider": "generic",
                                               "name": "fixture", "sealed": "fake"})
        created = self.service.scheduler.create(item)
        self.assertEqual(created["spec"]["credential_id"], "cred_fixture")
        with self.assertRaisesRegex(ValueError, "Saved credential reference"):
            self.service.scheduler.update(created["id"], {"version": 1, "credential_id": "missing"})
        self.assertEqual(self.service.store.get("schedules", created["id"]), created)


class FlatAdapterHTTPTests(fixtures.Fixture):
    request = fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(self.service, {"127.0.0.1"}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        super().tearDown()

    def test_both_collections_support_flat_create_and_preview_envelopes(self):
        request = flat("monthly", recurrence_interval=2)
        for prefix in ("/api/v1/scheduler", "/api/v1/schedules"):
            before = self.service.store.items("schedules")
            status, body, _ = self.request(prefix + "/preview", "POST", request)
            self.assertEqual(status, 200, body)
            self.assertEqual(self.service.store.items("schedules"), before)
            status, body, _ = self.request(prefix, "POST", request)
            self.assertEqual(status, 201, body)
            content = json.loads(body)
            item = content["data"] if prefix.endswith("scheduler") else content
            self.assertEqual(item["rule"]["kind"], "monthly")
            self.assertEqual(item["rule"]["every"], 2)

    def test_put_requires_version_and_protects_current_scope(self):
        status, body, _ = self.request("/api/v1/scheduler", "POST",
             flat("daily", targets=["extra.owned.invalid"], out_of_scope=["excluded.owned.invalid"]))
        self.assertEqual(status, 201, body)
        original = json.loads(body)["data"]
        path = "/api/v1/scheduler/" + original["id"]
        for bad in ({"name": "No version"}, {"version": True, "name": "Bool version"},
                    {"version": 0, "name": "Stale"}):
            status, body, _ = self.request(path, "PUT", bad)
            self.assertEqual(status, 400, body)
            self.assertEqual(self.service.store.get("schedules", original["id"]), original)
        status, body, _ = self.request(path, "PUT", {"version": 1, "name": "Updated", "noise": "low"})
        self.assertEqual(status, 200, body)
        changed = json.loads(body)["data"]
        self.assertEqual(changed["version"], 2)
        self.assertEqual(changed["spec"]["out_of_scope"], original["spec"]["out_of_scope"])
        self.assertEqual(changed["spec"]["targets"], original["spec"]["targets"])
        self.assertEqual(changed["rule"], original["rule"])
        self.assertEqual(changed["display_name"], "Updated")
        self.assertEqual(self.request(path, "PUT", {"version": 1, "name": "stale"})[0], 400)
        self.assertEqual(self.service.store.get("schedules", original["id"]), changed)

    def test_patch_and_toggle_keep_intentional_legacy_behavior(self):
        item = self.service.scheduler.create(flat())
        path = "/api/v1/schedules/" + item["id"]
        self.assertEqual(self.request(path, "PATCH", {"enabled": True})[0], 200)
        self.assertTrue(self.service.store.get("schedules", item["id"])["enabled"])
        self.assertEqual(self.request(path, "PATCH", {"version": 2, "name": "Compatibility"})[0], 200)
        saved = self.service.store.get("schedules", item["id"])
        self.assertEqual(saved["display_name"], "Compatibility")
        self.assertEqual(saved["spec"]["target"], "owned.invalid")

    def test_invalid_recurrence_returns_validation_error_not_server_error(self):
        for payload in (flat("interval"), flat("daily", recurrence_interval=0),
                        flat("daily", scheduled_at="2099-01-31T09:00:00-07:00")):
            status, body, _ = self.request("/api/v1/scheduler/preview", "POST", payload)
            self.assertEqual(status, 400, body)
            self.assertIn("error", json.loads(body))
        self.assertEqual(self.service.store.items("schedules"), [])

    def test_unauthenticated_and_viewer_cannot_mutate_or_preview(self):
        payload = flat()
        self.assertEqual(self.request("/api/v1/scheduler/preview", "POST", payload, auth=False)[0], 401)
        user = self.service.accounts.create("scheduler-viewer", "viewer-long-secret-123", "viewer")
        token = self.service.accounts.issue(self.service.store.get("users", user["id"]))["token"]
        headers = {"Authorization": "Bearer " + token}
        self.assertEqual(self.request("/api/v1/scheduler", "POST", payload, headers=headers)[0], 403)
        self.assertEqual(self.request("/api/v1/scheduler/preview", "POST", payload, headers=headers)[0], 403)
        created = self.service.scheduler.create(payload)
        self.assertEqual(self.request("/api/v1/scheduler/" + created["id"], "PUT",
                         {"version": 1, "name": "Forbidden"}, headers=headers)[0], 403)
        self.assertEqual(self.service.store.get("schedules", created["id"]), created)
