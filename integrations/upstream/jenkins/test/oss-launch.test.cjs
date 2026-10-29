"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");
const { spawnSync } = require("node:child_process");
const CLI = path.resolve(__dirname, "../target/jenkins-bundled-cli/darkmoon-client/darkmoon-ci.cjs");
const { OssLocalBackend } = require(CLI);
const { launchProducer } = require("../cli/oss-launch.cjs");
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function fixture(t, body) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "jenkins-launch-"));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  await fs.mkdir(path.join(dir, "campaigns"));
  await fs.mkdir(path.join(dir, "vulnerabilities"));
  const script = path.join(dir, "engine.cjs");
  await fs.writeFile(script, `#!/usr/bin/env node\nconst fs=require('node:fs');
const root=process.env.TEST_UNUSED || 'ses_exact_root';
const emit=(id=root)=>console.log(JSON.stringify({type:'step_start',sessionID:id,part:{type:'step-start',sessionID:id}}));
const campaign=(id,session=root)=>{fs.writeFileSync('campaigns/'+id+'.json',JSON.stringify({id,opencode_session_id:session,status:'completed',is_subagent:false,stats:{total_findings:0}}));fs.writeFileSync('vulnerabilities/'+id+'.json','[]')};
${body}\n`, { mode: 0o700 });
  return { dir, script, backend: new OssLocalBackend({ dataDir: dir, scriptPath: script, launchTimeoutMs: 1500 }) };
}
async function finished(state) {
  let timer;
  try { return await Promise.race([state.done, new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error("Launcher test deadline")), 5000);
  })]); } finally { clearTimeout(timer); }
}
async function launched(f, program = "same program") {
  const { correlation } = await f.backend.launchCampaign({ target: "offline.invalid", program });
  await finished(f.backend.launches.get(correlation.nonce));
  return correlation;
}

test("actual bundled backend uses producer root despite unrelated new files or timestamps", async t => {
  const f = await fixture(t, `
assertFlags();emit();campaign('camp_exact');campaign('camp_unrelated','ses_foreign');
fs.utimesSync('campaigns/camp_unrelated.json',new Date('2099-01-01'),new Date('2099-01-01'));
function assertFlags(){if(process.argv.slice(-2).join(' ')!=='--format json')process.exit(3)}
`);
  const ref = await launched(f);
  assert.equal(await f.backend.resolveCampaignId(ref), "camp_exact");
  assert.equal((await f.backend.getCampaignStatus(ref)).status, "completed");
  assert.equal((await f.backend.getCampaignStatus(ref)).severity.total, 0);
});

test("concurrent same-program launches retain independent roots in the shared data directory", async t => {
  const f = await fixture(t, `const own='ses_'+process.pid;emit(own);campaign('camp_'+process.pid,own);`);
  const refs = await Promise.all([launched(f), launched(f)]);
  assert.notEqual(refs[0].nonce, refs[1].nonce);
  const ids = await Promise.all(refs.map(ref => f.backend.resolveCampaignId(ref)));
  assert.notEqual(ids[0], ids[1]);
  for (let i=0;i<2;i++) {
    const raw=JSON.parse(await fs.readFile(path.join(f.dir,'campaigns',ids[i]+'.json')));
    assert.equal(raw.opencode_session_id,f.backend.launches.get(refs[i].nonce).rootSessionId);
  }
});

test("a pre-existing matching campaign cannot be replayed as a new launch", async t => {
  const f = await fixture(t, "emit()");
  await fs.writeFile(path.join(f.dir,'campaigns/camp_old.json'),JSON.stringify({id:'camp_old',opencode_session_id:'ses_exact_root',status:'completed'}));
  await fs.writeFile(path.join(f.dir,'vulnerabilities/camp_old.json'),'[]');
  const ref = await launched(f);
  await assert.rejects(f.backend.getCampaignStatus(ref));
});

for (const [name, body] of [
  ["missing identity", "campaign('camp_foreign')"],
  ["only a foreign campaign", "emit();campaign('camp_foreign','ses_foreign')"],
  ["two campaigns bound to one root", "emit();campaign('camp_a');campaign('camp_b')"],
  ["conflicting producer roots", "emit();campaign('camp_a');emit('ses_other')"],
  ["failed producer with a completed campaign", "emit();campaign('camp_a');process.exitCode=1"],
  ["nested marker text is not identity", "console.log(JSON.stringify({type:'text',sessionID:'ses_exact_root',part:{text:JSON.stringify({type:'step_start',sessionID:'ses_exact_root'})}}));campaign('camp_a')"],
  ["inconsistent event/part identity", "console.log(JSON.stringify({type:'step_start',sessionID:'ses_exact_root',part:{type:'step-start',sessionID:'ses_foreign'}}));campaign('camp_a')"],
  ["campaign filename/id mismatch", "emit();campaign('camp_a');fs.renameSync('campaigns/camp_a.json','campaigns/camp_b.json')"],
  ["symlink campaign", "emit();campaign('camp_a');fs.renameSync('campaigns/camp_a.json','hidden.json');fs.symlinkSync('../hidden.json','campaigns/camp_a.json')"],
  ["hard-linked campaign", "emit();campaign('camp_a');fs.linkSync('campaigns/camp_a.json','hidden.json')"],
  ["oversized campaign", "emit();campaign('camp_a');fs.appendFileSync('campaigns/camp_a.json',' '.repeat(4194305))"],
]) test(name + " cannot produce a findings verdict", async t => {
  const f = await fixture(t, body);
  const ref = await launched(f);
  await assert.rejects(f.backend.getCampaignStatus(ref));
});

