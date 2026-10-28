// Run the built portable CLI against owned loopback responses; never an assessment.
const assert=require('node:assert/strict'),http=require('node:http'),path=require('node:path'),{spawn}=require('node:child_process');
(async()=>{
 let status='completed',findings=[{id:'f_mine',campaign_id:'camp_mine',severity:'high'}],failure=0;
 const calls=[];
 const server=http.createServer((req,res)=>{
  req.resume();const route=new URL(req.url,'http://localhost').pathname;calls.push(route);
  const send=(body,code=200)=>{res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(body));};
  if(route==='/api/v1/system/info')return send({edition:'pro',api_version:'1.0.0'});
  if(req.headers.authorization!=='Bearer fixture-cli-token')return send({},401);
  if(route==='/api/v1/run/campaign')return send({run_id:'run_mine',campaign_id:'camp_mine'});
  if(route==='/api/v1/campaigns/camp_mine')return send({data:{id:'camp_mine',status,stats:{total_findings:0}}});
  if(route==='/api/v1/vulnerabilities'){
   if(failure===200){res.writeHead(200);res.end('{');return;}
   return send(failure?{detail:'PRIVATE-ERROR-BODY'}:{data:findings},failure||200);
  }
  return send({data:[{id:'camp_unrelated',status:'completed'}]});
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const url='http://127.0.0.1:'+server.address().port;
 const invoke=args=>new Promise((resolve,reject)=>{
  const p=spawn(process.execPath,[path.resolve('integrations/upstream/client/dist/cli/darkmoon-ci.cjs'),...args,'--mode','pro','--pro-url',url,'--timeout','2','--poll','0.01','--json'],{env:{...process.env,DARKMOON_PRO_TOKEN:'fixture-cli-token'}});
  let out='',err='';p.stdout.on('data',c=>out+=c);p.stderr.on('data',c=>err+=c);p.on('error',reject);p.on('exit',code=>resolve({code,out,err}));
 });
 try{
  let r=await invoke(['run','--target','owned.invalid']);assert.equal(r.code,2,r.err);assert.equal(JSON.parse(r.out).campaignId,'camp_mine');assert.ok(!calls.includes('/api/v1/campaigns'));
  r=await invoke(['wait','camp_mine']);assert.equal(r.code,2,'cached zero must not suppress a high finding');
  for(const value of ['failed','interrupted','timed_out','aborted','cancelled']){
   status=value;findings=[];r=await invoke(['wait','camp_mine']);assert.equal(r.code,1,'non-successful assessment '+value+' is a tool error');assert.ok(!r.out.includes('"pass"'));
  }
  status='completed';
  for(const value of [200,401,500]){failure=value;r=await invoke(['wait','camp_mine']);assert.equal(r.code,1,'finding-read errors fail closed');assert.doesNotMatch(r.err,/PRIVATE-ERROR-BODY|fixture-cli-token/);}
  failure=0;r=await invoke(['wait','camp_mine']);assert.equal(r.code,0);assert.equal(JSON.parse(r.out).total,0);
  console.log('PASS built CLI: explicit launch identity, stale-zero findings, five failed/stopped states, malformed/auth/server errors and genuine empty completion');
 }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1});
