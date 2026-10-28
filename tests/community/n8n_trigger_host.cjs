// Real n8n host lifecycle over a loopback protocol fixture. Never external delivery.
const {spawn}=require('node:child_process'),{createHmac,randomUUID}=require('node:crypto'),{createRequire}=require('node:module');
const http=require('node:http'),net=require('node:net'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const pause=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  assert.ok(Object.values(os.networkInterfaces()).flat().every(address=>address.internal), 'Native n8n tests require an isolated --network none container.');
 const cli=process.env.DARKMOON_N8N_CLI;if(!cli)throw Error('Set DARKMOON_N8N_CLI');
 const parse=createRequire(path.resolve(cli))('flatted').parse;
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'darkmoon-trigger-host-')),repo=path.resolve(__dirname,'../..');
 const token='disposable-trigger-host-api-token',secret='disposable-trigger-signing-secret-123456789';
 const hooks=new Map();let findingStatus='confirmed',polls=0;
 const mock=http.createServer(async(req,res)=>{
  const send=(status,body)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(body));};
  if(req.headers.authorization!=='Bearer '+token)return send(401,{error:'Unauthorized'});
  const route=new URL(req.url,'http://localhost').pathname;
  if(route==='/api/v1/vulnerabilities'){polls++;return send(200,{data:[{id:'fixture_finding',campaign_id:'fixture_campaign',severity:'high',status:findingStatus,evidence:{body:'DO-NOT-FORWARD-EVIDENCE'},endpoint:'DO-NOT-FORWARD-ENDPOINT'}]});}
  if(route==='/api/v1/campaigns')return send(200,{data:[{id:'fixture_campaign',status:'running'}]});
  if(route==='/api/v1/pull-requests')return send(200,{data:[]});
  if(route==='/api/v1/webhooks'&&req.method==='GET')return send(200,{data:[...hooks.values()].map(({secret,...safe})=>safe)});
  if(route==='/api/v1/webhooks'&&req.method==='POST'){
   let text='';for await(const part of req)text+=part;const body=JSON.parse(text),id='hook_'+hooks.size;
   assert.equal(body.secret,secret);hooks.set(id,{id,...body});return send(201,{id});
  }
  if(route.startsWith('/api/v1/webhooks/')&&req.method==='DELETE'){hooks.delete(route.split('/').at(-1));return send(200,{deleted:true});}
  send(404,{error:'Not found'});
 });
 await new Promise(resolve=>mock.listen(0,'127.0.0.1',resolve));
 const mockUrl='http://127.0.0.1:'+mock.address().port;
 const port=await new Promise(resolve=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p));});});
 const base='http://127.0.0.1:'+port;
 const env={...process.env,N8N_USER_FOLDER:path.join(root,'n8n'),N8N_DIAGNOSTICS_ENABLED:'false',N8N_DYNAMIC_BANNERS_ENABLED:'false',N8N_VERSION_NOTIFICATIONS_WHATS_NEW_ENABLED:'false',N8N_LICENSE_AUTO_RENEW_ENABLED:'false',N8N_VERSION_NOTIFICATIONS_ENABLED:'false',N8N_TEMPLATES_ENABLED:'false',N8N_RUNNERS_ENABLED:'false',N8N_ENCRYPTION_KEY:'disposable-trigger-host-encryption-key',N8N_SECURE_COOKIE:'false',N8N_LOG_LEVEL:'warn',N8N_PORT:String(port),N8N_HOST:'127.0.0.1',N8N_LISTEN_ADDRESS:'127.0.0.1',WEBHOOK_URL:base};
 let host,cookie='',log='';
 const run=args=>new Promise((resolve,reject)=>{const p=spawn(process.execPath,[cli,...args],{env,cwd:root});let out='';p.stdout.on('data',c=>out+=c);p.stderr.on('data',c=>out+=c);const timer=setTimeout(()=>{p.kill('SIGTERM');reject(Error('n8n CLI timeout'));},120000);p.on('error',reject);p.on('exit',code=>{clearTimeout(timer);code?reject(Error(out.slice(-3000))):resolve(out);});});
 const wait=async(label,predicate,timeout=80000)=>{const deadline=Date.now()+timeout;while(Date.now()<deadline){if(await predicate())return;await pause(250);}throw Error(label+' timed out\n'+log.slice(-3000));};
 const start=async()=>{host=spawn(process.execPath,[cli,'start'],{env,cwd:root});host.stdout.on('data',c=>log+=c);host.stderr.on('data',c=>log+=c);await wait('host readiness',async()=>{if(host.exitCode!==null)throw Error(log.slice(-3000));try{return(await fetch(base+'/healthz/readiness')).ok;}catch{return false;}},40000);};
 const stop=async()=>{const current=host;if(!current||current.exitCode!==null)return;const exited=new Promise(resolve=>current.once('exit',resolve));const timer=setTimeout(()=>{if(current.exitCode===null)current.kill('SIGKILL');},15000);current.kill('SIGTERM');try{await exited;}finally{clearTimeout(timer);}};
 const api=async(route,method='GET',body)=>{const res=await fetch(base+route,{method,headers:{'Content-Type':'application/json',Cookie:cookie},...(body?{body:JSON.stringify(body)}:{})});const text=await res.text();assert.ok(res.ok,method+' '+route+' '+res.status+' '+text.slice(0,500));return JSON.parse(text).data;};
 const executions=async id=>(await api('/rest/executions?limit=100&filter='+encodeURIComponent(JSON.stringify({workflowId:id})))).results;
 const workflow=async mode=>{
  const saved=await api('/rest/workflows','POST',{name:'Disposable DarkMoon '+mode,nodes:[{id:'trigger',webhookId:randomUUID(),name:'DarkMoon Trigger',type:'n8n-nodes-darkmoon.darkmoonTrigger',typeVersion:1,position:[0,0],credentials:{darkmoonApi:{id:'triggercredential',name:'Disposable trigger credential'}},parameters:{mode,events:[],pollTimes:{item:[{mode:'everyMinute'}]}}},{id:'output',name:'Output',type:'n8n-nodes-base.noOp',typeVersion:1,position:[250,0],parameters:{}}],connections:{'DarkMoon Trigger':{main:[[{node:'Output',type:'main',index:0}]]}},settings:{executionOrder:'v1',saveDataSuccessExecution:'all',saveDataErrorExecution:'all'}});
  await api('/rest/workflows/'+saved.id+'/activate','POST',{versionId:saved.versionId});return saved.id;
 };
 try{
  const installed=path.join(root,'n8n/.n8n/nodes/node_modules/n8n-nodes-darkmoon');await fs.mkdir(installed,{recursive:true});await fs.cp(path.join(repo,'integrations/upstream/n8n/dist'),path.join(installed,'dist'),{recursive:true});await fs.copyFile(path.join(repo,'integrations/upstream/n8n/package.json'),path.join(installed,'package.json'));
  const file=path.join(root,'credential.json');await fs.writeFile(file,JSON.stringify([{id:'triggercredential',name:'Disposable trigger credential',type:'darkmoonApi',data:{baseUrl:mockUrl,authMethod:'token',token,webhookSecret:secret}}]),{mode:0o600});await run(['import:credentials','--input='+file]);await fs.unlink(file);
  await start();const setup=await fetch(base+'/rest/owner/setup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'trigger-test@example.invalid',firstName:'Disposable',lastName:'Operator',password:'DisposableTriggerPassword42!'})});assert.equal(setup.status,200,await setup.text());cookie=setup.headers.getSetCookie().map(c=>c.split(';')[0]).join('; ');
  console.log('Native trigger: activating poll workflow');
  const pollId=await workflow('poll');await wait('initial poll',async()=>polls>0,10000);assert.equal((await executions(pollId)).length,0);
  findingStatus='exploited';console.log('Native trigger: waiting for scheduled transition');
  await wait('poll transition',async()=>(await executions(pollId)).some(e=>e.status==='success'));
  const beforeRestart=(await executions(pollId)).length;
  const detail=await api('/rest/workflows/'+pollId);assert.doesNotMatch(JSON.stringify(detail),new RegExp(secret));assert.ok(JSON.stringify(detail.staticData).includes('exploited'));
  console.log('Native trigger: restarting persisted poll workflow');
  await stop();const previousPolls=polls;await start();await wait('reactivated poll',async()=>polls>previousPolls,15000);assert.equal((await executions(pollId)).length,beforeRestart);
  const hookId=await workflow('webhook');await wait('webhook registration',async()=>hooks.size===1,10000);
  const registration=[...hooks.values()][0];const saved=await api('/rest/workflows/'+hookId);assert.doesNotMatch(JSON.stringify(saved),new RegExp(secret));
  const deliver=async(id,valid=true)=>{const body={id,event:'finding.exploited',raw:'DO-NOT-FORWARD-RAW',data:{campaign_id:'fixture_campaign',finding_id:'fixture_finding',severity:'high',evidence:{body:'DO-NOT-FORWARD-EVIDENCE'},endpoint:'DO-NOT-FORWARD-ENDPOINT'}};const payload=JSON.stringify(body,null,2),stamp=String(Math.floor(Date.now()/1000));return fetch(registration.url,{method:'POST',headers:{'Content-Type':'application/json','X-Darkmoon-Event-Id':id,'X-Darkmoon-Timestamp':stamp,'X-Darkmoon-Signature':'sha256='+createHmac('sha256',secret).update(payload).digest('hex'),'X-Darkmoon-Signature-V2':valid?'sha256='+createHmac('sha256',secret).update(`${stamp}.${id}.${payload}`).digest('hex'):'sha256=invalid'},body:payload});};
  console.log('Native trigger: HTTP signature rejection and safe downstream payload');
  assert.equal((await deliver('evt_invalid',false)).status,401);
  assert.equal((await executions(hookId)).length,0);
  assert.equal((await deliver('evt_persisted')).status,200);
  await wait('webhook execution',async()=>(await executions(hookId)).some(e=>e.status==='success'),20000);
  const rows=await executions(hookId),record=await api('/rest/executions/'+rows[0].id);const execution=typeof record.data==='string'?parse(record.data):record.data;
  const output=execution.resultData.runData.Output[0].data.main[0];assert.doesNotMatch(JSON.stringify(output),/DO-NOT-FORWARD|disposable-trigger/);assert.equal(output[0].json.data.finding_id,'fixture_finding');
  console.log('Native trigger: restarting webhook receiver and replaying signed event');
  await stop();await start();assert.equal(hooks.size,1,'restart must reuse registration');assert.equal((await deliver('evt_persisted')).status,200);await pause(1500);assert.equal((await executions(hookId)).length,rows.length);
  await api('/rest/workflows/'+hookId+'/deactivate','POST',{});assert.equal(hooks.size,0);assert.equal((await deliver('evt_after_deactivate')).status,404);
  await api('/rest/workflows/'+pollId+'/deactivate','POST',{});
  console.log(JSON.stringify({status:'passed',host:'n8n 2.45.4',checks:['poll activation primes without replay','scheduled transition','durable poll cursor across process restart','webhook credential secret absent from workflow export','HTTP 401 on invalid HMAC','safe downstream event projection','webhook registration reused across restart','replay suppressed after restart','deactivation removes remote registration and route'],root},null,2));
 }finally{await stop();mock.close();await fs.writeFile(path.join(root,'host.log'),log);}
})().catch(e=>{console.error(e.stack);if(e.cause)console.error('Cause:',String(e.cause));process.exitCode=1});