test("completed campaign does not win before producer exit; late identity conflict fails", async t => {
  const f = await fixture(t, "emit();campaign('camp_a');const timer=setInterval(()=>{if(fs.existsSync('continue')){clearInterval(timer);emit('ses_other')}},10)");
  const { correlation } = await f.backend.launchCampaign({ target: "offline.invalid" });
  const state = f.backend.launches.get(correlation.nonce);
  for (let i=0;i<100;i++) {
    try { await fs.access(path.join(f.dir,'campaigns/camp_a.json'));break; }
    catch { await sleep(10); }
  }
  await fs.access(path.join(f.dir,'campaigns/camp_a.json'));
  assert.equal(await f.backend.resolveCampaignId(correlation), null);
  await fs.writeFile(path.join(f.dir,'continue'),'');
  await finished(state);
  await assert.rejects(f.backend.getCampaignStatus(correlation));
});

test("large stdout/stderr is discarded; split and final non-newline identity frames work", async t => {
  const f = await fixture(t, `
process.stdout.write('PRIVATE_EVIDENCE'.repeat(100000)+'\\n');
process.stderr.write('PRIVATE_STDERR'.repeat(100000));
campaign('camp_a');const event=JSON.stringify({type:'step_start',sessionID:root,part:{type:'step-start',sessionID:root}});
process.stdout.write(event.slice(0,19));setTimeout(()=>process.stdout.write(event.slice(19)),30);
`);
  const ref = await launched(f);
  assert.equal(await f.backend.resolveCampaignId(ref), "camp_a");
});

test("spawn failures and hung producers fail within their deadline", async t => {
  const missing = launchProducer({ cmd: "/no/such/jenkins-test-engine", args: [], cwd: os.tmpdir(), timeoutMs: 500 });
  assert.equal((await finished(missing)).status, "failed");
  const f = await fixture(t, "emit();campaign('camp_a');setInterval(()=>{},100)");
  f.backend.cfg.launchTimeoutMs = 200;
  const ref = await launched(f);
  await assert.rejects(f.backend.getCampaignStatus(ref));
});

test("a completed binding cannot silently change and an unowned handle is rejected", async t => {
  const f = await fixture(t, "emit();campaign('camp_a')");
  const ref = await launched(f);
  assert.equal(await f.backend.resolveCampaignId(ref), "camp_a");
  await fs.rename(path.join(f.dir,"campaigns/camp_a.json"),path.join(f.dir,"old.json"));
  await fs.writeFile(path.join(f.dir,"campaigns/camp_b.json"),JSON.stringify({id:"camp_b",opencode_session_id:"ses_exact_root"}));
  await assert.rejects(f.backend.resolveCampaignId(ref));
  await assert.rejects(f.backend.resolveCampaignId({...ref,nonce:"not-owned"}));
});

test("standalone launch still detaches; private producer output never reaches CLI stdout/stderr", async t => {
  const f = await fixture(t, "console.log('PRIVATE_EVIDENCE');setTimeout(()=>{emit();campaign('camp_background')},250)");
  const run = spawnSync(process.execPath,[CLI,"launch","--mode","oss","--oss-data-dir",f.dir,"--oss-script",f.script,"--target","offline.invalid","--json"],{encoding:"utf8",timeout:5000});
  assert.equal(run.status,0,run.stderr);
  assert.equal(JSON.parse(run.stdout).campaignId,null);
  assert.ok(!(run.stdout+run.stderr).includes("PRIVATE_EVIDENCE"));
  for(let i=0;i<100;i++) {
    try { await fs.access(path.join(f.dir,"campaigns/camp_background.json"));return; }
    catch { await sleep(20); }
  }
  assert.fail("Detached producer did not complete");
});

test("status rechecks the root if campaign storage changes after resolution", async t => {
  const f = await fixture(t, "emit();campaign('camp_a')");
  const ref = await launched(f);
  const read = f.backend.readCampaignFile.bind(f.backend);
  let first = true;
  f.backend.readCampaignFile = async id => {
    const raw = await read(id);
    if (first) {
      first = false;
      await fs.writeFile(path.join(f.dir,'campaigns',id+'.json'),JSON.stringify({...raw,opencode_session_id:'ses_foreign'}));
    }
    return raw;
  };
  await assert.rejects(f.backend.getCampaignStatus(ref));
});

test("one-shot CLI returns only the exact completed campaign verdict", async t => {
  const f = await fixture(t, "emit();campaign('camp_a');campaign('camp_foreign','ses_foreign')");
  const run = spawnSync(process.execPath,[CLI,'run','--mode','oss','--oss-data-dir',f.dir,'--oss-script',f.script,
    '--target','offline.invalid','--timeout','2','--poll','0.02','--json'],{encoding:'utf8',timeout:5000});
  assert.equal(run.status,0,run.stderr);
  const verdict = JSON.parse(run.stdout);
  assert.equal(verdict.campaignId,'camp_a');
  assert.equal(verdict.total,0);
  assert.equal(verdict.verdict,'pass');
});
