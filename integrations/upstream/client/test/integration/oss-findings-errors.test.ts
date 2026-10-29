import {it, expect} from 'vitest';
import {promises as fs} from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import {OssLocalBackend, SchemaInvalid} from '../../src/index.js';

it('missing, malformed and foreign OSS findings cannot become a clean result',async()=>{
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'dm-findings-'));
  try {
    await fs.mkdir(path.join(dir,'campaigns'));await fs.mkdir(path.join(dir,'vulnerabilities'));
    await fs.writeFile(path.join(dir,'campaigns/camp_owned.json'),JSON.stringify({id:'camp_owned',status:'completed',stats:{total_findings:12,critical:12}}));
    const backend=new OssLocalBackend({dataDir:dir});
    await expect(backend.getCampaign('camp_owned')).rejects.toBeInstanceOf(SchemaInvalid);
    for(const value of ['not json','{}',JSON.stringify([{id:'foreign',campaign_id:'camp_other',severity:'high'}])]) {
      await fs.writeFile(path.join(dir,'vulnerabilities/camp_owned.json'),value);
      await expect(backend.getCampaign('camp_owned')).rejects.toBeInstanceOf(SchemaInvalid);
    }
    await fs.writeFile(path.join(dir,'vulnerabilities/camp_owned.json'),'[]');
    expect((await backend.getCampaign('camp_owned')).severity.total).toBe(0);
  } finally {await fs.rm(dir,{recursive:true,force:true});}
});
