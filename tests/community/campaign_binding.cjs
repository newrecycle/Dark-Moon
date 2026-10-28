// Node 24 executes the production TypeScript plugin via native type stripping.
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
(async () => {
  const { DarkmoonCampaignPlugin } = await import(pathToFileURL(path.resolve('conf/plugins/darkmoon-campaign.ts')));
  const sessions = new Map([
    ['ses_SAMEPRE1tailA', {}], ['ses_SAMEPRE1tailB', {}],
    ['ses_childA', {parentID:'ses_SAMEPRE1tailA'}],
    ['ses_grandchildA', {parentID:'ses_childA'}],
  ]);
  const calls = [];
  const client = {session:{get:async ({path,signal}) => {
    assert.ok(signal instanceof AbortSignal); calls.push(path.id);
    return sessions.has(path.id) ? {data:{id:path.id,...sessions.get(path.id)}} : {error:'not found'};
  }}};
  const hook = (await DarkmoonCampaignPlugin({client}))['tool.execute.before'];
  const bind = async id => {
    const output = {args:{session_id:'privacy-unchanged',opencode_session_id:'model-forged'}};
    await hook({tool:'darkmoon_dashboard_init_campaign',sessionID:id},output);
    assert.equal(output.args.session_id,'privacy-unchanged');
    return output.args.opencode_session_id;
  };
  assert.deepEqual(await Promise.all(['ses_SAMEPRE1tailA','ses_SAMEPRE1tailB','ses_grandchildA'].map(bind)),
    ['ses_SAMEPRE1tailA','ses_SAMEPRE1tailB','ses_SAMEPRE1tailA']);
  const n = calls.length, untouched = {args:{session_id:'privacy'}};
  await hook({tool:'other_dashboard_init_campaign',sessionID:'ses_missing'},untouched);
  assert.equal(calls.length,n); assert.deepEqual(untouched.args,{session_id:'privacy'});
  await assert.rejects(bind('ses_missing'),/Cannot bind/);
  sessions.set('ses_a',{parentID:'ses_b'});sessions.set('ses_b',{parentID:'ses_a'});
  await assert.rejects(bind('ses_a'),/Cyclic/);
  await assert.rejects(bind('../bad'),/Invalid/);
  const failureHook=(await DarkmoonCampaignPlugin({client:{session:{get:async()=>{throw new Error('native offline')}}}}))['tool.execute.before'];
  await assert.rejects(failureHook({tool:'darkmoon_dashboard_init_campaign',sessionID:'ses_root'}, {args:{}}),/native offline/);
  console.log('Campaign plugin: exact roots, nested children, concurrent bindings, privacy preservation and fail-closed API checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
