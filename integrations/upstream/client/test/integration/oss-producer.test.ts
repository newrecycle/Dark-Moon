import {afterEach, describe, expect, it} from "vitest";
import {mkdtemp, mkdir, writeFile, rm} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {OssLocalBackend, CorrelationFailed, SchemaInvalid} from "../../src/index.js";
const roots:string[]=[];
afterEach(async()=>{for(const root of roots.splice(0))await rm(root,{recursive:true,force:true});});
async function producer(mode:string) {
 const dir=await mkdtemp(path.join(os.tmpdir(),"dm-producer-"));roots.push(dir);
 await mkdir(path.join(dir,"campaigns"));
 const program=`const fs=require('fs');
 const save=(id,session)=>fs.writeFileSync('campaigns/'+id+'.json',JSON.stringify({id,opencode_session_id:session,is_subagent:false,status:'completed'}));
 save('camp_unrelated','ses_unrelated');
 ${mode==='unrelated'?"":"save('camp_owned','ses_owned');"}
 ${mode==='unbound'?"":"console.log(JSON.stringify({type:'step_start',sessionID:'ses_owned',part:{type:'step-start',sessionID:'ses_owned'}}));"}
 ${mode==='conflicting'?"console.log(JSON.stringify({type:'text',sessionID:'ses_other'}));":""}
 process.exitCode=${mode==='failed'?1:0};`;
 await writeFile(path.join(dir,"producer.cjs"),program);
 const backend=new OssLocalBackend({dataDir:dir,cwd:dir,launchTemplate:[process.execPath,path.join(dir,"producer.cjs")],timeoutMs:2000});
 const {correlation}=await backend.launchCampaign({target:'owned.invalid'});
 for(let i=0;i<200&&correlation.producerStatus==='running';i++)await new Promise(r=>setTimeout(r,10));
 expect(correlation.producerStatus).not.toBe('running');
 return {backend,correlation,dir};
}
describe('Own OSS producer binding',()=>{
 it('ignores unrelated newer campaigns and rechecks a changed binding',async()=>{
  const {backend,correlation,dir}=await producer('owned');
  expect(await backend.resolveCampaignId(correlation)).toBe('camp_owned');
  await writeFile(path.join(dir,'campaigns/camp_owned.json'),JSON.stringify({id:'camp_owned',opencode_session_id:'ses_other',session_id:'ses_owned',is_subagent:false}));
  await expect(backend.resolveCampaignId(correlation)).rejects.toBeInstanceOf(CorrelationFailed);
 });
 it('does not fall back to a sole unrelated campaign',async()=>{
  const {backend,correlation}=await producer('unrelated');
  expect(await backend.resolveCampaignId(correlation)).toBeNull();
  expect(correlation.campaignId).toBeNull();
 });
 it('bounds a stalled producer and rejects invalid deadlines before launch',async()=>{
  const dir=await mkdtemp(path.join(os.tmpdir(),"dm-producer-timeout-"));roots.push(dir);
  const config={dataDir:dir,cwd:dir,launchTemplate:[process.execPath,'-e','setInterval(()=>{},1000)']};
  await expect(new OssLocalBackend({...config,timeoutMs:0}).launchCampaign({target:'owned.invalid'})).rejects.toBeInstanceOf(SchemaInvalid);
  const backend=new OssLocalBackend({...config,timeoutMs:50});
  const {correlation}=await backend.launchCampaign({target:'owned.invalid'});
  for(let i=0;i<100&&correlation.producerStatus==='running';i++)await new Promise(r=>setTimeout(r,10));
  await expect(backend.resolveCampaignId(correlation)).rejects.toBeInstanceOf(CorrelationFailed);
 });
 for(const mode of ['failed','conflicting','unbound'])it('rejects '+mode+' producer identity',async()=>{
  const {backend,correlation}=await producer(mode);
  await expect(backend.resolveCampaignId(correlation)).rejects.toBeInstanceOf(CorrelationFailed);
 });
});
