"""DST, anchored recurrence, scheduler persistence and edit/claim races."""
import concurrent.futures
import copy
import json
import threading
from datetime import datetime, timezone
from unittest.mock import patch

import test_community as fixtures
from community.calendar_rules import normalize_rule, next_occurrence
from community.jobs import Scheduler
from community.server import HTTPServer, handler_for


def utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class CalendarTests(fixtures.Fixture):
    def rule(self, kind="daily", start="2026-03-07T02:30", **extra):
        return normalize_rule({"kind":kind,"timezone":"America/Edmonton","start_local":start,**extra})

    def test_daily_skips_spring_gap_without_moving_wall_time(self):
        rule=self.rule()
        self.assertEqual(next_occurrence(rule),utc("2026-03-07T09:30Z"))
        self.assertEqual(next_occurrence(rule,utc("2026-03-07T09:30Z")),utc("2026-03-09T08:30Z"))

    def test_fall_fold_is_explicit_and_occurs_once(self):
        for fold, expected in ((0,"2026-11-01T07:30Z"),(1,"2026-11-01T08:30Z")):
            rule=self.rule(start="2026-11-01T01:30",fold=fold)
            first=next_occurrence(rule);self.assertEqual(first,utc(expected))
            self.assertEqual(next_occurrence(rule,first),utc("2026-11-02T08:30Z"))

    def test_weekly_every_two_weeks_stays_anchored_across_dst(self):
        rule=self.rule("weekly","2026-03-01T10:00",every=2)
        self.assertEqual(next_occurrence(rule,utc("2026-03-01T17:00Z")),utc("2026-03-15T16:00Z"))
        self.assertEqual(next_occurrence(rule,utc("2026-03-30T00:00Z")),utc("2026-04-12T16:00Z"))

    def test_monthly_skips_missing_day_and_leap_year_boundaries(self):
        rule=self.rule("monthly","2026-01-31T09:00")
        self.assertEqual(next_occurrence(rule,utc("2026-01-31T16:00Z")),utc("2026-03-31T15:00Z"))
        leap=self.rule("monthly","2024-02-29T09:00",every=12)
        self.assertEqual(next_occurrence(leap,utc("2024-02-29T16:00Z")),utc("2028-02-29T16:00Z"))

    def test_one_time_gap_and_invalid_rules_are_rejected(self):
        for raw in ({"kind":"once","timezone":"America/Edmonton","start_local":"2026-03-08T02:30"},
                    {"kind":"daily","timezone":"not/a/zone","start_local":"2026-10-27T12:00"},
                    {"kind":"daily","timezone":"UTC","start_local":"2026-10-27T12:00Z"},
                    {"kind":"daily","timezone":"UTC","start_local":"2026-10-27T12:00","every":0}):
            with self.assertRaises(ValueError):normalize_rule(raw)

    def test_once_consumed_and_history_survives_scheduler_restart(self):
        scheduler=self.service.scheduler
        item=scheduler.create({"target":"example.invalid","rule":self.rule("once","2026-01-01T09:00")})
        scheduler.tick(utc("2026-10-27T12:00Z"));scheduler.tick(utc("2026-10-28T12:00Z"))
        self.assertFalse(self.service.store.get("schedules",item["id"])["enabled"])
        history=Scheduler(self.service.store,self.service.launch).history(item["id"])
        self.assertEqual(len(history),1);self.assertEqual(history[0]["disposition"],"queued")
        self.assertEqual(history[0]["job_status"],"queued")

    def test_missed_calendar_occurrences_coalesce_and_advance_from_anchor(self):
        item=self.service.scheduler.create({"target":"example.invalid","rule":self.rule("daily","2026-01-01T09:00")})
        self.service.scheduler.tick(utc("2026-10-27T18:03Z"))
        current=self.service.store.get("schedules",item["id"])
        self.assertEqual(utc(current["next_run"]),utc("2026-10-28T15:00Z"))
        self.assertEqual(len(self.service.scheduler.history(item["id"])),1)

    def test_legacy_elapsed_interval_keeps_tick_relative_meaning(self):
        item=self.service.scheduler.create({"target":"example.invalid","interval_seconds":3600,"next_run":"2020-01-01T00:00:00Z"})
        self.service.scheduler.tick(utc("2026-10-27T18:03Z"))
        current=self.service.store.get("schedules",item["id"])
        self.assertEqual(utc(current["next_run"]),utc("2026-10-27T19:03Z"))

    def test_preview_has_offsets_and_no_side_effects(self):
        before=copy.deepcopy(self.service.store.read())
        result=self.service.scheduler.preview({"target":"example.invalid","rule":self.rule("daily","2026-10-31T01:30")},clock=utc("2026-10-30T00:00Z"))
        self.assertEqual(len(result["occurrences"]),5)
        self.assertTrue(result["occurrences"][0]["local"].endswith("-06:00"))
        self.assertTrue(result["occurrences"][-1]["local"].endswith("-07:00"))
        self.assertEqual(before,self.service.store.read())

    def test_concurrent_edits_accept_only_current_version(self):
        item=self.service.scheduler.create({"target":"example.invalid","enabled":False})
        def edit(index):
            try:return self.service.scheduler.update(item["id"],{"version":1,"display_name":f"Edit {index}"})["version"]
            except ValueError:return "stale"
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(edit,range(6)))
        self.assertEqual(results.count(2),1);self.assertEqual(results.count("stale"),5)

    def test_duplicate_is_independent_paused_and_has_no_history(self):
        old=self.service.scheduler.create({"target":"example.invalid","rule":self.rule()})
        duplicate=self.service.scheduler.duplicate(old["id"],{"version":1})
        self.assertFalse(duplicate["enabled"]);self.assertNotEqual(old["id"],duplicate["id"])
        self.service.scheduler.update(duplicate["id"],{"version":1,"spec":{"target":"other.invalid"}})
        self.assertEqual(self.service.store.get("schedules",old["id"])["spec"]["target"],"example.invalid")
        self.assertEqual(self.service.scheduler.history(duplicate["id"]),[])

    def test_edit_during_launch_does_not_overwrite_new_configuration(self):
        scheduler=Scheduler(self.service.store,lambda *a,**k:None)
        item=scheduler.create({"target":"example.invalid","next_run":"2020-01-01T00:00:00Z"})
        def launch(*args,**kwargs):
            scheduler.update(item["id"],{"version":1,"display_name":"New definition"})
            return {"id":"job_old"}
        scheduler.launch=launch;scheduler.tick()
        current=self.service.store.get("schedules",item["id"])
        self.assertEqual(current["display_name"],"New definition")
        self.assertNotIn("last_job_id",current)
        self.assertEqual(scheduler.history(item["id"])[0]["job_id"],"job_old")

    def test_explicit_rearm_creates_a_new_job_not_an_idempotent_replay(self):
        item=self.service.scheduler.create({"target":"example.invalid","rule":self.rule("once","2026-01-01T09:00")})
        self.service.scheduler.tick()
        first=self.service.scheduler.history(item["id"])[0]["job_id"]
        self.service.store.update(lambda state: state["jobs"][first].update(status="succeeded"))
        self.service.scheduler.set_enabled(item["id"],True)
        self.service.scheduler.tick()
        jobs={row["job_id"] for row in self.service.scheduler.history(item["id"])}
        self.assertEqual(len(jobs),2)

    def test_simultaneous_schedulers_claim_an_occurrence_once(self):
        item=self.service.scheduler.create({"target":"example.invalid","next_run":"2020-01-01T00:00:00Z"})
        schedulers=[Scheduler(self.service.store,self.service.launch) for _ in range(6)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda s:s.tick(utc("2026-10-27T12:00Z")),schedulers))
        self.assertEqual(len(self.service.store.items("jobs")),1)
        self.assertEqual(len(self.service.scheduler.history(item["id"])),1)

    def test_overlap_history_is_bounded_and_does_not_invent_jobs(self):
        item=self.service.scheduler.create({"target":"example.invalid","interval_seconds":60,"next_run":"2020-01-01T00:00:00Z"})
        from datetime import timedelta
        for index in range(105):self.service.scheduler.tick(utc("2026-10-27T12:00Z")+timedelta(minutes=index))
        rows=self.service.scheduler.history(item["id"])
        self.assertEqual(len(rows),100)
        self.assertTrue(all(row["disposition"]=="skipped_overlap" for row in rows))
        self.assertTrue(all("job_id" not in row for row in rows))

    def test_failed_once_is_visible_and_consumed(self):
        def failed(*a,**k):raise ValueError("Launcher unavailable")
        scheduler=Scheduler(self.service.store,failed)
        item=scheduler.create({"target":"example.invalid","rule":self.rule("once","2026-01-01T09:00")})
        scheduler.tick()
        row=scheduler.history(item["id"])[0]
        self.assertEqual(row["disposition"],"failed")
        self.assertEqual(row["error"],"Launcher unavailable")
        self.assertFalse(self.service.store.get("schedules",item["id"])["enabled"])


