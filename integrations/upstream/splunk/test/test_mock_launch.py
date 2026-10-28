#!/usr/bin/env python3
"""Real owned-loopback HTTP/TLS checks. No assessment engine or vendor host."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
import urllib.error
from http.server import HTTPServer
from unittest.mock import patch

HERE = Path(__file__).resolve().parent

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

alert = module('alert_loopback', HERE / '../darkmoon/bin/darkmoon_campaign.py')
forwarder = module('forwarder_loopback', HERE / '../forwarder/darkmoon-to-hec.py')
mock = module('mock_loopback', HERE / 'mock_darkmoon.py')

class LoopbackHandler(mock.Handler):
    def do_GET(self):
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', 'http://127.0.0.1:1/not-followed')
            self.end_headers()
            return
        records = {
            '/api/v1/campaigns': [{'id':'camp_mock','target_id':'target_mock01','status':'completed'}],
            '/api/v1/vulnerabilities': [{'id':'finding_mock','campaign_id':'camp_mock','target_id':'target_mock01','severity':'high','evidence':{'body':'PRIVATE-BODY'}}],
            '/api/v1/pull-requests': [{'id':'proposal_mock','published':False,'finding_ids':['finding_mock']}],
            '/api/v1/retest': [{'id':'retest_complete','status':'completed','target_id':'target_mock01','base_campaign_id':'camp_mock','new_campaign_id':'camp_new','findings':[{'finding_id':'finding_mock','verdict':'not_observed'}]}]
        }
        if self.path in records:
            if self.headers.get('Authorization') != 'Bearer TESTTOKEN':
                return self._send(401, {'error':'fixture authentication required'})
            return self._send(200, {'data':records[self.path]})
        return super().do_GET()

    def do_POST(self):
        if self.path == '/services/collector/event':
            if self.headers.get('Authorization') != 'Splunk FIXTUREHEC':
                return self._send(403, {'code':4})
            raw = self.rfile.read(int(self.headers['Content-Length']))
            self.server.events.extend(json.loads(line) for line in raw.splitlines())
            return self._send(200, {'code':0})
        return super().do_POST()

class LoopbackContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.calls = Path(self.tmp.name) / 'calls.json'
        manager = patch.object(mock, 'CALLS_FILE', str(self.calls))
        manager.start(); self.addCleanup(manager.stop)
        original = socket.create_connection
        def owned_only(address, *args, **kwargs):
            if address[0] not in ('127.0.0.1', 'localhost', '::1'):
                raise AssertionError('External connection prohibited by loopback fixture')
            return original(address, *args, **kwargs)
        manager = patch('socket.create_connection', side_effect=owned_only)
        manager.start(); self.addCleanup(manager.stop)
        self.server = HTTPServer(('127.0.0.1',0), LoopbackHandler)
        self.server.events = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)

    def test_authenticated_saved_target_and_campaign_launch_acceptance(self):
        for kind in ('retest','campaign'):
            ok, message = alert.darkmoon_call(self.base, 'TESTTOKEN', False, kind, 'demo-shop.local', 'non-destructive')
            self.assertTrue(ok, message)
            self.assertIn('completion is not yet established', message)
        calls = json.loads(self.calls.read_text())
        self.assertEqual([call['path'] for call in calls], ['/api/v1/retest','/api/v1/run/campaign'])
        self.assertEqual(calls[0]['payload']['target_id'], 'target_mock01')
        self.assertEqual(calls[1]['payload']['target'], 'demo-shop.local')
        self.assertTrue(all(call['has_auth'] for call in calls))
        self.assertFalse(alert.darkmoon_call(self.base,'TESTTOKEN',True,'retest','demo-shop.local','non-destructive')[0])
        self.assertFalse(alert.darkmoon_call(self.base,'wrong-token',False,'retest','demo-shop.local','non-destructive')[0])

    def test_real_poll_projection_and_batched_hec_admission(self):
        data = forwarder.poll_rest(self.base,'TESTTOKEN',False)
        self.assertEqual(set(data), {'campaigns','vulnerabilities','pull_requests','retests','targets'})
        events = forwarder.build_events(data)
        self.assertEqual(len(events),5)
        count = forwarder.send_hec(self.base+'/services/collector/event','FIXTUREHEC',events,False,batch_size=2)
        self.assertEqual(count,5)
        self.assertEqual(len(self.server.events),5)
        self.assertNotIn('PRIVATE-BODY',json.dumps(self.server.events))
        self.assertNotIn('TESTTOKEN',json.dumps(self.server.events))
        self.assertEqual([row['event']['record_type'] for row in events if row['sourcetype']=='darkmoon:retest'],['lifecycle','comparison'])
        self.assertEqual(next(row for row in events if row['event'].get('verdict'))['event']['verdict'],'not_observed')

    def test_actual_http_redirect_is_not_followed(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            forwarder._get_json(self.base+'/redirect', {'Authorization':'Bearer TESTTOKEN'},False)
        self.assertEqual(error.exception.code,302)
        error.exception.close()

    @unittest.skipUnless(shutil.which('openssl'), 'OpenSSL CLI required to generate an owned temporary TLS certificate')
    def test_tls_verifies_trust_and_hostname_before_sending_authorization(self):
        certificate = Path(self.tmp.name)/'certificate.pem'
        key = Path(self.tmp.name)/'key.pem'
        generated = subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                                    '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost',
                                    '-keyout',str(key),'-out',str(certificate)], capture_output=True,timeout=20)
        self.assertEqual(generated.returncode,0)
        secure = HTTPServer(('127.0.0.1',0),LoopbackHandler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate,key)
        secure.socket = context.wrap_socket(secure.socket,server_side=True)
        thread = threading.Thread(target=secure.serve_forever,daemon=True); thread.start()
        original_context = ssl.create_default_context
        try:
            url = 'https://localhost:'+str(secure.server_port)+'/api/v1/campaigns'
            with self.assertRaises(urllib.error.URLError):
                forwarder._get_json(url,{'Authorization':'Bearer TESTTOKEN'},True)
            with patch.object(forwarder.ssl,'create_default_context',side_effect=lambda:original_context(cafile=certificate)):
                self.assertEqual(len(forwarder._get_json(url,{'Authorization':'Bearer TESTTOKEN'},True)['data']),1)
                with self.assertRaises(urllib.error.URLError):
                    forwarder._get_json(url.replace('localhost','127.0.0.1'),{'Authorization':'Bearer TESTTOKEN'},True)
        finally:
            secure.shutdown(); secure.server_close(); thread.join(timeout=5)

if __name__ == '__main__':
    unittest.main()
