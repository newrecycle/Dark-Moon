"""Producer-backed receiver admission survives restart without storing payloads."""
import concurrent.futures
import json
import threading
from unittest.mock import patch

import test_community as fixtures
from community.operations import Operations, WebhookReceiptCapacityError, WEBHOOK_RECEIPT_TTL
from community.server import HTTPServer, handler_for
from community.store import Store
from types import SimpleNamespace


class WebhookReceiptTests(fixtures.Fixture):
    def hook(self):
        return self.service.operations.register({'url':'https://receipt-fixture.example.invalid/hook',
            'secret':'RECEIPT-PRIVATE-SIGNING-SECRET-123456','events':['finding.exploited']})

    def test_atomic_admission_allows_one_caller_per_hook_and_event(self):
        hook=self.hook()['id']
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            results=list(pool.map(lambda _:self.service.operations.claim_webhook_event(hook,'evt_same',clock=1000),range(10)))
        self.assertEqual(sum(r['claimed'] for r in results),1)
        another=self.hook()['id']
        self.assertTrue(self.service.operations.claim_webhook_event(another,'evt_same',clock=1000)['claimed'])

    def test_receipt_survives_a_new_store_and_operations_instance(self):
        hook=self.hook()['id'];self.service.operations.claim_webhook_event(hook,'evt_restart',clock=1000)
        restarted=Operations(SimpleNamespace(store=Store(self.service.store.root)))
        self.assertFalse(restarted.claim_webhook_event(hook,'evt_restart',clock=1100)['claimed'])
        self.assertNotIn('RECEIPT-PRIVATE-SIGNING-SECRET',self.service.store.path.read_text())
        self.assertEqual(set(self.service.store.read()['webhook_receipts'][hook]),{'evt_restart'})

    def test_capacity_never_evicts_fresh_receipts_and_expired_entries_are_reclaimable(self):
        hook=self.hook()['id'];claim=self.service.operations.claim_webhook_event
        with patch('community.operations.MAX_WEBHOOK_RECEIPTS',2):
            claim(hook,'evt_a',clock=1000);claim(hook,'evt_b',clock=1001)
            with self.assertRaises(WebhookReceiptCapacityError) as error:claim(hook,'evt_c',clock=1002)
            self.assertGreater(error.exception.retry_after,0)
            self.assertFalse(claim(hook,'evt_a',clock=1003)['claimed'])
            self.assertEqual(len(self.service.store.read()['webhook_receipts'][hook]),2)
            self.assertTrue(claim(hook,'evt_c',clock=1002+WEBHOOK_RECEIPT_TTL)['claimed'])
            self.assertEqual(set(self.service.store.read()['webhook_receipts'][hook]),{'evt_c'})


class WebhookReceiptHTTPTests(fixtures.Fixture):
    request=fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        self.hook=self.service.operations.register({'url':'https://receipt-fixture.example.invalid/hook'})['id']
        self.url='/api/v1/webhooks/'+self.hook+'/events/claim'
        self.server=HTTPServer(('127.0.0.1',0),handler_for(self.service,{'127.0.0.1'}))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()

    def test_claim_is_admin_only_safe_and_idempotent(self):
        raw={'event_id':'evt_fixture'}
        self.assertEqual(self.request(self.url,'POST',raw,auth=False)[0],401)
        for role in ('viewer','analyst'):
            user=self.service.accounts.create(role,'a-long-receipt-password',role)
            token=self.service.accounts.issue(self.service.store.get('users',user['id']))['token']
            self.assertEqual(self.request(self.url,'POST',raw,headers={'Authorization':'Bearer '+token})[0],403)
        status,body,_=self.request(self.url,'POST',raw);self.assertEqual(status,200)
        self.assertEqual(json.loads(body),{'webhook_id':self.hook,'event_id':'evt_fixture','claimed':True})
        self.assertFalse(json.loads(self.request(self.url,'POST',raw)[1])['claimed'])
        self.assertTrue(json.loads(self.request('/api/v1/system/info',auth=False)[1])['features']['webhook_receipts'])

    def test_invalid_disabled_deleted_and_unknown_hooks_fail_closed(self):
        for raw in ({},{'event_id':None},{'event_id':'bad/id'},{'event_id':'x'*201},{'event_id':'evt_a','payload':'PRIVATE'}):
            self.assertEqual(self.request(self.url,'POST',raw)[0],400)
        self.assertNotIn('webhook_receipts',self.service.store.read())
        hook=self.service.store.get('webhooks',self.hook);hook['enabled']=False;self.service.store.save('webhooks',hook)
        self.assertEqual(self.request(self.url,'POST',{'event_id':'evt_a'})[0],403)
        hook['enabled']=True;self.service.store.save('webhooks',hook)
        self.request(self.url,'POST',{'event_id':'evt_a'})
        self.assertEqual(self.request('/api/v1/webhooks/'+self.hook,'DELETE')[0],200)
        self.assertNotIn(self.hook,self.service.store.read()['webhook_receipts'])
        self.assertEqual(self.request(self.url,'POST',{'event_id':'evt_a'})[0],404)

    def test_capacity_returns_retry_after_without_reopening_the_duplicate_window(self):
        with patch('community.operations.MAX_WEBHOOK_RECEIPTS',1):
            self.assertEqual(self.request(self.url,'POST',{'event_id':'evt_first'})[0],200)
            status,body,headers=self.request(self.url,'POST',{'event_id':'evt_next'})
            self.assertEqual(status,429);self.assertGreater(int(headers['Retry-After']),0)
            self.assertEqual(json.loads(body)['retry_after'],int(headers['Retry-After']))
            self.assertFalse(json.loads(self.request(self.url,'POST',{'event_id':'evt_first'})[1])['claimed'])
