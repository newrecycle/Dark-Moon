const {createHmac}=require('node:crypto');
const assert=require('node:assert/strict');
const {DarkmoonTrigger}=require('../../integrations/upstream/n8n/dist/nodes/DarkmoonTrigger/DarkmoonTrigger.node.js');
(async()=>{
  const secret='offline-receiver-test-secret-123456';
  const node=new DarkmoonTrigger(),state={};
  const body={id:'evt_fixture',event:'campaign.completed',data:{campaign_id:'camp_fixture',status:'completed'}};
  const payload=JSON.stringify(body),stamp=String(Math.floor(Date.now()/1000));
  const headers={
    'x-darkmoon-event-id':body.id,'x-darkmoon-timestamp':stamp,
    'x-darkmoon-signature':'sha256='+createHmac('sha256',secret).update(payload).digest('hex'),
    'x-darkmoon-signature-v2':'sha256='+createHmac('sha256',secret).update(`${stamp}.${body.id}.${payload}`).digest('hex')
  };
  let replyStatus;const response={status:s=>{replyStatus=s;return response},json:()=>response};
  const context={getCredentials:async()=>({webhookSecret:secret}),getResponseObject:()=>response,getRequestObject:()=>({body,rawBody:Buffer.from(payload)}),getWorkflowStaticData:()=>state,getHeaderData:()=>headers,getNodeParameter:()=>[]};
  const first=await node.webhook.call(context);assert.ok(first.workflowData);
  const replay=await node.webhook.call(context);assert.equal(replyStatus,200);assert.equal(replay.workflowData,undefined);
  headers['x-darkmoon-timestamp']='1';const stale=await node.webhook.call(context);assert.equal(replyStatus,401);
  headers['x-darkmoon-timestamp']=stamp;headers['x-darkmoon-event-id']='evt_other';const forged=await node.webhook.call(context);assert.equal(replyStatus,401);
  console.log('PASS: n8n HMAC v2, stale timestamp rejection, replay deduplication and forged event-id rejection');
})().catch(e=>{process.stderr.write(e.stack+'\n');process.exitCode=1;});
