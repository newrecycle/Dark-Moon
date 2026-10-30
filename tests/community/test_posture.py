"""Record-backed dashboard totals, conservative risk, safe metrics and exact drill-downs."""
import copy
import json
import math
import threading
import unittest

import test_community as fixtures
from api import json_storage as data
from community.finding_query import finding_page
from community.posture import posture
from community.server import HTTPServer, handler_for


def workspace():
    findings = [
        {"id":"same", "campaign_id":"c1", "project_id":"p1", "target_id":"t1", "severity":"critical", "status":"false_positive"},
        {"id":"b", "campaign_id":"c1", "project_id":"p1", "target_id":"t1", "severity":"high", "status":"accepted_risk", "mitre_attack_id":"T1190"},
        {"id":"same", "campaign_id":"c2", "project_id":"p2", "target_id":"t2", "severity":"critical", "status":"exploited", "mitre_attack_id":"T1190"},
        {"id":"d", "campaign_id":"c2", "project_id":"p2", "target_id":"t2", "severity":"high", "status":"remediated"},
        {"id":"e", "campaign_id":"c3", "project_id":"p1", "target_id":"t1", "severity":"medium", "status":"confirmed"},
        {"id":"orphan", "campaign_id":"missing", "target_id":"unregistered", "severity":"custom"},
    ]
    return {"projects":[{"id":"p1"},{"id":"p2"},{"id":"idle-project"}],
            "targets":[{"id":"t1","risk_level":"critical"},{"id":"t2","risk_level":"none"},{"id":"idle-target"}],
            "campaigns":[{"id":"c1","target_id":"t1","date":"2024-02-01T01:00:00Z","status":"completed","duration_seconds":120},
                         {"id":"c3","target_id":"t1","date":"2024-03-01T01:00:00Z","status":"running","duration_seconds":99},
                         {"id":"c2","target_id":"t2","date":"2024-02-01T01:00:00Z","status":"completed","duration_seconds":60}],
            "findings":findings,
            "remediations":[{"id":"r1","campaign_id":"c1","finding_id":"same","status":"validated","patch":"SECRET-PATCH"},
                            {"id":"r2","campaign_id":"c2","finding_id":"same","status":"failed"},
                            {"id":"r3","campaign_id":"c1","finding_id":"b","status":"rejected"},
                            {"id":"r4","campaign_id":"c1","finding_id":"d","status":"validated"},
                            {"id":"r5","campaign_id":"missing","finding_id":"orphan","status":"validated"}]}


