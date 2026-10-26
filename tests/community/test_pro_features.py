"""Reconstructed Pro features: isolated accounts, API, signing and operations."""
import io
import json
import os
import subprocess
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import test_community as fixtures
from api import json_storage as data
from community.auth import Accounts
from community.integrity import baseline, verify, seal_state
from community.operations import compare_retest, signed_headers, verify_delivery, timeseries
from community.server import HTTPServer, handler_for


class APITests(fixtures.Fixture):
    request = fixtures.HTTPTests.request

    def setUp(self):
        super().setUp()
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(self.service, {"127.0.0.1"}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        super().tearDown()

    def login(self, role="admin"):
        self.service.accounts.create("operator", "a-correct-long-password", role)
        status, body, _ = self.request('/api/v1/auth/login', 'POST', {'username':'operator','password':'a-correct-long-password'}, auth=False)
        self.assertEqual(status,200)
        return json.loads(body)['token']

    def test_account_login_jwt_role_and_revocation(self):
        token=self.login('viewer')
        headers={'Authorization':'Bearer '+token}
        self.assertEqual(self.request('/api/v1/dashboard/overview',headers=headers)[0],200)
        self.assertEqual(self.request('/api/v1/campaigns','POST',{'target':'example.com'},headers=headers)[0],403)
        self.assertEqual(self.request('/api/v1/credentials',headers=headers)[0],403)
        self.assertEqual(self.request('/api/v1/auth/logout','POST',{},headers=headers)[0],200)
        self.assertEqual(self.request('/api/v1/dashboard/overview',headers=headers)[0],401)

    def test_password_rotation_revokes_old_sessions(self):
        token=self.login();headers={'Authorization':'Bearer '+token}
        status,_,_=self.request('/api/v1/auth/password','POST',{'old_password':'a-correct-long-password','new_password':'another-correct-password'},headers=headers)
        self.assertEqual(status,200)
        self.assertEqual(self.request('/api/v1/dashboard/overview',headers=headers)[0],401)

    def test_credentials_are_encrypted_and_only_masked_metadata_is_returned(self):
        secret='private-test-token-that-must-never-appear'
        status,body,_=self.request('/api/v1/credentials','POST',{'name':'SCM','provider':'github','secret':secret})
        self.assertEqual(status,201);record=json.loads(body)['data'];self.assertNotIn(secret,body.decode())
        self.assertNotIn(secret,self.service.store.path.read_text())
        self.assertEqual(self.service.vault.resolve(record['id']),secret)
        short=self.service.vault.save({'name':'Short','secret':'a1B'})
        self.assertNotIn('a1B',json.dumps(short))
        self.assertNotIn('sealed',json.loads(self.request('/api/v1/credentials')[1])['data'][0])
        self.assertEqual(self.request('/api/v1/credentials/'+record['id'],'DELETE')[0],200)

    def test_public_capability_contract_is_non_sensitive(self):
        status,body,_=self.request('/api/v1/system/info',auth=False)
        self.assertEqual(status,200)
        info=json.loads(body);self.assertEqual(len(info['routers']),15)
        self.assertFalse(info['features']['publishing']);self.assertFalse(info['features']['licensing'])
        self.assertNotIn(str(self.root),body.decode())

    def test_sdk_campaign_finding_and_report_envelopes(self):
        cid=self.campaign()
        campaigns=json.loads(self.request('/api/v1/campaigns')[1]);self.assertEqual(campaigns['data'][0]['id'],cid)
        detail=json.loads(self.request('/api/v1/campaigns/'+cid)[1]);self.assertEqual(len(detail['data']['vulnerabilities']),1)
        findings=json.loads(self.request('/api/v1/vulnerabilities?campaign_id='+cid)[1]);self.assertEqual(len(findings['data']),1)
        self.assertNotIn('PRIVATE-EVIDENCE',json.dumps(findings))
        metadata=json.loads(self.request('/api/v1/vulnerabilities/vuln_fixture/evidence-meta')[1]);self.assertTrue(metadata['has_evidence'])
        report=json.loads(self.request('/api/v1/campaigns/'+cid+'/report')[1]);self.assertIn('PRIVATE-EVIDENCE',report['content'])

    def test_crud_project_and_target_analytics(self):
        self.campaign()
        project=data.load_projects()[0]
        status,body,_=self.request('/api/v1/projects/'+project['id']+'/analytics')
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['data']['total_vulnerabilities'],1)
        self.assertEqual(self.request('/api/v1/projects/'+project['id'],'DELETE')[0],400)
        status,body,_=self.request('/api/v1/projects','POST',{'name':'Empty project'})
        self.assertEqual(status,201)
        self.assertEqual(self.request('/api/v1/projects/'+json.loads(body)['data']['id'],'DELETE')[0],200)

    def test_run_endpoint_creates_a_real_local_queue_record_without_executing(self):
        status,body,_=self.request('/api/v1/run/campaign','POST',{'target':'example.com','program':'SDK run','focus':['sqli','xss'],'format':'h1','targets':['api.example.com']})
        self.assertEqual(status,202);job=json.loads(body)
        self.assertEqual(self.service.store.get('jobs',job['run_id'])['spec']['focus'],'sqli,xss')
        self.assertFalse(self.service.store.job_path(job['run_id']).exists())

    def test_webhook_creation_does_not_deliver_until_matching_event(self):
        self.service.operations.transport=unittest.mock.Mock(return_value=204)
        status,body,_=self.request('/api/v1/webhooks','POST',{'url':'https://receiver.example/hook','events':['campaign.updated'],'secret':'a-secret-with-24-or-more-characters'})
        self.assertEqual(status,201);record=json.loads(body)['data'];self.assertNotIn('secret',record)
        self.service.operations.transport.assert_not_called()
        self.service.operations.emit('campaign.updated',{'campaign_id':'camp_test','status':'completed','evidence':'DO NOT SEND'})
        self.service.operations.tick()
        args=self.service.operations.transport.call_args.args
        self.assertNotIn(b'DO NOT SEND',args[1])
        self.assertIn('X-Darkmoon-Signature',args[2])
        self.assertEqual(self.service.store.items('deliveries')[0]['status'],'delivered')

    def test_retest_absence_is_not_fabricated_as_proof_of_fix(self):
        cid=self.campaign()
        status,body,_=self.request('/api/v1/retest','POST',{'campaign_id':cid})
        self.assertEqual(status,201);record=json.loads(body)
        campaign=data.load_campaign(record['campaign_id']);campaign['status']='completed';data.save_campaign(campaign)
        self.service.operations.tick()
        result=self.service.store.get('retests',record['id'])
        self.assertEqual(result['verdicts'][0]['verdict'],'not_observed')
        self.assertNotIn('PRIVATE-EVIDENCE',json.dumps(result))

    def test_provider_profile_keeps_token_encrypted_until_explicit_apply(self):
        credential=self.service.vault.save({'name':'LLM','provider':'openai','secret':'private-api-key'})
        status,body,_=self.request('/api/v1/system/providers','POST',{'mode':'cloud','provider':'openai','model':'configured-model','credential_id':credential['id']})
        self.assertEqual(status,201);profile=json.loads(body)['data']
        self.assertFalse((self.root/'.opencode.env').exists())
        self.assertNotIn('private-api-key',body.decode())
        self.assertEqual(self.request('/api/v1/system/providers/'+profile['id']+'/apply','POST',{})[0],200)
        self.assertIn('OPENROUTER_API_KEY=private-api-key',(self.root/'.opencode.env').read_text())
        self.assertEqual((self.root/'.opencode.env').stat().st_mode&0o777,0o600)

    def test_one_shot_schedule_disables_itself_after_claim(self):
        status,body,_=self.request('/api/v1/scheduler','POST',{'target':'example.com','run_at':'2026-01-01T00:00:00Z'})
        self.assertEqual(status,201);record=json.loads(body)['data']
        self.service.scheduler.tick()
        self.assertFalse(self.service.store.get('schedules',record['id'])['enabled'])
        self.assertEqual(len(self.service.store.items('jobs')),1)

    def test_target_allowlist_applies_to_primary_and_additional_targets(self):
        with patch.dict(os.environ,{'DARKMOON_TARGET_ALLOWLIST':'*.example.com'}):
            self.assertEqual(self.request('/api/v1/run/campaign','POST',{'target':'test.example.com','targets':['outside.invalid']})[0],403)
            self.assertEqual(self.request('/api/v1/run/campaign','POST',{'target':'test.example.com'})[0],202)
        with patch.dict(os.environ,{'DARKMOON_TARGET_ALLOWLIST':'192.0.2.*'}):
            self.assertEqual(self.request('/api/v1/run/campaign','POST',{'target':'192.0.2.0/0'})[0],403)
        with patch.dict(os.environ,{'DARKMOON_TARGET_ALLOWLIST':'192.0.2.0/24'}):
            self.assertEqual(self.request('/api/v1/run/campaign','POST',{'target':'192.0.2.0/28'})[0],202)


