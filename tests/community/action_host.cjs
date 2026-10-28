// Execute the actual bundled action with toolkit file commands and owned HTTP.
const assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path'),{spawn}=require('node:child_process');
(async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'darkmoon-action-'));let mode='high',calls=[];
 const server=http.createServer((req,res)=>{
  req.resume();const route=new URL(req.url,'http://localhost').pathname;calls.push(route);
  const send=(data,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
  if(route==='/api/v1/system/info')return send({edition:'pro',api_version:'1.0.0',features:{sse_progress:false}});
  if(req.headers.authorization!=='Bearer fixture-action-token')return send({},401);
  if(route==='/api/v1/run/campaign')return send({run_id:'run_mine',campaign_id:'camp_mine'});
  if(route==='/api/v1/campaigns/camp_mine')return send({data:{id:'camp_mine',status:mode==='failed'?'failed':'completed',stats:{low:1,total_findings:1}}});
  if(route==='/api/v1/vulnerabilities'){
   if(mode==='auth')return send({detail:'DO-NOT-LEAK-ERROR'},401);
   if(mode==='malformed'){res.writeHead(200);return res.end('{');}
   return send({data:mode==='empty'?[]:[{id:'finding_mine',campaign_id:'camp_mine',severity:'high',status:'confirmed',title:'Loopback finding',evidence:{raw_response:'DO-NOT-LEAK-EVIDENCE'}}]});
  }
  return send({},404);
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const url='http://127.0.0.1:'+server.address().port;
 try{
  for(const scenario of ['high','empty','failed','auth','malformed']){
   mode=scenario;calls=[];const dir=path.join(root,scenario);await fs.mkdir(dir);
   const output=path.join(dir,'outputs'),summary=path.join(dir,'summary');await fs.writeFile(output,'');await fs.writeFile(summary,'');
   const r=await new Promise((resolve,reject)=>{
    const env={...process.env,GITHUB_OUTPUT:output,GITHUB_STEP_SUMMARY:summary,RUNNER_TEMP:dir,INPUT_MODE:'pro','INPUT_BASE-URL':url,'INPUT_API-TOKEN':'fixture-action-token',INPUT_TARGET:'owned.invalid','INPUT_FAIL-ON':'high','INPUT_REPORT-FORMAT':'sarif','INPUT_REPORT-DIR':dir,'INPUT_POST-REPORT':'false','INPUT_FULL-REPORT':'false','INPUT_SAFE-HARBOR':'false','INPUT_TIMEOUT-MS':'2000','INPUT_POLL-INTERVAL-MS':'10'};
    delete env.GITHUB_TOKEN;delete env.INPUT_GITHUB_TOKEN;env['INPUT_GITHUB-TOKEN']='';
    const p=spawn(process.execPath,[path.resolve('integrations/upstream/action/dist/index.js')],{env});let out='';p.stdout.on('data',c=>out+=c);p.stderr.on('data',c=>out+=c);p.on('error',reject);p.on('exit',code=>resolve({code,out}));
   });
   assert.equal(r.code,scenario==='empty'?0:1,scenario+'\n'+r.out);
   // setSecret emits a toolkit mask command; exclude that declaration from logs.
   const logs=r.out.split('\n').filter(line=>!line.startsWith('::add-mask::')).join('\n');assert.doesNotMatch(logs,/DO-NOT-LEAK|fixture-action-token/);
   assert.ok(!calls.includes('/api/v1/campaigns'),'no global correlation guess');
   const contents=await fs.readFile(output,'utf8'),text=await fs.readFile(summary,'utf8');assert.doesNotMatch(contents+text,/DO-NOT-LEAK|fixture-action-token/);
   if(['auth','malformed','failed'].includes(scenario)){
    assert.ok(!contents.includes('policy-failed'));assert.deepEqual((await fs.readdir(dir)).filter(f=>f.endsWith('.sarif')),[]);
   }else{
    const sarif=await fs.readFile(path.join(dir,'darkmoon-camp_mine.sarif'),'utf8');assert.doesNotMatch(sarif,/DO-NOT-LEAK|fixture-action-token/);
    assert.equal(JSON.parse(sarif).runs[0].results.length,scenario==='high'?1:0);
    assert.match(contents,new RegExp('policy-failed[^\\n]*\\n'+(scenario==='high'?'true':'false')));
   }
  }
  console.log('PASS bundled GitHub Action: exact identity, findings gate vs tool errors, stale counts, safe toolkit outputs/SARIF and genuine empty completion; comments disabled');
 }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1});
