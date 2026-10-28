const {createHmac}=require('node:crypto');
const assert=require('node:assert/strict');
const {DarkmoonTrigger}=require('../../integrations/upstream/n8n/dist/nodes/DarkmoonTrigger/DarkmoonTrigger.node.js');
(async()=>{
  const secret='offline-receiver-test-secret-123456';
  const node=new DarkmoonTrigger(),state={webhookId:'hook_fixture'};
  let body={id:'evt_fixture',event:'campaign.completed',data:{campaign_id:'camp_fixture',status:'completed'}};
  let payload=JSON.stringify(body),stamp=String(Math.floor(Date.now()/1000));
  const headers={
    'x-darkmoon-event-id':body.id,'x-darkmoon-timestamp':stamp,
    'x-darkmoon-signature':'sha256='+createHmac('sha256',secret).update(payload).digest('hex'),
    'x-darkmoon-signature-v2':'sha256='+createHmac('sha256',secret).update(`${stamp}.${body.id}.${payload}`).digest('hex')
  };
  const receipts=new Set();let replyStatus;const response={status:s=>{replyStatus=s;return response},json:()=>response};
  const context={getCredentials:async()=>({webhookSecret:secret,baseUrl:'http://fixture.invalid',authMethod:'token',token:'test-token'}),getNode:()=>({id:'receiver',name:'Receiver'}),helpers:{httpRequest:async o=>{const id=o.body.event_id,claimed=!receipts.has(id);receipts.add(id);return {statusCode:200,body:{claimed}}}},getResponseObject:()=>response,getRequestObject:()=>({body,rawBody:Buffer.from(payload)}),getWorkflowStaticData:()=>state,getHeaderData:()=>headers,getNodeParameter:()=>[]};
  const first=await node.webhook.call(context);assert.ok(first.workflowData);
  const replay=await node.webhook.call(context);assert.equal(replyStatus,200);assert.equal(replay.workflowData,undefined);
  headers['x-darkmoon-timestamp']='1';const stale=await node.webhook.call(context);assert.equal(replyStatus,401);
  headers['x-darkmoon-timestamp']=stamp;headers['x-darkmoon-event-id']='evt_other';const forged=await node.webhook.call(context);assert.equal(replyStatus,401);
  // Synthetic signed test events must be admitted for replay protection but
  // never launch a campaign, finding or remediation workflow.
  body={id:'evt_test_fixture',event:'webhook.test',synthetic:true,
    data:{synthetic:true,purpose:'delivery_validation'}};
  payload=JSON.stringify(body);
  headers['x-darkmoon-event-id']=body.id;
  headers['x-darkmoon-timestamp']=stamp;
  const sign=()=>{headers['x-darkmoon-signature']='sha256='+createHmac('sha256',secret).update(payload).digest('hex');
    headers['x-darkmoon-signature-v2']='sha256='+createHmac('sha256',secret).update(`${stamp}.${body.id}.${payload}`).digest('hex');};
  sign();
  const validTest=await node.webhook.call(context);
  assert.equal(replyStatus,200);
  assert.equal(validTest.workflowData,undefined);
  const duplicateTest=await node.webhook.call(context);
  assert.equal(replyStatus,200);
  assert.equal(duplicateTest.workflowData,undefined);
  body={id:'evt_test_bad',event:'webhook.test',synthetic:true,data:{synthetic:true,purpose:'campaign.completed'}};
  payload=JSON.stringify(body);headers['x-darkmoon-event-id']=body.id;sign();
  const malformed=await node.webhook.call(context);
  assert.equal(replyStatus,400);
  assert.equal(malformed.workflowData,undefined);
    console.log('PASS: n8n HMAC v2, stale timestamp rejection, replay deduplication and forged event-id rejection and synthetic test isolation');
})().catch(e=>{process.stderr.write(e.stack+'\n');process.exitCode=1;});