class SecurityTests(fixtures.Fixture):
    def test_target_credentials_reach_only_the_local_tokenizer_stdin(self):
        from community.credential_launch import prepare
        key=self.service.vault.save({'name':'Target','provider':'target-login','username':'test-user','secret':'TARGET-PASSWORD-PRIVATE'})
        calls=[]
        def run(argv,**options):
            self.assertNotIn('TARGET-PASSWORD-PRIVATE',' '.join(argv));calls.append((argv,options))
            if argv[-1]=='version':return subprocess.CompletedProcess(argv,0)
            self.assertIn('TARGET-PASSWORD-PRIVATE',options['input'])
            return subprocess.CompletedProcess(argv,0,stdout=json.dumps({'tokenized':'TARGET: URL_001 CREDS=USER_001:CRED_001'}))
        result=prepare(self.root,self.service.store,'TARGET: https://test.example',{'assessment_credential_id':key['id']},run)
        self.assertNotIn('TARGET-PASSWORD-PRIVATE',result);self.assertIn('CRED_001',result);self.assertEqual(len(calls),2)

    def test_target_credential_launch_fails_closed_if_tokenization_leaks(self):
        from community.credential_launch import prepare
        key=self.service.vault.save({'name':'Target','provider':'target-token','secret':'PRIVATE-TARGET-TOKEN'})
        def run(argv,**options):return subprocess.CompletedProcess(argv,0,stdout=json.dumps({'tokenized':'TOKEN=PRIVATE-TARGET-TOKEN'}))
        with self.assertRaises(ValueError):prepare(self.root,self.service.store,'TARGET: example.com',{'assessment_token_id':key['id']},run)

    def test_sealed_privacy_vault_survives_restart_without_plaintext_on_disk(self):
        from community.privacy_audit import SealedPrivacyVault,audit_summary
        from src.privacy import Category
        state=self.root/'sealed-privacy'
        with patch.dict(os.environ,{'DARKMOON_VAULT_STATE_DIR':str(state)}):
            first=SealedPrivacyVault('fixture-session')
            placeholder=first.register('192.0.2.42',Category.IP_PUBLIC)
            secret=first.register('private-example-password',Category.CRED)
            second=SealedPrivacyVault('fixture-session')
            self.assertEqual(second.rehydrate(placeholder),'192.0.2.42')
            self.assertIsNone(second.rehydrate(secret))
        for file in state.rglob('*'):
            if file.is_file():
                self.assertNotIn(b'192.0.2.42',file.read_bytes())
                self.assertNotIn(b'private-example-password',file.read_bytes())
        summary=audit_summary(fixtures.Store(state));self.assertTrue(summary['valid']);self.assertEqual(summary['events'],2)

    def test_privacy_journal_tampering_is_detected(self):
        from community.privacy_audit import append_audit,audit_summary
        append_audit(self.service.store,'private-session','IP_PRIVATE',False)
        path=self.service.store.root/'privacy-audit.jsonl'
        self.assertNotIn('private-session',path.read_text())
        path.write_text(path.read_text().replace('denied','allowed'))
        self.assertFalse(audit_summary(self.service.store)['valid'])

    def test_parallel_sealed_vault_instances_do_not_reuse_placeholders(self):
        import concurrent.futures
        from community.privacy_audit import SealedPrivacyVault
        from src.privacy import Category
        with patch.dict(os.environ,{'DARKMOON_VAULT_STATE_DIR':str(self.root/'concurrent-vault')}):
            vaults=[SealedPrivacyVault('shared-session'),SealedPrivacyVault('shared-session')]
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                values=list(pool.map(lambda i:vaults[i%2].register('192.0.2.'+str(i+1),Category.IP_PUBLIC),range(20)))
            self.assertEqual(len(set(values)),20)

    def test_generated_patch_is_rejected_when_scope_judge_disapproves(self):
        from community.remediation import remediate
        cid=self.campaign();repo=fixtures.RemediationTests.source_repo(self)
        proposal={'edits':[{'path':'app.py','old':'vulnerable','new':'fixed'}],'explanation':'Proposed fix'}
        with patch('community.remediation.generate_edits',return_value=proposal),patch('community.remediation.judge_patch',return_value={'approved':False,'confidence':0.2,'reason':'Scope changed'}):
            result=remediate(repo,cid,'vuln_fixture',generate=True,files=['app.py'],store=self.service.store)
        self.assertEqual(result['status'],'rejected')
        self.assertFalse(result['published'])

    def test_generation_retries_only_in_the_isolated_worktree_after_failed_retest(self):
        from community.remediation import remediate
        cid=self.campaign();repo=fixtures.RemediationTests.source_repo(self)
        proposals=[{'edits':[{'path':'app.py','old':'vulnerable','new':replacement}]} for replacement in ['partial','fixed']]
        class Sandbox:
            def __init__(self,image):pass
            def probe(self,root,probe):return {'exit_code':0,'timed_out':False,'output':'42' if probe['kind']=='normal' else (Path(root)/'app.py').read_text()}
        with patch('community.remediation.generate_edits',side_effect=proposals),patch('community.remediation.judge_patch',return_value={'approved':True,'confidence':0.9,'reason':'Minimal change'}):
            result=remediate(repo,cid,'vuln_fixture',generate=True,validate=True,files=['app.py'],store=self.service.store,sandbox_factory=Sandbox)
        self.assertEqual(result['status'],'validated');self.assertEqual(len(result['attempts']),2)
        self.assertIn('vulnerable',(repo/'app.py').read_text())

    def test_model_proposals_cannot_edit_unsupplied_sources(self):
        from community.remediation import validate_proposal_scope
        with self.assertRaises(ValueError):validate_proposal_scope({'edits':[{'path':'unrelated.py','old':'a','new':'b'}]},['app.py'])

    def test_bug_bounty_and_custom_report_formats_are_real_exports(self):
        from community.reports import markdown
        cid=self.campaign();campaign=self.service.campaign(cid)
        self.assertIn('HackerOne submission dossier',markdown(campaign|{'report_format':'h1'}))
        self.assertIn('Bugcrowd submission dossier',markdown(campaign|{'report_format':'bugcrowd'}))
        template=self.root/'report-template.md';template.write_text('# Custom $campaign_name\n$report')
        with patch.dict(os.environ,{'DARKMOON_REPORT_TEMPLATE':str(template)}):
            self.assertTrue(markdown(campaign|{'report_format':'custom'}).startswith('# Custom '))

    def test_readonly_remote_source_checkout_keeps_secret_out_of_argv(self):
        from community.source_checkout import checkout
        credential=self.service.vault.save({'name':'Source','provider':'github','secret':'SOURCE-SECRET-NEVER-IN-ARGV'})
        calls=[]
        def run(argv,**options):
            self.assertNotIn('SOURCE-SECRET-NEVER-IN-ARGV',' '.join(argv))
            self.assertIn('credential.helper=',argv)
            self.assertEqual(options['env']['DM_CHECKOUT_SECRET'],'SOURCE-SECRET-NEVER-IN-ARGV')
            calls.append(argv);return subprocess.CompletedProcess(argv,0)
        result=checkout(self.service,'https://github.com/example/source.git','camp_test',credential['id'],run)
        self.assertEqual(len(calls),1);self.assertNotIn('push',calls[0]);self.assertTrue(str(result).endswith('camp_test'))

    def test_launch_credential_validation_preserves_request_idempotency(self):
        first=self.service.launch({'target':'first.example'},key='first_request')
        self.assertEqual(first['id'],self.service.launch({'target':'first.example'},key='first_request')['id'])
        second=self.service.launch({'target':'second.example'},key='second_request')
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(first['idempotency_key'],'first_request')
        with self.assertRaises(ValueError):
            self.service.launch({'target':'third.example'},key='first_request')
        with self.assertRaises(ValueError):
            self.service.launch({'target':'first.example','remediate':'false'})

    def test_local_remediation_never_emits_a_false_pr_opened_event(self):
        snapshot={'campaigns':[],'findings':[],'remediations':[]}
        with patch.object(self.service,'snapshot',return_value=snapshot):
            self.service.operations.tick()
            proposal={'id':'fix_local','status':'proposed','published':False}
            snapshot['remediations'].append(proposal)
            self.service.operations.tick()
            self.assertEqual([e['event'] for e in self.service.store.items('events')],['remediation.updated'])
            proposal['published']=True
            self.service.operations.tick()
            self.assertEqual(self.service.store.items('events')[-1]['event'],'pr.opened')

    def test_retest_host_lookup_preserves_original_engagement_boundaries(self):
        cid=self.campaign();campaign=data.load_campaign(cid)
        campaign['scope']={'targets':['secondary.example'],'out_of_scope':['excluded.example'],
                           'rules':'Never access production data','safe_harbor':'Original terms'}
        data.save_campaign(campaign)
        target=data.load_target(campaign['target_id'])
        record=self.service.operations.launch_retest({'target_id':target['host'],'safe_harbor':'non-destructive'})
        spec=self.service.store.get('jobs',record['run_id'])['spec']
        self.assertEqual(spec['out_of_scope'],['excluded.example'])
        self.assertEqual(spec['rules'],'Never access production data')
        self.assertIn('Original terms',spec['safe_harbor'])
        self.assertIn('non-destructive',spec['safe_harbor'])

    def test_update_lookup_is_readonly_and_explicit(self):
        from community.updates import status
        with patch('urllib.request.urlopen') as open_url:
            self.assertFalse(status()['checked']);open_url.assert_not_called()
        response=io.BytesIO(json.dumps({'last_updated':'2026-10-26T12:00:00Z','images':[{'architecture':'amd64','digest':'sha256:new'}]}).encode())
        with patch('urllib.request.urlopen',return_value=response),patch.dict(os.environ,{'DARKMOON_IMAGE_DIGEST':'sha256:old'}),patch('platform.machine',return_value='x86_64'):
            self.assertTrue(status(True)['update_available'])

    def test_signature_timestamp_and_event_id_prevent_replay(self):
        body=b'{"event":"campaign.updated"}';secret='a-long-private-webhook-signing-secret';seen=set()
        headers=signed_headers(secret,body,'evt_test',1000)
        self.assertTrue(verify_delivery(secret,body,headers,seen,clock=1001))
        self.assertFalse(verify_delivery(secret,body,headers,seen,clock=1001))
        self.assertFalse(verify_delivery(secret,b'changed',headers,set(),clock=1001))
        self.assertFalse(verify_delivery(secret,body,headers,set(),clock=2000))

    def test_integrity_lock_persists_until_explicit_reseal(self):
        file=self.root/'source.py';file.write_text('original')
        baseline(self.root,self.service.store,['source.py'])
        self.assertTrue(verify(self.root,self.service.store)['ok'])
        file.write_text('tampered');self.assertFalse(verify(self.root,self.service.store)['ok'])
        file.write_text('original');self.assertFalse(verify(self.root,self.service.store)['ok'])
        baseline(self.root,self.service.store,['source.py']);self.assertTrue(verify(self.root,self.service.store)['ok'])

    def test_corrupt_integrity_manifest_fails_closed(self):
        (self.service.store.root/'integrity.json').write_text('not JSON')
        self.assertTrue(verify(self.root,self.service.store)['locked'])

    def test_sealed_state_uses_authenticated_encryption(self):
        source=self.root/'plaintext';source.write_text('private state')
        sealed=self.root/'sealed';restored=self.root/'restored'
        seal_state(self.service.store,source,sealed)
        self.assertNotIn(b'private state',sealed.read_bytes())
        seal_state(self.service.store,sealed,restored,True)
        self.assertEqual(source.read_bytes(),restored.read_bytes())

    def test_password_hashes_and_expired_jwts(self):
        import jwt
        self.service.accounts.create('operator','correct-long-password','analyst')
        self.assertNotIn('correct-long-password',self.service.store.path.read_text())
        expired=jwt.encode({'sub':'operator','exp':1,'iat':0,'jti':'expired','ver':1,'aud':'darkmoon-api','iss':'darkmoon-community'},self.service.accounts.key,algorithm='HS256')
        self.assertIsNone(self.service.accounts.identity(expired))

    def test_oidc_pkce_nonce_signed_identity_and_default_readonly_role(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        env={'DARKMOON_OIDC_ISSUER':'https://identity.example','DARKMOON_OIDC_CLIENT_ID':'client-test','DARKMOON_OIDC_REDIRECT_URI':'https://workspace.example/callback'}
        metadata={'issuer':'https://identity.example','authorization_endpoint':'https://identity.example/authorize','token_endpoint':'https://identity.example/token','jwks_uri':'https://identity.example/jwks'}
        with patch.dict(os.environ,env),patch.object(self.service.accounts,'json_request',return_value=metadata):
            start=self.service.accounts.oidc_begin()
        self.assertIn('code_challenge_method=S256',start['url'])
        nonce=self.service.accounts.oidc_flows[start['state']]['nonce']
        signed=jwt.encode({'iss':'https://identity.example','aud':'client-test','sub':'test-subject','iat':int(time.time()),'exp':int(time.time())+60,'nonce':nonce},key,algorithm='RS256')
        jwks=types.SimpleNamespace(get_signing_key_from_jwt=lambda token:types.SimpleNamespace(key=key.public_key()))
        with patch.dict(os.environ,env),patch.object(self.service.accounts,'json_request',return_value={'id_token':signed}),patch('jwt.PyJWKClient',return_value=jwks):
            result=self.service.accounts.oidc_finish('test-code',start['state'])
            self.assertEqual(result['user']['role'],'viewer')
            with self.assertRaises(PermissionError):self.service.accounts.oidc_finish('test-code',start['state'])

    def test_oidc_invalid_nonce_cannot_issue_session(self):
        with self.assertRaises(PermissionError):self.service.accounts.oidc_finish('code','unknown-state')
        self.assertEqual(self.service.store.items('sessions'),[])

    def test_pdf_is_encrypted_and_has_a_valid_embedded_signature(self):
        from reportlab.pdfgen import canvas
        from community.report_security import init_signer,secure_pdf
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign.validation import validate_pdf_signature
        from pyhanko_certvalidator import ValidationContext
        from asn1crypto import pem,x509
        with patch.dict(os.environ,{'DARKMOON_SIGNING_PASSWORD':'correct-signing-password'}):
            init_signer(self.service.store,'Test operator','correct-signing-password')
            raw=io.BytesIO();document=canvas.Canvas(raw);document.drawString(50,700,'Literal evidence');document.save()
            protected=secure_pdf(raw.getvalue(),self.service.store,'correct-report-password')
        reader=PdfFileReader(io.BytesIO(protected));self.assertTrue(reader.encrypted)
        reader.decrypt('correct-report-password');self.assertEqual(len(reader.embedded_signatures),1)
        certificate=x509.Certificate.load(pem.unarmor((self.service.store.root/'report-signing-cert.pem').read_bytes())[2])
        status=validate_pdf_signature(reader.embedded_signatures[0],ValidationContext(trust_roots=[certificate],allow_fetching=False))
        self.assertTrue(status.intact);self.assertTrue(status.valid);self.assertTrue(status.trusted)

    def test_analytics_groups_recorded_findings_without_evidence(self):
        self.campaign();result=timeseries({'metric':'severity','group':'day'})
        self.assertEqual(result['series'][0]['key'],'high')
        self.assertEqual(result['series'][0]['points'][0]['value'],1)
        self.assertNotIn('PRIVATE-EVIDENCE',json.dumps(result))

    def test_automatic_remediation_enqueues_only_after_finalized_campaign(self):
        cid=self.campaign();repo=fixtures.RemediationTests.source_repo(self)
        campaign=data.load_campaign(cid);campaign['status']='completed';data.save_campaign(campaign)
        job={'id':'job_automation','campaign_id':cid,'spec':{'remediate':True,'git_repo':str(repo)},'status':'succeeded','finished_at':'2026-10-26T12:00:00Z'}
        with patch.object(self.service,'prepare_remediation') as prepare:
            self.service._finished(job)
        self.assertEqual(prepare.call_count,1)
        self.assertTrue(prepare.call_args.args[0]['generate'])


if __name__=='__main__':unittest.main()
