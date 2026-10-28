// Exercise the production plugin against an actual disposable OpenCode server.
// No model inference, real account login or target scanning.
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const path = require('node:path');
(async () => {
  const base = process.env.DARKMOON_OPENCODE_TEST_URL;
  const authorization = process.env.DARKMOON_OPENCODE_TEST_AUTH;
  if (!base || !authorization) throw new Error('Disposable native server URL and authorization required');
  const request = async (route, method='GET', body) => {
    const response=await fetch(base+route,{method,headers:{authorization,'Content-Type':'application/json'},
      body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(15000)});
    if (!response.ok) throw new Error(`Native session API returned HTTP ${response.status}`);
    return response.json();
  };
  const created=[];
  try {
    const create = async parentID => {
      const session=await request('/session','POST',{title:'Disposable campaign identity validation',...(parentID?{parentID}:{})});
      created.push(session.id); return session;
    };
    const a=await create(), child=await create(a.id), grandchild=await create(child.id), b=await create();
    const {DarkmoonCampaignPlugin}=await import(pathToFileURL(path.resolve('conf/plugins/darkmoon-campaign.ts')));
    const hook=(await DarkmoonCampaignPlugin({client:{session:{get:async ({path})=>({data:await request('/session/'+encodeURIComponent(path.id))})}}}))['tool.execute.before'];
    const bind=async sessionID=>{
      const output={args:{session_id:'unchanged-privacy',opencode_session_id:'forged-by-model'}};
      await hook({tool:'darkmoon_dashboard_init_campaign',sessionID},output);
      assert.equal(output.args.session_id,'unchanged-privacy');
      return output.args.opencode_session_id;
    };
    assert.deepEqual(await Promise.all([a.id,child.id,grandchild.id,b.id].map(bind)),[a.id,a.id,a.id,b.id]);
    assert.equal(await bind(a.id),a.id);
    console.log('Native campaign binding passed: actual root/child/grandchild sessions remain isolated from a newer root.');
  } finally {
    for (const id of created.reverse()) await request('/session/'+encodeURIComponent(id),'DELETE');
  }
})().catch(error=>{console.error(error.message);process.exitCode=1});
