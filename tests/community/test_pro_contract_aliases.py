"""Pinned Pro method/input aliases preserve fork auth and version safeguards.

Reference: user-provided static audit, image sha256:48248382877e..., raw auth
source and run/scheduler typed declarations. No original runtime equivalence is
claimed; intentional security differences are asserted explicitly.
"""
import concurrent.futures
import http.client
import json
import threading

import test_community as fixtures
from community.server import HTTPServer, handler_for


class ProContractAliasTests(fixtures.Fixture):
    request = fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(self.service, {"127.0.0.1"}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        super().tearDown()

    def headers(self, role="analyst", username="operator", password="a-long-original-password"):
        self.service.accounts.create(username, password, role)
        token = self.service.accounts.login(username, password, "127.0.0.1")["token"]
        return {"Authorization": "Bearer " + token}

    def test_change_password_alias_renews_its_session_and_revokes_all_old_sessions(self):
        headers = self.headers()
        other = self.service.accounts.login("operator", "a-long-original-password", "other-client")["token"]
        new = "a-new-secret-long-password"
        status, body, _ = self.request('/api/v1/auth/change-password', 'POST',
                                      {"current_password":"a-long-original-password", "new_password":new}, headers=headers)
        self.assertEqual(status,200)
        result = json.loads(body)
        self.assertTrue(result["changed"]); self.assertFalse(result["reauthenticate"])
        self.assertIn("token",result); self.assertEqual(result["user"]["role"],"analyst")
        self.assertNotIn(new,body.decode()); self.assertNotIn("password_hash",body.decode()); self.assertNotIn('salt',result)
        self.assertIsNone(self.service.accounts.identity(other))
        self.assertEqual(self.request('/api/v1/auth/me',headers=headers)[0],401)
        self.assertEqual(self.request('/api/v1/auth/me',headers={"Authorization":"Bearer "+result["token"]})[0],200)
        user = self.service.store.get("users","operator")
        self.assertEqual(user["auth_version"],2); self.assertEqual(len(user["salt"]),32)
        self.assertNotIn(new,json.dumps(self.service.store.read()))

    def test_viewer_may_change_own_password_but_not_other_users(self):
        headers = self.headers('viewer')
        self.service.accounts.create('other','another-long-password','admin')
        before = self.service.store.get('users','other')
        raw = {"current_password":"a-long-original-password", "new_password":"a-new-long-viewer-password"}
        self.assertEqual(self.request('/api/v1/auth/change-password','POST',raw|{"username":"other"},headers=headers)[0],400)
        self.assertEqual(self.request('/api/v1/auth/change-password','POST',raw,headers=headers)[0],200)
        self.assertEqual(self.service.store.get('users','other'),before)

    def test_password_alias_rejects_anonymous_wrong_missing_weak_and_nonlocal_credentials(self):
        headers = self.headers()
        raw = {"current_password":"a-long-original-password", "new_password":"a-new-long-password"}
        self.assertEqual(self.request('/api/v1/auth/change-password','POST',raw,auth=False)[0],401)
        before = self.service.store.get('users','operator')
        for bad in ({"old_password":raw['current_password'],"new_password":raw['new_password']},
                    {"current_password":None,"new_password":raw['new_password']},
                    raw|{"new_password":"eight888"},raw|{"new_password":"x"*1025}):
            self.assertEqual(self.request('/api/v1/auth/change-password','POST',bad,headers=headers)[0],400)
        self.assertEqual(self.request('/api/v1/auth/change-password','POST',raw|{"current_password":"wrong"},headers=headers)[0],403)
        self.assertEqual(self.service.store.get('users','operator'),before)
        self.assertEqual(self.request('/api/v1/auth/change-password','POST',raw)[0],400)

    def test_concurrent_password_rotations_validate_the_current_hash_atomically(self):
        headers = self.headers()
        def change(i):
            return self.request('/api/v1/auth/change-password','POST',
                 {"current_password":"a-long-original-password","new_password":f"new-long-password-{i}"},headers=headers)[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(change,range(2)))
        self.assertEqual(results.count(200),1)
        self.assertTrue(all(status in {200,401,403} for status in results))
        self.assertEqual(self.service.store.get('users','operator')['auth_version'],2)

    def test_replacement_token_is_bound_to_its_own_rotation_during_later_rotation(self):
        headers = self.headers()
        identity = self.service.identity(headers['Authorization'])
        issue = self.service.accounts.issue
        first, second = 'first-new-long-password', 'second-new-long-password'
        def rotate_again_then_issue(user):
            self.service.accounts.password(identity,first,second)
            return issue(user)
        from unittest.mock import patch
        with patch.object(self.service.accounts,'issue',side_effect=rotate_again_then_issue):
            status,body,_=self.request('/api/v1/auth/change-password','POST',
                 {'current_password':'a-long-original-password','new_password':first},headers=headers)
        self.assertEqual(status,200)
        self.assertIsNone(self.service.accounts.identity(json.loads(body)['token']))
        self.assertEqual(self.service.store.get('users','operator')['auth_version'],3)
        latest=self.service.accounts.login('operator',second,'latest-client')['token']
        self.assertIsNotNone(self.service.accounts.identity(latest))

    def test_legacy_password_endpoint_retains_reauthentication_behavior(self):
        headers = self.headers()
        status,body,_ = self.request('/api/v1/auth/password','POST',
              {"old_password":"a-long-original-password","new_password":"legacy-new-long-password"},headers=headers)
        self.assertEqual(status,200); self.assertEqual(json.loads(body),{"changed":True,"reauthenticate":True})
        self.assertEqual(self.request('/api/v1/auth/me',headers=headers)[0],401)

    def test_delete_stop_is_bodyless_idempotent_and_preserves_campaign_identity(self):
        first = self.service.launch({"target":"owned-one.invalid"})
        second = self.service.launch({"target":"owned-two.invalid"})
        path = '/api/v1/run/'+first['id']+'/stop'
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            # Real bodyless DELETE: no JSON body or Content-Type header.
            connection.request('DELETE',path,headers={'Authorization':'Bearer '+self.service.token})
            response = connection.getresponse(); status=response.status; body=response.read()
        finally:
            connection.close()
        self.assertEqual(status,200); result=json.loads(body)
        self.assertEqual(result['id'],first['id']);self.assertEqual(result['campaign_id'],first['campaign_id'])
        self.assertEqual(result['status'],'cancelled')
        self.assertEqual(json.loads(self.request(path,'DELETE')[1]),result)
        self.assertEqual(self.service.store.get('jobs',second['id'])['status'],'queued')
        self.assertEqual(self.request('/api/v1/run/missing/stop','DELETE')[0],404)
        self.assertEqual(self.request(path,'DELETE',auth=False)[0],401)

    def test_stop_alias_denies_viewers_and_preserves_legacy_post(self):
        headers = self.headers('viewer')
        job = self.service.launch({"target":"owned.invalid"})
        path = '/api/v1/run/'+job['id']+'/stop'
        self.assertEqual(self.request(path,'DELETE',headers=headers)[0],403)
        self.assertEqual(self.service.store.get('jobs',job['id'])['status'],'queued')
        self.assertEqual(self.request(path,'POST',{})[0],200)

    def test_put_schedule_merges_only_versioned_fields_without_losing_scope_or_timing(self):
        item = self.service.scheduler.create({"target":"owned.invalid","out_of_scope":["skip.owned.invalid"],"enabled":False})
        url = '/api/v1/scheduler/'+item['id']
        status,body,_ = self.request(url,'PUT',{"version":1,"display_name":"Renamed","enabled":True})
        self.assertEqual(status,200);edited=json.loads(body)['data']
        self.assertEqual(edited['version'],2);self.assertEqual(edited['spec'],item['spec'])
        self.assertEqual(edited['next_run'],item['next_run']);self.assertTrue(edited['enabled'])
        self.assertEqual(self.request(url,'PUT',{"version":1,"display_name":"Stale"})[0],400)
        self.assertEqual(self.service.store.get('schedules',item['id']),edited)
        self.assertEqual(self.request(url,'PATCH',{"version":2,"display_name":"Legacy"})[0],200)

    def test_put_requires_version_even_for_toggle_and_denies_invalid_and_readonly_requests(self):
        item=self.service.scheduler.create({"target":"owned.invalid","enabled":False})
        url='/api/v1/scheduler/'+item['id'];headers=self.headers('viewer')
        self.assertEqual(self.request(url,'PUT',{"version":1,"enabled":True},auth=False)[0],401)
        self.assertEqual(self.request(url,'PUT',{"version":1,"enabled":True},headers=headers)[0],403)
        for raw in ({"enabled":True},{"version":True,"enabled":True},{"version":1,"unsupported_flat":"other.invalid"},{"version":1,"enabled":"false"}):
            self.assertEqual(self.request(url,'PUT',raw)[0],400)
        self.assertEqual(self.service.store.get('schedules',item['id']),item)
        self.assertEqual(self.request('/api/v1/scheduler/missing','PUT',{"version":1,"enabled":True})[0],404)