class CalendarAPITests(fixtures.Fixture):
    request=fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        self.server=HTTPServer(("127.0.0.1",0),handler_for(self.service,{"127.0.0.1"}))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.raw={"target":"example.invalid","display_name":"Monthly review","enabled":False,
                  "rule":{"kind":"monthly","timezone":"America/Edmonton","start_local":"2099-01-31T09:00"}}

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()

    def test_preview_create_edit_duplicate_history_and_delete(self):
        status,body,_=self.request('/api/v1/scheduler/preview','POST',self.raw)
        self.assertEqual(status,200);self.assertEqual(len(json.loads(body)['occurrences']),5)
        self.assertEqual(self.service.store.items('schedules'),[])
        status,body,_=self.request('/api/v1/scheduler','POST',self.raw)
        self.assertEqual(status,201);item=json.loads(body)['data'];url='/api/v1/schedules/'+item['id']
        self.assertEqual(self.request(url,'PATCH',{'version':1,'display_name':'Edited'})[0],200)
        self.assertEqual(self.request(url,'PATCH',{'version':1,'display_name':'Stale'})[0],400)
        status,body,_=self.request(url+'/duplicate','POST',{'version':2})
        self.assertEqual(status,201);self.assertFalse(json.loads(body)['enabled'])
        self.assertEqual(json.loads(self.request(url+'/history')[1])['data'],[])
        self.assertEqual(self.request(url,'DELETE')[0],200)
        self.assertEqual(self.request(url,'PATCH',{'enabled':True})[0],404)

    def test_viewer_cannot_preview_or_mutate_schedules(self):
        user=self.service.accounts.create('calendar-viewer','a-long-viewer-password','viewer')
        token=self.service.accounts.issue(self.service.store.get('users',user['id']))['token']
        headers={'Authorization':'Bearer '+token}
        self.assertEqual(self.request('/api/v1/scheduler','GET',headers=headers)[0],200)
        self.assertEqual(self.request('/api/v1/scheduler/preview','POST',self.raw,headers=headers)[0],403)
        self.assertEqual(self.request('/api/v1/scheduler','POST',self.raw,headers=headers)[0],403)