class PostureTests(unittest.TestCase):
    def test_explicit_tracking_groups_are_target_scoped_and_never_inferred(self):
        sample=workspace()
        self.assertEqual(posture(sample)['totals']['distinct_tracked_issues'],0)
        for index in (0,2,4):sample['findings'][index]['tracking_id']='reviewed_issue'
        totals=posture(sample)['totals']
        self.assertEqual(totals['tracked_records'],3)
        self.assertEqual(totals['distinct_tracked_issues'],2)
        self.assertEqual(totals['untracked_records'],3)
        sample['findings'][0]['tracking_id']={'malformed':'not an identity'}
        self.assertEqual(posture(sample)['totals']['untracked_records'],4)

    def test_window_cohort_is_half_open_current_state_without_mutation(self):
        from community.posture import windowed_posture
        original = workspace()
        before = copy.deepcopy(original)
        result = windowed_posture(original, {'from':['2024-02-01T02:00:00+01:00'], 'to':['2024-03-01T01:00:00Z']})
        self.assertEqual({c['id'] for c in result['campaign_history']}, {'c1','c2'})
        self.assertEqual(result['totals']['findings'], 4)
        self.assertEqual(result['cohort'], 'campaign_start_window_current_state')
        self.assertEqual(original, before)
        self.assertEqual(windowed_posture(original, {'from':['2025-01-01T00:00:00Z']})['totals']['findings'], 0)
        for params in ({'from':['2024-02-01']}, {'from':['2024-02-01T01:00:00']},
                       {'from':['']}, {'from':['2024-02-01T01:00:00Z']*2},
                       {'as_of':['2024-02-01T01:00:00Z']},
                       {'from':['2024-03-01T00:00:00Z'],'to':['2024-02-01T00:00:00Z']}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                windowed_posture(original, params)

    def test_empty_metrics_have_no_invented_rates_or_durations(self):
        p = posture({k:[] for k in ("projects","targets","campaigns","findings","remediations")})
        self.assertEqual(p["totals"]["findings"],0)
        self.assertEqual(p["totals"]["risk"],"none")
        self.assertIsNone(p["remediation"]["validated_share"])
        self.assertIsNone(p["duration"]["mean_seconds"])
        self.assertEqual(p["target_risk"],[])

    def test_totals_include_idle_records_orphans_and_repeat_campaign_findings(self):
        p=posture(workspace())
        self.assertEqual([p["totals"][k] for k in ("projects","targets","campaigns","findings")],[3,3,3,6])
        self.assertEqual(p["totals"]["active"],4)
        self.assertEqual(p["totals"]["excluded"],2)
        self.assertEqual(sum(p["severity_distribution"].values()),6)
        self.assertEqual(sum(p["status_distribution"].values()),6)
        self.assertEqual(p["coverage"],{"findings_without_registered_target":1,"findings_without_campaign":1})

    def test_risk_uses_active_findings_instead_of_stale_target_labels(self):
        p=posture(workspace())
        self.assertEqual([t["id"] for t in p["target_risk"]],["t2","t1","idle-target"])
        self.assertEqual([t["risk"] for t in p["target_risk"]],["critical","high","none"])
        self.assertEqual(p["target_risk"][1]["latest_campaign_id"],"c3")
        self.assertEqual(p["target_risk"][1]["campaigns"],2)

    def test_excluded_legacy_states_and_unknown_status_are_explicit(self):
        s=workspace();s["findings"]=[{"id":str(i),"target_id":"t1","status":v} for i,v in enumerate(
            ["closed","fixed","false_positive","remediated","resolved","accepted_risk","new_legacy",None])]
        p=posture(s)
        self.assertEqual(p["totals"]["active"],3)
        self.assertEqual(p["totals"]["excluded"],5)
        self.assertEqual(p["target_risk"][0]["risk"],"unknown")

    def test_local_rate_cohort_requires_both_finding_and_campaign_identity(self):
        r=posture(workspace())["remediation"]
        self.assertEqual(r["proposals"],3)
        self.assertEqual(r["validated"],1)
        self.assertAlmostEqual(r["validated_share"],1/3)
        self.assertEqual(r["findings_with_proposals"],3)
        self.assertEqual(r["unlinked_proposals"],2)
        self.assertEqual(r["status_distribution"],{"failed":1,"rejected":1,"validated":1})

    def test_durations_exclude_running_zero_negative_boolean_and_nonfinite(self):
        s=workspace()
        s["campaigns"].extend({"id":str(i),"status":"completed","duration_seconds":v} for i,v in enumerate([0,-1,True,None,"bad",math.inf,math.nan]))
        p=posture(s)
        self.assertEqual(p["duration"]["recorded_campaigns"],2)
        self.assertEqual(p["duration"]["mean_seconds"],90)
        self.assertEqual(p["duration"]["total_campaigns"],10)
        json.dumps(p,allow_nan=False)

    def test_history_is_deterministic_and_invalid_or_naive_dates_sort_last(self):
        s=workspace();s["campaigns"].extend([{"id":"old","date":"1960-01-01T00:00:00Z"},{"id":"undated"},
            {"id":"bad-date","date":"nonsense"},{"id":"naive","date":"2099-01-01T00:00:00"}])
        p=posture(s)
        self.assertEqual([c["id"] for c in p["campaign_history"]],["c3","c1","c2","old","bad-date","naive","undated"])
        s["campaigns"].reverse();s["targets"].reverse();s["findings"].reverse()
        self.assertEqual(posture(s),p)

    def test_no_evidence_report_patch_or_stored_risk_is_projected(self):
        s=workspace()
        for row in [*s["findings"],*s["campaigns"],*s["targets"],*s["projects"]]:
            row.update(evidence="SECRET-EVIDENCE",description="SECRET-DESCRIPTION",report="SECRET-REPORT",title="SECRET-TITLE",endpoint="SECRET-ENDPOINT")
        result=json.dumps(posture(s))
        for secret in ("SECRET-EVIDENCE","SECRET-DESCRIPTION","SECRET-REPORT","SECRET-TITLE","SECRET-ENDPOINT","SECRET-PATCH","risk_level"):
            self.assertNotIn(secret,result)

    def test_calculation_does_not_mutate_source_records(self):
        s=workspace();before=copy.deepcopy(s);posture(s);self.assertEqual(s,before)

    def test_missing_finding_identity_cannot_link_a_proposal(self):
        s=workspace()
        s['findings'].append({'campaign_id':'c1'})
        s['remediations'].append({'id':'missing-id','campaign_id':'c1','status':'validated'})
        self.assertEqual(posture(s)['remediation']['proposals'],3)
        self.assertEqual(posture(s)['remediation']['unlinked_proposals'],3)

    def test_every_finding_metric_has_an_exact_query_cohort(self):
        s=workspace();p=posture(s)
        for field,distribution in (("severity",p["severity_distribution"]),("status",p["status_distribution"]),("mitre_attack_id",p["mitre_distribution"])):
            for value,count in distribution.items():
                self.assertEqual(finding_page(s["findings"],{field:value})["total"],count)
        for triage in ("active","excluded"):
            self.assertEqual(finding_page(s["findings"],{"triage":triage})["total"],p["totals"][triage])
        for target in p["target_risk"]:
            self.assertEqual(finding_page(s["findings"],{"triage":"active","target_id":target["id"]})["total"],target["active"])
        self.assertEqual(finding_page(s["findings"],{"triage":"active","project_id":"p1","mitre_attack_id":"T1190"})["total"],1)
        with self.assertRaises(ValueError):finding_page(s["findings"],{"triage":"invalid"})


class PostureHTTPTests(fixtures.Fixture):
    request=fixtures.HTTPTests.request

    def setUp(self):
        super().setUp();self.cid=self.campaign()
        data.save_project({"id":"idle-project","name":"Idle"})
        self.server=HTTPServer(("127.0.0.1",0),handler_for(self.service,{"127.0.0.1"}))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()

    def test_safe_authenticated_posture_matches_snapshot_and_recomputes_after_triage(self):
        self.assertEqual(self.request('/api/v1/dashboard/posture',auth=False)[0],401)
        status,body,_=self.request('/api/v1/dashboard/posture');self.assertEqual(status,200)
        p=json.loads(body);self.assertNotIn(b'PRIVATE-EVIDENCE',body)
        self.assertEqual(p['totals']['projects'],2)
        self.assertEqual(p,json.loads(self.request('/api/v1/overview')[1])['posture'])
        self.service.change_finding(self.cid,'vuln_fixture',{'status':'false_positive'})
        p=json.loads(self.request('/api/v1/dashboard/posture')[1])
        self.assertEqual(p['totals']['active'],0);self.assertEqual(p['target_risk'][0]['risk'],'none')
        query='/api/v1/vulnerabilities?triage=excluded&mitre_attack_id=T1190'
        self.assertEqual(json.loads(self.request(query)[1])['total'],1)
        self.assertEqual(self.request('/api/v1/dashboard/posture?from=2020',auth=True)[0],400)

    def test_window_http_keeps_semantics_and_rejects_duplicate_parameters(self):
        self.campaign()
        url = '/api/v1/dashboard/posture?from=2000-01-01T00:00:00Z&to=2100-01-01T00:00:00Z'
        status, body, _ = self.request(url)
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result['cohort'], 'campaign_start_window_current_state')
        self.assertEqual(result['totals']['findings'], 1)
        self.assertEqual(result['window']['to'], '2100-01-01T00:00:00+00:00')
        self.assertEqual(self.request(url + '&from=2001-01-01T00:00:00Z')[0], 400)
        self.assertEqual(self.request(url, auth=False)[0], 401)
        all_findings='/api/v1/vulnerabilities?campaign_from=2000-01-01T00:00:00Z&campaign_to=2100-01-01T00:00:00Z'
        self.assertEqual(json.loads(self.request(all_findings)[1])['total'],1)
        empty='/api/v1/vulnerabilities?campaign_from=2100-01-01T00:00:00Z'
        self.assertEqual(json.loads(self.request(empty)[1])['total'],0)
        self.assertEqual(self.request(empty+'&campaign_from=2200-01-01T00:00:00Z')[0],400)
        self.assertEqual(self.request('/api/v1/vulnerabilities?campaign_from=')[0],400)


    def test_viewer_can_read_metrics_but_cannot_change_triage(self):
        self.service.accounts.create('reader','long-reader-password','viewer')
        token=self.service.accounts.login('reader','long-reader-password','127.0.0.1')['token']
        headers={'Authorization':'Bearer '+token}
        self.assertEqual(self.request('/api/v1/dashboard/posture',headers=headers)[0],200)
        self.assertEqual(self.request('/api/v1/vulnerabilities/vuln_fixture','PATCH',{'status':'resolved'},headers=headers)[0],403)
