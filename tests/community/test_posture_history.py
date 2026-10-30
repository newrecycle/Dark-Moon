"""Real SQLite observation consistency, archive/recovery and HTTP authorization."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import patch

import test_evidence_access as evidence_fixtures
import test_community as fixtures
from community import posture_history as history
from community.posture import posture
from test_posture import workspace


class RecordedPostureTests(fixtures.Fixture):
    def setUp(self):
        super().setUp()
        import threading
        from community.server import HTTPServer, handler_for
        self.server=HTTPServer(('127.0.0.1',0),handler_for(self.service,{'127.0.0.1'}))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.cid=self.campaign();self.fid='vuln_fixture'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()
    request = evidence_fixtures.EvidenceHTTPTests.request
    role = evidence_fixtures.EvidenceHTTPTests.role
    # Reuse HTTP/storage setup, without re-collecting its inherited test methods.
    def test_record_read_archive_restore_and_corruption_refusal(self):
        store=self.service.store
        snapshot=workspace(); first=history.capture(store,posture(snapshot))
        snapshot['findings'][0]['status']='confirmed'
        second=history.capture(store,posture(snapshot))
        self.assertLess(first['created_at'],second['created_at'])
        old=history.read(store,first['created_at'])
        self.assertTrue(old['historical']); self.assertEqual(old['totals']['active'],4)
        self.assertEqual(history.read(store,second['created_at'])['totals']['active'],5)
        with self.assertRaises(KeyError): history.read(store,'2000-01-01T00:00:00Z')
        for value in ('bad','2026-01-01','2999-01-01T00:00:00Z'):
            with self.subTest(value=value),self.assertRaises(ValueError):history.read(store,value)
        target=self.root/'observations.jsonl'
        archived=history.archive(store,second['created_at'],target,prune=True)
        self.assertEqual(archived['pruned'],1)
        with self.assertRaises(KeyError):history.read(store,first['created_at'])
        self.assertEqual(history.restore(store,target)['restored'],1)
        self.assertEqual(history.restore(store,target)['restored'],0)
        self.assertEqual(history.read(store,first['created_at'])['totals'],old['totals'])
        with self.assertRaises(FileExistsError):history.archive(store,second['created_at'],target,prune=True)
        count=history.observations(store)['total']
        with patch.object(history,'MAX_RECORDS',count):
            with self.assertRaises(ValueError):history.capture(store,posture(snapshot))
        row=store.get('posture_history',first['id']);row['posture']['totals']['active']=999
        store.save('posture_history',row)
        with self.assertRaises(ValueError):history.read(store,first['created_at'])

    def test_recording_http_is_admin_only_and_asof_is_not_current_state(self):
        reader=self.role('viewer','posture_history_viewer')
        route='/api/v1/dashboard/posture/captures'
        self.assertEqual(self.request(route,'POST',{},headers=reader)[0],403)
        self.assertEqual(self.request(route,'POST',{},auth=False)[0],401)
        status,body,_=self.request(route,'POST',{})
        self.assertEqual(status,201)
        record=json.loads(body)
        self.service.change_finding(self.cid,self.fid,{'status':'false_positive','tracking_id':'issue_one'})
        url='/api/v1/dashboard/posture?as_of='+record['created_at'].replace('+','%2B')
        status,body,_=self.request(url,headers=reader)
        self.assertEqual(status,200)
        historical=json.loads(body)
        self.assertTrue(historical['historical']);self.assertEqual(historical['totals']['active'],1)
        current=json.loads(self.request('/api/v1/dashboard/posture')[1])
        self.assertEqual(current['totals']['active'],0)
        self.assertEqual(current['totals']['distinct_tracked_issues'],1)
        self.assertNotIn('PRIVATE-EVIDENCE',body.decode())
        self.assertEqual(self.request(url+'&from=2000-01-01T00:00:00Z')[0],400)
        self.assertEqual(self.request(url+'&as_of=bad')[0],400)
        self.assertEqual(self.request(route,headers=reader)[0],200)
