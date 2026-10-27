// Execute imported nodes inside a real installed n8n CLI against our HTTP server.
// Uses disposable credentials/data and read-only campaign/finding operations.
const {spawn}=require('node:child_process');
const net=require('node:net');
const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
(async()=>{
  const cli=process.env.DARKMOON_N8N_CLI;
  if(!cli)throw Error('Set DARKMOON_N8N_CLI to an installed n8n/bin/n8n');
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'darkmoon-n8n-host-'));
  const repo=path.resolve(__dirname,'../..');
  const child=spawn(process.env.DARKMOON_PYTHON||'python3',[path.join(__dirname,'browser_fixture.py')],{cwd:repo,env:{...process.env,PYTHONPATH:path.join(repo,'mcp'),DARKMOON_SHARED_DIR:root,DARKMOON_DASHBOARD_TOKEN:'isolated-n8n-host-fixture-token-123456789'}});
  try{
    const fixture=await new Promise((resolve,reject)=>{
      let output='';const timer=setTimeout(()=>reject(Error('Fixture startup timeout')),15000);
      child.stdout.on('data',c=>{output+=c;if(output.includes('\n')){clearTimeout(timer);resolve(JSON.parse(output.split('\n')[0]));}});
      child.stderr.on('data',()=>{});child.on('exit',code=>{clearTimeout(timer);reject(Error('Fixture exited '+code));});
    });
    const env={...process.env,N8N_USER_FOLDER:path.join(root,'n8n'),N8N_DIAGNOSTICS_ENABLED:'false',N8N_VERSION_NOTIFICATIONS_ENABLED:'false',N8N_TEMPLATES_ENABLED:'false',N8N_RUNNERS_ENABLED:'false',N8N_ENCRYPTION_KEY:'isolated-native-host-test-key-123456789',N8N_SECURE_COOKIE:'false',N8N_LOG_LEVEL:'info'};
    const run=async args=>new Promise((resolve,reject)=>{
      const p=spawn(process.execPath,[cli,...args],{env,cwd:root});let output='',errors='';
      const timer=setTimeout(()=>{p.kill('SIGTERM');reject(Error('n8n CLI timed out'))},120000);
      p.stdout.on('data',c=>output+=c);p.stderr.on('data',c=>errors+=c);
      p.on('exit',code=>{fs.writeFile(path.join(root,args[0].replaceAll(':','-')+'.log'),output+errors);clearTimeout(timer);if(code)reject(Error('n8n '+args[0]+' exited '+code+': '+(output+errors).slice(-4000)));else resolve(output+errors)});
    });
    const installed=path.join(root,'n8n/.n8n/nodes/node_modules/n8n-nodes-darkmoon');
    await fs.mkdir(installed,{recursive:true});
    await fs.cp(path.join(repo,'integrations/upstream/n8n/dist'),path.join(installed,'dist'),{recursive:true});
    await fs.copyFile(path.join(repo,'integrations/upstream/n8n/package.json'),path.join(installed,'package.json'));
    const creds=path.join(root,'credentials.json');
    await fs.writeFile(creds,JSON.stringify([{id:'dmhostcredential',name:'Disposable DarkMoon host',type:'darkmoonApi',data:{baseUrl:`http://127.0.0.1:${fixture.port}`,authMethod:'token',token:fixture.token}}]),{mode:0o600});
    await run(['import:credentials','--input='+creds]);await fs.unlink(creds);
    const workflow={id:'dmhostworkflow01',name:'DarkMoon native host acceptance',nodes:[
      {id:'start',name:'Start',type:'n8n-nodes-base.manualTrigger',typeVersion:1,position:[0,0],parameters:{}},
      {id:'findings',name:'DarkMoon findings',type:'n8n-nodes-darkmoon.darkmoon',typeVersion:1,position:[250,0],parameters:{resource:'finding',operation:'list',findingFilters:{campaignId:fixture.campaign_id}},credentials:{darkmoonApi:{id:'dmhostcredential',name:'Disposable DarkMoon host'}}},
      {id:'end',name:'Output',type:'n8n-nodes-base.noOp',typeVersion:1,position:[500,0],parameters:{}}
    ],connections:{Start:{main:[[{node:'DarkMoon findings',type:'main',index:0}]]},'DarkMoon findings':{main:[[{node:'Output',type:'main',index:0}]]}},settings:{executionOrder:'v1'},active:false};
    const file=path.join(root,'workflow.json');await fs.writeFile(file,JSON.stringify(workflow));
    await run(['import:workflow','--input='+file]);
    const output=await run(['execute','--id='+workflow.id,'--rawOutput']);
    await fs.writeFile(path.join(root,'execution-output.json'),output);
    assert.doesNotMatch(output,/window\.injected|Differential response|reproduce\.py|isolated-n8n-host-fixture-token/);
    const start=output.indexOf('{');assert.ok(start>=0,'No JSON execution output');const result=JSON.parse(output.slice(start));
    assert.equal(result.finished,true,JSON.stringify(result.data?.resultData?.error||{}));
    const rows=result.data.resultData.runData.Output[0].data.main[0];
    assert.equal(rows[0].json.total,3);
    assert.equal(rows[0].json.findings.length,3);
    assert.ok(rows[0].json.findings.every(f=>f.evidence===null||f.evidence===undefined));
    const port=await new Promise((resolve,reject)=>{const server=net.createServer();server.once('error',reject);server.listen(0,'127.0.0.1',()=>{const port=server.address().port;server.close(()=>resolve(port))})});
    const host=spawn(process.execPath,[cli,'start'],{env:{...env,N8N_PORT:String(port),N8N_HOST:'127.0.0.1',N8N_LISTEN_ADDRESS:'127.0.0.1'},cwd:root});
    let hostLog='';host.stdout.on('data',c=>hostLog+=c);host.stderr.on('data',c=>hostLog+=c);
    try {
      const base=`http://127.0.0.1:${port}`;let ready=false;
      for(let attempt=0;attempt<100;attempt++){
        try{if((await fetch(base+'/healthz/readiness')).ok){ready=true;break}}catch{}
        if(host.exitCode!==null)throw Error('n8n editor exited during startup: '+hostLog.slice(-1000));
        await new Promise(resolve=>setTimeout(resolve,250));
      }
      assert.ok(ready,'n8n editor did not become ready');
      const setup=await fetch(base+'/rest/owner/setup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'host-test@example.invalid',firstName:'Disposable',lastName:'Operator',password:'NativeHostFixturePassword42!'})});
      assert.equal(setup.status,200,await setup.text());
      const cookie=setup.headers.getSetCookie().map(c=>c.split(';')[0]).join('; ');
      const checkCredential=async(data,expected)=>{
        const result=await fetch(base+'/rest/credentials/test',{method:'POST',headers:{'Content-Type':'application/json',Cookie:cookie},body:JSON.stringify({credentials:{id:'dmhostcredential',name:'Disposable credential test',type:'darkmoonApi',data}})});
        const body=await result.json();assert.equal(result.status,200,JSON.stringify(body));
        assert.equal(body.data.status,expected,JSON.stringify(body));
      };
      const url=`http://127.0.0.1:${fixture.port}`;
      await checkCredential({baseUrl:url,authMethod:'token',token:fixture.token},'OK');
      await checkCredential({baseUrl:url+'/api/v1',authMethod:'token',token:'invalid-disposable-token'},'Error');
      await checkCredential({baseUrl:url+'/api/v1',authMethod:'password',username:'fixture-admin',password:'offline-fixture-password'},'OK');
      await checkCredential({baseUrl:url,authMethod:'password',username:'fixture-admin',password:'invalid-disposable-password'},'Error');
    } finally {host.kill('SIGTERM');await fs.writeFile(path.join(root,'editor.log'),hostLog);}
    console.log(JSON.stringify({status:'passed',host:'real n8n CLI',checks:['encrypted credential import','custom node loading','real workflow engine','finding list over real DarkMoon HTTP','downstream output','safe metadata only','real editor credential tester accepts valid token/password and rejects invalid ones'],root},null,2));
  }finally{child.kill('SIGTERM');}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
