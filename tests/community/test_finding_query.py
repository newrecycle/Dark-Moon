"""Stable composed finding pages and the SDK-facing HTTP envelope."""
import json
import threading
import unittest

import test_community as fixtures
from api import json_storage as data
from community.finding_query import finding_page
from community.server import HTTPServer, handler_for


ROWS = [
    {"id":"b","campaign_id":"camp_a","target_id":"t1","severity":"high","status":"confirmed","category":"sqli","title":"SQL query","cvss_score":8.1},
    {"id":"a","campaign_id":"camp_a","target_id":"t1","severity":"high","status":"confirmed","category":"sqli","title":"SQL query","cvss_score":8.1},
    {"id":"c","campaign_id":"camp_b","target_id":"t2","severity":"low","status":"unconfirmed","category":"config","title":"Header","cvss_score":0},
    {"id":"d","campaign_id":"camp_b","target_id":"t2","severity":"critical","status":"exploited","category":"sqli","title":"Critical query","cvss_score":None},
]


class FindingQueryTests(unittest.TestCase):
    def test_filters_search_and_totals_compose_before_paging(self):
        page = finding_page(ROWS, {"severity":"high","status":"confirmed","category":"sqli","campaign_id":"camp_a","target_id":"t1","q":"SQL","limit":"1","offset":"1"})
        self.assertEqual(page["total"],2)
        self.assertEqual([f["id"] for f in page["data"]],["b"])
        self.assertEqual(ROWS[0]["id"],"b")

    def test_ties_have_stable_order_independent_of_storage_order(self):
        for sort in ("severity_desc","cvss_asc","title_desc"):
            a = finding_page(ROWS,{"sort":sort})
            b = finding_page(list(reversed(ROWS)),{"sort":sort})
            self.assertEqual([f["id"] for f in a["data"]],[f["id"] for f in b["data"]])
            ids=[f["id"] for f in a["data"]]
            self.assertLess(ids.index("a"),ids.index("b"))

    def test_cvss_zero_is_a_score_and_unknowns_stay_last(self):
        self.assertEqual([f["id"] for f in finding_page(ROWS,{"sort":"cvss_asc"})["data"]],["c","a","b","d"])
        self.assertEqual([f["id"] for f in finding_page(ROWS,{"sort":"cvss_desc"})["data"]],["a","b","c","d"])

    def test_empty_and_out_of_range_pages_keep_exact_denominator(self):
        self.assertEqual(finding_page(ROWS,{"q":"missing"})["total"],0)
        page=finding_page(ROWS,{"offset":"50","limit":"10"})
        self.assertEqual(page["data"],[]);self.assertEqual(page["total"],4)

    def test_invalid_controls_are_rejected(self):
        for query in ({"sort":"unknown"},{"limit":"0"},{"limit":"501"},{"limit":"ten"},{"offset":"-1"},{"q":"x"*501}):
            with self.subTest(query=query),self.assertRaises(ValueError):finding_page(ROWS,query)

    def test_large_input_has_bounded_page_and_legacy_calls_remain_unlimited(self):
        rows=[ROWS[0]|{"id":f"f{i:06}"} for i in range(20000)]
        page=finding_page(rows,{"limit":"25","offset":"19975"})
        self.assertEqual(page["total"],20000);self.assertEqual(len(page["data"]),25)
        self.assertEqual(page["data"][0]["id"],"f019975")
        self.assertEqual(len(finding_page(ROWS,{})["data"]),4)


class FindingQueryHTTPTests(fixtures.Fixture):
    request=fixtures.HTTPTests.request

    def setUp(self):
        super().setUp();self.cid=self.campaign()
        data.save_vulnerabilities(self.cid,[r|{"campaign_id":self.cid,"evidence":{"output":"PRIVATE-QUERY-EVIDENCE"}} for r in ROWS])
        self.server=HTTPServer(("127.0.0.1",0),handler_for(self.service,{"127.0.0.1"}))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()

    def test_paged_contract_preserves_safe_projection(self):
        status,body,_=self.request('/api/v1/vulnerabilities?severity=high&status=confirmed&category=sqli&sort=title_asc&limit=1&offset=1&q=SQL')
        self.assertEqual(status,200);page=json.loads(body)
        self.assertEqual(page['total'],2);self.assertEqual(len(page['data']),1)
        self.assertEqual(page['data'][0]['id'],'b')
        self.assertNotIn(b'PRIVATE-QUERY-EVIDENCE',body)
        self.assertEqual(len(json.loads(self.request('/api/v1/vulnerabilities')[1])['data']),4)

    def test_invalid_and_unauthenticated_queries_fail_explicitly(self):
        self.assertEqual(self.request('/api/v1/vulnerabilities?limit=1',auth=False)[0],401)
        self.assertEqual(self.request('/api/v1/vulnerabilities?limit=0')[0],400)
        self.assertEqual(self.request('/api/v1/vulnerabilities?sort=bogus')[0],400)
