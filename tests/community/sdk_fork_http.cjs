// Built SDK over the actual fork HTTP service with disposable, offline records.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path'),{spawn}=require('node:child_process');
const {DarkmoonClient,AuthError}=require('../../integrations/upstream/client/dist/index.cjs');
(async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'darkmoon-sdk-fork-'));
 const child=spawn(process.env.DARKMOON_TEST_PYTHON||'python3',['tests/community/browser_fixture.py'],{cwd:path.resolve(__dirname,'../..'),env:{...process.env,PYTHONPATH:'mcp',DARKMOON_SHARED_DIR:root}});
 let log='';child.stderr.on('data',c=>log+=c);
 try{
  const ready=await new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(Error('Fixture startup timeout: '+log.slice(-1000))),20000);child.stdout.on('data',c=>{out+=c;for(const line of out.split('\n'))try{const d=JSON.parse(line);if(d.port){clearTimeout(timer);resolve(d);}}catch{}});child.once('exit',code=>{clearTimeout(timer);reject(Error('Fixture exited '+code+': '+log.slice(-1000)));});});
  const baseUrl='http://127.0.0.1:'+ready.port;
  const client=new DarkmoonClient({mode:'pro',pro:{baseUrl,username:'fixture-admin',password:'offline-fixture-password'}});
  const list=await client.listCampaigns();assert.equal(list.length,3);
  const campaign=await client.getCampaign(ready.campaign_id);assert.equal(campaign.id,ready.campaign_id);assert.equal(campaign.status,'completed');assert.equal(campaign.severity.total,3);
  const findings=await client.listFindings({campaignId:campaign.id});assert.equal(findings.length,3);assert.ok(findings.every(f=>f.campaignId===campaign.id&&f.evidence===null));
  const finding=await client.getFinding(ready.finding_id,{includeEvidence:true});assert.equal(finding.id,ready.finding_id);
  const report=await client.getReport(campaign.id);assert.equal(report.campaignId,campaign.id);assert.equal(report.redacted,true);
  assert.equal((await client.detect()).available,true);
  assert.equal((await client.getEvidenceMeta(ready.finding_id)).hasEvidence,true);
  assert.ok((await client.getTimeseries({metric:'severity',group:'day'})).series.length);
  const hook=await client.registerWebhook({url:'https://receiver.example/hook',events:['campaign.completed'],secret:'offline-sdk-webhook-secret-123456'});
  assert.ok(hook.id);assert.equal((await client.listWebhooks()).length,1);
  assert.equal(await client.deleteWebhook(hook.id),true);
  const retest=await client.launchRetest({campaignId:campaign.id});
  assert.equal((await client.getRetest(retest.retestId)).retestId,retest.retestId);
  const launch=await client.launchCampaign({target:'fixture.example',program:'SDK contract assessment',focus:['sqli']});
  assert.ok(launch.runId);
  const progress=[];
  for await(const event of client.streamProgress(launch,{signal:AbortSignal.timeout(15000)})){
    progress.push(event);if(event.terminal)break;
  }
  assert.ok(progress.some(event=>event.type==='run_completed'));
  const invalid=new DarkmoonClient({mode:'pro',pro:{baseUrl,token:'invalid-fixture-token'}});await assert.rejects(()=>invalid.listCampaigns(),AuthError);
  console.log('PASS built SDK against actual fork HTTP: authenticated reads, three campaign identities, exact detail/finding/report identity, counts, evidence default, invalid-token rejection, capabilities, analytics, webhook CRUD, retest and launch/SSE');
 }finally{child.kill('SIGTERM');await new Promise(resolve=>{if(child.exitCode!==null)return resolve();const timer=setTimeout(()=>child.kill('SIGKILL'),5000);child.once('exit',()=>{clearTimeout(timer);resolve();});});}
})().catch(error=>{console.error(error);process.exitCode=1});
