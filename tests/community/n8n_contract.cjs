// Exercise compiled nodes with adversarial protocol responses; no external traffic.
const assert=require('node:assert/strict'),{createHmac}=require('node:crypto');
const {DarkmoonTrigger}=require('../../integrations/upstream/n8n/dist/nodes/DarkmoonTrigger/DarkmoonTrigger.node.js');
const {launchAndCorrelate,dmDelete}=require('../../integrations/upstream/n8n/dist/nodes/Darkmoon/GenericFunctions.js');
const node={id:'contract',name:'DarkMoon',type:'darkmoon',typeVersion:1,position:[0,0],parameters:{}};
const session={apiBase:'http://fixture.invalid/api/v1',token:'contract-secret-token'};
const clone=x=>JSON.parse(JSON.stringify(x));
let passed=0;
async function check(name,fn){await fn();passed++;console.log('PASS '+name);}
function ctx(state,respond,params={}){return {getNode:()=>node,getCredentials:async()=>({baseUrl:session.apiBase,authMethod:'token',token:session.token}),getWorkflowStaticData:()=>state,getMode:()=> 'trigger',getNodeParameter:(name,def)=>params[name]??def,helpers:{httpRequest:async o=>respond(new URL(o.url).pathname,o)}};}
const response=(body,statusCode=200)=>({body,statusCode});
(async()=>{
 await check('launch uses explicit campaign identity; unrelated completed campaigns are never listed',async()=>{
  const calls=[];const c=ctx({},(path,o)=>{calls.push(path);return response(o.method==='POST'?{run_id:'run_new',campaign_id:'camp_new'}:{data:{id:'camp_new',status:'completed',stats:{high:1}}});});
  const result=await launchAndCorrelate(c,node,session,{}, {wait:true,pollMs:1,timeoutMs:100});
  assert.equal(result.campaignId,'camp_new');assert.equal(result.campaign.id,'camp_new');assert.equal(result.status,'completed');
  assert.deepEqual(calls,['/api/v1/run/campaign','/api/v1/campaigns/camp_new']);
 });
 await check('non-waited launches retain returned campaign id',async()=>{
  const result=await launchAndCorrelate(ctx({},()=>response({run_id:'run_new',campaign_id:'camp_new'})),node,session,{}, {wait:false,pollMs:1,timeoutMs:100});
  assert.equal(result.campaignId,'camp_new');assert.equal(result.campaign,null);
 });
 await check('legacy run lookup is explicit and mismatched campaign details fail closed',async()=>{
  const c=ctx({},path=>response(path.endsWith('/run/campaign')?{run_id:'run_new'}:path.endsWith('/run/run_new')?{campaign_id:'camp_new'}:{data:{id:'camp_other',status:'completed'}}));
  await assert.rejects(()=>launchAndCorrelate(c,node,session,{}, {wait:true,pollMs:1,timeoutMs:100}),/does not match/);
  const missing=ctx({},()=>response({}));await assert.rejects(()=>launchAndCorrelate(missing,node,session,{}, {wait:true,pollMs:1,timeoutMs:100}),/no run or campaign identity/);
 });
 await check('awaiting review times out rather than reporting a clean completed campaign',async()=>{
  const c=ctx({},(path,o)=>response(o.method==='POST'?{campaign_id:'camp_new'}:{data:{id:'camp_new',status:'awaiting_review'}}));
  const result=await launchAndCorrelate(c,node,session,{}, {wait:true,pollMs:1,timeoutMs:15});assert.equal(result.status,'timeout');
 });
 await check('failed and aborted launcher states terminate explicitly',async()=>{
  for(const [raw,expected] of [['timed_out','failed'],['interrupted','failed'],['aborted','stopped']]){
   const c=ctx({},(path,o)=>response(o.method==='POST'?{campaign_id:'camp_new'}:{data:{id:'camp_new',status:raw}}));
   assert.equal((await launchAndCorrelate(c,node,session,{}, {wait:true,pollMs:1,timeoutMs:100})).status,expected);
  }
 });
 await check('deletion errors retain webhook registration for retry without logging response secrets',async()=>{
  const state={webhookId:'hook_fixture',webhookSecret:'retained-signing-secret'};
  const c=ctx(state,()=>response({detail:'SECRET RESPONSE'},403));
  await assert.rejects(()=>dmDelete(c,node,session,'/webhooks/hook_fixture'));
  await assert.rejects(()=>new DarkmoonTrigger().webhookMethods.default.delete.call(c),error=>!/SECRET/.test(error.message));
  assert.equal(state.webhookId,'hook_fixture');assert.equal(state.webhookSecret,'retained-signing-secret');
  c.helpers.httpRequest=async()=>response({},404);await new DarkmoonTrigger().webhookMethods.default.delete.call(c);
  assert.equal(state.webhookId,undefined);assert.equal(state.webhookSecret,undefined);
 });
 await check('webhook signing secret stays in encrypted credentials and legacy static secret is removed on replacement',async()=>{
  const state={webhookId:'old',webhookSecret:'legacy-exportable-secret'},calls=[];
  const c=ctx(state,(path,o)=>{calls.push([path,o.method,o.body]);return response(o.method==='POST'?{id:'new'}:o.method==='GET'?{data:[{id:'new'}]}:{});},{mode:'webhook'});
  c.getCredentials=async()=>({baseUrl:session.apiBase,authMethod:'token',token:session.token,webhookSecret:'encrypted-credential-signing-secret'});
  c.getNodeWebhookUrl=()=> 'http://127.0.0.1/webhook/fixture';
  const hooks=new DarkmoonTrigger().webhookMethods.default;
  assert.equal(await hooks.checkExists.call(c),false);await hooks.create.call(c);
  assert.equal(state.webhookId,'new');assert.equal(state.webhookSecret,undefined);
  assert.equal(calls[0][1],'DELETE');assert.equal(calls[1][2].secret,'encrypted-credential-signing-secret');
  assert.equal(await hooks.checkExists.call(c),true);
 });
 let rows=[],campaigns=[],proposals=[],fail=false;const state={};
 const c=ctx(state,path=>{if(fail&&path.endsWith('/campaigns'))return response({},503);return response({data:path.endsWith('/vulnerabilities')?rows:path.endsWith('/campaigns')?campaigns:proposals});});
 const poll=()=>DarkmoonTrigger.prototype.poll.call(c);
 await check('first poll primes; identical finding ids in two campaigns remain independent',async()=>{
  rows=[{id:'same',campaign_id:'camp_a',status:'confirmed'},{id:'same',campaign_id:'camp_b',status:'exploited'}];assert.equal(await poll(),null);
  rows[1].status='confirmed';const out=await poll();assert.equal(out[0].length,1);assert.equal(out[0][0].json.data.campaign_id,'camp_b');
 });
 await check('poll cursor survives serialization and does not advance after partial API failure',async()=>{
  Object.assign(state,clone(state));assert.equal(await poll(),null);const before=clone(state);
  rows.push({id:'new',campaign_id:'camp_b',status:'exploited'});fail=true;await assert.rejects(poll);assert.deepEqual(clone(state),before);
  fail=false;const out=await poll();assert.ok(out[0].some(e=>e.json.event==='finding.discovered'&&e.json.data.finding_id==='new'));
 });
 await check('polling excludes evidence/endpoints/arbitrary stats and distinguishes local proposals from PRs',async()=>{
  rows.push({id:'private',campaign_id:'camp_a',status:'confirmed',endpoint:'SECRET-ENDPOINT',evidence:{body:'SECRET-EVIDENCE'}});
  campaigns=[{id:'camp_a',status:'completed',stats:{high:2,evidence:'SECRET-STATS'}}];proposals=[{id:'local',campaign_id:'camp_a',status:'validated',state:'validated',published:false}];
  const out=await poll();assert.doesNotMatch(JSON.stringify(out),/SECRET/);assert.ok(out[0].some(e=>e.json.event==='remediation.updated'));assert.ok(!out[0].some(e=>e.json.event==='pr.opened'));
  proposals[0].published=true;assert.equal((await poll())[0][0].json.event,'pr.opened');
 });
 await check('changing API source re-primes the cursor',async()=>{
  c.getCredentials=async()=>({baseUrl:'http://other.invalid',authMethod:'token',token:session.token});assert.equal(await poll(),null);
 });
 await check('signed webhook output is allowlisted and replay suppression survives a restart',async()=>{
  const signingSecret='fixture-signing-secret',receipts=new Set();let state={webhookId:'hook_fixture'},headers={},body,replyStatus;
  const reply={status:s=>{replyStatus=s;return reply},json:()=>reply};
  const c={getCredentials:async()=>({webhookSecret:signingSecret,baseUrl:session.apiBase,authMethod:'token',token:session.token}),getNode:()=>node,helpers:{httpRequest:async o=>{const id=o.body.event_id,claimed=!receipts.has(id);receipts.add(id);return response({claimed});}},getResponseObject:()=>reply,getWorkflowStaticData:()=>state,getRequestObject:()=>({body,rawBody:Buffer.from(JSON.stringify(body))}),getHeaderData:()=>headers,getNodeParameter:()=>[]};
  const deliver=async(id,event='finding.exploited')=>{
   body={id,event,raw:'SECRET-RAW',data:{finding_id:'f1',campaign_id:'c1',evidence:{body:'SECRET-EVIDENCE'},endpoint:'SECRET-ENDPOINT'}};
   const stamp=String(Math.floor(Date.now()/1000)),raw=JSON.stringify(body),secret=signingSecret;
   headers={'x-darkmoon-event-id':id,'x-darkmoon-timestamp':stamp,'x-darkmoon-signature':'sha256='+createHmac('sha256',secret).update(raw).digest('hex'),'x-darkmoon-signature-v2':'sha256='+createHmac('sha256',secret).update(`${stamp}.${id}.${raw}`).digest('hex')};
   return DarkmoonTrigger.prototype.webhook.call(c);
  };
  const first=await deliver('evt_new');assert.ok(first.workflowData);assert.doesNotMatch(JSON.stringify(first),/SECRET/);
  state=clone(state);assert.equal((await deliver('evt_new')).workflowData,undefined);
  assert.ok((await deliver('__proto__')).workflowData);state=clone(state);assert.equal((await deliver('__proto__')).workflowData,undefined);
  await deliver('evt_bad','');assert.equal(replyStatus,400);
  await deliver('evt_unicode');headers['x-darkmoon-signature']='é'.repeat(64);await DarkmoonTrigger.prototype.webhook.call(c);assert.equal(replyStatus,401);
  const request=c.helpers.httpRequest;c.helpers.httpRequest=async()=>response({},503);const refused=await deliver('evt_retry');assert.equal(replyStatus,503);assert.equal(refused.workflowData,undefined);c.helpers.httpRequest=request;assert.ok((await deliver('evt_retry')).workflowData);
 });
 console.log(JSON.stringify({status:'passed',checks:passed}));
})().catch(e=>{console.error(e.stack);process.exitCode=1});
